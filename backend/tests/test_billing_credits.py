"""Billing / credits / Razorpay endpoint tests (iteration 3).

Covers: GET /api/credits, GET /api/plans, credit deduction on POST /api/missions,
zero-credit DEMO_MODE behaviour, POST /api/create-order, POST /api/verify-payment.
"""
import os
import sys

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")

FE = dotenv_values("/app/frontend/.env")
BE = dotenv_values("/app/backend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or FE.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

MONGO_URL = os.environ.get("MONGO_URL") or BE.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or BE.get("DB_NAME")
DEFAULT_USER = "default-user"


@pytest.fixture(scope="session")
def users_col():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]["users"]
    client.close()


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def set_user(users_col, fields):
    users_col.update_one({"id": DEFAULT_USER}, {"$set": fields}, upsert=True)


@pytest.fixture
def fresh_user(users_col):
    import billing  # noqa: PLC0415
    set_user(users_col, billing.default_user_fields())
    yield
    set_user(users_col, billing.default_user_fields())


# ---------- GET /api/credits ----------
class TestCredits:
    def test_fresh_user_has_10_credits_free_plan(self, api, fresh_user):
        r = api.get(f"{BASE_URL}/api/credits", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["credits"] == 10
        assert d["plan"] == "free"
        assert d["exhausted"] is False
        assert d["demo_mode"] is True
        assert d["credit_allowance"] == 10

    def test_mission_submit_deducts_one_credit(self, api, fresh_user):
        before = api.get(f"{BASE_URL}/api/credits", timeout=30).json()["credits"]
        assert before == 10
        r = api.post(f"{BASE_URL}/api/missions", json={"goal": "TEST_ credit deduction check mission"}, timeout=60)
        assert r.status_code == 200, r.text
        assert "id" in r.json()
        after = api.get(f"{BASE_URL}/api/credits", timeout=30).json()["credits"]
        assert after == before - 1, f"expected {before-1}, got {after}"

    def test_zero_credits_demo_mode_still_allows_mission(self, api, users_col, fresh_user):
        set_user(users_col, {"credits": 1, "credits_reset_at": None})
        r = api.post(f"{BASE_URL}/api/missions", json={"goal": "TEST_ drain last credit mission"}, timeout=60)
        assert r.status_code == 200, r.text
        state = api.get(f"{BASE_URL}/api/credits", timeout=30).json()
        assert state["credits"] == 0
        assert state["exhausted"] is True
        assert state["credits_reset_at"], "free user at 0 should get a scheduled reset time"
        # DEMO_MODE => still executable at 0
        r2 = api.post(f"{BASE_URL}/api/missions", json={"goal": "TEST_ mission at zero credits demo mode"}, timeout=60)
        assert r2.status_code == 200, r2.text
        assert api.get(f"{BASE_URL}/api/credits", timeout=30).json()["credits"] == 0

    def test_mission_goal_too_short_rejected_and_no_credit_spent(self, api, fresh_user):
        before = api.get(f"{BASE_URL}/api/credits", timeout=30).json()["credits"]
        r = api.post(f"{BASE_URL}/api/missions", json={"goal": "hi"}, timeout=30)
        assert r.status_code == 400
        assert api.get(f"{BASE_URL}/api/credits", timeout=30).json()["credits"] == before


# ---------- GET /api/plans ----------
class TestPlans:
    def test_plans_shape_and_allowances(self, api):
        r = api.get(f"{BASE_URL}/api/plans", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        plans = {p["id"]: p for p in d["plans"]}
        assert set(plans) == {"free", "pro", "business"}
        assert plans["free"]["credits"] == 10
        assert plans["pro"]["credits"] == 500
        assert plans["business"]["credits"] == 2500
        assert plans["pro"]["price_monthly"] == 499
        assert plans["business"]["price_monthly"] == 1999
        assert d["currency"] == "INR"
        assert d["demo_mode"] is True


# ---------- Razorpay ----------
class TestRazorpay:
    def test_config_exposes_key_id_not_secret(self, api):
        r = api.get(f"{BASE_URL}/api/razorpay/config", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["configured"] is True
        assert d["key_id"].startswith("rzp_")
        assert "secret" not in str(d).lower()

    def test_create_order_pro_monthly(self, api):
        r = api.post(f"{BASE_URL}/api/create-order", json={"plan": "pro", "billing": "monthly"}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["amount"] == 49900
        assert isinstance(d["order_id"], str) and d["order_id"].startswith("order_")
        assert d["currency"] == "INR"

    def test_create_order_business_yearly(self, api):
        r = api.post(f"{BASE_URL}/api/create-order", json={"plan": "business", "billing": "yearly"}, timeout=60)
        assert r.status_code == 200, r.text
        assert r.json()["amount"] == 1999000

    def test_create_order_free_plan_rejected(self, api):
        r = api.post(f"{BASE_URL}/api/create-order", json={"plan": "free", "billing": "monthly"}, timeout=30)
        assert r.status_code == 400, r.text

    def test_create_order_bad_billing_rejected(self, api):
        r = api.post(f"{BASE_URL}/api/create-order", json={"plan": "pro", "billing": "weekly"}, timeout=30)
        assert r.status_code == 400, r.text

    def test_verify_payment_bogus_signature_rejected_no_grant(self, api, fresh_user):
        order = api.post(f"{BASE_URL}/api/create-order", json={"plan": "pro", "billing": "monthly"}, timeout=60).json()
        r = api.post(f"{BASE_URL}/api/verify-payment", json={
            "razorpay_order_id": order["order_id"],
            "razorpay_payment_id": "pay_TESTbogus123",
            "razorpay_signature": "deadbeef" * 8,
            "plan": "pro", "billing": "monthly",
        }, timeout=60)
        assert r.status_code == 400, r.text
        state = api.get(f"{BASE_URL}/api/credits", timeout=30).json()
        assert state["plan"] == "free", "plan must NOT be upgraded on bad signature"
        assert state["credits"] == 10
        assert state["subscription_status"] == "none"

    def test_verify_payment_unknown_order_rejected(self, api):
        r = api.post(f"{BASE_URL}/api/verify-payment", json={
            "razorpay_order_id": "order_TESTdoesnotexist",
            "razorpay_payment_id": "pay_x",
            "razorpay_signature": "x" * 32,
            "plan": "pro", "billing": "monthly",
        }, timeout=30)
        assert r.status_code == 400, r.text
