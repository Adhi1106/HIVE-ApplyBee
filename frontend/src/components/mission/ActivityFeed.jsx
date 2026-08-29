import { useEffect, useRef } from "react";
import {
  Circle, CheckCircle2, AlertTriangle, RefreshCw, Wrench, ShieldCheck,
  GitBranch, Users, PlayCircle, Send, Crown, Zap,
} from "lucide-react";
import { LEVEL_DOT } from "@/lib/status";

const ICONS = {
  MISSION_CREATED: Crown,
  WORKFORCE_ASSEMBLING: Users,
  AGENT_JOINED: Users,
  TASK_CREATED: GitBranch,
  PARALLEL_EXECUTION: Zap,
  TASK_STARTED: PlayCircle,
  TASK_COMPLETED: CheckCircle2,
  OUTPUT_UPDATED: Send,
  REVIEW_REQUESTED: ShieldCheck,
  REVISION_REQUIRED: AlertTriangle,
  ISSUE_ROUTED: RefreshCw,
  DEPENDENCY_CHANGED: GitBranch,
  DEPENDENCY_CHECKED: CheckCircle2,
  REVIEW_PASSED: ShieldCheck,
  MISSION_VERIFIED: CheckCircle2,
  MISSION_BLOCKED: AlertTriangle,
};

export default function ActivityFeed({ events }) {
  const endRef = useRef(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events?.length]);

  return (
    <div className="h-full flex flex-col" data-testid="activity-feed">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-zinc-800 shrink-0">
        <Circle className="w-2 h-2 fill-sky-400 text-sky-400 animate-pulse" />
        <span className="font-display font-semibold text-sm text-white">Live Mission Activity</span>
        <span className="text-xs text-zinc-600 font-mono ml-auto">{events?.length || 0} events</span>
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-2 font-mono text-[13px]">
        {(events || []).map((e) => {
          const Icon = ICONS[e.type] || Circle;
          return (
            <div
              key={e.id}
              data-testid="feed-event"
              className="hive-fade-in flex items-start gap-2.5 px-2 py-1.5 rounded hover:bg-zinc-900/60"
            >
              <Icon className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: LEVEL_DOT[e.level] || "#38bdf8" }} />
              <div className="min-w-0">
                <span className="text-zinc-500">{e.actor}</span>
                <span className="text-zinc-700"> · </span>
                <span
                  className={
                    e.level === "success" ? "text-emerald-300"
                      : e.level === "warning" ? "text-amber-300"
                      : e.level === "error" ? "text-red-300"
                      : "text-zinc-300"
                  }
                >
                  {e.message}
                </span>
              </div>
            </div>
          );
        })}
        <div ref={endRef} />
      </div>
    </div>
  );
}
