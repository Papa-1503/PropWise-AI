import { useState, useEffect, useCallback } from "react";

/**
 * Onboarding tour — staff-only, since staff have the genuinely more
 * complex UI (sidebar, building switching, command palette) worth a
 * short walkthrough; tenants' 5-tab experience is largely
 * self-explanatory without one. Modeled on the shared design's
 * onboarding-tooltip concept, which only showed the positioning CSS
 * (a colored box with an arrow) with no actual step content or trigger
 * logic — the flow itself (which steps, when it shows, how it's
 * dismissed, persistence) is new, not something to imitate since
 * nothing concrete existed to imitate there.
 *
 * Targets real DOM elements via data-onboarding-target="<step id>"
 * attributes placed on the actual elements being introduced, computing
 * position live via getBoundingClientRect() rather than hardcoded
 * coordinates — so it stays correct if layout ever shifts.
 */

const STORAGE_KEY = "rentflow_onboarding_complete";

const STEPS = [
  {
    target: "sidebar-nav",
    title: "Everything lives here",
    body: "All your tools are listed in the sidebar — no more hunting through a hidden \"More\" menu.",
  },
  {
    target: "building-selector",
    title: "Switch properties anytime",
    body: "Most pages scope to whichever building is selected here. Pick \"All Buildings\" to see everything at once.",
  },
  {
    target: "search-button",
    title: "Find anything fast",
    body: "Search leases, tickets, and leads from anywhere — tap this, or press Ctrl+K on a keyboard.",
  },
  {
    target: "dark-mode-toggle",
    title: "Easier on the eyes",
    body: "Switch to a dark theme anytime — it's remembered for next time too.",
  },
];

export default function OnboardingTour({ active }) {
  const [stepIndex, setStepIndex] = useState(0);
  const [rect, setRect] = useState(null);
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "true";
    } catch {
      return false;
    }
  });

  const step = STEPS[stepIndex];

  const measure = useCallback(() => {
    if (!step) return;
    const el = document.querySelector(`[data-onboarding-target="${step.target}"]`);
    // A CSS-hidden element (e.g. the desktop sidebar on a mobile
    // viewport, via Tailwind's `hidden lg:flex`) still exists in the
    // DOM and still returns a rect from getBoundingClientRect() — just
    // one with all-zero dimensions, not null. Checking for real size
    // is what actually distinguishes "found but invisible" from
    // "found and on screen".
    if (el) {
      const r = el.getBoundingClientRect();
      setRect(r.width > 0 && r.height > 0 ? r : null);
    } else {
      setRect(null);
    }
  }, [step]);

  useEffect(() => {
    if (!active || dismissed) return;
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [active, dismissed, stepIndex, measure]);

  function finish() {
    setDismissed(true);
    try {
      localStorage.setItem(STORAGE_KEY, "true");
    } catch {
      // persistence is a nicety here, not required for the tour to work this session
    }
  }

  if (!active || dismissed || !step) return null;

  // If the target element genuinely isn't on screen right now (e.g. the
  // mobile sidebar is collapsed), skip straight past this step rather
  // than show a tooltip pointing at nothing.
  if (!rect) {
    if (stepIndex < STEPS.length - 1) {
      setTimeout(() => setStepIndex((i) => i + 1), 0);
    } else {
      setTimeout(finish, 0);
    }
    return null;
  }

  const tooltipTop = rect.bottom + 10;
  const tooltipLeft = Math.min(Math.max(rect.left, 12), window.innerWidth - 300);

  return (
    <div className="fixed inset-0 z-[120]" role="dialog" aria-label="Onboarding tour">
      <div className="absolute inset-0 bg-slate-900/50" />
      <div
        className="absolute border-2 border-white rounded-lg pointer-events-none"
        style={{
          top: rect.top - 4,
          left: rect.left - 4,
          width: rect.width + 8,
          height: rect.height + 8,
          boxShadow: "0 0 0 4000px rgba(15, 23, 42, 0.5)",
        }}
      />
      <div
        className="absolute bg-white rounded-xl shadow-2xl p-4 w-72"
        style={{ top: tooltipTop, left: tooltipLeft }}
      >
        <p className="text-sm font-semibold text-slate-800 mb-1">{step.title}</p>
        <p className="text-xs text-slate-500 mb-3">{step.body}</p>
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-slate-400">{stepIndex + 1} of {STEPS.length}</span>
          <div className="flex gap-2">
            <button onClick={finish} className="text-xs text-slate-400 hover:text-slate-600">
              Skip
            </button>
            <button
              onClick={() => (stepIndex < STEPS.length - 1 ? setStepIndex((i) => i + 1) : finish())}
              className="text-xs font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg"
            >
              {stepIndex < STEPS.length - 1 ? "Next" : "Got it"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
