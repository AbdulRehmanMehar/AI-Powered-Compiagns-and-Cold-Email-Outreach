#!/usr/bin/env python3
"""Check lead stats with the cutoff filter."""
import sys
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

from database import leads_collection, emails_collection
from datetime import datetime
cutoff_date = datetime(2026, 1, 29, 0, 0, 0)

# Check created_at distribution
print('=== LEAD CREATED_AT DISTRIBUTION ===')
before_cutoff = leads_collection.count_documents({'created_at': {'$lt': cutoff_date}})
after_cutoff = leads_collection.count_documents({'created_at': {'$gte': cutoff_date}})
print(f'  Before Jan 29:      {before_cutoff} (SKIPPED)')
print(f'  On/After Jan 29:    {after_cutoff} (ELIGIBLE)')

# Check emails collection for sent emails
print('\n=== EMAIL STATUS DISTRIBUTION ===')
email_pipeline = [
    {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
]
for doc in emails_collection.aggregate(email_pipeline):
    print(f'  {doc["_id"]}: {doc["count"]}')

# Get lead IDs that have been contacted (sent emails)
sent_lead_ids = set(emails_collection.distinct(
    "lead_id", 
    {"status": {"$in": ["sent", "opened", "replied"]}}
))
print(f'\n=== CONTACT STATUS ===')
print(f'  Unique leads with sent emails: {len(sent_lead_ids)}')

# Count eligible pending leads (after cutoff, not contacted)
print(f'\n=== ELIGIBLE PENDING LEADS ===')
pending_count = 0
query = {"created_at": {"$gte": cutoff_date}}
for lead in leads_collection.find(query):
    lead_id = str(lead["_id"])
    email = lead.get("email", "")
    if lead_id not in sent_lead_ids and email:
        pending_count += 1

print(f'  Leads created >= Jan 29 and NOT contacted: {pending_count}')
