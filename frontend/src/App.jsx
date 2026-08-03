import { useState } from "react";
import { AuthProvider, useAuth } from "./AuthContext";
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

function AppShell() {
  const { user, loading, logout } = useAuth();
  const [tab, setTab] = useState("dashboard");

  if (loading) return <p className="p-6 text-sm text-slate-400">Loading…</p>;
  if (!user) return <LoginScreen />;

  const tabs = user.role === "staff" ? STAFF_TABS : TENANT_TABS;
  const activeTab = tabs.includes(tab) ? tab : tabs[0];

  return (
    <div className="min-h-screen bg-[#f6f3ec]">
      <header className="bg-[#14213d] text-white px-6 py-3 flex items-center justify-between">
        <h1 className="font-serif font-bold text-lg">RentFlow AI</h1>
        <div className="flex items-center gap-3 text-sm">
          <NotificationBell />
          <span>{user.name} · {user.role === "staff" ? "Staff" : `Unit ${user.unitId || "—"}`}</span>
          <button onClick={logout} className="text-xs border border-white/30 rounded px-2 py-1 hover:bg-white/10">
            Sign out
          </button>
        </div>
      </header>

      <nav className="flex gap-2 px-6 py-3">
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-sm px-3 py-1.5 rounded-full capitalize ${
              activeTab === t ? "bg-slate-900 text-white" : "bg-white border border-slate-200 text-slate-600"
            }`}
          >
            {t}
          </button>
        ))}
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
