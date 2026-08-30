"""HIVE Runner Hub — manages WebSocket connections from local runners,
pairing sessions, and request/response tool RPC over the socket.

Runners connect OUTBOUND to the backend, so the web app never needs direct
access to the user's machine. Tool calls are relayed to the runner and the
real result is returned.

Pairing sessions are persisted in MongoDB so a pairing code stays valid across
backend reloads/restarts (the dev server runs with --reload). Only the live
WebSocket object lives in memory; when the backend restarts the runner simply
reconnects and re-registers against the still-valid code.
"""
from __future__ import annotations
import asyncio
import secrets
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("hive.runner_hub")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

DEMO_CODE = "HIVE-DEMO"
DEMO_SESSION = "demo"
MIN_RUNNER = (1, 2, 0)  # runners older than this must re-download


def _ver_tuple(v: str):
    try:
        return tuple(int(x) for x in (v or "0").split(".")[:3])
    except Exception:  # noqa: BLE001
        return (0,)


class Session:
    """Runtime view of a pairing session. `live` is set by the hub from the
    presence of a real WebSocket connection; everything else is persisted."""

    def __init__(self, sid: str, code: str):
        self.id = sid
        self.code = code
        self.approved = False
        self.ever_connected = False
        self.live = False
        self.runner_id: Optional[str] = None
        self.workspace: Optional[str] = None
        self.machine: Optional[str] = None
        self.os: Optional[str] = None
        self.version: Optional[str] = None
        self.capabilities = []
        self.permissions = []
        self.connected_at: Optional[str] = None
        self.last_heartbeat: Optional[str] = None
        self.current_mission: Optional[str] = None

    @property
    def status(self) -> str:
        if self.live and self.approved:
            return "approved"
        if self.live:
            return "connected"
        if self.ever_connected:
            return "disconnected"
        return "waiting"

    def doc(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "approved": self.approved,
            "ever_connected": self.ever_connected,
            "runner_id": self.runner_id,
            "workspace": self.workspace,
            "machine": self.machine,
            "os": self.os,
            "version": self.version,
            "capabilities": self.capabilities,
            "permissions": self.permissions,
            "connected_at": self.connected_at,
            "last_heartbeat": self.last_heartbeat,
            "current_mission": self.current_mission,
        }

    @classmethod
    def from_doc(cls, d: Dict[str, Any]) -> "Session":
        s = cls(d["id"], d["code"])
        s.approved = d.get("approved", False)
        s.ever_connected = d.get("ever_connected", False)
        s.runner_id = d.get("runner_id")
        s.workspace = d.get("workspace")
        s.machine = d.get("machine")
        s.os = d.get("os")
        s.version = d.get("version")
        s.capabilities = d.get("capabilities", [])
        s.permissions = d.get("permissions", [])
        s.connected_at = d.get("connected_at")
        s.last_heartbeat = d.get("last_heartbeat")
        s.current_mission = d.get("current_mission")
        return s

    def public(self) -> Dict[str, Any]:
        return {
            "session_id": self.id,
            "code": self.code,
            "status": self.status,
            "workspace": self.workspace,
            "machine": self.machine,
            "os": self.os,
            "version": self.version,
            "capabilities": self.capabilities,
            "permissions": self.permissions,
            "connected": self.live,
            "approved": self.live and self.approved,
            "connected_at": self.connected_at,
            "last_heartbeat": self.last_heartbeat,
            "current_mission": self.current_mission,
        }


