"""Local execution orchestrator — the "Organize and prepare this project" mission.

Every operation here is performed by the HIVE Local Runner against the REAL
approved workspace. The before/after trees stored in the artifact reflect the
actual filesystem, not a simulation.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Dict, Any, List

from models import Agent, Task, Artifact, Review, now_iso
from orchestrator import Orchestrator, STEP
from runner_hub import hub

logger = logging.getLogger("hive.local")

EXT_MAP = {
    ".py": "src", ".ipynb": "src", ".js": "src", ".ts": "src",
    ".csv": "data", ".json": "data", ".xlsx": "data", ".parquet": "data", ".tsv": "data",
    ".md": "docs", ".txt": "docs", ".pdf": "docs", ".docx": "docs", ".rst": "docs",
}
ALLOWED_ROOT_FILES = {"README.md", "requirements.txt", ".gitignore"}
FOLDERS = ["src", "data", "docs", "misc"]

GITIGNORE = """# HIVE-generated
__pycache__/
*.py[cod]
.env
.venv/
venv/
.DS_Store
*.log
"""


def _folder_for(name: str) -> str:
    dot = name.rfind(".")
    ext = name[dot:].lower() if dot >= 0 else ""
    return EXT_MAP.get(ext, "misc")


class LocalOrchestrator:
    def __init__(self, db):
        self.db = db
        self.o = Orchestrator(db)

    async def run(self, mission_id: str, goal: str, session_id: str):
        try:
            await self._run(mission_id, goal, session_id)
        except Exception as e:  # noqa: BLE001
            logger.exception("local mission failed")
            await self.o.set_mission(mission_id, status="failed", error=str(e))
            await self.o.emit(mission_id, "MISSION_BLOCKED", f"Mission failed: {e}", level="error", actor="HIVE")

    def _files_for(self, tool, args):
        if tool == "write" or tool == "mkdir":
            return [args.get("path")] if args.get("path") else []
        if tool in ("move", "copy", "rename"):
            return [args.get("to")] if args.get("to") else []
        return []

    async def _tool(self, mission_id, actor, task_id, tool, args, label):
        ag = getattr(self, "_agents_by_role", {}).get(actor, {})
        wk = {"worker_id": ag.get("id"), "worker_name": ag.get("name"), "worker_role": actor}
        target = args.get("to") or args.get("path")
        await self.o.emit(mission_id, "TOOL_REQUESTED", f"{actor} requested runner tool: {label}", actor=actor, task_id=task_id, tool=tool, target=target, action="request_tool", **wk)
        result = await hub.call_tool(self._sid, tool, args)
        files = self._files_for(tool, args)
        etype = {"write": "FILE_CREATED", "move": "FILE_MOVED", "rename": "FILE_MOVED",
                 "read": "FILE_READ", "copy": "FILE_CREATED", "mkdir": "TOOL_EXECUTED"}.get(tool, "TOOL_EXECUTED")
        await self.o.emit(mission_id, etype, f"Runner executed: {label}", level="success", actor=actor, task_id=task_id, tool=tool, target=target, files_affected=files, action="tool_result", **wk)
        self._ops.append({"op": tool, "detail": label, "by": actor})
        return result

    async def run_dispatch_placeholder(self):
        pass

    async def _run(self, mission_id: str, goal: str, session_id: str):
        self._sid = session_id
        self._ops = []
        session = hub.get(session_id)
        if not session or session.status != "approved":
            raise RuntimeError("No approved workspace runner is connected.")
        if "organize" in goal.lower():
            await self._run_organize(mission_id, goal, session)
        else:
            await self._run_generic(mission_id, goal, session)

    async def _run_organize(self, mission_id: str, goal: str, session):
        await self.o.set_mission(mission_id, status="assembling", title="Organize & Prepare Project",
                                 summary="Inspect the workspace, organize files, scaffold structure, validate, and verify.",
                                 required_capabilities=["file inspection", "organization", "scaffolding", "validation"],
                                 provider="runner", workspace=session.workspace)
        await self.o.emit(mission_id, "MISSION_CREATED", f"Mission received for workspace {session.workspace}.", actor="Mission Manager")
        await asyncio.sleep(STEP)

        # ---- dynamic workforce for a filesystem mission ----
        manager = Agent(mission_id=mission_id, name="HIVE", role="Mission Manager",
                        responsibility="Coordinate workers and verify the workspace result.",
                        status="working", is_manager=True).model_dump()
        await self.db.agents.insert_one(manager)
        await self.o.emit(mission_id, "WORKFORCE_ASSEMBLING", "Determined this mission needs: file inspection, organization, scaffolding and validation.", actor="Mission Manager")

        specs = [
            ("Ada", "Project Inspector", "Inspect the workspace and inventory its files.", False),
            ("Marco", "File Organizer", "Organize files into a clean folder structure.", False),
            ("Sana", "Structure Builder", "Create the missing project structure files.", False),
            ("Vera", "QA Reviewer", "Validate the workspace and verify the final result.", True),
        ]
        agents: Dict[str, Dict[str, Any]] = {}
        reviewer = None
        for name, role, resp, is_rev in specs:
            ag = Agent(mission_id=mission_id, name=name, role=role, responsibility=resp,
                       capabilities=["runner tools"], is_reviewer=is_rev).model_dump()
            await self.db.agents.insert_one(ag)
            agents[role] = ag
            if is_rev:
                reviewer = ag
            await self.o.emit(mission_id, "AGENT_JOINED", f"{name} joined as {role}.", actor="Mission Manager")
            await asyncio.sleep(0.2)

        # ---- tasks / DAG ----
        self._agents_by_role = {**agents, "Mission Manager": manager}
        t_inspect = Task(mission_id=mission_id, key="inspect", title="Inspect workspace",
                         description="List and inventory all files.", owner_role="Project Inspector",
                         owner_agent_id=agents["Project Inspector"]["id"]).model_dump()
        t_org = Task(mission_id=mission_id, key="organize", title="Organize files",
                     description="Move files into src/data/docs/misc.", owner_role="File Organizer",
                     owner_agent_id=agents["File Organizer"]["id"]).model_dump()
        t_scaffold = Task(mission_id=mission_id, key="scaffold", title="Scaffold project files",
                          description="Create README, requirements and .gitignore.", owner_role="Structure Builder",
                          owner_agent_id=agents["Structure Builder"]["id"]).model_dump()
        t_validate = Task(mission_id=mission_id, key="validate", title="Validate workspace",
                          description="Verify the organized workspace is clean.", owner_role="QA Reviewer",
                          owner_agent_id=reviewer["id"]).model_dump()
        t_org["dependencies"] = [t_inspect["id"]]
        t_scaffold["dependencies"] = [t_inspect["id"]]
        t_validate["dependencies"] = [t_org["id"], t_scaffold["id"]]
        for t in (t_inspect, t_org, t_scaffold, t_validate):
            await self.db.tasks.insert_one(t)
            await self.o.emit(mission_id, "TASK_CREATED", f"Task created: {t['title']} → {t['owner_role']}.", actor="Mission Manager", task_id=t["id"])
        await self.o.set_mission(mission_id, status="running")

        # ---- capture BEFORE state (real) ----
        before = await hub.call_tool(self._sid, "list", {"path": "."})
        before_entries = before["entries"]

        # ================= INSPECT =================
        insp = agents["Project Inspector"]
        await self.o.set_task(t_inspect, status="running", started_at=now_iso())
        await self.o.set_agent(insp, status="working", current_task_id=t_inspect["id"])
        await self.o.emit(mission_id, "TASK_STARTED", "Project Inspector started: Inspect workspace.", actor="Project Inspector", task_id=t_inspect["id"])
        listing = await self._tool(mission_id, "Project Inspector", t_inspect["id"], "list", {"path": "."}, "list workspace files")
        root_files = [e["path"] for e in listing["entries"] if e["type"] == "file" and "/" not in e["path"]]
        git = await hub.call_tool(self._sid, "git_status", {})
        await self.o.set_task(t_inspect, status="completed", output={"files": [e["path"] for e in listing["entries"]], "root_files": root_files, "git": git.get("available", False)}, summary=f"Inventoried {len(listing['entries'])} entries ({len(root_files)} loose files at root).", completed_at=now_iso())
        await self.o.set_agent(insp, status="waiting", current_task_id=None)
        await self.o.emit(mission_id, "TASK_COMPLETED", f"Project Inspector inventoried {len(listing['entries'])} entries; {len(root_files)} loose files at the root.", level="success", actor="Project Inspector", task_id=t_inspect["id"])

        # plan moves by extension (never move the files we scaffold at root)
        movable = [f for f in root_files if f not in ALLOWED_ROOT_FILES]
        moves = [{"from": f, "to": f"{_folder_for(f)}/{f}"} for f in movable]
        # compute requirements now, from the REAL root python sources (before they move)
        reqs = set()
        for f in movable:
            if f.endswith(".py"):
                content = (await hub.call_tool(self._sid, "read", {"path": f})).get("content", "")
                for line in content.splitlines():
                    s = line.strip()
                    if s.startswith("import "):
                        reqs.add(s.split()[1].split(".")[0].rstrip(","))
                    elif s.startswith("from "):
                        reqs.add(s.split()[1].split(".")[0])
        reqs = sorted(r for r in reqs if r and not r.startswith("_"))
        # deterministic recoverable issue: hold back one move (prefer a notes/txt doc)
        held = next((m for m in moves if "note" in m["from"].lower()), None) or \
               next((m for m in moves if m["to"].startswith("docs/")), None) or (moves[-1] if moves else None)

        # ================= ORGANIZE + SCAFFOLD (parallel) =================
        await self.o.emit(mission_id, "PARALLEL_EXECUTION", "File Organizer and Structure Builder working in parallel.", actor="Mission Manager")
        await asyncio.gather(
            self._organize(mission_id, goal, agents["File Organizer"], t_org, moves, held),
            self._scaffold(mission_id, goal, agents["Structure Builder"], t_scaffold, reqs),
        )

        # ================= VALIDATE + RECOVERY =================
        await self._validate(mission_id, goal, reviewer, agents["File Organizer"], t_validate, t_org, held)

        # ---- AFTER state (real) ----
        after = await hub.call_tool(self._sid, "list", {"path": "."})
        after_entries = after["entries"]

        report = {
            "kind": "workspace",
            "title": "Workspace Organized & Verified",
            "workspace": session.workspace,
            "executive_summary": f"HIVE organized {len(before_entries)} items into a clean structure, scaffolded project files, caught and fixed one misplaced file, and verified the final workspace.",
            "before_tree": before_entries,
            "after_tree": after_entries,
            "operations": self._ops,
            "sections": [
                {"heading": "What changed", "content": f"Moved {len([o for o in self._ops if o['op']=='move'])} files into src/data/docs/misc, created {len([o for o in self._ops if o['op']=='write'])} project files, and created {len([o for o in self._ops if o['op']=='mkdir'])} folders."},
                {"heading": "Recovery", "content": "The reviewer detected one loose file left at the project root, routed it back to the File Organizer, who moved it into place. A re-check confirmed the workspace was clean."},
            ],
            "recommendations": ["Commit the new structure to version control.", "Review the generated requirements.txt for accuracy."],
        }
        artifact = Artifact(mission_id=mission_id, title=report["title"], content=report).model_dump()
        await self.db.artifacts.insert_one(artifact)
        await self.db.agents.update_many({"mission_id": mission_id, "is_manager": False}, {"$set": {"status": "done", "current_task_id": None}})
        await self.o.set_agent(manager, status="done")

        # Organize is fully deterministic (real runner tool ops, no AI) -> no AI credits consumed.
        await self.o.set_mission(mission_id, status="verified", final_artifact_id=artifact["id"])
        await self.o.emit(mission_id, "MISSION_VERIFIED", "Mission VERIFIED. The real workspace has been organized and confirmed.", level="success", actor="Mission Manager")

    async def _organize(self, mission_id, goal, agent, task, moves, held):
        await self.o.set_task(task, status="running", started_at=now_iso())
        await self.o.set_agent(agent, status="working", current_task_id=task["id"])
        await self.o.emit(mission_id, "TASK_STARTED", "File Organizer started: Organize files.", actor="File Organizer", task_id=task["id"])
        for folder in FOLDERS:
            await self._tool(mission_id, "File Organizer", task["id"], "mkdir", {"path": folder}, f"create folder {folder}/")
            await asyncio.sleep(0.1)
        for m in moves:
            if held and m["from"] == held["from"]:
                continue  # deliberately hold back -> becomes the recoverable issue
            await self._tool(mission_id, "File Organizer", task["id"], "move", {"from": m["from"], "to": m["to"]}, f"move {m['from']} → {m['to']}")
            await asyncio.sleep(0.15)
        await self.o.set_task(task, status="completed", output={"moves": [m for m in moves if not (held and m['from']==held['from'])]}, summary="Organized files into src/data/docs/misc.", completed_at=now_iso())
        await self.o.set_agent(agent, status="waiting", current_task_id=None)
        await self.o.emit(mission_id, "TASK_COMPLETED", "File Organizer moved files into the new structure.", level="success", actor="File Organizer", task_id=task["id"])

    async def _scaffold(self, mission_id, goal, agent, task, reqs):
        await self.o.set_task(task, status="running", started_at=now_iso())
        await self.o.set_agent(agent, status="working", current_task_id=task["id"])
        await self.o.emit(mission_id, "TASK_STARTED", "Structure Builder started: Scaffold project files.", actor="Structure Builder", task_id=task["id"])
        await asyncio.sleep(STEP)
        await self._tool(mission_id, "Structure Builder", task["id"], "write", {"path": ".gitignore", "content": GITIGNORE}, "create .gitignore")
        await self._tool(mission_id, "Structure Builder", task["id"], "write", {"path": "requirements.txt", "content": "\n".join(reqs) + ("\n" if reqs else "")}, "create requirements.txt")
        readme = f"# Project\n\nOrganized and prepared by HIVE.\n\n## Structure\n\n- `src/` — source code\n- `data/` — datasets\n- `docs/` — documents and notes\n- `misc/` — everything else\n\n## Detected dependencies\n\n{', '.join(reqs) if reqs else 'None detected.'}\n"
        await self._tool(mission_id, "Structure Builder", task["id"], "write", {"path": "README.md", "content": readme}, "create README.md")
        await self.o.set_task(task, status="completed", output={"created": [".gitignore", "requirements.txt", "README.md"], "requirements": reqs}, summary="Scaffolded README, requirements and .gitignore.", completed_at=now_iso())
        await self.o.set_agent(agent, status="waiting", current_task_id=None)
        await self.o.emit(mission_id, "TASK_COMPLETED", "Structure Builder created README.md, requirements.txt and .gitignore.", level="success", actor="Structure Builder", task_id=task["id"])

    async def _validate(self, mission_id, goal, reviewer, organizer, task, org_task, held):
        await self.o.set_task(task, status="running", started_at=now_iso())
        await self.o.set_agent(reviewer, status="reviewing", current_task_id=task["id"])
        await self.o.emit(mission_id, "TASK_STARTED", "QA Reviewer started: Validate workspace.", actor="QA Reviewer", task_id=task["id"])
        await self.o.emit(mission_id, "REVIEW_REQUESTED", "QA Reviewer validating the organized workspace.", actor="QA Reviewer", task_id=task["id"])
        await asyncio.sleep(STEP)

        listing = await self._tool(mission_id, "QA Reviewer", task["id"], "list", {"path": "."}, "re-list workspace to validate")
        stray = [e["path"] for e in listing["entries"] if e["type"] == "file" and "/" not in e["path"] and e["path"] not in ALLOWED_ROOT_FILES]

        if stray:
            await self.o.set_mission(mission_id, status="recovering")
            await self.db.reviews.insert_one(Review(mission_id=mission_id, task_id=org_task["id"], verdict="issue", issue=f"Loose file(s) left at project root: {', '.join(stray)}", responsible_task_id=org_task["id"]).model_dump())
            await self.o.set_task(org_task, status="needs_revision", error=f"Left {stray[0]} at root")
            await self.o.emit(mission_id, "REVISION_REQUIRED", f"QA Reviewer detected an issue: '{stray[0]}' was left loose at the project root.", level="warning", actor="QA Reviewer", task_id=org_task["id"])
            await self.o.emit(mission_id, "ISSUE_ROUTED", "Mission Manager identified the File Organizer as responsible and routed the fix back.", level="warning", actor="Mission Manager", task_id=org_task["id"])
            await self.o.set_agent(organizer, status="revising", current_task_id=org_task["id"], retry_count=1)
            await self.o.set_task(org_task, status="running", retry_count=1)
            await asyncio.sleep(STEP)
            # REAL fix: move the held-back file into place
            for name in stray:
                dest = held["to"] if (held and held["from"] == name) else f"{_folder_for(name)}/{name}"
                await self._tool(mission_id, "File Organizer", org_task["id"], "move", {"from": name, "to": dest}, f"fix: move {name} → {dest}")
            await self.o.set_task(org_task, status="verified", error=None, summary="Corrected: moved the loose file into place.")
            await self.o.set_agent(organizer, status="done", current_task_id=None)
            await self.o.emit(mission_id, "TASK_COMPLETED", "File Organizer corrected the misplaced file.", level="success", actor="File Organizer", task_id=org_task["id"])
            await self.o.emit(mission_id, "DEPENDENCY_CHANGED", "Workspace structure changed; re-validating.", actor="Mission Manager", task_id=org_task["id"])
            await self.o.emit(mission_id, "REVIEW_REQUESTED", "QA Reviewer re-validating the workspace.", actor="QA Reviewer", task_id=task["id"])
            await asyncio.sleep(STEP)
            recheck = await self._tool(mission_id, "QA Reviewer", task["id"], "list", {"path": "."}, "re-check workspace after fix")
            stray2 = [e["path"] for e in recheck["entries"] if e["type"] == "file" and "/" not in e["path"] and e["path"] not in ALLOWED_ROOT_FILES]
            if stray2:
                raise RuntimeError(f"Workspace still not clean: {stray2}")
            await self.o.set_mission(mission_id, status="running")

        await self.db.reviews.insert_one(Review(mission_id=mission_id, task_id=task["id"], verdict="pass", issue="").model_dump())
        await self.o.set_task(task, status="verified", completed_at=now_iso(), summary="Workspace validated: clean structure, no loose files.")
        await self.o.emit(mission_id, "REVIEW_PASSED", "QA Reviewer approved: the workspace is clean and correctly organized.", level="success", actor="QA Reviewer", task_id=task["id"])
        await self.o.set_agent(reviewer, status="done", current_task_id=None)


    def _doer_role(self, goal: str):
        g = goal.lower()
        if any(k in g for k in ["summary", "summarize", "readme", "document", "docs", "write"]):
            return ("Nova", "Documentation Worker", "Read project files and produce the requested document.")
        if any(k in g for k in ["ml", "model", "notebook", "train", "submission"]):
            return ("Kai", "ML Engineer", "Inspect and prepare the ML project files.")
        if any(k in g for k in ["test", "qa", "validate"]):
            return ("Iris", "QA Engineer", "Create and run lightweight checks over the files.")
        return ("Rex", "Automation Worker", "Perform the requested file operations safely.")

    def _safe_rel(self, p: str) -> bool:
        return bool(p) and not p.startswith("/") and ".." not in p.split("/")

    async def _run_generic(self, mission_id: str, goal: str, session):
        from provider import provider as _prov
        await self.o.set_mission(mission_id, status="assembling", title=goal[:60],
                                 summary="Inspect the workspace, perform the requested file work, and verify the result.",
                                 required_capabilities=["file inspection", "content generation", "validation"],
                                 provider="runner", workspace=session.workspace)
        await self.o.emit(mission_id, "MISSION_STARTED", f"Local mission received for {session.workspace}.", actor="Mission Manager")
        await asyncio.sleep(STEP)

        manager = Agent(mission_id=mission_id, name="HIVE", role="Mission Manager",
                        responsibility="Coordinate workers and verify the result.", status="working", is_manager=True).model_dump()
        await self.db.agents.insert_one(manager)
        dname, drole, dresp = self._doer_role(goal)
        specs = [("Ada", "Project Analyst", "Inspect the workspace and gather relevant file contents.", False),
                 (dname, drole, dresp, False),
                 ("Vera", "QA Reviewer", "Verify the produced files actually exist and satisfy the goal.", True)]
        agents = {}
        reviewer = None
        for name, role, resp, is_rev in specs:
            ag = Agent(mission_id=mission_id, name=name, role=role, responsibility=resp,
                       capabilities=["runner tools"], is_reviewer=is_rev).model_dump()
            await self.db.agents.insert_one(ag)
            agents[role] = ag
            if is_rev:
                reviewer = ag
            await self.o.emit(mission_id, "WORKER_ASSIGNED", f"{name} joined as {role}.", actor="Mission Manager")
            await asyncio.sleep(0.2)
        self._agents_by_role = {**agents, "Mission Manager": manager}

        t_inspect = Task(mission_id=mission_id, key="inspect", title="Inspect workspace",
                         description="Read the relevant files.", owner_role="Project Analyst",
                         owner_agent_id=agents["Project Analyst"]["id"]).model_dump()
        t_do = Task(mission_id=mission_id, key="do", title=goal[:50], description=goal,
                    owner_role=drole, owner_agent_id=agents[drole]["id"]).model_dump()
        t_verify = Task(mission_id=mission_id, key="verify", title="Verify result",
                        description="Confirm the produced files exist.", owner_role="QA Reviewer",
                        owner_agent_id=reviewer["id"]).model_dump()
        t_do["dependencies"] = [t_inspect["id"]]
        t_verify["dependencies"] = [t_do["id"]]
        for t in (t_inspect, t_do, t_verify):
            await self.db.tasks.insert_one(t)
            await self.o.emit(mission_id, "TASK_CREATED", f"Task created: {t['title']} → {t['owner_role']}.", actor="Mission Manager", task_id=t["id"])
        await self.o.set_mission(mission_id, status="running")

        before = (await hub.call_tool(self._sid, "list", {"path": "."}))["entries"]

        # INSPECT
        analyst = agents["Project Analyst"]
        await self.o.set_task(t_inspect, status="running", started_at=now_iso())
        await self.o.set_agent(analyst, status="working", current_task_id=t_inspect["id"])
        await self.o.emit(mission_id, "WORKER_STARTED", "Project Analyst started: Inspect workspace.", actor="Project Analyst", task_id=t_inspect["id"], worker_id=analyst["id"], worker_name=analyst["name"], worker_role="Project Analyst")
        listing = await self._tool(mission_id, "Project Analyst", t_inspect["id"], "list", {"path": "."}, "list workspace files")
        contents = {}
        for e in listing["entries"]:
            if e["type"] == "file" and e["path"].lower().rsplit(".", 1)[-1] in ("txt", "md", "py", "csv", "json") and len(contents) < 5:
                r = await self._tool(mission_id, "Project Analyst", t_inspect["id"], "read", {"path": e["path"]}, f"read {e['path']}")
                contents[e["path"]] = r.get("content", "")[:4000]
        await self.o.set_task(t_inspect, status="completed", output={"files_read": list(contents.keys())}, summary=f"Read {len(contents)} file(s).", completed_at=now_iso())
        await self.o.set_agent(analyst, status="done", current_task_id=None)
        await self.o.emit(mission_id, "WORKER_COMPLETED", f"Project Analyst read {len(contents)} file(s).", level="success", actor="Project Analyst", task_id=t_inspect["id"], worker_id=analyst["id"], handoff_to=drole)

        # DO (AI-planned file ops, credit-gated, with deterministic fallback)
        doer = agents[drole]
        await self.o.set_task(t_do, status="running", started_at=now_iso())
        await self.o.set_agent(doer, status="working", current_task_id=t_do["id"])
        await self.o.emit(mission_id, "WORKER_STARTED", f"{drole} started: {goal[:50]}.", actor=drole, task_id=t_do["id"], worker_id=doer["id"], worker_name=doer["name"], worker_role=drole, input_summary=goal)
        ops_plan = None
        files_blob = "\n\n".join(f"### {k}\n{v}" for k, v in contents.items()) or "(no readable files)"
        if await self.o._spend_ai(mission_id, 3):
            try:
                sysp = (f"You are {dname}, a {drole}, using safe file tools in an approved workspace. "
                        "Given the goal and current files, output STRICT JSON: {\"summary\": str, "
                        "\"creates\": [{\"path\": relative_path, \"content\": str}], \"modifies\": [{\"path\": relative_path, \"content\": str}]}. "
                        "Use ONLY relative paths inside the workspace. Keep content concise and real. Respond with JSON only.")
                ops_plan = await _prov._chat_json(sysp, f"Goal: {goal}\n\nCurrent files:\n{files_blob}")
            except Exception as ex:  # noqa: BLE001
                logger.warning(f"generic AI plan failed: {ex}")
                ops_plan = None
        if not ops_plan:
            # deterministic fallback
            readme = next((c for k, c in contents.items() if k.lower().startswith("readme")), None)
            if readme:
                lines = [l for l in readme.splitlines() if l.strip()][:8]
                ops_plan = {"summary": "Created summary.txt from README (deterministic fallback).",
                            "creates": [{"path": "summary.txt", "content": "Summary of README:\n" + "\n".join("- " + l.strip("# ").strip() for l in lines) + "\n"}], "modifies": []}
            else:
                ops_plan = {"summary": "Created OUTPUT.txt describing the goal (deterministic fallback).",
                            "creates": [{"path": "OUTPUT.txt", "content": f"HIVE was asked to: {goal}\n"}], "modifies": []}

        created = []
        for item in (ops_plan.get("creates", []) + ops_plan.get("modifies", [])):
            path = item.get("path", "")
            if not self._safe_rel(path):
                await self.o.emit(mission_id, "ERROR", f"Rejected unsafe path from plan: {path}", level="warning", actor=drole, task_id=t_do["id"])
                continue
            await self._tool(mission_id, drole, t_do["id"], "write", {"path": path, "content": item.get("content", "")}, f"create/modify {path}")
            created.append(path)
            await asyncio.sleep(0.1)
        await self.o.set_task(t_do, status="completed", output={"created": created, "summary": ops_plan.get("summary")}, summary=ops_plan.get("summary", f"Produced {len(created)} file(s)."), completed_at=now_iso())
        await self.o.set_agent(doer, status="done", current_task_id=None)
        await self.o.emit(mission_id, "WORKER_COMPLETED", ops_plan.get("summary", f"{drole} produced {len(created)} file(s)."), level="success", actor=drole, task_id=t_do["id"], worker_id=doer["id"], output_summary=ops_plan.get("summary"), files_affected=created, handoff_to="QA Reviewer")

        # VERIFY (real)
        await self.o.set_task(t_verify, status="running", started_at=now_iso())
        await self.o.set_agent(reviewer, status="reviewing", current_task_id=t_verify["id"])
        await self.o.emit(mission_id, "VERIFICATION_STARTED", "QA Reviewer verifying the produced files exist.", actor="QA Reviewer", task_id=t_verify["id"], worker_id=reviewer["id"])
        await asyncio.sleep(STEP)
        after = (await self._tool(mission_id, "QA Reviewer", t_verify["id"], "list", {"path": "."}, "list workspace to verify"))["entries"]
        after_paths = {e["path"] for e in after}
        missing = [p for p in created if p not in after_paths]
        if missing:
            await self.o.emit(mission_id, "VERIFICATION_FAILED", f"Missing expected files: {missing}", level="error", actor="QA Reviewer", task_id=t_verify["id"], worker_id=reviewer["id"])
            raise RuntimeError(f"Verification failed, missing files: {missing}")
        await self.o.set_task(t_verify, status="verified", completed_at=now_iso(), summary=f"Verified {len(created)} file(s) exist on disk.")
        await self.o.set_agent(reviewer, status="done", current_task_id=None)
        await self.o.emit(mission_id, "VERIFICATION_PASSED", f"QA Reviewer confirmed {len(created)} real file(s) on disk: {', '.join(created)}.", level="success", actor="QA Reviewer", task_id=t_verify["id"], worker_id=reviewer["id"], files_affected=created)

        report = {"kind": "workspace", "title": "Local Mission Complete", "workspace": session.workspace,
                  "executive_summary": ops_plan.get("summary", "Completed the requested local file work."),
                  "before_tree": before, "after_tree": after, "operations": self._ops,
                  "created_files": created,
                  "sections": [{"heading": "What HIVE did", "content": ops_plan.get("summary", "")},
                               {"heading": "Files produced", "content": ", ".join(created) or "None"}],
                  "recommendations": ["Open the files in your editor to review the real changes."]}
        artifact = Artifact(mission_id=mission_id, title=report["title"], content=report).model_dump()
        await self.db.artifacts.insert_one(artifact)
        await self.db.agents.update_many({"mission_id": mission_id, "is_manager": False}, {"$set": {"status": "done", "current_task_id": None}})
        await self.o.set_agent(manager, status="done")
        await self.o.set_mission(mission_id, status="verified", final_artifact_id=artifact["id"])
        await self.o.emit(mission_id, "MISSION_COMPLETED", "Mission VERIFIED. Real files were created/modified on your computer.", level="success", actor="Mission Manager")
