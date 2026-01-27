"""Analyze bounce patterns to understand why emails are bouncing"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
import config
from collections import Counter

client = MongoClient(config.DATABASE_URL)
db = client.get_database()

# Get bounce stats
total = db['emails'].count_documents({})
bounced = db['emails'].count_documents({'status': 'bounced'})
sent = db['emails'].count_documents({'status': 'sent'})

print('='*60)
print('Email Bounce Analysis')
print('='*60)
print(f'\nEmail Stats:')
print(f'  Total emails: {total}')
print(f'  Sent: {sent}')
print(f'  Bounced: {bounced}')
if (sent + bounced) > 0:
    print(f'  Bounce Rate: {bounced/(sent+bounced)*100:.1f}%')

# Analyze bounced email patterns
print('\n' + '-'*60)
print('Bounced Email Analysis')
print('-'*60)

bounced_emails = list(db['emails'].aggregate([
    {"$match": {"status": "bounced"}},
    {"$lookup": {"from": "leads", "localField": "lead_id", "foreignField": "_id", "as": "lead"}},
    {"$unwind": "$lead"},
    {"$project": {"email": "$lead.email", "company": "$lead.company", "error_message": 1}}
]))

print(f'\nTotal bounced emails with lead data: {len(bounced_emails)}')

# Check domain patterns
domains = []
for e in bounced_emails:
    email = e.get('email', '')
    if '@' in email:
        domains.append(email.split('@')[1])
    else:
        domains.append('unknown')

domain_counts = Counter(domains)
print('\nBounced by domain (top 15):')
for domain, count in domain_counts.most_common(15):
    print(f'  {domain}: {count}')

# Check for patterns in bounced emails
print('\nBounced email type patterns:')
patterns = {'personal': 0, 'role_based': 0, 'company': 0}
role_prefixes = ['info', 'support', 'admin', 'contact', 'hello', 'sales', 'team', 'office', 'hr', 'jobs', 'careers']
personal_domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com', 'aol.com', 'protonmail.com']

for e in bounced_emails:
    email = e.get('email', '').lower()
    local_part = email.split('@')[0] if '@' in email else ''
    domain = email.split('@')[1] if '@' in email else ''
    
    if any(local_part == r or local_part.startswith(r + '.') for r in role_prefixes):
        patterns['role_based'] += 1
    elif domain in personal_domains:
        patterns['personal'] += 1
    else:
        patterns['company'] += 1

print(f'  Role-based (info@, support@, etc): {patterns["role_based"]}')
print(f'  Personal domains (gmail, yahoo): {patterns["personal"]}')
print(f'  Company emails: {patterns["company"]}')

# Show actual bounced emails
print('\n' + '-'*60)
print('Sample of Bounced Emails:')
print('-'*60)
for e in bounced_emails[:20]:
    email = e.get('email', 'N/A')
    company = e.get('company', 'N/A')
    error = e.get('error_message', 'N/A')
    print(f'  {email} ({company})')
    if error and error != 'N/A':
        print(f'    Error: {error[:80]}...' if len(str(error)) > 80 else f'    Error: {error}')

# Check error messages
print('\n' + '-'*60)
print('Bounce Error Types:')
print('-'*60)
errors = [e.get('error_message', 'unknown') for e in bounced_emails]
error_types = Counter()
for err in errors:
    if err is None:
        error_types['No error message'] += 1
    elif '550' in str(err) or 'not exist' in str(err).lower() or 'unknown user' in str(err).lower():
        error_types['Invalid/Non-existent mailbox'] += 1
    elif '553' in str(err) or 'relay' in str(err).lower():
        error_types['Relay denied'] += 1
    elif '552' in str(err) or 'quota' in str(err).lower():
        error_types['Mailbox full'] += 1
    elif 'timeout' in str(err).lower() or 'connection' in str(err).lower():
        error_types['Connection/Timeout'] += 1
    elif 'spam' in str(err).lower() or 'blocked' in str(err).lower():
        error_types['Blocked/Spam'] += 1
    else:
        error_types['Other'] += 1

for error_type, count in error_types.most_common():
    print(f'  {error_type}: {count}')
