# HIVE — AI Workforce Orchestration (PRD)

## Original Problem
Build the first functional MVP of HIVE: an AI workforce orchestration platform.
A user gives a high-level goal; HIVE dynamically assembles a specialist AI
workforce, breaks the mission into a task DAG with dependencies, runs tasks
(parallel where possible), lets agents communicate via mission events, detects a
problem, identifies the responsible agent, recovers, rechecks dependencies,
reviews, and marks the mission VERIFIED with a tangible deliverable.
NOT a chatbot. Prioritize workflow/functionality over polish. Clean dark UI.

## Architecture
- Frontend: React (CRA/craco) + Tailwind + shadcn/ui + @xyflow/react (React Flow) + dagre.
- Backend: FastAPI (single service), MongoDB (motor). String UUID ids for clean
  future migration to PostgreSQL/Supabase.
- AI: provider abstraction (`provider.py`) → OpenAI-compatible chat completions
  (`gpt-5-nano`, JSON mode) with deterministic mock fallback (`mock_provider.py`).
  Keys via backend/.env (OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL). Never hardcoded.
- Orchestrator (`orchestrator.py`): the Mission Manager engine. Runs async in the
  background, persists real mission state; frontend polls GET /api/missions/{id}.

## Data model (MongoDB collections)
users, missions, agents, tasks, mission_events, artifacts, reviews.

## Core AI functions
plan_mission → dynamic workforce + task DAG; execute_task (per agent);
review + deterministic controlled issue → identify responsible agent → recover
→ recheck dependents → re-review → final_report → VERIFIED.

## Implemented (2026-08-29)
- Dashboard: large mission input, HIVE IT, example missions, demo mission, credits.
- Mission Room: React Flow DAG (Mission Manager → tasks → Reviewer → Verified),
  live workforce side panel, live activity feed, recovery banner, verified deliverable dialog.
- Dynamic workforce (LLM-decided, not hardcoded), parallel wave execution.
- Deterministic reviewer-caught inconsistency + responsibility routing + recovery + recheck.
- Mission History, Workforce, Credits pages. Safety guard blocks unsafe missions.
- Live AI verified working end-to-end + mock fallback.

## Backlog (future)
- P1: SSE/websocket streaming instead of polling; per-task output drill-down panel.
- P1: real auth + multi-user; persistent per-mission memory.
- P2: subscriptions/billing, mission limits, workforce marketplace, integrations.
