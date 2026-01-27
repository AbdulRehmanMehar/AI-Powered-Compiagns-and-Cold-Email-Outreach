"""Test SMTP verification against the remaining bounced emails"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rocketreach_client import verify_email_smtp, full_email_verification

# The 5 emails that passed quick checks but still bounced
remaining_bounced = [
    'graemew@virtusa.com',
    'mohammed.ziauddin@usrealco.com',
    'cweirich@centrias.de',
    'fazmercadoapp@fazmercado.com',
    'malikove@taxmaro.com',
    'mehars.6925@gmail.com'
]

print('=' * 80)
print('SMTP Verification Test (FREE)')
print('=' * 80)
print()
print('Testing against 5 emails that passed quick checks but still bounced...')
print('(This may take 5-25 seconds as we connect to each mail server)')
print()

caught = []
missed = []
inconclusive = []

for email in remaining_bounced:
    print(f'Testing: {email}...', end=' ', flush=True)
    
    is_valid, reason = verify_email_smtp(email, timeout=10)
    
    if is_valid is False:
        caught.append((email, reason))
        print(f'✓ CAUGHT - {reason}')
    elif is_valid is True:
        missed.append((email, reason))
        print(f'✗ MISSED - {reason}')
    else:
        inconclusive.append((email, reason))
        print(f'? INCONCLUSIVE - {reason}')

print()
print('=' * 80)
print('SMTP VERIFICATION RESULTS')
print('=' * 80)
print(f'Caught (would not send):    {len(caught)}/5')
print(f'Missed (would still send):  {len(missed)}/5')
print(f'Inconclusive:               {len(inconclusive)}/5')
print()

if caught:
    print('Caught emails:')
    for email, reason in caught:
        print(f'  ✓ {email}: {reason}')
    print()

if missed:
    print('Missed emails (SMTP said valid but actually bounced):')
    for email, reason in missed:
        print(f'  ✗ {email}: {reason}')
    print()

if inconclusive:
    print('Inconclusive (server blocked verification):')
    for email, reason in inconclusive:
        print(f'  ? {email}: {reason}')
    print()

# Calculate final projected bounce rate
print('=' * 80)
print('FINAL PROJECTED IMPACT')
print('=' * 80)
original_bounces = 56
original_total = 139
original_rate = original_bounces / original_total * 100

# Quick checks catch 13/18, SMTP catches additional ones
quick_catch = 13
smtp_catch = len(caught)
total_catch = quick_catch + smtp_catch
total_bounced = 18

catch_rate = total_catch / total_bounced
remaining_bounces = original_bounces * (1 - catch_rate)

print(f'Original bounce rate:     {original_rate:.1f}%')
print(f'Quick checks catch:       {quick_catch}/18 bounces (72.2%)')
print(f'SMTP catches additional:  {smtp_catch}/5 bounces')
print(f'Total caught:             {total_catch}/18 ({total_catch/total_bounced*100:.1f}%)')
print(f'Projected bounce rate:    ~{remaining_bounces/original_total*100:.1f}%')
