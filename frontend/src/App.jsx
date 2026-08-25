import { useState } from "react";
import { LayoutDashboard, Zap, ClipboardCheck, Wrench, DollarSign, Rss, Sparkles, FileText, Image, MoreHorizontal, GitBranch } from "lucide-react";
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
import BuildingSelector from "./BuildingSelector";
import OwnerPortal from "./OwnerPortal";

/**
 * App
 *
 * Ties everything together: shows LoginScreen until authenticated, then
 * routes staff vs tenant into the right set of screens. Swap the simple
 * tab state below for your actual router (React Router, etc.) as needed.
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

const STAFF_TABS = ["dashboard", "actions", "inspections", "maintenance", "payments", "workflows", "documents", "gallery", "feed", "ai"];
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
};
function AppShell() {
  const { user, loading, logout, selectedProperty } = useAuth();
  const [tab, setTab] = useState("dashboard");
  const [moreOpen, setMoreOpen] = useState(false);
  if (window.location.pathname === "/apply") return <LeadCaptureForm />;
  if (loading) return <p className="p-6 text-sm text-slate-400">Loading…</p>;
  if (!user) return <LoginScreen />;
  if (user.role === "owner") return <OwnerPortal user={user} logout={logout} />;

  const tabs = user.role === "staff" ? STAFF_TABS : TENANT_TABS;
  const activeTab = tabs.includes(tab) ? tab : tabs[0];

  // Staff: scoped to whatever building they've selected (or null = all
  // buildings, aggregated). Tenants: always scoped to their own unit's
  // property — the selector doesn't apply to them.
  const effectivePropertyId = user.role === "staff" ? (selectedProperty?.id || null) : user.propertyId;

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
        {(user.role === "staff" ? PRIMARY_STAFF_TABS : PRIMARY_TENANT_TABS).map((t) => {
          const Icon = TAB_ICONS[t];
          return (
            <button
              key={t}
              onClick={() => { setTab(t); setMoreOpen(false); }}
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

        {tabs.filter((t) => !(user.role === "staff" ? PRIMARY_STAFF_TABS : PRIMARY_TENANT_TABS).includes(t)).length > 0 && (
          <div className="relative">
            <button
              onClick={() => setMoreOpen((v) => !v)}
              className={`text-sm px-3 py-1.5 rounded-full capitalize flex items-center gap-1.5 transition-transform hover:scale-105 hover:-translate-y-0.5 ${
                tabs.filter((t) => !(user.role === "staff" ? PRIMARY_STAFF_TABS : PRIMARY_TENANT_TABS).includes(t)).includes(activeTab)
                  ? "bg-gradient-to-r from-indigo-600 to-fuchsia-600 text-white shadow-sm"
                  : "bg-white border border-slate-200 text-slate-600"
              }`}
            >
              <MoreHorizontal size={14} />
              More
            </button>
            {moreOpen && (
              <div className="absolute left-0 top-10 bg-white border border-slate-200 rounded-xl shadow-lg py-1.5 w-40 z-10">
                {tabs.filter((t) => !(user.role === "staff" ? PRIMARY_STAFF_TABS : PRIMARY_TENANT_TABS).includes(t)).map((t) => {
                  const Icon = TAB_ICONS[t];
                  return (
                    <button
                      key={t}
                      onClick={() => { setTab(t); setMoreOpen(false); }}
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
        {activeTab === "dashboard" && (
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
        )}
        {activeTab === "actions" && <AIActionsPanel propertyId={effectivePropertyId} />}
        {activeTab === "inspections" && (
          <InspectionsList
            propertyId={effectivePropertyId}
            inspectorName={user.name}
          />
        )}
        {activeTab === "maintenance" && <MaintenanceTickets propertyId={effectivePropertyId} />}
        {activeTab === "payments" && <PaymentsPanel propertyId={effectivePropertyId} />}
        {activeTab === "workflows" && <Workflows />}
        {activeTab === "documents" && <Documents />}
        {activeTab === "gallery" && <Gallery />}
        {activeTab === "feed" && <SocialFeed />}
        {activeTab === "ai" && <AICopilot propertyId={effectivePropertyId} />}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}
