#!/usr/bin/env python3
"""
Test: How many of 28 requested leads actually get emails sent?

Checks historical data to see the conversion rate:
- Leads fetched vs emails sent
- Common filtering reasons
"""

from database import campaigns_collection, Email
from datetime import datetime, timedelta
from bson import ObjectId

print("📊 Historical Campaign Analysis: Leads Fetched vs Emails Sent")
print("=" * 70)

# Get last 10 campaigns
recent_campaigns = list(campaigns_collection.find({}).sort("created_at", -1).limit(10))

if not recent_campaigns:
    print("\n⚠️  No campaigns found in database")
    print("\nTo verify 28 leads → 28 emails:")
    print("1. Run a test campaign tomorrow")
    print("2. Monitor the logs for:")
    print("   - 'leads_fetched: X'")
    print("   - 'sent: Y'")
    print("   - Skip reasons (invalid, bounced, etc.)")
else:
    print(f"\nFound {len(recent_campaigns)} recent campaigns:\n")
    
    total_fetched = 0
    total_sent = 0
    
    for camp in recent_campaigns:
        name = camp.get('name', 'Unnamed')[:40]
        stats = camp.get('stats', {})
        leads = stats.get('total_leads', 0)
        sent = stats.get('emails_sent', 0)
        
        if leads > 0:
            conversion = int(sent / leads * 100) if leads else 0
            total_fetched += leads
            total_sent += sent
            
            print(f"{name:40} | Fetched: {leads:2} | Sent: {sent:2} | Rate: {conversion:3}%")
    
    print("\n" + "=" * 70)
    if total_fetched > 0:
        avg_conversion = int(total_sent / total_fetched * 100)
        print(f"AVERAGE CONVERSION: {total_sent}/{total_fetched} = {avg_conversion}%")
        print()
        print("Based on this data:")
        print(f"  - To send 28 emails: fetch {int(28 / (avg_conversion/100))} leads")
        print(f"  - With max_leads=28: expect ~{int(28 * avg_conversion/100)} emails sent")
    
print("\n" + "=" * 70)
print("RECOMMENDATION:")
print("=" * 70)
print()
print("Option 1: INCREASE max_leads in MongoDB config")
print("  Change: max_leads=28 → max_leads=40")
print("  Result: Fetch 40, send ~28-32 after filtering")
print()
print("Option 2: MONITOR first few days")
print("  Watch actual sent/fetched ratio")
print("  Adjust max_leads accordingly")
print()
print("Option 3: REDUCE verification strictness")
print("  Accept 'risky' emails (currently warns but continues)")
print("  May increase spam complaints")
