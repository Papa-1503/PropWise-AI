import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation, Outlet, useOutletContext } from "react-router-dom";
import { useState, lazy, Suspense } from "react";
import { LayoutDashboard, Zap, ClipboardCheck, Wrench, DollarSign, Rss, Sparkles, FileText, Image, GitBranch, MessageSquare, FileSignature, UserSearch, UserPlus2, Users, CalendarClock, Landmark, Building2, Menu, Moon, Sun, Search, PhoneCall, ClipboardList, Package } from "lucide-react";
import { AuthProvider, useAuth } from "./AuthContext";
import { ToastProvider } from "./ToastContext";
import { DarkModeProvider, useDarkMode } from "./DarkModeContext";
import Avatar from "./Avatar";
import LeadCaptureForm from "./LeadCaptureForm";
import Documents from "./Documents";
import Gallery from "./Gallery";
import LoginScreen from "./LoginScreen";
import RecentActivity from "./RecentActivity";
import CommandPalette from "./CommandPalette";
import Settings from "./Settings";
import OnboardingTour from "./OnboardingTour";
import WelcomeScreen from "./WelcomeScreen";
import InstallBanner from "./InstallBanner";
import PushSetup from "./PushSetup";
const Dashboard = lazy(() => import("./Dashboard"));
import MaintenanceTickets from "./MaintenanceTickets";
import InspectionsList from "./InspectionsList";
import AICopilot from "./AICopilot";
import AIActionsPanel from "./AIActionsPanel";
import PaymentsPanel from "./PaymentsPanel";
import PortfolioHealthHeader from "./PortfolioHealthHeader";
import AIWorkforcePanel from "./AIWorkforcePanel";
import OccupancyInsight from "./OccupancyInsight";
import AskPropWiseSidebar from "./AskPropWiseSidebar";
import ConfidenceDistribution from "./ConfidenceDistribution";
import MaintenanceTrendAlert from "./MaintenanceTrendAlert";
import SocialFeed from "./SocialFeed";
import NotificationBell from "./NotificationBell";
import Workflows from "./Workflows";
import FormLibrary from "./FormLibrary";
import Packages from "./Packages";
import CommunicationsPanel from "./CommunicationsPanel";
import LeasesList from "./LeasesList";
import ScreeningList from "./ScreeningList";
import LeadsList from "./LeadsList";
import StaffAssignments from "./StaffAssignments";
import MaintenanceSchedules from "./MaintenanceSchedules";
import OnCall from "./OnCall";
import Reconciliation from "./Reconciliation";
import PropertyManagement from "./PropertyManagement";
import BuildingSelector from "./BuildingSelector";
import OwnerPortal from "./OwnerPortal";
import NotFound from "./NotFound";

/** Simpler 404 for an unmatched path *within* the already-authenticated
 * app shell — the real header/nav are already showing via AppGate, so
 * this doesn't repeat the full standalone NotFound page's own title. */
function TabNotFound() {
  return (
    <div className="text-center py-16">
      <p className="text-slate-500">We couldn't find that page.</p>
    </div>
  );
}

/**
 * App
 *
 * CHANGED Aug 25, 2026: real URL-based routing (React Router).
 *
 * CORRECTED same day: the first version had AppShell call its own
 * independent <Routes> nested inside a wildcard parent route
 * ("descendant routes"). That structure had a real, confirmed bug —
 * unmatched paths like /app/nonsense rendered the Dashboard route
 * instead of the catch-all NotFound route. Rather than patch around a
 * subtlety I couldn't fully diagnose without a live browser, rebuilt
 * using React Router's officially recommended pattern instead: real
 * nested <Route> children at the top level, with the layout
 * (header/nav) rendering its children via <Outlet />. This avoids the
 * whole class of bug the previous structure had.
 *
 * Auth handling: the /app parent route always renders AppGate, which
 * checks auth and either shows LoginScreen or the real layout — at the
 * SAME url the person was trying to reach, so after logging in they
 * land exactly where they were headed, no separate redirect needed.
 *
 * Building context: staff can see every property, and several buildings
 * can share the same unit numbers (e.g. multiple "Unit 101"s across the
 * portfolio), so which building is "active" matters. Staff pick a
 * building via BuildingSelector in the header; every panel below is
 * scoped to that selection via effectivePropertyId. Picking "All
 * Buildings" (selectedProperty = null) shows the portfolio-wide
 * aggregate view. Tenants don't see the selector — always scoped to
 * their own unit's property.
 */

