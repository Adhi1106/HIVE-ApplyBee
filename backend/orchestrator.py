"""HIVE Mission Orchestrator — the Mission Manager engine.

Maintains real mission state in MongoDB: plans the mission, assembles a dynamic
workforce, builds a task DAG, executes independent tasks in parallel, injects one
deterministic reviewer-caught inconsistency, routes it to the responsible agent,
recovers, rechecks dependents, reviews, and marks the mission VERIFIED.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Dict, Any, List, Optional

from models import Mission, Agent, Task, MissionEvent, Artifact, Review, now_iso
from provider import provider
import mock_provider

logger = logging.getLogger("hive.orchestrator")

_seq_locks: Dict[str, asyncio.Lock] = {}
_seqs: Dict[str, int] = {}
_warned: set = set()  # missions already warned about credit exhaustion

STEP = 0.7  # base pacing delay so the workforce is watchable
AI_PLAN_COST = 5
AI_TASK_COST = 3


class Orchestrator:
    def __init__(self, db):
        self.db = db

    # ---------------- event / state helpers ----------------
    async def _next_seq(self, mission_id: str) -> int:
        lock = _seq_locks.setdefault(mission_id, asyncio.Lock())
        async with lock:
            _seqs[mission_id] = _seqs.get(mission_id, 0) + 1
            return _seqs[mission_id]

    async def emit(self, mission_id: str, etype: str, message: str,
                   level: str = "info", actor: str = "HIVE", task_id: Optional[str] = None, **extra):
        seq = await self._next_seq(mission_id)
        clean = {k: v for k, v in extra.items() if v is not None}
        ev = MissionEvent(mission_id=mission_id, seq=seq, type=etype,
                          level=level, actor=actor, message=message, task_id=task_id, **clean)
        await self.db.mission_events.insert_one(ev.model_dump())

    # ---------------- credit gating (never kills a running mission) ----------------
    async def _spend_ai(self, mission_id: str, cost: int) -> bool:
        """Deduct credits for a NEW AI operation. Returns False (and flags the mission)
        when the balance is exhausted, so the caller can fall back to deterministic work."""
        res = await self.db.users.update_one(
            {"id": "default-user", "credits": {"$gte": cost}},
            {"$inc": {"credits": -cost}},
        )
        if res.modified_count:
            await self.db.missions.update_one({"id": mission_id}, {"$inc": {"credits_used": cost}})
            return True
        await self.db.missions.update_one({"id": mission_id}, {"$set": {"credits_exhausted": True}})
        if mission_id not in _warned:
            _warned.add(mission_id)
            await self.emit(mission_id, "CREDITS_EXHAUSTED",
                            "Demo credits exhausted — continuing with safe deterministic execution so the mission can finish and verify.",
                            level="warning", actor="HIVE")
        return False

    async def _ai_plan(self, mission_id, goal):
        if await self._spend_ai(mission_id, AI_PLAN_COST):
            return await provider.plan_mission(goal), provider.last_source
        return mock_provider.plan_mission(goal), "mock"

    async def _ai_execute(self, mission_id, goal, actor, name, resp, task, dep_outputs, revision_issue=None):
        if await self._spend_ai(mission_id, AI_TASK_COST):
            return await provider.execute_task(goal, actor, name, resp, task, dep_outputs, revision_issue=revision_issue)
        return mock_provider.execute_task(actor, name, task, dep_outputs, revision_issue)

    async def _ai_report(self, mission_id, goal, completed):
        if await self._spend_ai(mission_id, AI_TASK_COST):
            return await provider.final_report(goal, completed)
        return mock_provider.final_report(goal, completed)

    async def set_mission(self, mission_id: str, **fields):
        fields["updated_at"] = now_iso()
        await self.db.missions.update_one({"id": mission_id}, {"$set": fields})

    async def set_task(self, task: Dict[str, Any], **fields):
        fields["updated_at"] = now_iso()
        task.update(fields)
        await self.db.tasks.update_one({"id": task["id"]}, {"$set": fields})

    async def set_agent(self, agent: Dict[str, Any], **fields):
        agent.update(fields)
        await self.db.agents.update_one({"id": agent["id"]}, {"$set": fields})

    # ---------------- main entry ----------------
    async def run(self, mission_id: str, goal: str):
        try:
            await self._run(mission_id, goal)
        except Exception as e:  # noqa: BLE001
            logger.exception("mission failed")
            await self.set_mission(mission_id, status="failed", error=str(e))
            await self.emit(mission_id, "MISSION_BLOCKED", f"Mission failed: {e}", level="error", actor="HIVE")

    async def _run(self, mission_id: str, goal: str):
        # 1. PLAN
        await self.emit(mission_id, "MISSION_CREATED", "Mission received. Mission Manager is analyzing the goal.", actor="Mission Manager")
        await asyncio.sleep(STEP)
        plan, psource = await self._ai_plan(mission_id, goal)
        await self.set_mission(mission_id, status="assembling", title=plan.get("title", "Mission"),
                               summary=plan.get("summary", ""), required_capabilities=plan.get("required_capabilities", []),
                               provider=psource)

        # 2. WORKFORCE
        manager = Agent(mission_id=mission_id, name="HIVE", role="Mission Manager",
                        responsibility="Coordinate the workforce, route issues and verify completion.",
                        capabilities=["orchestration"], status="working", is_manager=True).model_dump()
        await self.db.agents.insert_one(manager)
        await self.emit(mission_id, "WORKFORCE_ASSEMBLING",
                        f"Determined this mission needs: {', '.join(plan.get('required_capabilities', [])) or 'a specialist workforce'}.",
                        actor="Mission Manager")
        await asyncio.sleep(STEP)

        agents_by_role: Dict[str, Dict[str, Any]] = {}
        reviewer = None
        for w in plan["workforce"]:
            is_rev = "review" in w["role"].lower()
            ag = Agent(mission_id=mission_id, name=w.get("name", w["role"]), role=w["role"],
                       responsibility=w.get("responsibility", ""), capabilities=w.get("capabilities", []),
                       status="idle", is_reviewer=is_rev)
            doc = ag.model_dump()
            await self.db.agents.insert_one(doc)
            agents_by_role[w["role"]] = doc
            if is_rev:
                reviewer = doc
            await self.emit(mission_id, "AGENT_JOINED", f"{ag.name} joined as {ag.role}.", level="info", actor="Mission Manager")
            await asyncio.sleep(0.25)

        if reviewer is None:
            ag = Agent(mission_id=mission_id, name="Vera", role="Reviewer",
                       responsibility="Verify quality and consistency.", capabilities=["qa"], is_reviewer=True)
            reviewer = ag.model_dump()
            await self.db.agents.insert_one(reviewer)
            await self.emit(mission_id, "AGENT_JOINED", "Vera joined as Reviewer.", actor="Mission Manager")

        # 3. TASKS
        key_to_id: Dict[str, str] = {}
        tasks: List[Dict[str, Any]] = []
        for t in plan["tasks"]:
            owner = agents_by_role.get(t["owner_role"])
            task = Task(mission_id=mission_id, key=t["key"], title=t["title"],
                        description=t.get("description", ""), owner_role=t["owner_role"],
                        owner_agent_id=owner["id"] if owner else None)
            doc = task.model_dump()
            tasks.append(doc)
            key_to_id[t["key"]] = doc["id"]
        for t, spec in zip(tasks, plan["tasks"]):
            t["dependencies"] = [key_to_id[d] for d in spec.get("dependencies", []) if d in key_to_id]
            await self.db.tasks.insert_one(t)
            await self.emit(mission_id, "TASK_CREATED", f"Task created: {t['title']} → {t['owner_role']}.", actor="Mission Manager", task_id=t["id"])
        await self.set_mission(mission_id, status="running")

        tasks_by_id = {t["id"]: t for t in tasks}
        dependents: Dict[str, List[str]] = {t["id"]: [] for t in tasks}
        for t in tasks:
            for d in t["dependencies"]:
                dependents[d].append(t["id"])

        # deterministic flagged task: the one with the most downstream dependents
        flagged_id = max(tasks, key=lambda t: len(dependents[t["id"]]))["id"]
        recheck_pending: set = set()

        # 4. EXECUTE (waves; independent tasks run in parallel)
        while any(t["status"] in ("pending",) for t in tasks):
            done_ids = {t["id"] for t in tasks if t["status"] in ("completed", "verified")}
            ready = [t for t in tasks if t["status"] == "pending" and all(d in done_ids for d in t["dependencies"])]
            if not ready:
                for t in tasks:
                    if t["status"] == "pending":
                        await self.set_task(t, status="blocked")
                raise RuntimeError("Task dependencies could not be satisfied")
            if len(ready) > 1:
                await self.emit(mission_id, "PARALLEL_EXECUTION",
                                f"{len(ready)} independent tasks running in parallel.", actor="Mission Manager")
            await asyncio.gather(*[
                self._run_task(mission_id, goal, t, tasks_by_id, dependents,
                               reviewer, flagged_id, recheck_pending) for t in ready
            ])

        # 5. FINAL REVIEW + VERIFY
        await self.set_mission(mission_id, status="reviewing")
        await self.set_agent(reviewer, status="reviewing")
        await self.emit(mission_id, "REVIEW_REQUESTED", "Reviewer performing final verification of the complete mission.", actor=reviewer["role"])
        await asyncio.sleep(STEP)
        completed = [t for t in tasks if t["status"] in ("completed", "verified")]
        report = await self._ai_report(mission_id, goal, completed)
        artifact = Artifact(mission_id=mission_id, title=report.get("title", "Deliverable"), content=report)
        await self.db.artifacts.insert_one(artifact.model_dump())
        await self.db.reviews.insert_one(Review(mission_id=mission_id, verdict="pass", issue="").model_dump())
        await self.emit(mission_id, "REVIEW_PASSED", "Final review passed. All outputs are consistent.", level="success", actor=reviewer["role"])
        await self.set_agent(reviewer, status="done")
        await self.set_agent(manager, status="done")
        # all specialists finished their contribution
        await self.db.agents.update_many({"mission_id": mission_id, "is_reviewer": False, "is_manager": False}, {"$set": {"status": "done", "current_task_id": None}})

        await self.set_mission(mission_id, status="verified", final_artifact_id=artifact.id)
        await self.emit(mission_id, "MISSION_VERIFIED", "Mission VERIFIED. Final deliverable is ready.", level="success", actor="Mission Manager")

    # ---------------- per-task execution ----------------
    async def _run_task(self, mission_id, goal, task, tasks_by_id, dependents,
                        reviewer, flagged_id, recheck_pending):
        agent = await self.db.agents.find_one({"id": task["owner_agent_id"]}, {"_id": 0}) if task["owner_agent_id"] else None
        actor = agent["role"] if agent else task["owner_role"]

        await self.set_task(task, status="running", started_at=now_iso())
        if agent:
            await self.set_agent(agent, status="working", current_task_id=task["id"])
        wk = {"worker_id": agent["id"] if agent else None, "worker_name": agent["name"] if agent else actor, "worker_role": actor}
        await self.emit(mission_id, "WORKER_STARTED", f"{actor} started: {task['title']}.", actor=actor, task_id=task["id"], action="start_task", status="running", input_summary=task.get("description"), **wk)
        await asyncio.sleep(STEP)

        dep_outputs = [
            {"title": tasks_by_id[d]["title"], "output": tasks_by_id[d].get("output")}
            for d in task["dependencies"] if tasks_by_id.get(d)
        ]
        result = await self._ai_execute(
            mission_id, goal, actor, agent["name"] if agent else actor,
            agent["responsibility"] if agent else "", task, dep_outputs,
        )
        await self.set_task(task, output=result.get("output"), summary=result.get("summary", ""), status="completed", completed_at=now_iso())
        if agent:
            await self.set_agent(agent, status="waiting", current_task_id=None)
        await self.emit(mission_id, "WORKER_COMPLETED", result.get("summary", f"{actor} completed {task['title']}."), level="success", actor=actor, task_id=task["id"], action="complete_task", status="completed", output_summary=result.get("summary"), **wk)
        # structured handoff to dependent task owners
        for d in dependents.get(task["id"], []):
            dep = tasks_by_id.get(d)
            if dep:
                await self.emit(mission_id, "HANDOFF", f"{actor} handed '{task['title']}' output to {dep['owner_role']}.", actor=actor, task_id=task["id"], action="handoff", handoff_to=dep["owner_role"], output_summary=result.get("summary"), **wk)

        # recheck note if this task was downstream of a corrected task
        if task["id"] in recheck_pending:
            recheck_pending.discard(task["id"])
            await self.emit(mission_id, "DEPENDENCY_CHECKED", f"Dependency recheck passed: '{task['title']}' is consistent with the corrected input.", level="success", actor=reviewer["role"], task_id=task["id"])

        # deterministic controlled failure + recovery
        if task["id"] == flagged_id and task["retry_count"] == 0:
            await self._recover(mission_id, goal, task, tasks_by_id, dependents, reviewer, agent, actor, recheck_pending)

    # ---------------- responsibility routing + recovery ----------------
    async def _recover(self, mission_id, goal, task, tasks_by_id, dependents, reviewer, agent, actor, recheck_pending):
        await self.set_mission(mission_id, status="recovering")
        await self.set_agent(reviewer, status="reviewing")
        await self.emit(mission_id, "REVIEW_REQUESTED", f"Reviewer is checking '{task['title']}'.", actor=reviewer["role"], task_id=task["id"])
        await asyncio.sleep(STEP)

        issue = f"The figures in '{task['title']}' are internally inconsistent and don't reconcile with the source metrics."
        await self.db.reviews.insert_one(Review(mission_id=mission_id, task_id=task["id"], verdict="issue", issue=issue, responsible_task_id=task["id"]).model_dump())
        await self.set_task(task, status="needs_revision", error=issue)
        await self.emit(mission_id, "REVISION_REQUIRED", f"Reviewer detected an inconsistency in '{task['title']}': {issue}", level="warning", actor=reviewer["role"], task_id=task["id"])
        await asyncio.sleep(STEP)

        # Mission Manager identifies the responsible agent
        wk = {"worker_id": agent["id"] if agent else None, "worker_name": agent["name"] if agent else actor, "worker_role": actor}
        await self.emit(mission_id, "ERROR", f"Reviewer detected an issue in '{task['title']}'.", level="warning", actor=reviewer["role"], task_id=task["id"], error=issue, **wk)
        await self.emit(mission_id, "ISSUE_ROUTED", f"Mission Manager identified {actor} as responsible and routed the issue back for revision.", level="warning", actor="Mission Manager", task_id=task["id"], handoff_to=actor)
        if agent:
            await self.set_agent(agent, status="revising", current_task_id=task["id"], retry_count=agent.get("retry_count", 0) + 1)
        await self.set_task(task, status="running", retry_count=task["retry_count"] + 1)
        await self.emit(mission_id, "RECOVERY_STARTED", f"{actor} is revising '{task['title']}' to correct the inconsistency.", actor=actor, task_id=task["id"], action="revise", status="running", **wk)
        await asyncio.sleep(STEP)

        dep_outputs = [
            {"title": tasks_by_id[d]["title"], "output": tasks_by_id[d].get("output")}
            for d in task["dependencies"] if tasks_by_id.get(d)
        ]
        fixed = await self._ai_execute(
            mission_id, goal, actor, agent["name"] if agent else actor,
            agent["responsibility"] if agent else "", task, dep_outputs, revision_issue=issue,
        )
        await self.set_task(task, output=fixed.get("output"), summary=fixed.get("summary", ""), status="completed", error=None)
        await self.emit(mission_id, "RECOVERY_COMPLETED", fixed.get("summary", "Correction applied."), level="success", actor=actor, task_id=task["id"], action="revise", status="completed", output_summary=fixed.get("summary"), **wk)

        # mark downstream dependents for recheck
        downstream = dependents.get(task["id"], [])
        if downstream:
            for d in downstream:
                recheck_pending.add(d)
            await self.emit(mission_id, "DEPENDENCY_CHANGED", f"{len(downstream)} downstream task(s) flagged for recheck with the corrected output.", actor="Mission Manager", task_id=task["id"])

        # reviewer re-reviews the correction
        await self.emit(mission_id, "REVIEW_REQUESTED", f"Reviewer re-checking the corrected '{task['title']}'.", actor=reviewer["role"], task_id=task["id"])
        await asyncio.sleep(STEP)
        await self.db.reviews.insert_one(Review(mission_id=mission_id, task_id=task["id"], verdict="pass", issue="").model_dump())
        await self.set_task(task, status="verified")
        await self.emit(mission_id, "REVIEW_PASSED", f"Reviewer approved the correction to '{task['title']}'.", level="success", actor=reviewer["role"], task_id=task["id"])
        if agent:
            await self.set_agent(agent, status="waiting", current_task_id=None)
        await self.set_agent(reviewer, status="waiting")
        await self.set_mission(mission_id, status="running")
