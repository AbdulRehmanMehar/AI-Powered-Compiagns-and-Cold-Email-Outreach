"""List pending leads with timestamps."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import leads_collection, emails_collection
from datetime import datetime

# Get leads that have been sent emails
sent_lead_ids = set(emails_collection.distinct('lead_id', {'status': {'$in': ['sent', 'opened', 'replied']}}))

print('=== PENDING LEADS (oldest first with timestamps) ===\n')
print(f'{"Created":<20} {"Age":<8} {"Name":<25} {"Email"}')
print('-' * 90)

count = 0
for lead in leads_collection.find().sort('created_at', 1).limit(100):
    lead_id = str(lead['_id'])
    if lead_id in sent_lead_ids:
        continue
    if not lead.get('email'):
        continue
    
    created = lead.get('created_at')
    if created:
        age = (datetime.utcnow() - created).days
        created_str = created.strftime('%Y-%m-%d %H:%M')
        age_str = f'{age}d ago'
    else:
        age_str = '?'
        created_str = 'NO TIMESTAMP'
    
    name = f"{lead.get('first_name', '?')} {lead.get('last_name', '') or ''}"
    email = lead.get('email', 'no email')
    
    print(f'{created_str:<20} {age_str:<8} {name:<25} {email}')
    
    count += 1
    if count >= 30:
        break

print(f'\n--- Showing {count} oldest pending leads ---')

# Summary
total_pending = leads_collection.count_documents({}) - len(sent_lead_ids)
print(f'\nTotal leads in DB: {leads_collection.count_documents({})}')
print(f'Already contacted: {len(sent_lead_ids)}')
print(f'Estimated pending: ~{total_pending}')
