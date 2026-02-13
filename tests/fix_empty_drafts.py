"""
Fix the 66 empty drafts created by the broken pre-generator.

The pre_generator.py was calling `generate_cold_email()` which doesn't exist
on EmailGenerator — the correct method is `generate_initial_email()`.
This caused all drafts to be created as empty placeholders (status="generating")
that never got content.

This script marks them as "failed" so the leads become eligible for retry.
"""
import sys
sys.path.insert(0, "/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails")

from database import db
from datetime import datetime

drafts_col = db["email_drafts"]

# Find all drafts that are stuck in "generating" status with no body
stuck_drafts = list(drafts_col.find({
    "status": "generating",
    "body": {"$in": [None, ""]},
}))

print(f"Found {len(stuck_drafts)} stuck empty drafts")

if not stuck_drafts:
    # Also check for "created" status (older versions may use different status)
    stuck_drafts = list(drafts_col.find({
        "body": {"$in": [None, ""]},
        "subject": {"$in": [None, ""]},
        "status": {"$nin": ["failed", "skipped", "sent", "ready_to_send"]},
    }))
    print(f"Found {len(stuck_drafts)} stuck drafts (broader search)")

if stuck_drafts:
    for d in stuck_drafts[:5]:
        print(f"  Example: {d.get('to_email')} | status={d.get('status')} | created={d.get('created_at')}")
    
    confirm = input(f"\nMark {len(stuck_drafts)} drafts as 'failed'? (y/n): ")
    if confirm.lower() == 'y':
        result = drafts_col.update_many(
            {"_id": {"$in": [d["_id"] for d in stuck_drafts]}},
            {"$set": {
                "status": "failed",
                "error": "generate_cold_email method did not exist — fixed in deploy",
                "updated_at": datetime.utcnow(),
            }}
        )
        print(f"✅ Marked {result.modified_count} drafts as failed")
        print("   These leads will be eligible for retry on next pre-gen run")
    else:
        print("Aborted")
else:
    print("✅ No stuck drafts found — nothing to fix")
