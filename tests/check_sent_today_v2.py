"""Check emails sent today — both v1 and v2, accounting for timezone."""
from database import db
from datetime import datetime, timedelta

# Today in UTC
now_utc = datetime.utcnow()
today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

# ET is UTC-5, so "today in ET" started at UTC 05:00
today_et = today_utc + timedelta(hours=5)
yesterday_et_start = today_utc - timedelta(hours=19)  # Feb 13 05:00 UTC = Feb 13 00:00 ET

print(f"Current UTC: {now_utc.strftime('%Y-%m-%d %H:%M')}")
print(f"Today UTC midnight: {today_utc}")
print(f"Today ET midnight (in UTC): {yesterday_et_start}")
print()

# ── Check emails collection (used by both v1 and v2) ──
for label, since in [("Since UTC midnight", today_utc), ("Since ET midnight", yesterday_et_start)]:
    print(f"=== Emails Collection — {label} ===")
    
    # By sent_at
    sent_by_sent_at = db["emails"].count_documents({
        "status": "sent",
        "sent_at": {"$gte": since}
    })
    
    # By created_at (in case sent_at is missing)
    sent_by_created = db["emails"].count_documents({
        "status": "sent",
        "created_at": {"$gte": since}
    })
    
    print(f"  By sent_at: {sent_by_sent_at}")
    print(f"  By created_at: {sent_by_created}")
    
    # Breakdown by account
    pipeline = [
        {"$match": {"status": "sent", "sent_at": {"$gte": since}}},
        {"$group": {"_id": "$from_email", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    by_account = list(db["emails"].aggregate(pipeline))
    if by_account:
        for a in by_account:
            print(f"    {a['_id']}: {a['count']}")
    
    # Also try created_at grouping if sent_at showed 0
    if sent_by_sent_at == 0 and sent_by_created > 0:
        pipeline2 = [
            {"$match": {"status": "sent", "created_at": {"$gte": since}}},
            {"$group": {"_id": "$from_email", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        by_account2 = list(db["emails"].aggregate(pipeline2))
        if by_account2:
            print(f"  (by created_at):")
            for a in by_account2:
                print(f"    {a['_id']}: {a['count']}")
    print()

# ── Check email_drafts collection (v2 only) ──
print("=== Email Drafts Collection (v2) ===")
draft_stats_pipeline = [
    {"$group": {"_id": "$status", "count": {"$sum": 1}}}
]
draft_stats = {r["_id"]: r["count"] for r in db["email_drafts"].aggregate(draft_stats_pipeline)}
for status, count in sorted(draft_stats.items()):
    print(f"  {status}: {count}")

# ── Show last 10 sent emails (regardless of date) ──
print()
print("=== Last 10 Sent Emails ===")
last_sent = list(db["emails"].find(
    {"status": "sent"},
    {"to_email": 1, "from_email": 1, "sent_at": 1, "created_at": 1, "subject": 1}
).sort("sent_at", -1).limit(10))

if not last_sent:
    # Try sorting by created_at
    last_sent = list(db["emails"].find(
        {"status": "sent"},
        {"to_email": 1, "from_email": 1, "sent_at": 1, "created_at": 1, "subject": 1}
    ).sort("created_at", -1).limit(10))

for e in last_sent:
    sent = e.get("sent_at") or e.get("created_at") or "?"
    subj = (e.get("subject") or "")[:50]
    print(f"  {sent} | {e.get('from_email','?')} → {e.get('to_email','?')} | {subj}")

# ── Total sent all time ──
print()
total = db["emails"].count_documents({"status": "sent"})
print(f"Total emails sent (all time): {total}")
