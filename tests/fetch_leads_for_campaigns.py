"""
Manually trigger RocketReach lead fetch for:
  1. All 9 NEW DRAFT campaigns (Feb 17-19 ICP changes) — fetch leads + activate them
  2. The 5 main ACTIVE sending campaigns — top up their lead pool

Usage:
    python tests/fetch_leads_for_campaigns.py             # fetch for new drafts + active
    python tests/fetch_leads_for_campaigns.py --dry-run   # show what would be fetched
    python tests/fetch_leads_for_campaigns.py --active-only    # only top-up active
    python tests/fetch_leads_for_campaigns.py --new-only       # only new draft campaigns
    python tests/fetch_leads_for_campaigns.py --max-per-campaign 100
"""

import sys
import os
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from bson import ObjectId

# ── IDs from inventory query (2026-02-19) ─────────────────────────────────────

# 5 big active campaigns currently generating/sending (top them up)
ACTIVE_CAMPAIGNS = [
    "697b680957f7339fa5ad0f4d",   # Scheduling Automation Startups - 2026-01-29
    "697b936f57f7339fa5ad104d",   # Target seed-stage founders (MVP dev)
    "697b940f57f7339fa5ad104e",   # Target marketplace founders
    "697b94f057f7339fa5ad1056",   # Target product leaders (AI personalization)
    "697b95dd57f7339fa5ad1057",   # Target CTOs at SaaS companies (scaling)
]

# 9 new DRAFT campaigns created Feb 17-19 (ICPs changed) — need leads + activation
NEW_DRAFT_ICP_CAMPAIGNS = [
    "69947494b91705dd73171a39",   # Campaign: Ctos At Capacity      (02/17 14:00)
    "69949e92b91cf3fa5bc77f2e",   # Campaign: Legacy Modernization  (02/17 17:00)
    "6994c8c4b91cf3fa5bc77f94",   # Campaign: Product Leaders Roadmap Slip (02/17 20:00)
    "6995c614d0aa8dd13d30ed04",   # Campaign: Ctos At Capacity      (02/18 14:00)
    "6995f047d0aa8dd13d30ed06",   # Campaign: Legacy Modernization  (02/18 17:00)
    "69961a7ad0aa8dd13d30ed08",   # Campaign: Product Leaders Roadmap Slip (02/18 20:00)
    "6997178b7d52035cc55f7fa6",   # Campaign: Funded Saas Founders  (02/19 14:00)
    "699741bf7d52035cc55f8026",   # Campaign: Scaling Ctos          (02/19 17:00)
    "69976bf57d52035cc55f8077",   # Campaign: Ai Stuck Enterprise   (02/19 20:00)
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_campaign_summary(campaign_id: str) -> dict:
    c = db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not c:
        return {"error": "not found"}
    lead_count = db.leads.count_documents({"campaign_id": ObjectId(campaign_id)})
    ready  = db["email_drafts"].count_documents({"campaign_id": ObjectId(campaign_id), "status": "ready_to_send"})
    sent   = db["email_drafts"].count_documents({"campaign_id": ObjectId(campaign_id), "status": "sent"})
    return {
        "id": campaign_id,
        "name": c.get("name", "?"),
        "status": c.get("status"),
        "leads": lead_count,
        "ready_to_send": ready,
        "sent": sent,
        "criteria_keys": list(c.get("target_criteria", {}).keys()),
    }


def fetch_for_campaign(campaign_manager, campaign_id: str, max_leads: int, dry_run: bool) -> int:
    """Fetch leads for a single campaign. Returns number of leads fetched."""
    summary = get_campaign_summary(campaign_id)
    if "error" in summary:
        print(f"  ⚠  Campaign {campaign_id} not found — skipping")
        return 0

    print(f"\n  Campaign: {summary['name'][:60]}")
    print(f"    status={summary['status']}  leads={summary['leads']}  "
          f"ready={summary['ready_to_send']}  sent={summary['sent']}")
    print(f"    criteria keys: {summary['criteria_keys']}")

    if dry_run:
        print(f"    [DRY RUN] would fetch up to {max_leads} leads via RocketReach")
        return 0

    try:
        leads = campaign_manager.fetch_leads_for_campaign(campaign_id, max_leads=max_leads)
        fetched = len(leads) if leads else 0
        print(f"    ✓ Fetched {fetched} leads")
        return fetched
    except Exception as e:
        print(f"    ✗ Error fetching leads: {e}")
        return 0


def activate_campaign(campaign_id: str, dry_run: bool):
    c = db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not c:
        return
    if c.get("status") == "active":
        print(f"    → Already active")
        return
    if dry_run:
        print(f"    [DRY RUN] would set status: {c.get('status')} → active")
        return
    db.campaigns.update_one(
        {"_id": ObjectId(campaign_id)},
        {"$set": {"status": "active", "activated_at": datetime.datetime.utcnow()}}
    )
    print(f"    ✓ Status changed: {c.get('status')} → active")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch RocketReach leads for campaigns")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without calling RocketReach")
    parser.add_argument("--active-only", action="store_true", help="Only top-up the 5 active campaigns")
    parser.add_argument("--new-only", action="store_true", help="Only process the 9 new draft ICP campaigns")
    parser.add_argument("--max-per-campaign", type=int, default=200, help="Leads to fetch per campaign (default: 200)")
    args = parser.parse_args()

    if args.dry_run:
        print("=" * 60)
        print("  DRY RUN — no RocketReach calls will be made")
        print("=" * 60)

    from campaign_manager import CampaignManager
    cm = CampaignManager()

    total_fetched = 0
    total_activated = 0

    # ── Phase 1: New draft campaigns (fetch + activate) ────────────────────────
    if not args.active_only:
        print(f"\n{'='*60}")
        print(f"PHASE 1: New Draft ICP Campaigns ({len(NEW_DRAFT_ICP_CAMPAIGNS)} campaigns)")
        print(f"  Max leads per campaign: {args.max_per_campaign}")
        print(f"{'='*60}")

        for cid in NEW_DRAFT_ICP_CAMPAIGNS:
            n = fetch_for_campaign(cm, cid, args.max_per_campaign, args.dry_run)
            total_fetched += n
            activate_campaign(cid, args.dry_run)
            if not args.dry_run:
                total_activated += 1

    # ── Phase 2: Active campaigns (top up) ────────────────────────────────────
    if not args.new_only:
        print(f"\n{'='*60}")
        print(f"PHASE 2: Active Sending Campaigns — Top Up ({len(ACTIVE_CAMPAIGNS)} campaigns)")
        print(f"  Max leads per campaign: {args.max_per_campaign}")
        print(f"{'='*60}")

        for cid in ACTIVE_CAMPAIGNS:
            n = fetch_for_campaign(cm, cid, args.max_per_campaign, args.dry_run)
            total_fetched += n

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"DONE")
    if args.dry_run:
        print(f"  [DRY RUN] No actual fetches performed")
    else:
        print(f"  Total leads fetched : {total_fetched}")
        print(f"  Campaigns activated : {total_activated}")
    print(f"{'='*60}")
    print()

    if not args.dry_run and total_fetched > 0:
        print(f"Next steps:")
        print(f"  1. pre_generator will pick up the new leads within the next cycle")
        print(f"  2. Monitor: tail -f scheduler.log | grep 'pregen\\|draft'")
        print(f"  3. Check new draft counts: python tests/check_feb19_emails.py")


if __name__ == "__main__":
    main()
