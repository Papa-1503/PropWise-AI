"""
Shared date parsing helper.

BUG THIS FIXES (found by actually running the app): datetime.fromisoformat()
on a date-only string like "2026-07-01" returns a timezone-NAIVE datetime.
Everywhere else in this codebase uses datetime.now(timezone.utc), which is
timezone-AWARE. Comparing a naive and an aware datetime directly raises
TypeError in Python — this crashed payments.py's compute_status() the
first time it was actually exercised. Route every ISO date string parsed
from user input through this function instead of calling
datetime.fromisoformat() directly, so this class of bug can't recur.

SECOND BUG THIS FIXES (found in a later live-testing pass): a malformed
date string (e.g. "not-a-date") made datetime.fromisoformat() raise an
uncaught ValueError, which FastAPI turned into a raw 500 with a full
stack trace instead of a clean validation error. This function now
catches that and raises a proper HTTPException(400) instead.
"""
from datetime import datetime, timezone
from fastapi import HTTPException


def parse_date_utc(value: str) -> datetime:
    """Parses an ISO date or datetime string into a timezone-AWARE UTC datetime.
    If the input has no timezone info, it's assumed to already be UTC.
    Raises HTTPException(400) on an unparseable string rather than letting
    a raw ValueError surface as an unhandled 500."""
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid date format: {value!r}. Expected ISO format, e.g. '2026-08-01'.")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
