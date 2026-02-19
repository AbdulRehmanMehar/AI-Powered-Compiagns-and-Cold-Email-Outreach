"""
REAL E2E Pipeline Test — Live RocketReach + Ollama Calls
=========================================================
Uses REAL API calls to show exactly what the system produces:

1. Picks 4 diverse ICP templates
2. Creates campaign configs from each
3. Searches RocketReach for REAL leads (2 per template — minimal credits)
4. Generates REAL cold emails via Ollama (qwen2.5:7b)
5. Displays everything: lead data, system prompt highlights, and final email

No emails are SENT. This only tests generation.
"""

import sys
import os
import json
import time
import textwrap
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from primestrides_context import ICP_TEMPLATES, CASE_STUDIES
from icp_manager import ICPManager
from rocketreach_client import RocketReachClient
from email_generator import EmailGenerator

# ============================================================
# CONFIG
# ============================================================
# Pick a diverse spread: original + new personas, different company sizes
TEST_ICPS = [
    "scaling_ctos",               # Original — 51-200 employees, engineering leaders
    "agency_whitelabel_partners",  # New — agencies, 11-50 employees 
    "ops_leaders_manual_processes",# New — COOs/VP Ops, 201-1000 employees
    "revenue_ops_leaders",         # New — CROs, 51-500 employees
]

LEADS_PER_ICP = 2  # Keep it minimal to save RocketReach credits
SEPARATOR = "=" * 78


def print_header(text):
    print(f"\n{SEPARATOR}")
    print(f"  {text}")
    print(SEPARATOR)


def print_subheader(text):
    print(f"\n{'─' * 78}")
    print(f"  {text}")
    print(f"{'─' * 78}")


def wrap_text(text, width=74, indent="    "):
    """Word-wrap text with indent for display"""
    lines = text.split('\n')
    wrapped = []
    for line in lines:
        if line.strip() == '':
            wrapped.append('')
        else:
            wrapped.extend(textwrap.wrap(line, width=width, initial_indent=indent, subsequent_indent=indent))
    return '\n'.join(wrapped)


# ============================================================
# STEP 1: Initialize real clients
# ============================================================
print_header("INITIALIZING (Real Ollama + RocketReach)")

rocketreach = RocketReachClient()
email_gen = EmailGenerator()

print(f"  LLM Provider: {email_gen.provider}")
print(f"  LLM Model:    {email_gen.model}")
print(f"  RocketReach:  API key configured ({'yes' if rocketreach.api_key else 'NO'})")
print(f"  Templates:    {len(TEST_ICPS)} selected for testing")
print(f"  Leads/ICP:    {LEADS_PER_ICP}")

all_results = []
total_rr_time = 0
total_llm_time = 0

