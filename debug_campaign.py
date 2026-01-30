#!/usr/bin/env python3
from database import leads_collection, campaigns_collection, emails_collection
from datetime import datetime
from bson import ObjectId

# Check for the campaign mentioned in the error
campaign_id = '697c0cf2a0876a8eca5cae9d'
campaign = campaigns_collection.find_one({'_id': ObjectId(campaign_id)})
print(f'Campaign {campaign_id}: {"FOUND" if campaign else "NOT FOUND"}')
if campaign:
    print(f'  Name: {campaign.get("name")}')
    print(f'  Status: {campaign.get("status")}')

# Check for leads with this campaign_id
leads_with_campaign = leads_collection.count_documents({'campaign_id': ObjectId(campaign_id)})
print(f'  Leads with this campaign_id: {leads_with_campaign}')

# Check for pending leads (no emails sent)
print('\n--- Pending Leads Analysis ---')
cutoff_date = datetime(2026, 1, 29, 0, 0, 0)
pending_count = 0
campaign_ids = set()

for lead in leads_collection.find({'created_at': {'$gte': cutoff_date}}).limit(20):
    lead_id = str(lead['_id'])
    email_sent = emails_collection.find_one({'lead_id': lead['_id'], 'status': {'$in': ['sent', 'opened', 'replied']}})
    if not email_sent:
        pending_count += 1
        if 'campaign_id' in lead:
            campaign_ids.add(str(lead['campaign_id']))
        else:
            print(f'  Lead {lead.get("email")} has no campaign_id')

print(f'Total pending leads (sample of 20): {pending_count}')
print(f'Unique campaign IDs in pending leads: {len(campaign_ids)}')
for cid in list(campaign_ids)[:5]:
    c = campaigns_collection.find_one({'_id': ObjectId(cid)})
    print(f'  {cid}: {c.get("name") if c else "NOT FOUND IN DB"}')
