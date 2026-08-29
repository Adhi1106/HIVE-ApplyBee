import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Hexagon, FileCheck2, AlertTriangle, Loader2, GitBranch, FolderTree } from "lucide-react";
import { getMission } from "@/lib/api";
import { MISSION_STATUS_META } from "@/lib/status";
import MissionGraph from "@/components/mission/MissionGraph";
import ActivityFeed from "@/components/mission/ActivityFeed";
import WorkforcePanel from "@/components/mission/WorkforcePanel";
import WorkspacePanel from "@/components/mission/WorkspacePanel";
import ArtifactView from "@/components/mission/ArtifactView";

const TERMINAL = ["verified", "failed"];

export default function MissionRoom() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [showArtifact, setShowArtifact] = useState(false);
  const [view, setView] = useState("graph");
  const artifactShown = useRef(false);
  const prevStatus = useRef(null);
  const timer = useRef(null);

  useEffect(() => {
    let mounted = true;
    const poll = async () => {
      try {
        const d = await getMission(id);
        if (!mounted) return;
        setData(d);
        // only auto-open on a live transition INTO verified (not when opening an already-finished mission)
        if (
          d.mission.status === "verified" &&
          prevStatus.current &&
          prevStatus.current !== "verified" &&
          !artifactShown.current
        ) {
          artifactShown.current = true;
          setShowArtifact(true);
          if (d.mission.type === "local") setView("workspace");
        }
        prevStatus.current = d.mission.status;
        if (!TERMINAL.includes(d.mission.status)) {
          timer.current = setTimeout(poll, 1200);
        }
      } catch (e) {
        timer.current = setTimeout(poll, 2000);
      }
    };
    poll();
    return () => {
      mounted = false;
      clearTimeout(timer.current);
    };
  }, [id]);

  const mission = data?.mission;
  const tasks = data?.tasks || [];
  const agents = data?.agents || [];
  const events = data?.events || [];

  const total = tasks.length || 1;
  const done = tasks.filter((t) => t.status === "verified" || t.status === "completed").length;
  const progress = mission?.status === "verified" ? 100 : Math.round((done / total) * 100);
  const meta = MISSION_STATUS_META[mission?.status] || MISSION_STATUS_META.planning;
  const recovering = mission?.status === "recovering" || tasks.some((t) => t.status === "needs_revision");
  const isLocal = mission?.type === "local";

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden">
      {/* top bar */}
      <header className="h-14 shrink-0 border-b border-zinc-800 backdrop-blur-xl bg-black/60 flex items-center px-4 gap-4">
        <Link to="/history" data-testid="back-btn" className="text-zinc-400 hover:text-white transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <Link to="/" className="flex items-center gap-1.5">
          <Hexagon className="w-5 h-5 text-sky-400 fill-sky-400/10" strokeWidth={1.5} />
          <span className="font-display font-bold text-white">HIVE</span>
        </Link>
        <div className="h-5 w-px bg-zinc-800" />
        <div className="min-w-0 flex-1">
          <div className="text-sm text-white font-medium truncate" data-testid="mission-title">
            {mission?.title || "Assembling mission…"}
          </div>
          <div className="text-[11px] text-zinc-500 truncate font-mono">{mission?.goal}</div>
        </div>
        <span
          data-testid="mission-status"
          className={`text-xs px-3 py-1 rounded-full font-mono flex items-center gap-1.5 ${meta.cls}`}
        >
          {!TERMINAL.includes(mission?.status) && <Loader2 className="w-3 h-3 animate-spin" />}
          {meta.label}
        </span>
        {mission?.status === "verified" && data?.artifact && (
          <button
            data-testid="view-deliverable-btn"
            onClick={() => setShowArtifact(true)}
            className="inline-flex items-center gap-2 bg-emerald-500 text-zinc-950 font-semibold rounded-full px-4 py-1.5 text-sm hover:-translate-y-0.5 transition-transform"
          >
            <FileCheck2 className="w-4 h-4" /> View Deliverable
          </button>
        )}
      </header>

      {/* recovery banner */}
      {recovering && (
        <div data-testid="recovery-banner" className="shrink-0 bg-amber-500/10 border-b border-amber-500/30 px-4 py-2 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
          <span className="text-sm text-amber-200">
            Reviewer flagged an inconsistency — HIVE routed it to the responsible agent to fix and recheck dependencies.
          </span>
        </div>
      )}

      {/* body */}
      <div className="flex-1 flex min-h-0">
        {/* main */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="shrink-0 px-4 py-2 border-b border-zinc-800 flex items-center gap-3">
            <span className="text-xs text-zinc-500 font-mono">Progress</span>
            <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
              <div
                className={`h-full transition-all duration-500 ${mission?.status === "verified" ? "bg-emerald-500" : "bg-sky-400"}`}
                style={{ width: `${progress}%` }}
                data-testid="progress-bar"
              />
            </div>
            <span className="text-xs font-mono text-zinc-400 w-10 text-right">{progress}%</span>
            {isLocal && (
              <div className="flex items-center gap-1 ml-2 rounded-full border border-zinc-800 p-0.5">
                <button
                  data-testid="view-graph-btn"
                  onClick={() => setView("graph")}
                  className={`flex items-center gap-1 text-xs px-3 py-1 rounded-full transition-colors ${view === "graph" ? "bg-zinc-800 text-white" : "text-zinc-500 hover:text-white"}`}
                >
                  <GitBranch className="w-3.5 h-3.5" /> Graph
                </button>
                <button
                  data-testid="view-workspace-btn"
                  onClick={() => setView("workspace")}
                  className={`flex items-center gap-1 text-xs px-3 py-1 rounded-full transition-colors ${view === "workspace" ? "bg-zinc-800 text-white" : "text-zinc-500 hover:text-white"}`}
                >
                  <FolderTree className="w-3.5 h-3.5" /> Workspace
                </button>
              </div>
            )}
          </div>
          <div className="flex-1 min-h-0 bg-[#0a0a0c]">
            {isLocal && view === "workspace" ? (
              <WorkspacePanel artifact={data?.artifact} workspace={mission?.workspace} />
            ) : (
              <MissionGraph mission={mission} tasks={tasks} />
            )}
          </div>
          <div className="h-[34%] shrink-0 border-t border-zinc-800 bg-zinc-950/80">
            <ActivityFeed events={events} />
          </div>
        </div>
        {/* sidebar */}
        <aside className="w-80 shrink-0 border-l border-zinc-800 bg-zinc-950/60">
          <WorkforcePanel agents={agents} tasks={tasks} />
        </aside>
      </div>

      <ArtifactView open={showArtifact} onOpenChange={setShowArtifact} artifact={data?.artifact} />
    </div>
  );
}
