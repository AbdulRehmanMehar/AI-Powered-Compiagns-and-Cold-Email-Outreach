"""
CRITICAL Review Against LeadGenJay Guidelines
Analyzes pattern repetition across multiple emails
"""

import json
import os
from collections import Counter

# Load the test results
script_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(script_dir, "test_emails_v2.json"), "r") as f:
    emails = json.load(f)

print("="*80)
print("🔍 CRITICAL LEADGENJAY PATTERN ANALYSIS")
print("="*80)

# Extract all bodies
bodies = [e['body'].lower() for e in emails]
subjects = [e['subject'].lower() for e in emails]

print(f"\n📧 Analyzing {len(emails)} emails for templated patterns...\n")

issues = []

# 1. Check opening patterns
print("─"*80)
print("1. OPENING PATTERNS (first 10 characters)")
print("─"*80)
openings = [b[:20] for b in bodies]
opening_counts = Counter(openings)
for opening, count in opening_counts.most_common():
    pct = count/len(bodies)*100
    if pct > 40:
        print(f"   ❌ '{opening}...' used {count}/{len(bodies)} times ({pct:.0f}%) - TOO REPETITIVE")
        issues.append(f"Opening '{opening[:15]}...' used {pct:.0f}% of time")
    else:
        print(f"   ✅ '{opening}...' used {count} times ({pct:.0f}%)")

# 2. Check for repeated phrases
print("\n" + "─"*80)
print("2. REPEATED PHRASES (appearing in 40%+ of emails)")
print("─"*80)
phrases_to_check = [
    "yo—", "yo -", "hey ",
    "caught my eye", "looks awesome", "sounds awesome",
    "must be wild", "must be tough", "must be tricky",
    "a similar company", "similar company",
    "worth a quick chat", "worth a chat", "interested?",
    "new feature", "new ai", "new platform",
    "🔥", "🤔", "😀",
]

for phrase in phrases_to_check:
    count = sum(1 for b in bodies if phrase in b)
    if count > 0:
        pct = count/len(bodies)*100
        if pct >= 60:
            print(f"   ❌ '{phrase}' - {count}/{len(bodies)} ({pct:.0f}%) - PATTERN DETECTED")
            issues.append(f"'{phrase}' used in {pct:.0f}% of emails")
        elif pct >= 40:
            print(f"   ⚠️  '{phrase}' - {count}/{len(bodies)} ({pct:.0f}%) - borderline")
        else:
            print(f"   ✅ '{phrase}' - {count}/{len(bodies)} ({pct:.0f}%)")

# 3. Check CTA variation
print("\n" + "─"*80)
print("3. CTA VARIATION")
print("─"*80)
ctas = []
for b in bodies:
    if "worth a quick chat" in b:
        ctas.append("worth a quick chat?")
    elif "worth a chat" in b:
        ctas.append("worth a chat?")
    elif "interested?" in b:
        ctas.append("interested?")
    elif "make sense" in b:
        ctas.append("make sense?")
    else:
        ctas.append("other")

cta_counts = Counter(ctas)
for cta, count in cta_counts.most_common():
    pct = count/len(bodies)*100
    if pct >= 80:
        print(f"   ❌ '{cta}' used {count}/{len(bodies)} ({pct:.0f}%) - NO VARIATION")
        issues.append(f"CTA '{cta}' used in {pct:.0f}% of emails")
    elif pct >= 60:
        print(f"   ⚠️  '{cta}' used {count}/{len(bodies)} ({pct:.0f}%) - needs more variation")
    else:
        print(f"   ✅ '{cta}' used {count}/{len(bodies)} ({pct:.0f}%)")

# 4. Check subject variation
print("\n" + "─"*80)
print("4. SUBJECT LINE VARIATION")
print("─"*80)
subj_counts = Counter(subjects)
for subj, count in subj_counts.most_common():
    pct = count/len(subjects)*100
    if count > 1:
        print(f"   ⚠️  '{subj}' used {count} times ({pct:.0f}%)")
    else:
        print(f"   ✅ '{subj}' - unique")

# 5. Check for specificity
print("\n" + "─"*80)
print("5. SPECIFICITY CHECK (LeadGenJay: 'specify WHAT you saw')")
print("─"*80)
vague_count = 0
for i, e in enumerate(emails):
    body = e['body']
    lead = e['lead']
    
    # Check if "new feature" or "new AI" without specifics
    if "new feature" in body.lower() or "new ai feature" in body.lower():
        if not any(specific in body.lower() for specific in ['fraud', 'route', 'cross-border', 'analytics', 'telehealth']):
            print(f"   ❌ Email to {lead}: 'new feature' without specifics")
            vague_count += 1
            issues.append(f"Vague 'new feature' to {lead}")
        else:
            print(f"   ✅ Email to {lead}: Feature is specified")
    else:
        print(f"   ✅ Email to {lead}: No vague 'new feature'")

# 6. Case study usage
print("\n" + "─"*80)
print("6. CASE STUDY USAGE (LeadGenJay: 'relevant case study to industry')")
print("─"*80)
for e in emails:
    body = e['body']
    case_study = e['case_study']
    lead = e['lead']
    
    if "a similar company" in body.lower() and case_study != "generic":
        print(f"   ⚠️  {lead}: Used '{case_study}' but said 'a similar company' - could be more specific")
    else:
        print(f"   ✅ {lead}: Case study '{case_study}'")

# Summary
print("\n" + "="*80)
print("📊 CRITICAL REVIEW SUMMARY")
print("="*80)

if not issues:
    print("\n🏆 NO CRITICAL ISSUES - Emails look production ready!")
else:
    print(f"\n🚨 FOUND {len(issues)} ISSUES:\n")
    for i, issue in enumerate(issues, 1):
        print(f"   {i}. {issue}")
    
    print("\n" + "─"*80)
    print("RECOMMENDATIONS:")
    print("─"*80)
    if any("yo—" in i.lower() for i in issues):
        print("   • Vary openings: 'Hey', 'Yo—', '[Company]...', '[Name]!', just start with observation")
    if any("similar company" in i.lower() for i in issues):
        print("   • Use actual case study names when industry matches")
    if any("cta" in i.lower() for i in issues):
        print("   • Rotate CTAs: 'interested?', 'make sense?', 'worth exploring?', 'thoughts?'")
    if any("new feature" in i.lower() for i in issues):
        print("   • Be SPECIFIC about what feature - research each company")
