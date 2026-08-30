"""E2E: local-runner generative mission produces a REAL deliverable on disk.

Run directly:  python /app/backend/tests/local_generative_e2e.py
Spawns the real hive_runner against the EXTERNAL wss endpoint.
"""
import json
import os
import shutil
import subprocess
import sys
import time

from dotenv import dotenv_values

BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
WSS = BASE.replace("https://", "wss://").replace("http://", "ws://") + "/api/runner/ws"


def curl(method, path, data=None):
    args = ["curl", "-s", "-X", method, BASE + path, "-H", "Content-Type: application/json"]
    if data is not None:
        args += ["-d", json.dumps(data)]
    out = subprocess.check_output(args)
    return json.loads(out)


def run_case(goal, workdir, timeout=120):
    shutil.rmtree(workdir, ignore_errors=True)
    os.makedirs(workdir, exist_ok=True)
    pair = curl("POST", "/api/runner/pair")
    sid, code = pair["session_id"], pair["code"]
    proc = subprocess.Popen(
        [sys.executable, "/app/hive_runner/runner.py", "--server", WSS, "--code", code, "--workspace", workdir],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        connected = False
        for _ in range(25):
            time.sleep(1)
            if curl("GET", f"/api/runner/session/{sid}").get("connected"):
                connected = True
                break
        assert connected, "runner never connected"
        curl("POST", f"/api/runner/session/{sid}/approve")
        mid = curl("POST", "/api/missions/local", {"session_id": sid, "goal": goal})["id"]
        status = None
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(2)
            status = curl("GET", f"/api/missions/{mid}")["mission"]["status"]
            if status in ("verified", "failed"):
                break
        files = {}
        for root, _dirs, names in os.walk(workdir):
            for n in names:
                p = os.path.join(root, n)
                rel = os.path.relpath(p, workdir)
                try:
                    files[rel] = open(p, encoding="utf-8", errors="replace").read()
                except Exception as e:  # noqa: BLE001
                    files[rel] = f"<unreadable {e}>"
        return {"mission_id": mid, "status": status, "files": files}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()


def main():
    failures = []
    cases = [
        ("Make a text file with 5 jokes", "/tmp/hive_ws_jokes", ["?"]),
        ("Write a short poem about the ocean into poem.txt", "/tmp/hive_ws_poem", ["ocean"]),
    ]
    for goal, wd, keywords in cases:
        print(f"\n===== CASE: {goal}")
        r = run_case(goal, wd)
        print("mission:", r["mission_id"], "status:", r["status"])
        print("files:", list(r["files"].keys()))
        for name, content in r["files"].items():
            print(f"--- {name} ({len(content)} chars) ---")
            print(content[:800])
        if r["status"] != "verified":
            failures.append(f"[{goal}] status={r['status']} (expected verified)")
        if not r["files"]:
            failures.append(f"[{goal}] no files created on disk")
        blob = "\n".join(r["files"].values()).lower()
        if "hive was asked to" in blob:
            failures.append(f"[{goal}] ECHO BUG: content contains 'HIVE was asked to'")
        if "could not reach the content generator" in blob:
            failures.append(f"[{goal}] FALLBACK placeholder used - LLM generation failed")
        for kw in keywords:
            if kw.lower() not in blob:
                failures.append(f"[{goal}] expected keyword {kw!r} not found in deliverable")
        if len(blob.strip()) < 40:
            failures.append(f"[{goal}] deliverable too short ({len(blob.strip())} chars)")

    print("\n===== RESULT")
    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(1)
    print("PASS: all generative local-runner cases produced real deliverables")


if __name__ == "__main__":
    main()
