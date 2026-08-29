"""Deterministic mock provider — reliable fallback so the full HIVE workflow
(workforce -> tasks -> collaboration -> failure -> recovery -> review -> VERIFIED)
always works even when the live AI is unavailable."""
from __future__ import annotations
from typing import Dict, Any


def _plan_churn() -> Dict[str, Any]:
    return {
        "title": "SaaS Churn Investigation",
        "summary": "Determine the likely causes of the 20% churn increase and recommend corrective actions.",
        "required_capabilities": ["data analysis", "user research", "business strategy", "quality review"],
        "workforce": [
            {"name": "Dana", "role": "Data Analyst", "responsibility": "Quantify churn patterns from the provided metrics.", "capabilities": ["cohort analysis", "metrics"]},
            {"name": "Riley", "role": "Research Analyst", "responsibility": "Surface qualitative drivers behind cancellations.", "capabilities": ["user research", "surveys"]},
            {"name": "Ben", "role": "Business Analyst", "responsibility": "Translate findings into root causes and actions.", "capabilities": ["strategy", "synthesis"]},
            {"name": "Vera", "role": "Reviewer", "responsibility": "Verify consistency and quality of all outputs.", "capabilities": ["qa", "verification"]},
        ],
        "tasks": [
            {"key": "t1", "title": "Analyze churn metrics", "description": "Break down the 20% churn increase by cohort and plan.", "owner_role": "Data Analyst", "dependencies": []},
            {"key": "t2", "title": "Gather cancellation feedback", "description": "Identify qualitative reasons users cancelled.", "owner_role": "Research Analyst", "dependencies": []},
            {"key": "t3", "title": "Determine root causes", "description": "Combine data and research into likely root causes.", "owner_role": "Business Analyst", "dependencies": ["t1", "t2"]},
            {"key": "t4", "title": "Recommend corrective actions", "description": "Propose prioritized actions to reduce churn.", "owner_role": "Business Analyst", "dependencies": ["t3"]},
        ],
    }


def _plan_marketing() -> Dict[str, Any]:
    return {
        "title": "Product Marketing Campaign",
        "summary": "Design a launch marketing campaign for the new product.",
        "required_capabilities": ["market research", "strategy", "copywriting", "quality review"],
        "workforce": [
            {"name": "Ivy", "role": "Research Agent", "responsibility": "Research audience and competitors.", "capabilities": ["market research"]},
            {"name": "Marcus", "role": "Marketing Strategist", "responsibility": "Define channels, messaging and timeline.", "capabilities": ["strategy"]},
            {"name": "Cleo", "role": "Copywriter", "responsibility": "Write launch copy and taglines.", "capabilities": ["copywriting"]},
            {"name": "Vera", "role": "Reviewer", "responsibility": "Verify quality and consistency.", "capabilities": ["qa"]},
        ],
        "tasks": [
            {"key": "t1", "title": "Research target audience", "description": "Identify audience segments and competitors.", "owner_role": "Research Agent", "dependencies": []},
            {"key": "t2", "title": "Build campaign strategy", "description": "Define channels, budget split and timeline.", "owner_role": "Marketing Strategist", "dependencies": ["t1"]},
            {"key": "t3", "title": "Write launch copy", "description": "Create taglines and channel copy.", "owner_role": "Copywriter", "dependencies": ["t2"]},
            {"key": "t4", "title": "Draft launch calendar", "description": "Sequence activities into a launch calendar.", "owner_role": "Marketing Strategist", "dependencies": ["t2"]},
        ],
    }


