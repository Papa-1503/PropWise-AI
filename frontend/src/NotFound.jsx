import { Link } from "react-router-dom";
import { Home } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-screen app-bg flex items-center justify-center px-6">
      <div className="text-center">
        <h1 className="font-serif font-bold text-2xl text-slate-800 mb-2">RentFlow AI</h1>
        <p className="text-slate-500 mb-6">We couldn't find that page.</p>
        <Link
          to="/app/dashboard"
          className="inline-flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-4 py-2 rounded-lg hover:bg-slate-800"
        >
          <Home size={14} />
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
