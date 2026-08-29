"""Full mission lifecycle: plan -> workforce -> DAG -> parallel exec -> recovery -> verified artifact."""
import pytest

from conftest import BASE_URL, create_mission, poll_mission

GOAL = "Plan a marketing campaign for a new product."


@pytest.fixture(scope="class")
def mission(api_client):
    mid = create_mission(api_client, GOAL)
    payload = poll_mission(api_client, mid)
    payload["_id_str"] = mid
    return payload


@pytest.mark.xdist_group(name="runner_ws")
class TestMissionLifecycle:
    def test_reaches_verified(self, mission):
        m = mission["mission"]
        assert m["status"] == "verified", f"status={m['status']} error={m.get('error')}"
        assert m["title"]
        assert m["credits_used"] > 0
        assert m["provider"] in ("openai", "mock")

    def test_dynamic_workforce(self, mission):
        agents = mission["agents"]
        assert len(agents) >= 3
        managers = [a for a in agents if a["is_manager"]]
        reviewers = [a for a in agents if a["is_reviewer"]]
        assert len(managers) == 1 and managers[0]["role"] == "Mission Manager"
        assert len(reviewers) >= 1
        for a in agents:
            assert a["name"] and a["role"]
            assert a["status"] in ["idle", "working", "waiting", "reviewing", "revising", "done"]

    def test_task_dag(self, mission):
        tasks = mission["tasks"]
        assert len(tasks) >= 2
        ids = {t["id"] for t in tasks}
        assert any(t["dependencies"] for t in tasks), "no dependencies in DAG"
        for t in tasks:
            assert t["status"] in ("completed", "verified"), f"{t['title']} -> {t['status']}"
            assert t["output"] is not None
            for d in t["dependencies"]:
                assert d in ids

    def test_events_ordered(self, mission):
        events = mission["events"]
        assert len(events) > 5
        seqs = [e["seq"] for e in events]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs), "duplicate seq values"
        types = [e["type"] for e in events]
        for required in ["MISSION_CREATED", "WORKFORCE_ASSEMBLING", "AGENT_JOINED",
                         "TASK_CREATED", "WORKER_STARTED", "WORKER_COMPLETED",
                         "REVIEW_REQUESTED", "REVIEW_PASSED", "MISSION_VERIFIED"]:
            assert required in types, f"missing event {required}"

    def test_deterministic_recovery(self, mission):
        tasks = mission["tasks"]
        retried = [t for t in tasks if t["retry_count"] == 1]
        assert len(retried) == 1, f"expected exactly one retried task, got {len(retried)}"
        assert retried[0]["status"] == "verified"
        assert retried[0]["error"] is None
        events = mission["events"]
        rev = [e for e in events if e["type"] == "REVISION_REQUIRED"]
        routed = [e for e in events if e["type"] == "ISSUE_ROUTED"]
        passed = [e for e in events if e["type"] == "REVIEW_PASSED"]
        assert len(rev) == 1 and rev[0]["level"] == "warning"
        assert len(routed) == 1 and routed[0]["level"] == "warning"
        assert len(passed) >= 2, "expected task-level and final REVIEW_PASSED"
        # ordering: revision required -> routed -> review passed
        assert rev[0]["seq"] < routed[0]["seq"] < passed[-1]["seq"]

    def test_parallel_execution(self, mission):
        events = mission["events"]
        parallel = [e for e in events if e["type"] == "PARALLEL_EXECUTION"]
        independent = [t for t in mission["tasks"] if not t["dependencies"]]
        assert parallel or len(independent) >= 2, "no evidence of parallel/independent tasks"

    def test_artifact(self, mission):
        art = mission["artifact"]
        assert art is not None
        assert art["title"]
        content = art["content"]
        assert isinstance(content.get("title"), str) and content["title"]
        assert isinstance(content.get("sections"), list) and len(content["sections"]) >= 1
        assert content.get("recommendations"), "missing recommendations"

    def test_mission_persisted_in_list(self, api_client, mission):
        mid = mission["mission"]["id"]
        r = api_client.get(f"{BASE_URL}/api/missions", timeout=30)
        assert r.status_code == 200
        assert any(m["id"] == mid and m["status"] == "verified" for m in r.json()["missions"])

    def test_credits_deducted(self, api_client, mission):
        """Iteration-3 costing: credits are spent PER AI call
        (plan=5, task=3, one extra task call for the deterministic revision, report=3)."""
        r = api_client.get(f"{BASE_URL}/api/credits", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json()["credits"], int)
        expected = 5 + 3 * (len(mission["tasks"]) + 1) + 3
        assert mission["mission"]["credits_used"] == expected, \
            f'credits_used={mission["mission"]["credits_used"]} expected={expected}'
