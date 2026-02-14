"""Quick verification that all fixes import and work correctly."""
import sys
import os
import inspect

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    print("Testing campaign_manager imports...")
    from campaign_manager import CampaignManager
    print("  OK CampaignManager imported")

    print("Testing pre_generator imports...")
    from v2.pre_generator import PreGenerator, EmailDraft
    print("  OK PreGenerator imported")

    print("Testing send_worker imports...")
    from v2.send_worker import SendWorker
    print("  OK SendWorker imported")

    print("Testing scheduler imports...")
    from v2.scheduler import AsyncScheduler
    print("  OK AsyncScheduler imported")

    print("Testing account_pool imports...")
    from v2.account_pool import AccountPool
    print("  OK AccountPool imported")

    # Verify get_pending_leads has skip_drafted param
    sig = inspect.signature(CampaignManager.get_pending_leads)
    assert "skip_drafted" in sig.parameters, "skip_drafted parameter missing!"
    print("  OK get_pending_leads has skip_drafted parameter")

    # Verify _run_campaign no longer calls run_autonomous_campaign
    src = inspect.getsource(AsyncScheduler._run_campaign)
    assert "run_autonomous_campaign" not in src, "_run_campaign still calls run_autonomous_campaign!"
    assert "send_followup_emails" not in src, "_run_campaign still calls send_followup_emails!"
    assert "fetch_leads_for_campaign" in src, "_run_campaign does not call fetch_leads_for_campaign!"
    print("  OK _run_campaign is lead-fetch only (no legacy send path)")

    # Verify send_worker checks business hours before claiming
    sw_src = inspect.getsource(SendWorker._process_one_draft)
    assert "_can_send_now" in sw_src, "send_worker does not check business hours before claiming!"
    print("  OK send_worker checks business hours before claiming drafts")

    print()
    print("ALL CHECKS PASSED")

except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
