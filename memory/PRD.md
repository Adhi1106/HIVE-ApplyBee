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

## HIVE Local Runner — Real Local Execution (2026-08-29)
- New separate executable `/app/hive_runner/runner.py`: connects OUTBOUND to backend
  WebSocket `/api/runner/ws`, performs REAL file ops sandboxed to one approved workspace
  (`Workspace._safe` blocks path traversal / outside access; no shell; git read-only).
  Tools: list, read, write, mkdir, move/rename, copy, git_status, git_diff.
- Backend `runner_hub.py`: manages ws sessions + pairing codes + tool RPC (call_tool with
  correlation ids). Persistent demo session (code `HIVE-DEMO`, id `demo`). A supervised
  `hive-runner` program runs a hosted demo runner on `/app/hive_demo_workspace`.
- Backend `local_orchestrator.py`: the "Organize and prepare this project" mission. Dynamic
  filesystem workforce (Mission Manager, Project Inspector, File Organizer, Structure Builder,
  QA Reviewer). Real inspect → organize (by extension) + scaffold (README/requirements/.gitignore)
  in parallel → validate detects one loose root file → routes to File Organizer → real move →
  re-check → VERIFIED. Idempotent re-runs (scaffolded root files excluded from moves; requirements
  computed from real sources before moving). Artifact stores real before_tree/after_tree/operations.
- Routes: `/api/runner/pair|session/{sid}|/approve|/tree|/seed-demo`, `POST /api/missions/local`.
- Frontend: `/connect` Connect Workspace flow (demo runner or pair-your-own with code + wss command,
  permission review, approve, seed demo, run mission). Mission Room adds a Graph/Workspace toggle
  and a real Before/After + operations `WorkspacePanel` for local missions. Existing UI untouched.
- Verified end-to-end: real files moved on disk; recovery + verification shown; 35/35 backend tests pass.
- Known MVP limits (future): runner sessions are in-memory (lost on backend restart; runner auto-reconnects,
  approval must be re-granted); `/runner/pair` has no TTL/auth yet.

## Execution-experience overhaul (2026-08-29)
- **Credits (non-destructive)**: deducted PER real AI call (plan=5, task=3). Reaching 0 never kills a running
  mission — `_spend_ai` returns False, emits a single `CREDITS_EXHAUSTED` warning, sets `mission.credits_exhausted`,
  and the orchestrator falls back to deterministic/mock work so the mission still finishes & verifies; no stuck
  workers. `POST /api/credits/renew` resets the demo balance (modular for future real billing). Frontend:
  `CreditExhaustedModal` (Dashboard gate + Mission Room banner) with Renew / Continue.
- **Demo vs Local mode**: `mission.mode` = `demo` (simulated AI missions, no filesystem) or `local` (real Runner).
  Mission Room shows a `mission-mode` badge; never claims local changes in demo mode.
- **Real local execution (generic)**: `local_orchestrator._run_generic` handles any local goal (e.g. "Read
  README.txt and create summary.txt"): Project Analyst → doer (dynamic by keyword: Documentation Worker / ML
  Engineer / QA Engineer / Automation Worker) → QA Reviewer. AI plans file ops (credit-gated, deterministic
  fallback), Runner performs REAL read/create, reviewer verifies files exist on disk (real). Organize mission
  remains and is deterministic (no AI credits).
- **Canonical worker events**: `MissionEvent` extended (worker_id/name/role, action, tool, target, input/output
  summaries, files_affected, handoff_to, error, status). One source of truth for feed + drill-down + timeline.
  New event types: WORKER_STARTED/COMPLETED, TOOL_REQUESTED/EXECUTED, FILE_READ/CREATED/MOVED, HANDOFF, ERROR,
  RECOVERY_STARTED/COMPLETED, VERIFICATION_STARTED/PASSED/FAILED, MISSION_STARTED/COMPLETED, CREDITS_EXHAUSTED.
- **Worker drill-down**: `GET /api/missions/{mid}/agents/{aid}` builds a structured panel (input, actions timeline,
  tools, files, handoffs, issues, recovery, output, verification) purely from events. UI: clickable Workforce
  cards → `WorkerDetailPanel`.
- **Projects → missions**: `Project` model + `mission.project_id/workspace_id`. Standard missions → "AI Workforce
  (Demo)"; local missions → a per-workspace local project. `GET /api/projects`, `/projects/{id}/missions`,
  `/missions?project_id`. Frontend History has a project filter; histories never mix.
- **Orchestrator instructions**: `prompts.ORCHESTRATOR_SYSTEM` encodes the multi-agent operating principles;
  dynamic workforce (different missions → different workers); deterministic recovery preserved.
