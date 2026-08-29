import { Handle, Position } from "@xyflow/react";
import {
  Crown, CheckCircle2, ShieldCheck, Loader2, AlertTriangle, Wrench, Circle, Dot,
} from "lucide-react";
import { TASK_STATUS_META } from "@/lib/status";

const StatusIcon = ({ status }) => {
  if (status === "running") return <Loader2 className="w-3.5 h-3.5 animate-spin text-sky-400" />;
  if (status === "verified") return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />;
  if (status === "completed") return <CheckCircle2 className="w-3.5 h-3.5 text-sky-300" />;
  if (status === "needs_revision") return <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />;
  if (status === "failed") return <AlertTriangle className="w-3.5 h-3.5 text-red-400" />;
  return <Circle className="w-3 h-3 text-zinc-600" />;
};

export function HiveNode({ data }) {
  const { kind, title, subtitle, status, revising } = data;

  if (kind === "manager") {
    return (
      <div data-testid="node-manager" className="w-[220px] rounded-xl border border-sky-500/40 bg-gradient-to-b from-sky-500/10 to-zinc-900 px-4 py-3 shadow-lg shadow-sky-500/10">
        <Handle type="source" position={Position.Bottom} />
        <div className="flex items-center gap-2">
          <Crown className="w-4 h-4 text-sky-400" />
          <span className="font-display font-bold text-white text-sm">Mission Manager</span>
        </div>
        <div className="text-[11px] text-zinc-400 mt-1 font-mono">Coordinates the workforce</div>
      </div>
    );
  }

  if (kind === "review") {
    return (
      <div data-testid="node-review" className="w-[200px] rounded-xl border border-violet-500/40 bg-violet-500/5 px-4 py-3">
        <Handle type="target" position={Position.Top} />
        <Handle type="source" position={Position.Bottom} />
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-violet-300" />
          <span className="font-display font-bold text-white text-sm">Reviewer</span>
        </div>
        <div className="text-[11px] text-zinc-400 mt-1 font-mono">Verifies final output</div>
      </div>
    );
  }

  if (kind === "verified") {
    const done = status === "verified";
    return (
      <div
        data-testid="node-verified"
        className={`w-[200px] rounded-xl border px-4 py-3 ${
          done ? "border-emerald-500/60 bg-emerald-500/10 shadow-lg shadow-emerald-500/20" : "border-zinc-700 bg-zinc-900"
        }`}
      >
        <Handle type="target" position={Position.Top} />
        <div className="flex items-center gap-2">
          <CheckCircle2 className={`w-4 h-4 ${done ? "text-emerald-400" : "text-zinc-600"}`} />
          <span className={`font-display font-bold text-sm ${done ? "text-emerald-300" : "text-zinc-500"}`}>
            {done ? "VERIFIED" : "Verification"}
          </span>
        </div>
      </div>
    );
  }

  // task node
  const meta = TASK_STATUS_META[status] || TASK_STATUS_META.pending;
  return (
    <div
      data-testid={`node-task`}
      className={`w-[230px] rounded-xl border border-zinc-800 border-l-4 ${meta.border} bg-zinc-900 px-4 py-3 transition-colors ${
        status === "running" ? "hive-running" : ""
      } ${status === "needs_revision" ? "ring-1 ring-amber-500/40" : ""}`}
    >
      <Handle type="target" position={Position.Top} />
      <Handle type="source" position={Position.Bottom} />
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">{subtitle}</span>
        {revising ? <Wrench className="w-3.5 h-3.5 text-amber-400" /> : <StatusIcon status={status} />}
      </div>
      <div className="text-sm text-white font-medium mt-1 leading-snug line-clamp-2">{title}</div>
      <div className={`text-[11px] mt-2 font-mono ${meta.text} flex items-center gap-1`}>
        <Dot className="w-3 h-3" style={{ color: meta.dot }} />
        {meta.label}
      </div>
    </div>
  );
}

export const nodeTypes = { hive: HiveNode };
