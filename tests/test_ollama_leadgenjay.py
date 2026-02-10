#!/usr/bin/env python3
"""
Ollama Email Generation Test with LeadGenJay Quality Review

Tests actual email generation using the real system prompts with Ollama (qwen2.5:7b)
and evaluates them against LeadGenJay's guidelines.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from datetime import datetime

# Force Ollama for this test
os.environ['LLM_PROVIDER'] = 'ollama'
os.environ['OLLAMA_BASE_URL'] = 'http://192.168.1.9:11434'
os.environ['OLLAMA_MODEL'] = 'qwen2.5:7b'

print("="*80)
print("OLLAMA EMAIL GENERATION TEST WITH LEADGENJAY QUALITY REVIEW")
print("="*80)
print(f"\nDate: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"LLM: {os.environ['LLM_PROVIDER']} - {os.environ['OLLAMA_MODEL']}")
print(f"Server: {os.environ['OLLAMA_BASE_URL']}")

# Test leads representing different scenarios
test_leads = [
    {
        "first_name": "Sarah",
        "email": "sarah.chen@techstartup.io",
        "company": "DataFlow AI",
        "company_name": "DataFlow AI",
        "title": "CTO",
        "industry": "Artificial Intelligence",
        "description": "Early-stage AI startup building ML infrastructure",
    },
    {
        "first_name": "Mike",
        "email": "mike@healthtech.com",
        "company": "MediSync",
        "company_name": "MediSync",
        "title": "VP Engineering",
        "industry": "Healthcare Technology",
        "description": "Healthcare SaaS handling patient data",
    },
    {
        "first_name": "Alex",
        "email": "alex@constructech.com",
        "company": "BuildTrack",
        "company_name": "BuildTrack",
        "title": "Founder & CEO",
        "industry": "Construction Technology",
        "description": "Construction management platform",
    },
]

# LeadGenJay's Quality Criteria
LEADGENJAY_CRITERIA = {
    "word_count": {
        "ideal": (50, 60),
        "acceptable": (35, 75),
        "description": "Email should be 50-60 words (max 75)"
    },
    "subject_line": {
        "word_count": (2, 4),
        "banned": ["re:", "quick question from", "partnership", "opportunity"],
        "description": "2-4 words, sounds like a colleague"
    },
    "first_line": {
        "required": "curiosity",
        "banned": ["i noticed", "i saw", "i came across", "reaching out", "hope this email finds"],
        "description": "Creates curiosity, NOT 'I noticed X'"
    },
    "em_dash": {
        "allowed": False,
        "description": "NO em dashes (—) - #1 AI writing tell"
    },
    "banned_phrases": [
        "leverage", "synergy", "streamline", "optimize", "game-changing",
        "innovative", "cutting-edge", "sound familiar?", "most teams struggle",
        "you're probably", "scaling is hard", "growth is tough"
    ],
    "specificity": {
        "required": True,
        "description": "Must reference company specifically, not generic template"
    },
    "pain_point": {
        "count": 1,
        "description": "ONE specific pain point, not a list"
    },
    "cta": {
        "type": "soft",
        "examples": ["worth a chat?", "thoughts?", "make sense?"],
        "banned": ["schedule a call", "book a meeting", "let's connect"],
        "description": "Soft CTA only, never 'schedule a call'"
    },
    "case_study": {
        "required": True,
        "must_have_numbers": True,
        "description": "Relevant case study with specific numbers/timeline"
    }
}

def evaluate_email_against_leadgenjay(email: dict, lead: dict) -> dict:
    """Evaluate email against LeadGenJay's criteria"""
    subject = email.get('subject', '')
    body = email.get('body', '')
    
    results = {
        "overall_score": 0,
        "max_score": 100,
        "passes": [],
        "warnings": [],
        "failures": [],
        "details": {}
    }
    
    # 1. Word Count (15 points)
    word_count = len(body.split())
    ideal_min, ideal_max = LEADGENJAY_CRITERIA["word_count"]["ideal"]
    accept_min, accept_max = LEADGENJAY_CRITERIA["word_count"]["acceptable"]
    
    if ideal_min <= word_count <= ideal_max:
        results["overall_score"] += 15
        results["passes"].append(f"✅ Perfect word count: {word_count} words (ideal: 50-60)")
    elif accept_min <= word_count <= accept_max:
        results["overall_score"] += 10
        results["warnings"].append(f"⚠️  Word count OK but not ideal: {word_count} words")
    else:
        results["failures"].append(f"❌ Word count out of range: {word_count} words (acceptable: 45-75)")
    
    results["details"]["word_count"] = word_count
    
    # 2. Subject Line (15 points)
    subject_words = len(subject.split())
    min_words, max_words = LEADGENJAY_CRITERIA["subject_line"]["word_count"]
    
    if min_words <= subject_words <= max_words:
        results["overall_score"] += 10
        results["passes"].append(f"✅ Subject length good: {subject_words} words")
    else:
        results["failures"].append(f"❌ Subject too long/short: {subject_words} words (need 2-4)")
    
    subject_lower = subject.lower()
    banned_in_subject = [b for b in LEADGENJAY_CRITERIA["subject_line"]["banned"] if b in subject_lower]
    subject_has_dash = '-' in subject or '—' in subject
    if banned_in_subject:
        results["failures"].append(f"❌ Subject has banned phrases: {banned_in_subject}")
    elif subject_has_dash:
        results["failures"].append(f"❌ Subject has dashes (looks like em dash): {subject}")
    else:
        results["overall_score"] += 5
        results["passes"].append("✅ No banned phrases in subject")
    
    results["details"]["subject"] = subject
    results["details"]["subject_word_count"] = subject_words
    
    # 3. First Line / Preview Text (20 points)
    first_line = body.split('\n')[0] if body else ""
    first_line_lower = first_line.lower()
    
    banned_first_line = [b for b in LEADGENJAY_CRITERIA["first_line"]["banned"] if b in first_line_lower]
    if not banned_first_line:
        results["overall_score"] += 10
        results["passes"].append("✅ First line passes (no banned phrases)")
    else:
        results["failures"].append(f"❌ First line has banned phrases: {banned_first_line}")
    
    # Check if first line creates curiosity (doesn't immediately reveal it's a pitch)
    # LeadGenJay: preview text must sound like a FRIEND, NO company name, NO pitch hint
    company_name_lower = lead.get('company_name', '').lower() or lead.get('company', '').lower()
    pitch_reveals = ["we built", "we help", "we're a", "our team", "our company",
                     "i was looking at", "i noticed", "i saw", "interesting spot",
                     "caught my eye"]
    first_line_has_company = company_name_lower and company_name_lower in first_line_lower
    first_line_has_pitch = any(reveal in first_line_lower for reveal in pitch_reveals)
    
    if not first_line_has_pitch and not first_line_has_company:
        results["overall_score"] += 10
        results["passes"].append("✅ First line creates curiosity (doesn't reveal pitch)")
    elif first_line_has_company:
        results["warnings"].append(f"⚠️  First line mentions company name - should be pure curiosity")
    else:
        results["warnings"].append("⚠️  First line might reveal pitch too early")
    
    results["details"]["first_line"] = first_line
    
    # 4. Em Dash Check (10 points) - CRITICAL
    if '—' not in body:
        results["overall_score"] += 10
        results["passes"].append("✅ No em dashes (—)")
    else:
        results["failures"].append("❌ CRITICAL: Contains em dash (—) - #1 AI tell!")
    
    # 5. Banned Phrases (15 points)
    body_lower = body.lower()
    found_banned = [p for p in LEADGENJAY_CRITERIA["banned_phrases"] if p in body_lower]
    if not found_banned:
        results["overall_score"] += 15
        results["passes"].append("✅ No banned corporate jargon")
    else:
        results["failures"].append(f"❌ Contains banned phrases: {found_banned}")
    
    # 6. Company Specificity (10 points)
    company_name = lead.get('company_name', '')
    company_name_lower = company_name.lower()
    if company_name_lower in body_lower:
        results["overall_score"] += 10
        results["passes"].append(f"✅ Mentions company name: {company_name}")
    else:
        # Fuzzy match - Qwen sometimes misspells company names
        import difflib
        words = body.split()
        close_match = False
        for word in words:
            clean = word.strip(".,!?'\"():;")
            if clean.lower().endswith("'s"):
                clean = clean[:-2]
            sim = difflib.SequenceMatcher(None, clean.lower(), company_name_lower).ratio()
            if sim >= 0.7 and len(clean) >= 3:
                results["overall_score"] += 5
                results["warnings"].append(f"⚠️  Company name misspelled: '{clean}' (expected '{company_name}')")
                close_match = True
                break
        if not close_match:
            results["failures"].append(f"❌ Doesn't mention company name: {company_name}")
    
    # Check for duplicate lines
    lines = [l.strip().lower() for l in body.split('\n') if l.strip()]
    from collections import Counter
    line_counts = Counter(lines)
    dupes = {line: count for line, count in line_counts.items() if count > 1}
    if dupes:
        for line, count in dupes.items():
            results["warnings"].append(f"⚠️  Duplicate line ({count}x): '{line[:50]}...'")
    
    # 7. Pain Point (10 points)
    # Should have one clear pain point, not multiple
    pain_indicators = ["struggling", "challenge", "issue", "problem", "pain", "bottleneck", "stuck",
                       "drowning", "hitting a wall", "firefighting", "spread too thin",
                       "can't keep up", "slipping", "can't hire", "stretched",
                       "maintenance", "tech debt", "manual process", "build-vs-buy",
                       "speed vs quality", "fixing old", "keeping up"]
    pain_count = sum(1 for p in pain_indicators if p in body_lower)
    
    if pain_count == 1:
        results["overall_score"] += 10
        results["passes"].append("✅ ONE focused pain point")
    elif pain_count == 0:
        results["warnings"].append("⚠️  No clear pain point mentioned")
    else:
        results["warnings"].append(f"⚠️  Multiple pain points mentioned ({pain_count})")
    
    # 8. CTA Check (10 points)
    soft_ctas = ["worth a chat", "thoughts?", "make sense", "worth exploring", "ring any bells",
                 "worth a quick chat", "am i off base", "crazy or worth", "worth 15 min",
                 "curious if this resonates", "make any sense", "does this resonate",
                 "interested?", "open to"]
    hard_ctas = ["schedule a call", "book a meeting", "let's connect", "set up a time",
                 "book a demo", "schedule a demo"]
    
    has_soft_cta = any(cta in body_lower for cta in soft_ctas)
    has_hard_cta = any(cta in body_lower for cta in hard_ctas)
    
    if has_soft_cta and not has_hard_cta:
        results["overall_score"] += 10
        results["passes"].append("✅ Has soft CTA (no hard sell)")
    elif has_hard_cta:
        results["failures"].append("❌ Uses hard CTA (schedule/book)")
    else:
        results["warnings"].append("⚠️  No clear CTA found")
    
    # 9. Case Study with Numbers (15 points)
    has_numbers = any(char.isdigit() for char in body)
    if has_numbers:
        results["overall_score"] += 15
        results["passes"].append("✅ Includes specific numbers/metrics")
    else:
        results["failures"].append("❌ No specific numbers/metrics in case study")
    
    # Cap score at 100
    results["overall_score"] = min(results["overall_score"], results["max_score"])
    
    return results

