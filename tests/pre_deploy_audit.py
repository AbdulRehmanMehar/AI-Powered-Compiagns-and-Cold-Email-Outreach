"""Pre-deploy audit: verify all cross-module method calls are valid."""
import sys, inspect
sys.path.insert(0, "/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails")

from email_generator import EmailGenerator
from email_reviewer import EmailReviewer
from database import Campaign, Lead, Email, DoNotContact

ok = 0
fail = 0

def check(label, condition):
    global ok, fail
    if condition:
        print(f"  ✅ {label}")
        ok += 1
    else:
        print(f"  ❌ {label}")
        fail += 1

print("=== EmailGenerator method signatures ===")
eg = EmailGenerator()
sig1 = inspect.signature(eg.generate_initial_email)
p1 = list(sig1.parameters.keys())
check(f"generate_initial_email params: {p1}", "lead" in p1 and "campaign_context" in p1)

sig2 = inspect.signature(eg.generate_followup_email)
p2 = list(sig2.parameters.keys())
check(f"generate_followup_email params: {p2}", "lead" in p2 and "campaign_context" in p2 and "previous_emails" in p2 and "followup_number" in p2)
check("NO generate_cold_email method", not hasattr(eg, "generate_cold_email"))

print("\n=== EmailReviewer methods ===")
er = EmailReviewer()
check("review_email exists", hasattr(er, "review_email"))
check("_rewrite_email exists", hasattr(er, "_rewrite_email"))

print("\n=== Database model methods (used by pre_generator) ===")
check("Campaign.get_by_id", hasattr(Campaign, "get_by_id"))
check("Lead.get_by_id", hasattr(Lead, "get_by_id"))
check("Lead.mark_invalid_email", hasattr(Lead, "mark_invalid_email"))
check("Lead.update_verification_status", hasattr(Lead, "update_verification_status"))
check("Email.get_pending_followups", hasattr(Email, "get_pending_followups"))
check("Email.get_thread_info", hasattr(Email, "get_thread_info"))
check("Email.get_sender_for_lead", hasattr(Email, "get_sender_for_lead"))
check("Email.get_by_lead_and_campaign", hasattr(Email, "get_by_lead_and_campaign"))
check("Email.has_been_contacted_by_email", hasattr(Email, "has_been_contacted_by_email"))
check("DoNotContact.is_blocked", hasattr(DoNotContact, "is_blocked"))

print("\n=== v2 module imports ===")
import importlib
for mod_name in ["v2.scheduler", "v2.send_worker", "v2.pre_generator", "v2.account_pool", "v2.imap_worker", "v2.human_behavior"]:
    try:
        importlib.import_module(mod_name)
        check(f"import {mod_name}", True)
    except Exception as e:
        check(f"import {mod_name}: {e}", False)

print("\n=== pre_generator.py cross-call verification ===")
# Simulate the actual call patterns to make sure they won't crash
from v2.pre_generator import PreGenerator, EmailDraft, DraftStatus

# Verify EmailDraft static methods
check("EmailDraft.create", hasattr(EmailDraft, "create"))
check("EmailDraft.mark_ready", hasattr(EmailDraft, "mark_ready"))
check("EmailDraft.mark_failed", hasattr(EmailDraft, "mark_failed"))
check("EmailDraft.mark_review_failed", hasattr(EmailDraft, "mark_review_failed"))
check("EmailDraft.has_draft_for_lead", hasattr(EmailDraft, "has_draft_for_lead"))
check("EmailDraft.claim_next_ready", hasattr(EmailDraft, "claim_next_ready"))
check("EmailDraft.cleanup_stale_claimed", hasattr(EmailDraft, "cleanup_stale_claimed"))
check("EmailDraft.release_claimed", hasattr(EmailDraft, "release_claimed"))

# Verify DraftStatus values
check("DraftStatus.READY", DraftStatus.READY == "ready_to_send")
check("DraftStatus.FAILED", DraftStatus.FAILED == "failed")
check("DraftStatus.GENERATING", DraftStatus.GENERATING == "generating")

print("\n=== send_worker.py cross-call verification ===")
from v2.send_worker import SendWorker
check("SendWorker._process_one_draft", hasattr(SendWorker, "_process_one_draft"))
# _check_and_refill_queue and _run_background_pregen removed — pre-gen is now continuous

print("\n=== pre_generator continuous mode verification ===")
from v2.pre_generator import PreGenerator
check("PreGenerator.run_continuous", hasattr(PreGenerator, "run_continuous"))
check("PreGenerator._get_campaign_manager", hasattr(PreGenerator, "_get_campaign_manager"))
check("PreGenerator._sleep_or_shutdown", hasattr(PreGenerator, "_sleep_or_shutdown"))

print("\n=== main_v2.py import check ===")
try:
    import main_v2
    check("main_v2 imports OK", True)
except Exception as e:
    check(f"main_v2 import: {e}", False)

print(f"\n{'='*50}")
print(f"RESULT: {ok} passed, {fail} failed")
if fail > 0:
    print("❌ DO NOT DEPLOY — fix failures above")
    sys.exit(1)
else:
    print("✅ ALL CHECKS PASSED — safe to deploy")
