import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import {
  User, ShieldCheck, Wrench, FileText, ArrowRightLeft, AlertTriangle, CheckCircle2, Clock, Boxes,
} from "lucide-react";
import { getWorkerDetail } from "@/lib/api";

const Section = ({ icon: Icon, title, children, count }) => (
  <div className="rounded-lg border border-zinc-800 bg-zinc-950/60">
    <div className="px-3 py-2 border-b border-zinc-800 flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-zinc-500">
      <Icon className="w-3.5 h-3.5" /> {title} {count != null && <span className="text-zinc-600">({count})</span>}
    </div>
    <div className="p-3 text-sm text-zinc-300">{children}</div>
  </div>
);

export default function WorkerDetailPanel({ open, onOpenChange, missionId, agentId }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    if (open && missionId && agentId) {
      setData(null);
      getWorkerDetail(missionId, agentId).then(setData).catch(() => {});
    }
  }, [open, missionId, agentId]);

  const a = data?.agent;
  const s = data?.summary || {};

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="worker-detail-panel" className="max-w-2xl max-h-[85vh] overflow-y-auto bg-zinc-950 border-zinc-800">
        <DialogHeader>
          <div className="flex items-center gap-2">
            {a?.is_reviewer ? <ShieldCheck className="w-5 h-5 text-violet-300" /> : <User className="w-5 h-5 text-sky-400" />}
            <DialogTitle className="font-display text-xl text-white">{a?.name || "Worker"}</DialogTitle>
            {a && <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono ${s.verified ? "bg-emerald-500/15 text-emerald-400" : "bg-zinc-800 text-zinc-400"}`}>{a.status}</span>}
          </div>
          <DialogDescription className="text-zinc-500 font-mono text-xs">
            {a?.role}{s.verified ? " · work verified ✓" : ""}
          </DialogDescription>
        </DialogHeader>

        {!data ? (
          <div className="text-zinc-600 font-mono text-sm py-8 text-center">Loading worker execution…</div>
        ) : (
          <div className="space-y-3">
            <Section icon={Boxes} title="Input / Tasks" count={s.input?.length}>
              {s.input?.length ? s.input.map((t, i) => (
                <div key={i} className="mb-1"><span className="text-white">{t.task}</span>{t.context ? <span className="text-zinc-500"> — {t.context}</span> : null}</div>
              )) : <span className="text-zinc-600">No task assigned.</span>}
            </Section>

            <Section icon={Clock} title="Actions timeline" count={s.actions?.length}>
              {s.actions?.length ? (
                <div className="font-mono text-[12px] space-y-1">
                  {s.actions.map((ac, i) => (
                    <div key={i} className="flex items-start gap-2" data-testid="worker-action">
                      <span className="text-sky-400 shrink-0">{ac.type}</span>
                      <span className="text-zinc-400">{ac.message}</span>
                    </div>
                  ))}
                </div>
              ) : <span className="text-zinc-600">No actions recorded.</span>}
            </Section>

            <div className="grid grid-cols-2 gap-3">
              <Section icon={Wrench} title="Tools" count={s.tools?.length}>
                {s.tools?.length ? s.tools.map((t, i) => <span key={i} className="inline-block mr-1 mb-1 px-2 py-0.5 rounded bg-zinc-800 text-xs font-mono">{t}</span>) : <span className="text-zinc-600 text-xs">None</span>}
              </Section>
              <Section icon={FileText} title="Files affected" count={s.files?.length}>
                {s.files?.length ? s.files.map((f, i) => <div key={i} className="font-mono text-[12px] text-zinc-400">{f}</div>) : <span className="text-zinc-600 text-xs">None</span>}
              </Section>
            </div>

            <Section icon={ArrowRightLeft} title="Handoffs" count={s.handoffs?.length}>
              {s.handoffs?.length ? s.handoffs.map((h, i) => (
                <div key={i} className="text-[13px]">→ <span className="text-white">{h.to}</span> <span className="text-zinc-500">{h.what}</span></div>
              )) : <span className="text-zinc-600 text-xs">No handoffs.</span>}
            </Section>

            {(s.issues?.length > 0 || s.recovery?.length > 0) && (
              <Section icon={AlertTriangle} title="Issues & recovery" count={(s.issues?.length || 0)}>
                {s.issues?.map((it, i) => <div key={i} className="text-amber-300 text-[13px]">⚠ {it.message}</div>)}
                {s.recovery?.map((r, i) => <div key={i} className="text-emerald-300 text-[13px]">🔧 {r.message}</div>)}
              </Section>
            )}

            <Section icon={CheckCircle2} title="Output">
              {s.output?.length ? s.output.map((o, i) => (
                <div key={i} className="mb-2">
                  <div className="text-white text-[13px]">{o.task}</div>
                  {o.summary && <div className="text-zinc-400 text-[12px]">{o.summary}</div>}
                </div>
              )) : <span className="text-zinc-600 text-xs">No output.</span>}
              <div className={`mt-2 text-xs font-mono ${s.verified ? "text-emerald-400" : "text-zinc-500"}`}>
                Verification: {s.verified ? "PASSED ✓" : "pending"}
              </div>
            </Section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
