"""Analyze when bounced emails were sent and if verification was called"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
import config

client = MongoClient(config.DATABASE_URL)
db = client.get_database()

bounced_emails = [
    'ericdonzier@openfieldlive.com', 
    'nbrown@preshift.io', 
    'rlee@honbu.io', 
    'wkariuki@nanasi.co', 
    'evan@omycarapp.com', 
    'lkaufman@mypowerfarm.com'
]

print('='*70)
print('CRITICAL ANALYSIS: WHEN WERE BOUNCED EMAILS SENT?')
print('='*70)

for email_addr in bounced_emails:
    lead = db['leads'].find_one({'email': email_addr})
    if not lead:
        print(f'\n{email_addr}: Lead not found')
        continue
    
    emails = list(db['emails'].find({'lead_id': lead['_id']}).sort('created_at', 1))
    
    print(f'\n{email_addr}:')
    print(f'  Lead created: {lead.get("created_at", "unknown")}')
    print(f'  Lead verification_status: {lead.get("verification_status", "NOT SET")}')
    print(f'  Lead email_verified: {lead.get("email_verified", "NOT SET")}')
    
    if emails:
        for e in emails[:1]:
            print(f'  Email created_at: {e.get("created_at")}')
            print(f'  Email sent_at: {e.get("sent_at")}')
            print(f'  Email status: {e.get("status")}')
    else:
        print(f'  No email records found')

print('\n' + '='*70)
print('KEY QUESTION: WAS VERIFICATION CODE EVEN IN THE SEND PATH?')
print('='*70)

# Check if there's any lead with verification data
verified_leads = db['leads'].count_documents({'verification_status': {'$exists': True}})
print(f'\nLeads with verification_status field: {verified_leads}')

total_leads = db['leads'].count_documents({})
print(f'Total leads: {total_leads}')

# Check git history or code to see when verification was added
print('\n' + '='*70)
print('CHECKING CODE: Is verification ACTUALLY called before sending?')
print('='*70)
