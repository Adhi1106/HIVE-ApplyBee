"""Tests for the NEW local-execution layer: runner session, approval, seeding,
local mission lifecycle, real workspace organization and deterministic recovery."""
import time

import pytest
import requests

from conftest import BASE_URL

SID = "demo"
MESSY = ["app.py", "model.py", "data.csv", "notes.txt", "report.pdf", "README_old.md"]
ALLOWED_ROOT = {"README.md", "requirements.txt", ".gitignore"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _root_files(entries):
    return [e["path"] for e in entries if e["type"] == "file" and "/" not in e["path"]]


# ---------------- runner session / connectivity ----------------
@pytest.mark.xdist_group(name="runner_ws")
class TestRunnerSession:
    def test_demo_session_connected(self, client):
        # tolerate a brief runner reconnect window after a backend hot-reload
        d = None
        for _ in range(10):
            r = client.get(f"{BASE_URL}/api/runner/session/{SID}", timeout=30)
            assert r.status_code == 200, r.text[:300]
            d = r.json()
            if d["status"] in ("connected", "approved"):
                break
            time.sleep(2)
        assert d["session_id"] == SID
        assert d["status"] in ("connected", "approved"), d
        assert d["connected"] is True
        assert d["workspace"] == "/app/hive_demo_workspace", d["workspace"]
        for cap in ["list", "read", "write", "mkdir", "move", "copy", "git_status"]:
            assert cap in d["capabilities"], f"missing capability {cap}"
        assert isinstance(d["permissions"], list) and len(d["permissions"]) >= 3
        assert "_id" not in d

    def test_unknown_session_404(self, client):
        r = client.get(f"{BASE_URL}/api/runner/session/nope-xyz", timeout=30)
        assert r.status_code == 404

    def test_approve(self, client):
        r = client.post(f"{BASE_URL}/api/runner/session/{SID}/approve", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["approved"] is True
        assert d["status"] == "approved"

    def test_pair_creates_waiting_session(self, client):
        r = client.post(f"{BASE_URL}/api/runner/pair", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "waiting"
        assert d["connected"] is False and d["approved"] is False
        assert len(d["code"]) >= 4
        # approving an unconnected session must fail
        r2 = client.post(f"{BASE_URL}/api/runner/session/{d['session_id']}/approve", timeout=30)
        assert r2.status_code == 400
        # tool call on unconnected session must fail cleanly (not 500)
        r3 = client.get(f"{BASE_URL}/api/runner/session/{d['session_id']}/tree", timeout=30)
        assert r3.status_code == 400, r3.status_code

    def test_seed_demo_creates_real_files(self, client):
        client.post(f"{BASE_URL}/api/runner/session/{SID}/approve", timeout=30)
        r = client.post(f"{BASE_URL}/api/runner/session/{SID}/seed-demo", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["root"] == "/app/hive_demo_workspace"
        roots = _root_files(d["entries"])
        for f in MESSY:
            assert f in roots, f"{f} not seeded at root; got {roots}"

    def test_tree_endpoint(self, client):
        r = client.get(f"{BASE_URL}/api/runner/session/{SID}/tree", timeout=30)
        assert r.status_code == 200
        assert "entries" in r.json()


# ---------------- local mission lifecycle ----------------
@pytest.mark.xdist_group(name="runner_ws")
class TestLocalMission:
    payload = {}

    def test_run_local_mission_to_verified(self, client):
        client.post(f"{BASE_URL}/api/runner/session/{SID}/approve", timeout=30)
        client.post(f"{BASE_URL}/api/runner/session/{SID}/seed-demo", timeout=60)
        r = client.post(f"{BASE_URL}/api/missions/local", json={"session_id": SID}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert isinstance(d["id"], str) and d["status"]
        mid = d["id"]

        deadline = time.time() + 90
        payload = None
        while time.time() < deadline:
            g = client.get(f"{BASE_URL}/api/missions/{mid}", timeout=60)
            assert g.status_code == 200, g.text[:300]
            payload = g.json()
            if payload["mission"]["status"] in ("verified", "failed"):
                break
            time.sleep(2)
        assert payload and payload["mission"]["status"] == "verified", \
            f"status={payload['mission']['status']} err={payload['mission'].get('error')}"
        m = payload["mission"]
        assert m["type"] == "local"
        assert m["provider"] == "runner"
        assert m["workspace"] == "/app/hive_demo_workspace"
        assert m.get("credits_used", 0) > 0
        TestLocalMission.payload = payload

    def test_dynamic_filesystem_workforce(self, client):
        p = TestLocalMission.payload
        assert p, "mission test must run first"
        agents = p["agents"]
        roles = {a["role"] for a in agents}
        for role in ["Mission Manager", "Project Inspector", "File Organizer",
                     "Structure Builder", "QA Reviewer"]:
            assert role in roles, f"missing {role}; got {roles}"
        assert any(a["is_manager"] for a in agents)
        assert any(a["is_reviewer"] for a in agents)
        # standard AI workforce roles must NOT appear
        assert not (roles & {"Researcher", "Strategist", "Writer", "Analyst"})
        assert all("_id" not in a for a in agents)

    def test_real_workspace_artifact(self, client):
        p = TestLocalMission.payload
        art = p.get("artifact")
        assert art, "no artifact"
        c = art["content"]
        assert c["kind"] == "workspace"
        assert c["workspace"] == "/app/hive_demo_workspace"
        before_roots = _root_files(c["before_tree"])
        for f in MESSY:
            assert f in before_roots, f"{f} missing from before_tree roots {before_roots}"
        after_paths = {e["path"] for e in c["after_tree"]}
        for expected in ["src", "data", "docs", "misc", "src/app.py", "src/model.py",
                         "data/data.csv", "docs/notes.txt", "docs/report.pdf",
                         "docs/README_old.md", "README.md", "requirements.txt", ".gitignore"]:
            assert expected in after_paths, f"{expected} missing in after_tree"
        after_roots = set(_root_files(c["after_tree"]))
        assert after_roots <= ALLOWED_ROOT, f"loose files left at root: {after_roots - ALLOWED_ROOT}"
        ops = c["operations"]
        assert len(ops) > 5
        kinds = {o["op"] for o in ops}
        for k in ["mkdir", "move", "write", "list"]:
            assert k in kinds, f"op {k} missing; got {kinds}"

    def test_deterministic_recovery_events(self, client):
        p = TestLocalMission.payload
        events = p["events"]
        types = [e["type"] for e in events]
        assert "REVISION_REQUIRED" in types
        rev = next(e for e in events if e["type"] == "REVISION_REQUIRED")
        assert rev["level"] == "warning"
        assert "root" in rev["message"].lower()
        routed = next(e for e in events if e["type"] == "ISSUE_ROUTED")
        assert routed["actor"] == "Mission Manager"
        assert "File Organizer" in routed["message"]
        # a corrective TOOL_EXECUTED must follow the routing
        idx = types.index("ISSUE_ROUTED")
        assert "TOOL_EXECUTED" in types[idx:], "no corrective tool execution after routing"
        assert types.index("REVIEW_PASSED") > idx
        assert "MISSION_VERIFIED" in types
        assert types.index("MISSION_VERIFIED") > types.index("REVIEW_PASSED")
        # exactly the organize task retried once and verified
        tasks = p["tasks"]
        retried = [t for t in tasks if t.get("retry_count") == 1]
        assert len(retried) == 1, [(t["key"], t.get("retry_count")) for t in tasks]
        assert retried[0]["key"] == "organize"
        assert retried[0]["status"] == "verified"

    def test_workspace_clean_via_tree(self, client):
        r = client.get(f"{BASE_URL}/api/runner/session/{SID}/tree", timeout=30)
        assert r.status_code == 200
        entries = r.json()["entries"]
        roots = set(_root_files(entries))
        assert roots <= ALLOWED_ROOT, f"loose files at root after mission: {roots - ALLOWED_ROOT}"
        paths = {e["path"] for e in entries}
        for folder in ["src", "data", "docs", "misc"]:
            assert folder in paths

    def test_local_mission_requires_approved_session(self, client):
        r = client.post(f"{BASE_URL}/api/missions/local", json={"session_id": "does-not-exist"}, timeout=30)
        assert r.status_code == 400


# ---------------- sandbox safety ----------------
class TestSandbox:
    def test_path_traversal_rejected(self, client):
        """Runner _safe() must reject writes outside the workspace.
        Exercised through the real runner via an internal tool call helper."""
        import asyncio
        import sys
        sys.path.insert(0, "/app/backend")
        # exercised in-process is not possible (hub lives in the server process);
        # instead assert the runner's Workspace._safe directly on a temp root.
        sys.path.insert(0, "/app/hive_runner")
        from runner import Workspace  # noqa: PLC0415

        ws = Workspace("/tmp/TEST_hive_sandbox")
        with pytest.raises(ValueError):
            ws.write("../escape.txt", "nope")
        with pytest.raises(ValueError):
            ws.list("../")
        with pytest.raises(ValueError):
            ws.move(**{"from": "a.txt", "to": "../../a.txt"})
        with pytest.raises(ValueError):
            ws.read("/etc/passwd")
        # unknown / private tool names rejected
        with pytest.raises(ValueError):
            ws.dispatch("_git", {"args": ["log"]})
        with pytest.raises(ValueError):
            ws.dispatch("shell", {"cmd": "ls"})
        assert asyncio  # keep import used
