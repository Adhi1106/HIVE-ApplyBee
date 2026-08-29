import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  HardDrive, Loader2, ShieldCheck, CheckCircle2, Terminal, FolderTree, Play, Sparkles, Copy,
} from "lucide-react";
import { toast } from "sonner";
import {
  runnerPair, runnerSession, runnerApprove, runnerTree, runnerSeedDemo,
  createLocalMission, runnerWsUrl,
} from "@/lib/api";

export default function ConnectWorkspace() {
  const [session, setSession] = useState(null);
  const [sid, setSid] = useState(null);
  const [tree, setTree] = useState([]);
  const [busy, setBusy] = useState(false);
  const [customGoal, setCustomGoal] = useState("");
  const timer = useRef(null);
  const navigate = useNavigate();

  const startPolling = (id) => {
    setSid(id);
    const poll = async () => {
      try {
        const s = await runnerSession(id);
        setSession(s);
        if (s.approved) {
          try { setTree((await runnerTree(id)).entries || []); } catch (e) {}
        }
      } catch (e) {}
      timer.current = setTimeout(poll, 1500);
    };
    clearTimeout(timer.current);
    poll();
  };

  useEffect(() => () => clearTimeout(timer.current), []);

  const useDemo = () => startPolling("demo");

  const pairOwn = async () => {
    const s = await runnerPair();
    setSession(s);
    startPolling(s.session_id);
  };

  const approve = async () => {
    try {
      const s = await runnerApprove(sid);
      setSession(s);
      toast.success("Workspace connected & approved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not approve");
    }
  };

  const seed = async () => {
    setBusy(true);
    try {
      const r = await runnerSeedDemo(sid);
      setTree(r.entries || []);
      toast.success("Loaded a deliberately messy demo project");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Seed failed");
    } finally { setBusy(false); }
  };

  const runMission = async (goal) => {
    setBusy(true);
    try {
      const res = await createLocalMission(sid, goal);
      navigate(`/mission/${res.id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not start mission");
      setBusy(false);
    }
  };

  const cmd = `python runner.py \\
  --server ${runnerWsUrl()} \\
  --code ${session?.code || "YOUR-CODE"} \\
  --workspace /absolute/path/to/your/project`;

  const step = session?.approved ? 3 : session?.connected ? 2 : 1;

  return (
    <div className="max-w-4xl mx-auto px-6 py-12">
      <div className="flex items-center gap-2 mb-1">
        <HardDrive className="w-5 h-5 text-sky-400" />
        <h1 className="font-display font-extrabold text-3xl text-white">Connect Workspace</h1>
      </div>
      <p className="text-zinc-500 text-sm mb-8">
        HIVE performs real work through the <span className="text-zinc-300">Local Runner</span> on your computer — restricted to one folder you approve. The web app never touches your filesystem directly.
      </p>

      {/* stepper */}
      <div className="flex items-center gap-2 mb-8 text-xs font-mono">
        {["Select workspace", "Review permissions", "Connected"].map((label, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className={`px-3 py-1 rounded-full border ${step > i ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10" : step === i + 1 ? "border-sky-500/40 text-sky-400 bg-sky-500/10" : "border-zinc-800 text-zinc-600"}`}>
              {step > i + 1 ? "✓ " : ""}{label}
            </span>
            {i < 2 && <span className="text-zinc-700">→</span>}
          </div>
        ))}
      </div>

      {!session && (
        <div className="grid sm:grid-cols-2 gap-4" data-testid="connect-options">
          <button onClick={useDemo} data-testid="use-demo-runner-btn" className="text-left rounded-xl border border-sky-500/30 bg-sky-500/5 hover:bg-sky-500/10 p-5 transition-colors">
            <Sparkles className="w-6 h-6 text-sky-400 mb-3" />
            <div className="font-display font-semibold text-white">Use hosted demo runner</div>
            <div className="text-xs text-zinc-400 mt-1 leading-relaxed">A runner is already running in a sandboxed demo workspace. Best for a quick end-to-end demo.</div>
          </button>
          <button onClick={pairOwn} data-testid="pair-own-btn" className="text-left rounded-xl border border-zinc-800 bg-zinc-900/40 hover:border-zinc-700 p-5 transition-colors">
            <Terminal className="w-6 h-6 text-zinc-300 mb-3" />
            <div className="font-display font-semibold text-white">Pair my own computer</div>
            <div className="text-xs text-zinc-400 mt-1 leading-relaxed">Get a pairing code and run the HIVE Runner locally against your real project folder.</div>
          </button>
        </div>
      )}

      {session && !session.approved && (
        <div className="space-y-4" data-testid="pairing-panel">
          {session.code !== "HIVE-DEMO" && (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-zinc-300 font-medium">Run the HIVE Runner on your computer</span>
                <button onClick={() => { navigator.clipboard.writeText(cmd); toast.success("Command copied"); }} className="text-xs text-sky-400 flex items-center gap-1"><Copy className="w-3 h-3" /> Copy</button>
              </div>
              <pre className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-[12px] text-zinc-300 font-mono overflow-x-auto whitespace-pre-wrap">{cmd}</pre>
              <div className="text-xs text-zinc-500 mt-2">Pairing code: <span className="text-sky-400 font-mono">{session.code}</span></div>
            </div>
          )}

          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 flex items-center gap-3" data-testid="runner-status">
            {session.connected ? <CheckCircle2 className="w-5 h-5 text-emerald-400" /> : <Loader2 className="w-5 h-5 text-sky-400 animate-spin" />}
            <div className="flex-1">
              <div className="text-sm text-white">{session.connected ? "Runner connected" : "Waiting for runner to connect…"}</div>
              {session.workspace && <div className="text-xs text-zinc-500 font-mono">{session.workspace}</div>}
            </div>
          </div>

          {session.connected && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-5" data-testid="permissions-panel">
              <div className="flex items-center gap-2 mb-3">
                <ShieldCheck className="w-5 h-5 text-amber-400" />
                <span className="font-display font-semibold text-white">Requested permissions</span>
              </div>
              <ul className="space-y-1.5 mb-4">
                {(session.permissions || []).map((p, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-zinc-300">
                    <CheckCircle2 className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" /> {p}
                  </li>
                ))}
              </ul>
              <button onClick={approve} data-testid="approve-workspace-btn" className="inline-flex items-center gap-2 bg-sky-400 text-zinc-950 font-semibold rounded-full px-5 py-2 hover:-translate-y-0.5 transition-transform">
                <ShieldCheck className="w-4 h-4" /> Approve & Connect
              </button>
            </div>
          )}
        </div>
      )}

      {session?.approved && (
        <div className="space-y-4" data-testid="connected-panel">
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-5 flex items-center gap-3">
            <CheckCircle2 className="w-6 h-6 text-emerald-400" />
            <div className="flex-1">
              <div className="font-display font-semibold text-white">CONNECTED</div>
              <div className="text-xs text-zinc-400 font-mono">{session.workspace}</div>
            </div>
            <div className="flex gap-2">
              <button onClick={seed} disabled={busy} data-testid="seed-demo-btn" className="inline-flex items-center gap-2 border border-zinc-700 text-zinc-200 rounded-full px-4 py-2 text-sm hover:border-zinc-500 transition-colors disabled:opacity-50">
                <FolderTree className="w-4 h-4" /> Load demo messy project
              </button>
              <button onClick={() => runMission()} disabled={busy || tree.length === 0} data-testid="run-local-mission-btn" className="inline-flex items-center gap-2 bg-emerald-500 text-zinc-950 font-semibold rounded-full px-4 py-2 text-sm hover:-translate-y-0.5 transition-transform disabled:opacity-50 disabled:translate-y-0">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />} Organize & prepare this project
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4" data-testid="custom-local-mission">
            <div className="text-sm text-white font-medium mb-1">Or give this workspace any mission</div>
            <div className="text-xs text-zinc-500 mb-3">HIVE assembles a workforce and performs real file operations in this folder.</div>
            <div className="flex gap-2">
              <input
                data-testid="custom-goal-input"
                value={customGoal}
                onChange={(e) => setCustomGoal(e.target.value)}
                placeholder="e.g. Read README.txt and create summary.txt containing a short summary."
                className="flex-1 bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-sky-500/40"
              />
              <button
                data-testid="run-custom-mission-btn"
                onClick={() => customGoal.trim().length >= 5 ? runMission(customGoal.trim()) : toast.error("Describe the mission")}
                disabled={busy || tree.length === 0}
                className="inline-flex items-center gap-2 bg-sky-400 text-zinc-950 font-semibold rounded-full px-4 py-2 text-sm hover:-translate-y-0.5 transition-transform disabled:opacity-50 disabled:translate-y-0"
              >
                <Play className="w-4 h-4" /> Run
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-zinc-800 bg-zinc-950/60">
            <div className="px-4 py-2 border-b border-zinc-800 text-xs font-mono uppercase tracking-widest text-zinc-500">
              Current workspace ({tree.length} items)
            </div>
            <div className="p-4 font-mono text-[12px] grid sm:grid-cols-2 gap-y-0.5 gap-x-6" data-testid="workspace-tree">
              {tree.length === 0 && <span className="text-zinc-600">Empty — load the demo messy project to begin.</span>}
              {tree.map((e, i) => (
                <div key={i} className={e.type === "dir" ? "text-sky-300" : "text-zinc-400"}>
                  {e.type === "dir" ? "▸ " : "· "}{e.path}{e.type === "dir" ? "/" : ""}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
