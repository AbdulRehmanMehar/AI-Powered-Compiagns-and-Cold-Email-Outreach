#!/usr/bin/env python3
"""Check what the dry-run created and review follow-up email quality"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import emails_collection
from datetime import datetime, timedelta

# Find emails created in last 5 minutes (from dry-run)
cutoff = datetime.utcnow() - timedelta(minutes=10)
recent = list(emails_collection.find({
    "created_at": {"$gte": cutoff}
}).sort("created_at", -1))

print(f"Found {len(recent)} emails created in last 10 minutes")
print("=" * 80)

for i, email in enumerate(recent, 1):
    status = email.get("status", "?")
    email_type = email.get("email_type", "?")
    to = email.get("to", "?")
    subject = email.get("subject", "?")
    body = email.get("body", "")
    followup_num = email.get("followup_number", "?")
    
    print(f"\n{'='*80}")
    print(f"EMAIL #{i}")
    print(f"  Status: {status} | Type: {email_type} | Follow-up #: {followup_num}")
    print(f"  To: {to}")
    print(f"  Subject: {subject}")
    print(f"  Body ({len(body)} chars):")
    print(f"  ---")
    for line in body.split('\n'):
        print(f"  | {line}")
    print(f"  ---")

# Now clean up ALL pending follow-ups created by dry-run
if recent:
    pending_ids = [e["_id"] for e in recent if e.get("status") == "pending"]
    if pending_ids:
        result = emails_collection.delete_many({"_id": {"$in": pending_ids}})
        print(f"\n🧹 Cleaned up {result.deleted_count} pending records from dry-run")
    else:
        print(f"\n✅ No pending records to clean")
