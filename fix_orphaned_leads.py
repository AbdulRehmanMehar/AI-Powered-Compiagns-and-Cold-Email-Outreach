#!/usr/bin/env python3
"""
Fix orphaned leads that reference deleted campaigns or have no campaign_id
"""
from database import leads_collection, campaigns_collection
from bson import ObjectId
from datetime import datetime

print("=" * 60)
print("FIXING ORPHANED LEADS")
print("=" * 60)

# Step 1: Find leads with campaign_id pointing to deleted campaigns
deleted_campaign_leads = []
for lead in leads_collection.find({'campaign_id': {'$exists': True, '$ne': None}}):
    campaign_id = lead['campaign_id']
    campaign = campaigns_collection.find_one({'_id': campaign_id})
    if not campaign:
        deleted_campaign_leads.append(lead)
        print(f"Found lead {lead.get('email')} with deleted campaign: {campaign_id}")

print(f"\nTotal leads with deleted campaigns: {len(deleted_campaign_leads)}")

# Step 2: Find leads with no campaign_id
cutoff_date = datetime(2026, 1, 29, 0, 0, 0)
no_campaign_leads = list(leads_collection.find({
    'created_at': {'$gte': cutoff_date},
    '$or': [
        {'campaign_id': None},
        {'campaign_id': {'$exists': False}}
    ]
}))

print(f"Total leads with no campaign_id: {len(no_campaign_leads)}")

# Step 3: Remove campaign_id from orphaned leads so they're treated as "unknown"
all_orphaned = deleted_campaign_leads + no_campaign_leads
print(f"\n Total orphaned leads to fix: {len(all_orphaned)}")

if all_orphaned:
    response = input("\nRemove campaign_id from these orphaned leads? (y/n): ")
    if response.lower() == 'y':
        for lead in all_orphaned:
            result = leads_collection.update_one(
                {'_id': lead['_id']},
                {'$unset': {'campaign_id': ""}}
            )
            if result.modified_count > 0:
                print(f"  ✓ Removed campaign_id from {lead.get('email')}")
        
        print(f"\n✅ Fixed {len(all_orphaned)} orphaned leads")
        print("These leads will now be processed with default campaign context")
    else:
        print("Cancelled")
else:
    print("\n✅ No orphaned leads found")
