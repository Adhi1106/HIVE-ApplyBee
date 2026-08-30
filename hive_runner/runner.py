#!/usr/bin/env python3
"""
HIVE Local Runner
=================
A small, standalone service that runs on the USER'S computer. It connects
outbound to the HIVE backend over a WebSocket and performs REAL filesystem
operations, strictly sandboxed to a single user-approved workspace folder.

Safety:
  * Every path is resolved and confirmed to live inside the approved workspace.
  * No access to files outside the workspace, no credentials, no arbitrary shell.
  * Git is read-only (status/diff) via a fixed argument list, never a shell.

Usage:
  python runner.py --server ws://localhost:8001/api/runner/ws \
                   --code ABC123 --workspace /path/to/your/project

Environment fallbacks: HIVE_RUNNER_SERVER, HIVE_RUNNER_CODE, HIVE_RUNNER_WORKSPACE
"""
import argparse
import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import websockets

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


class Workspace:
    def __init__(self, root: str):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe(self, rel: str) -> Path:
        p = (self.root / (rel or "")).resolve()
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
        # Destructive: requires explicit authorization from HIVE.
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


async def run(server, code, workspace):
    ws_env = Workspace(workspace)
    print("HIVE Runner starting...")
    print(f"OS: {platform.system()} ({platform.release()})")
    print(f"Workspace: {ws_env.root}")
    print(f"Connecting to HIVE... ({server})")
    async for conn in websockets.connect(server, ping_interval=20, ping_timeout=20, max_size=8_000_000):
        hb = None
        try:
            print("Pairing...")
            await conn.send(json.dumps({
                "type": "register",
                "code": code,
                "workspace": str(ws_env.root),
                "machine": platform.node() or "local",
                "os": platform.system(),
                "version": "1.0.0",
                "capabilities": CAPABILITIES,
                "permissions": PERMISSIONS,
            }))
            hb = asyncio.ensure_future(_heartbeat(conn))
            print("Connected \u2713")
            print("Workspace ready \u2713")
            print("Waiting for tasks...")
            async for raw in conn:
                msg = json.loads(raw)
                t = msg.get("type")
                if t == "tool_call":
                    call_id = msg["id"]
                    tool = msg.get("tool")
                    args = msg.get("args") or {}
                    tgt = args.get("path") or args.get("to") or ""
                    print(f"Task received -> {tool} {tgt}".rstrip())
                    try:
                        result = ws_env.dispatch(tool, args)
                        await conn.send(json.dumps({"type": "tool_result", "id": call_id, "ok": True, "result": result}))
                        print(f"  Operation completed \u2713  ({tool} {tgt})".rstrip())
                    except Exception as e:  # noqa: BLE001
                        await conn.send(json.dumps({"type": "tool_result", "id": call_id, "ok": False, "error": str(e)}))
                        print(f"  \u2717 {tool}: {e}")
                    print("Waiting for tasks...")
                elif t == "approved":
                    print("Workspace approved by user \u2713")
                elif t == "heartbeat_ack":
                    pass
                elif t == "error":
                    print(f"Server error: {msg.get('error')}")
        except websockets.ConnectionClosed:
            print("Connection lost. Attempting to reconnect...")
            await asyncio.sleep(2)
        except Exception as e:  # noqa: BLE001
            print(f"Error: {e}. Attempting to reconnect...")
            await asyncio.sleep(2)
        finally:
            if hb:
                hb.cancel()


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="HIVE Local Runner")
    ap.add_argument("--server", default=os.environ.get("HIVE_RUNNER_SERVER", "ws://localhost:8001/api/runner/ws"))
    ap.add_argument("--code", default=os.environ.get("HIVE_RUNNER_CODE", "HIVE-DEMO"))
    ap.add_argument("--workspace", default=os.environ.get("HIVE_RUNNER_WORKSPACE", str(Path.home() / "hive_workspace")))
    a = ap.parse_args()
    try:
        asyncio.run(run(a.server, a.code, a.workspace))
    except KeyboardInterrupt:
        print("\n[HIVE Runner] stopped.")


if __name__ == "__main__":
    main()
