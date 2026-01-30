#!/usr/bin/env python3
"""Disable all campaigns created before Jan 29, 2026 (pre-enhancement)."""
import sys
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

from database import campaigns_collection
from datetime import datetime

cutoff = datetime(2026, 1, 29, 0, 0, 0)

# Disable all campaigns created before Jan 29, 2026
result = campaigns_collection.update_many(
    {'created_at': {'$lt': cutoff}},
    {'$set': {'status': 'disabled', 'disabled_reason': 'Pre-enhancement campaign (before Jan 29, 2026)'}}
)

print(f'✅ Disabled {result.modified_count} old campaigns (before Jan 29, 2026)')

# Verify new status distribution
print(f'\n=== UPDATED CAMPAIGN STATUS ===')
pipeline = [{'$group': {'_id': '$status', 'count': {'$sum': 1}}}]
for doc in campaigns_collection.aggregate(pipeline):
    print(f'  {doc["_id"]}: {doc["count"]}')

# Show campaigns that remain active
print(f'\n=== ACTIVE CAMPAIGNS (Post-Enhancement) ===')
active = list(campaigns_collection.find({'status': 'active'}).sort('created_at', -1).limit(10))
for c in active:
    created = c.get('created_at', '?')
    if hasattr(created, 'strftime'):
        created = created.strftime('%Y-%m-%d %H:%M')
    print(f'  {created} | {c.get("name", "Unnamed")}')
