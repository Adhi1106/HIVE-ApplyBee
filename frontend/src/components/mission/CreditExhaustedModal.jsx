import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Zap, RefreshCw } from "lucide-react";
import { renewCredits } from "@/lib/api";
import { toast } from "sonner";

export default function CreditExhaustedModal({ open, onOpenChange, onRenewed }) {
  const renew = async () => {
    try {
      const u = await renewCredits();
      toast.success("Demo credits renewed");
      onRenewed?.(u?.credits);
      onOpenChange(false);
    } catch (e) {
      toast.error("Could not renew credits");
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="credit-exhausted-modal" className="max-w-md bg-zinc-950 border-amber-500/30">
        <DialogHeader>
          <div className="flex items-center gap-2 text-amber-400">
            <Zap className="w-5 h-5" />
            <DialogTitle className="font-display text-xl text-white">Demo credits exhausted</DialogTitle>
          </div>
          <DialogDescription className="text-zinc-400">
            This is a hackathon demo. You have reached the current demo usage limit. Any running mission will still finish and verify with safe deterministic execution.
          </DialogDescription>
        </DialogHeader>
        <div className="flex gap-2 mt-2">
          <button data-testid="renew-credits-btn" onClick={renew} className="inline-flex items-center gap-2 bg-amber-400 text-zinc-950 font-semibold rounded-full px-4 py-2 text-sm hover:-translate-y-0.5 transition-transform">
            <RefreshCw className="w-4 h-4" /> Renew Demo Credits
          </button>
          <button data-testid="continue-close-btn" onClick={() => onOpenChange(false)} className="rounded-full border border-zinc-700 text-zinc-200 px-4 py-2 text-sm hover:border-zinc-500 transition-colors">
            Continue / Close
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
