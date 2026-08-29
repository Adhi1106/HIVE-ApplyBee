"""HIVE Runner Hub — manages WebSocket connections from local runners,
pairing sessions, and request/response tool RPC over the socket.

Runners connect OUTBOUND to the backend, so the web app never needs direct
access to the user's machine. Tool calls are relayed to the runner and the
real result is returned.
"""
from __future__ import annotations
import asyncio
import secrets
import uuid
import logging
from typing import Dict, Any, Optional

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("hive.runner_hub")

DEMO_CODE = "HIVE-DEMO"
DEMO_SESSION = "demo"


class Session:
    def __init__(self, sid: str, code: str):
        self.id = sid
        self.code = code
        self.status = "waiting"  # waiting | connected | approved | disconnected
        self.runner_id: Optional[str] = None
        self.workspace: Optional[str] = None
        self.machine: Optional[str] = None
        self.capabilities = []
        self.permissions = []

    def public(self) -> Dict[str, Any]:
        return {
            "session_id": self.id,
            "code": self.code,
            "status": self.status,
            "workspace": self.workspace,
            "machine": self.machine,
            "capabilities": self.capabilities,
            "permissions": self.permissions,
            "connected": self.status in ("connected", "approved"),
            "approved": self.status == "approved",
        }


class RunnerHub:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self.by_code: Dict[str, str] = {}
        self.conns: Dict[str, WebSocket] = {}       # runner_id -> ws
        self.pending: Dict[str, asyncio.Future] = {}
        # persistent demo session so a hosted runner can always attach
        demo = Session(DEMO_SESSION, DEMO_CODE)
        self.sessions[DEMO_SESSION] = demo
        self.by_code[DEMO_CODE] = DEMO_SESSION

    def create_session(self) -> Session:
        sid = uuid.uuid4().hex[:12]
        code = secrets.token_hex(3).upper()
        s = Session(sid, code)
        self.sessions[sid] = s
        self.by_code[code] = sid
        return s

    def get(self, sid: str) -> Optional[Session]:
        return self.sessions.get(sid)

    def approve(self, sid: str) -> bool:
        s = self.sessions.get(sid)
        if not s or s.status not in ("connected", "approved"):
            return False
        s.status = "approved"
        conn = self.conns.get(s.runner_id) if s.runner_id else None
        if conn:
            asyncio.create_task(self._safe_send(conn, {"type": "approved"}))
        return True

    async def _safe_send(self, ws: WebSocket, payload: dict):
        try:
            await ws.send_json(payload)
        except Exception:  # noqa: BLE001
            pass

    async def call_tool(self, sid: str, tool: str, args: dict, timeout: float = 30) -> Any:
        s = self.sessions.get(sid)
        if not s or s.status not in ("connected", "approved") or not s.runner_id:
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
                    sid = self.by_code.get(msg.get("code", ""))
                    if not sid:
                        await ws.send_json({"type": "error", "error": "invalid pairing code"})
                        continue
                    session = self.sessions[sid]
                    runner_id = uuid.uuid4().hex
                    session.runner_id = runner_id
                    session.workspace = msg.get("workspace")
                    session.machine = msg.get("machine")
                    session.capabilities = msg.get("capabilities", [])
                    session.permissions = msg.get("permissions", [])
                    if session.status != "approved":
                        session.status = "connected"
                    self.conns[runner_id] = ws
                    await ws.send_json({"type": "registered", "runner_id": runner_id, "session_id": sid})
                    logger.info(f"runner registered on session {sid} ws={session.workspace}")
                elif t == "tool_result":
                    fut = self.pending.get(msg.get("id"))
                    if fut and not fut.done():
                        fut.set_result(msg)
                elif t == "pong":
                    pass
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001
            logger.warning(f"runner ws error: {e}")
        finally:
            if runner_id:
                self.conns.pop(runner_id, None)
            if session and session.runner_id == runner_id:
                session.status = "disconnected"
                session.runner_id = None


hub = RunnerHub()
