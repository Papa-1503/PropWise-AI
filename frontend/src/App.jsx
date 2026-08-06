import { useState } from "react";
import { LayoutDashboard, Zap, ClipboardCheck, Wrench, DollarSign, Rss, Sparkles } from "lucide-react";
import { AuthProvider, useAuth } from "./AuthContext";import Avatar from "./Avatar";
import LeadCaptureForm from "./LeadCaptureForm";
import LoginScreen from "./LoginScreen";
import Dashboard from "./Dashboard";
import MaintenanceTickets from "./MaintenanceTickets";
import InspectionChecklist from "./InspectionChecklist";
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

/**
 * App
 *
 * Ties everything together: shows LoginScreen until authenticated, then
 * routes staff vs tenant into the right set of screens. Swap the simple
 * tab state below for your actual router (React Router, etc.) as needed.
 */

const STAFF_TABS = ["dashboard", "actions", "inspections", "maintenance", "payments", "feed", "ai"];
const TENANT_TABS = ["maintenance", "payments", "ai"];
const TAB_ICONS = {
  dashboard: LayoutDashboard,
  actions: Zap,
  inspections: ClipboardCheck,
  maintenance: Wrench,
  payments: DollarSign,
  feed: Rss,
  ai: Sparkles,
};
function AppShell() {
  const { user, loading, logout } = useAuth();
  const [tab, setTab] = useState("dashboard");

  if (loading) return <p className="p-6 text-sm text-slate-400">Loading…</p>;
  if (!user) return <LoginScreen />;

  const tabs = user.role === "staff" ? STAFF_TABS : TENANT_TABS;
  const activeTab = tabs.includes(tab) ? tab : tabs[0];

  return (
    <div className="min-h-screen app-bg">
      <header className="bg-gradient-to-r from-indigo-600 via-violet-600 to-fuchsia-600 text-white px-6 py-3 flex items-center justify-between shadow-md">
        <h1 className="font-serif font-bold text-lg">RentFlow AI</h1>
        <div className="flex items-center gap-3 text-sm">
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

      <nav className="flex gap-2 px-6 py-3">
        {tabs.map((t) => {
          const Icon = TAB_ICONS[t];
          return (
            <button
              key={t}
              onClick={() => setTab(t)}
              
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
      </nav>

      <main className="px-6 pb-10">
        {activeTab === "dashboard" && (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5">
            <div className="space-y-5">
              <PortfolioHealthHeader propertyId={user.propertyId} userName={user.name} />
              <Dashboard propertyId={user.propertyId} />
              <OccupancyInsight propertyId={user.propertyId} />
              <AIWorkforcePanel propertyId={user.propertyId} />
            </div>
            <div className="space-y-5">
              <AskRentFlowSidebar propertyId={user.propertyId} />
              <MaintenanceTrendAlert propertyId={user.propertyId} />
              <ConfidenceDistribution propertyId={user.propertyId} />
            </div>
          </div>
        )}
        {activeTab === "actions" && <AIActionsPanel propertyId={user.propertyId} />}
        {activeTab === "inspections" && (
          <InspectionChecklist
            propertyId={user.propertyId}
            unitId={user.unitId || "TBD"}
            inspectorName={user.name}
          />
        )}
        {activeTab === "maintenance" && <MaintenanceTickets propertyId={user.propertyId} />}
        {activeTab === "payments" && <PaymentsPanel propertyId={user.propertyId} />}
        {activeTab === "feed" && <SocialFeed />}
        {activeTab === "ai" && <AICopilot propertyId={user.propertyId} />}
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
