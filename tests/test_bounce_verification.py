"""Test verification of bounced emails"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_verifier import EmailVerifier, full_verify

# Bounced emails from logs
bounced_emails = [
    "ericdonzier@openfieldlive.com",
    "nbrown@preshift.io",
    "aresurreccion@etaka.ph",
    "rlee@honbu.io",
    "wkariuki@nanasi.co",
    "evan@omycarapp.com",
    "lkaufman@mypowerfarm.com",
    "coste@likehoop.com",
    "singh@pikme.io",
]

print('='*70)
print('VERIFYING BOUNCED EMAILS')
print('='*70)

verifier = EmailVerifier(skip_smtp_verify=False, smtp_timeout=15)

for email in bounced_emails:
    print(f"\nTesting: {email}")
    result = verifier.verify(email)
    print(f"  Status: {result.status.value}")
    print(f"  Score: {result.score}")
    print(f"  Safe to send: {result.is_safe_to_send()}")
    print(f"  Reason: {result.reason}")
    print(f"  Checks: {result.checks}")
