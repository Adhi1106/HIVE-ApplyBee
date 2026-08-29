import os
import time

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = _base.rstrip("/")

POLL_TIMEOUT = 200


@pytest.fixture(scope="class")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def create_mission(client, goal):
    r = client.post(f"{BASE_URL}/api/missions", json={"goal": goal}, timeout=60)
    assert r.status_code == 200, f"create failed {r.status_code}: {r.text[:400]}"
    data = r.json()
    assert "id" in data and isinstance(data["id"], str)
    assert data["status"] in ("planning", "assembling", "running")
    return data["id"]


def poll_mission(client, mission_id, timeout=POLL_TIMEOUT):
    """Poll GET /api/missions/{id} until terminal status. Returns full payload."""
    deadline = time.time() + timeout
    payload = None
    while time.time() < deadline:
        r = client.get(f"{BASE_URL}/api/missions/{mission_id}", timeout=60)
        assert r.status_code == 200, f"get mission {r.status_code}: {r.text[:300]}"
        payload = r.json()
        status = payload["mission"]["status"]
        if status in ("verified", "failed"):
            return payload
        time.sleep(3)
    return payload
