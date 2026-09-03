"""
Lightweight scheduler resilience check — genuinely useful without the
cost/complexity of a full Celery + Redis migration (a real, larger
architectural change deliberately deferred until this app is closer
to production traffic, not because it isn't a real improvement).

What this actually does: each scheduler loop (main.py's
rent_automation_scheduler, vendor_sla_scheduler) records a real
heartbeat timestamp in MongoDB after every completed cycle. At
startup, before a scheduler's very first cycle runs, this checks
whether the previous heartbeat is older than expected given that
scheduler's own interval — if Render restarted the app mid-cycle (a
deploy, a crash, a free-tier spin-down), the gap between "when it
should have run again" and "right now" will be visibly larger than
one normal interval, and that fact gets logged clearly rather than
silently disappearing into a fresh, uneventful-looking startup.

What this does NOT do: it doesn't prevent a missed cycle (that's what
Celery + Redis's persistent task queue would actually solve), and it
doesn't retroactively run whatever was missed. Every check these
schedulers call was already built to be safe to skip a cycle and
catch up next time (idempotent, re-checks real current state rather
than assuming a fixed schedule was followed) — this module's whole
job is just making a missed cycle VISIBLE, not silent, so it's a real
signal if it starts happening often enough to justify the bigger
migration.
"""
from datetime import datetime, timezone

from db import scheduler_health_col


async def record_heartbeat(scheduler_name: str):
    await scheduler_health_col.update_one(
        {"scheduler": scheduler_name},
        {"$set": {"lastHeartbeatAt": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def check_for_missed_cycle(scheduler_name: str, expected_interval_seconds: int, logger) -> None:
    """Called once, right before a scheduler's first cycle at startup.
    A gap of more than 1.5x the expected interval since the last
    recorded heartbeat is the real signal something was missed — some
    slack is intentional, since a normal deploy (a minute or two of
    downtime) shouldn't itself trigger a false alarm."""
    doc = await scheduler_health_col.find_one({"scheduler": scheduler_name})
    if not doc or not doc.get("lastHeartbeatAt"):
        logger.info(
            f"[scheduler-health] {scheduler_name}: no prior heartbeat on record — "
            f"first run since this app was created, or since this check was added."
        )
        return

    last_run = doc["lastHeartbeatAt"]
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    gap_seconds = (now - last_run).total_seconds()

    if gap_seconds > expected_interval_seconds * 1.5:
        gap_hours = round(gap_seconds / 3600, 1)
        logger.warning(
            f"[scheduler-health] {scheduler_name}: last heartbeat was {gap_hours}h ago, "
            f"longer than the expected ~{expected_interval_seconds / 3600:.1f}h interval — "
            f"this app was very likely restarted (deploy, crash, or free-tier spin-down) and "
            f"skipped at least one cycle. Every check this scheduler runs is safe to have "
            f"skipped (each re-checks real current state, not a fixed schedule), so nothing "
            f"needs manual recovery — this is logged only so a pattern of frequent restarts "
            f"would actually be visible."
        )
    else:
        logger.info(f"[scheduler-health] {scheduler_name}: last heartbeat {round(gap_seconds / 60)} min ago — normal.")
