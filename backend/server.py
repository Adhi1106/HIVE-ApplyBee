from fastapi import FastAPI, APIRouter, HTTPException, WebSocket, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import asyncio
import logging
import uuid
import razorpay
from pathlib import Path
from pydantic import BaseModel

from models import Mission, MissionCreate, LocalMissionCreate, now_iso
from orchestrator import Orchestrator
from local_orchestrator import LocalOrchestrator
from runner_hub import hub
from provider import provider
import billing

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')
RAZORPAY_WEBHOOK_SECRET = os.environ.get('RAZORPAY_WEBHOOK_SECRET', '')
rzp = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) if RAZORPAY_KEY_ID else None

app = FastAPI(title="HIVE")
api_router = APIRouter(prefix="/api")

orchestrator = Orchestrator(db)
local_orchestrator = LocalOrchestrator(db)

DEFAULT_USER = "default-user"
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
        doc = {"id": DEFAULT_USER, "name": "HIVE Operator", "created_at": now_iso()}
        doc.update(billing.default_user_fields())
        await db.users.insert_one(doc)
        return
    # backfill billing fields for pre-existing users without wiping their balance
    missing = {k: v for k, v in billing.default_user_fields().items() if k not in u}
    if missing:
        await db.users.update_one({"id": DEFAULT_USER}, {"$set": missing})


async def get_user_synced():
    """Fetch the user and apply any due lazy resets (backend-authoritative)."""
    await ensure_user()
    u = await db.users.find_one({"id": DEFAULT_USER}, {"_id": 0})
    updates = billing.compute_resets(u)
    if updates:
        await db.users.update_one({"id": DEFAULT_USER}, {"$set": updates})
        u.update(updates)
    return u


async def consume_credit():
    """Deduct exactly 1 credit for a submitted mission. In DEMO_MODE the app is
    never blocked at 0; otherwise a 0 balance raises 402 so the caller can
    prompt an upgrade. Returns the refreshed user."""
    u = await get_user_synced()
    if u.get("credits", 0) <= 0:
        if not billing.DEMO_MODE:
            raise HTTPException(status_code=402, detail="You're out of credits. Upgrade to continue.")
        return u  # demo: allow, stay at 0
    new_credits = u["credits"] - 1
    updates = {"credits": new_credits}
    if new_credits <= 0:
        updates.update(billing.on_exhausted({**u, **updates}))
    await db.users.update_one({"id": DEFAULT_USER}, {"$set": updates})
    u.update(updates)
    return u


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
    u = await get_user_synced()
    return billing.public_state(u)


@api_router.post("/credits/renew")
async def renew_credits():
    """Demo-only: restore the FREE balance immediately (skips the 2h wait)."""
    await ensure_user()
    await db.users.update_one({"id": DEFAULT_USER}, {"$set": {"credits": billing.FREE_CREDITS, "credits_reset_at": None}})
    u = await get_user_synced()
    return billing.public_state(u)


@api_router.get("/plans")
async def plans():
    return {"plans": list(billing.PLANS.values()), "currency": billing.CURRENCY, "demo_mode": billing.DEMO_MODE}


