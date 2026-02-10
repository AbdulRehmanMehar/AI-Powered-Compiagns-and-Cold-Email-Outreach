#!/usr/bin/env python3
"""
Test the complete email sending flow with the fixed connect() method
"""
from zoho_sender import ZohoEmailSender
from database import BlockedAccounts

print("=" * 60)
print("TESTING FIXED EMAIL SENDING FLOW")
print("=" * 60)

# Initialize sender
sender = ZohoEmailSender()

print(f"\nTotal accounts configured: {len(sender.accounts)}")
for i, account in enumerate(sender.accounts):
    email = account["email"]
    blocked = BlockedAccounts.is_blocked(email)
    status = "🔴 BLOCKED" if blocked else "🟢 Available"
    print(f"  [{i+1}] {email} - {status}")

# Test connect() method (the fixed one)
print("\n" + "=" * 60)
print("Testing connect() method (tries all accounts)...")
print("=" * 60)

success = sender.connect()

if success:
    print("\n✅ SUCCESS - At least one account connected")
    print("   Emails WILL be sent")
else:
    print("\n❌ FAILED - No accounts available")
    print("   Emails will NOT be sent")
    
# Check get_sending_status
print("\n" + "=" * 60)
print("Sending Status")
print("=" * 60)

status = sender.get_sending_status()
print(f"Can send now: {status['can_send_now']}")
print(f"Total remaining capacity today: {status['total_remaining']}")

if not status['can_send_now']:
    print(f"⚠️  Reason: {status.get('time_reason', 'Unknown')}")

# Cleanup
sender.disconnect_all()

print("\n" + "=" * 60)
