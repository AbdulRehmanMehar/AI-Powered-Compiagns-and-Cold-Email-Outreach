"""Check why leads are being skipped — draft dedup analysis."""
from database import db

# Count leads that have drafts (non-failed, non-skipped)
leads_with_drafts = db["email_drafts"].distinct("lead_id", {
    "status": {"$nin": ["failed", "skipped"]}
})
print(f"Leads with active drafts (not failed/skipped): {len(leads_with_drafts)}")

# Count leads with ANY draft at all
all_drafted = db["email_drafts"].distinct("lead_id")
print(f"Leads with ANY draft (including failed): {len(all_drafted)}")

# Leads contacted via emails collection
contacted = set(str(r["_id"]) for r in db["emails"].aggregate([
    {"$match": {"status": "sent"}},
    {"$group": {"_id": "$lead_id"}}
]))
print(f"Leads contacted (emails sent): {len(contacted)}")

# Pending leads (campaign_id, valid email, not contacted)
all_potential = list(db["leads"].find({
    "campaign_id": {"$exists": True, "$ne": None},
    "email": {"$exists": True, "$ne": "", "$ne": None},
    "email_invalid": {"$ne": True},
}, {"_id": 1, "email": 1}))

pending = [l for l in all_potential if str(l["_id"]) not in contacted]
leads_with_drafts_set = set(leads_with_drafts)
pending_no_draft = [l for l in pending if l["_id"] not in leads_with_drafts_set]
pending_with_draft = [l for l in pending if l["_id"] in leads_with_drafts_set]

print(f"\nPending leads (not contacted): {len(pending)}")
print(f"  WITH active draft (skipped by has_draft_for_lead): {len(pending_with_draft)}")
print(f"  WITHOUT active draft (should be generated): {len(pending_no_draft)}")

# Also check: has_been_contacted_by_email (by email address, not lead_id)
contacted_emails = set(r["_id"] for r in db["emails"].aggregate([
    {"$match": {"status": "sent"}},
    {"$group": {"_id": "$to_email"}}
]))
print(f"\nContacted email addresses: {len(contacted_emails)}")

# How many pending leads have an email address that was already contacted?
skipped_by_email = [l for l in pending_no_draft if l.get("email") in contacted_emails]
truly_pending = [l for l in pending_no_draft if l.get("email") not in contacted_emails]
print(f"Pending no-draft leads whose EMAIL was already contacted: {len(skipped_by_email)}")
print(f"Truly pending (not contacted by lead_id OR email): {len(truly_pending)}")

# Draft status breakdown
print("\n=== Draft status breakdown ===")
for r in db["email_drafts"].aggregate([{"$group": {"_id": "$status", "count": {"$sum": 1}}}]):
    print(f"  {r['_id']}: {r['count']}")

# Check: how many of the 'sent' drafts correspond to today's sends?
from datetime import datetime, timedelta
today_et = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=19)
drafts_sent_today = db["email_drafts"].count_documents({"status": "sent", "sent_at": {"$gte": today_et}})
emails_sent_today = db["emails"].count_documents({"status": "sent", "sent_at": {"$gte": today_et}})
print(f"\n=== Today's sends ===")
print(f"Drafts sent today: {drafts_sent_today}")
print(f"Emails sent today: {emails_sent_today}")
print(f"Difference (emails without draft): {emails_sent_today - drafts_sent_today}")