@api_router.post("/missions")
async def create_mission(body: MissionCreate):
    goal = (body.goal or "").strip()
    if len(goal) < 5:
        raise HTTPException(status_code=400, detail="Please describe what you want your workforce to accomplish.")
    if _is_unsafe(goal):
        raise HTTPException(status_code=400, detail="This mission requests unsafe or disallowed actions and was blocked by HIVE safety policy.")
    await ensure_user()
    await ensure_default_project()
    await consume_credit()
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
    """Serve the CURRENT, real persistent runner.py so users never run a stale stub.
    No-store headers guarantee the browser never hands back a cached old file."""
    from fastapi.responses import FileResponse
    path = ROOT_DIR.parent / "hive_runner" / "runner.py"
    return FileResponse(
        str(path), media_type="text/x-python", filename="runner.py",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


@api_router.get("/runner/version")
async def runner_version():
    from runner_hub import MIN_RUNNER
    return {"latest": ".".join(str(x) for x in MIN_RUNNER)}


@api_router.get("/runner/debug")
async def runner_debug():
    """Live diagnostics: which runners are actually connected to the backend and
    the last register attempts (so we can tell 'never reached backend' vs
    'wrong code' vs 'old version' vs 'connected')."""
    return hub.debug()


@api_router.get("/runner/active")
async def runner_active():
    """Minimal workspace status for the first page (no technical details)."""
    return hub.active()


@api_router.post("/missions/local")
async def create_local_mission(body: LocalMissionCreate):
    s = await hub.get(body.session_id)
    if not s or s.status != "approved":
        raise HTTPException(status_code=400, detail="Connect and approve a workspace runner first.")
    await ensure_user()
    await consume_credit()
    project = await get_or_create_local_project(s)
    mission = Mission(goal=body.goal, user_id=DEFAULT_USER, type="local", mode="local",
                      project_id=project["id"], workspace_id=s.workspace,
                      session_id=body.session_id, workspace=s.workspace, provider="runner")
    await db.missions.insert_one(mission.model_dump())
    s.current_mission = mission.id
    asyncio.create_task(local_orchestrator.run(mission.id, body.goal, body.session_id))
    return {"id": mission.id, "status": mission.status}


# ============================ Razorpay billing ============================
class OrderReq(BaseModel):
    plan: str
    billing: str = "monthly"


class VerifyReq(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan: str
    billing: str = "monthly"


@api_router.get("/razorpay/config")
async def razorpay_config():
    """Public checkout key only — the secret NEVER leaves the backend."""
    return {"key_id": RAZORPAY_KEY_ID, "configured": bool(rzp), "currency": billing.CURRENCY}


@api_router.post("/create-order")
async def create_order(body: OrderReq):
    if not rzp:
        raise HTTPException(status_code=503, detail="Payments are not configured.")
    if body.plan not in ("pro", "business"):
        raise HTTPException(status_code=400, detail="Choose a paid plan (pro or business).")
    if body.billing not in ("monthly", "yearly"):
        raise HTTPException(status_code=400, detail="Invalid billing period.")
    amount = billing.order_amount_paise(body.plan, body.billing)
    if amount < 100:
        raise HTTPException(status_code=400, detail="Invalid order amount.")
    receipt = f"hive_{body.plan}_{uuid.uuid4().hex[:8]}"[:40]
    try:
        order = rzp.order.create({"amount": amount, "currency": billing.CURRENCY,
                                  "receipt": receipt, "payment_capture": 1,
                                  "notes": {"plan": body.plan, "billing": body.billing}})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"razorpay order failed: {e}")
        raise HTTPException(status_code=502, detail="Could not create payment order.")
    await db.payments.insert_one({"order_id": order["id"], "user_id": DEFAULT_USER,
                                  "plan": body.plan, "billing": body.billing, "amount": amount,
                                  "status": "created", "created_at": now_iso()})
    return {"order_id": order["id"], "amount": amount, "currency": billing.CURRENCY, "key_id": RAZORPAY_KEY_ID}


@api_router.post("/verify-payment")
async def verify_payment(body: VerifyReq):
    if not rzp:
        raise HTTPException(status_code=503, detail="Payments are not configured.")
    pay = await db.payments.find_one({"order_id": body.razorpay_order_id})
    if not pay:
        raise HTTPException(status_code=400, detail="Unknown order.")
    # Idempotency: never grant twice for the same order.
    if pay.get("status") == "paid":
        u = await get_user_synced()
        return {"ok": True, "already": True, **billing.public_state(u)}
    try:
        rzp.utility.verify_payment_signature({
            "razorpay_order_id": body.razorpay_order_id,
            "razorpay_payment_id": body.razorpay_payment_id,
            "razorpay_signature": body.razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        await db.payments.update_one({"order_id": body.razorpay_order_id}, {"$set": {"status": "verification_failed"}})
        raise HTTPException(status_code=400, detail="Payment verification failed.")
    # Verified — activate using the plan stored server-side with the order.
    plan = pay.get("plan", body.plan)
    billing_period = pay.get("billing", body.billing)
    await db.payments.update_one({"order_id": body.razorpay_order_id},
                                 {"$set": {"status": "paid", "payment_id": body.razorpay_payment_id, "paid_at": now_iso()}})
    await ensure_user()
    updates = billing.activate(plan, billing_period)
    await db.users.update_one({"id": DEFAULT_USER}, {"$set": updates})
    u = await get_user_synced()
    return {"ok": True, "plan": plan, **billing.public_state(u)}


@api_router.post("/razorpay/webhook")
async def razorpay_webhook(request: Request):
    if not RAZORPAY_WEBHOOK_SECRET:
        return {"status": "ignored"}
    payload = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    try:
        rzp.utility.verify_webhook_signature(payload.decode(), signature, RAZORPAY_WEBHOOK_SECRET)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")
    return {"status": "ok"}


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
