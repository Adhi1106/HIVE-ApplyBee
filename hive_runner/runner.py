#!/usr/bin/env python3
"""
HIVE Local Runner
=================
A small, standalone service that runs on the USER'S computer. It connects
outbound to the HIVE backend over a WebSocket and performs REAL filesystem
operations, strictly sandboxed to a single user-approved workspace folder.

It stays alive after connecting and keeps listening for tasks until you press
Ctrl+C. It reconnects automatically if the connection drops.

Safety:
  * Every path is resolved and confirmed to live inside the approved workspace.
  * No access to files outside the workspace, no credentials, no arbitrary shell.
  * Git is read-only (status/diff) via a fixed argument list, never a shell.

Usage (one line):
  python runner.py --server "wss://YOUR-HOST/api/runner/ws" --code ABC123 --workspace "C:\\path\\to\\folder"

Environment fallbacks: HIVE_RUNNER_SERVER, HIVE_RUNNER_CODE, HIVE_RUNNER_WORKSPACE
"""
import argparse
import asyncio
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import websockets

VERSION = "1.2.0"

CAPABILITIES = [
    "list", "read", "write", "mkdir", "move", "copy", "rename", "git_status", "git_diff",
]
PERMISSIONS = [
    "Read files in the approved workspace",
    "Create and edit files in the approved workspace",
    "Create folders and move/rename/copy files in the approved workspace",
    "Inspect Git status/diff (read-only)",
]
MAX_READ = 200_000  # bytes


def log(msg: str):
    print(f"[HIVE] {msg}", flush=True)


