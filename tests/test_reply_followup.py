"""Test reply detection and follow-up system."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reply_detector import ReplyDetector
from campaign_manager import CampaignManager
from database import Email, Campaign, emails_collection

print('📬 TESTING REPLY DETECTION & FOLLOW-UPS')
print('='*50)

# Test reply detector
print('\n1. Testing ReplyDetector connection...')
detector = ReplyDetector()
print(f'   Accounts configured: {len(detector.accounts)}')

# Try to connect to first account
if detector.accounts:
    account = detector.accounts[0]
    print(f'   Testing: {account["email"]}')
    conn = detector.connect(account)
    if conn:
        print('   ✅ IMAP connection works!')
        detector.disconnect_all()
    else:
        print('   ⚠️ IMAP not enabled (requires paid Zoho)')
else:
    print('   ⚠️ No email accounts configured')

# Check pending follow-ups
print('\n2. Checking pending follow-ups...')
campaigns = Campaign.get_active_campaigns()
print(f'   Active campaigns: {len(campaigns)}')

total_pending = 0
for c in campaigns[:3]:  # Check first 3
    campaign_id = str(c['_id'])
    pending = Email.get_pending_followups(campaign_id, days_since_last=3)
    if pending:
        print(f'   {c["name"]}: {len(pending)} pending follow-ups')
        total_pending += len(pending)

print(f'\n   Total pending follow-ups: {total_pending}')

# Check email statuses
print('\n3. Email status breakdown:')
pipeline = [
    {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
]
for doc in emails_collection.aggregate(pipeline):
    print(f'   {doc["_id"]}: {doc["count"]}')

# Check followup counts
print('\n4. Followup count breakdown:')
pipeline = [
    {'$group': {'_id': '$followup_count', 'count': {'$sum': 1}}}
]
for doc in emails_collection.aggregate(pipeline):
    count = doc["_id"] if doc["_id"] is not None else 0
    print(f'   Followup #{count}: {doc["count"]} emails')

print('\n' + '='*50)
print('Summary:')
print('  - Reply detection: Requires IMAP (paid Zoho)')
print('  - Follow-ups: Run every 6 hours via auto_scheduler')
print('  - Logic: Day 3 = same thread, Day 6 = new thread')
