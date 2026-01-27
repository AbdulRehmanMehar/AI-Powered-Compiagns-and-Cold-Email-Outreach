#!/usr/bin/env python3
"""Backfill from_email for existing sent emails."""

import sys
sys.path.insert(0, '..')

from database import emails_collection
import config
from collections import defaultdict

print('Backfilling from_email for existing sent emails...')
print('(Assigning round-robin since original sender unknown)')
print()

# Get all sent emails without from_email
emails_missing = list(emails_collection.find({
    'status': 'sent',
    'from_email': {'$exists': False}
}))

print(f'Found {len(emails_missing)} emails to update')

if not emails_missing:
    print('Nothing to update!')
    sys.exit(0)

# Group by lead_id so each lead gets consistent sender
by_lead = defaultdict(list)
for email in emails_missing:
    by_lead[str(email['lead_id'])].append(email)

# Assign accounts consistently per lead
accounts = [acc['email'] for acc in config.ZOHO_ACCOUNTS]
updated = 0

for i, (lead_id, lead_emails) in enumerate(by_lead.items()):
    # Each lead gets one consistent sender
    sender = accounts[i % len(accounts)]
    
    for email in lead_emails:
        emails_collection.update_one(
            {'_id': email['_id']},
            {'$set': {'from_email': sender}}
        )
        updated += 1

print(f'Updated {updated} emails across {len(by_lead)} leads')
print()

# Verify
sample = emails_collection.find_one({'status': 'sent', 'from_email': {'$exists': True}})
print(f'Sample updated email sender: {sample.get("from_email") if sample else "none"}')

# Show distribution
print()
print('Sender distribution:')
for acc in accounts:
    count = emails_collection.count_documents({'from_email': acc, 'status': 'sent'})
    if count > 0:
        print(f'  {acc}: {count} emails')
