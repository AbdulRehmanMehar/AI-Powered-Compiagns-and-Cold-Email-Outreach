#!/usr/bin/env python3
"""Fetch emails written after a specific date for review."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
from datetime import datetime
import json
import config

client = MongoClient(config.DATABASE_URL)
db = client.get_database()
emails_collection = db['emails']
leads_collection = db['leads']

# Jan 28 02:25:21 +0500 = Jan 27 21:25:21 UTC
cutoff = datetime(2026, 1, 27, 21, 25, 21)

# Get emails after cutoff from emails collection
emails = list(emails_collection.find({'created_at': {'$gte': cutoff}}).sort('created_at', -1))
print(f"Found {len(emails)} emails after {cutoff}")

emails_found = []
for e in emails:
    lead = leads_collection.find_one({'_id': e.get('lead_id')})
    emails_found.append({
        'to': lead.get('name') if lead else 'Unknown',
        'company': lead.get('company') if lead else 'Unknown',
        'email': lead.get('email') if lead else 'Unknown',
        'status': e.get('status'),
        'created_at': str(e.get('created_at')),
        'subject': e.get('subject'),
        'body': e.get('body'),
        'word_count': len(e.get('body', '').split()) if e.get('body') else 0
    })

print("=" * 80)

for i, email in enumerate(emails_found, 1):
    print(f"\n--- Email {i} ---")
    print(f"To: {email['to']} at {email['company']}")
    print(f"Email: {email['email']}")
    print(f"Status: {email['status']}")
    print(f"Created: {email['created_at']}")
    print(f"Subject: {email['subject']}")
    print(f"Word Count: {email['word_count']}")
    print(f"Body:\n{email['body']}")
    print()

# Save to JSON for analysis
output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recent_emails_for_review.json')
with open(output_path, 'w') as f:
    json.dump(emails_found, f, indent=2)
    
print(f"\nSaved {len(emails_found)} emails to {output_path}")
