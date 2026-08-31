import { useState } from "react";
import { useAuth } from "./AuthContext";
import { Receipt, Camera } from "lucide-react";
import { API_BASE } from "./config";

export default function BillScan({ propertyId }) {
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState(null);
  const [extracted, setExtracted] = useState(null);
  const [imageUrl, setImageUrl] = useState(null);
  const { authFetch } = useAuth();

  async function handleScan(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setScanning(true);
    setError(null);
    setExtracted(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await authFetch(`${API_BASE}/bill-scan/extract`, { method: "POST", body: formData });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't read the bill.");
      setExtracted(data.extracted);
      setImageUrl(data.imageUrl);
    } catch (err) {
      setError(err.message);
    } finally {
      setScanning(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center gap-2 mb-3">
        <Receipt size={18} className="text-indigo-600" />
        <h2 className="text-lg font-semibold">Bill Scan</h2>
      </div>

      <p className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg p-3 mb-3">
        Upload a photo of a real bill — the extracted vendor, amount, date, and category are a draft for you to review, not a saved record. Submit the confirmed values through Reconciliation.
      </p>

      <label className="flex items-center justify-center gap-2 text-sm font-medium text-indigo-600 border-2 border-dashed border-indigo-200 rounded-lg py-6 cursor-pointer hover:bg-indigo-50">
        <Camera size={18} />
        {scanning ? "Reading bill..." : "Scan a bill photo"}
        <input type="file" accept="image/*" className="hidden" onChange={handleScan} disabled={scanning} />
      </label>

      {error && <p className="text-sm text-rose-600 mt-3" role="alert">{error}</p>}

      {extracted && (
        <div className="bg-white border border-slate-200 rounded-xl p-4 mt-3">
          <h3 className="text-sm font-semibold mb-2">
            Extracted — confidence: <span className="capitalize">{extracted.confidence}</span>
          </h3>
          <div className="grid grid-cols-2 gap-2 text-sm mb-2">
            <div><span className="text-slate-400 text-xs">Vendor</span><p>{extracted.vendorName || "—"}</p></div>
            <div><span className="text-slate-400 text-xs">Amount</span><p>{extracted.amount != null ? `$${extracted.amount.toFixed(2)}` : "—"}</p></div>
            <div><span className="text-slate-400 text-xs">Date</span><p>{extracted.billDate || "—"}</p></div>
            <div><span className="text-slate-400 text-xs">Category</span><p className="capitalize">{extracted.category || "—"}</p></div>
          </div>
          {extracted.notes && <p className="text-xs text-amber-600">{extracted.notes}</p>}
          {imageUrl && <img src={imageUrl} alt="Scanned bill" className="mt-3 rounded-lg border border-slate-200 max-h-48 object-contain" />}
          <p className="text-xs text-slate-400 mt-3">
            Review these values, then go to Reconciliation to create the real bank line entry — this scan alone hasn't saved anything.
          </p>
        </div>
      )}
    </div>
  );
}
