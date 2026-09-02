function formatDuration(ms) {
  if (ms == null) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

const STATUS_COLOR = {
  success: { bar: "bg-emerald-400", text: "text-emerald-950", border: "border-emerald-500" },
  failed: { bar: "bg-rose-400", text: "text-rose-950", border: "border-rose-500" },
  skipped: { bar: "bg-slate-300", text: "text-slate-600", border: "border-slate-400" },
};

function actionDisplayName(type) {
  const names = {
    send_email: "send_email()",
    create_task: "create_task()",
    create_turnover_checklist: "create_turnover_checklist()",
    assign_user: "assign_user()",
    route_to_team: "route_to_team()",
    set_status: "set_status()",
    webhook: "webhook()",
  };
  return names[type] || `${type}()`;
}

/**
 * Renders one real workflow run as a nested execution timeline — a
 * trigger "parent" bar with each of its actions chained underneath as
 * sequential child bars, styled directly after Render's own Workflows
 * documentation (colored horizontal bars sized to real duration,
 * L-shaped connector lines, a duration label on the right of each
 * bar). Every number shown is real, measured data from this run's own
 * `steps` array (see services/events.py's execute_workflow) — nothing
 * here is decorative or estimated. Bar width is proportional to the
 * longest step in this run, with a minimum floor so a near-instant
 * step (a few ms) still renders as a visible sliver rather than
 * disappearing.
 */
export default function WorkflowRunFlow({ run }) {
  if (!run) return null;
  const steps = run.steps || [];
  const totalMs = run.startedAt && run.finishedAt
    ? new Date(run.finishedAt).getTime() - new Date(run.startedAt).getTime()
    : null;
  const maxStepMs = Math.max(1, ...steps.map((s) => s.durationMs || 0));
  const MIN_WIDTH_PCT = 8;

  return (
    <div className="bg-slate-900 rounded-lg p-4 font-mono text-xs overflow-x-auto">
      {/* Parent bar — the trigger event that started this run */}
      <div className="flex items-center gap-2 mb-1">
        <span className="text-indigo-400">→</span>
        <div className="flex-1 bg-indigo-500 text-indigo-950 rounded px-3 py-1.5 flex items-center justify-between min-w-[200px]">
          <span className="font-bold">{run.triggerEvent}()</span>
          <span className="opacity-70">{totalMs != null ? formatDuration(totalMs) : "—"}</span>
        </div>
      </div>

      {/* Sequential child bars — this workflow's actions, in order, each
          connected to the one above via an L-shaped line (a vertical
          rule down the left edge + a short horizontal branch into the
          bar), matching the chained-steps pattern shown throughout the
          Render Workflows docs. */}
      <div className="pl-4 border-l-2 border-indigo-400/40 ml-2.5 space-y-1 pt-1">
        {steps.length === 0 && (
          <p className="text-slate-500 pl-3 py-1">No steps recorded for this run.</p>
        )}
        {steps.map((step, i) => {
          const colors = STATUS_COLOR[step.status] || STATUS_COLOR.skipped;
          const widthPct = step.durationMs
            ? Math.max(MIN_WIDTH_PCT, Math.round((step.durationMs / maxStepMs) * 100))
            : MIN_WIDTH_PCT;
          return (
            <div key={i} className="flex items-center gap-2 relative">
              <span className="text-indigo-400/70 -ml-4">↳</span>
              <div
                className={`${colors.bar} ${colors.text} rounded px-2.5 py-1 flex items-center justify-between border ${colors.border}`}
                style={{ width: `${widthPct}%`, minWidth: "140px" }}
                title={step.status === "failed" ? step.error : undefined}
              >
                <span className="font-semibold truncate">{actionDisplayName(step.action)}</span>
                <span className="opacity-70 ml-2 shrink-0">{formatDuration(step.durationMs)}</span>
              </div>
              {step.status === "failed" && (
                <span className="text-rose-400 text-[10px] truncate max-w-[300px]">✕ {step.error}</span>
              )}
              {step.status === "skipped" && (
                <span className="text-slate-500 text-[10px]">skipped — no handler registered</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
