"""Pydantic models and MongoDB document helpers for HIVE."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ---------- Enums (as plain strings for portability to PostgreSQL later) ----------
MISSION_STATUS = [
    "planning", "assembling", "running", "reviewing",
    "recovering", "verified", "failed",
]
TASK_STATUS = [
    "pending", "ready", "running", "waiting", "completed",
    "failed", "blocked", "needs_revision", "verified",
]
AGENT_STATUS = ["idle", "working", "waiting", "reviewing", "revising", "done"]


# ---------- Request models ----------
class MissionCreate(BaseModel):
    goal: str


class LocalMissionCreate(BaseModel):
    session_id: str
    goal: str = "Organize and prepare this project."


class Project(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str = "default-user"
    name: str
    kind: str = "demo"  # demo | local
    workspace: Optional[str] = None
    session_id: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


# ---------- Document models ----------
class Mission(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str = "default-user"
    goal: str
    title: str = ""
    summary: str = ""
    status: str = "planning"
    type: str = "standard"  # standard | local
    mode: str = "demo"  # demo (simulated) | local (real runner)
    project_id: Optional[str] = None
    workspace_id: Optional[str] = None
    session_id: Optional[str] = None
    workspace: Optional[str] = None
    credits_exhausted: bool = False
    required_capabilities: List[str] = Field(default_factory=list)
    credits_used: int = 0
    provider: str = "mock"  # "openai" or "mock"
    final_artifact_id: Optional[str] = None
    error: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class Agent(BaseModel):
    id: str = Field(default_factory=new_id)
    mission_id: str
    name: str
    role: str
    responsibility: str = ""
    capabilities: List[str] = Field(default_factory=list)
    status: str = "idle"
    current_task_id: Optional[str] = None
    permissions: List[str] = Field(default_factory=lambda: ["reason", "read_demo_data", "generate_text", "generate_json"])
    retry_count: int = 0
    is_manager: bool = False
    is_reviewer: bool = False
    created_at: str = Field(default_factory=now_iso)


class Task(BaseModel):
    id: str = Field(default_factory=new_id)
    mission_id: str
    key: str
    title: str
    description: str = ""
    owner_agent_id: Optional[str] = None
    owner_role: str = ""
    dependencies: List[str] = Field(default_factory=list)  # task ids
    status: str = "pending"
    input: Dict[str, Any] = Field(default_factory=dict)
    output: Optional[Dict[str, Any]] = None
    summary: str = ""
    retry_count: int = 0
    error: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class MissionEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    mission_id: str
    project_id: Optional[str] = None
    workspace_id: Optional[str] = None
    seq: int = 0
    type: str
    level: str = "info"  # info | success | warning | error
    actor: str = "HIVE"
    message: str
    task_id: Optional[str] = None
    # canonical worker-event fields (one source of truth for feed + drill-down + timeline)
    worker_id: Optional[str] = None
    worker_name: Optional[str] = None
    worker_role: Optional[str] = None
    action: Optional[str] = None
    tool: Optional[str] = None
    target: Optional[str] = None
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    files_affected: List[str] = Field(default_factory=list)
    handoff_to: Optional[str] = None
    error: Optional[str] = None
    status: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class Artifact(BaseModel):
    id: str = Field(default_factory=new_id)
    mission_id: str
    title: str
    content: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)


class Review(BaseModel):
    id: str = Field(default_factory=new_id)
    mission_id: str
    task_id: Optional[str] = None
    verdict: str  # pass | issue
    issue: str = ""
    responsible_task_id: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