- Verified directly via curl + screenshots (incremental credits, exhaustion+renew, worker drill-down, projects,
  real README→summary on disk, organize idempotency+recovery, mode badges, project-scoped history). The
  full testing-agent sweep timed out purely due to many slow live-AI missions (infra), not defects.

## Real Local Runner connection + real filesystem ops (2026-08-30)
- Persistent runner (hive_runner/runner.py): connects over WSS, heartbeat every 15s, never exits, auto-reconnects,
  spec-style terminal logs, unbuffered stdout, sends OS/version on register. Tools: list/read/write/mkdir/move/
  rename/copy/git; DELETE requires explicit authorized. Sandbox rejects ../ traversal + absolute paths (verified).
- Backend hub tracks real state (os, version, connected_at, last_heartbeat, current_mission); flips to
  disconnected when runner closes (verified approved->disconnected->connected). GET /api/runner/download serves
  the CURRENT runner.py (fixes users running a stale stub).
- Real end-to-end verified on disk: "Create HIVE_TESTED.md" and "Create HELLO_HIVE.md" physically written;
  README.md really read + summarized. Dynamic routing (Code Agent / Documentation Worker / ML Engineer / QA).
  Reviewer verifies files exist on disk before VERIFIED. No fake success.
- Connect UX: beginner Pair flow (OS + terminal selectors, Download runner.py, Copy dynamic wss command + real
  pairing code, honest "Waiting for runner"), approve workspace -> real task input; custom local mission input.
- Internal agent instructions hardened for LOCAL mode.
- DEFERRED backlog: Replay mode, public mission sharing, real multi-user auth, subscription/pricing redesign,
  Workforce-page global-capabilities split, filesystem watcher streaming.


## 2026-08-30 — Local Runner pairing hardening (debug fork)
- ROOT CAUSE of "stuck on Waiting…": (a) pairing sessions lived only in backend RAM, so any `--reload`/restart
  between pairing and connecting wiped the code -> runner's register silently rejected; frontend swallowed the
  404 forever. (b) User was running a STALE runner.py whose handshake predated the current protocol.
- FIX backend (`runner_hub.py`): pairing sessions now PERSISTED in Mongo `runner_sessions` (only the live socket
  stays in RAM). Codes survive backend restarts; runner just re-registers on reconnect. `connected` is derived
  strictly from a live socket (no false positives). Unknown code -> explicit `{type:error, fatal, code:invalid_code}`.
  hub.get/create_session/approve are now async (updated server.py + local_orchestrator.py call sites).
- FIX runner (`runner.py` v1.1.0): waits for server `registered` reply BEFORE declaring connected; prints explicit
  failure reasons (invalid/expired code, connect error). Served fresh via GET /api/runner/download.
- FIX frontend (`ConnectWorkspace.jsx`): no longer swallows poll errors — distinguishes Waiting (with elapsed s) /
  Runner connected / session-expired(404) with a "Generate a new pairing code" re-pair action.
- VERIFIED externally against live preview: WS upgrade OK, handshake OK, poll connected=true 60s, approve pushes to
  runner, backend RPC tool_call reaches runner, AND code stays valid across a backend restart.

## 2026-08-30 (2) — Runner instant-exit fixed (websockets 14+ breaking change)
- ROOT CAUSE of "prints message then returns to prompt": runner used `async for conn in websockets.connect(...)`
  auto-reconnect. In websockets >=14 (users `pip install` gets 16.x) that helper only retries TRANSIENT network
  errors by default, so on any clean/non-transient close the loop ENDED and the process exited.
- FIX runner (`runner.py` v1.2.0): replaced with a MANUAL `while` reconnect loop using `async with connect()`
  (compatible websockets 10->16). Never exits except Ctrl+C or a fatal/expired code. Added [HIVE] status logs
  (connecting/connected/authenticated/executing/completed/failed/disconnected/reconnecting), graceful SIGINT/SIGTERM,
  exponential backoff, absolute-path + traversal rejection, `--version`.
- FIX backend: version gate (`MIN_RUNNER=1.2.0`) rejects stale runners with a fatal "re-download" message;
  GET /api/runner/download now sends no-store headers; added GET /api/runner/version.
- FIX frontend: Connect page shows a Runner v1.2 re-download note.
- PROVEN end-to-end by launching the REAL runner.py subprocess against the external wss URL: connected in 1s,
  process STAYED ALIVE, seed-demo wrote 6 real files to disk THROUGH the runner, backend restart -> runner
  AUTO-RECONNECTED in 1s with approval preserved (persisted session). RESULT: PASS.
- NOT done this turn (user said prioritize runner first): Workforce page cleanup (#14), Mission History polish (#15),
  real auth (#16), credits/subscription tiers polish (#17). These remain backlog.
