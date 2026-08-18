import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";
import AffirmationBanner from "./AffirmationBanner";

/**
 * Dashboard
 *
 * Pulls real aggregate numbers from GET /api/dashboard/stats — nothing
 * hardcoded. Pair with MaintenanceTickets / InspectionChecklist / AICopilot
 * for the full flow.
 */

const TONE_STYLES = {
  up: { from: "#10b981", to: "#34d399", text: "text-emerald-600", icon: "↑" },
  down: { from: "#f43f5e", to: "#fb7185", text: "text-rose-600", icon: "↓" },
  neutral: { from: "#0ea5e9", to: "#38bdf8", text: "text-sky-500", icon: "•" },
};

function StatCard({ label, value, hint, tone = "neutral" }) {
  const style = TONE_STYLES[tone];
  return (
    <div
      className="stat-card-accent flex-1 min-w-[150px] bg-white border border-slate-200 rounded-xl p-4 shadow-soft hover:shadow-softHover transition-all duration-200"
      style={{ "--accent-from": style.from, "--accent-to": style.to }}
    >
      <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400">{label}</div>
      <div className="text-2xl font-semibold mt-1.5 text-slate-800">{value}</div>
