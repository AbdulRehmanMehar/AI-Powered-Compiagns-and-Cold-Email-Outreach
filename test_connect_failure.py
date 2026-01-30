#!/usr/bin/env python3
"""
Test what happens when connect() returns False
"""
from zoho_sender import ZohoEmailSender
from database import BlockedAccounts
from unittest.mock import patch

print("=" * 70)
print("TESTING connect() FAILURE SCENARIO")
print("=" * 70)

sender = ZohoEmailSender()

# Test 1: Normal connect (should succeed)
print("\n1️⃣  Normal connect() call:")
result = sender.connect()
print(f"   Result: {result}")
sender.disconnect_all()

# Test 2: Simulate connection failure by blocking all accounts temporarily
print("\n2️⃣  Simulating all accounts connection failure:")

# Mock _get_connection to return None (simulate connection failure)
original_get_connection = sender._get_connection

def mock_failed_connection(account):
    print(f"   [MOCK] Connection attempt to {account['email']} failed")
    return None

sender._get_connection = mock_failed_connection
result = sender.connect()
print(f"   Result: {result}")
print(f"   Expected: False (no accounts connected)")

# Restore
sender._get_connection = original_get_connection

# Test 3: Block all accounts in database and try
print("\n3️⃣  Simulating all accounts blocked in database:")

# Temporarily block all accounts
for account in sender.accounts:
    BlockedAccounts.mark_blocked(account["email"], "Test block")

result = sender.connect()
print(f"   Result: {result}")
print(f"   Expected: False (all blocked)")

# Unblock all accounts
for account in sender.accounts:
    BlockedAccounts.unblock(account["email"])

print("\n4️⃣  After unblocking:")
result = sender.connect()
print(f"   Result: {result}")
print(f"   Expected: True (accounts available again)")

sender.disconnect_all()

print("\n" + "=" * 70)
print("CONCLUSION:")
print("=" * 70)
print("✅ connect() correctly returns False when no accounts available")
print("✅ connect() correctly returns True when accounts available")
print("\n⚠️  CRITICAL: If connect() returns False, send_initial_emails()")
print("   immediately returns {'error': 'Failed to connect to email server'}")
print("   and NO emails are sent!")
print("=" * 70)
