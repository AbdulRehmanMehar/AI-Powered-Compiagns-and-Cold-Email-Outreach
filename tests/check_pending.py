#!/usr/bin/env python3
"""Analyze why leads aren't being contacted"""

from database import leads_collection, emails_collection, DoNotContact
from datetime import datetime

cutoff = datetime(2026, 1, 29, 0, 0, 0)

# Get sent lead IDs
sent_lead_ids = set(emails_collection.distinct(
    'lead_id', 
    {'status': {'$in': ['sent', 'opened', 'replied']}}
))
print(f'Leads with sent emails: {len(sent_lead_ids)}')

# Check leads after cutoff
pending_count = 0
blocked_count = 0
no_email_count = 0
already_sent_count = 0
invalid_count = 0
pending_leads = []

for lead in leads_collection.find({'created_at': {'$gte': cutoff}}):
    lead_id = str(lead['_id'])
    email = lead.get('email', '')
    
    if not email:
        no_email_count += 1
        continue
    if lead_id in sent_lead_ids:
        already_sent_count += 1
        continue
    if DoNotContact.is_blocked(email):
        blocked_count += 1
        continue
    if lead.get('email_invalid'):
        invalid_count += 1
        continue
    pending_count += 1
    if len(pending_leads) < 5:
        pending_leads.append(lead)

print(f'\n=== LEADS AFTER JAN 29 (278 total) ===')
print(f'Already sent: {already_sent_count}')
print(f'No email: {no_email_count}')
print(f'Blocked (DNC): {blocked_count}')
print(f'Invalid email: {invalid_count}')
print(f'PENDING (should be contacted): {pending_count}')

if pending_leads:
    print(f'\nSample pending leads:')
    for lead in pending_leads:
        print(f'  - {lead.get("email")} ({lead.get("company")})')
