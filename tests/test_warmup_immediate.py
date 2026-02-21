#!/usr/bin/env python3
"""
Test warm-up emails by creating drafts scheduled to send RIGHT NOW.
Use this to verify the system works before waiting 4+ hours.

Usage:
    python3 tests/test_warmup_immediate.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from datetime import datetime
from bson import ObjectId

email_drafts_col = db['email_drafts']

# Test emails
test_emails = [
    'mehars.6925@gmail.com',
    'abdrehman6925@gmail.com', 
    'webdeveloper.6925@gmail.com',
]

print(f"\n=== IMMEDIATE TEST: Create drafts to send RIGHT NOW ===\n")

# Fetch one high-quality draft to clone
source_draft = email_drafts_col.find_one(
    {
        'status': 'ready_to_send',
        'quality_score': {'$gte': 70}
    },
    sort=[('created_at', -1)]
)

if not source_draft:
    print("❌ No ready-to-send drafts found.")
    print("   Wait for pre_generator to create some first.")
    sys.exit(1)

print(f"✅ Using source draft: {source_draft.get('subject', 'N/A')}")
print(f"   Quality score: {source_draft.get('quality_score')}")
print(f"   From: {source_draft.get('from_account')}\n")

# Create one test draft per email, scheduled for NOW
drafts_created = 0
now = datetime.utcnow()

for test_email in test_emails:
    test_draft_doc = {
        'lead_id': ObjectId(),
        'campaign_id': source_draft['campaign_id'],
        'to_email': test_email,
        'to_name': 'Test User',
        'email_type': 'warmup_test',
        'followup_number': 0,
        'subject': source_draft.get('subject', ''),
        'body': source_draft.get('body', ''),
        'html_body': source_draft.get('html_body'),
        'from_account': source_draft.get('from_account'),
        'in_reply_to': source_draft.get('in_reply_to'),
        'references': source_draft.get('references', []),
        'quality_score': source_draft.get('quality_score', 0),
        'review_passed': True,
        'status': 'ready_to_send',
        'created_at': now,
        'scheduled_send_at': now,  # SEND NOW (or very soon)
        'sent_at': None,
        'error_message': None,
        'retry_count': 0,
        'icp_template': source_draft.get('icp_template'),
        'is_icp': False,
    }
    
    result = email_drafts_col.insert_one(test_draft_doc)
    drafts_created += 1
    print(f"📧 {test_email}")
    print(f"   Draft ID: {str(result.inserted_id)[:16]}...")
    print(f"   Will send in next 5-10 seconds (when send_worker picks it up)\n")

print(f"{'='*60}")
print(f"CREATED {drafts_created} IMMEDIATE TEST DRAFTS")
print(f"{'='*60}")
print(f"""
Next steps:
  1. These drafts will be picked up by send_worker immediately
  2. Check your test emails in 5-30 seconds
  3. If in SPAM → expected during warm-up
  4. If in INBOX → great! Domain reputation looks good

Monitor by:
  - Check emails collection: 
    db.emails.find({{to_email: /mehars|abdrehman|webdeveloper/}})
  - Count sent: db.emails.count_documents({{status: 'sent'}})
  - Watch logs: tail -f scheduler.log | grep warmup_test

After confirmation:
  - Run setup_warmup_campaign.py for 4x daily scheduled sends
  - Monitor for 7-14 days
  - Then scale up production campaigns
""")
