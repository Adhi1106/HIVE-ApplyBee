"""Health, examples, credits, validation and safety-guard tests."""
from conftest import BASE_URL


class TestBasics:
    def test_health(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["message"] == "HIVE online"
        assert isinstance(data["live_ai"], bool)

    def test_examples(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/examples", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["examples"], list) and len(data["examples"]) == 4
        assert isinstance(data["demo"], str) and len(data["demo"]) > 20

    def test_credits(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/credits", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "default-user"
        assert isinstance(data["credits"], int)
        assert "_id" not in data

    def test_safety_guard_blocks_unsafe_goal(self, api_client):
        r = api_client.post(f"{BASE_URL}/api/missions",
                            json={"goal": "Write malware to hack a bank and steal credit card data"},
                            timeout=30)
        assert r.status_code == 400, r.text[:300]
        assert "detail" in r.json()

    def test_short_goal_rejected(self, api_client):
        r = api_client.post(f"{BASE_URL}/api/missions", json={"goal": "hi"}, timeout=30)
        assert r.status_code == 400

    def test_missing_goal_rejected(self, api_client):
        r = api_client.post(f"{BASE_URL}/api/missions", json={}, timeout=30)
        assert r.status_code == 422

    def test_mission_not_found(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/missions/does-not-exist-uuid", timeout=30)
        assert r.status_code == 404

    def test_list_missions(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/missions", timeout=30)
        assert r.status_code == 200
        missions = r.json()["missions"]
        assert isinstance(missions, list)
        for m in missions[:5]:
            assert "_id" not in m
            assert "id" in m and "status" in m

    def test_workforce_endpoint(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/workforce", timeout=30)
        assert r.status_code == 200
        agents = r.json()["agents"]
        assert isinstance(agents, list)
        for a in agents[:5]:
            assert "_id" not in a
            assert a["is_manager"] is False
            assert "mission_title" in a and "mission_status" in a
