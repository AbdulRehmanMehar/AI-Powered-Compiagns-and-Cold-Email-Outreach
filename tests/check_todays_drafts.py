#!/usr/bin/env python3
"""
Check ready_to_send drafts generated today.
Usage: python3 tests/check_todays_drafts.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from datetime import datetime, timezone, timedelta

# Today in UTC (Feb 20 2026 midnight)
now_utc = datetime.now(timezone.utc)
today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
today_end = today_start + timedelta(days=1)

collection = db["email_drafts"]

# All ready_to_send drafts created today
drafts = list(collection.find(
    {
        "status": "ready_to_send",
        "created_at": {"$gte": today_start.replace(tzinfo=None), "$lt": today_end.replace(tzinfo=None)}
    },
    {
        "to_email": 1,
        "subject": 1,
        "campaign_id": 1,
        "review_score": 1,
        "created_at": 1,
        "email_type": 1,
    }
).sort("created_at", -1))

print(f"\n{'='*60}")
print(f"  Ready-to-Send Drafts Generated Today ({now_utc.strftime('%b %d, %Y')} UTC)")
print(f"{'='*60}")
print(f"  Total: {len(drafts)}\n")

if not drafts:
    print("  No ready_to_send drafts found for today.")
else:
    # Group by campaign
    by_campaign: dict = {}
    for d in drafts:
        cid = str(d.get("campaign_id", "unknown"))
        by_campaign.setdefault(cid, []).append(d)

    # Resolve campaign names
    campaign_ids = list(by_campaign.keys())
    from bson import ObjectId
    name_map = {}
    for cid in campaign_ids:
        try:
            doc = db["campaigns"].find_one({"_id": ObjectId(cid)}, {"name": 1})
            name_map[cid] = doc["name"] if doc else cid
        except Exception:
            name_map[cid] = cid

    for cid, items in sorted(by_campaign.items(), key=lambda x: -len(x[1])):
        cname = name_map.get(cid, cid)
        print(f"  Campaign: {cname}  ({len(items)} drafts)")
        print(f"  {'-'*56}")
        for d in items:
            created = d.get("created_at")
            created_str = created.strftime("%H:%M:%S") if created else "N/A"
            score = d.get("review_score", "N/A")
            email_type = d.get("email_type", "initial")
            subject = d.get("subject", "")
            to_email = d.get("to_email", "")
            print(f"  [{created_str}] {to_email:<38} score={score:<5} type={email_type}")
            print(f"             Subject: {subject}")
        print()

# Summary counts across all statuses for today
print(f"{'='*60}")
print("  Today's Draft Status Breakdown")
print(f"{'='*60}")
statuses = ["generating", "ready_to_send", "claimed", "sent", "failed", "review_failed", "skipped"]
for status in statuses:
    count = collection.count_documents({
        "status": status,
        "created_at": {
            "$gte": today_start.replace(tzinfo=None),
            "$lt": today_end.replace(tzinfo=None)
        }
    })
    if count:
        print(f"  {status:<20}: {count}")
print()
