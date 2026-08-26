import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { useState } from "react";
import { LayoutDashboard, Zap, ClipboardCheck, Wrench, DollarSign, Rss, Sparkles, FileText, Image, MoreHorizontal, GitBranch, MessageSquare, FileSignature, UserSearch } from "lucide-react";
import { AuthProvider, useAuth } from "./AuthContext";
import Avatar from "./Avatar";
import LeadCaptureForm from "./LeadCaptureForm";
import Documents from "./Documents";
import Gallery from "./Gallery";
import LoginScreen from "./LoginScreen";
import Dashboard from "./Dashboard";
import MaintenanceTickets from "./MaintenanceTickets";
import InspectionsList from "./InspectionsList";
import AICopilot from "./AICopilot";
import AIActionsPanel from "./AIActionsPanel";
import PaymentsPanel from "./PaymentsPanel";
import PortfolioHealthHeader from "./PortfolioHealthHeader";
import AIWorkforcePanel from "./AIWorkforcePanel";
import OccupancyInsight from "./OccupancyInsight";
import AskRentFlowSidebar from "./AskRentFlowSidebar";
import ConfidenceDistribution from "./ConfidenceDistribution";
import MaintenanceTrendAlert from "./MaintenanceTrendAlert";
import SocialFeed from "./SocialFeed";
import NotificationBell from "./NotificationBell";
import Workflows from "./Workflows";
import CommunicationsPanel from "./CommunicationsPanel";
import LeasesList from "./LeasesList";
import ScreeningList from "./ScreeningList";
import BuildingSelector from "./BuildingSelector";
import OwnerPortal from "./OwnerPortal";
import NotFound from "./NotFound";

/**
 * App
 *
 * CHANGED Aug 25, 2026: real URL-based routing (React Router), replacing
 * the previous useState-based tab switching — flagged by an external
 * audit as a real gap: refresh, browser back/forward, bookmarking, and
 * link-sharing didn't work for any tab before this change, and a direct
 * load of /apply 404'd (fixed alongside this, plus a Render rewrite
 * rule). Every staff/tenant tab is now a real path under /app/, e.g.
 * /app/leases, /app/maintenance.
 *
 * Auth handling: visiting a protected path while logged out renders
 * LoginScreen at that same URL (rather than redirecting away first) —
 * once login succeeds, the already-correct URL just renders its real
 * content, which naturally preserves "where you were headed" through
 * sign-in without extra redirect logic.
 *
 * Building context: staff can see every property, and several buildings
 * can share the same unit numbers (e.g. multiple "Unit 101"s across the
 * portfolio), so which building is "active" matters. Staff pick a
 * building via BuildingSelector in the header; every panel below is
 * scoped to that selection via effectivePropertyId. Picking "All
 * Buildings" (selectedProperty = null) shows the portfolio-wide
 * aggregate view, same as the previous default behavior. Tenants don't
 * see the selector at all — they're always scoped to their own unit's
 * property, same as before.
 */

const STAFF_TABS = ["dashboard", "actions", "inspections", "maintenance", "payments", "workflows", "communications", "leases", "screening", "documents", "gallery", "feed", "ai"];
const TENANT_TABS = ["documents", "maintenance", "payments", "gallery", "ai"];
const PRIMARY_STAFF_TABS = ["dashboard", "actions", "inspections", "maintenance", "payments"];
const PRIMARY_TENANT_TABS = ["maintenance", "payments"];
const TAB_ICONS = {
  dashboard: LayoutDashboard,
  actions: Zap,
  inspections: ClipboardCheck,
  maintenance: Wrench,
  payments: DollarSign,
  feed: Rss,
  ai: Sparkles,
  documents: FileText,
  gallery: Image,
  workflows: GitBranch,
  communications: MessageSquare,
  leases: FileSignature,
  screening: UserSearch,
};

