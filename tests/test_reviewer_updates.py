#!/usr/bin/env python3
"""Test that problematic emails now fail the reviewer."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_reviewer import EmailReviewer

reviewer = EmailReviewer()

# Test bad emails that were being passed before
bad_emails = [
    {
        'subject': 'quick q',
        'body': '''random thought. 8tory scaling fast. 
scaling is hard. 
a SaaS firm raised Series A in 6 weeks.
thoughts?'''
    },
    {
        'subject': 'random thought',
        'body': '''random thought. OPENFIELD scaling fast.
growth is hard.
a SaaS company raised Series A in 6 weeks.
worth a chat?'''
    },
    {
        'subject': 'quick q',
        'body': '''random thought. curfex scaling must hurt.
Scaling is tough.
a FinTech company boosted throughput 2.7x in 10 weeks.
thoughts?'''
    },
    {
        'subject': 'quick q',
        'body': '''random thought. Daima Ventures scaling fast. 
raising funds is tough. 
a SaaS firm raised Series A in 6 weeks. 
thoughts?'''
    },
]

# Test good email that should pass
good_emails = [
    {
        'subject': 'quick thought',
        'body': '''hey, been looking at what Acme Corp is building in the fintech space.

most fintech teams we talk to are drowning in compliance while trying to ship fast.

worked with a similar company recently, they cracked 43% faster deploys in about 6 weeks.

make sense for you?'''
    },
]

lead = {'company': 'TestCompany', 'first_name': 'Test', 'industry': 'SaaS'}

print('Testing problematic emails that were previously passing...')
print('='*60)

all_failed = True
for i, email in enumerate(bad_emails, 1):
    result = reviewer.review_email(email, lead, save_review=False)
    status = '✅ PASS' if result.status.value == 'pass' else '❌ FAIL'
    if result.status.value == 'pass':
        all_failed = False
    print(f'\nBad Email {i}: {status} (score: {result.score})')
    if result.rule_violations:
        for v in result.rule_violations[:3]:
            print(f'  🚫 {v}')
    body_preview = email["body"].replace('\n', ' ')[:60]
    print(f'  Preview: {body_preview}...')

print('\n' + '='*60)
print('Testing good emails that should pass...')
print('='*60)

for i, email in enumerate(good_emails, 1):
    result = reviewer.review_email(email, lead, save_review=False)
    status = '✅ PASS' if result.status.value == 'pass' else '❌ FAIL'
    print(f'\nGood Email {i}: {status} (score: {result.score})')
    if result.rule_violations:
        for v in result.rule_violations[:3]:
            print(f'  🚫 {v}')

print('\n' + '='*60)
if all_failed:
    print('✅ SUCCESS: All bad emails are now being rejected!')
else:
    print('⚠️  WARNING: Some bad emails are still passing!')
