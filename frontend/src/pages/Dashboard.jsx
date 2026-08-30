import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ArrowRight, Loader2, Sparkles, Users, GitBranch, HardDrive, FlaskConical, FolderCheck, RefreshCw } from "lucide-react";
import { createMission, createLocalMission, getExamples, getCredits, runnerActive } from "@/lib/api";
import { toast } from "sonner";
import CreditExhaustedModal from "@/components/mission/CreditExhaustedModal";

export default function Dashboard() {
  const [goal, setGoal] = useState("");
  const [examples, setExamples] = useState([]);
  const [demo, setDemo] = useState("");
  const [loading, setLoading] = useState(false);
  const [credits, setCredits] = useState(null);
  const [showCreditModal, setShowCreditModal] = useState(false);
  const [mode, setMode] = useState("demo"); // "demo" | "local"
  const [active, setActive] = useState(null); // runner status
  const navigate = useNavigate();

  const refreshActive = () => runnerActive().then(setActive).catch(() => {});

  useEffect(() => {
    getExamples().then((d) => {
      setExamples(d.examples || []);
      setDemo(d.demo || "");
    }).catch(() => {});
    getCredits().then((u) => setCredits(u?.credits)).catch(() => {});
    refreshActive();
    const id = setInterval(refreshActive, 5000);
    return () => clearInterval(id);
  }, []);

  const launch = async (text) => {
    const g = (text ?? goal).trim();
    if (g.length < 5) {
      toast.error("Describe what you want your workforce to accomplish.");
      return;
    }
    setLoading(true);
    try {
      let res;
      if (mode === "local") {
        if (!active?.approved || !active?.session_id) {
          toast.error("Connect and approve a local workspace first.");
          setLoading(false);
          navigate("/connect");
          return;
        }
        res = await createLocalMission({ session_id: active.session_id, goal: g });
      } else {
        res = await createMission(g);
      }
      window.dispatchEvent(new Event("hive-credits-refresh"));
      navigate(`/mission/${res.id}`);
    } catch (e) {
      if (e?.response?.status === 402) {
        toast.error("You're out of credits. Upgrade to keep running missions.");
        navigate("/subscription");
      } else {
        toast.error(e?.response?.data?.detail || "Could not start mission.");
      }
      setLoading(false);
    }
  };

  return (
    <div className="relative overflow-hidden">
      {/* background texture */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            "url('https://images.unsplash.com/photo-1639322537228-f710d846310a?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NDh8MHwxfHNlYXJjaHwzfHxhYnN0cmFjdCUyMGRhcmslMjBkYXRhJTIwdGVjaG5vbG9neXxlbnwwfHx8fDE3ODgwMjc3ODR8MA&ixlib=rb-4.1.0&q=85')",
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      />
      <div className="relative max-w-4xl mx-auto px-6 pt-24 pb-32">
        <div className="flex items-center gap-2 mb-6">
          <span className="inline-flex items-center gap-1.5 text-xs font-mono uppercase tracking-widest text-sky-400 border border-sky-500/20 bg-sky-500/5 rounded-full px-3 py-1">
            <Sparkles className="w-3 h-3" /> AI Workforce Orchestration
          </span>
        </div>

        <h1 className="font-display font-extrabold tracking-tight text-4xl sm:text-5xl lg:text-6xl leading-[1.05] text-white">
          Tell HIVE what you<br />
          <span className="text-sky-400">need done.</span>
        </h1>
        <p className="mt-5 text-zinc-400 text-base sm:text-lg max-w-2xl">
          Give HIVE a goal. It assembles the right specialist workforce, splits the work, collaborates,
          catches its own mistakes, and delivers a verified result.
        </p>

        <div className="mt-10 rounded-2xl border border-zinc-800 bg-zinc-900/60 backdrop-blur-md p-4 focus-within:border-sky-500/40 transition-colors">
          <label className="block text-xs font-mono uppercase tracking-widest text-zinc-500 mb-2 px-1">
            What do you want your workforce to accomplish?
          </label>
          <textarea
            data-testid="mission-input"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) launch();
            }}
            rows={3}
            placeholder="e.g. Analyze why our SaaS churn increased and recommend actions…"
            className="w-full bg-transparent resize-none outline-none text-white text-xl sm:text-2xl font-display placeholder:text-zinc-600 px-1"
          />
          <div className="flex items-center justify-between mt-3">
            <span className="text-xs text-zinc-600 font-mono hidden sm:block">⌘ + Enter</span>
            <button
              data-testid="hive-it-btn"
              onClick={() => launch()}
              disabled={loading}
              className="inline-flex items-center gap-2 bg-sky-400 text-zinc-950 font-semibold rounded-full px-6 py-3 hover:-translate-y-0.5 active:translate-y-0 transition-transform disabled:opacity-60 disabled:translate-y-0"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
              HIVE IT
            </button>
          </div>
        </div>

        {/* Execution mode selector */}
        <div className="mt-6" data-testid="execution-mode">
          <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-2">Execution mode</div>
          <div className="grid sm:grid-cols-2 gap-3">
            <button
              data-testid="mode-demo"
              onClick={() => setMode("demo")}
              className={`text-left rounded-xl border p-4 transition-colors ${
                mode === "demo" ? "border-sky-500/50 bg-sky-500/10" : "border-zinc-800 bg-zinc-900/40 hover:border-zinc-700"
              }`}
            >
              <div className="flex items-center gap-2">
                <FlaskConical className={`w-4 h-4 ${mode === "demo" ? "text-sky-400" : "text-zinc-400"}`} />
                <span className="text-sm font-semibold text-white">Demo run</span>
                {mode === "demo" && <span className="ml-auto text-[10px] font-mono text-sky-400">SELECTED</span>}
              </div>
              <div className="text-xs text-zinc-400 mt-1">Try HIVE with a simulated workspace. Nothing on your computer is touched.</div>
            </button>
            <button
              data-testid="mode-local"
              onClick={() => { setMode("local"); refreshActive(); }}
              className={`text-left rounded-xl border p-4 transition-colors ${
                mode === "local" ? "border-emerald-500/50 bg-emerald-500/10" : "border-zinc-800 bg-zinc-900/40 hover:border-zinc-700"
              }`}
            >
              <div className="flex items-center gap-2">
                <HardDrive className={`w-4 h-4 ${mode === "local" ? "text-emerald-400" : "text-zinc-400"}`} />
                <span className="text-sm font-semibold text-white">Local workspace</span>
                {mode === "local" && <span className="ml-auto text-[10px] font-mono text-emerald-400">SELECTED</span>}
              </div>
              <div className="text-xs text-zinc-400 mt-1">Give HIVE access to your selected local folder and let it create, read, and modify real files.</div>
            </button>
          </div>

          {mode === "local" && (
            <div className="mt-3 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4" data-testid="local-workspace-status">
              {active?.connected ? (
                <div className="flex items-center gap-3">
                  <FolderCheck className="w-5 h-5 text-emerald-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-white flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-emerald-400" /> {active.approved ? "Connected" : "Connected — approval needed"}
                    </div>
                    <div className="text-xs text-zinc-400 font-mono truncate" data-testid="active-workspace-path">{active.workspace}</div>
                  </div>
                  <button onClick={refreshActive} title="Refresh" className="text-zinc-500 hover:text-white p-1"><RefreshCw className="w-4 h-4" /></button>
                  <Link to="/connect" data-testid="change-workspace-btn" className="text-xs text-emerald-400 hover:text-emerald-300 border border-emerald-500/40 rounded-full px-3 py-1.5 whitespace-nowrap">
                    {active.approved ? "Change workspace" : "Approve"}
                  </Link>
                </div>
              ) : (
                <div className="flex items-center gap-3">
                  <span className="w-2 h-2 rounded-full bg-zinc-600 shrink-0" />
                  <div className="flex-1 text-sm text-zinc-300">Not connected</div>
                  <Link to="/connect" data-testid="connect-workspace-btn" className="text-xs text-emerald-400 hover:text-emerald-300 border border-emerald-500/40 rounded-full px-3 py-1.5">
                    Connect workspace
                  </Link>
                </div>
              )}
            </div>
          )}

          {mode === "demo" && demo && (
            <button
              data-testid="demo-mission-btn"
              onClick={() => launch(demo)}
              className="mt-3 text-sm text-sky-400 hover:text-sky-300 transition-colors font-mono"
            >
              ▸ Run the reliable demo mission (SaaS churn recovery)
            </button>
          )}
        </div>

        <div className="mt-14">
          <div className="flex items-center gap-2 text-zinc-500 text-xs font-mono uppercase tracking-widest mb-4">
            <span>Example missions</span>
            <div className="h-px flex-1 bg-zinc-800" />
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            {examples.map((ex, i) => (
              <button
                key={i}
                data-testid={`example-mission-${i}`}
                onClick={() => setGoal(ex)}
                className="group text-left rounded-xl border border-zinc-800 bg-zinc-900/40 hover:bg-zinc-900 hover:border-zinc-700 p-4 transition-colors"
              >
                <div className="flex items-start justify-between gap-3">
                  <span className="text-sm text-zinc-300 group-hover:text-white transition-colors">{ex}</span>
                  <ArrowRight className="w-4 h-4 text-zinc-600 group-hover:text-sky-400 shrink-0 mt-0.5 transition-colors" />
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="mt-16 grid sm:grid-cols-3 gap-4">
          {[
            { icon: Users, title: "Dynamic workforce", body: "HIVE picks the specialists this mission actually needs." },
            { icon: GitBranch, title: "Real collaboration", body: "Agents pass outputs, run in parallel, and share mission state." },
            { icon: Sparkles, title: "Self-correcting", body: "A reviewer catches issues and routes them to the responsible agent." },
          ].map((f, i) => (
            <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
              <f.icon className="w-5 h-5 text-sky-400 mb-3" />
              <div className="font-display font-semibold text-white text-sm">{f.title}</div>
              <div className="text-xs text-zinc-500 mt-1 leading-relaxed">{f.body}</div>
            </div>
          ))}
        </div>
      </div>
      <CreditExhaustedModal open={showCreditModal} onOpenChange={setShowCreditModal} onRenewed={(c) => setCredits(c)} />
    </div>
  );
}
