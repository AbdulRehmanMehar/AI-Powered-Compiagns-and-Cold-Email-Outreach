"""Check sending stats and daily limits."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from datetime import datetime
import config

# Check sending stats
stats = list(db['sending_stats'].find().sort('date', -1).limit(20))
print('📊 SENDING STATS (Recent):')
print('='*60)

by_date = {}
for s in stats:
    date = s.get('date', 'unknown')
    if date not in by_date:
        by_date[date] = []
    by_date[date].append(s)

for date, entries in sorted(by_date.items(), reverse=True)[:3]:
    print(f'\n📅 {date}:')
    total = 0
    for e in entries:
        account = e.get('account_email', 'unknown')
        sent = e.get('emails_sent', 0)
        total += sent
        print(f'   {account}: {sent} emails')
    print(f'   TOTAL: {total}')

# Check daily limit config
print(f'\n⚙️ CONFIG:')
limit = getattr(config, 'MAX_EMAILS_PER_ACCOUNT_PER_DAY', 25)
print(f'   MAX_EMAILS_PER_ACCOUNT_PER_DAY: {limit}')
print(f'   Accounts: {len(config.ZOHO_ACCOUNTS)}')
print(f'   Theoretical daily capacity: {len(config.ZOHO_ACCOUNTS) * limit}')

# Check if any accounts have capacity left today
today = datetime.utcnow().strftime('%Y-%m-%d')
print(f'\n📅 TODAY ({today}):')
today_stats = [s for s in stats if s.get('date') == today]
for account in config.ZOHO_ACCOUNTS:
    email = account['email']
    sent_today = next((s.get('emails_sent', 0) for s in today_stats if s.get('account_email') == email), 0)
    remaining = limit - sent_today
    status = '✅' if remaining > 0 else '❌'
    print(f'   {status} {email}: {sent_today}/{limit} sent, {remaining} remaining')