for icp_idx, icp_name in enumerate(TEST_ICPS, 1):
    template = ICP_TEMPLATES[icp_name]
    persona = template.get("persona", {})
    
    # ============================================================
    # STEP 2: Generate campaign config from ICP
    # ============================================================
    print_header(f"ICP {icp_idx}/{len(TEST_ICPS)}: {icp_name}")
    
    icp_mgr = ICPManager()
    campaign_config = icp_mgr.generate_campaign_from_icp(icp_name)
    
    if "error" in campaign_config:
        print(f"  ERROR: {campaign_config['error']}")
        continue
    
    tc = campaign_config["target_criteria"]
    ctx = campaign_config["campaign_context"]
    
    print(f"  Persona:       {persona.get('name', 'N/A')} — {persona.get('archetype', '')}")
    print(f"  Titles:        {tc['current_title'][:3]}{'...' if len(tc['current_title']) > 3 else ''}")
    print(f"  Industries:    {tc['industry'][:2]}{'...' if len(tc['industry']) > 2 else ''}")
    print(f"  Company size:  {tc['company_size']}")
    print(f"  Pain point:    {ctx['single_pain_point'][:90]}...")
    print(f"  Case study:    {ctx['case_study'].get('company_name', 'N/A')}")
    print()
    print(f"  CHRIS DO CONTEXT (fed to LLM):")
    print(f"    The Crap:    {persona.get('the_crap_they_deal_with', 'N/A')[:90]}...")
    print(f"    The Hunger:  {persona.get('the_hunger', 'N/A')[:90]}...")
    print(f"    Fears:       {persona.get('fears', 'N/A')[:90]}...")
    
    # ============================================================
    # STEP 3: Search RocketReach for REAL leads
    # ============================================================
    print_subheader(f"ROCKETREACH SEARCH — {icp_name}")
    
    # Merge industry into keywords (same as production fetch_leads does)
    merged_kw = list(tc.get("keywords") or [])
    industry_terms = tc.get("industry", [])
    if industry_terms:
        existing_lower = {k.lower() for k in merged_kw}
        for term in industry_terms:
            simplified = term.split(" - ")[0].replace("Hospitals & ", "").lower().strip()
            if simplified and simplified not in existing_lower:
                merged_kw.append(simplified)
                existing_lower.add(simplified)
    
    t0 = time.time()
    search_result = rocketreach.search_people(
        current_title=tc["current_title"],
        location=tc["location"],
        industry=None,  # DISABLED: industry filter doesn't work, merged into keywords
        keywords=merged_kw if merged_kw else None,
        company_size=tc["company_size"],
        page_size=LEADS_PER_ICP,
        start=1
    )
    rr_elapsed = time.time() - t0
    total_rr_time += rr_elapsed
    
    profiles = search_result.get("profiles", [])
    total_found = search_result.get("pagination", {}).get("total", 0)
    
    print(f"  Total matches: {total_found:,}")
    print(f"  Returned:      {len(profiles)} profiles")
    print(f"  Time:          {rr_elapsed:.1f}s")
    
    if not profiles:
        print(f"  ⚠️  No results — skipping email generation for this ICP")
        # Try fallback without keywords
        print(f"  🔄 Retrying without keywords...")
        search_result = rocketreach.search_people(
            current_title=tc["current_title"],
            location=tc["location"],
            industry=None,  # Still disabled
            company_size=tc["company_size"],
            page_size=LEADS_PER_ICP,
            start=1
        )
        profiles = search_result.get("profiles", [])
        total_found = search_result.get("pagination", {}).get("total", 0)
        print(f"  Fallback total: {total_found:,}")
        print(f"  Fallback returned: {len(profiles)} profiles")
        
        if not profiles:
            print(f"  ❌ Still no results, moving on")
            continue
    
    # ============================================================
    # STEP 4: Display leads and generate REAL emails
    # ============================================================
    for lead_idx, profile in enumerate(profiles, 1):
        # Look up real email via RocketReach profile lookup
        # search_people() only returns metadata (name, title, company), not emails
        profile_id = profile.get("id")
        real_email = "unknown@example.com"
        
        if profile_id:
            print(f"\n  🔍 Looking up email for profile {profile_id}...")
            detailed = rocketreach.get_person_with_email(profile_id)
            if detailed:
                emails = detailed.get("emails", []) or []
                for e in emails:
                    if isinstance(e, str):
                        real_email = e
                        break
                    elif isinstance(e, dict):
                        e_addr = e.get("email", "")
                        e_valid = (e.get("smtp_valid") or "").lower()
                        e_grade = e.get("grade", "F")
                        if e_valid == "invalid" or e_grade == "F":
                            continue
                        real_email = e_addr
                        if e_valid == "valid":
                            break  # Prefer valid over inconclusive
        
        lead = {
            "first_name": profile.get("first_name", ""),
            "last_name": profile.get("last_name", ""),
            "email": real_email,
            "title": profile.get("current_title", ""),
            "company": profile.get("current_employer", ""),
            "industry": profile.get("industry", "") or (tc["industry"][0] if tc["industry"] else ""),
            "location": profile.get("location", ""),
        }
        
        print_subheader(f"LEAD {lead_idx}: {lead['first_name']} {lead['last_name']} — {lead['title']} at {lead['company']}")
        print(f"  Industry:  {lead['industry']}")
        print(f"  Location:  {lead['location']}")
        print(f"  Email:     {lead['email']}")
        
        # Generate real email via Ollama
        print(f"\n  📝 Generating email via {email_gen.provider}/{email_gen.model}...")
        
        t0 = time.time()
        try:
            # Build the campaign_context as stored in MongoDB (nested in target_criteria)
            full_campaign_context = ctx
            
            result = email_gen.generate_initial_email(
                lead=lead,
                campaign_context=full_campaign_context,
                include_review_learnings=False  # Skip DB calls for reviewer learnings
            )
            llm_elapsed = time.time() - t0
            total_llm_time += llm_elapsed
            
            if result is None:
                print(f"  ⚠️  generate_initial_email returned None (lead skipped)")
                continue
            
            subject = result.get("subject", "")
            body = result.get("body", "")
            word_count = len(body.split()) if body else 0
            
            print(f"\n  ┌─────────────────────────────────────────────────────────────────────┐")
            print(f"  │ Subject: {subject:<63}│")
            print(f"  │ Words: {word_count:<65}│")
            print(f"  │ Gen time: {llm_elapsed:.1f}s{' ' * 58}│")
            print(f"  ├─────────────────────────────────────────────────────────────────────┤")
            
            for line in body.split('\n'):
                # Truncate very long lines
                display = line[:69]
                print(f"  │ {display:<69}│")
            
            print(f"  └─────────────────────────────────────────────────────────────────────┘")
            
            # Quality checks
            issues = []
            if word_count > 80:
                issues.append(f"Too long ({word_count} words, target 45-70)")
            if word_count < 30 and word_count > 0:
                issues.append(f"Too short ({word_count} words)")
            if '—' in body:
                issues.append("Contains em dash (should use comma/period)")
            if lead['company'].lower() not in body.lower() and lead['company']:
                issues.append(f"Missing company name '{lead['company']}'")
            if body.count('\n\n') < 2:
                issues.append("Less than 3 paragraph breaks (needs 4-line structure)")
            
            # Check for stalker phrases
            stalker = ['i noticed', 'i saw', 'came across', 'i was looking']
            for s in stalker:
                if s in body.lower():
                    issues.append(f"Stalker phrase: '{s}'")
            
            # Check for jargon
            jargon = ['leverage', 'streamline', 'optimize', 'synergy', 'empower', 'innovative', 'solutions']
            for j in jargon:
                if j in body.lower():
                    issues.append(f"Jargon: '{j}'")
            
            if issues:
                print(f"\n  ⚠️  Quality flags:")
                for issue in issues:
                    print(f"      - {issue}")
            else:
                print(f"\n  ✅ Passes all quality checks")
            
            all_results.append({
                "icp": icp_name,
                "lead": f"{lead['first_name']} {lead['last_name']}",
                "title": lead["title"],
                "company": lead["company"],
                "subject": subject,
                "body": body,
                "word_count": word_count,
                "gen_time": llm_elapsed,
                "issues": issues
            })
            
        except Exception as e:
            llm_elapsed = time.time() - t0
            print(f"  ❌ Email generation failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            all_results.append({
                "icp": icp_name,
                "lead": f"{lead['first_name']} {lead['last_name']}",
                "title": lead["title"],
                "company": lead["company"],
                "error": str(e),
                "gen_time": llm_elapsed,
            })


