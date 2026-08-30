"""HIVE billing/credits — modular, backend-authoritative subscription logic.

Isolated from the mission/runner code. All plan amounts and credit allowances
live here so they can be changed without touching the rest of the app.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone, timedelta

DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() == "true"
FREE_CREDITS = 10
FREE_RESET_HOURS = 2
CURRENCY = "INR"

# Prices in whole rupees. Yearly = 10 months (2 months free) — a real charge.
PLANS = {
    "free": {
        "id": "free", "name": "Free", "price_monthly": 0, "price_yearly": 0,
        "credits": FREE_CREDITS, "recommended": False,
        "tagline": "Kick the tyres",
        "features": ["10 starter credits", "Demo & Workforce missions", "Local Runner access", "Community support"],
    },
    "pro": {
        "id": "pro", "name": "Pro", "price_monthly": 499, "price_yearly": 4990,
        "credits": 100, "recommended": True,
        "tagline": "For serious builders",
        "features": ["100 credits / month", "Everything in Free", "Priority mission execution", "Email support"],
    },
    "business": {
        "id": "business", "name": "Business", "price_monthly": 1999, "price_yearly": 19990,
        "credits": 500, "recommended": False,
        "tagline": "For teams shipping fast",
        "features": ["500 credits / month", "Everything in Pro", "Team-oriented usage", "Priority support"],
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:  # noqa: BLE001
        return None


def default_user_fields() -> dict:
    return {
        "credits": FREE_CREDITS,
        "plan": "free",
        "billing": None,
        "subscription_status": "none",
        "credit_allowance": FREE_CREDITS,
        "credits_reset_at": None,
        "subscription_expiry": None,
    }


def compute_resets(user: dict) -> dict:
    """Return the field updates needed to apply any due lazy reset/downgrade.
    Backend is the source of truth — no browser timer involved."""
    plan = user.get("plan", "free")
    status = user.get("subscription_status", "none")
    reset_at = _parse(user.get("credits_reset_at"))
    expiry = _parse(user.get("subscription_expiry"))
    n = _now()

    if plan != "free" and status == "active":
        if expiry and n >= expiry:
            u = default_user_fields()  # subscription lapsed -> back to Free
            return u
        if reset_at and n >= reset_at:  # monthly allowance refresh
            allowance = user.get("credit_allowance", PLANS.get(plan, PLANS["free"])["credits"])
            return {"credits": allowance, "credits_reset_at": _iso(n + timedelta(days=30))}
        return {}

    # Free plan: restore to 10 once the 2-hour window has elapsed.
    if reset_at and n >= reset_at:
        return {"credits": FREE_CREDITS, "credits_reset_at": None}
    return {}


def on_exhausted(user: dict) -> dict:
    """When a free user hits 0, schedule the 2-hour restore (idempotent)."""
    if user.get("plan", "free") == "free" and not user.get("credits_reset_at"):
        return {"credits_reset_at": _iso(_now() + timedelta(hours=FREE_RESET_HOURS))}
    return {}


def activate(plan: str, billing: str) -> dict:
    n = _now()
    allowance = PLANS[plan]["credits"]
    days = 365 if billing == "yearly" else 30
    return {
        "plan": plan,
        "billing": billing,
        "subscription_status": "active",
        "credit_allowance": allowance,
        "credits": allowance,
        "credits_reset_at": _iso(n + timedelta(days=30)),
        "subscription_expiry": _iso(n + timedelta(days=days)),
    }


def order_amount_paise(plan: str, billing: str) -> int:
    p = PLANS[plan]
    rupees = p["price_yearly"] if billing == "yearly" else p["price_monthly"]
    return int(rupees * 100)


def public_state(user: dict) -> dict:
    """The full, backend-authoritative billing snapshot for the frontend."""
    credits = user.get("credits", 0)
    return {
        "credits": credits,
        "plan": user.get("plan", "free"),
        "billing": user.get("billing"),
        "subscription_status": user.get("subscription_status", "none"),
        "credit_allowance": user.get("credit_allowance", FREE_CREDITS),
        "credits_reset_at": user.get("credits_reset_at"),
        "subscription_expiry": user.get("subscription_expiry"),
        "exhausted": credits <= 0,
        "demo_mode": DEMO_MODE,
        "free_reset_hours": FREE_RESET_HOURS,
    }
