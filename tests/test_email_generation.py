"""
Critical Email Generation Test v2
Generate multiple emails and critically analyze them against LeadGenJay guidelines
"""

import sys
sys.path.insert(0, '..')
from email_generator import EmailGenerator
import json

generator = EmailGenerator()

# Test with diverse leads to see variation
test_leads = [
    {
        "first_name": "James",
        "full_name": "James Wilson",
        "title": "CTO",
        "company": "DataVault",
        "industry": "Data Analytics",
    },
    {
        "first_name": "Sarah",
        "full_name": "Sarah Martinez",
        "title": "VP Product",
        "company": "RetailAI",
        "industry": "Retail Tech",
    },
    {
        "first_name": "Kevin",
        "full_name": "Kevin Park",
        "title": "Founder",
        "company": "CyberShield",
        "industry": "Cybersecurity",
    },
    {
        "first_name": "Emily",
        "full_name": "Emily Johnson",
        "title": "Head of Engineering",
        "company": "EduLearn",
        "industry": "EdTech",
    },
    {
        "first_name": "Marcus",
        "full_name": "Marcus Brown",
        "title": "CEO",
        "company": "GreenFleet",
        "industry": "Electric Vehicles / CleanTech",
    },
]

context = {"single_pain_point": "shipping features faster", "front_end_offer": "free architecture review"}

print("="*80)
print("🔬 CRITICAL EMAIL GENERATION TEST v2 - HUMAN READABILITY CHECK")
print("="*80)

all_emails = []
total_issues = 0

for i, lead in enumerate(test_leads, 1):
    print(f"\n{'─'*80}")
    print(f"TEST #{i}: {lead['first_name']} - {lead['title']} at {lead['company']} ({lead['industry']})")
    print(f"{'─'*80}")
    
    email = generator.generate_initial_email(lead, context)
    
    print(f"\n📧 GENERATED EMAIL:")
    print(f"   Subject: {email['subject']}")
    print(f"\n   Body:")
    for line in email['body'].split('\n'):
        print(f"   {line}")
    
    print(f"\n📊 METRICS:")
    word_count = len(email['body'].split())
    print(f"   Word count: {word_count}")
    print(f"   Case study: {email.get('case_study_used', 'N/A')}")
    
    # Critical analysis
    body = email['body']
    subject = email['subject']
    issues = []
    
    print(f"\n🔍 LEADGENJAY COMPLIANCE CHECK:")
    
    # 1. Check for "I noticed" opener (the #1 issue)
    first_line = body.split('\n')[0].lower()
    if first_line.startswith("i noticed") or "i noticed" in first_line[:50]:
        issues.append("❌ ROBOTIC: Opens with 'I noticed' - instant delete")
    elif first_line.startswith("i saw") or "i saw that" in first_line[:50]:
        issues.append("❌ TEMPLATED: Opens with 'I saw' - looks automated")
    else:
        print("   ✅ Opening avoids robotic 'I noticed/saw' pattern")
    
    # 2. Check for formal corporate questions
    formal_patterns = [
        "how are you navigating",
        "how are you ensuring", 
        "how are you managing",
        "how are you handling",
        "how are you balancing",
        "how's that affecting",
        "how are you thinking"
    ]
    found_formal = [p for p in formal_patterns if p in body.lower()]
    if found_formal:
        issues.append(f"❌ TOO FORMAL: '{found_formal[0]}' - no human texts like this")
    else:
        print("   ✅ No overly formal corporate questions")
    
    # 3. Check subject length
    subj_words = len(subject.split())
    if subj_words > 4:
        issues.append(f"❌ Subject too long ({subj_words} words)")
    else:
        print(f"   ✅ Subject length OK ({subj_words} words)")
    
    # 4. Check for double CTAs
    ctas = ["worth a chat", "worth a quick chat", "interested", "make sense", "open to", "curious if", "what do you think", "think it's worth", "thoughts?", "worth exploring", "curious to hear", "could help", "want to chat", "worth a look"]
    cta_count = sum(1 for c in ctas if c in body.lower())
    if cta_count > 1:
        issues.append(f"❌ DESPERATE: Multiple CTAs ({cta_count}) - pick ONE")
    elif cta_count == 1:
        print("   ✅ Single soft CTA")
    else:
        issues.append("⚠️  No clear CTA detected")
    
    # 5. Check word count (target 40-55)
    if word_count > 75:
        issues.append(f"❌ TOO LONG: {word_count} words (target <60)")
    elif word_count > 60:
        issues.append(f"⚠️  Slightly long: {word_count} words")
    else:
        print(f"   ✅ Good length: {word_count} words")
    
    # 6. Check for corporate jargon
    jargon = ["leverage", "synergy", "streamline", "optimize", "utilize", "innovative", "cutting-edge", "game-changing"]
    found_jargon = [w for w in jargon if w in body.lower()]
    if found_jargon:
        issues.append(f"❌ CORPORATE JARGON: {found_jargon}")
    else:
        print("   ✅ No corporate jargon")
    
    # 7. Human readability - sentence length (LeadGenJay says "short", typically under 20)
    sentences = [s.strip() for s in body.replace('\n', ' ').split('.') if s.strip()]
    if sentences:
        max_sentence = max(len(s.split()) for s in sentences)
        if max_sentence > 20:
            issues.append(f"❌ Long sentence ({max_sentence} words) - break it up")
        elif max_sentence > 15:
            print(f"   ⚠️  Moderate sentence length (max {max_sentence} words) - acceptable")
        else:
            print(f"   ✅ Sentences are short (max {max_sentence} words)")
    
    # 8. Does it sound like a text message?
    company_name = lead['company'].lower()
    text_indicators = any([
        body.lower().startswith(company_name),
        "!" in body,
        "?" in body,
        len(body.split('\n')) >= 2,  # Has line breaks (casual formatting)
    ])
    if text_indicators:
        print("   ✅ Has casual text-like elements")
    else:
        issues.append("⚠️  May not feel like a text message")
    
    # Print issues
    if issues:
        print(f"\n   🚨 ISSUES FOUND:")
        for issue in issues:
            print(f"   {issue}")
            total_issues += 1
    else:
        print(f"\n   ✨ PASSED ALL CHECKS!")
    
    all_emails.append({
        "lead": f"{lead['first_name']} at {lead['company']}",
        "subject": subject,
        "body": body,
        "word_count": word_count,
        "case_study": email.get('case_study_used'),
        "issues": issues
    })

