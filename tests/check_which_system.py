"""Deep check: which system sent today's emails, heartbeat, draft pipeline."""
from database import db
from datetime import datetime, timedelta

now_utc = datetime.utcnow()
today_et = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=19)

print("=== v2 Heartbeat ===")
hb = db["heartbeat"].find_one({"_id": "v2_scheduler"})
if hb:
    for k, v in hb.items():
        print(f"  {k}: {v}")
else:
    print("  No v2 heartbeat found")

print()
print("=== Drafts marked 'sent' (v2 send_worker path) ===")
sent_drafts = list(db["email_drafts"].find(
    {"status": "sent"},
    {"to_email": 1, "actual_from_email": 1, "sent_at": 1, "smtp_message_id": 1, "email_type": 1}
).sort("sent_at", -1).limit(5))
for d in sent_drafts:
    print(f"  {d.get('sent_at')} | {d.get('actual_from_email')} -> {d.get('to_email')} | {d.get('email_type')}")
print(f"  Total drafts sent: {db['email_drafts'].count_documents({'status': 'sent'})}")

print()
print("=== Last 5 emails in 'emails' collection ===")
recent = list(db["emails"].find(
    {"status": "sent"},
).sort("sent_at", -1).limit(5))
for e in recent:
    ts = e.get("sent_at") or e.get("created_at")
    subj = (e.get("subject") or "")[:40]
    etype = e.get("email_type", "?")
    print(f"  {ts} | {e.get('from_email','?')} -> {e.get('to_email','?')} | {etype} | {subj}")

print()
print("=== Today's sends by hour (ET) ===")
pipeline = [
    {"$match": {"status": "sent", "sent_at": {"$gte": today_et}}},
    {"$project": {
        "hour": {"$hour": {"$subtract": ["$sent_at", 5 * 3600 * 1000]}},
        "from_email": 1,
    }},
    {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
    {"$sort": {"_id": 1}},
]
# simpler approach - just group by hour of sent_at in UTC
pipeline2 = [
    {"$match": {"status": "sent", "sent_at": {"$gte": today_et}}},
    {"$group": {
        "_id": {"$hour": "$sent_at"},
        "count": {"$sum": 1}
    }},
    {"$sort": {"_id": 1}},
]
by_hour = list(db["emails"].aggregate(pipeline2))
for h in by_hour:
    utc_h = h["_id"]
    et_h = (utc_h - 5) % 24
    print(f"  {et_h:02d}:00 ET ({utc_h:02d}:00 UTC): {h['count']} emails")

total_today = sum(h["count"] for h in by_hour)
print(f"  TOTAL today: {total_today}")

print()
print("=== v2 Scheduler Log (last 20 lines) ===")
import os
log_path = "v2_scheduler.log"
if os.path.exists(log_path):
    with open(log_path) as f:
        lines = f.readlines()
    for line in lines[-20:]:
        print(f"  {line.rstrip()}")
else:
    print("  No v2_scheduler.log found locally (check Docker container)")
