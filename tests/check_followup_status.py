#!/usr/bin/env python3
"""Check the follow-up email status across all campaigns"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import *
from bson import ObjectId
from datetime import datetime, timedelta
import config

print("=" * 70)
print("FOLLOW-UP STATUS DIAGNOSTIC")
print("=" * 70)

# 1. Check total emails and their statuses
print("\n📊 EMAIL STATUS OVERVIEW:")
statuses = emails_collection.aggregate([
    {"$group": {"_id": "$status", "count": {"$sum": 1}}}
])
for s in statuses:
    print(f"   {s['_id']}: {s['count']}")

# 2. Check how many emails have message_id
total = emails_collection.count_documents({"status": "sent"})
with_msgid = emails_collection.count_documents({"status": "sent", "message_id": {"$exists": True, "$ne": None}})
without_msgid = total - with_msgid
print(f"\n📧 SENT EMAILS:")
print(f"   Total sent: {total}")
print(f"   With message_id (threadable): {with_msgid}")
print(f"   Without message_id (pre-threading): {without_msgid}")

# 3. Check follow-up candidates
print(f"\n📋 FOLLOW-UP CONFIG:")
print(f"   FOLLOWUP_DELAY_DAYS: {config.FOLLOWUP_DELAY_DAYS}")
print(f"   MAX_FOLLOWUPS: {config.MAX_FOLLOWUPS}")

cutoff = datetime.utcnow() - timedelta(days=config.FOLLOWUP_DELAY_DAYS)
print(f"   Cutoff date: {cutoff.strftime('%Y-%m-%d %H:%M')} UTC")

# 4. Run the actual pending followups query for each campaign
active_campaigns = list(campaigns_collection.find({"status": {"$in": ["active", "running", "draft"]}}))
print(f"\n📁 ACTIVE CAMPAIGNS: {len(active_campaigns)}")

for camp in active_campaigns:
    camp_id = str(camp["_id"])
    camp_name = camp.get("name", "Unknown")
    print(f"\n   Campaign: {camp_name} (status: {camp.get('status')})")
    
    # Count sent emails in this campaign
    sent_in_camp = emails_collection.count_documents({
        "campaign_id": camp["_id"],
        "status": "sent"
    })
    print(f"   Sent emails: {sent_in_camp}")
    
    # Run the pending followups pipeline
    pending = Email.get_pending_followups(camp_id, config.FOLLOWUP_DELAY_DAYS)
    print(f"   Pending follow-ups: {len(pending)}")
    
    if pending:
        for p in pending[:5]:
            lead = leads_collection.find_one({"_id": p["_id"]})
            lead_name = (lead or {}).get("full_name", "Unknown")
            last_sent = p["last_email"].get("sent_at")
            days_since = (datetime.utcnow() - last_sent).days if last_sent else "?"
            email_count = p["email_count"]
            has_msgid = p.get("first_message_id") is not None
            print(f"      → {lead_name}: {email_count} emails, last sent {days_since}d ago, msgid={has_msgid}")

# 5. Check for orphaned email records (created but not sent — follow-up failures)
print(f"\n🔍 ORPHANED EMAILS (created but never sent):")
orphans = list(emails_collection.find({
    "status": {"$nin": ["sent", "bounced", "replied"]},
    "email_type": {"$regex": "followup"}
}).sort("created_at", -1).limit(10))
print(f"   Found: {len(orphans)}")
for o in orphans:
    lead = leads_collection.find_one({"_id": o.get("lead_id")})
    lead_name = (lead or {}).get("full_name", "Unknown")
    print(f"   → {lead_name}: status={o['status']}, type={o.get('email_type')}, created={o.get('created_at')}")

# 6. Check for duplicate pending emails (same lead, same followup_number)
print(f"\n🔍 DUPLICATE FOLLOW-UP RECORDS:")
dup_pipeline = [
    {"$match": {"email_type": {"$regex": "followup"}}},
    {"$group": {
        "_id": {"lead_id": "$lead_id", "followup_number": "$followup_number"},
        "count": {"$sum": 1},
        "statuses": {"$push": "$status"}
    }},
    {"$match": {"count": {"$gt": 1}}}
]
dupes = list(emails_collection.aggregate(dup_pipeline))
print(f"   Found: {len(dupes)} duplicate groups")
for d in dupes[:5]:
    lead = leads_collection.find_one({"_id": d["_id"]["lead_id"]})
    lead_name = (lead or {}).get("full_name", "Unknown")
    print(f"   → {lead_name}: followup #{d['_id']['followup_number']}, {d['count']}x records, statuses={d['statuses']}")

# 7. Check the sending hours right now
print(f"\n⏰ CURRENT TIME CHECK:")
import pytz
tz = pytz.timezone(config.TARGET_TIMEZONE)
now_est = datetime.now(pytz.utc).astimezone(tz)
print(f"   Current time in {config.TARGET_TIMEZONE}: {now_est.strftime('%Y-%m-%d %H:%M %Z')}")
print(f"   Sending window: {config.SENDING_HOUR_START}:00 - {config.SENDING_HOUR_END}:00")
in_window = config.SENDING_HOUR_START <= now_est.hour < config.SENDING_HOUR_END
print(f"   Currently in window: {'✅ YES' if in_window else '❌ NO'}")
print(f"   Day: {now_est.strftime('%A')} (weekend: {'YES' if now_est.weekday() >= 5 else 'NO'})")

print("\n" + "=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)
