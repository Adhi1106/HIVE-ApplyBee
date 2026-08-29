"""Different goals must produce different specialist workforces."""
import pytest

from conftest import create_mission, poll_mission

CHURN = ("Analyze a fictional SaaS product whose customer churn has increased by 20% "
         "and determine the likely causes and recommended actions.")
BUILD = "Build a simple software product for tracking daily habits."


@pytest.fixture(scope="class")
def two_missions(api_client):
    id1 = create_mission(api_client, CHURN)
    id2 = create_mission(api_client, BUILD)
    p1 = poll_mission(api_client, id1)
    p2 = poll_mission(api_client, id2)
    return p1, p2


class TestDynamicWorkforce:
    def test_both_verified(self, two_missions):
        p1, p2 = two_missions
        assert p1["mission"]["status"] == "verified", p1["mission"].get("error")
        assert p2["mission"]["status"] == "verified", p2["mission"].get("error")

    def test_roles_differ(self, two_missions):
        p1, p2 = two_missions
        r1 = {a["role"] for a in p1["agents"] if not a["is_manager"]}
        r2 = {a["role"] for a in p2["agents"] if not a["is_manager"]}
        assert r1 and r2
        assert r1 != r2, f"identical workforce roles: {r1}"

    def test_each_has_recovery(self, two_missions):
        for p in two_missions:
            retried = [t for t in p["tasks"] if t["retry_count"] == 1]
            assert len(retried) == 1, f"mission {p['mission']['id']} retries={len(retried)}"
            types = [e["type"] for e in p["events"]]
            assert "REVISION_REQUIRED" in types and "ISSUE_ROUTED" in types

    def test_each_has_artifact(self, two_missions):
        for p in two_missions:
            assert p["artifact"] is not None
            assert p["artifact"]["content"].get("sections")
