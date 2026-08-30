import { Outlet, NavLink, Link, useNavigate } from "react-router-dom";
import { useEffect, useState, useCallback } from "react";
import { Hexagon, Zap } from "lucide-react";
import { getCredits } from "@/lib/api";

const HiveLogo = () => (
  <Link to="/" data-testid="hive-logo" className="flex items-center gap-2 group">
    <div className="relative">
      <Hexagon className="w-7 h-7 text-sky-400 fill-sky-400/10 transition-transform group-hover:rotate-90 duration-500" strokeWidth={1.5} />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="w-1.5 h-1.5 rounded-full bg-sky-400" />
      </div>
    </div>
    <span className="font-display font-extrabold text-xl tracking-tight text-white">HIVE</span>
  </Link>
);

const navItems = [
  { to: "/", label: "Missions", end: true },
  { to: "/connect", label: "Runner" },
  { to: "/workforce", label: "Workforce" },
  { to: "/history", label: "Mission History" },
  { to: "/subscription", label: "Subscription" },
];

export default function Layout() {
  const [credits, setCredits] = useState(null);
  const [plan, setPlan] = useState("free");
  const navigate = useNavigate();

  const refresh = useCallback(() => {
    getCredits().then((d) => { setCredits(d?.credits ?? null); setPlan(d?.plan || "free"); }).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    const onEvt = () => refresh();
    window.addEventListener("hive-credits-refresh", onEvt);
    return () => { clearInterval(id); window.removeEventListener("hive-credits-refresh", onEvt); };
  }, [refresh]);

  const zero = credits !== null && credits <= 0;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-40 backdrop-blur-xl bg-black/60 border-b border-zinc-800">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-10">
            <HiveLogo />
            <nav className="hidden md:flex items-center gap-1">
              {navItems.map((n) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  end={n.end}
                  data-testid={`nav-${n.label.toLowerCase().replace(/\s/g, "-")}`}
                  className={({ isActive }) =>
                    `px-3 py-2 text-sm rounded-md transition-colors ${
                      isActive ? "text-white bg-zinc-800" : "text-zinc-400 hover:text-white hover:bg-zinc-900"
                    }`
                  }
                >
                  {n.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <button
            onClick={() => navigate("/subscription")}
            data-testid="nav-credits"
            title={zero ? "Free credits exhausted — click to upgrade" : `${plan.toUpperCase()} plan`}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-full border transition-colors ${
              zero
                ? "border-red-500/60 bg-red-500/10 hover:bg-red-500/20 animate-pulse"
                : "border-zinc-800 bg-zinc-900/60 hover:border-sky-500/40"
            }`}
          >
            <Zap className={`w-4 h-4 ${zero ? "text-red-400" : "text-sky-400"}`} />
            <span className={`font-mono text-sm ${zero ? "text-red-300 font-bold" : "text-zinc-200"}`} data-testid="credits-badge">
              {credits ?? "—"}
            </span>
            <span className={`text-xs ${zero ? "text-red-400/80" : "text-zinc-500"}`}>
              {zero ? "exhausted" : "credits"}
            </span>
          </button>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  );
}
