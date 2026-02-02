#!/usr/bin/env python3
"""Check what's happening with today's bounces"""

from database import leads_collection, emails_collection

bounced_recipients = [
    'prakash.balaji@workflowautomation.in',
    'cweirich@centrias.de', 
    'graemew@virtusa.com',
    'rlee@hubspot.com',
    'dario@microsoft.com',
    'liam@google.com'
]

print('=' * 70)
print('ANALYZING BOUNCED EMAILS FROM TODAY')
print('=' * 70)

print('\n--- Lead status for bounced emails ---')
for recip in bounced_recipients:
    lead = leads_collection.find_one({'email': recip})
    if lead:
        status = lead.get('status', 'unknown')
        email_sent = lead.get('email_sent_at')
        verification = lead.get('verification_status', 'NOT SET')
        email_verified = lead.get('email_verified', 'NOT SET')
        email_invalid = lead.get('email_invalid', False)
        print(f'{recip[:40]}')
        print(f'  status: {status}, sent_at: {email_sent}')
        print(f'  verification_status: {verification}, email_verified: {email_verified}')
        print(f'  email_invalid: {email_invalid}')
    else:
        print(f'{recip[:40]} | NOT FOUND in leads')

# Check if there are ANY leads with verification_status set
print('\n--- How many leads have verification_status? ---')
with_verification = leads_collection.count_documents({'verification_status': {'$exists': True}})
total_leads = leads_collection.count_documents({})
print(f'Leads with verification_status: {with_verification} / {total_leads}')

# Check most recent leads
print('\n--- Most recently emailed leads ---')
recent_leads = list(leads_collection.find(
    {'email_sent_at': {'$exists': True}},
    {'email': 1, 'email_sent_at': 1, 'verification_status': 1, 'email_verified': 1, 'status': 1}
).sort('email_sent_at', -1).limit(10))

for lead in recent_leads:
    email = lead.get('email', 'unknown')
    sent = lead.get('email_sent_at')
    verification = lead.get('verification_status', 'NOT SET')
    email_verified = lead.get('email_verified', 'NOT SET')
    print(f'{email[:40]:40} | Sent: {sent} | verified: {email_verified}')
