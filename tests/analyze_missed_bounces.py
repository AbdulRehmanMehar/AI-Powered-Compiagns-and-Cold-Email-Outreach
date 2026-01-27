"""Analyze the 7 remaining missed bounced emails"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dns.resolver

missed_emails = [
    'graemew@virtusa.com',
    'mohammed.ziauddin@usrealco.com', 
    'roy@xray.tech',
    'in@repairservicesindia.com',
    'cweirich@centrias.de',
    'fazmercadoapp@fazmercado.com',
    'malikove@taxmaro.com',
]

print('=' * 80)
print('Analyzing Remaining Missed Bounces')
print('=' * 80)
print()

for email in missed_emails:
    domain = email.split('@')[1]
    local = email.split('@')[0]
    
    print(f'{email}')
    print(f'  Local part: "{local}" (length: {len(local)})')
    print(f'  Domain: {domain}')
    
    # Check MX
    try:
        mx = dns.resolver.resolve(domain, 'MX')
        mx_hosts = [str(r.exchange).rstrip('.') for r in mx]
        print(f'  MX Records: ✓ {mx_hosts[:2]}')
    except Exception as e:
        print(f'  MX Records: ✗ Failed ({e})')
    
    # Pattern analysis
    issues = []
    if len(local) < 3:
        issues.append('Very short local part')
    if len(local) < 4:
        issues.append('Short local part (<4 chars)')
    if local == domain.split('.')[0]:
        issues.append('Local matches company name (suspicious)')
    if local.startswith(domain.split('.')[0]):
        issues.append('Local starts with company name')
    
    print(f'  Patterns: {issues or "None detected"}')
    print()

print('=' * 80)
print('CONCLUSION:')
print('=' * 80)
print('''
These 7 emails are the hardest to catch without SMTP verification:
- They have valid domains with MX records
- The email format looks legitimate
- They just happen to be invalid mailboxes (person left company, typo, etc.)

Options to catch these:
1. SMTP verification (slow, ~1-5 seconds per email, may be blocked)
2. Use an email verification API like:
   - ZeroBounce ($15/10K verifications)
   - NeverBounce ($8/10K verifications) 
   - Hunter.io (100 free/month, $49/10K)
3. Build a bounced-domain tracker (learn from our own bounces)

Recommendation: Add SMTP verification for new leads and use a 
paid API for high-volume verification.
''')

# Check for short local parts
print('Potential new rule: Skip emails where local part is very short?')
for email in missed_emails:
    local = email.split('@')[0]
    if len(local) <= 3:
        print(f'  Would catch: {email} (local="{local}", len={len(local)})')
