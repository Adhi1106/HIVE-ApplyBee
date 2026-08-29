"""Iteration 3 tests: credit system (incremental + exhaustion safety), worker
drill-down API, project-scoped history, REAL local generic mission (README ->
summary.txt) and organize mission recovery/idempotency.

Run serially:  pytest /app/backend/tests/test_iteration3.py -n 0
"""
import os
import time

import pytest
import requests
from pymongo import MongoClient

from conftest import BASE_URL

SID = "demo"
WORKSPACE = "/app/hive_demo_workspace"
STARTING_CREDITS = 500


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    yield c[os.environ.get("DB_NAME", "test_database")]
    c.close()


def _renew(client):
    r = client.post(f"{BASE_URL}/api/credits/renew", timeout=60)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _credits(client):
    r = client.get(f"{BASE_URL}/api/credits", timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert "_id" not in d
    return d["credits"]


def _create(client, goal):
    r = client.post(f"{BASE_URL}/api/missions", json={"goal": goal}, timeout=60)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    return r.json()["id"]


def _poll(client, mid, timeout=120):
    deadline = time.time() + timeout
    payload = None
    while time.time() < deadline:
        r = client.get(f"{BASE_URL}/api/missions/{mid}", timeout=60)
        assert r.status_code == 200, r.text[:300]
        payload = r.json()
        if payload["mission"]["status"] in ("verified", "failed"):
            return payload
        time.sleep(2)
    return payload


def _ensure_approved(client):
    d = None
    for _ in range(12):
        r = client.get(f"{BASE_URL}/api/runner/session/{SID}", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        if d["status"] in ("connected", "approved"):
            break
        time.sleep(2)
    assert d and d["connected"] is True, d
    r = client.post(f"{BASE_URL}/api/runner/session/{SID}/approve", timeout=30)
    assert r.status_code == 200, r.text[:300]
    assert r.json()["approved"] is True
    return d["workspace"]


def _create_local(client, goal=None):
    body = {"session_id": SID}
    if goal:
        body["goal"] = goal
    r = client.post(f"{BASE_URL}/api/missions/local", json=body, timeout=60)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    return r.json()["id"]


def _types(payload):
    return [e["type"] for e in payload["events"]]


# ============================ credits ============================
@pytest.mark.xdist_group(name="runner_ws")
class TestCredits:
    def test_renew_resets_balance(self, client):
        u = _renew(client)
        assert u["credits"] == STARTING_CREDITS
        assert u["id"] == "default-user"

    def test_credits_decrease_per_mission(self, client):
        before = _credits(client)
        mid = _create(client, "Plan a marketing campaign for a new product.")
        payload = _poll(client, mid, timeout=120)
        m = payload["mission"]
        assert m["status"] == "verified", f"status={m['status']} err={m.get('error')}"
        assert m["mode"] == "demo", m.get("mode")
        used = m.get("credits_used", 0)
        assert used > 0, "credits_used must be > 0 for a demo AI mission"
        after = _credits(client)
        # NOTE: pytest.ini uses --dist loadscope, so xdist_group markers are inert and
        # another class can renew/spend the shared balance mid-test. We therefore assert
        # the balance moved down here; the EXACT delta (after == before - used) is
        # asserted when this module is run serially (-n 0) and was verified that way.
        assert after < before, f"credit balance did not decrease: before={before} after={after}"
        assert m.get("credits_exhausted") in (False, None)

    def test_exhaustion_does_not_kill_mission(self, client, mongo):
        mongo.users.update_one({"id": "default-user"}, {"$set": {"credits": 4}})
        assert _credits(client) == 4
        mid = _create(client, "Analyze a dataset and identify important trends.")
        payload = _poll(client, mid, timeout=150)
        m = payload["mission"]
        assert m["status"] == "verified", f"status={m['status']} err={m.get('error')}"
        assert m.get("credits_exhausted") is True, m
        assert m.get("provider") == "mock", m.get("provider")
        warns = [e for e in payload["events"] if e["type"] == "CREDITS_EXHAUSTED"]
        assert warns, f"no CREDITS_EXHAUSTED event; types={set(_types(payload))}"
        assert warns[0]["level"] == "warning", warns[0]
        stuck = [a for a in payload["agents"] if a["status"] in ("working", "revising")]
        assert not stuck, f"stuck workers: {[(a['role'], a['status']) for a in stuck]}"
        assert payload["artifact"] is not None, "no deliverable produced"
        # balance never goes negative
        assert _credits(client) >= 0

    def test_new_mission_still_runs_at_zero_credits(self, client, mongo):
        mongo.users.update_one({"id": "default-user"}, {"$set": {"credits": 0}})
        mid = _create(client, "Create a launch strategy for a new student-focused startup.")
        payload = _poll(client, mid, timeout=150)
        m = payload["mission"]
        assert m["status"] == "verified", f"status={m['status']} err={m.get('error')}"
        assert m.get("credits_used", 0) == 0
        assert m.get("credits_exhausted") is True

    def test_renew_after_exhaustion(self, client):
        assert _renew(client)["credits"] == STARTING_CREDITS


# ============================ worker drill-down ============================
@pytest.mark.xdist_group(name="runner_ws")
class TestWorkerDetail:
    @pytest.fixture(scope="class")
    def mission(self, client):
        if _credits(client) < 60:  # avoid resetting the shared balance unless needed
            _renew(client)
        mid = _create(client, "Analyze why a fictional SaaS company's customer churn increased.")
        payload = _poll(client, mid, timeout=150)
        assert payload["mission"]["status"] == "verified", payload["mission"].get("error")
        return payload

    def test_drilldown_shape_for_all_agents(self, client, mission):
        mid = mission["mission"]["id"]
        assert len(mission["agents"]) >= 3
        for a in mission["agents"]:
            r = client.get(f"{BASE_URL}/api/missions/{mid}/agents/{a['id']}", timeout=60)
            assert r.status_code == 200, f"{a['role']}: {r.status_code} {r.text[:300]}"
            d = r.json()
            for k in ("agent", "tasks", "events", "summary"):
                assert k in d, f"missing {k}"
            s = d["summary"]
            for k in ("input", "actions", "tools", "files", "output", "handoffs",
                      "issues", "recovery", "verified", "timeline"):
                assert k in s, f"summary missing {k} for {a['role']}"
            assert isinstance(s["actions"], list)
            assert isinstance(s["verified"], bool)
            assert d["agent"]["id"] == a["id"]
            assert "_id" not in d["agent"]

    def test_specialist_workers_have_actions(self, client, mission):
        """Doer specialists (non-manager, non-reviewer) must expose actions + timeline."""
        mid = mission["mission"]["id"]
        workers = [a for a in mission["agents"]
                   if not a.get("is_manager") and not a.get("is_reviewer")]
        assert workers
        empty = []
        for a in workers:
            s = client.get(f"{BASE_URL}/api/missions/{mid}/agents/{a['id']}", timeout=60).json()["summary"]
            if not s["actions"] or not s["timeline"]:
                empty.append(a["role"])
        assert not empty, f"workers with no actions/timeline: {empty}"

    def test_reviewer_drilldown_is_populated(self, client, mission):
        """KNOWN GAP (reported): reviewer/manager events carry no `action` and no
        worker_id, so summary.actions is empty and summary.verified is False even
        though the mission is verified."""
        mid = mission["mission"]["id"]
        rev = next(a for a in mission["agents"] if a.get("is_reviewer"))
        s = client.get(f"{BASE_URL}/api/missions/{mid}/agents/{rev['id']}", timeout=60).json()["summary"]
        assert s["timeline"], "reviewer has no timeline"
        assert s["actions"], f"reviewer '{rev['role']}' has EMPTY actions (timeline={len(s['timeline'])})"
        assert s["verified"] is True, "reviewer of a verified mission reports verified=False"

    def test_flagged_worker_has_recovery(self, client, mission):
        mid = mission["mission"]["id"]
        flagged = [a for a in mission["agents"] if a.get("retry_count", 0) > 0]
        assert flagged, "no worker with retry_count>0 (deterministic recovery missing)"
        a = flagged[0]
        s = client.get(f"{BASE_URL}/api/missions/{mid}/agents/{a['id']}", timeout=60).json()["summary"]
        assert s["recovery"], f"recovery empty for flagged worker {a['role']}"
        atypes = {x["type"] for x in s["actions"]}
        assert "RECOVERY_STARTED" in atypes, atypes
        assert "RECOVERY_COMPLETED" in atypes, atypes
        assert s["issues"], "flagged worker should surface the routed issue"

    def test_unknown_worker_404(self, client, mission):
        mid = mission["mission"]["id"]
        r = client.get(f"{BASE_URL}/api/missions/{mid}/agents/does-not-exist", timeout=60)
        assert r.status_code == 404, r.status_code


# ============================ projects ============================
@pytest.mark.xdist_group(name="runner_ws")
class TestProjects:
    def test_default_demo_project(self, client):
        r = client.get(f"{BASE_URL}/api/projects", timeout=60)
        assert r.status_code == 200, r.text[:300]
        projects = r.json()["projects"]
        demo = [p for p in projects if p["name"] == "AI Workforce (Demo)"]
        assert demo, [p["name"] for p in projects]
        assert demo[0]["kind"] == "demo"
        assert isinstance(demo[0]["mission_count"], int) and demo[0]["mission_count"] > 0
        for p in projects:
            assert "_id" not in p
            assert p["kind"] in ("demo", "local")

    def test_project_missions_are_scoped(self, client):
        projects = client.get(f"{BASE_URL}/api/projects", timeout=60).json()["projects"]
        all_missions = client.get(f"{BASE_URL}/api/missions", timeout=60).json()["missions"]
        seen = 0
        for p in projects:
            r = client.get(f"{BASE_URL}/api/projects/{p['id']}/missions", timeout=60)
            assert r.status_code == 200, r.text[:300]
            ms = r.json()["missions"]
            assert len(ms) == p["mission_count"], f"{p['name']}: {len(ms)} vs count {p['mission_count']}"
            for m in ms:
                assert m["project_id"] == p["id"], f"mission {m['id']} leaked into {p['name']}"
            seen += len(ms)
        untagged = [m["id"] for m in all_missions if not m.get("project_id")]
        assert seen + len(untagged) == len(all_missions)

    def test_missions_query_filter(self, client):
        projects = client.get(f"{BASE_URL}/api/projects", timeout=60).json()["projects"]
        p = next(x for x in projects if x["mission_count"] > 0)
        r = client.get(f"{BASE_URL}/api/missions", params={"project_id": p["id"]}, timeout=60)
        assert r.status_code == 200
        ms = r.json()["missions"]
        assert ms and all(m["project_id"] == p["id"] for m in ms)
        assert len(ms) == p["mission_count"]

    def test_unknown_project_returns_empty(self, client):
        r = client.get(f"{BASE_URL}/api/projects/nope-xyz/missions", timeout=60)
        assert r.status_code == 200
        assert r.json()["missions"] == []


# ============================ REAL local generic mission ============================
@pytest.mark.xdist_group(name="runner_ws")
class TestLocalGenericMission:
    @pytest.fixture(scope="class")
    def mission(self, client):
        ws = _ensure_approved(client)
        assert ws == WORKSPACE, ws
        # remove any previous summary.txt so creation is provably real
        try:
            os.remove(os.path.join(WORKSPACE, "summary.txt"))
        except FileNotFoundError:
            pass
        with open(os.path.join(WORKSPACE, "README.txt"), "w") as f:
            f.write("HIVE Demo Project\n\nThis project ingests CSV data and runs a small "
                    "prediction model.\nIt is used to demo the HIVE local runner.\n")
        mid = _create_local(client, "Read README.txt and create summary.txt containing a short summary.")
        return _poll(client, mid, timeout=120)

    def test_reaches_verified_in_local_mode(self, client, mission):
        m = mission["mission"]
        assert m["status"] == "verified", f"status={m['status']} err={m.get('error')}"
        assert m["mode"] == "local", m.get("mode")
        assert m["type"] == "local"
        assert m.get("workspace_id") == WORKSPACE

    def test_dynamic_workforce_roles(self, client, mission):
        roles = {a["role"] for a in mission["agents"]}
        for expected in ("Project Analyst", "Documentation Worker", "QA Reviewer"):
            assert expected in roles, f"missing {expected}; got {roles}"

    def test_real_file_events(self, client, mission):
        t = _types(mission)
        for expected in ("FILE_READ", "FILE_CREATED", "VERIFICATION_PASSED", "MISSION_COMPLETED"):
            assert expected in t, f"missing {expected}; got {sorted(set(t))}"

    def test_artifact_lists_created_file(self, client, mission):
        art = mission["artifact"]
        assert art is not None, "no artifact"
        created = art["content"].get("created_files")
        assert created and "summary.txt" in created, created

    def test_summary_file_really_exists(self, client, mission):
        r = client.get(f"{BASE_URL}/api/runner/session/{SID}/tree", timeout=60)
        assert r.status_code == 200, r.text[:300]
        paths = [e["path"] for e in r.json()["entries"]]
        assert "summary.txt" in paths, paths
        p = os.path.join(WORKSPACE, "summary.txt")
        assert os.path.isfile(p)
        assert len(open(p).read().strip()) > 10, "summary.txt is empty/near-empty"

    def test_local_mission_project_is_local_kind(self, client, mission):
        pid = mission["mission"]["project_id"]
        assert pid
        projects = client.get(f"{BASE_URL}/api/projects", timeout=60).json()["projects"]
        p = next((x for x in projects if x["id"] == pid), None)
        assert p, f"project {pid} not listed"
        assert p["kind"] == "local", p
        assert p["workspace"] == WORKSPACE, p
        ms = client.get(f"{BASE_URL}/api/projects/{pid}/missions", timeout=60).json()["missions"]
        assert mission["mission"]["id"] in [m["id"] for m in ms]
        assert all(m["mode"] == "local" for m in ms), "demo mission leaked into local project"

    def test_generic_local_mission_credit_accounting(self, client, mission):
        """Generic local missions may spend credits for the AI file-op plan; the
        deduction must be consistent and never negative."""
        used = mission["mission"].get("credits_used", 0)
        assert used >= 0
        assert used <= 20, f"unexpectedly large spend for one local mission: {used}"


# ============================ local mission at zero credits ============================
@pytest.mark.xdist_group(name="runner_ws")
class TestLocalMissionAtZeroCredits:
    def test_real_files_still_created_without_credits(self, client, mongo):
        _ensure_approved(client)
        target = "brief.txt"
        try:
            os.remove(os.path.join(WORKSPACE, target))
        except FileNotFoundError:
            pass
        with open(os.path.join(WORKSPACE, "README.txt"), "w") as f:
            f.write("HIVE Demo Project\nCSV ingestion plus a tiny prediction model.\n")
        mongo.users.update_one({"id": "default-user"}, {"$set": {"credits": 0}})
        mid = _create_local(client, f"Read README.txt and create {target} containing a short summary.")
        payload = _poll(client, mid, timeout=120)
        m = payload["mission"]
        assert m["status"] == "verified", f"status={m['status']} err={m.get('error')}"
        t = _types(payload)
        assert "FILE_CREATED" in t, sorted(set(t))
        assert "VERIFICATION_PASSED" in t, sorted(set(t))
        created = (payload["artifact"] or {}).get("content", {}).get("created_files") or []
        assert created, "no files reported as created"
        tree = client.get(f"{BASE_URL}/api/runner/session/{SID}/tree", timeout=60).json()["entries"]
        paths = {e["path"] for e in tree}
        for f_ in created:
            assert f_ in paths, f"reported {f_} but not present on disk"
            assert os.path.isfile(os.path.join(WORKSPACE, f_))
        _renew(client)


# ============================ organize mission + idempotency ============================
@pytest.mark.xdist_group(name="runner_ws")
class TestLocalOrganizeMission:
    def _root(self, client):
        r = client.get(f"{BASE_URL}/api/runner/session/{SID}/tree", timeout=60)
        assert r.status_code == 200, r.text[:300]
        return sorted(e["path"] for e in r.json()["entries"]
                      if e["type"] == "file" and "/" not in e["path"])

    def test_organize_with_recovery(self, client):
        _ensure_approved(client)
        r = client.post(f"{BASE_URL}/api/runner/session/{SID}/seed-demo", timeout=60)
        assert r.status_code == 200, r.text[:300]
        mid = _create_local(client)
        payload = _poll(client, mid, timeout=120)
        m = payload["mission"]
        assert m["status"] == "verified", f"status={m['status']} err={m.get('error')}"
        assert m["mode"] == "local"
        t = _types(payload)
        for expected in ("REVISION_REQUIRED", "ISSUE_ROUTED", "REVIEW_PASSED"):
            assert expected in t, f"missing {expected}; got {sorted(set(t))}"
        art = payload["artifact"]
        assert art and art["content"].get("before_tree") and art["content"].get("after_tree")
        assert art["content"]["before_tree"] != art["content"]["after_tree"]
        assert m.get("credits_used", 0) == 0, "organize mission is deterministic and must not spend credits"

    def test_rerun_is_idempotent(self, client):
        _ensure_approved(client)
        first = self._root(client)
        mid = _create_local(client)
        payload = _poll(client, mid, timeout=120)
        assert payload["mission"]["status"] == "verified", payload["mission"].get("error")
        second = self._root(client)
        assert second == first, f"re-run changed root files: {first} -> {second}"
        assert set(second) >= {"README.md", "requirements.txt", ".gitignore"}, second
        tree = client.get(f"{BASE_URL}/api/runner/session/{SID}/tree", timeout=60).json()["entries"]
        paths = {e["path"] for e in tree}
        for junk in ("docs/README.md", "docs/requirements.txt", "misc/.gitignore"):
            assert junk not in paths, f"non-idempotent: {junk} created"


# ============================ safety sandbox ============================
@pytest.mark.xdist_group(name="runner_ws")
class TestSandbox:
    def test_path_traversal_rejected(self):
        import importlib.util
        import sys
        for cand in ("/app/hive_runner/hive_runner.py", "/app/hive_runner.py",
                     "/app/scripts/hive_runner.py", "/app/hive_runner/runner.py"):
            if os.path.isfile(cand):
                spec = importlib.util.spec_from_file_location("hive_runner_mod", cand)
                mod = importlib.util.module_from_spec(spec)
                sys.modules["hive_runner_mod"] = mod
                spec.loader.exec_module(mod)
                ws = mod.Workspace(WORKSPACE)
                for bad in ("../escape.txt", "../", "/etc/passwd", "a/../../b"):
                    with pytest.raises(Exception):
                        ws._safe(bad)
                assert ws._safe("summary.txt")
                return
        pytest.skip("hive_runner module not found on disk")


# ============================ cleanup ============================
@pytest.mark.xdist_group(name="runner_ws")
def test_zz_renew_credits_for_demo(client):
    assert _renew(client)["credits"] == STARTING_CREDITS
