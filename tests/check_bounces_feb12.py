"""
Quick bounce diagnostic for Feb 12, 2026
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import emails_collection
from datetime import datetime, timedelta
from collections import Counter

# Check recent bounces
week_ago = datetime.now() - timedelta(days=7)
all_bounces = list(emails_collection.find({
    'status': 'bounced',
    'created_at': {'$gte': week_ago}
}).sort('created_at', -1))

print(f"📊 BOUNCE ANALYSIS (Last 7 Days)")
print("=" * 80)
print(f"Total bounces: {len(all_bounces)}\n")

# Group by date
by_date = {}
for b in all_bounces:
    date_str = b['created_at'].strftime('%Y-%m-%d')
    if date_str not in by_date:
        by_date[date_str] = []
    by_date[date_str].append(b)

print("Daily breakdown:")
for date in sorted(by_date.keys(), reverse=True):
    print(f"  {date}: {len(by_date[date])} bounces")

# Domain analysis
print("\nTop bouncing domains:")
domains = Counter()
for b in all_bounces:
    email = b.get('to_email', '')
    if '@' in email:
        domains[email.split('@')[1]] += 1

for domain, count in domains.most_common(5):
    print(f"  {domain}: {count}")

# Check if harmonic.ai is the issue
harmonic_bounces = [b for b in all_bounces if 'harmonic.ai' in b.get('to_email', '')]
print(f"\nharmonic.ai specific: {len(harmonic_bounces)} bounces")

if harmonic_bounces:
    print("\nSample harmonic.ai bounces:")
    for b in harmonic_bounces[:5]:
        print(f"  {b.get('to_email')} - sent: {b.get('sent_at', 'N/A')}")

# Check recent sends
three_days = datetime.now() - timedelta(days=3)
sent_count = emails_collection.count_documents({
    'status': 'sent',
    'sent_at': {'$gte': three_days}
})

print(f"\n📧 Activity:")
print(f"  Emails sent (last 3 days): {sent_count}")
print(f"  Bounce rate: {len(all_bounces) / max(sent_count, 1) * 100:.1f}%")

# TODAY's bounces
today_start = datetime(2026, 2, 12, 0, 0, 0)
today_bounces = [b for b in all_bounces if b['created_at'] >= today_start]
print(f"\n🚨 TODAY (Feb 12):")
print(f"  Bounces detected: {len(today_bounces)}")

if today_bounces:
    for b in today_bounces:
        print(f"  - {b.get('to_email')} at {b['created_at']}")
