import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listMissions } from "@/lib/api";
import { MISSION_STATUS_META } from "@/lib/status";
import { ArrowRight, Inbox } from "lucide-react";

export default function History() {
  const [missions, setMissions] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    listMissions().then((d) => setMissions(d.missions || [])).finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-4xl mx-auto px-6 py-12">
      <h1 className="font-display font-extrabold text-3xl text-white mb-1">Mission History</h1>
      <p className="text-zinc-500 text-sm mb-8">Every mission keeps its full event history and verified deliverable.</p>

      {loading ? (
        <div className="text-zinc-600 font-mono text-sm">Loading…</div>
      ) : missions.length === 0 ? (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-10 text-center">
          <Inbox className="w-8 h-8 text-zinc-700 mx-auto mb-3" />
          <p className="text-zinc-500 text-sm">No missions yet.</p>
          <Link to="/" className="text-sky-400 text-sm hover:text-sky-300 mt-2 inline-block">Start your first mission →</Link>
        </div>
      ) : (
        <div className="space-y-2" data-testid="history-list">
          {missions.map((m) => {
            const meta = MISSION_STATUS_META[m.status] || MISSION_STATUS_META.planning;
            return (
              <Link
                key={m.id}
                to={`/mission/${m.id}`}
                data-testid="history-item"
                className="group flex items-center gap-4 rounded-xl border border-zinc-800 bg-zinc-900/40 hover:border-zinc-700 hover:bg-zinc-900 p-4 transition-colors"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-white font-medium text-sm truncate">{m.title || m.goal}</div>
                  <div className="text-xs text-zinc-500 font-mono truncate mt-0.5">{m.goal}</div>
                </div>
                <span className="text-[11px] text-zinc-600 font-mono hidden sm:block">
                  {m.provider === "openai" ? "live AI" : "mock"}
                </span>
                <span className={`text-xs px-3 py-1 rounded-full font-mono ${meta.cls}`}>{meta.label}</span>
                <ArrowRight className="w-4 h-4 text-zinc-600 group-hover:text-sky-400 transition-colors" />
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
