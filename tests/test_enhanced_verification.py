"""Test enhanced email verification against bounced emails"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rocketreach_client import quick_email_check, refresh_bounced_domains_cache

# Refresh cache to get latest bounced domains
refresh_bounced_domains_cache()

# All bounced emails from our analysis
bounced_emails = [
    'prakash.balaji@workflowautomation.in',
    'ss@workflowautomation.in',
    'ario@fonzy.co',
    'liam@google.com',
    'graemew@virtusa.com',
    'mohammed.ziauddin@usrealco.com',
    'vivek.tomar@coinbase.com',
    'roy@xray.tech',
    'robert.m@workflowautomation.in',
    'in@repairservicesindia.com',
    'mohsen.gh@bitpin.ir',
    'cweirich@centrias.de',
    'sarahkolawole@upwork.com',
    'fazmercadoapp@fazmercado.com',
    'dario@microsoft.com',
    'robertm@workflowautomation.in',
    'malikove@taxmaro.com',
    'prakashkuikel@developertools.bt',
]

print('=' * 80)
print('Email Verification Test - Enhanced')
print('=' * 80)

caught = []
missed = []

for email in bounced_emails:
    is_valid, reason = quick_email_check(email)
    
    if not is_valid:
        caught.append((email, reason))
        print(f'✓ CAUGHT: {email}')
        print(f'         Reason: {reason}')
    else:
        missed.append(email)
        print(f'✗ MISSED: {email} (would still send)')

print()
print('=' * 80)
print(f'SUMMARY:')
print(f'  Caught: {len(caught)}/{len(bounced_emails)} ({len(caught)/len(bounced_emails)*100:.1f}%)')
print(f'  Missed: {len(missed)}/{len(bounced_emails)} ({len(missed)/len(bounced_emails)*100:.1f}%)')
print('=' * 80)

if missed:
    print()
    print('Still missing these (would need SMTP verification):')
    for email in missed:
        print(f'  - {email}')

# Show impact on bounce rate
print()
print('=' * 80)
print('PROJECTED IMPACT')
print('=' * 80)
original_bounces = 56  # from our analysis
original_total = 139  # sent + bounced
original_rate = original_bounces / original_total * 100

# How many bounces would we catch?
catch_rate = len(caught) / len(bounced_emails)
new_bounces = original_bounces * (1 - catch_rate)
new_rate = new_bounces / (original_total - len(caught)) * 100

print(f'Original bounce rate: {original_rate:.1f}%')
print(f'With enhanced verification: ~{new_rate:.1f}%')
print(f'Improvement: {original_rate - new_rate:.1f} percentage points')
