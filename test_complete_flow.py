#!/usr/bin/env python3
"""
Simulate the complete email sending flow to identify ALL blocking points
"""
from campaign_manager import CampaignManager
from zoho_sender import ZohoEmailSender
from database import BlockedAccounts, Campaign, Lead, Email
from datetime import datetime

print("=" * 70)
print("COMPLETE FLOW SIMULATION - FINDING ALL BLOCKING POINTS")
print("=" * 70)

# Step 1: Check pending leads
print("\n1️⃣  CHECKING PENDING LEADS")
print("-" * 70)
manager = CampaignManager()
pending_leads = manager.get_pending_leads(max_leads=20)
print(f"   Found {len(pending_leads)} pending leads")

if pending_leads:
    # Group by campaign
    by_campaign = {}
    for lead in pending_leads:
        cid = lead.get("campaign_id", "unknown")
        by_campaign[cid] = by_campaign.get(cid, 0) + 1
    
    print(f"   Grouped by campaign:")
    for cid, count in by_campaign.items():
        if cid == "unknown" or cid is None:
            print(f"     • No campaign: {count} leads")
        else:
            campaign = Campaign.get_by_id(cid)
            if campaign:
                print(f"     • {campaign.get('name')}: {count} leads")
            else:
                print(f"     • DELETED CAMPAIGN {cid}: {count} leads ⚠️")

# Step 2: Check email sender
print("\n2️⃣  CHECKING EMAIL SENDER")
print("-" * 70)
sender = ZohoEmailSender()
print(f"   Total accounts: {len(sender.accounts)}")

blocked = 0
at_limit = 0
available = 0

for account in sender.accounts:
    email = account["email"]
    is_blocked = BlockedAccounts.is_blocked(email)
    can_send, reason, remaining = sender._can_account_send(email)
    
    if is_blocked:
        blocked += 1
        print(f"   🔴 {email} - BLOCKED")
    elif not can_send:
        at_limit += 1
        print(f"   🟡 {email} - AT LIMIT ({reason})")
    else:
        available += 1
        print(f"   🟢 {email} - Available ({remaining} remaining)")

print(f"\n   Summary: {available} available, {at_limit} at limit, {blocked} blocked")

# Step 3: Test connect() method
print("\n3️⃣  TESTING connect() METHOD")
print("-" * 70)
connect_result = sender.connect()
print(f"   Result: {'✅ SUCCESS' if connect_result else '❌ FAILED'}")

if not connect_result:
    print("   ⚠️  THIS WILL BLOCK ALL EMAIL SENDING!")
    print("   Reason: send_initial_emails() checks connect() and returns error if False")
else:
    print("   ✅ At least one account connected successfully")

# Step 4: Check sending hours
print("\n4️⃣  CHECKING SENDING HOURS")
print("-" * 70)
can_send_now, reason = sender._can_send_now()
print(f"   Can send now: {'✅ YES' if can_send_now else '❌ NO'}")
if not can_send_now:
    print(f"   Reason: {reason}")
    print("   ⚠️  THIS WILL BLOCK ALL EMAIL SENDING!")

# Step 5: Simulate send_initial_emails flow
print("\n5️⃣  SIMULATING send_initial_emails() FLOW")
print("-" * 70)

if not pending_leads:
    print("   No pending leads to process")
else:
    # Take first lead as example
    test_lead = pending_leads[0]
    lead_email = test_lead.get("email")
    campaign_id = test_lead.get("campaign_id", "unknown")
    
    print(f"   Test lead: {lead_email}")
    print(f"   Campaign ID: {campaign_id}")
    
    # Check if campaign exists
    if campaign_id and campaign_id != "unknown":
        campaign = Campaign.get_by_id(campaign_id)
        if not campaign:
            print(f"   ⚠️  Campaign {campaign_id} NOT FOUND")
            print(f"   Before fix: Would raise ValueError and crash")
            print(f"   After fix: Treats as 'unknown' campaign")
    
    # Check deduplication
    lead_id = str(test_lead["_id"])
    if campaign_id != "unknown":
        existing = Email.get_by_lead_and_campaign(lead_id, campaign_id)
        if existing:
            print(f"   ⚠️  Lead already emailed in this campaign - will skip")
    
    if Email.has_been_contacted_by_email(lead_email):
        print(f"   ⚠️  Email address already contacted - will skip")

# Step 6: Check for other blocking conditions
print("\n6️⃣  CHECKING OTHER BLOCKING CONDITIONS")
print("-" * 70)

status = sender.get_sending_status()
print(f"   Total remaining capacity: {status['total_remaining']}")

if status['total_remaining'] == 0:
    print("   ⚠️  NO CAPACITY REMAINING - all accounts at daily limit")

# Final verdict
print("\n" + "=" * 70)
print("FINAL VERDICT")
print("=" * 70)

will_send = True
blockers = []

if not pending_leads:
    will_send = False
    blockers.append("No pending leads")

if not connect_result:
    will_send = False
    blockers.append("connect() failed - no accounts connected")

if not can_send_now:
    will_send = False
    blockers.append(f"Outside sending hours: {reason}")

if status['total_remaining'] == 0:
    will_send = False
    blockers.append("All accounts at daily limit")

if will_send:
    print("✅ EMAILS WILL BE SENT")
    print(f"   • {len(pending_leads)} pending leads ready")
    print(f"   • {available} accounts available")
    print(f"   • {status['total_remaining']} sending capacity remaining")
else:
    print("❌ EMAILS WILL NOT BE SENT")
    print("\nBlockers:")
    for blocker in blockers:
        print(f"   • {blocker}")

sender.disconnect_all()
print("\n" + "=" * 70)
