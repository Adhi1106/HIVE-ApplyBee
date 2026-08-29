import { Folder, FolderOpen, FileText, FileCode2, FileSpreadsheet, File } from "lucide-react";

function iconFor(name) {
  const n = name.toLowerCase();
  if (n.endsWith(".py") || n.endsWith(".js") || n.endsWith(".ts")) return FileCode2;
  if (n.endsWith(".csv") || n.endsWith(".json") || n.endsWith(".xlsx")) return FileSpreadsheet;
  if (n.endsWith(".md") || n.endsWith(".txt") || n.endsWith(".pdf")) return FileText;
  return File;
}

function TreeCard({ title, entries, tone }) {
  const sorted = [...(entries || [])].sort((a, b) => a.path.localeCompare(b.path));
  return (
    <div className={`flex-1 min-w-0 rounded-lg border ${tone} bg-zinc-950/60 flex flex-col`}>
      <div className="px-3 py-2 border-b border-zinc-800 text-xs font-mono uppercase tracking-widest text-zinc-500 shrink-0">
        {title}
      </div>
      <div className="p-3 font-mono text-[12px] overflow-y-auto">
        {sorted.length === 0 ? (
          <span className="text-zinc-600">empty</span>
        ) : (
          sorted.map((e, i) => {
            const parts = e.path.split("/");
            const name = parts[parts.length - 1];
            const depth = parts.length - 1;
            const Icon = e.type === "dir" ? FolderOpen : iconFor(name);
            return (
              <div
                key={i}
                className={`flex items-center gap-1.5 py-0.5 ${e.type === "dir" ? "text-sky-300" : "text-zinc-400"}`}
                style={{ paddingLeft: depth * 16 }}
              >
                <Icon className={`w-3.5 h-3.5 ${e.type === "dir" ? "text-sky-400" : "text-zinc-500"}`} />
                <span>{name}{e.type === "dir" ? "/" : ""}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default function WorkspacePanel({ artifact, workspace }) {
  const c = artifact?.content || {};
  return (
    <div className="h-full flex flex-col p-4 overflow-hidden" data-testid="workspace-panel">
      <div className="flex items-center gap-2 mb-3 shrink-0">
        <Folder className="w-4 h-4 text-sky-400" />
        <span className="font-display font-semibold text-white text-sm">Real Workspace Changes</span>
        <span className="text-[11px] text-zinc-600 font-mono truncate">{workspace}</span>
      </div>
      <div className="flex-1 flex gap-3 min-h-0">
        <TreeCard title="Before" entries={c.before_tree} tone="border-zinc-800" />
        <TreeCard title="After (verified)" entries={c.after_tree} tone="border-emerald-500/30" />
        <div className="w-72 shrink-0 rounded-lg border border-zinc-800 bg-zinc-950/60 flex flex-col">
          <div className="px-3 py-2 border-b border-zinc-800 text-xs font-mono uppercase tracking-widest text-zinc-500 shrink-0">
            Operations ({(c.operations || []).length})
          </div>
          <div className="p-2 font-mono text-[11px] overflow-y-auto">
            {(c.operations || []).map((o, i) => (
              <div key={i} className="flex items-start gap-1.5 py-0.5" data-testid="workspace-op">
                <span className="text-sky-400 shrink-0">{o.op}</span>
                <span className="text-zinc-400 truncate">{o.detail}</span>
              </div>
            ))}
            {(c.operations || []).length === 0 && <span className="text-zinc-600">No operations yet…</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
