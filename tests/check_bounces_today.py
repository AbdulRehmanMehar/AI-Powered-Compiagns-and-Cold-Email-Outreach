"""Check today's bounces and their verification status"""
import sys
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

from database import emails_collection, leads_collection
from datetime import datetime, timedelta

# Use collections directly
emails = emails_collection
leads = leads_collection

db = get_database()

# Get today's bounces
today_start = datetime(2026, 1, 29, 0, 0, 0)

# Find bounced emails from today
bounced = list(db.emails.find({
    'status': 'bounced',
    'sent_at': {'$gte': today_start}
}).sort('sent_at', -1))

print(f'=== TODAY\'S BOUNCES: {len(bounced)} ===')
print()

# Track verification stats
verified_count = 0
unverified_count = 0
not_set_count = 0

# Check each bounced email's lead verification status
for i, email in enumerate(bounced[:30]):
    lead_id = email.get('lead_id')
    lead = db.leads.find_one({'_id': lead_id})
    
    to_email = email.get('to_email', 'unknown')
    sent_at = email.get('sent_at', '')
    bounce_reason = email.get('bounce_reason', email.get('error', 'unknown'))
    
    # Check verification status of the lead
    if lead:
        verified = lead.get('email_verified', 'NOT_SET')
        verification_method = lead.get('verification_method', 'NONE')
        verification_score = lead.get('verification_score', 'N/A')
        
        if verified == True:
            verified_count += 1
        elif verified == False:
            unverified_count += 1
        else:
            not_set_count += 1
    else:
        verified = 'LEAD_NOT_FOUND'
        verification_method = 'N/A'
        verification_score = 'N/A'
        not_set_count += 1
    
    print(f'{i+1}. {to_email}')
    print(f'   Sent: {sent_at}')
    print(f'   Bounce: {str(bounce_reason)[:80]}')
    print(f'   Lead verified: {verified} | Method: {verification_method} | Score: {verification_score}')
    print()

print('=' * 60)
print('SUMMARY OF BOUNCED EMAILS:')
print(f'  - Verified (email_verified=True): {verified_count}')
print(f'  - Unverified (email_verified=False): {unverified_count}')
print(f'  - Not Set / Not Found: {not_set_count}')
print()

# Now check the overall verification stats for leads being emailed
print('=' * 60)
print('OVERALL LEAD VERIFICATION STATS:')

# All leads that have been emailed
emailed_leads = db.leads.find({'status': {'$in': ['emailed', 'contacted', 'replied']}})
total_emailed = 0
emailed_verified = 0
emailed_unverified = 0
emailed_not_set = 0

for lead in emailed_leads:
    total_emailed += 1
    verified = lead.get('email_verified')
    if verified == True:
        emailed_verified += 1
    elif verified == False:
        emailed_unverified += 1
    else:
        emailed_not_set += 1

print(f'Total emailed leads: {total_emailed}')
print(f'  - Verified before email: {emailed_verified} ({100*emailed_verified/max(total_emailed,1):.1f}%)')
print(f'  - Unverified: {emailed_unverified} ({100*emailed_unverified/max(total_emailed,1):.1f}%)')
print(f'  - Never verified: {emailed_not_set} ({100*emailed_not_set/max(total_emailed,1):.1f}%)')
