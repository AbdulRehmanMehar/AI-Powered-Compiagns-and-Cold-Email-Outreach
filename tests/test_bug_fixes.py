"""Test all bug fixes from log analysis."""
import sys
sys.path.insert(0, '.')

passed = 0
failed = 0

def check(label, condition):
    global passed, failed
    if condition:
        print(f"  ✅ {label}")
        passed += 1
    else:
        print(f"  ❌ {label}")
        failed += 1

print("=" * 60)
print("BUG FIX TESTS")
print("=" * 60)

# ─── Test 1: Zombie pending leads - DB query filter ───
print("\n🔧 Bug #3: Zombie pending leads (DB filter)")
from campaign_manager import CampaignManager
cm = CampaignManager()
leads = cm.get_pending_leads(max_leads=5)
invalid_in_results = [l for l in leads if l.get('email_invalid')]
check("get_pending_leads excludes email_invalid leads", len(invalid_in_results) == 0)
print(f"     Returned {len(leads)} leads, {len(invalid_in_results)} invalid (should be 0)")

# ─── Test 2: Domain guessing from company name ───
print("\n🔧 Bug #6: no_domain enrichment (domain guessing)")
from lead_enricher import LeadEnricher
enricher = LeadEnricher()

# Personal email + company name → should guess domain
d1 = enricher._get_company_domain({'email': 'test@gmail.com', 'company': 'DataVault Technologies'})
check(f"DataVault Technologies → {d1}", d1 == 'datavault.com')

d2 = enricher._get_company_domain({'email': 'test@gmail.com', 'company': 'Acme Corp'})
check(f"Acme Corp → {d2}", d2 == 'acme.com')

d3 = enricher._get_company_domain({'email': 'test@gmail.com', 'company': 'BuildOS'})
check(f"BuildOS → {d3}", d3 == 'buildos.com')

d4 = enricher._get_company_domain({'email': 'test@gmail.com', 'company': 'HealthSync Inc'})
check(f"HealthSync Inc → {d4}", d4 == 'healthsync.com')

# Company email → should still use email domain (not company name)
d5 = enricher._get_company_domain({'email': 'test@datavault.io'})
check(f"test@datavault.io → {d5}", d5 == 'datavault.io')

# No company at all → should return None
d6 = enricher._get_company_domain({'email': 'test@gmail.com'})
check(f"No company → {d6}", d6 is None)

# ─── Test 3: 503 handling in fallback chains ───
print("\n🔧 Bug #7: 503 handling in fallback chains")
import email_generator
import email_reviewer
import lead_enricher
import inspect

# Check email_generator._call_llm has 503 handling
eg_src = inspect.getsource(email_generator.EmailGenerator._call_llm)
check("email_generator: handles '503'", "'503'" in eg_src)
check("email_generator: handles 'service unavailable'", "'service unavailable'" in eg_src)
check("email_generator: handles 'timeout'", "'timeout'" in eg_src)

# Check email_reviewer._call_llm has 503 handling
er_src = inspect.getsource(email_reviewer.EmailReviewer._call_llm)
check("email_reviewer: handles '503'", "'503'" in er_src)
check("email_reviewer: handles 'service unavailable'", "'service unavailable'" in er_src)

# Check lead_enricher._call_llm has 503 handling
le_src = inspect.getsource(lead_enricher.LeadEnricher._call_llm)
check("lead_enricher: handles '503'", "'503'" in le_src)
check("lead_enricher: handles 'service unavailable'", "'service unavailable'" in le_src)

# ─── Test 4: Scheduler crash resilience ───
print("\n🔧 Bug #5: Scheduler crash resilience")
import auto_scheduler
sched_src = inspect.getsource(auto_scheduler.AutoScheduler.start)
check("Scheduler main loop catches generic Exception", "except Exception as e:" in sched_src)
check("Scheduler logs traceback on crash", "traceback.print_exc()" in sched_src)
check("Scheduler retries after 60s on error", "will retry in 60s" in sched_src)

# Check _run_scheduled_campaign also prints traceback
run_src = inspect.getsource(auto_scheduler.AutoScheduler._run_scheduled_campaign)
check("Campaign failure logs traceback", "traceback.print_exc()" in run_src)

# ─── Test 5: Non-ICP gate ───
print("\n🔧 Bug #5: Non-ICP leads gate")
cm_src = inspect.getsource(CampaignManager.send_initial_emails)
check("Has non-ICP skip gate", "Skipping non-ICP lead" in cm_src)
check("Tracks skipped_non_icp count", "skipped_non_icp" in cm_src)
# Verify the gate has a continue after it (check raw file)
with open('campaign_manager.py', 'r') as f:
    raw = f.read()
    gate_pos = raw.find('Skipping non-ICP lead')
    next_100 = raw[gate_pos:gate_pos+400]
    check("Gate uses continue after skip", 'continue' in next_100)

# ─── Test 6: RocketReach invalid → mark in DB ───
print("\n🔧 Bug #3b: RocketReach invalid marks DB")
with open('campaign_manager.py', 'r') as f:
    raw_cm = f.read()
    rr_pos = raw_cm.find('RocketReach marked INVALID')
    next_300 = raw_cm[rr_pos:rr_pos+500]
    check("RocketReach skip calls mark_invalid_email", 'mark_invalid_email' in next_300)

# ─── Summary ───
print("\n" + "=" * 60)
total = passed + failed
print(f"RESULTS: {passed}/{total} passed, {failed} failed")
if failed == 0:
    print("🎉 ALL TESTS PASSED!")
else:
    print(f"⚠️  {failed} test(s) failed")
    sys.exit(1)
