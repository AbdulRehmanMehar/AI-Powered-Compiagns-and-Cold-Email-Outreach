#!/usr/bin/env python3
"""Check warm-up status for all email accounts."""

import sys
sys.path.insert(0, '..')

from zoho_sender import ZohoEmailSender
from database import AccountMetadata, SendingStats
from datetime import datetime
import config

sender = ZohoEmailSender()

print("\n" + "=" * 70)
print("ACCOUNT WARM-UP STATUS")
print("=" * 70)

total_capacity = 0

for account in config.ZOHO_ACCOUNTS:
    email = account['email']
    
    # Get added_date from MongoDB
    added_date = AccountMetadata.get_added_date(email)
    
    if added_date:
        days_active = (datetime.utcnow() - added_date).days
        week = (days_active // 7) + 1
        days_left = 7 - (days_active % 7)
        limit = sender._get_daily_limit_for_account(email)
        sends_today = SendingStats.get_sends_today(email)
        total_capacity += limit
        
        print(f"\n{email}")
        print(f"  Added: {added_date.strftime('%Y-%m-%d')} ({days_active} days ago)")
        print(f"  Week {week} -> {limit} emails/day (sent {sends_today} today)")
        if week < 4:
            print(f"  Upgrades to Week {week+1} in {days_left} days")
        else:
            print(f"  FULLY WARMED UP!")
    else:
        limit = config.WARMUP_WEEK1_LIMIT
        total_capacity += limit
        print(f"\n{email}")
        print(f"  WARNING: No added_date in MongoDB!")
        print(f"  Defaulting to Week 1 -> {limit} emails/day")

print("\n" + "=" * 70)
print(f"Warm-up Schedule:")
print(f"  Week 1: {config.WARMUP_WEEK1_LIMIT} emails/day")
print(f"  Week 2: {config.WARMUP_WEEK2_LIMIT} emails/day")
print(f"  Week 3: {config.WARMUP_WEEK3_LIMIT} emails/day")
print(f"  Week 4+: {config.WARMUP_WEEK4_LIMIT} emails/day")
print(f"\nTotal daily capacity: {total_capacity} emails/day across {len(config.ZOHO_ACCOUNTS)} accounts")
print("=" * 70)
