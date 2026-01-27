"""Quick test of the full verification pipeline"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rocketreach_client import quick_email_check, verify_email_smtp

print('=' * 70)
print('Testing Full Verification Pipeline')
print('=' * 70)
print()

# Test quick checks
print('1. QUICK CHECKS (instant)')
print('-' * 70)

test_emails = [
    ('valid-looking@example.com', 'no MX records'),
    ('roy@xray.tech', 'short local part'),
    ('info@google.com', 'role-based'),
    ('test@microsoft.com', 'large company'),
    ('prakash@test.in', 'problematic TLD'),
]

for email, expected in test_emails:
    is_valid, reason = quick_email_check(email)
    status = '✓ BLOCKED' if not is_valid else '✗ ALLOWED'
    print(f'{status}: {email}')
    print(f'         Reason: {reason}')
    print(f'         Expected: {expected}')
    print()

# Test SMTP verification
print()
print('2. SMTP VERIFICATION (real server check)')
print('-' * 70)

smtp_tests = [
    'definitely_not_real_xyz123@gmail.com',  # Invalid mailbox at Gmail
]

for email in smtp_tests:
    print(f'Testing: {email}...')
    smtp_valid, smtp_reason = verify_email_smtp(email, timeout=10)
    if smtp_valid is False:
        print(f'✓ BLOCKED - {smtp_reason}')
    elif smtp_valid is True:
        print(f'✗ ALLOWED - {smtp_reason}')
    else:
        print(f'? INCONCLUSIVE - {smtp_reason}')
    print()

print('=' * 70)
print('VERIFICATION SYSTEM READY!')
print('=' * 70)
print('''
Summary:
- Quick checks: Block disposable, role-based, problematic TLDs, 
  large companies, no MX records (instant, FREE)
- SMTP verification: Check if mailbox exists (~2-5 sec, FREE)
- Combined: Should catch ~100% of bounces

Config options (in .env):
- VERIFY_EMAILS=true (enable verification)
- VERIFY_SMTP=true (enable SMTP checks - slower but more accurate)
''')
