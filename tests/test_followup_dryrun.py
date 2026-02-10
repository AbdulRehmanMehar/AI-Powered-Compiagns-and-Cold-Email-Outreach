#!/usr/bin/env python3
"""Test follow-up system with dry-run to see what would happen"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from campaign_manager import CampaignManager
from database import *
from datetime import datetime
import config

print("=" * 70)
print("FOLLOW-UP DRY-RUN TEST")
print("=" * 70)
print(f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
print(f"Follow-up delay: {config.FOLLOWUP_DELAY_DAYS} days")
print(f"Max follow-ups: {config.MAX_FOLLOWUPS}")

# Find campaigns with pending follow-ups
active_campaigns = list(campaigns_collection.find({
    "status": {"$in": ["active", "running", "draft"]}
}))

manager = CampaignManager()

total_pending = 0
for camp in active_campaigns:
    camp_id = str(camp["_id"])
    camp_name = camp.get("name", "Unknown")
    
    pending = Email.get_pending_followups(camp_id, config.FOLLOWUP_DELAY_DAYS)
    if not pending:
        continue
    
    total_pending += len(pending)
    print(f"\n{'='*60}")
    print(f"Campaign: {camp_name}")
    print(f"Pending follow-ups: {len(pending)}")
    print(f"{'='*60}")
    
    # Run dry-run for this campaign
    try:
        results = manager.send_followup_emails(camp_id, dry_run=True)
        print(f"\nDry-run results:")
        print(f"  Total: {results['total']}")
        print(f"  Would send: {results['sent']}")
        print(f"  Failed: {results['failed']}")
        print(f"  Skipped (max reached): {results['skipped_max_reached']}")
        if results.get('details'):
            for d in results['details'][:5]:
                print(f"  → {d['lead_email']}: fu#{d['followup_number']} - {d['status']}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

if total_pending == 0:
    print("\nNo follow-ups pending across any campaign.")

print(f"\n{'='*70}")
print("DRY-RUN COMPLETE")
print(f"{'='*70}")