const STAFF_TABS = ["dashboard", "actions", "inspections", "maintenance", "payments", "workflows", "communications", "leases", "screening", "leads", "staff", "schedules", "on-call", "reconciliation", "properties", "documents", "gallery", "feed", "ai", "forms", "packages"];
const TENANT_TABS = ["documents", "maintenance", "payments", "gallery", "ai"];
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
  leads: UserPlus2,
  staff: Users,
  schedules: CalendarClock,
  "on-call": PhoneCall,
  reconciliation: Landmark,
  properties: Building2,
  forms: ClipboardList,
  packages: Package,
};

/** Auth gate + layout for everything under /app. Renders LoginScreen
 * (at the same URL) if not authenticated, the separate OwnerPortal
 * shell for owners, or the staff/tenant header+nav+Outlet layout. */
/** Redirects to the current user's own first tab, not a hardcoded one —
 * the original bug: this was <Navigate to="dashboard" replace /> always,
 * regardless of role. For a tenant (whose tabs don't include "dashboard"
 * at all), that silently sent them to a staff-only page. */
function IndexRedirect() {
  const { user } = useAuth();
  const tabs = user?.role === "staff" ? STAFF_TABS : TENANT_TABS;
  return <Navigate to={tabs[0]} replace />;
}

// A plain <Navigate to="/app/dashboard"> drops the query string entirely
// on redirect (confirmed real bug: ?resetOnboarding on the root path
// silently vanished before OnboardingTour ever saw it, since react-
// router-dom's Navigate does not forward location.search by default).
// This preserves it, so debugging aids like ?resetOnboarding — and any
// other query param someone might rely on hitting "/" with — actually
// survive the redirect to /app/dashboard.
function RootRedirect() {
  const location = useLocation();
  return <Navigate to={`/app/dashboard${location.search}`} replace />;
}