class RunnerHub:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}      # sid -> Session (cache)
        self.by_code: Dict[str, str] = {}           # code -> sid (cache)
        self.conns: Dict[str, WebSocket] = {}       # runner_id -> ws (RAM only)
        self.pending: Dict[str, asyncio.Future] = {}
        self.db = None
        # persistent demo session so a hosted runner can always attach
        demo = Session(DEMO_SESSION, DEMO_CODE)
        self.sessions[DEMO_SESSION] = demo
        self.by_code[DEMO_CODE] = DEMO_SESSION

    def attach_db(self, db):
        self.db = db

    async def _persist(self, s: Session):
        if self.db is None:
            return
        try:
            await self.db.runner_sessions.update_one(
                {"id": s.id}, {"$set": s.doc()}, upsert=True)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"session persist failed: {e}")

    def _hydrate(self, s: Session) -> Session:
        s.live = bool(s.runner_id and s.runner_id in self.conns)
        self.sessions[s.id] = s
        self.by_code[s.code] = s.id
        return s

    async def create_session(self) -> Session:
        sid = uuid.uuid4().hex[:12]
        code = secrets.token_hex(3).upper()
        s = Session(sid, code)
        self.sessions[sid] = s
        self.by_code[code] = sid
        await self._persist(s)
        logger.info(f"pairing session created sid={sid} code={code}")
        return s

    async def get(self, sid: str) -> Optional[Session]:
        s = self.sessions.get(sid)
        if s:
            return self._hydrate(s)
        if self.db is not None:
            d = await self.db.runner_sessions.find_one({"id": sid}, {"_id": 0})
            if d:
                return self._hydrate(Session.from_doc(d))
        return None

    async def _get_by_code(self, code: str) -> Optional[Session]:
        sid = self.by_code.get(code)
        if sid and sid in self.sessions:
            return self._hydrate(self.sessions[sid])
        if self.db is not None:
            d = await self.db.runner_sessions.find_one({"code": code}, {"_id": 0})
            if d:
                return self._hydrate(Session.from_doc(d))
        # allow the always-on demo code even if cache was wiped
        if code == DEMO_CODE:
            return self._hydrate(self.sessions[DEMO_SESSION])
        return None

    async def approve(self, sid: str) -> bool:
        s = await self.get(sid)
        if not s or not s.live:
            return False
        s.approved = True
        await self._persist(s)
        conn = self.conns.get(s.runner_id) if s.runner_id else None
        if conn:
            await self._safe_send(conn, {"type": "approved"})
        return True

    async def _safe_send(self, ws: WebSocket, payload: dict):
        try:
            await ws.send_json(payload)
        except Exception:  # noqa: BLE001
            pass

    async def call_tool(self, sid: str, tool: str, args: dict, timeout: float = 30) -> Any:
        s = await self.get(sid)
        if not s or not s.live or not s.runner_id:
            raise RuntimeError("runner not connected")
        conn = self.conns.get(s.runner_id)
        if not conn:
            raise RuntimeError("runner not connected")
        call_id = uuid.uuid4().hex
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self.pending[call_id] = fut
        await conn.send_json({"type": "tool_call", "id": call_id, "tool": tool, "args": args})
        try:
            res = await asyncio.wait_for(fut, timeout)
        finally:
            self.pending.pop(call_id, None)
        if not res.get("ok"):
            raise RuntimeError(res.get("error", "tool failed"))
        return res.get("result")

    async def handle(self, ws: WebSocket):
        await ws.accept()
        runner_id = None
        session: Optional[Session] = None
        try:
            while True:
                msg = await ws.receive_json()
                t = msg.get("type")
                if t == "register":
                    code = (msg.get("code") or "").strip()
                    rv = _ver_tuple(msg.get("version"))
                    if rv < MIN_RUNNER:
                        min_s = ".".join(str(x) for x in MIN_RUNNER)
                        logger.warning(f"register rejected: runner version {msg.get('version')} < {min_s}")
                        await ws.send_json({
                            "type": "error", "fatal": True, "code": "version_incompatible",
                            "error": f"This runner (v{msg.get('version') or '?'}) is out of date. "
                                     f"Download the latest runner.py (v{min_s}+) from the HIVE browser and re-run."})
                        continue
                    session = await self._get_by_code(code)
                    if not session:
                        logger.warning(f"register rejected: unknown code '{code}'")
                        await ws.send_json({
                            "type": "error", "fatal": True, "code": "invalid_code",
                            "error": f"Pairing code '{code}' is not recognized. "
                                     "It may have expired — generate a new code in the HIVE browser and re-run."})
                        continue
                    runner_id = uuid.uuid4().hex
                    session.runner_id = runner_id
                    session.workspace = msg.get("workspace")
                    session.machine = msg.get("machine")
                    session.os = msg.get("os")
                    session.version = msg.get("version")
                    session.capabilities = msg.get("capabilities", [])
                    session.permissions = msg.get("permissions", [])
                    session.connected_at = _now()
                    session.last_heartbeat = _now()
                    session.ever_connected = True
                    self.conns[runner_id] = ws
                    session.live = True
                    await self._persist(session)
                    await ws.send_json({
                        "type": "registered", "runner_id": runner_id,
                        "session_id": session.id, "approved": session.approved})
                    logger.info(f"runner registered session={session.id} code={code} ws={session.workspace}")
                elif t == "tool_result":
                    fut = self.pending.get(msg.get("id"))
                    if fut and not fut.done():
                        fut.set_result(msg)
                elif t in ("heartbeat", "pong", "ping"):
                    if session:
                        session.last_heartbeat = _now()
                    await ws.send_json({"type": "heartbeat_ack"})
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001
            logger.warning(f"runner ws error: {e}")
        finally:
            if runner_id:
                self.conns.pop(runner_id, None)
            if session and session.runner_id == runner_id:
                session.runner_id = None
                session.live = False
                await self._persist(session)
                logger.info(f"runner disconnected session={session.id}")


hub = RunnerHub()