def print_evaluation(results: dict):
    """Print evaluation results"""
    score = results["overall_score"]
    max_score = results["max_score"]
    percentage = (score / max_score) * 100
    
    print(f"\n{'='*80}")
    print(f"LEADGENJAY QUALITY SCORE: {score}/{max_score} ({percentage:.1f}%)")
    print(f"{'='*80}")
    
    if results["passes"]:
        print(f"\n✅ PASSED ({len(results['passes'])} criteria):")
        for p in results["passes"]:
            print(f"   {p}")
    
    if results["warnings"]:
        print(f"\n⚠️  WARNINGS ({len(results['warnings'])} items):")
        for w in results["warnings"]:
            print(f"   {w}")
    
    if results["failures"]:
        print(f"\n❌ FAILED ({len(results['failures'])} criteria):")
        for f in results["failures"]:
            print(f"   {f}")
    
    print(f"\n📊 Details:")
    print(f"   Word count: {results['details'].get('word_count', 'N/A')}")
    print(f"   Subject: \"{results['details'].get('subject', 'N/A')}\"")
    print(f"   First line: \"{results['details'].get('first_line', 'N/A')[:60]}...\"")
    
    # Overall verdict
    print(f"\n🎯 VERDICT:")
    if percentage >= 85:
        print(f"   🟢 EXCELLENT - Ready to send!")
    elif percentage >= 70:
        print(f"   🟡 GOOD - Minor improvements needed")
    elif percentage >= 50:
        print(f"   🟠 FAIR - Significant improvements needed")
    else:
        print(f"   🔴 POOR - Needs complete rewrite")

