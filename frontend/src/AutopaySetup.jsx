import { useState, useEffect, useCallback } from "react";
import { loadStripe } from "@stripe/stripe-js";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";
import { Landmark, CheckCircle2, AlertCircle } from "lucide-react";

/**
 * AutopaySetup
 *
 * Tenant-facing bank-account linking for ACH autopay. Backend side is
 * routers/payments.py (setup-intent, autopay/enroll, autopay/cancel)
 * and stripe_service.py.
 *
 * Real Stripe.js flow, confirmed against the actual installed
 * @stripe/stripe-js type definitions rather than guessed:
 *   1. POST /setup-intent - gets a SetupIntent client secret from our
 *      backend, tied to this resident's Stripe Customer
 *   2. stripe.createPaymentMethod({type: 'us_bank_account', ...}) -
 *      collects account/routing number, exchanges for a tokenized
 *      PaymentMethod. Account/routing numbers exist only in this
 *      browser call to Stripe directly; they never touch PropWise AI's
 *      own backend at any point.
 *   3. stripe.confirmUsBankAccountSetup(clientSecret, {payment_method})
 *      - attaches that PaymentMethod to the SetupIntent, completing
 *      verification
 *   4. POST /autopay/enroll with the resulting paymentMethodId - only
 *      this token, never the raw account details, reaches our backend
 *
 * Honestly degrades rather than crashing or silently doing nothing:
 * if GET /stripe-config returns publishableKey: null (Stripe not
 * configured on the backend yet), this shows a clear "not available
 * yet" message instead of attempting to load Stripe.js against a key
 * that doesn't exist.
 */

export default function AutopaySetup() {
  const [publishableKey, setPublishableKey] = useState(undefined); // undefined = loading, null = not configured
  const [stripe, setStripe] = useState(null);
  const [autopayEnabled, setAutopayEnabled] = useState(false);
  const [accountNumber, setAccountNumber] = useState("");
  const [routingNumber, setRoutingNumber] = useState("");
  const [accountHolderName, setAccountHolderName] = useState("");
  const [accountType, setAccountType] = useState("checking");
  const [linking, setLinking] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const { authFetch, user } = useAuth();

  const fetchConfig = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE}/payments/stripe-config`);
      const data = await res.json();
      setPublishableKey(data.publishableKey || null);
    } catch {
      setPublishableKey(null);
    }
  }, [authFetch]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  useEffect(() => {
    if (publishableKey) {
      loadStripe(publishableKey).then(setStripe);
    }
  }, [publishableKey]);

  useEffect(() => {
    setAutopayEnabled(Boolean(user?.autopayEnabled));
  }, [user]);

  async function handleLinkAccount() {
    if (!stripe) return;
    if (!accountNumber || !routingNumber || !accountHolderName.trim()) {
      setError("Bank name, account number, and routing number are all required.");
      return;
    }
    setLinking(true);
    setError(null);
    try {
      const setupRes = await authFetch(`${API_BASE}/payments/setup-intent`, { method: "POST" });
      const setupData = await setupRes.json().catch(() => ({}));
      if (!setupRes.ok) throw new Error(setupData.detail || "Couldn't start bank account setup.");

      const { paymentMethod, error: pmError } = await stripe.createPaymentMethod({
        type: "us_bank_account",
        us_bank_account: {
          account_number: accountNumber,
          routing_number: routingNumber,
          account_holder_type: "individual",
          account_type: accountType,
        },
        billing_details: { name: accountHolderName },
      });
      if (pmError) throw new Error(pmError.message);

      const { setupIntent, error: confirmError } = await stripe.confirmUsBankAccountSetup(
        setupData.clientSecret,
        { payment_method: paymentMethod.id }
      );
      if (confirmError) throw new Error(confirmError.message);

      const enrollRes = await authFetch(`${API_BASE}/payments/autopay/enroll`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paymentMethodId: setupIntent.payment_method }),
      });
      const enrollData = await enrollRes.json().catch(() => ({}));
      if (!enrollRes.ok) throw new Error(enrollData.detail || "Couldn't enable autopay.");

      setAutopayEnabled(true);
      setSuccess(true);
      setAccountNumber("");
      setRoutingNumber("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLinking(false);
    }
  }

  async function handleCancelAutopay() {
    setLinking(true);
    try {
      await authFetch(`${API_BASE}/payments/autopay/cancel`, { method: "POST" });
      setAutopayEnabled(false);
      setSuccess(false);
    } finally {
      setLinking(false);
    }
  }

  if (publishableKey === undefined) {
    return <div className="h-32 bg-slate-100 rounded-xl animate-pulse" />;
  }

  if (publishableKey === null) {
    return (
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex items-start gap-3">
        <AlertCircle size={18} className="text-slate-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-medium text-slate-600">Autopay isn't set up yet</p>
          <p className="text-xs text-slate-400 mt-0.5">
            Online bank payments aren't available on this property yet. Contact staff to pay another way.
          </p>
        </div>
      </div>
    );
  }

  if (autopayEnabled) {
    return (
      <div className="bg-emerald-50 border border-emerald-100 rounded-xl p-4 flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <CheckCircle2 size={18} className="text-emerald-600 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-emerald-800">Autopay is on</p>
            <p className="text-xs text-emerald-600 mt-0.5">
              Rent will be charged automatically from your linked bank account on the due date.
            </p>
          </div>
        </div>
        <button
          onClick={handleCancelAutopay}
          disabled={linking}
          className="text-xs font-medium text-emerald-700 underline shrink-0 disabled:opacity-50"
        >
          Turn off
        </button>
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Landmark size={16} className="text-slate-500" />
        <h3 className="text-sm font-semibold">Set up autopay</h3>
      </div>

      {error && <p role="alert" className="text-xs text-rose-600 mb-2">{error}</p>}

      <div className="grid grid-cols-2 gap-2 mb-2">
        <input
          value={accountHolderName}
          onChange={(e) => setAccountHolderName(e.target.value)}
          placeholder="Name on account"
          className="col-span-2 text-sm border border-slate-200 rounded-lg px-3 py-2"
        />
        <input
          value={routingNumber}
          onChange={(e) => setRoutingNumber(e.target.value)}
          placeholder="Routing number"
          className="text-sm border border-slate-200 rounded-lg px-3 py-2"
        />
        <input
          value={accountNumber}
          onChange={(e) => setAccountNumber(e.target.value)}
          placeholder="Account number"
          className="text-sm border border-slate-200 rounded-lg px-3 py-2"
        />
        <select
          value={accountType}
          onChange={(e) => setAccountType(e.target.value)}
          className="col-span-2 text-sm border border-slate-200 rounded-lg px-3 py-2"
        >
          <option value="checking">Checking</option>
          <option value="savings">Savings</option>
        </select>
      </div>

      <p className="text-[11px] text-slate-400 mb-3">
        Your bank details go directly to Stripe, our payment processor — PropWise AI never
        stores your account or routing number.
      </p>

      <button
        onClick={handleLinkAccount}
        disabled={linking || !stripe}
        className="w-full bg-indigo-600 text-white text-sm font-medium py-2 rounded-lg disabled:opacity-50"
      >
        {linking ? "Linking…" : "Link bank account & enable autopay"}
      </button>
    </div>
  );
}
