import { useEffect, useState } from "react";
import { getWorkforce } from "@/lib/api";
import { AGENT_STATUS_META } from "@/lib/status";
import { ShieldCheck, User, Users } from "lucide-react";

export default function WorkforcePage() {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    getWorkforce().then((d) => setAgents(d.agents || [])).finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-5xl mx-auto px-6 py-12">
      <h1 className="font-display font-extrabold text-3xl text-white mb-1">Workforce</h1>
      <p className="text-zinc-500 text-sm mb-8">
        HIVE assembles a fresh, temporary workforce for each mission — the specialists are chosen dynamically.
      </p>

      {loading ? (
        <div className="text-zinc-600 font-mono text-sm">Loading…</div>
      ) : agents.length === 0 ? (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-10 text-center">
          <Users className="w-8 h-8 text-zinc-700 mx-auto mb-3" />
          <p className="text-zinc-500 text-sm">No agents assembled yet. Start a mission to build a workforce.</p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="workforce-grid">
          {agents.map((a) => {
            const meta = AGENT_STATUS_META[a.status] || AGENT_STATUS_META.idle;
            const Icon = a.is_reviewer ? ShieldCheck : User;
            return (
              <div key={a.id} className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <div className={`w-8 h-8 rounded-md flex items-center justify-center ${a.is_reviewer ? "bg-violet-500/15" : "bg-zinc-800"}`}>
                    <Icon className={`w-4 h-4 ${a.is_reviewer ? "text-violet-300" : "text-zinc-300"}`} />
                  </div>
                  <div className="min-w-0">
                    <div className="text-white text-sm font-medium truncate">{a.name}</div>
                    <div className="text-[11px] text-zinc-500 font-mono truncate">{a.role}</div>
                  </div>
                </div>
                <p className="text-xs text-zinc-400 leading-snug mb-3 line-clamp-2">{a.responsibility}</p>
                <div className="flex items-center justify-between">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono ${meta.cls}`}>{meta.label}</span>
                  <span className="text-[10px] text-zinc-600 font-mono truncate max-w-[55%]">{a.mission_title}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
