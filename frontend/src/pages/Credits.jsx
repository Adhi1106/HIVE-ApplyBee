import { useEffect, useState } from "react";
import { getCredits, listMissions } from "@/lib/api";
import { Zap, TrendingDown } from "lucide-react";

export default function Credits() {
  const [user, setUser] = useState(null);
  const [missions, setMissions] = useState([]);
  useEffect(() => {
    getCredits().then(setUser).catch(() => {});
    listMissions().then((d) => setMissions(d.missions || [])).catch(() => {});
  }, []);

  const used = missions.reduce((s, m) => s + (m.credits_used || 0), 0);

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      <h1 className="font-display font-extrabold text-3xl text-white mb-1">Credits</h1>
      <p className="text-zinc-500 text-sm mb-8">A placeholder credit meter for this MVP. Billing arrives later.</p>

      <div className="grid sm:grid-cols-2 gap-4 mb-8">
        <div className="rounded-2xl border border-sky-500/30 bg-gradient-to-b from-sky-500/10 to-zinc-900 p-6">
          <Zap className="w-6 h-6 text-sky-400 mb-4" />
          <div className="text-4xl font-display font-extrabold text-white" data-testid="credits-remaining">
            {user?.credits ?? "—"}
          </div>
          <div className="text-xs text-zinc-500 font-mono mt-1">credits remaining</div>
        </div>
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6">
          <TrendingDown className="w-6 h-6 text-zinc-400 mb-4" />
          <div className="text-4xl font-display font-extrabold text-white">{used}</div>
          <div className="text-xs text-zinc-500 font-mono mt-1">credits used across {missions.length} missions</div>
        </div>
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 divide-y divide-zinc-800">
        <div className="px-4 py-3 text-xs font-mono uppercase tracking-widest text-zinc-500">Estimated usage per mission</div>
        {missions.slice(0, 8).map((m) => (
          <div key={m.id} className="px-4 py-3 flex items-center justify-between gap-3">
            <span className="text-sm text-zinc-300 truncate">{m.title || m.goal}</span>
            <span className="text-sm font-mono text-sky-400 shrink-0">{m.credits_used || 0}</span>
          </div>
        ))}
        {missions.length === 0 && (
          <div className="px-4 py-6 text-center text-sm text-zinc-600">No usage yet.</div>
        )}
      </div>
    </div>
  );
}
