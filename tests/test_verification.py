"""Test email verification against known bounced emails"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
import config
from rocketreach_client import quick_email_check

client = MongoClient(config.DATABASE_URL)
db = client.get_database()

print("="*60)
print("Testing Email Verification Against Bounced Emails")
print("="*60)

# Get bounced emails
bounced_emails = list(db['emails'].aggregate([
    {"$match": {"status": "bounced"}},
    {"$lookup": {"from": "leads", "localField": "lead_id", "foreignField": "_id", "as": "lead"}},
    {"$unwind": "$lead"},
    {"$group": {"_id": "$lead.email"}},  # Unique emails only
]))

unique_bounced = [e['_id'] for e in bounced_emails if e.get('_id')]

print(f"\nTotal unique bounced emails: {len(unique_bounced)}")

# Test verification on each
would_catch = 0
would_miss = 0
catch_reasons = {}

print("\n" + "-"*60)
print("Verification Results:")
print("-"*60)

for email in unique_bounced:
    is_valid, reason = quick_email_check(email)
    
    if not is_valid:
        would_catch += 1
        catch_reasons[reason] = catch_reasons.get(reason, 0) + 1
        print(f"✅ WOULD CATCH: {email} - {reason}")
    else:
        would_miss += 1
        print(f"❌ WOULD MISS: {email}")

print("\n" + "="*60)
print("Summary")
print("="*60)
print(f"\nWould catch: {would_catch}/{len(unique_bounced)} ({would_catch/len(unique_bounced)*100:.1f}%)")
print(f"Would miss: {would_miss}/{len(unique_bounced)} ({would_miss/len(unique_bounced)*100:.1f}%)")

print("\nReasons for catches:")
for reason, count in sorted(catch_reasons.items(), key=lambda x: -x[1]):
    print(f"  {reason}: {count}")

# Estimated new bounce rate
current_bounce_rate = 40.3
estimated_reduction = would_catch / len(unique_bounced) * 100
new_bounce_rate = current_bounce_rate * (1 - would_catch/len(unique_bounced))
print(f"\n📊 Estimated Impact:")
print(f"  Current bounce rate: {current_bounce_rate:.1f}%")
print(f"  Emails verification would block: {estimated_reduction:.1f}%")
print(f"  New estimated bounce rate: {new_bounce_rate:.1f}%")
