#!/usr/bin/env python3
"""Backfill campaign_id for existing leads."""
import sys
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

from database import leads_collection, emails_collection

# Check how many leads have campaign_id
with_campaign = leads_collection.count_documents({'campaign_id': {'$exists': True, '$ne': None}})
without_campaign = leads_collection.count_documents({'$or': [{'campaign_id': None}, {'campaign_id': {'$exists': False}}]})

print(f'Leads WITH campaign_id: {with_campaign}')
print(f'Leads WITHOUT campaign_id: {without_campaign}')

# Try to backfill from emails collection
print('\nBackfilling campaign_id from emails...')
backfilled = 0

# Get unique lead_id -> campaign_id mappings from emails
lead_campaigns = {}
for email_doc in emails_collection.find({'campaign_id': {'$exists': True, '$ne': None}}):
    lead_id = email_doc.get('lead_id')
    campaign_id = email_doc.get('campaign_id')
    if lead_id and campaign_id:
        lead_campaigns[lead_id] = campaign_id

print(f'Found {len(lead_campaigns)} leads with emails that have campaign_id')

# Update leads that don't have campaign_id
from bson import ObjectId
for lead_id, campaign_id in lead_campaigns.items():
    try:
        # Handle both string and ObjectId
        lead_oid = ObjectId(lead_id) if isinstance(lead_id, str) else lead_id
        result = leads_collection.update_one(
            {'_id': lead_oid, '$or': [{'campaign_id': None}, {'campaign_id': {'$exists': False}}]},
            {'$set': {'campaign_id': campaign_id}}
        )
        if result.modified_count > 0:
            backfilled += 1
    except Exception as e:
        pass  # Skip invalid IDs

print(f'Backfilled {backfilled} leads with campaign_id')

# Final counts
with_campaign = leads_collection.count_documents({'campaign_id': {'$exists': True, '$ne': None}})
without_campaign = leads_collection.count_documents({'$or': [{'campaign_id': None}, {'campaign_id': {'$exists': False}}]})
print(f'\nFinal counts:')
print(f'  Leads WITH campaign_id: {with_campaign}')
print(f'  Leads WITHOUT campaign_id: {without_campaign}')
