import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ArrowRight, Loader2, Sparkles, Users, GitBranch, HardDrive } from "lucide-react";
import { createMission, getExamples, getCredits } from "@/lib/api";
import { toast } from "sonner";
import CreditExhaustedModal from "@/components/mission/CreditExhaustedModal";

export default function Dashboard() {
  const [goal, setGoal] = useState("");
  const [examples, setExamples] = useState([]);
  const [demo, setDemo] = useState("");
  const [loading, setLoading] = useState(false);
  const [credits, setCredits] = useState(null);
  const [showCreditModal, setShowCreditModal] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    getExamples().then((d) => {
      setExamples(d.examples || []);
      setDemo(d.demo || "");
    }).catch(() => {});
    getCredits().then((u) => setCredits(u?.credits)).catch(() => {});
  }, []);

  const launch = async (text) => {
    const g = (text ?? goal).trim();
    if (g.length < 5) {
      toast.error("Describe what you want your workforce to accomplish.");
      return;
    }
    if (credits !== null && credits <= 0) {
      setShowCreditModal(true);
      return;
    }
    setLoading(true);
    try {
      const res = await createMission(g);
      navigate(`/mission/${res.id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not start mission.");
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

        {demo && (
          <button
            data-testid="demo-mission-btn"
            onClick={() => launch(demo)}
            className="mt-4 text-sm text-sky-400 hover:text-sky-300 transition-colors font-mono"
          >
            ▸ Run the reliable demo mission (SaaS churn recovery)
          </button>
        )}

        <Link
          to="/connect"
          data-testid="connect-workspace-cta"
          className="mt-6 group flex items-center gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/5 hover:bg-emerald-500/10 p-4 transition-colors"
        >
          <HardDrive className="w-5 h-5 text-emerald-400 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-sm text-white font-medium">Run HIVE on your own files (Local Runner)</div>
            <div className="text-xs text-zinc-400">Connect a workspace folder and let the workforce do real file operations — try "Organize and prepare this project".</div>
          </div>
          <ArrowRight className="w-4 h-4 text-emerald-400 group-hover:translate-x-0.5 transition-transform shrink-0" />
        </Link>

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
