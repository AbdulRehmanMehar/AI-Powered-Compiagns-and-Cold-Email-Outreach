#!/usr/bin/env python3
"""
EMERGENCY DIAGNOSTIC AND FIX SCRIPT
Runs comprehensive checks and attempts auto-recovery
"""

import sys
from database import db
from datetime import datetime, timedelta
import subprocess
import os

print("🚨 EMERGENCY DIAGNOSTIC STARTING...")
print("=" * 80)

# 1. Check MongoDB connection
try:
    db.command('ping')
    print("✅ MongoDB: Connected")
except Exception as e:
    print(f"❌ MongoDB: FAILED - {e}")
    sys.exit(1)

# 2. Check lead status data integrity
print("\n📊 LEAD STATUS AUDIT:")
total_leads = db.leads.count_documents({})
print(f"  Total leads in DB: {total_leads}")

status_breakdown = {}
for status in ['pending', 'sent', 'bounced', 'invalid', 'replied', 'do_not_contact']:
    count = db.leads.count_documents({'status': status})
    status_breakdown[status] = count
    print(f"    {status}: {count}")

# 3. Check for orphaned data
print("\n🔍 ORPHANED DATA CHECK:")
leads_with_sent_date = db.leads.count_documents({'initial_sent_at': {'$exists': True}})
leads_with_sent_status = db.leads.count_documents({'status': 'sent'})
print(f"  Leads with initial_sent_at: {leads_with_sent_date}")
print(f"  Leads with status='sent': {leads_with_sent_status}")

if leads_with_sent_date != leads_with_sent_status:
    print(f"  ⚠️  MISMATCH: {leads_with_sent_date - leads_with_sent_status} orphaned records!")
    
    # Find orphaned leads
    orphaned = list(db.leads.find({
        'initial_sent_at': {'$exists': True},
        'status': {'$ne': 'sent'}
    }).limit(10))
    
    print(f"\n  Sample orphaned leads:")
    for lead in orphaned:
        print(f"    - {lead.get('email')}: status={lead.get('status')}, sent_at={lead.get('initial_sent_at')}")

# 4. Check Groq usage
print("\n📈 GROQ API USAGE CHECK:")
try:
    result = subprocess.run(['python3', 'check_groq_usage.py'], 
                          capture_output=True, text=True, timeout=10)
    print(result.stdout)
except Exception as e:
    print(f"  ⚠️  Could not check Groq usage: {e}")

# 5. Check scheduler config
print("\n⚙️  SCHEDULER CONFIG:")
try:
    config = db.scheduler_config.find_one()
    if config:
        print(f"  Config found: {len(config.get('campaigns', []))} campaigns")
        print(f"  Max emails per day: {config.get('max_emails_per_day', 'N/A')}")
    else:
        print("  ❌ NO SCHEDULER CONFIG FOUND")
except Exception as e:
    print(f"  ❌ Error reading config: {e}")

# 6. Check for running processes
print("\n🔄 PROCESS CHECK:")
result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
if 'auto_scheduler' in result.stdout or 'main.py' in result.stdout:
    print("  ✅ Scheduler appears to be running")
    for line in result.stdout.split('\n'):
        if 'auto_scheduler' in line or 'main.py' in line:
            print(f"    {line}")
else:
    print("  ❌ NO SCHEDULER PROCESS RUNNING")

# 7. Suggest fixes
print("\n" + "=" * 80)
print("💡 RECOMMENDED FIXES:")
print("=" * 80)

fixes = []
if leads_with_sent_date != leads_with_sent_status:
    fixes.append("1. Fix orphaned leads with initial_sent_at but wrong status")
    
if status_breakdown.get('pending', 0) > 100:
    fixes.append(f"2. Investigate {status_breakdown['pending']} pending leads")

if 'NO SCHEDULER PROCESS RUNNING' in result.stdout:
    fixes.append("3. Restart auto_scheduler.py")
    
if not fixes:
    fixes.append("Run manual investigation of campaign failure at line 3806")

for fix in fixes:
    print(f"  {fix}")

print("\n" + "=" * 80)
print("🔧 AUTO-FIX OPTIONS:")
print("  Run: python3 fix_orphaned_leads.py  # Fix status mismatches")
print("  Run: python3 auto_scheduler.py       # Restart scheduler")
print("=" * 80)
