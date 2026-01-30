"""Check how many leads in the database have invalid emails according to RocketReach"""
import sys
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

from database import leads_collection, emails_collection
from datetime import datetime

# Count leads by validation status
total = 0
invalid = 0
valid = 0
inconclusive = 0
no_data = 0

# Get all leads
leads = leads_collection.find({})

invalid_leads = []

for lead in leads:
    total += 1
    email = lead.get('email', '')
    raw_data = lead.get('raw_data', {})
    rr_emails = raw_data.get('emails', [])
    
    found = False
    for e in rr_emails:
        if isinstance(e, dict) and e.get('email') == email:
            found = True
            smtp_valid = e.get('smtp_valid', '').lower()
            grade = e.get('grade', '')
            
            if smtp_valid == 'invalid' or grade == 'F':
                invalid += 1
                invalid_leads.append({
                    'email': email,
                    'smtp_valid': smtp_valid,
                    'grade': grade,
                    'status': lead.get('status', 'unknown')
                })
            elif smtp_valid == 'valid':
                valid += 1
            else:
                inconclusive += 1
            break
    
    if not found:
        no_data += 1

print("=" * 60)
print("LEAD EMAIL VALIDATION STATUS (from RocketReach data)")
print("=" * 60)
print(f"Total leads: {total}")
print(f"  - Valid (smtp_valid=valid): {valid} ({100*valid/max(total,1):.1f}%)")
print(f"  - Invalid (smtp_valid=invalid or grade=F): {invalid} ({100*invalid/max(total,1):.1f}%)")
print(f"  - Inconclusive: {inconclusive} ({100*inconclusive/max(total,1):.1f}%)")
print(f"  - No RocketReach data: {no_data} ({100*no_data/max(total,1):.1f}%)")
print()

# Check how many of the invalid leads have NOT been emailed yet
not_emailed_invalid = 0
emailed_invalid = 0

for il in invalid_leads:
    email_addr = il['email']
    email_sent = emails_collection.find_one({'to_email': email_addr, 'status': {'$ne': 'failed'}})
    if email_sent:
        emailed_invalid += 1
    else:
        not_emailed_invalid += 1

print("=" * 60)
print("INVALID LEADS - PREVENTABLE BOUNCES")
print("=" * 60)
print(f"Invalid leads NOT yet emailed (will be skipped now): {not_emailed_invalid}")
print(f"Invalid leads already emailed (damage done): {emailed_invalid}")
print()

if invalid_leads:
    print("Sample of invalid leads:")
    for il in invalid_leads[:10]:
        print(f"  - {il['email']} (smtp_valid={il['smtp_valid']}, grade={il['grade']}, status={il['status']})")
