import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { FileCheck2, CheckCircle2, Lightbulb } from "lucide-react";

export default function ArtifactView({ open, onOpenChange, artifact }) {
  const c = artifact?.content || {};
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="artifact-dialog"
        className="max-w-2xl max-h-[85vh] overflow-y-auto bg-zinc-950 border-zinc-800"
      >
        <DialogHeader>
          <div className="flex items-center gap-2 text-emerald-400 text-xs font-mono uppercase tracking-widest mb-1">
            <FileCheck2 className="w-4 h-4" /> Verified Deliverable
          </div>
          <DialogTitle className="font-display text-2xl text-white">
            {c.title || artifact?.title || "Deliverable"}
          </DialogTitle>
          <DialogDescription className="text-zinc-500">
            Verified result produced and reviewed by the HIVE workforce.
          </DialogDescription>
        </DialogHeader>

        {c.executive_summary && (
          <p className="text-zinc-300 leading-relaxed text-sm border-l-2 border-sky-500/50 pl-4">
            {c.executive_summary}
          </p>
        )}

        <div className="space-y-4 mt-2">
          {(c.sections || []).map((s, i) => (
            <div key={i}>
              <h4 className="font-display font-semibold text-white text-sm mb-1">{s.heading}</h4>
              <p className="text-zinc-400 text-sm leading-relaxed">{s.content}</p>
            </div>
          ))}
        </div>

        {(c.recommendations || []).length > 0 && (
          <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="flex items-center gap-2 text-amber-400 text-xs font-mono uppercase tracking-widest mb-3">
              <Lightbulb className="w-4 h-4" /> Recommendations
            </div>
            <ul className="space-y-2">
              {c.recommendations.map((r, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-zinc-300">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                  {r}
                </li>
              ))}
            </ul>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
