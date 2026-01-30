#!/usr/bin/env python3
"""
Test SMTP connections for all Zoho accounts
"""
import smtplib
from config import ZOHO_ACCOUNTS, ZOHO_SMTP_HOST, ZOHO_SMTP_PORT

print("=" * 60)
print("TESTING SMTP CONNECTIONS")
print("=" * 60)

results = []

for i, account in enumerate(ZOHO_ACCOUNTS):
    email = account["email"]
    password = account["password"]
    name = account["sender_name"]
    
    print(f"\n[{i+1}/{len(ZOHO_ACCOUNTS)}] Testing {email} ({name})...")
    
    try:
        server = smtplib.SMTP(ZOHO_SMTP_HOST, ZOHO_SMTP_PORT, timeout=10)
        server.set_debuglevel(0)
        server.starttls()
        server.login(email, password)
        server.quit()
        
        print(f"  ✅ SUCCESS - Connection established")
        results.append((email, True, None))
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"  ❌ AUTH FAILED - Invalid credentials")
        print(f"     Error: {e}")
        results.append((email, False, "Authentication failed"))
        
    except smtplib.SMTPException as e:
        print(f"  ❌ SMTP ERROR - {e}")
        results.append((email, False, f"SMTP error: {e}"))
        
    except Exception as e:
        print(f"  ❌ CONNECTION FAILED - {e}")
        results.append((email, False, f"Connection error: {e}"))

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

success_count = sum(1 for _, success, _ in results if success)
fail_count = len(results) - success_count

print(f"✅ Working accounts: {success_count}/{len(results)}")
print(f"❌ Failed accounts: {fail_count}/{len(results)}")

if fail_count > 0:
    print("\nFailed accounts:")
    for email, success, error in results:
        if not success:
            print(f"  • {email}: {error}")

print("\n" + "=" * 60)
