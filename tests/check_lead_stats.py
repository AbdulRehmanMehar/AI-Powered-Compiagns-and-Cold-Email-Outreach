"""Check lead and email statistics"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
import config

client = MongoClient(config.DATABASE_URL)
db = client.get_database()

# Total leads
total_leads = db['leads'].count_documents({})
print(f'Total leads in database: {total_leads}')

# Contacted leads
contacted_pipeline = [
    {"$match": {"status": {"$in": ["sent", "replied", "opened"]}}},
    {"$lookup": {"from": "leads", "localField": "lead_id", "foreignField": "_id", "as": "lead"}},
    {"$unwind": "$lead"},
    {"$group": {"_id": "$lead.email"}}
]
contacted_emails = list(db['emails'].aggregate(contacted_pipeline))
print(f'Contacted emails: {len(contacted_emails)}')

# Total emails
total_emails = db['emails'].count_documents({})
sent_emails = db['emails'].count_documents({"status": "sent"})
bounced_emails = db['emails'].count_documents({"status": "bounced"})
pending_emails = db['emails'].count_documents({"status": "pending"})

print(f'\nEmail stats:')
print(f'  Total: {total_emails}')
print(f'  Sent: {sent_emails}')
print(f'  Bounced: {bounced_emails}')
print(f'  Pending: {pending_emails}')

# Check unique lead emails
unique_emails = db['leads'].distinct('email')
print(f'\nUnique lead emails: {len(unique_emails)}')

# Check how many campaigns
total_campaigns = db['campaigns'].count_documents({})
print(f'\nTotal campaigns: {total_campaigns}')

# Sample of lead titles to understand the pool
print(f'\n--- Sample of titles in lead pool ---')
title_pipeline = [
    {"$group": {"_id": "$title", "count": {"$sum": 1}}},
    {"$sort": {"count": -1}},
    {"$limit": 20}
]
titles = list(db['leads'].aggregate(title_pipeline))
for t in titles:
    print(f'  {t["_id"]}: {t["count"]}')
