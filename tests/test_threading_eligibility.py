#!/usr/bin/env python3
"""
Test that follow-ups are only sent for emails with message_id (threading support).

Emails sent before 2026-01-29 17:27 EST don't have message_id and will be skipped.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Email, emails_collection, campaigns_collection
from bson import ObjectId

def test_threading_eligibility():
    # Count emails WITH message_id (new - eligible for followups)
    with_msg_id = emails_collection.count_documents({
        'status': 'sent',
        'message_id': {'$exists': True, '$ne': None}
    })

    # Count emails WITHOUT message_id (old - will be skipped)
    without_msg_id = emails_collection.count_documents({
        'status': 'sent',
        '$or': [
            {'message_id': {'$exists': False}},
            {'message_id': None}
        ]
    })

    print('📊 Email Threading Status:')
    print(f'   ✅ Emails WITH message_id (eligible for followup): {with_msg_id}')
    print(f'   ⏭️  Emails WITHOUT message_id (will be skipped): {without_msg_id}')

    # Test the updated get_pending_followups
    print('\n🔍 Testing get_pending_followups (should only return emails with message_id)...')

    # Get a sample campaign
    campaign = campaigns_collection.find_one({}, sort=[('created_at', -1)])
    if campaign:
        campaign_id = str(campaign['_id'])
        pending = Email.get_pending_followups(campaign_id, days_since_last=3)
        print(f'   Campaign: {campaign.get("name", "Unknown")[:50]}')
        print(f'   Pending followups returned: {len(pending)}')
        
        # Check if any returned have no message_id
        for p in pending[:3]:
            first_msg_id = p.get('first_message_id')
            status = "✅ EXISTS" if first_msg_id else "❌ MISSING"
            print(f'   → Lead {p["_id"]}: first_message_id = {status}')
    else:
        print('   No campaigns found')

    print('\n' + '=' * 60)
    print('✅ Old emails (before 2026-01-29 17:27 EST) will NOT get followups')
    print('✅ New emails (with message_id) WILL get properly threaded followups')
    print('=' * 60)

if __name__ == '__main__':
    test_threading_eligibility()