print("\n" + "="*80)
print("📋 FINAL SUMMARY")
print("="*80)

# Check for variation
subjects = [e['subject'] for e in all_emails]
unique_subjects = len(set(subjects))
print(f"\n📊 Subject variation: {unique_subjects}/{len(subjects)} unique")
if unique_subjects < len(subjects) * 0.6:
    print("   ❌ NOT ENOUGH VARIATION")
else:
    print("   ✅ Good variation")

# Check opening variation
first_lines = [e['body'].split('\n')[0][:30] for e in all_emails]
unique_openings = len(set(first_lines))
print(f"\n📊 Opening variation: {unique_openings}/{len(first_lines)} unique first lines")
if unique_openings < len(first_lines) * 0.8:
    print("   ❌ OPENINGS ARE TOO SIMILAR - looks templated")
else:
    print("   ✅ Good opening variation")

avg_words = sum(e['word_count'] for e in all_emails) / len(all_emails)
print(f"\n📊 Average word count: {avg_words:.1f}")
if avg_words > 60:
    print("   ⚠️  Slightly high (target 40-55)")
else:
    print("   ✅ Good average length")

print(f"\n🎯 TOTAL ISSUES FOUND: {total_issues}")
if total_issues == 0:
    print("   🏆 PERFECT - All emails pass LeadGenJay guidelines!")
elif total_issues <= 3:
    print("   ✅ GOOD - Minor issues only")
elif total_issues <= 7:
    print("   ⚠️  NEEDS WORK - Several issues to fix")
else:
    print("   ❌ FAIL - Major overhaul needed")

# Export
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
output_path = os.path.join(script_dir, "test_emails_v2.json")
with open(output_path, "w") as f:
    json.dump(all_emails, f, indent=2)

print(f"\n📄 Full results saved to: tests/test_emails_v2.json")
