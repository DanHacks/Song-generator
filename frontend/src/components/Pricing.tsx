import { useEffect, useState } from "react";
import {
  getPlans,
  getBillingStatus,
  checkout,
  mockConfirm,
  type BillingStatus,
  type PlansResponse,
} from "../api";

type Status = "idle" | "pending" | "success" | "error";

interface Props {
  onError: (msg: string) => void;
}

const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "—";

export default function Pricing({ onError }: Props) {
  const [plans, setPlans] = useState<PlansResponse | null>(null);
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [provider, setProvider] = useState("mock");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<Status>("idle");

  async function load() {
    try {
      const [p, s] = await Promise.all([getPlans(), getBillingStatus()]);
      setPlans(p);
      setStatus(s);
      if (!p.providers.mpesa) setProvider((cur) => (cur === "mpesa" ? "mock" : cur));
    } catch (e) {
      onError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function subscribe(plan: string) {
    setBusy(true);
    setMsg("idle");
    try {
      if (provider === "mpesa") {
        await checkout(plan, "mpesa", phone);
        setMsg("pending");
        pollUntilPaid();
        return;
      }
      if (provider === "stripe") {
        const res = await checkout(plan, "stripe");
        const url = res.url as string;
        if (url) window.location.href = url;
        return;
      }
      const res = await checkout(plan, "mock");
      await mockConfirm(res.checkout_id as string);
      setMsg("success");
      await load();
    } catch (e) {
      setMsg("error");
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function pollUntilPaid() {
    for (let i = 0; i < 24; i++) {
      await new Promise((r) => setTimeout(r, 5000));
      const s = await getBillingStatus();
      setStatus(s);
      if (s.tier !== "free") {
        setMsg("success");
        return;
      }
    }
    setMsg("error");
  }

  if (!plans || !status) return <div className="panel sub">Loading plans…</div>;

  const current = status.tier;
  const usage = status.usage;

  return (
    <div>
      <div className="panel">
        <h2>Your Plan</h2>
        <p className="sub">
          Current plan: <strong>{status.label}</strong>
          {status.expires_at && <span> · renews/expires {fmtDate(status.expires_at)}</span>}
        </p>
        {usage.max != null ? (
          <p className="sub">
            Generations used: <strong>{usage.used}</strong> of {usage.max} · {usage.remaining} left this plan
          </p>
        ) : (
          <p className="sub">Unlimited generations on your current plan.</p>
        )}
      </div>

      <div className="pricing-grid">
        {Object.entries(plans.plans).map(([key, p]) => (
          <div key={key} className={"plan-card" + (current === key ? " current" : "")}>
            <h3>{p.label}</h3>
            {p.price_kes > 0 ? (
              <div className="plan-price">
                <span className="kes">KSH {p.price_kes.toLocaleString()}</span>
                <span className="mo">/mo</span>
              </div>
            ) : (
              <div className="plan-price">
                <span className="kes">Free</span>
              </div>
            )}
            <ul>
              <li>{p.max_generations == null ? "Unlimited generations" : `${p.max_generations} generations`}</li>
              <li>Up to {p.max_duration_s}s per track</li>
              <li>{p.stems ? "Stem export included" : "Standard WAV export"}</li>
            </ul>
            {current === key ? (
              <button className="gen-btn" disabled>
                {key === "free" ? "Current" : "Active"}
              </button>
            ) : key === "free" ? (
              <button className="gen-btn" onClick={() => onError("You're already on the Free plan.")}>
                Current
              </button>
            ) : (
              <button className="gen-btn" disabled={busy} onClick={() => subscribe(key)}>
                {busy ? "Processing…" : `Upgrade to ${p.label}`}
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="panel">
        <h2>Payment Method</h2>
        <div className="providers">
          <label>
            <input type="radio" name="provider" checked={provider === "mock"} onChange={() => setProvider("mock")} />
            Mock (sandbox demo)
          </label>
          {plans.providers.mpesa && (
            <label>
              <input type="radio" name="provider" checked={provider === "mpesa"} onChange={() => setProvider("mpesa")} />
              M-Pesa (STK Push)
            </label>
          )}
          {plans.providers.stripe && (
            <label>
              <input type="radio" name="provider" checked={provider === "stripe"} onChange={() => setProvider("stripe")} />
              Card (Stripe)
            </label>
          )}
        </div>
        {provider === "mpesa" && (
          <div className="mpesa-phone">
            <input
              type="tel"
              placeholder="M-Pesa phone number, e.g. 0712345678"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </div>
        )}
        {provider === "mock" && (
          <p className="sub">
            Demo mode: subscribing instantly grants the plan (no real money moves). Real M-Pesa/Stripe activate once
            credentials are configured on the server.
          </p>
        )}
        {msg === "pending" && <p className="sub ok">STK push sent — approve the payment on your phone. Checking status…</p>}
        {msg === "success" && <p className="sub ok">Payment confirmed — your plan is now active!</p>}
        {msg === "error" && <p className="sub err">Payment could not be completed.</p>}
      </div>
    </div>
  );
}
