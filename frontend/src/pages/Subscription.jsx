import { useEffect, useState } from "react";
import { Zap, Check, Crown, Building2, Sparkles, Loader2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { getPlans, getCredits, createOrder, verifyPayment, razorpayConfig } from "@/lib/api";

const loadRazorpay = () =>
  new Promise((resolve) => {
    if (window.Razorpay) return resolve(true);
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => resolve(true);
    s.onerror = () => resolve(false);
    document.body.appendChild(s);
  });

const ICONS = { free: Sparkles, pro: Crown, business: Building2 };

export default function Subscription() {
  const [plans, setPlans] = useState([]);
  const [state, setState] = useState(null);
  const [billing, setBilling] = useState("monthly");
  const [busy, setBusy] = useState(null);

  const refreshState = () => getCredits().then(setState).catch(() => {});

  useEffect(() => {
    getPlans().then((d) => setPlans(d.plans || [])).catch(() => {});
    refreshState();
    razorpayConfig().catch(() => {});
  }, []);

  const price = (p) => (billing === "yearly" ? p.price_yearly : p.price_monthly);

  const upgrade = async (plan) => {
    setBusy(plan.id);
    try {
      const ok = await loadRazorpay();
      if (!ok) { toast.error("Could not load the payment library. Check your connection."); setBusy(null); return; }
      const order = await createOrder(plan.id, billing);
      const rzp = new window.Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: "HIVE",
        description: `${plan.name} plan — ${billing}`,
        order_id: order.order_id,
        theme: { color: "#38bdf8" },
        handler: async (resp) => {
          try {
            const res = await verifyPayment({
              razorpay_order_id: resp.razorpay_order_id,
              razorpay_payment_id: resp.razorpay_payment_id,
              razorpay_signature: resp.razorpay_signature,
              plan: plan.id,
              billing,
            });
            setState(res);
            window.dispatchEvent(new Event("hive-credits-refresh"));
            toast.success(`🎉 ${plan.name} activated! ${res.credits} credits added.`);
          } catch (e) {
            toast.error("Payment verification failed. Please try again — no credits were granted.");
          } finally {
            setBusy(null);
          }
        },
        modal: {
          ondismiss: () => {
            toast("Checkout closed. No credits were deducted.");
            setBusy(null);
          },
        },
      });
      rzp.on("payment.failed", () => {
        toast.error("Payment could not be completed. No credits were deducted.");
        setBusy(null);
      });
      rzp.open();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not start checkout.");
      setBusy(null);
    }
  };

  const currentPlan = state?.plan || "free";
  const exhausted = state?.exhausted;

  return (
    <div className="max-w-6xl mx-auto px-6 py-14">
      <div className="flex items-center gap-2 mb-1">
        <Zap className="w-5 h-5 text-sky-400" />
        <h1 className="font-display font-extrabold text-4xl text-white">Plans &amp; Credits</h1>
      </div>
      <p className="text-zinc-500 text-sm mb-6 max-w-2xl">
        Every mission you run spends 1 credit. Free credits refresh automatically; paid plans give you a larger monthly allowance.
      </p>

      {exhausted && (
        <div className="mb-8 rounded-xl border border-red-500/40 bg-red-500/10 p-4 flex items-center gap-3" data-testid="exhausted-banner">
          <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
          <div className="text-sm text-red-200">
            You're out of free credits. They refresh in ~{state?.free_reset_hours || 2} hours — or unlock more below.
            {state?.demo_mode && <span className="text-red-300/70"> (Demo mode: missions still run for now.)</span>}
          </div>
        </div>
      )}

      {/* billing toggle */}
      <div className="flex items-center gap-2 mb-8" data-testid="billing-toggle">
        {[["monthly", "Monthly"], ["yearly", "Yearly"]].map(([k, label]) => (
          <button
            key={k}
            data-testid={`billing-${k}`}
            onClick={() => setBilling(k)}
            className={`text-sm px-4 py-1.5 rounded-full border transition-colors ${
              billing === k ? "border-sky-500/50 text-sky-300 bg-sky-500/10" : "border-zinc-800 text-zinc-400 hover:text-white"
            }`}
          >
            {label}{k === "yearly" && <span className="ml-1.5 text-[10px] text-emerald-400">2 months free</span>}
          </button>
        ))}
      </div>

      <div className="grid md:grid-cols-3 gap-5">
        {plans.map((p) => {
          const Icon = ICONS[p.id] || Sparkles;
          const isCurrent = currentPlan === p.id;
          const isPaid = p.id !== "free";
          return (
            <div
              key={p.id}
              data-testid={`plan-card-${p.id}`}
              className={`relative rounded-2xl border p-6 flex flex-col transition-colors ${
                p.recommended
                  ? "border-sky-500/50 bg-gradient-to-b from-sky-500/10 to-zinc-900/40"
                  : "border-zinc-800 bg-zinc-900/40"
              }`}
            >
              {p.recommended && (
                <span className="absolute -top-3 left-6 text-[10px] font-mono uppercase tracking-widest bg-sky-400 text-zinc-950 rounded-full px-3 py-1 font-bold">
                  Recommended
                </span>
              )}
              <div className="flex items-center gap-2 mb-3">
                <Icon className={`w-5 h-5 ${p.recommended ? "text-sky-400" : "text-zinc-300"}`} />
                <span className="font-display font-bold text-xl text-white">{p.name}</span>
                {isCurrent && (
                  <span className="ml-auto text-[10px] font-mono uppercase tracking-widest text-emerald-400 border border-emerald-500/40 bg-emerald-500/10 rounded-full px-2 py-0.5" data-testid={`current-${p.id}`}>
                    Current
                  </span>
                )}
              </div>
              <div className="text-xs text-zinc-500 mb-4">{p.tagline}</div>
              <div className="mb-1">
                <span className="text-4xl font-display font-extrabold text-white">₹{price(p)}</span>
                <span className="text-sm text-zinc-500">/{billing === "yearly" ? "yr" : "mo"}</span>
              </div>
              <div className="text-xs text-sky-400 font-mono mb-5">
                {p.credits} credits{isPaid ? " / month" : " to start"}
              </div>
              <ul className="space-y-2 mb-6 flex-1">
                {p.features.map((f, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-zinc-300">
                    <Check className="w-4 h-4 text-sky-400 mt-0.5 shrink-0" /> {f}
                  </li>
                ))}
              </ul>
              {!isPaid ? (
                <button
                  disabled
                  data-testid="plan-free-btn"
                  className="w-full rounded-full py-2.5 text-sm font-semibold border border-zinc-800 text-zinc-500 cursor-default"
                >
                  {isCurrent ? "Your current plan" : "Free forever"}
                </button>
              ) : (
                <button
                  onClick={() => upgrade(p)}
                  disabled={busy === p.id}
                  data-testid={`upgrade-${p.id}-btn`}
                  className={`w-full rounded-full py-2.5 text-sm font-semibold inline-flex items-center justify-center gap-2 transition-transform hover:-translate-y-0.5 disabled:opacity-60 disabled:translate-y-0 ${
                    p.recommended ? "bg-sky-400 text-zinc-950" : "bg-white/90 text-zinc-950"
                  }`}
                >
                  {busy === p.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                  {isCurrent ? `Renew ${p.name}` : `Upgrade to ${p.name}`}
                </button>
              )}
            </div>
          );
        })}
      </div>

      <p className="text-xs text-zinc-600 mt-8 text-center">
        Payments are processed securely by Razorpay in test mode. Use test card 4111 1111 1111 1111, any future expiry &amp; CVV.
      </p>
    </div>
  );
}