# ============================================================
# SUMMARY
# ============================================================
print_header("SUMMARY")

total_generated = len([r for r in all_results if "body" in r])
total_failed = len([r for r in all_results if "error" in r])
total_clean = len([r for r in all_results if "body" in r and not r.get("issues")])

print(f"""
  ICPs tested:       {len(TEST_ICPS)}
  Leads found:       {len(all_results)}
  Emails generated:  {total_generated}
  Generation errors: {total_failed}
  Clean (no flags):  {total_clean}/{total_generated}
  
  Avg word count:    {sum(r.get('word_count', 0) for r in all_results) / max(total_generated, 1):.0f}
  RocketReach time:  {total_rr_time:.1f}s total
  LLM time:          {total_llm_time:.1f}s total ({total_llm_time / max(total_generated, 1):.1f}s/email avg)
""")

if total_generated > 0:
    print("  EMAIL SAMPLES:")
    print("  " + "─" * 74)
    for r in all_results:
        if "body" not in r:
            continue
        status = "✅" if not r.get("issues") else f"⚠️ ({len(r['issues'])} flags)"
        print(f"  {status} [{r['icp']}] → {r['lead']} ({r['title']} at {r['company']})")
        print(f"     Subject: {r['subject']}")
        first_line = r['body'].split('\n')[0]
        print(f"     Preview: {first_line[:70]}...")
        print()

# Save full output for review
output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "real_pipeline_output.json")
with open(output_file, 'w') as f:
    json.dump(all_results, f, indent=2)
print(f"  Full output saved to: tests/real_pipeline_output.json")
