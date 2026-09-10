"""
Restores a database dump created by backup_db.py. A backup that has
never actually been tested to restore is not a real backup - this is
the genuine, matching other half, not an afterthought.

SAFETY: this is a real, destructive operation on whichever database
MONGO_URL points at - it replaces (not merges) each collection found
in the backup file. Requires a real, explicit --yes-i-am-sure flag; it
will not run from just providing a backup file path, specifically so
it can never be run accidentally against a live production database by
someone who meant to point it at a staging/local one.

Usage:
    cd backend
    python3 scripts/restore_db.py backups/propwise_backup_<timestamp>.json --yes-i-am-sure

    # Restores into whatever MONGO_URL/DB_NAME currently point at -
    # double check those before running this for real.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bson import json_util
from motor.motor_asyncio import AsyncIOMotorClient


async def restore(backup_path: str) -> None:
    mongo_url = os.getenv("MONGO_URL")
    db_name = os.getenv("DB_NAME", "rentflow")
    if not mongo_url:
        print("ERROR: MONGO_URL is not set in the environment.")
        sys.exit(1)

    path = Path(backup_path)
    if not path.exists():
        print(f"ERROR: backup file not found: {backup_path}")
        sys.exit(1)

    with open(path) as f:
        data = json_util.loads(f.read())

    backed_up_at = data.get("backedUpAt", "unknown time")
    collections = data.get("collections", {})
    if not collections:
        print("ERROR: this backup file has no collections in it - refusing to restore an empty/malformed backup.")
        sys.exit(1)

    print(f"About to restore a backup taken at {backed_up_at} into database "
          f"'{db_name}' at {mongo_url.split('@')[-1] if '@' in mongo_url else mongo_url}")
    print(f"This will REPLACE {len(collections)} collection(s): {', '.join(collections.keys())}")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    for name, docs in collections.items():
        await db[name].delete_many({})
        if docs:
            await db[name].insert_many(docs)
        print(f"  {name}: restored {len(docs)} documents")

    print(f"\nRestore complete into database '{db_name}'.")
    client.close()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    if len(sys.argv) < 3 or sys.argv[2] != "--yes-i-am-sure":
        print(__doc__)
        print("\nRefusing to run without the explicit --yes-i-am-sure flag, since this "
              "is a real, destructive operation on whichever database MONGO_URL currently points at.")
        sys.exit(1)

    asyncio.run(restore(sys.argv[1]))