function AppGate() {
  const { user, loading, logout, selectedProperty } = useAuth();
  const { dark, toggle: toggleDarkMode } = useDarkMode();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  if (loading) return <p className="p-6 text-sm text-slate-400">Loading…</p>;
  if (!user) return <LoginScreen />;
  if (user.role === "owner") return <OwnerPortal user={user} logout={logout} />;

  const tabs = user.role === "staff" ? STAFF_TABS : TENANT_TABS;
  const currentSegment = location.pathname.replace(/^\/app\/?/, "");
  const activeTab = tabs.includes(currentSegment) ? currentSegment : null;

  // Guard against a wrong-role path — e.g. a tenant with a stale
  // bookmark/browser-history entry pointing at a staff-only tab like
  // /app/leases. Any recognized tab name that isn't in THIS user's own
  // allowed list gets redirected, rather than rendering that content —
  // this is the real fix for the bug where a tenant briefly saw the
  // staff-only Leases page. The ALL_TABS check below distinguishes "a
  // real tab that just isn't yours" from "a genuinely unknown path",
  // which should still fall through to TabNotFound instead.
  const allKnownTabs = [...new Set([...STAFF_TABS, ...TENANT_TABS])];
  if (currentSegment && allKnownTabs.includes(currentSegment) && !tabs.includes(currentSegment)) {
    return <Navigate to={`/app/${tabs[0]}`} replace />;
  }
  const effectivePropertyId = user.role === "staff" ? (selectedProperty?.id || null) : user.propertyId;

  const goTo = (t) => {
    navigate(`/app/${t}`);
    setMobileNavOpen(false);
  };

  const sidebarContent = (
    <>
      <div className="flex items-center gap-3 h-16 px-5 border-b border-slate-200">
        <div className="w-8 h-8 bg-gradient-to-br from-indigo-600 to-fuchsia-600 rounded-lg flex items-center justify-center shrink-0">
          <span className="text-white font-bold text-sm">R</span>
        </div>
        <span className="font-serif font-bold text-slate-900 truncate">PropWise AI</span>
      </div>
      <nav data-onboarding-target="sidebar-nav" className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        {tabs.map((t) => {
          const Icon = TAB_ICONS[t];
          return (
            <button
              key={t}
              onClick={() => goTo(t)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium capitalize transition-colors ${
                activeTab === t ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              {Icon && <Icon size={17} />}
              {t}
            </button>
          );
        })}
      </nav>
      <div className="p-3 border-t border-slate-200">
        <button
          onClick={() => goTo("settings")}
          className="w-full flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-slate-50 text-left"
        >
          <Avatar name={user.name} size={30} />
          <div className="min-w-0">
            <p className="text-sm font-medium text-slate-800 truncate">{user.name}</p>
            <p className="text-xs text-slate-500 truncate">{user.role === "staff" ? "Staff" : `Unit ${user.unitId || "—"}`}</p>
          </div>
        </button>
        <button
          data-onboarding-target="dark-mode-toggle"
          onClick={toggleDarkMode}
          className="w-full flex items-center gap-2 text-left text-xs text-slate-500 hover:text-slate-800 px-2 py-1.5 mt-1"
        >
          {dark ? <Sun size={13} /> : <Moon size={13} />}
          {dark ? "Light mode" : "Dark mode"}
        </button>
        <button
          onClick={logout}
          className="w-full text-left text-xs text-slate-500 hover:text-slate-800 px-2 py-1.5"
        >
          Sign out
        </button>
      </div>
    </>
  );

  return (
    <div className="min-h-screen app-bg lg:flex">
      <CommandPalette propertyId={effectivePropertyId} open={paletteOpen} onOpenChange={setPaletteOpen} />
      <OnboardingTour active={user.role === "staff"} />
      {user.role === "tenant" && <WelcomeScreen userName={user.name} />}
      <PushSetup />
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-white focus:text-slate-900 focus:px-3 focus:py-2 focus:rounded-md focus:shadow-lg"
      >
        Skip to main content
      </a>

      {/* Mobile sidebar overlay */}
      {mobileNavOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="fixed inset-0 bg-slate-900/60" onClick={() => setMobileNavOpen(false)} />
          <div className="fixed inset-y-0 left-0 w-64 bg-white shadow-xl flex flex-col">{sidebarContent}</div>
        </div>
      )}

      {/* Desktop sidebar */}
      <aside className="hidden lg:flex lg:flex-col lg:w-60 lg:shrink-0 bg-white border-r border-slate-200 lg:sticky lg:top-0 lg:h-screen">
        {sidebarContent}
      </aside>

      <div className="w-full flex-1 min-w-0">
        <header className="bg-gradient-to-r from-indigo-600 via-violet-600 to-fuchsia-600 text-white px-4 lg:px-6 py-3 flex items-center justify-between gap-2 flex-wrap shadow-md">
          <div className="flex items-center gap-3 min-w-0">
            <button onClick={() => setMobileNavOpen(true)} className="lg:hidden p-1.5 -ml-1.5 rounded hover:bg-white/10 shrink-0">
              <Menu size={20} />
            </button>
            <span className="font-serif font-bold text-lg lg:hidden truncate">PropWise AI</span>
          </div>
          <div className="flex items-center gap-2 text-sm shrink-0">
            {user.role === "staff" && <BuildingSelector />}
            {user.role === "staff" && (
              <button
                data-onboarding-target="search-button"
                onClick={() => setPaletteOpen(true)}
                className="flex items-center gap-1.5 text-xs bg-white/10 hover:bg-white/20 text-white border border-white/25 rounded-full px-3 py-1.5 shrink-0"
              >
                <Search size={13} />
                <span className="hidden md:inline">Search</span>
                <kbd className="hidden md:inline border border-white/30 rounded px-1 py-0.5 text-[10px]">Ctrl K</kbd>
              </button>
            )}
            <NotificationBell />
          </div>
        </header>

        <main id="main-content" tabIndex={-1} className="px-4 lg:px-6 pb-10 pt-3">
          <Outlet context={{ effectivePropertyId, userName: user.name }} />
        </main>
      </div>
    </div>
  );
}

function DashboardTab({ effectivePropertyId, userName }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5">
      <div className="space-y-5">
        <PortfolioHealthHeader propertyId={effectivePropertyId} userName={userName} />
        <Suspense fallback={<div className="h-40 bg-slate-100 rounded-xl animate-pulse" />}>
          <Dashboard propertyId={effectivePropertyId} />
        </Suspense>
        <OccupancyInsight propertyId={effectivePropertyId} />
        <AIWorkforcePanel propertyId={effectivePropertyId} />
      </div>
      <div className="space-y-5">
        <AskPropWiseSidebar propertyId={effectivePropertyId} />
        <RecentActivity propertyId={effectivePropertyId} />
        <MaintenanceTrendAlert propertyId={effectivePropertyId} />
        <ConfidenceDistribution propertyId={effectivePropertyId} />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <DarkModeProvider>
        <AuthProvider>
          <InstallBanner />
          <BrowserRouter>
            <Routes>
              <Route path="/apply" element={<LeadCaptureForm />} />
              <Route path="/" element={<RootRedirect />} />

          <Route path="/app" element={<AppGate />}>
            <Route index element={<IndexRedirect />} />
            <Route path="dashboard" element={<DashboardTabWrapper />} />
            <Route path="actions" element={<AIActionsPanelWrapper />} />
            <Route path="inspections" element={<InspectionsListWrapper />} />
            <Route path="maintenance" element={<MaintenanceTicketsWrapper />} />
            <Route path="payments" element={<PaymentsPanelWrapper />} />
            <Route path="workflows" element={<Workflows />} />
            <Route path="forms" element={<FormLibrary />} />
            <Route path="packages" element={<PackagesWrapper />} />
            <Route path="communications" element={<CommunicationsPanelWrapper />} />
            <Route path="leases" element={<LeasesListWrapper />} />
            <Route path="screening" element={<ScreeningListWrapper />} />
            <Route path="leads" element={<LeadsListWrapper />} />
            <Route path="staff" element={<StaffAssignments />} />
            <Route path="schedules" element={<MaintenanceSchedulesWrapper />} />
            <Route path="on-call" element={<OnCallWrapper />} />
            <Route path="reconciliation" element={<ReconciliationWrapper />} />
            <Route path="properties" element={<PropertyManagement />} />
            <Route path="documents" element={<Documents />} />
            <Route path="gallery" element={<GalleryWrapper />} />
            <Route path="settings" element={<Settings />} />
            <Route path="feed" element={<SocialFeed />} />
            <Route path="ai" element={<AICopilotWrapper />} />
            <Route path="*" element={<TabNotFound />} />
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
      </AuthProvider>
      </DarkModeProvider>
    </ToastProvider>
  );
}