function AppShell() {
  const { user, loading, logout, selectedProperty } = useAuth();
  const [moreOpen, setMoreOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  if (loading) return <p className="p-6 text-sm text-slate-400">Loading…</p>;
  if (!user) return <LoginScreen />;
  if (user.role === "owner") return <OwnerPortal user={user} logout={logout} />;

  const tabs = user.role === "staff" ? STAFF_TABS : TENANT_TABS;
  const currentSegment = location.pathname.replace(/^\/app\/?/, "");
  const activeTab = tabs.includes(currentSegment) ? currentSegment : tabs[0];
  const primaryTabs = user.role === "staff" ? PRIMARY_STAFF_TABS : PRIMARY_TENANT_TABS;

  // Staff: scoped to whatever building they've selected (or null = all
  // buildings, aggregated). Tenants: always scoped to their own unit's
  // property — the selector doesn't apply to them.
  const effectivePropertyId = user.role === "staff" ? (selectedProperty?.id || null) : user.propertyId;

  const goTo = (t) => {
    navigate(`/app/${t}`);
    setMoreOpen(false);
  };

  return (
    <div className="min-h-screen app-bg">
      <header className="bg-gradient-to-r from-indigo-600 via-violet-600 to-fuchsia-600 text-white px-6 py-3 flex items-center justify-between shadow-md">
        <h1 className="font-serif font-bold text-lg">RentFlow AI</h1>
        <div className="flex items-center gap-3 text-sm">
          {user.role === "staff" && <BuildingSelector />}
          <NotificationBell />
          <div className="flex items-center gap-2">
            <Avatar name={user.name} size={26} />
            <span>{user.name} · {user.role === "staff" ? "Staff" : `Unit ${user.unitId || "—"}`}</span>
          </div>
          <button onClick={logout} className="text-xs border border-white/30 rounded px-2 py-1 hover:bg-white/10">
            Sign out
          </button>
        </div>
      </header>

      <nav className="relative flex gap-2 px-6 py-3">
        {primaryTabs.map((t) => {
          const Icon = TAB_ICONS[t];
          return (
            <button
              key={t}
              onClick={() => goTo(t)}
              className={`text-sm px-3 py-1.5 rounded-full capitalize flex items-center gap-1.5 transition-transform hover:scale-105 hover:-translate-y-0.5 ${
                activeTab === t
                  ? "bg-gradient-to-r from-indigo-600 to-fuchsia-600 text-white shadow-sm"
                  : "bg-white border border-slate-200 text-slate-600"
              }`}
            >
              {Icon && <Icon size={14} />}
              {t}
            </button>
          );
        })}

        {tabs.filter((t) => !primaryTabs.includes(t)).length > 0 && (
          <div className="relative">
            <button
              onClick={() => setMoreOpen((v) => !v)}
              className={`text-sm px-3 py-1.5 rounded-full capitalize flex items-center gap-1.5 transition-transform hover:scale-105 hover:-translate-y-0.5 ${
                tabs.filter((t) => !primaryTabs.includes(t)).includes(activeTab)
                  ? "bg-gradient-to-r from-indigo-600 to-fuchsia-600 text-white shadow-sm"
                  : "bg-white border border-slate-200 text-slate-600"
              }`}
            >
              <MoreHorizontal size={14} />
              More
            </button>
            {moreOpen && (
              <div className="absolute left-0 top-10 bg-white border border-slate-200 rounded-xl shadow-lg py-1.5 w-40 z-10">
                {tabs.filter((t) => !primaryTabs.includes(t)).map((t) => {
                  const Icon = TAB_ICONS[t];
                  return (
                    <button
                      key={t}
                      onClick={() => goTo(t)}
                      className={`w-full text-left text-sm px-3 py-2 capitalize flex items-center gap-2 hover:bg-slate-50 ${
                        activeTab === t ? "text-indigo-600 font-semibold" : "text-slate-600"
                      }`}
                    >
                      {Icon && <Icon size={14} />}
                      {t}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </nav>

      <main className="px-6 pb-10">
        <Routes>
          <Route
            path="dashboard"
            element={
              <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5">
                <div className="space-y-5">
                  <PortfolioHealthHeader propertyId={effectivePropertyId} userName={user.name} />
                  <Dashboard propertyId={effectivePropertyId} />
                  <OccupancyInsight propertyId={effectivePropertyId} />
                  <AIWorkforcePanel propertyId={effectivePropertyId} />
                </div>
                <div className="space-y-5">
                  <AskRentFlowSidebar propertyId={effectivePropertyId} />
                  <MaintenanceTrendAlert propertyId={effectivePropertyId} />
                  <ConfidenceDistribution propertyId={effectivePropertyId} />
                </div>
              </div>
            }
          />
          <Route path="actions" element={<AIActionsPanel propertyId={effectivePropertyId} />} />
          <Route
            path="inspections"
            element={<InspectionsList propertyId={effectivePropertyId} inspectorName={user.name} />}
          />
          <Route path="maintenance" element={<MaintenanceTickets propertyId={effectivePropertyId} />} />
          <Route path="payments" element={<PaymentsPanel propertyId={effectivePropertyId} />} />
          <Route path="workflows" element={<Workflows />} />
          <Route path="communications" element={<CommunicationsPanel propertyId={effectivePropertyId} />} />
          <Route path="leases" element={<LeasesList propertyId={effectivePropertyId} />} />
          <Route path="screening" element={<ScreeningList propertyId={effectivePropertyId} />} />
          <Route path="documents" element={<Documents />} />
          <Route path="gallery" element={<Gallery />} />
          <Route path="feed" element={<SocialFeed />} />
          <Route path="ai" element={<AICopilot propertyId={effectivePropertyId} />} />
          <Route path="" element={<Navigate to={`/app/${tabs[0]}`} replace />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/apply" element={<LeadCaptureForm />} />
          <Route path="/app/*" element={<AppShell />} />
          <Route path="/" element={<Navigate to="/app/dashboard" replace />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
