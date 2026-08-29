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


async def run(server, code, workspace):
    ws_env = Workspace(workspace)
    print(f"[HIVE Runner] workspace = {ws_env.root}")
    print(f"[HIVE Runner] connecting to {server} ...")
    async for conn in websockets.connect(server, ping_interval=20, max_size=8_000_000):
        try:
            await conn.send(json.dumps({
                "type": "register",
                "code": code,
                "workspace": str(ws_env.root),
                "machine": platform.node() or "local",
                "capabilities": CAPABILITIES,
                "permissions": PERMISSIONS,
            }))
            print("[HIVE Runner] registered, awaiting approval / tool calls")
            async for raw in conn:
                msg = json.loads(raw)
                t = msg.get("type")
                if t == "tool_call":
                    call_id = msg["id"]
                    try:
                        result = ws_env.dispatch(msg["tool"], msg.get("args"))
                        await conn.send(json.dumps({"type": "tool_result", "id": call_id, "ok": True, "result": result}))
                        print(f"  ✓ {msg['tool']} {msg.get('args', {})}")
                    except Exception as e:  # noqa: BLE001
                        await conn.send(json.dumps({"type": "tool_result", "id": call_id, "ok": False, "error": str(e)}))
                        print(f"  ✗ {msg['tool']}: {e}")
                elif t == "approved":
                    print("[HIVE Runner] workspace approved by user ✓")
                elif t == "error":
                    print(f"[HIVE Runner] server error: {msg.get('error')}")
        except websockets.ConnectionClosed:
            print("[HIVE Runner] connection closed, reconnecting...")
            await asyncio.sleep(2)
        except Exception as e:  # noqa: BLE001
            print(f"[HIVE Runner] error: {e}; reconnecting...")
            await asyncio.sleep(2)


def main():
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