// Small wrapper components pull effectivePropertyId/userName from the
// Outlet context set by AppGate, so each panel below keeps the exact
// same props/behavior it already had — only how it's reached changed.

function DashboardTabWrapper() {
  const { effectivePropertyId, userName } = useOutletContext();
  return <DashboardTab effectivePropertyId={effectivePropertyId} userName={userName} />;
}
function AIActionsPanelWrapper() {
  const { effectivePropertyId } = useOutletContext();
  return <AIActionsPanel propertyId={effectivePropertyId} />;
}
function InspectionsListWrapper() {
  const { effectivePropertyId, userName } = useOutletContext();
  return <InspectionsList propertyId={effectivePropertyId} inspectorName={userName} />;
}
function MaintenanceTicketsWrapper() {
  const { effectivePropertyId } = useOutletContext();
  return <MaintenanceTickets propertyId={effectivePropertyId} />;
}
function PackagesWrapper() {
  const { effectivePropertyId } = useOutletContext();
  return <Packages propertyId={effectivePropertyId} />;
}
function PaymentsPanelWrapper() {
  const { effectivePropertyId } = useOutletContext();
  return <PaymentsPanel propertyId={effectivePropertyId} />;
}
function CommunicationsPanelWrapper() {
  const { effectivePropertyId } = useOutletContext();
  return <CommunicationsPanel propertyId={effectivePropertyId} />;
}
function LeasesListWrapper() {
  const { effectivePropertyId } = useOutletContext();
  return <LeasesList propertyId={effectivePropertyId} />;
}
function ScreeningListWrapper() {
  const { effectivePropertyId } = useOutletContext();
  return <ScreeningList propertyId={effectivePropertyId} />;
}
function LeadsListWrapper() {
  const { effectivePropertyId } = useOutletContext();
  return <LeadsList propertyId={effectivePropertyId} />;
}
function GalleryWrapper() {
  const { effectivePropertyId } = useOutletContext();
  return <Gallery propertyId={effectivePropertyId} />;
}
function MaintenanceSchedulesWrapper() {
  const { effectivePropertyId } = useOutletContext();
  return <MaintenanceSchedules propertyId={effectivePropertyId} />;
}
function OnCallWrapper() {
  const { effectivePropertyId } = useOutletContext();
  return <OnCall propertyId={effectivePropertyId} />;
}
function ReconciliationWrapper() {
  const { effectivePropertyId } = useOutletContext();
  return <Reconciliation propertyId={effectivePropertyId} />;
}
function AICopilotWrapper() {
  const { effectivePropertyId } = useOutletContext();
  return <AICopilot propertyId={effectivePropertyId} />;
}
