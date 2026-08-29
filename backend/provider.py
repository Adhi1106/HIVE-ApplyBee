"""LLM provider abstraction for HIVE.

Live path: any OpenAI-compatible chat completions endpoint (configured via env).
Fallback path: deterministic mock provider (mock_provider.py).

Swapping providers later only requires changing env vars / this file.
"""
from __future__ import annotations
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

import httpx
from dotenv import load_dotenv

import mock_provider
import prompts

load_dotenv(Path(__file__).parent / '.env')
logger = logging.getLogger("hive.provider")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-nano")


class HiveProvider:
    """Coordinates live LLM calls with a deterministic mock fallback."""

    def __init__(self):
        self.last_source = "mock"

    def live_available(self) -> bool:
        return bool(OPENAI_API_KEY)

    async def _chat_json(self, system: str, user: str) -> Dict[str, Any]:
        """Call the OpenAI-compatible endpoint and return parsed JSON. Raises on failure."""
        if not OPENAI_API_KEY:
            raise RuntimeError("no api key configured")
        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        if OPENAI_MODEL.startswith("gpt-5") or OPENAI_MODEL.startswith("o"):
            payload["reasoning_effort"] = "low"
            payload["max_completion_tokens"] = 4000
        else:
            payload["temperature"] = 0.7
            payload["max_tokens"] = 2000

        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{OPENAI_BASE_URL}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)

    # ---------- planMission ----------
    async def plan_mission(self, goal: str) -> Dict[str, Any]:
        try:
            plan = await self._chat_json(prompts.PLAN_MISSION_SYSTEM, f"User goal: {goal}\n\nDesign the workforce and task DAG as JSON.")
            _validate_plan(plan)
            self.last_source = "openai"
            return plan
        except Exception as e:  # noqa: BLE001
            logger.warning(f"plan_mission live failed, using mock: {e}")
            self.last_source = "mock"
            return mock_provider.plan_mission(goal)

    # ---------- executeAgentTask ----------
    async def execute_task(self, goal: str, role: str, name: str, responsibility: str,
                           task: Dict[str, Any], dep_outputs: List[Dict[str, Any]],
                           revision_issue: Optional[str] = None) -> Dict[str, Any]:
        deps_text = "\n".join(
            f"- {d.get('title')}: {json.dumps(d.get('output'))}" for d in dep_outputs
        ) or "None"
        user = (
            f"Mission goal: {goal}\n"
            f"Your responsibility: {responsibility}\n"
            f"Your task: {task.get('title')} — {task.get('description')}\n"
            f"Outputs from tasks you depend on:\n{deps_text}\n"
        )
        if revision_issue:
            user += (
                f"\nIMPORTANT: A reviewer found this problem with your previous output: \"{revision_issue}\".\n"
                f"Your previous output was: {json.dumps(task.get('output'))}\n"
                f"Revise your output to fully resolve this inconsistency."
            )
        try:
            result = await self._chat_json(prompts.execute_task_system(role, name), user)
            if not isinstance(result.get("output"), dict):
                raise ValueError("bad output shape")
            result.setdefault("summary", f"Completed '{task.get('title')}'.")
            return result
        except Exception as e:  # noqa: BLE001
            logger.warning(f"execute_task live failed, using mock: {e}")
            return mock_provider.execute_task(role, name, task, dep_outputs, revision_issue)

    # ---------- verifyMission / final artifact ----------
    async def final_report(self, goal: str, task_outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        outs = "\n".join(
            f"- {t.get('title')}: {json.dumps(t.get('output'))}" for t in task_outputs
        )
        user = f"Mission goal: {goal}\n\nWorker outputs:\n{outs}\n\nCompile the final verified deliverable as JSON."
        try:
            report = await self._chat_json(prompts.FINAL_REPORT_SYSTEM, user)
            if not report.get("sections"):
                raise ValueError("empty report")
            return report
        except Exception as e:  # noqa: BLE001
            logger.warning(f"final_report live failed, using mock: {e}")
            return mock_provider.final_report(goal, task_outputs)


def _validate_plan(plan: Dict[str, Any]):
    assert isinstance(plan.get("workforce"), list) and len(plan["workforce"]) >= 2
    assert isinstance(plan.get("tasks"), list) and len(plan["tasks"]) >= 2
    roles = {w["role"] for w in plan["workforce"]}
    keys = {t["key"] for t in plan["tasks"]}
    for t in plan["tasks"]:
        assert t["owner_role"] in roles, f"task owner {t['owner_role']} not in workforce"
        for d in t.get("dependencies", []):
            assert d in keys, "dependency references unknown task"
    # ensure a reviewer exists
    assert any("review" in r.lower() for r in roles), "no reviewer role"


provider = HiveProvider()