def _plan_build() -> Dict[str, Any]:
    return {
        "title": "Software Product Build Plan",
        "summary": "Plan and outline the build of the requested software product.",
        "required_capabilities": ["product planning", "frontend", "backend", "quality review"],
        "workforce": [
            {"name": "Priya", "role": "Product Planner", "responsibility": "Define scope and requirements.", "capabilities": ["planning"]},
            {"name": "Leo", "role": "Frontend Developer", "responsibility": "Design the UI structure.", "capabilities": ["frontend"]},
            {"name": "Sam", "role": "Backend Developer", "responsibility": "Design the API and data model.", "capabilities": ["backend"]},
            {"name": "Vera", "role": "Reviewer", "responsibility": "QA the plan for consistency.", "capabilities": ["qa"]},
        ],
        "tasks": [
            {"key": "t1", "title": "Define product scope", "description": "List core features and requirements.", "owner_role": "Product Planner", "dependencies": []},
            {"key": "t2", "title": "Design frontend structure", "description": "Outline pages and components.", "owner_role": "Frontend Developer", "dependencies": ["t1"]},
            {"key": "t3", "title": "Design backend API", "description": "Define endpoints and data model.", "owner_role": "Backend Developer", "dependencies": ["t1"]},
            {"key": "t4", "title": "Integration plan", "description": "Describe how frontend and backend connect.", "owner_role": "Backend Developer", "dependencies": ["t2", "t3"]},
        ],
    }


def _plan_generic() -> Dict[str, Any]:
    return {
        "title": "Mission Plan",
        "summary": "Research, analyze and produce a verified deliverable for the goal.",
        "required_capabilities": ["research", "analysis", "strategy", "quality review"],
        "workforce": [
            {"name": "Riley", "role": "Research Analyst", "responsibility": "Gather relevant background and facts.", "capabilities": ["research"]},
            {"name": "Dana", "role": "Data Analyst", "responsibility": "Analyze information and find patterns.", "capabilities": ["analysis"]},
            {"name": "Ben", "role": "Business Analyst", "responsibility": "Synthesize findings and recommend actions.", "capabilities": ["strategy"]},
            {"name": "Vera", "role": "Reviewer", "responsibility": "Verify quality and consistency.", "capabilities": ["qa"]},
        ],
        "tasks": [
            {"key": "t1", "title": "Research the topic", "description": "Collect key facts and context.", "owner_role": "Research Analyst", "dependencies": []},
            {"key": "t2", "title": "Analyze information", "description": "Identify trends and insights.", "owner_role": "Data Analyst", "dependencies": []},
            {"key": "t3", "title": "Synthesize findings", "description": "Combine research and analysis.", "owner_role": "Business Analyst", "dependencies": ["t1", "t2"]},
            {"key": "t4", "title": "Recommend actions", "description": "Propose prioritized recommendations.", "owner_role": "Business Analyst", "dependencies": ["t3"]},
        ],
    }


def plan_mission(goal: str) -> Dict[str, Any]:
    g = goal.lower()
    if "churn" in g or "saas" in g:
        return _plan_churn()
    if "market" in g or "campaign" in g or "launch" in g:
        return _plan_marketing()
    if "build" in g or "software" in g or "app" in g or "product" in g and "develop" in g:
        return _plan_build()
    return _plan_generic()


def execute_task(role: str, name: str, task: Dict[str, Any], deps, revision_issue=None) -> Dict[str, Any]:
    title = task.get("title", "task")
    if revision_issue:
        return {
            "summary": f"Revised '{title}' to correct the flagged inconsistency.",
            "output": {
                "headline": f"Corrected {title.lower()}",
                "details": [
                    "Re-aligned the figures so they are internally consistent.",
                    "Addressed the reviewer's note directly.",
                    "Confirmed the corrected result matches the source metrics.",
                ],
            },
        }
    return {
        "summary": f"Completed '{title}'.",
        "output": {
            "headline": f"{role} deliverable for {title.lower()}",
            "details": [
                f"Key finding produced by {name} ({role}).",
                "Grounded in the provided mission context and dependencies.",
                "Ready for downstream tasks and review.",
            ],
        },
    }


def final_report(goal: str, task_outputs) -> Dict[str, Any]:
    return {
        "title": "Verified Mission Deliverable",
        "executive_summary": "The workforce collaborated, resolved one flagged inconsistency, and produced a verified result for the mission goal.",
        "sections": [
            {"heading": t.get("title", "Section"),
             "content": (t.get("output") or {}).get("headline", "") + ". " +
                        "; ".join((t.get("output") or {}).get("details", []))}
            for t in task_outputs
        ],
        "recommendations": [
            "Act on the highest-impact finding first.",
            "Monitor results and re-run the mission if conditions change.",
        ],
    }
