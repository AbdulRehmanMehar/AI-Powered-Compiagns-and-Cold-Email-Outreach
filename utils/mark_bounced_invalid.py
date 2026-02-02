"""
Mark all bounced emails as invalid to prevent future send attempts.
This is a one-time cleanup script.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
import config
from datetime import datetime

client = MongoClient(config.DATABASE_URL)
db = client.get_database()

print('='*70)
print('MARKING BOUNCED LEADS AS INVALID')
print('='*70)

# Find all unique leads that have bounced emails
bounced_pipeline = [
    {"$match": {"status": "bounced"}},
    {"$group": {"_id": "$lead_id"}},
]

bounced_lead_ids = [doc["_id"] for doc in db['emails'].aggregate(bounced_pipeline)]
print(f"\nFound {len(bounced_lead_ids)} leads with bounced emails")

# Mark each lead as invalid
marked = 0
already_invalid = 0
for lead_id in bounced_lead_ids:
    lead = db['leads'].find_one({"_id": lead_id})
    if not lead:
        continue
    
    if lead.get("email_invalid"):
        already_invalid += 1
        continue
    
    db['leads'].update_one(
        {"_id": lead_id},
        {"$set": {
            "email_invalid": True,
            "email_invalid_reason": "Historical bounce detected",
            "email_invalid_at": datetime.utcnow()
        }}
    )
    marked += 1
    print(f"  Marked invalid: {lead.get('email', 'unknown')}")

print(f"\n{'='*70}")
print(f"SUMMARY")
print(f"{'='*70}")
print(f"Total bounced leads: {len(bounced_lead_ids)}")
print(f"Newly marked invalid: {marked}")
print(f"Already marked: {already_invalid}")
print(f"\nThese leads will now be skipped during future campaigns.")
