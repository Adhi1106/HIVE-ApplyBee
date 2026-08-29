// Shared status metadata (colors + labels) for HIVE UI.

export const TASK_STATUS_META = {
  pending: { label: "Pending", dot: "#52525b", text: "text-zinc-400", border: "border-l-zinc-600" },
  ready: { label: "Ready", dot: "#a1a1aa", text: "text-zinc-300", border: "border-l-zinc-500" },
  running: { label: "Running", dot: "#38bdf8", text: "text-sky-400", border: "border-l-sky-500" },
  waiting: { label: "Waiting", dot: "#a1a1aa", text: "text-zinc-300", border: "border-l-zinc-500" },
  completed: { label: "Completed", dot: "#38bdf8", text: "text-sky-300", border: "border-l-sky-500" },
  needs_revision: { label: "Needs Revision", dot: "#f59e0b", text: "text-amber-400", border: "border-l-amber-500" },
  blocked: { label: "Blocked", dot: "#ef4444", text: "text-red-400", border: "border-l-red-500" },
  failed: { label: "Failed", dot: "#ef4444", text: "text-red-400", border: "border-l-red-500" },
  verified: { label: "Verified", dot: "#10b981", text: "text-emerald-400", border: "border-l-emerald-500" },
};

export const AGENT_STATUS_META = {
  idle: { label: "Idle", cls: "bg-zinc-800 text-zinc-400" },
  working: { label: "Working", cls: "bg-sky-500/15 text-sky-400" },
  waiting: { label: "Waiting", cls: "bg-zinc-800 text-zinc-300" },
  reviewing: { label: "Reviewing", cls: "bg-violet-500/15 text-violet-300" },
  revising: { label: "Revising", cls: "bg-amber-500/15 text-amber-400" },
  done: { label: "Done", cls: "bg-emerald-500/15 text-emerald-400" },
};

export const MISSION_STATUS_META = {
  planning: { label: "Planning", cls: "bg-sky-500/15 text-sky-400" },
  assembling: { label: "Assembling", cls: "bg-sky-500/15 text-sky-400" },
  running: { label: "Running", cls: "bg-sky-500/15 text-sky-400" },
  reviewing: { label: "Reviewing", cls: "bg-violet-500/15 text-violet-300" },
  recovering: { label: "Recovering", cls: "bg-amber-500/15 text-amber-400" },
  verified: { label: "Verified", cls: "bg-emerald-500/15 text-emerald-400" },
  failed: { label: "Failed", cls: "bg-red-500/15 text-red-400" },
};

export const LEVEL_DOT = {
  info: "#38bdf8",
  success: "#10b981",
  warning: "#f59e0b",
  error: "#ef4444",
};
