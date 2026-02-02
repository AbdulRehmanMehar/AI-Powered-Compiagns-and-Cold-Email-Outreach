"""Check if bounced emails were verified before sending"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
import config

client = MongoClient(config.DATABASE_URL)
db = client.get_database()

# Get ALL bounced emails with lead verification data
bounced = list(db['emails'].aggregate([
    {"$match": {"status": "bounced"}},
    {"$lookup": {"from": "leads", "localField": "lead_id", "foreignField": "_id", "as": "lead"}},
    {"$unwind": "$lead"},
    {"$project": {
        "email": "$lead.email", 
        "verification_status": "$lead.verification_status",
        "verification_score": "$lead.verification_score", 
        "email_verified": "$lead.email_verified",
        "error_message": 1
    }},
    {"$limit": 50}
]))

print('='*70)
print('VERIFICATION STATUS OF BOUNCED EMAILS')
print('='*70)

verified_count = 0
unverified_count = 0
risky_count = 0

for l in bounced:
    email = l.get('email', 'N/A')
    v_status = l.get('verification_status', 'NOT_VERIFIED')
    v_score = l.get('verification_score', 'N/A')
    e_verified = l.get('email_verified', False)
    error = l.get('error_message', '')
    
    if v_status == 'valid' or e_verified:
        verified_count += 1
    elif v_status == 'risky':
        risky_count += 1
    else:
        unverified_count += 1
    
    print(f'{email}:')
    print(f'  verification_status: {v_status}')
    print(f'  verification_score: {v_score}')
    print(f'  email_verified: {e_verified}')
    if error:
        print(f'  error: {str(error)[:80]}')
    print()

print('-'*70)
print('SUMMARY')
print('-'*70)
print(f'Verified (status=valid or email_verified=True): {verified_count}')
print(f'Risky: {risky_count}')
print(f'Unverified/Unknown: {unverified_count}')
print()

# Check config
print('-'*70)
print('CONFIGURATION CHECK')
print('-'*70)
print(f'VERIFY_EMAILS setting: {config.VERIFY_EMAILS}')
print(f'VERIFY_SMTP setting: {config.VERIFY_SMTP}')
