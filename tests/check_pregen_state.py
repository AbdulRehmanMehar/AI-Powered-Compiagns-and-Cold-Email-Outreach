"""Quick check of pre-gen pipeline state."""
import sys
sys.path.insert(0, "/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails")
from database import db

pending_with_cid = db.leads.count_documents({
    "contacted": False,
    "email_invalid": {"$ne": True},
    "campaign_id": {"$exists": True}
})
pending_no_cid = db.leads.count_documents({
    "contacted": False,
    "email_invalid": {"$ne": True},
    "campaign_id": {"$exists": False}
})
total_drafts = db.email_drafts.count_documents({})
ready = db.email_drafts.count_documents({"status": "ready_to_send"})
failed = db.email_drafts.count_documents({"status": "failed"})
generating = db.email_drafts.count_documents({"status": "generating"})
sent = db.email_drafts.count_documents({"status": "sent"})
claimed = db.email_drafts.count_documents({"status": "claimed"})

draft_lead_ids = db.email_drafts.distinct("lead_id")

print(f"LEADS:")
print(f"  Pending WITH campaign_id: {pending_with_cid}")
print(f"  Pending WITHOUT campaign_id: {pending_no_cid}")
print(f"\nDRAFTS:")
print(f"  Total: {total_drafts}")
print(f"  ready_to_send: {ready}")
print(f"  failed: {failed}")
print(f"  generating: {generating}")
print(f"  sent: {sent}")
print(f"  claimed: {claimed}")
print(f"\n  Distinct leads with any draft: {len(draft_lead_ids)}")
