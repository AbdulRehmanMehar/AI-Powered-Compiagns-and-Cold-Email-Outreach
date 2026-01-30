"""Check how leads are getting into the system without verification"""
import sys
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

from database import emails_collection, leads_collection
from datetime import datetime

# Get today's bounced emails and their leads
today_start = datetime(2026, 1, 29, 0, 0, 0)

bounced = list(emails_collection.find({
    'status': 'bounced',
    'sent_at': {'$gte': today_start}
}))

print(f"=== CHECKING {len(bounced)} BOUNCED EMAILS ===")
print()

# Check each bounced email
for i, email_doc in enumerate(bounced[:10]):
    lead_id = email_doc.get('lead_id')
    lead = leads_collection.find_one({'_id': lead_id})
    
    if lead:
        email_addr = lead.get('email', 'unknown')
        raw_data = lead.get('raw_data', {})
        
        # Check if RocketReach already marked it invalid
        rr_emails = raw_data.get('emails', [])
        
        print(f"{i+1}. Lead: {email_addr}")
        print(f"   Created: {lead.get('created_at')}")
        
        # Check RocketReach validation status
        if rr_emails:
            for e in rr_emails:
                if e.get('email') == email_addr:
                    print(f"   RocketReach status: smtp_valid={e.get('smtp_valid')}, grade={e.get('grade')}")
                    break
            else:
                print(f"   RocketReach status: Email not in RR list")
        else:
            print(f"   RocketReach status: No emails in raw_data")
        
        # Check if lead has email_verified field
        print(f"   Lead.email_verified: {lead.get('email_verified', 'NOT SET')}")
        print()

print("=" * 60)
print()
print("=== CHECKING VERIFICATION CONFIG ===")

import config
print(f"VERIFY_EMAILS: {config.VERIFY_EMAILS}")
print(f"VERIFY_MX_RECORDS: {config.VERIFY_MX_RECORDS}")
print(f"VERIFY_SMTP: {config.VERIFY_SMTP}")
