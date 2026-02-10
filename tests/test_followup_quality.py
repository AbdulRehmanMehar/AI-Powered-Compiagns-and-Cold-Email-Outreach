#!/usr/bin/env python3
"""
Test follow-up email quality - exercises all 3 follow-up types:
  #1: Same-thread value-add
  #2: New-thread front-end offer
  #3: Breakup email
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_generator import EmailGenerator
import json

generator = EmailGenerator()

# Test leads with variety
test_leads = [
    {
        "first_name": "Dan",
        "full_name": "Dan Barker",
        "title": "CTO",
        "company": "Palo Alto Networks",
        "industry": "Cybersecurity",
        "email": "dbarker@gmail.com",
    },
    {
        "first_name": "Sarah",
        "full_name": "Sarah Chen",
        "title": "VP of Product",
        "company": "Stripe",
        "industry": "FinTech",
        "email": "sarah@stripe.com",
    },
    {
        "first_name": "Mohit",
        "full_name": "Mohit Teckchandani",
        "title": "Founder",
        "company": "MedFlow",
        "industry": "HealthTech",
        "email": "mohit@medflow.com",
    },
]

# Simulate previous emails (what the initial email would have been)
previous_emails_map = [
    [{"subject": "quick q", "body": "hey dan, had a random thought.\n\nis palo alto networks' dev team spending more time on maintenance than new features? seems to be the pattern with cybersecurity companies scaling up.\n\nwe helped an enterprise staffing company 3.2x faster deploy cycles and 41% cost savings.\n\nworth a quick chat?\nabdul"}],
    [{"subject": "random thought", "body": "hey sarah, quick one.\n\nis stripe's roadmap getting squeezed because the team's stretched? i keep hearing that from product leads in fintech.\n\nwe helped a b2b saas startup go from idea to Series A in under 4 months.\n\nthoughts?\nabdul"}],
    [{"subject": "odd idea", "body": "hey mohit, had a thought.\n\nis medflow at the crossroads of fixing old stuff vs building new things? that's usually where founders in healthtech land.\n\nwe helped a hipaa-compliant health startup launched hipaa-compliant in just 8 weeks.\n\nworth a quick chat?\nabdul"}],
]

campaign_contexts = [
    {"front_end_offer": "free technical roadmap session", "single_pain_point": "team stretched thin"},
    {"front_end_offer": "free roadmap acceleration session", "single_pain_point": "features taking too long"},
    {"front_end_offer": "free AI architecture review", "single_pain_point": "shipping medical AI fast"},
]

PASS = 0
FAIL = 0
WARNINGS = 0

def check(condition, label, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}: {detail}")

def warn(condition, label, detail=""):
    global WARNINGS
    if not condition:
        WARNINGS += 1
        print(f"  ⚠️  {label}: {detail}")

print("=" * 70)
print("FOLLOW-UP EMAIL QUALITY TEST")
print("=" * 70)

for i, lead in enumerate(test_leads):
    previous = previous_emails_map[i]
    context = campaign_contexts[i]
    
    print(f"\n{'='*70}")
    print(f"LEAD: {lead['full_name']} ({lead['title']} at {lead['company']})")
    print(f"{'='*70}")
    
    # =====================================================
    # TEST FOLLOW-UP #1: Same-thread value-add
    # =====================================================
    print(f"\n--- Follow-up #1 (Same Thread) ---")
    fu1 = generator.generate_followup_email(
        lead=lead,
        campaign_context=context,
        previous_emails=previous,
        followup_number=1
    )
    
    subject1 = fu1.get("subject", "")
    body1 = fu1.get("body", "")
    words1 = len(body1.split())
    
    print(f"  Subject: {subject1}")
    print(f"  Body ({words1} words):")
    for line in body1.split('\n'):
        print(f"    | {line}")
    
    # Quality checks
    check(subject1.startswith("Re:"), "Subject starts with Re:")
    check("just following up" not in body1.lower(), "No 'just following up'")
    check("circling back" not in body1.lower(), "No 'circling back'")
    check("bumping" not in body1.lower(), "No 'bumping'")
    check("checking in" not in body1.lower(), "No 'checking in'")
    check(words1 >= 15, "At least 15 words", f"got {words1}")
    check(words1 <= 60, "Under 60 words", f"got {words1}")
    check(fu1.get("new_thread") is None or fu1.get("new_thread") == False, "Not marked as new thread")
    # Should reference a case study or offer something concrete
    check(any(w in body1.lower() for w in ['helped', 'doc', 'breakdown', 'playbook', 'write-up', 'case study', 'put together']),
          "Contains value-add reference")
    # Should have a soft CTA
    check(any(w in body1.lower() for w in ['want', 'happy to', 'worth', 'interested', 'send it']),
          "Has soft CTA")
    # Should NOT have em dashes
    check('—' not in body1, "No em dashes")
    
    # =====================================================
    # TEST FOLLOW-UP #2: New-thread front-end offer
    # =====================================================
    print(f"\n--- Follow-up #2 (New Thread) ---")
    # For follow-up #2, previous includes both initial + follow-up #1
    previous_with_fu1 = previous + [{"subject": subject1, "body": body1}]
    
    fu2 = generator.generate_followup_email(
        lead=lead,
        campaign_context=context,
        previous_emails=previous_with_fu1,
        followup_number=2
    )
    
    subject2 = fu2.get("subject", "")
    body2 = fu2.get("body", "")
    words2 = len(body2.split())
    
    print(f"  Subject: {subject2}")
    print(f"  Body ({words2} words):")
    for line in body2.split('\n'):
        print(f"    | {line}")
    
    # Quality checks
    check(not subject2.startswith("Re:"), "New subject (no Re:)")
    check(subject2 not in [p.get('subject', '') for p in previous], "Subject not reused from previous")
    check(fu2.get("new_thread") == True, "Marked as new thread")
    check(lead['first_name'].lower() in body2.lower()[:30], "Starts with first name")
    check(words2 >= 20, "At least 20 words", f"got {words2}")
    check(words2 <= 55, "Under 55 words", f"got {words2}")
    # Should mention the offer
    check(any(w in body2.lower() for w in ['30 min', 'review', 'session', 'feedback', 'no pitch', 'roadmap']),
          "Mentions the front-end offer")
    # Should have a CTA
    check(any(w in body2.lower() for w in ['want', 'interested', 'worth', 'grab']),
          "Has CTA question")
    # Should NOT reference previous emails
    check("last email" not in body2.lower(), "No reference to previous emails")
    check("follow up" not in body2.lower(), "No 'follow up' language")
    check('—' not in body2, "No em dashes")
    
    # =====================================================
    # TEST FOLLOW-UP #3: Breakup email
    # =====================================================
    print(f"\n--- Follow-up #3 (Breakup) ---")
    previous_all = previous_with_fu1 + [{"subject": subject2, "body": body2}]
    
    fu3 = generator.generate_followup_email(
        lead=lead,
        campaign_context=context,
        previous_emails=previous_all,
        followup_number=3
    )
    
    subject3 = fu3.get("subject", "")
    body3 = fu3.get("body", "")
    words3 = len(body3.split())
    
    print(f"  Subject: {subject3}")
    print(f"  Body ({words3} words):")
    for line in body3.split('\n'):
        print(f"    | {line}")
    
    # Quality checks
    check(fu3.get("new_thread") == True, "Marked as new thread")
    check(lead['first_name'].lower() in body3.lower()[:30], "Starts with first name")
    check(words3 >= 15, "At least 15 words", f"got {words3}")
    check(words3 <= 50, "Under 50 words", f"got {words3}")
    # Should have the "someone else" redirect (LeadGenJay's key move)
    check(any(w in body3.lower() for w in ['someone else', 'close', 'check back', 'close this out']),
          "Has redirect/close language")
    # Should mention company
    check(lead['company'].lower() in body3.lower(), "Mentions company name")
    # Should NOT be desperate or guilt-trippy
    check("i hope" not in body3.lower(), "No 'I hope' language")
    check("per my" not in body3.lower(), "No 'per my' language")
    check('—' not in body3, "No em dashes")

# =====================================================
# VARIETY TEST: Generate same follow-up 5 times, check diversity
# =====================================================
print(f"\n{'='*70}")
print("VARIETY TEST: Same lead, 5 follow-up #1 generations")
print(f"{'='*70}")

test_lead = test_leads[0]
openers_seen = set()
bodies_seen = set()

for j in range(5):
    fu = generator.generate_followup_email(
        lead=test_lead,
        campaign_context=campaign_contexts[0],
        previous_emails=previous_emails_map[0],
        followup_number=1
    )
    body = fu.get("body", "")
    # Extract opener (first few words)
    opener = body.split('-')[0].strip() if '-' in body[:40] else body[:30]
    openers_seen.add(opener)
    bodies_seen.add(body[:50])  # first 50 chars for uniqueness
    print(f"  Run {j+1}: {body[:80]}...")

unique_openers = len(openers_seen)
unique_bodies = len(bodies_seen)
print(f"\n  Unique openers: {unique_openers}/5")
print(f"  Unique bodies (first 50 chars): {unique_bodies}/5")
check(unique_openers >= 2, "At least 2 different openers in 5 runs", f"got {unique_openers}")
check(unique_bodies >= 3, "At least 3 different bodies in 5 runs", f"got {unique_bodies}")

# =====================================================
# SUMMARY
# =====================================================
print(f"\n{'='*70}")
print(f"RESULTS: {PASS} passed, {FAIL} failed, {WARNINGS} warnings")
total = PASS + FAIL
if total > 0:
    score = round(PASS / total * 100, 1)
    print(f"Score: {score}/100")
    if FAIL == 0:
        print("🎉 ALL CHECKS PASSED!")
    else:
        print(f"⚠️  {FAIL} checks need attention")
print(f"{'='*70}")
