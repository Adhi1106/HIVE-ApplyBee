import { Crown, ShieldCheck, User, Wrench, Loader2 } from "lucide-react";
import { AGENT_STATUS_META } from "@/lib/status";

function AgentCard({ agent, task, onClick }) {
  const meta = AGENT_STATUS_META[agent.status] || AGENT_STATUS_META.idle;
  const Icon = agent.is_manager ? Crown : agent.is_reviewer ? ShieldCheck : User;
  return (
    <button
      type="button"
      data-testid="workforce-agent"
      onClick={() => onClick?.(agent)}
      className={`w-full text-left rounded-lg border bg-zinc-900/50 p-3 transition-colors ${
        agent.status === "revising" ? "border-amber-500/40" : "border-zinc-800 hover:border-sky-500/40"
      }`}
    >
      <div className="flex items-center gap-2">
        <div className={`w-8 h-8 rounded-md flex items-center justify-center shrink-0 ${
          agent.is_manager ? "bg-sky-500/15" : agent.is_reviewer ? "bg-violet-500/15" : "bg-zinc-800"
        }`}>
          <Icon className={`w-4 h-4 ${
            agent.is_manager ? "text-sky-400" : agent.is_reviewer ? "text-violet-300" : "text-zinc-300"
          }`} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm text-white font-medium truncate">{agent.name}</div>
          <div className="text-[11px] text-zinc-500 font-mono truncate">{agent.role}</div>
        </div>
        <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono flex items-center gap-1 ${meta.cls}`}>
          {(agent.status === "working" || agent.status === "revising") && <Loader2 className="w-2.5 h-2.5 animate-spin" />}
          {meta.label}
        </span>
      </div>
      {task && (
        <div className="mt-2 pt-2 border-t border-zinc-800 flex items-start gap-1.5">
          <Wrench className="w-3 h-3 text-zinc-600 mt-0.5 shrink-0" />
          <span className="text-[11px] text-zinc-400 leading-snug">{task.title}</span>
        </div>
      )}
      <div className="mt-2 text-[10px] text-sky-400/70 font-mono">click for details →</div>
    </button>
  );
}

export default function WorkforcePanel({ agents, tasks, onSelectAgent }) {
  const taskById = Object.fromEntries((tasks || []).map((t) => [t.id, t]));
  const ordered = [...(agents || [])].sort((a, b) => (b.is_manager ? 1 : 0) - (a.is_manager ? 1 : 0));
  return (
    <div className="h-full flex flex-col" data-testid="workforce-panel">
      <div className="px-4 py-2.5 border-b border-zinc-800 shrink-0 flex items-center gap-2">
        <span className="font-display font-semibold text-sm text-white">Workforce</span>
        <span className="text-xs text-zinc-600 font-mono ml-auto">{agents?.length || 0} agents</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {(agents || []).length === 0 && (
          <div className="text-xs text-zinc-600 font-mono px-1 py-4 text-center">Assembling workforce…</div>
        )}
        {ordered.map((a) => (
          <AgentCard key={a.id} agent={a} task={a.current_task_id ? taskById[a.current_task_id] : null} onClick={onSelectAgent} />
        ))}
      </div>
    </div>
  );
}
