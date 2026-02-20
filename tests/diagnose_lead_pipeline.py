"""
Diagnose the two lead pipeline bugs:
  1. sent_lead_ids type mismatch in get_pending_leads (ObjectId vs str)
  2. get_pending_followups returning 0 results

Run: source venv/bin/activate && python tests/diagnose_lead_pipeline.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db, Email, Campaign
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import config

emails_col    = db["emails"]
drafts_col    = db["email_drafts"]
leads_col     = db["leads"]


def section(title):
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")


# ─────────────────────────────────────────────────────────────
# BUG 1: sent_lead_ids type mismatch
# ─────────────────────────────────────────────────────────────
section("BUG 1 — sent_lead_ids type mismatch")

raw_ids = emails_col.distinct("lead_id", {"status": {"$in": ["sent", "opened", "replied"]}})
print(f"  emails.distinct('lead_id') → {len(raw_ids)} values")
if raw_ids:
    sample = raw_ids[0]
    print(f"  Sample type: {type(sample).__name__}  value: {sample}")
    # Simulate the bug
    lead_id_str = str(sample)
    in_set = lead_id_str in set(raw_ids)
    print(f"  str(id) in set(ObjectIds) → {in_set}  ← should be True if fix is applied")
    if not in_set:
        print("  ⚠️  BUG CONFIRMED: string never matches ObjectId in set!")
        print("  FIX: use set(str(oid) for oid in raw_ids)")
    else:
        print("  ✅  No type mismatch detected")

total_sent_leads_objectid = len(set(raw_ids))
total_sent_leads_str      = len(set(str(x) for x in raw_ids))
print(f"\n  Total sent lead IDs (ObjectId set): {total_sent_leads_objectid}")
print(f"  Total sent lead IDs (str set):      {total_sent_leads_str}")

# ─────────────────────────────────────────────────────────────
# How many leads does get_pending_leads actually see as "free"?
# ─────────────────────────────────────────────────────────────
section("Lead Inventory Breakdown")

cutoff_date = datetime(2026, 1, 29, 0, 0, 0)

sent_lead_ids_str = set(str(x) for x in raw_ids)  # correct version
drafted_lead_ids  = set(
    str(oid) for oid in drafts_col.distinct(
        "lead_id", {"status": {"$nin": ["failed", "skipped"]}}
    )
)

total_leads = leads_col.count_documents({})
post_cutoff = leads_col.count_documents({"created_at": {"$gte": cutoff_date}})
invalid     = leads_col.count_documents({"email_invalid": True, "created_at": {"$gte": cutoff_date}})

print(f"  Total leads:              {total_leads}")
print(f"  Created after Jan 29:     {post_cutoff}")
print(f"  Invalid (after cutoff):   {invalid}")
print(f"  Sent lead IDs (emails):   {len(sent_lead_ids_str)}")
print(f"  Drafted lead IDs:         {len(drafted_lead_ids)}")

# Simulate the full filter
INVALID_COMPANY_NAMES = {
    "stealth startup", "stealth mode", "stealth", "stealth company",
    "undisclosed", "n/a", "none", "unknown", "confidential",
    "private company", "stealth mode startup",
}

import pymongo
eligible = 0
no_company = 0
dnc = 0
already_sent = 0
already_drafted = 0
no_email = 0

for lead in leads_col.find({"created_at": {"$gte": cutoff_date}, "email_invalid": {"$ne": True}}).sort("created_at", pymongo.ASCENDING).limit(5000):
    lid = str(lead["_id"])
    email = lead.get("email", "")
    company = (lead.get("company") or lead.get("company_name") or "").strip()

    if lid in sent_lead_ids_str:
        already_sent += 1
        continue
    if lid in drafted_lead_ids:
        already_drafted += 1
        continue
    if not email:
        no_email += 1
        continue
    if company.lower() in INVALID_COMPANY_NAMES or not company:
        no_company += 1
        continue
    eligible += 1

print(f"\n  Simulated get_pending_leads filter (first 5000 leads post-cutoff):")
print(f"    Already sent (emails):    {already_sent}")
print(f"    Already drafted:          {already_drafted}")
print(f"    No email:                 {no_email}")
print(f"    No/invalid company:       {no_company}")
print(f"    ✅ Eligible (new leads):  {eligible}")

# How many pass the BROKEN filter (ObjectId set)?
broken_eligible = 0
broken_sent_ids = set(raw_ids)  # ObjectIds -- this is the bugged version
for lead in leads_col.find({"created_at": {"$gte": cutoff_date}, "email_invalid": {"$ne": True}}).sort("created_at", pymongo.ASCENDING).limit(5000):
    lid = str(lead["_id"])
    lid_oid = lead["_id"]
    company = (lead.get("company") or lead.get("company_name") or "").strip()
    if lid_oid in broken_sent_ids:  # ObjectId comparison — works
        continue
    if lid in drafted_lead_ids:
        continue
    if not lead.get("email", ""):
        continue
    if company.lower() in INVALID_COMPANY_NAMES or not company:
        continue
    broken_eligible += 1

print(f"\n  With BROKEN filter (ObjectId set, same as current code):")
print(f"    ✅ Eligible: {broken_eligible}  ← should match above if fix works")

# ─────────────────────────────────────────────────────────────
# BUG 2: get_pending_followups returning 0
# ─────────────────────────────────────────────────────────────
section("BUG 2 — get_pending_followups analysis")

active_campaigns = Campaign.get_active_campaigns()
print(f"  Active campaigns: {len(active_campaigns)}")

now = datetime.utcnow()
cutoff_3d = now - timedelta(days=config.FOLLOWUP_1_DELAY_DAYS)
cutoff_6d = now - timedelta(days=config.FOLLOWUP_2_DELAY_DAYS)

print(f"  FOLLOWUP_1_DELAY_DAYS: {config.FOLLOWUP_1_DELAY_DAYS}  (cutoff: {cutoff_3d.strftime('%Y-%m-%d')})")
print(f"  FOLLOWUP_2_DELAY_DAYS: {config.FOLLOWUP_2_DELAY_DAYS}  (cutoff: {cutoff_6d.strftime('%Y-%m-%d')})")
print(f"  MAX_FOLLOWUPS: {config.MAX_FOLLOWUPS}")

for camp in active_campaigns:
    cid = str(camp["_id"])
    cid_oid = camp["_id"]

    # How many sent emails with message_id for this campaign?
    sent_with_msgid = emails_col.count_documents({
        "campaign_id": cid_oid,
        "status": "sent",
        "message_id": {"$exists": True, "$ne": None}
    })
    # How many are old enough for followup 1?
    old_enough = emails_col.count_documents({
        "campaign_id": cid_oid,
        "status": "sent",
        "message_id": {"$exists": True, "$ne": None},
        "sent_at": {"$lt": cutoff_3d}
    })
    # Run actual get_pending_followups query
    fu1 = Email.get_pending_followups(cid, config.FOLLOWUP_1_DELAY_DAYS)
    fu2 = Email.get_pending_followups(cid, config.FOLLOWUP_2_DELAY_DAYS)

    name = camp.get("name", cid[:12])
    print(f"\n  Campaign: {name}")
    print(f"    Sent emails w/ message_id: {sent_with_msgid}")
    print(f"    Old enough (>{config.FOLLOWUP_1_DELAY_DAYS}d): {old_enough}")
    print(f"    get_pending_followups(delay={config.FOLLOWUP_1_DELAY_DAYS}d) → {len(fu1)} eligible")
    print(f"    get_pending_followups(delay={config.FOLLOWUP_2_DELAY_DAYS}d) → {len(fu2)} eligible")
    if old_enough > 0 and len(fu1) == 0:
        print(f"    ⚠️  BUG: {old_enough} emails old enough but 0 followups found!")
        # Check a sample
        sample = emails_col.find_one({
            "campaign_id": cid_oid,
            "status": "sent",
            "message_id": {"$exists": True, "$ne": None},
            "sent_at": {"$lt": cutoff_3d}
        })
        if sample:
            print(f"    Sample email: lead={sample.get('lead_id')}  sent_at={sample.get('sent_at')}  email_count=?")
            # Check email_count for this lead
            ec = emails_col.count_documents({"lead_id": sample["lead_id"], "campaign_id": cid_oid, "status": "sent"})
            print(f"    email_count for that lead: {ec}  (MAX_FOLLOWUPS+1={config.MAX_FOLLOWUPS+1}, must be < this)")
