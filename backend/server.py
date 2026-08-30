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
DEFAULT_PROJECT = "ai-workforce"

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


async def ensure_default_project():
    p = await db.projects.find_one({"id": DEFAULT_PROJECT})
    if not p:
        await db.projects.insert_one({"id": DEFAULT_PROJECT, "user_id": DEFAULT_USER, "name": "AI Workforce (Demo)",
                                      "kind": "demo", "workspace": None, "session_id": None, "created_at": now_iso()})


async def get_or_create_local_project(session):
    p = await db.projects.find_one({"kind": "local", "workspace": session.workspace})
    if p:
        return p
    name = (session.workspace or "Local Project").rstrip("/").split("/")[-1] or "Local Project"
    doc = {"id": __import__("uuid").uuid4().hex[:12], "user_id": DEFAULT_USER, "name": name,
           "kind": "local", "workspace": session.workspace, "session_id": session.id, "created_at": now_iso()}
    await db.projects.insert_one(doc)
    return doc


@app.on_event("startup")
async def startup():
    hub.attach_db(db)
    await ensure_user()
    await ensure_default_project()


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


@api_router.post("/credits/renew")
async def renew_credits():
    """Demo-only: reset the demo credit balance. A real subscription/billing
    provider will replace this endpoint later (kept modular on purpose)."""
    await ensure_user()
    await db.users.update_one({"id": DEFAULT_USER}, {"$set": {"credits": STARTING_CREDITS}})
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
    await ensure_default_project()
    mission = Mission(goal=goal, user_id=DEFAULT_USER, mode="demo", project_id=DEFAULT_PROJECT,
                      provider="openai" if provider.live_available() else "mock")
    await db.missions.insert_one(mission.model_dump())
    asyncio.create_task(orchestrator.run(mission.id, goal))
    return {"id": mission.id, "status": mission.status}


@api_router.get("/projects")
async def list_projects():
    await ensure_default_project()
    projects = await db.projects.find({}, {"_id": 0}).sort("created_at", 1).to_list(200)
    counts = {}
    for m in await db.missions.find({}, {"_id": 0, "project_id": 1}).to_list(1000):
        counts[m.get("project_id")] = counts.get(m.get("project_id"), 0) + 1
    for p in projects:
        p["mission_count"] = counts.get(p["id"], 0)
    return {"projects": projects}


@api_router.get("/projects/{project_id}/missions")
async def project_missions(project_id: str):
    missions = await db.missions.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"missions": missions}


@api_router.get("/missions")
async def list_missions(project_id: str | None = None):
    q = {"project_id": project_id} if project_id else {}
    missions = await db.missions.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
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


@api_router.get("/missions/{mission_id}/agents/{agent_id}")
async def worker_detail(mission_id: str, agent_id: str):
    """Structured worker drill-down built ONLY from canonical mission events + tasks
    (no hidden reasoning, no hardcoded descriptions)."""
    agent = await db.agents.find_one({"id": agent_id, "mission_id": mission_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Worker not found")
    tasks = await db.tasks.find({"mission_id": mission_id, "owner_agent_id": agent_id}, {"_id": 0}).to_list(100)
    all_events = await db.mission_events.find({"mission_id": mission_id}, {"_id": 0}).sort("seq", 1).to_list(2000)
    events = [e for e in all_events if e.get("worker_id") == agent_id or e.get("actor") == agent.get("role")]
    files, tools, handoffs, issues, recovery = [], [], [], [], []
    for e in events:
        for f in (e.get("files_affected") or []):
            if f not in files:
                files.append(f)
        if e.get("tool") and e["tool"] not in tools:
            tools.append(e["tool"])
        if e.get("handoff_to"):
            handoffs.append({"to": e["handoff_to"], "what": e.get("output_summary") or e.get("message"), "at": e.get("created_at")})
        if e.get("level") in ("warning", "error") or e.get("error"):
            issues.append({"message": e.get("error") or e.get("message"), "at": e.get("created_at")})
        if e.get("type") in ("RECOVERY_STARTED", "RECOVERY_COMPLETED"):
            recovery.append({"type": e["type"], "message": e.get("message"), "at": e.get("created_at")})
    verified = any(t.get("status") == "verified" for t in tasks) or any(
        e.get("type") in ("VERIFICATION_PASSED", "REVIEW_PASSED") and e.get("worker_id") == agent_id for e in all_events)
    summary = {
        "input": [{"task": t["title"], "context": t.get("description")} for t in tasks],
        "actions": [{"type": e["type"], "action": e.get("action"), "message": e["message"], "at": e.get("created_at")} for e in events if e.get("action") or e["type"] in ("WORKER_STARTED", "WORKER_COMPLETED", "TOOL_EXECUTED", "RECOVERY_STARTED", "RECOVERY_COMPLETED")],
        "tools": tools,
        "files": files,
        "output": [{"task": t["title"], "summary": t.get("summary"), "output": t.get("output")} for t in tasks],
        "handoffs": handoffs,
        "issues": issues,
        "recovery": recovery,
        "verified": verified,
        "timeline": [{"type": e["type"], "message": e["message"], "level": e.get("level"), "at": e.get("created_at")} for e in events],
    }
    return {"agent": agent, "tasks": tasks, "events": events, "summary": summary}


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
    s = await hub.create_session()
    return s.public()


@api_router.get("/runner/session/{sid}")
async def runner_session(sid: str):
    s = await hub.get(sid)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s.public()


@api_router.post("/runner/session/{sid}/approve")
async def runner_approve(sid: str):
    if not await hub.approve(sid):
        raise HTTPException(status_code=400, detail="Runner not connected for this session.")
    s = await hub.get(sid)
    return s.public()


@api_router.get("/runner/session/{sid}/tree")
async def runner_tree(sid: str):
    try:
        return await hub.call_tool(sid, "list", {"path": "."})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@api_router.post("/runner/session/{sid}/seed-demo")
async def runner_seed_demo(sid: str):
    s = await hub.get(sid)
    if not s or s.status != "approved":
        raise HTTPException(status_code=400, detail="Approve a connected workspace first.")
    for name, content in DEMO_FILES.items():
        await hub.call_tool(sid, "write", {"path": name, "content": content})
    return await hub.call_tool(sid, "list", {"path": "."})


@api_router.get("/runner/download")
async def runner_download():
    """Serve the CURRENT, real persistent runner.py so users never run a stale stub."""
    from fastapi.responses import FileResponse
    path = ROOT_DIR.parent / "hive_runner" / "runner.py"
    return FileResponse(str(path), media_type="text/x-python", filename="runner.py")


@api_router.post("/missions/local")
async def create_local_mission(body: LocalMissionCreate):
    s = await hub.get(body.session_id)
    if not s or s.status != "approved":
        raise HTTPException(status_code=400, detail="Connect and approve a workspace runner first.")
    await ensure_user()
    project = await get_or_create_local_project(s)
    mission = Mission(goal=body.goal, user_id=DEFAULT_USER, type="local", mode="local",
                      project_id=project["id"], workspace_id=s.workspace,
                      session_id=body.session_id, workspace=s.workspace, provider="runner")
    await db.missions.insert_one(mission.model_dump())
    s.current_mission = mission.id
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
