"""Check how many emails were sent today."""
from database import db
from datetime import datetime

today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

# Emails sent today from emails collection
sent_today = db["emails"].count_documents({
    "status": "sent",
    "sent_at": {"$gte": today}
})

# Also check email_drafts collection
drafts_sent = db["email_drafts"].count_documents({
    "status": "sent",
    "sent_at": {"$gte": today}
})

# Get breakdown by account
pipeline = [
    {"$match": {"status": "sent", "sent_at": {"$gte": today}}},
    {"$group": {"_id": "$from_email", "count": {"$sum": 1}}},
    {"$sort": {"count": -1}}
]
by_account = list(db["emails"].aggregate(pipeline))

# Draft queue status
draft_stats_pipeline = [
    {"$group": {"_id": "$status", "count": {"$sum": 1}}}
]
draft_stats = {r["_id"]: r["count"] for r in db["email_drafts"].aggregate(draft_stats_pipeline)}

print(f"=== Emails Sent Today (Feb 14, 2026) ===")
print(f"Emails collection: {sent_today}")
print(f"Drafts collection: {drafts_sent}")
print()

if by_account:
    print("By account:")
    for a in by_account:
        print(f"  {a['_id']}: {a['count']}")
else:
    print("No emails sent today.")

print()
print("=== Draft Queue Status ===")
if draft_stats:
    for status, count in sorted(draft_stats.items()):
        print(f"  {status}: {count}")
    print(f"  TOTAL: {sum(draft_stats.values())}")
else:
    print("  No drafts in queue.")
