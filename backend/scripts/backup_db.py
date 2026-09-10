"""
Standalone database backup script — genuinely missing before this.

WHY THIS EXISTS: this app's MongoDB Atlas M0 (free) tier does not
support Atlas's own built-in Cloud Backup (continuous, point-in-time
recovery) — that requires upgrading to M10 or higher (roughly
$57+/month as of this writing). For a product handling real customer
data and real payments, upgrading to M10+ before real launch is the
genuinely correct long-term answer, not a replacement for this script
- this script is a real, practical stopgap for the M0 tier, and
remains good defense-in-depth practice even after upgrading (an
independent, portable backup outside Atlas's own infrastructure).

WHAT THIS DOES: connects to the real database using this app's own
MONGO_URL, and dumps every collection to a single timestamped JSON
file, using bson.json_util so ObjectIds, datetimes, and other BSON
types round-trip correctly on restore (not just python's stdlib json,
which cannot represent these types at all).

WHAT THIS DELIBERATELY DOES NOT DO: run itself on a schedule. Render's
free tier has no persistent background-job/cron infrastructure (the
same real constraint documented in main.py's own rent_automation_scheduler
docstring). Run this manually, or set up your own scheduling - e.g.
a cron job on your own machine (pointed at MONGO_URL over the public
internet, since Atlas allows this by default) or a paid Render Cron
Job, if you want this to run automatically. Real, valuable follow-on
work, not attempted here.

Usage:
    cd backend
    python3 scripts/backup_db.py

    # Writes ./backups/propwise_backup_<timestamp>.json

    Restore with:
    python3 scripts/restore_db.py backups/propwise_backup_<timestamp>.json
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bson import json_util
from motor.motor_asyncio import AsyncIOMotorClient


async def backup(output_dir: str = "backups") -> str:
    mongo_url = os.getenv("MONGO_URL")
    db_name = os.getenv("DB_NAME", "rentflow")
    if not mongo_url:
        print("ERROR: MONGO_URL is not set in the environment. Set it (e.g. `export MONGO_URL=...` "
              "or run this with your real .env loaded) before running a backup.")
        sys.exit(1)

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    collection_names = await db.list_collection_names()
    if not collection_names:
        print(f"WARNING: database '{db_name}' has no collections at all. "
              "Double-check MONGO_URL/DB_NAME point at the real production database "
              "before trusting this as a real backup.")

    dump = {}
    total_docs = 0
    for name in collection_names:
        docs = await db[name].find({}).to_list(length=None)
        dump[name] = docs
        total_docs += len(docs)
        print(f"  {name}: {len(docs)} documents")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = Path(output_dir) / f"propwise_backup_{timestamp}.json"

    with open(output_path, "w") as f:
        # json_util.dumps (not plain json.dumps) is what correctly
        # preserves ObjectId, datetime, and other real BSON types as
        # a real, restorable representation - plain json would either
        # crash on these types or silently stringify them in a way
        # restore_db.py could not reliably reverse.
        f.write(json_util.dumps({"dbName": db_name, "backedUpAt": timestamp, "collections": dump}, indent=2))

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\nBackup complete: {output_path} ({total_docs} total documents, {size_mb:.1f} MB)")
    print("Store this file somewhere durable and OFF this machine (e.g. encrypted cloud storage) - "
          "a backup that lives only on the same machine as the database it backs up protects against "
          "far fewer real failure scenarios.")

    client.close()
    return str(output_path)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(backup())
