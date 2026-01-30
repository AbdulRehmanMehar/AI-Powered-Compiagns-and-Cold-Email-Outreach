"""Deep dive into bounced email records"""
import sys
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

from database import emails_collection, leads_collection
from datetime import datetime
import json

# Get one bounced email to see full structure
today_start = datetime(2026, 1, 29, 0, 0, 0)
bounced = emails_collection.find_one({
    'status': 'bounced',
    'sent_at': {'$gte': today_start}
})

print("=== FULL BOUNCED EMAIL RECORD ===")
if bounced:
    bounced['_id'] = str(bounced['_id'])
    if bounced.get('lead_id'):
        bounced['lead_id'] = str(bounced['lead_id'])
    print(json.dumps(bounced, indent=2, default=str))
else:
    print("No bounced emails found")

print()
print("=== CHECKING LEAD RECORD ===")
if bounced and bounced.get('lead_id'):
    from bson import ObjectId
    lead = leads_collection.find_one({'_id': ObjectId(bounced['lead_id'])})
    if lead:
        lead['_id'] = str(lead['_id'])
        print(json.dumps(lead, indent=2, default=str))
    else:
        print(f"Lead not found for ID: {bounced['lead_id']}")
else:
    print("No lead_id in email record")

print()
print("=== SAMPLE OF ALL LEADS WITH VERIFICATION STATUS ===")
# Check how many leads have verification data
total = leads_collection.count_documents({})
has_verified_true = leads_collection.count_documents({'email_verified': True})
has_verified_false = leads_collection.count_documents({'email_verified': False})
has_verified_field = leads_collection.count_documents({'email_verified': {'$exists': True}})

print(f"Total leads: {total}")
print(f"With email_verified field: {has_verified_field}")
print(f"  - email_verified=True: {has_verified_true}")
print(f"  - email_verified=False: {has_verified_false}")
print(f"Without email_verified: {total - has_verified_field}")
