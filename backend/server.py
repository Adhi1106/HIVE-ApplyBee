from fastapi import FastAPI, APIRouter, HTTPException, WebSocket
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import asyncio
import logging
from pathlib import Path

from models import Mission, MissionCreate, LocalMissionCreate, now_iso
from orchestrator import Orchestrator
from local_orchestrator import LocalOrchestrator
from runner_hub import hub
from provider import provider

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="HIVE")
api_router = APIRouter(prefix="/api")

orchestrator = Orchestrator(db)
local_orchestrator = LocalOrchestrator(db)

DEFAULT_USER = "default-user"
STARTING_CREDITS = 500

EXAMPLE_MISSIONS = [
    "Analyze why a fictional SaaS company's customer churn increased.",
    "Create a launch strategy for a new student-focused startup.",
    "Analyze a dataset and identify important trends.",
    "Plan a marketing campaign for a new product.",
]
DEMO_MISSION = "Analyze a fictional SaaS product whose customer churn has increased by 20% and determine the likely causes and recommended actions."


async def ensure_user():
    u = await db.users.find_one({"id": DEFAULT_USER})
    if not u:
        await db.users.insert_one({"id": DEFAULT_USER, "name": "HIVE Operator", "credits": STARTING_CREDITS, "created_at": now_iso()})


@app.on_event("startup")
async def startup():
    await ensure_user()


@api_router.get("/")
async def root():
    return {"message": "HIVE online", "live_ai": provider.live_available()}


@api_router.get("/examples")
async def examples():
    return {"examples": EXAMPLE_MISSIONS, "demo": DEMO_MISSION}


@api_router.get("/credits")
async def credits():
    await ensure_user()
    u = await db.users.find_one({"id": DEFAULT_USER}, {"_id": 0})
    return u


@api_router.post("/missions")
async def create_mission(body: MissionCreate):
    goal = (body.goal or "").strip()
    if len(goal) < 5:
        raise HTTPException(status_code=400, detail="Please describe what you want your workforce to accomplish.")
    if _is_unsafe(goal):
        raise HTTPException(status_code=400, detail="This mission requests unsafe or disallowed actions and was blocked by HIVE safety policy.")
    await ensure_user()
    u = await db.users.find_one({"id": DEFAULT_USER})
    if (u or {}).get("credits", 0) <= 0:
        raise HTTPException(status_code=402, detail="Out of credits. Add more to launch another mission.")
    mission = Mission(goal=goal, user_id=DEFAULT_USER, provider="openai" if provider.live_available() else "mock")
    await db.missions.insert_one(mission.model_dump())
    asyncio.create_task(orchestrator.run(mission.id, goal))
    return {"id": mission.id, "status": mission.status}


@api_router.get("/missions")
async def list_missions():
    missions = await db.missions.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"missions": missions}


@api_router.get("/missions/{mission_id}")
async def get_mission(mission_id: str):
    mission = await db.missions.find_one({"id": mission_id}, {"_id": 0})
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    agents = await db.agents.find({"mission_id": mission_id}, {"_id": 0}).to_list(100)
    tasks = await db.tasks.find({"mission_id": mission_id}, {"_id": 0}).to_list(100)
    events = await db.mission_events.find({"mission_id": mission_id}, {"_id": 0}).sort("seq", 1).to_list(1000)
    artifact = None
    if mission.get("final_artifact_id"):
        artifact = await db.artifacts.find_one({"id": mission["final_artifact_id"]}, {"_id": 0})
    return {"mission": mission, "agents": agents, "tasks": tasks, "events": events, "artifact": artifact}


@api_router.get("/workforce")
async def workforce():
    agents = await db.agents.find({"is_manager": False}, {"_id": 0}).sort("created_at", -1).to_list(300)
    missions = await db.missions.find({}, {"_id": 0, "id": 1, "title": 1, "status": 1}).to_list(300)
    mmap = {m["id"]: m for m in missions}
    for a in agents:
        a["mission_title"] = mmap.get(a["mission_id"], {}).get("title", "")
        a["mission_status"] = mmap.get(a["mission_id"], {}).get("status", "")
    return {"agents": agents}


def _is_unsafe(goal: str) -> bool:
    g = goal.lower()
    banned = ["hack", "ddos", "malware", "ransomware", "steal", "credit card", "exploit",
              "phishing", "keylogger", "bypass authentication", "delete all files",
              "rm -rf", "sql injection", "botnet", "crack password"]
    return any(b in g for b in banned)


# ============================ HIVE Local Runner ============================
DEMO_FILES = {
    "app.py": "import os\nimport pandas as pd\nfrom model import predict\n\n\ndef main():\n    df = pd.read_csv('data.csv')\n    print(predict(df))\n\n\nif __name__ == '__main__':\n    main()\n",
    "model.py": "import numpy as np\n\n\ndef predict(df):\n    return np.mean(df.select_dtypes('number').values)\n",
    "data.csv": "id,value\n1,10\n2,20\n3,30\n",
    "notes.txt": "TODO: clean up this project. Files are everywhere.\n",
    "report.pdf": "%PDF-1.4 (placeholder report file)\nQuarterly summary.\n",
    "README_old.md": "# Old Readme\nThis is outdated and messy.\n",
}


@api_router.websocket("/runner/ws")
async def runner_ws(ws: WebSocket):
    await hub.handle(ws)


@api_router.post("/runner/pair")
async def runner_pair():
    s = hub.create_session()
    return s.public()


@api_router.get("/runner/session/{sid}")
async def runner_session(sid: str):
    s = hub.get(sid)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s.public()


@api_router.post("/runner/session/{sid}/approve")
async def runner_approve(sid: str):
    if not hub.approve(sid):
        raise HTTPException(status_code=400, detail="Runner not connected for this session.")
    return hub.get(sid).public()


@api_router.get("/runner/session/{sid}/tree")
async def runner_tree(sid: str):
    try:
        return await hub.call_tool(sid, "list", {"path": "."})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@api_router.post("/runner/session/{sid}/seed-demo")
async def runner_seed_demo(sid: str):
    s = hub.get(sid)
    if not s or s.status != "approved":
        raise HTTPException(status_code=400, detail="Approve a connected workspace first.")
    for name, content in DEMO_FILES.items():
        await hub.call_tool(sid, "write", {"path": name, "content": content})
    return await hub.call_tool(sid, "list", {"path": "."})


@api_router.post("/missions/local")
async def create_local_mission(body: LocalMissionCreate):
    s = hub.get(body.session_id)
    if not s or s.status != "approved":
        raise HTTPException(status_code=400, detail="Connect and approve a workspace runner first.")
    await ensure_user()
    u = await db.users.find_one({"id": DEFAULT_USER})
    if (u or {}).get("credits", 0) <= 0:
        raise HTTPException(status_code=402, detail="Out of credits.")
    mission = Mission(goal=body.goal, user_id=DEFAULT_USER, type="local",
                      session_id=body.session_id, workspace=s.workspace, provider="runner")
    await db.missions.insert_one(mission.model_dump())
    asyncio.create_task(local_orchestrator.run(mission.id, body.goal, body.session_id))
    return {"id": mission.id, "status": mission.status}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("hive")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
