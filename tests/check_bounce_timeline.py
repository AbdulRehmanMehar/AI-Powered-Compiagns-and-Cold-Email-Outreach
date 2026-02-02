#!/usr/bin/env python3
"""Analyze timeline of bounced emails vs when verification was added"""

from database import emails_collection, leads_collection
from datetime import datetime

print("=" * 70)
print("CRITICAL TIMELINE ANALYSIS: BOUNCED EMAILS vs VERIFICATION CODE")
print("=" * 70)

# When was verification code added? Jan 30, 2026
VERIFICATION_ADDED = datetime(2026, 1, 30)
print(f"\n📅 Email verification code added: {VERIFICATION_ADDED.strftime('%Y-%m-%d')}")

# Get all bounced emails with their sent dates
bounced = list(emails_collection.find({'status': 'bounced'}, {
    'recipient_email': 1, 
    'sent_at': 1, 
    'created_at': 1,
    'campaign_id': 1
}))

print(f"\n📊 Total bounced emails: {len(bounced)}")

# Categorize by when they were sent
before_verification = []
after_verification = []
no_date = []

for email in bounced:
    sent = email.get('sent_at') or email.get('created_at')
    if sent is None:
        no_date.append(email)
    elif sent < VERIFICATION_ADDED:
        before_verification.append(email)
    else:
        after_verification.append(email)

print(f"\n🔴 Sent BEFORE verification code (Jan 30): {len(before_verification)}")
print(f"🟢 Sent AFTER verification code (Jan 30):  {len(after_verification)}")
print(f"⚪ No date recorded:                        {len(no_date)}")

# This is the KEY question
if after_verification:
    print("\n" + "=" * 70)
    print("⚠️  CRITICAL: EMAILS BOUNCED EVEN AFTER VERIFICATION WAS ADDED!")
    print("=" * 70)
    print("\nEmails sent AFTER Jan 30 that still bounced:")
    for email in sorted(after_verification, key=lambda x: x.get('sent_at') or x.get('created_at'))[:20]:
        sent = email.get('sent_at') or email.get('created_at')
        recip = email['recipient_email']
        print(f"  - {recip[:40]:40} | Sent: {sent}")
    
    # Check if these leads had verification status
    print("\n--- Checking verification status for these leads ---")
    for email in after_verification[:10]:
        lead = leads_collection.find_one({'email': email['recipient_email']})
        if lead:
            v_status = lead.get('verification_status', 'NOT SET')
            e_verified = lead.get('email_verified', 'NOT SET')
            print(f"  {email['recipient_email'][:35]:35} | verification_status: {v_status}, email_verified: {e_verified}")

if before_verification:
    print("\n" + "-" * 70)
    print("📋 Emails sent BEFORE verification was added (expected to bounce):")
    for email in sorted(before_verification, key=lambda x: x.get('sent_at') or x.get('created_at'))[:15]:
        sent = email.get('sent_at') or email.get('created_at')
        recip = email.get('recipient_email', email.get('to_email', 'unknown'))
        print(f"  - {recip[:40]:40} | Sent: {sent}")

print("\n" + "=" * 70)
print("CONCLUSION:")
print("=" * 70)
if len(after_verification) == 0:
    print("✅ ALL bounced emails were sent BEFORE verification code was added.")
    print("   This explains the bounces - verification wasn't in place yet!")
else:
    pct = len(after_verification) / len(bounced) * 100
    print(f"⚠️  {len(after_verification)} emails ({pct:.1f}%) bounced AFTER verification was added.")
    print("   This indicates the verification code has bugs or isn't being called!")
