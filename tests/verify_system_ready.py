#!/usr/bin/env python3
"""
System Readiness Check — Verify campaigns, leads, drafts, and account health
Run this to diagnose why draft queue might be empty.
"""

import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db, Campaign, Lead, Email
from v2.account_pool import AccountReputation
import config

def main():
    print("=" * 70)
    print("  Cold Email System — Readiness Check")
    print("=" * 70)
    print()
    
    # 1. Check active campaigns
    print("🎯 ACTIVE CAMPAIGNS")
    print("-" * 70)
    active_campaigns = Campaign.get_active_campaigns()
    
    if not active_campaigns:
        print("❌ NO ACTIVE CAMPAIGNS FOUND!")
        print("   → System cannot send without at least one active campaign")
        print("   → Create a campaign or unpause existing ones")
        print()
    else:
        print(f"✅ Found {len(active_campaigns)} active campaign(s):")
        for camp in active_campaigns:
            print(f"   - {camp.get('name', 'Unnamed')} (ID: {camp['_id']})")
            print(f"     Created: {camp.get('created_at', 'Unknown')}")
            print(f"     End date: {camp.get('end_date', 'None')}")
            print(f"     ICP: {camp.get('icp', {}).get('title', 'Not set')}")
        print()
    
    # 2. Check pending leads (not contacted)
    print("👥 PENDING LEADS (Not Yet Contacted)")
    print("-" * 70)
    pending_leads = db.leads.count_documents({
        "contacted": False,
        "email_invalid": {"$ne": True}
    })
    dnc_count = db.do_not_contact.count_documents({})
    invalid_count = db.leads.count_documents({"email_invalid": True})
    
    print(f"   Pending (ready to contact): {pending_leads}")
    print(f"   Do Not Contact (DNC): {dnc_count}")
    print(f"   Invalid emails: {invalid_count}")
    
    if pending_leads == 0:
        print("   ⚠️  No pending leads! Adaptive campaign will fetch more at 09:00")
    elif pending_leads < 300:
        print(f"   ⚠️  Only {pending_leads} pending — may need more for 300/day target")
    else:
        print(f"   ✅ Sufficient leads for sending")
    print()
    
    # 3. Check draft queue
    print("📝 DRAFT QUEUE STATUS")
    print("-" * 70)
    drafts = db.email_drafts.aggregate([
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1}
            }
        }
    ])
    draft_stats = {d["_id"]: d["count"] for d in drafts}
    total_drafts = sum(draft_stats.values())
    
    if total_drafts == 0:
        print("   ❌ DRAFT QUEUE EMPTY!")
        print("   → Pre-generation hasn't run or failed")
        print("   → Check if pre-gen is scheduled for 17:30 ET")
        print("   → Adaptive campaign will trigger pre-gen at 09:00")
    else:
        print(f"   Total drafts: {total_drafts}")
        for status, count in draft_stats.items():
            emoji = "✅" if status == "ready" else "⏳" if status == "claimed" else "❌"
            print(f"   {emoji} {status}: {count}")
    print()
    
    # 4. Check today's sends
    print("📧 TODAY'S SENDING ACTIVITY")
    print("-" * 70)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = db.emails.count_documents({
        "sent_at": {"$gte": today_start},
        "status": {"$in": ["sent", "opened", "replied"]}
    })
    bounced_today = db.emails.count_documents({
        "sent_at": {"$gte": today_start},
        "status": "bounced"
    })
    
    print(f"   Sent today: {sent_today}/{config.GLOBAL_DAILY_TARGET if config.GLOBAL_DAILY_TARGET > 0 else 'N/A'}")
    print(f"   Bounced today: {bounced_today}")
    if sent_today > 0:
        bounce_rate = bounced_today / sent_today
        print(f"   Bounce rate: {bounce_rate:.1%}")
    print()
    
    # 5. Check account reputation
    print("💯 ACCOUNT REPUTATION")
    print("-" * 70)
    low_rep_count = 0
    paused_count = 0
    
    for account in config.ZOHO_ACCOUNTS:
        email = account["email"]
        rep = AccountReputation.get_saved_score(email)
        
        if not rep:
            print(f"   {email}: No reputation data yet")
            continue
        
        score = rep.get("score", 100)
        emoji = "✅" if score >= 60 else "⚠️" if score >= 40 else "❌"
        
        if score < 60:
            low_rep_count += 1
        if score < 40:
            paused_count += 1
        
        status = "PAUSED" if score < 40 else "LOW" if score < 60 else "OK"
        print(f"   {emoji} {email}: {score}/100 ({status})")
        
        if score < 60:
            print(f"      Reason: {rep.get('reason', 'N/A')}")
            print(f"      Bounce rate: {rep.get('bounce_rate', 0):.1%}")
            print(f"      Total sent: {rep.get('total_sent', 0)}")
    
    if paused_count > 0:
        print(f"\n   ❌ {paused_count} account(s) auto-paused (score < 40)")
    if low_rep_count > 0:
        print(f"   ⚠️  {low_rep_count} account(s) flagged low reputation")
    print()
    
    # 6. Check for blockers
    print("🚦 BLOCKING ISSUES")
    print("-" * 70)
    blockers = []
    warnings = []
    
    if not active_campaigns:
        blockers.append("No active campaigns")
    
    if total_drafts == 0 and pending_leads == 0:
        blockers.append("No drafts AND no pending leads")
    
    if paused_count == len(config.ZOHO_ACCOUNTS):
        blockers.append("ALL accounts are paused (reputation < 40)")
    
    if paused_count > len(config.ZOHO_ACCOUNTS) / 2:
        warnings.append(f"{paused_count}/{len(config.ZOHO_ACCOUNTS)} accounts paused")
    
    if total_drafts == 0:
        warnings.append("Draft queue empty — system won't send until pre-gen runs")
    
    if pending_leads < 300:
        warnings.append(f"Only {pending_leads} pending leads — may not hit 300/day target")
    
    if blockers:
        print("   ❌ BLOCKERS (must fix):")
        for b in blockers:
            print(f"      • {b}")
    else:
        print("   ✅ No critical blockers")
    
    if warnings:
        print("\n   ⚠️  WARNINGS (review):")
        for w in warnings:
            print(f"      • {w}")
    
    if not blockers and not warnings:
        print("   ✅ System is healthy and ready to send!")
    
    print()
    
    # 7. Next steps
    print("📋 NEXT STEPS")
    print("-" * 70)
    
    if blockers:
        print("   1. Fix blocking issues above")
        if not active_campaigns:
            print("      → Create/unpause a campaign")
        if total_drafts == 0 and pending_leads == 0:
            print("      → Fetch leads via adaptive campaign or run campaign manually")
    else:
        now_et = datetime.utcnow() - timedelta(hours=5)  # Rough EST/EDT
        current_hour = now_et.hour
        
        if total_drafts == 0:
            if current_hour < 17:
                print("   1. Pre-gen scheduled for 17:30 ET today")
                print("   2. If empty by 09:00 tomorrow, adaptive campaign will fetch leads")
            else:
                print("   1. Pre-gen should have run at 17:30 ET")
                print("   2. Check scheduler logs for pre-gen errors")
                print("   3. Adaptive campaign will fetch leads at 09:00 tomorrow")
        else:
            print("   1. System ready — will start sending at 09:00 ET")
            print(f"   2. Monitor logs and bounce rates")
            print(f"   3. Target: {config.GLOBAL_DAILY_TARGET}/day")
    
    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