# Main test
try:
    from email_generator import EmailGenerator
    
    generator = EmailGenerator()
    
    print(f"\n{'='*80}")
    print(f"Generating {len(test_leads)} test emails...")
    print(f"{'='*80}")
    
    all_results = []
    
    for i, lead in enumerate(test_leads, 1):
        print(f"\n{'='*80}")
        print(f"TEST EMAIL #{i}/{len(test_leads)}")
        print(f"{'='*80}")
        print(f"\n👤 Lead Profile:")
        print(f"   Name: {lead['first_name']}")
        print(f"   Title: {lead['title']}")
        print(f"   Company: {lead['company_name']}")
        print(f"   Industry: {lead['industry']}")
        
        # Generate email
        print(f"\n⏳ Generating email with Ollama (may take 10-30 seconds)...")
        start_time = datetime.now()
        
        try:
            result = generator.generate_initial_email(
                lead=lead,
                campaign_context={
                    "description": lead.get('description', ''),
                    "tone": "casual"
                },
                tone="casual"
            )
            
            generation_time = (datetime.now() - start_time).total_seconds()
            
            print(f"\n✅ Email generated in {generation_time:.1f}s")
            print(f"\n{'─'*80}")
            print(f"SUBJECT: {result.get('subject', 'N/A')}")
            print(f"{'─'*80}")
            print(result.get('body', 'N/A'))
            print(f"{'─'*80}")
            
            # Evaluate against LeadGenJay criteria
            evaluation = evaluate_email_against_leadgenjay(result, lead)
            print_evaluation(evaluation)
            
            # Store for summary
            all_results.append({
                "lead": lead,
                "email": result,
                "evaluation": evaluation,
                "generation_time": generation_time
            })
            
        except Exception as e:
            print(f"\n❌ Error generating email: {e}")
            import traceback
            traceback.print_exc()
    
    # Final summary
    print(f"\n\n{'='*80}")
    print(f"SUMMARY: OLLAMA vs LEADGENJAY STANDARDS")
    print(f"{'='*80}")
    
    if all_results:
        avg_score = sum(r['evaluation']['overall_score'] for r in all_results) / len(all_results)
        avg_time = sum(r['generation_time'] for r in all_results) / len(all_results)
        avg_words = sum(r['evaluation']['details']['word_count'] for r in all_results) / len(all_results)
        
        print(f"\n📊 Aggregate Metrics:")
        print(f"   Average Score: {avg_score:.1f}/100")
        print(f"   Average Generation Time: {avg_time:.1f}s")
        print(f"   Average Word Count: {avg_words:.0f} words")
        
        # Count passes/failures
        total_passes = sum(len(r['evaluation']['passes']) for r in all_results)
        total_warnings = sum(len(r['evaluation']['warnings']) for r in all_results)
        total_failures = sum(len(r['evaluation']['failures']) for r in all_results)
        
        print(f"\n📈 Overall Results:")
        print(f"   ✅ Passes: {total_passes}")
        print(f"   ⚠️  Warnings: {total_warnings}")
        print(f"   ❌ Failures: {total_failures}")
        
        # Most common issues
        all_failures = []
        for r in all_results:
            all_failures.extend(r['evaluation']['failures'])
        
        if all_failures:
            print(f"\n🚨 Common Issues:")
            from collections import Counter
            failure_counts = Counter(all_failures)
            for failure, count in failure_counts.most_common(3):
                print(f"   {count}x: {failure}")
        
        # Recommendation
        print(f"\n🎯 RECOMMENDATION:")
        if avg_score >= 85:
            print(f"   🟢 DEPLOY: Ollama (qwen2.5:7b) meets LeadGenJay standards!")
            print(f"   Quality is excellent - ready for production use.")
        elif avg_score >= 70:
            print(f"   🟡 CAUTION: Ollama quality is good but needs minor tuning")
            print(f"   Consider prompt improvements or review threshold adjustment.")
        else:
            print(f"   🔴 DON'T DEPLOY: Ollama needs significant improvements")
            print(f"   Stick with Groq until prompt engineering improves.")
        
        # Save results to file
        output_file = "tests/ollama_leadgenjay_test_results.json"
        with open(output_file, 'w') as f:
            # Convert datetime objects to strings for JSON
            json_results = []
            for r in all_results:
                json_results.append({
                    "lead": r["lead"],
                    "email": r["email"],
                    "evaluation": {
                        "score": r["evaluation"]["overall_score"],
                        "max_score": r["evaluation"]["max_score"],
                        "percentage": (r["evaluation"]["overall_score"] / r["evaluation"]["max_score"]) * 100,
                        "passes": r["evaluation"]["passes"],
                        "warnings": r["evaluation"]["warnings"],
                        "failures": r["evaluation"]["failures"],
                        "details": r["evaluation"]["details"]
                    },
                    "generation_time": r["generation_time"],
                    "timestamp": datetime.now().isoformat()
                })
            
            json.dump(json_results, f, indent=2)
        
        print(f"\n💾 Results saved to: {output_file}")
    
except Exception as e:
    print(f"\n❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"\n{'='*80}")
print(f"TEST COMPLETE")
print(f"{'='*80}\n")
