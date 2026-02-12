"""
Check if lead pipeline can support GLOBAL_DAILY_TARGET=300
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from campaign_manager import CampaignManager
from database import leads_collection, emails_collection, db
from datetime import datetime, timedelta

email_drafts_collection = db["email_drafts"]

# Check pending leads
cm = CampaignManager()
pending = cm.get_pending_leads(max_leads=500)

print(f'📊 LEAD PIPELINE STATUS FOR 300/DAY TARGET')
print('='*70)
print(f'Pending leads (ready to email): {len(pending)}')

# Check draft queue
ready_drafts = email_drafts_collection.count_documents({'status': 'ready'})
generating_drafts = email_drafts_collection.count_documents({'status': 'generating'})
print(f'Ready-to-send drafts: {ready_drafts}')
print(f'Generating drafts: {generating_drafts}')

# Check sends in last 24h
yesterday = datetime.now() - timedelta(hours=24)
sent_24h = emails_collection.count_documents({
    'status': 'sent',
    'sent_at': {'$gte': yesterday}
})
print(f'\nEmails sent (last 24h): {sent_24h}')

print('\n' + '='*70)
print('ANALYSIS FOR GLOBAL_DAILY_TARGET=300:')
print('='*70)

# Can we support 300/day?
total_available = len(pending) + ready_drafts
print(f'\n1️⃣  CURRENT CAPACITY:')
print(f'   Pending leads + Ready drafts = {total_available}')
if total_available >= 300:
    print(f'   ✅ CAN support 300 emails today')
else:
    print(f'   ❌ CANNOT support 300 — short by {300 - total_available} leads')

# How does the system get more leads?
print(f'\n2️⃣  HOW SYSTEM FETCHES LEADS:')
print(f'   • Scheduled campaigns run at specific times (09:00, 09:30, etc.)')
print(f'   • Each campaign fetches max_leads from RocketReach')
print(f'   • Current config: campaigns fetch 15-28 leads each')
print(f'   • NO feedback loop to reach daily target')

# The problem
print(f'\n3️⃣  THE PROBLEM:')
print(f'   ❌ System runs campaigns ONCE per schedule (e.g., 09:00 AM)')
print(f'   ❌ If campaign fetches 28 leads, that\'s ALL for that run')
print(f'   ❌ No "keep fetching until we hit 300" logic')
print(f'   ❌ Campaigns run on specific days (Mon/Tue/Thu/Fri only)')

# What happens
print(f'\n4️⃣  WHAT ACTUALLY HAPPENS:')
print(f'   • Morning: Campaign runs, fetches 28 leads')
print(f'   • System generates drafts for those 28 leads')
print(f'   • System sends those 28 emails throughout the day')
print(f'   • Daily total: ~28-56 emails (not 300)')

print(f'\n5️⃣  TO HIT 300/DAY, YOU NEED:')
print(f'   ✅ EITHER: Multiple campaigns throughout the day')
print(f'      - 09:00: fetch 50 leads')
print(f'      - 11:00: fetch 50 leads')
print(f'      - 13:00: fetch 50 leads')
print(f'      - 15:00: fetch 50 leads')
print(f'      - 17:00: fetch 50 leads')
print(f'      - etc.')
print(f'   ✅ OR: Increase max_leads per campaign to ~300')
print(f'   ✅ OR: Implement adaptive campaign logic (fetch more if under target)')

print(f'\n6️⃣  CURRENT BOTTLENECK:')
print(f'   • RocketReach API quota')
print(f'   • Campaign schedule (only runs at fixed times)')
print(f'   • max_leads hardcoded in scheduler_config.json')

print('\n' + '='*70)
