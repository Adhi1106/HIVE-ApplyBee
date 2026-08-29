import { Outlet, NavLink, Link } from "react-router-dom";
import { useEffect, useState } from "react";
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
];

export default function Layout() {
  const [credits, setCredits] = useState(null);
  useEffect(() => {
    getCredits().then((d) => setCredits(d?.credits)).catch(() => {});
  }, []);

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
          <NavLink
            to="/credits"
            data-testid="nav-credits"
            className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-zinc-800 bg-zinc-900/60 hover:border-sky-500/40 transition-colors"
          >
            <Zap className="w-4 h-4 text-sky-400" />
            <span className="font-mono text-sm text-zinc-200" data-testid="credits-badge">
              {credits ?? "—"}
            </span>
            <span className="text-xs text-zinc-500">credits</span>
          </NavLink>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  );
}
