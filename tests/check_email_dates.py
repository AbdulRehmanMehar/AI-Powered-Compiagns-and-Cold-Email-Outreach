#!/usr/bin/env python3
"""Check what dates emails were sent."""

import sys
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

from pymongo import MongoClient
import config

client = MongoClient(config.DATABASE_URL)
db = client.get_database()
leads_collection = db['leads']

cursor = leads_collection.find({
    'emails': {'$exists': True, '$ne': []}
})

all_dates = []
for lead in cursor:
    for email in lead.get('emails', []):
        created = email.get('created_at')
        if created:
            all_dates.append(created)

all_dates.sort(reverse=True)

print(f"Total emails in database: {len(all_dates)}")
print(f"\nMost recent 20 emails:")
for d in all_dates[:20]:
    print(f"  {d}")
    
print(f"\nOldest email: {all_dates[-1] if all_dates else 'None'}")
print(f"Newest email: {all_dates[0] if all_dates else 'None'}")
