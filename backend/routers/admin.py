"""
One-off admin endpoints to trigger scheduled jobs without shell access
(not available on Render's free tier). Protected by a shared secret in
the URL, not staff auth, since these are meant to be visited directly
in a browser or hit by an external scheduler (e.g. cron-job.org) rather
than called from the app itself.

/seed-demo             -> (existing) triggers demo simulation seed data
/run-maintenance-check  -> finds preventive maintenance schedules that are
                           due, creates a ticket for each, advances their
                           next due date. Safe to run repeatedly — only
                           acts on schedules that are actually due.
"""
import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException

from db import maintenance_schedules_col, tickets_col, users_col
import notifications_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


def check_key(key: str):
    expected = os.getenv("SEED_SECRET")
    if not expected:
        raise HTTPException(status_code=500, detail="SEED_SECRET is not configured")
    if key != expected:
        raise HTTPException(status_code=403, detail="Invalid key")


@router.get("/seed-demo")
async def seed_demo(key: str = ""):
    check_key(key)
    from scripts.seed_property_data import seed
    await seed()
    return {"status": "done", "message": "Simulation data seeded. Refresh the app to see it."}


@router.get("/run-maintenance-check")
async def run_maintenance_check(key: str = ""):
    check_key(key)

    now = datetime.now(timezone.utc)
    cursor = maintenance_schedules_col.find({"active": True, "nextDueDate": {"$lte": now}})
    due_schedules = await cursor.to_list(length=500)

    created = []
    for schedule in due_schedules:
        ticket = {
            "propertyId": schedule["propertyId"],
            "unitId": schedule.get("unitId"),
            "title": schedule["title"],
            "priority": "normal",
            "source": "preventive_maintenance",
            "sourceInspectionId": None,
            "room": None,
            "assignee": None,
            "category": schedule.get("category", "general"),
            "status": "open",
            "createdAt": now,
        }

        assigned_tech = await users_col.find_one({"role": "staff", "assignedProperties": schedule["propertyId"]})
        if assigned_tech:
            ticket["assignee"] = assigned_tech.get("email")

        result = await tickets_col.insert_one(ticket)
        created.append(str(result.inserted_id))

        if assigned_tech:
            await notifications_service.notify_user(
                str(assigned_tech["_id"]),
                type="general",
                title=f"Preventive maintenance due: {schedule['title']}",
                body=f"Property {schedule['propertyId']} — scheduled task now due",
                link=f"/maintenance/{str(result.inserted_id)}",
            )
        else:
            await notifications_service.notify_all_staff(
                type="general",
                title=f"Preventive maintenance due: {schedule['title']}",
                body=f"Property {schedule['propertyId']} — no tech assigned to this property yet",
                link=f"/maintenance/{str(result.inserted_id)}",
            )

        next_due = now + timedelta(days=schedule["intervalDays"])
        await maintenance_schedules_col.update_one(
            {"_id": schedule["_id"]},
            {"$set": {"lastCompletedDate": now, "nextDueDate": next_due}},
        )

    return {
        "status": "done",
        "schedulesChecked": len(due_schedules),
        "ticketsCreated": len(created),
        "ticketIds": created,
    }
