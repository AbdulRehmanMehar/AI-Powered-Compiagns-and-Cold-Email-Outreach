#!/usr/bin/env python3
"""Check if follow-up system is production ready."""

import sys
sys.path.insert(0, '..')

from database import SendingStats, AccountMetadata, Email, Campaign
from zoho_sender import ZohoEmailSender
import config

print("=" * 60)
print("FOLLOW-UP PRODUCTION READINESS CHECK")
print("=" * 60)

# 1. Check sending capacity
sender = ZohoEmailSender()
print("\n1. SENDING CAPACITY")
total_remaining = 0
for account in config.ZOHO_ACCOUNTS:
    email = account['email']
    can_send, reason, remaining = sender._can_account_send(email)
    total_remaining += remaining
    status = "Y" if can_send else "N"
    print(f"   [{status}] {email}: {remaining} remaining")
print(f"   Total remaining today: {total_remaining}")

# 2. Check follow-up detection
print("\n2. FOLLOW-UP DETECTION")
try:
    # Get active campaigns
    campaigns = Campaign.get_active_campaigns()
    total_followups = 0
    
    for campaign in campaigns:
        campaign_id = str(campaign["_id"])
        pending = Email.get_pending_followups(campaign_id, config.FOLLOWUP_DELAY_DAYS)
        if pending:
            print(f"   Campaign '{campaign.get('name', campaign_id)}': {len(pending)} pending follow-ups")
            total_followups += len(pending)
    
    if total_followups == 0:
        print("   No follow-ups pending")
    print(f"   Total follow-ups needed: {total_followups}")
except Exception as e:
    print(f"   ERROR: {e}")
    import traceback
    traceback.print_exc()
    total_followups = 0

# 3. Check if we can handle the load
print("\n3. CAPACITY VS DEMAND")
if total_remaining >= total_followups:
    print(f"   OK: {total_remaining} capacity >= {total_followups} follow-ups")
else:
    print(f"   WARN: {total_remaining} capacity < {total_followups} follow-ups")
    print(f"   Will send {total_remaining} today, {total_followups - total_remaining} tomorrow")

# 4. Check time window
print("\n4. SENDING WINDOW")
can_send_now, time_reason = sender._can_send_now()
if can_send_now:
    print(f"   OK: {time_reason}")
else:
    print(f"   BLOCKED: {time_reason}")

# 5. Summary
print("\n" + "=" * 60)
if total_remaining > 0 and can_send_now:
    print("RESULT: FOLLOW-UP SYSTEM IS PRODUCTION READY")
    print(f"Can send up to {min(total_remaining, total_followups)} follow-ups now")
elif total_remaining > 0:
    print("RESULT: READY - WAITING FOR SEND WINDOW")
else:
    print("RESULT: NO CAPACITY - TRY TOMORROW")
print("=" * 60)
