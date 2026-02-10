#!/usr/bin/env python3
"""Check specific follow-up lead records"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import *
from bson import ObjectId

for name in ['Dan Barker', 'Greg Hoffman', 'Catrice']:
    lead = leads_collection.find_one({'full_name': {'$regex': name, '$options': 'i'}})
    if not lead:
        print(f'{name}: NOT FOUND')
        continue
    
    print(f'\n{"="*60}')
    print(f'{lead["full_name"]} ({lead.get("email")})')
    print(f'{"="*60}')
    
    emails = list(emails_collection.find({'lead_id': lead['_id']}).sort('created_at', 1))
    print(f'Total email records: {len(emails)}')
    
    for e in emails:
        camp = campaigns_collection.find_one({'_id': e.get('campaign_id')})
        camp_name = (camp or {}).get('name', '?')[:40]
        status = e['status']
        etype = e.get('email_type', 'initial')
        fu_num = e.get('followup_number', 0)
        has_msgid = 'Yes' if e.get('message_id') else 'No'
        from_email = e.get('from_email', '?')
        sent_at = e.get('sent_at', 'never')
        created = e.get('created_at', '?')
        
        print(f'  [{status:8s}] type={etype:20s} fu#{fu_num} msgid={has_msgid:3s} from={from_email}')
        print(f'           campaign={camp_name}')
        print(f'           created={created} sent={sent_at}')

print(f'\n{"="*60}')
print('CHECKING PENDING FOLLOWUP RECORDS ACROSS ALL CAMPAIGNS')
print(f'{"="*60}')

# Check all pending followup records
pending_followups = list(emails_collection.find({
    'status': 'pending',
    'email_type': {'$regex': 'followup'}
}))
print(f'Total pending followup records: {len(pending_followups)}')

for pf in pending_followups:
    lead = leads_collection.find_one({'_id': pf.get('lead_id')})
    lead_name = (lead or {}).get('full_name', '?')
    print(f'  {lead_name}: fu#{pf.get("followup_number",0)}, created={pf.get("created_at")}, to={pf.get("to_email")}')

# Check all failed followup records
print(f'\n--- FAILED FOLLOWUP RECORDS ---')
failed_followups = list(emails_collection.find({
    'status': 'failed',
    'email_type': {'$regex': 'followup'}
}))
print(f'Total failed followup records: {len(failed_followups)}')
for ff in failed_followups[:10]:
    lead = leads_collection.find_one({'_id': ff.get('lead_id')})
    lead_name = (lead or {}).get('full_name', '?')
    print(f'  {lead_name}: fu#{ff.get("followup_number",0)}, error={ff.get("error","?")[:60]}')