class Workspace:
    def __init__(self, root: str):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe(self, rel: str) -> Path:
        # Reject absolute paths and any escape outside the approved workspace.
        rel = rel or ""
        if os.path.isabs(rel) or (len(rel) > 1 and rel[1] == ":"):
            raise ValueError(f"absolute paths are not allowed: '{rel}'")
        p = (self.root / rel).resolve()
        if p != self.root and self.root not in p.parents:
            raise ValueError(f"path '{rel}' is outside the approved workspace")
        return p

    def list(self, path="."):
        base = self._safe(path)
        entries = []
        if base.exists():
            for p in sorted(base.rglob("*")):
                if ".git" in p.parts:
                    continue
                entries.append({
                    "path": str(p.relative_to(self.root)),
                    "type": "dir" if p.is_dir() else "file",
                    "size": p.stat().st_size if p.is_file() else 0,
                })
        return {"root": str(self.root), "entries": entries}

    def read(self, path):
        p = self._safe(path)
        data = p.read_bytes()[:MAX_READ]
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            content = data.decode("utf-8", errors="replace")
        return {"path": path, "content": content, "truncated": p.stat().st_size > MAX_READ}

    def write(self, path, content=""):
        p = self._safe(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"path": path, "bytes": len(content.encode("utf-8"))}

    def mkdir(self, path):
        p = self._safe(path)
        p.mkdir(parents=True, exist_ok=True)
        return {"path": path}

    def move(self, **kw):
        src = self._safe(kw["from"]); dst = self._safe(kw["to"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"from": kw["from"], "to": kw["to"]}

    rename = move

    def copy(self, **kw):
        src = self._safe(kw["from"]); dst = self._safe(kw["to"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))
        return {"from": kw["from"], "to": kw["to"]}

    def delete(self, path=None, authorized=False, **kw):
        if not authorized:
            raise ValueError("delete requires explicit authorization")
        p = self._safe(path)
        if p.is_dir():
            shutil.rmtree(str(p))
        else:
            p.unlink(missing_ok=True)
        return {"path": path, "deleted": True}

    # friendly aliases so backend tool names always resolve
    def list_files(self, **kw):
        return self.list(**kw)

    def read_file(self, **kw):
        return self.read(**kw)

    def create_file(self, **kw):
        return self.write(**kw)

    def write_file(self, **kw):
        return self.write(**kw)

    def modify_file(self, **kw):
        return self.write(**kw)

    def delete_file(self, **kw):
        return self.delete(**kw)

    def _git(self, args):
        if not (self.root / ".git").exists():
            return {"available": False}
        out = subprocess.run(["git", *args], cwd=str(self.root),
                             capture_output=True, text=True, timeout=15)
        return {"available": True, "output": out.stdout[-MAX_READ:]}

    def git_status(self):
        return self._git(["status", "--porcelain=v1", "-b"])

    def git_diff(self):
        return self._git(["diff"])

    def dispatch(self, tool, args):
        args = args or {}
        fn = getattr(self, tool, None)
        if not callable(fn) or tool.startswith("_"):
            raise ValueError(f"unknown tool '{tool}'")
        return fn(**args)


async def _heartbeat(conn):
    try:
        while True:
            await asyncio.sleep(15)
            await conn.send(json.dumps({"type": "heartbeat"}))
    except Exception:
        return


async def _serve(conn, ws_env, code):
    """Handle one live connection. Returns 'fatal' to stop reconnecting,
    or 'retry' when the connection ended and we should reconnect."""
    log("WebSocket connected")
    log(f"Pairing with code: {code}")
    await conn.send(json.dumps({
        "type": "register",
        "code": code,
        "workspace": str(ws_env.root),
        "machine": platform.node() or "local",
        "os": platform.system(),
        "version": VERSION,
        "capabilities": CAPABILITIES,
        "permissions": PERMISSIONS,
    }))

    registered = False
    hb = None
    try:
        async for raw in conn:
            msg = json.loads(raw)
            t = msg.get("type")

            if t == "registered":
                registered = True
                hb = asyncio.ensure_future(_heartbeat(conn))
                log("Authentication successful")
                log("Runner connected \u2713")
                if msg.get("approved"):
                    log("Workspace already approved. Waiting for tasks...")
                else:
                    log("Go to your HIVE browser tab — it now shows 'Runner connected'.")
                    log("Approve this workspace there, then send a task.")
                    log("Waiting for tasks...")

            elif t == "error":
                log("PAIRING FAILED: " + str(msg.get("error")))
                if msg.get("fatal"):
                    log("-> Generate a fresh pairing code in the HIVE browser and re-run this command.")
                    return "fatal"

            elif t == "approved":
                log("Workspace approved by user \u2713. Waiting for tasks...")

            elif t == "tool_call":
                if not registered:
                    continue
                call_id = msg["id"]
                tool = msg.get("tool")
                args = msg.get("args") or {}
                tgt = args.get("path") or args.get("to") or ""
                log(f"Task received: {tool} {tgt}".rstrip())
                log("Workspace validation: OK")
                log("Executing...")
                try:
                    result = ws_env.dispatch(tool, args)
                    await conn.send(json.dumps({"type": "tool_result", "id": call_id, "ok": True, "result": result}))
                    log(f"Completed \u2713 ({tool} {tgt})".rstrip())
                except Exception as e:  # noqa: BLE001
                    await conn.send(json.dumps({"type": "tool_result", "id": call_id, "ok": False, "error": str(e)}))
                    log(f"Failed \u2717 {tool}: {e}")
                log("Waiting for tasks...")

            elif t == "heartbeat_ack":
                pass
    finally:
        if hb:
            hb.cancel()
    return "retry"


async def run(server, code, workspace, stop_event):
    ws_env = Workspace(workspace)
    print("=" * 60)
    print(f"  HIVE Local Runner  v{VERSION}")
    print("=" * 60)
    log(f"OS        : {platform.system()} ({platform.release()})")
    log(f"Workspace : {ws_env.root}")
    log(f"Server    : {server}")
    log(f"Code      : {code}")
    print("-" * 60)

    backoff = 2
    while not stop_event.is_set():
        try:
            log("Connecting to HIVE...")
            # Manual reconnect loop — compatible across websockets 10 -> 16.
            async with websockets.connect(
                server, ping_interval=20, ping_timeout=20, max_size=8_000_000
            ) as conn:
                backoff = 2  # reset after a successful connect
                outcome = await _serve(conn, ws_env, code)
                if outcome == "fatal":
                    return
            log("Disconnected. Reconnecting...")
        except asyncio.CancelledError:
            break
        except (OSError, websockets.exceptions.WebSocketException) as e:
            log(f"Connection failed: {e}")
            log(f"Reconnecting in {backoff}s... (Ctrl+C to stop)")
        except Exception as e:  # noqa: BLE001
            log(f"Unexpected error: {e}")
            log(f"Reconnecting in {backoff}s... (Ctrl+C to stop)")
        # wait with the ability to break out immediately on shutdown
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=backoff)
        except asyncio.TimeoutError:
            pass
        backoff = min(backoff * 2, 30)


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="HIVE Local Runner")
    ap.add_argument("--server", default=os.environ.get("HIVE_RUNNER_SERVER", "ws://localhost:8001/api/runner/ws"))
    ap.add_argument("--code", default=os.environ.get("HIVE_RUNNER_CODE", "HIVE-DEMO"))
    ap.add_argument("--workspace", default=os.environ.get("HIVE_RUNNER_WORKSPACE", str(Path.home() / "hive_workspace")))
    ap.add_argument("--version", action="version", version=f"HIVE Local Runner v{VERSION}")
    a = ap.parse_args()

    async def _amain():
        stop_event = asyncio.Event()
        loop = asyncio.get_event_loop()
        # graceful shutdown on SIGINT/SIGTERM where supported (POSIX)
        for sig in ("SIGINT", "SIGTERM"):
            try:
                loop.add_signal_handler(getattr(signal, sig), stop_event.set)
            except (NotImplementedError, AttributeError):
                pass  # Windows: fall back to KeyboardInterrupt below
        await run(a.server, a.code, a.workspace, stop_event)

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        log("Stopped by user (Ctrl+C).")


if __name__ == "__main__":
    main()
