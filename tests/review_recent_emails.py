"""
Fetch and critically review all emails created after Wed Jan 21 23:54:22 2026 +0500
Based on LeadGenJay cold email guidelines
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from collections import Counter
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
import config

# Connect to database
client = MongoClient(config.DATABASE_URL)
db = client.get_database()
emails_collection = db["emails"]
leads_collection = db["leads"]

# Cutoff date: Wed Jan 21 23:54:22 2026 +0500
# Convert to UTC: +0500 means subtract 5 hours
# Jan 21, 2026 23:54:22 +0500 = Jan 21, 2026 18:54:22 UTC
CUTOFF_DATE = datetime(2026, 1, 21, 18, 54, 22)


def fetch_emails_after_date():
    """Fetch all emails created after the cutoff date with lead info"""
    
    pipeline = [
        {
            "$match": {
                "created_at": {"$gt": CUTOFF_DATE}
            }
        },
        {
            "$lookup": {
                "from": "leads",
                "localField": "lead_id",
                "foreignField": "_id",
                "as": "lead"
            }
        },
        {
            "$unwind": {"path": "$lead", "preserveNullAndEmptyArrays": True}
        },
        {
            "$project": {
                "subject": 1,
                "body": 1,
                "email_type": 1,
                "status": 1,
                "sent_at": 1,
                "created_at": 1,
                "lead_email": "$lead.email",
                "lead_name": "$lead.full_name",
                "lead_company": "$lead.company",
                "lead_title": "$lead.title",
                "lead_industry": "$lead.industry"
            }
        },
        {"$sort": {"created_at": 1}}
    ]
    
    return list(emails_collection.aggregate(pipeline))


def analyze_patterns(emails):
    """Analyze emails for templated patterns per LeadGenJay guidelines"""
    
    issues = []
    bodies = [e.get('body', '').lower() for e in emails]
    subjects = [e.get('subject', '').lower() for e in emails]
    
    print("\n" + "="*80)
    print("🔍 CRITICAL LEADGENJAY PATTERN ANALYSIS")
    print("="*80)
    print(f"\n📧 Analyzing {len(emails)} emails for templated patterns...\n")
    
    # ========================================================================
    # 1. OPENING PATTERNS
    # ========================================================================
    print("─"*80)
    print("1. OPENING PATTERNS (first 20 characters)")
    print("─"*80)
    
    openings = [b[:20] if len(b) >= 20 else b for b in bodies if b]
    opening_counts = Counter(openings)
    
    for opening, count in opening_counts.most_common(10):
        pct = (count / len(bodies)) * 100 if bodies else 0
        if pct > 40:
            print(f"   ❌ '{opening}...' used {count}/{len(bodies)} times ({pct:.0f}%) - TOO REPETITIVE")
            issues.append(f"Opening '{opening[:15]}...' used {pct:.0f}% of time")
        elif pct > 20:
            print(f"   ⚠️  '{opening}...' used {count}/{len(bodies)} times ({pct:.0f}%) - borderline")
        else:
            print(f"   ✅ '{opening}...' used {count}/{len(bodies)} times ({pct:.0f}%)")
    
    # ========================================================================
    # 2. REPEATED PHRASES
    # ========================================================================
    print("\n" + "─"*80)
    print("2. REPEATED PHRASES (appearing in 40%+ of emails)")
    print("─"*80)
    
    phrases_to_check = [
        # Common openings
        "yo—", "yo -", "hey ", "hi ", "hope this finds",
        # Observations
        "caught my eye", "looks awesome", "sounds awesome",
        "must be wild", "must be tough", "must be tricky", "must be challenging",
        "i noticed", "i saw", "i was checking out",
        # Vague references
        "a similar company", "similar company", "another company",
        "new feature", "new ai", "new platform", "new tool",
        # CTAs
        "worth a quick chat", "worth a chat", "interested?",
        "make sense?", "worth exploring?", "thoughts?",
        # Emojis (overuse check)
        "🔥", "🤔", "😀", "👀", "💡", "🚀",
        # Sales-y phrases
        "game changer", "game-changer", "cutting edge", "state of the art",
        "revolutionary", "transform your", "increase your",
    ]
    
    phrase_issues = []
    for phrase in phrases_to_check:
        count = sum(1 for b in bodies if phrase in b)
        if count > 0:
            pct = (count / len(bodies)) * 100 if bodies else 0
            if pct >= 60:
                print(f"   ❌ '{phrase}' - {count}/{len(bodies)} ({pct:.0f}%) - PATTERN DETECTED")
                phrase_issues.append(f"'{phrase}' used in {pct:.0f}% of emails")
            elif pct >= 40:
                print(f"   ⚠️  '{phrase}' - {count}/{len(bodies)} ({pct:.0f}%) - borderline")
            elif pct >= 15:
                print(f"   📊 '{phrase}' - {count}/{len(bodies)} ({pct:.0f}%)")
    
    issues.extend(phrase_issues)
    
    # ========================================================================
    # 3. CTA VARIATION
    # ========================================================================
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
        elif "worth exploring" in b:
            ctas.append("worth exploring?")
        elif "thoughts?" in b:
            ctas.append("thoughts?")
        elif "let me know" in b:
            ctas.append("let me know")
        else:
            ctas.append("other")
    
    cta_counts = Counter(ctas)
    for cta, count in cta_counts.most_common():
        pct = (count / len(bodies)) * 100 if bodies else 0
        if pct >= 80:
            print(f"   ❌ '{cta}' used {count}/{len(bodies)} ({pct:.0f}%) - NO VARIATION")
            issues.append(f"CTA '{cta}' used in {pct:.0f}% of emails")
        elif pct >= 60:
            print(f"   ⚠️  '{cta}' used {count}/{len(bodies)} ({pct:.0f}%) - needs more variation")
        elif pct >= 30:
            print(f"   📊 '{cta}' used {count}/{len(bodies)} ({pct:.0f}%)")
        else:
            print(f"   ✅ '{cta}' used {count}/{len(bodies)} ({pct:.0f}%)")
    
    # ========================================================================
    # 4. SUBJECT LINE VARIATION
    # ========================================================================
    print("\n" + "─"*80)
    print("4. SUBJECT LINE VARIATION")
    print("─"*80)
    
    subj_counts = Counter(subjects)
    duplicates = 0
    for subj, count in subj_counts.most_common():
        if count > 1:
            print(f"   ❌ '{subj}' used {count} times - DUPLICATE SUBJECT")
            duplicates += count - 1
        else:
            print(f"   ✅ '{subj}' - unique")
    
    if duplicates > 0:
        issues.append(f"{duplicates} duplicate subject lines")
    
    # ========================================================================
    # 5. WORD COUNT CHECK (LeadGenJay: keep it SHORT - 50-75 words ideal)
    # ========================================================================
    print("\n" + "─"*80)
    print("5. WORD COUNT CHECK (Ideal: 50-75 words)")
    print("─"*80)
    
    word_counts = [len(b.split()) for b in bodies if b]
    if word_counts:
        avg_words = sum(word_counts) / len(word_counts)
        min_words = min(word_counts)
        max_words = max(word_counts)
        
        too_long = sum(1 for wc in word_counts if wc > 100)
        too_short = sum(1 for wc in word_counts if wc < 40)
        just_right = sum(1 for wc in word_counts if 50 <= wc <= 75)
        
        print(f"   📊 Average: {avg_words:.0f} words")
        print(f"   📊 Range: {min_words} - {max_words} words")
        print(f"   ✅ Just right (50-75): {just_right}/{len(word_counts)} ({just_right/len(word_counts)*100:.0f}%)")
        
        if too_long > 0:
            pct = too_long / len(word_counts) * 100
            print(f"   ❌ Too long (>100 words): {too_long}/{len(word_counts)} ({pct:.0f}%)")
            if pct > 20:
                issues.append(f"{pct:.0f}% of emails are too long (>100 words)")
        
        if too_short > 0:
            pct = too_short / len(word_counts) * 100
            print(f"   ⚠️  Too short (<40 words): {too_short}/{len(word_counts)} ({pct:.0f}%)")
    
    # ========================================================================
    # 6. SPECIFICITY CHECK (LeadGenJay: "specify WHAT you saw")
    # ========================================================================
    print("\n" + "─"*80)
    print("6. SPECIFICITY CHECK (LeadGenJay: 'specify WHAT you saw')")
    print("─"*80)
    
    vague_count = 0
    for email in emails:
        body = email.get('body', '').lower()
        lead_name = email.get('lead_name', 'Unknown')
        company = email.get('lead_company', '')
        
        # Check for vague "new feature" without specifics
        vague_phrases = ["new feature", "new ai feature", "new product", "your platform"]
        has_vague = any(vp in body for vp in vague_phrases)
        
        # Check if there are specifics mentioned
        has_specifics = any(spec in body for spec in [
            company.lower() if company else 'XXXNOTFOUNDXXX',
            'fraud', 'route', 'cross-border', 'analytics', 'telehealth',
            'payment', 'checkout', 'dashboard', 'api', 'integration'
        ])
        
        if has_vague and not has_specifics:
            print(f"   ❌ Email to {lead_name} ({company}): Vague feature reference without specifics")
            vague_count += 1
    
    if vague_count > 0:
        pct = vague_count / len(emails) * 100 if emails else 0
        if pct > 20:
            issues.append(f"{pct:.0f}% of emails have vague feature references")
    
    if vague_count == 0:
        print("   ✅ All emails have specific observations")
    
    # ========================================================================
    # 7. PERSONALIZATION CHECK
    # ========================================================================
    print("\n" + "─"*80)
    print("7. PERSONALIZATION CHECK")
    print("─"*80)
    
    no_personalization = 0
    for email in emails:
        body = email.get('body', '').lower()
        company = (email.get('lead_company') or '').lower()
        name = (email.get('lead_name') or '').lower().split()[0] if email.get('lead_name') else ''
        
        has_company = company and company in body
        has_name = name and name in body
        
        if not has_company and not has_name:
            lead_name = email.get('lead_name', 'Unknown')
            print(f"   ⚠️  Email to {lead_name}: No company or name mentioned in body")
            no_personalization += 1
    
    if no_personalization > 0:
        pct = no_personalization / len(emails) * 100 if emails else 0
        if pct > 30:
            issues.append(f"{pct:.0f}% of emails lack personalization")
        print(f"\n   📊 {no_personalization}/{len(emails)} emails lack company/name in body")
    else:
        print("   ✅ All emails have personalization")
    
    # ========================================================================
    # 8. SPAM TRIGGER WORDS
    # ========================================================================
    print("\n" + "─"*80)
    print("8. SPAM TRIGGER WORDS CHECK")
    print("─"*80)
    
    spam_words = [
        "free", "act now", "limited time", "click here", "buy now",
        "no obligation", "risk free", "winner", "congratulations",
        "urgent", "100%", "guarantee", "promise", "amazing deal"
    ]
    
    spam_detected = []
    for word in spam_words:
        count = sum(1 for b in bodies if word in b)
        if count > 0:
            print(f"   ⚠️  '{word}' found in {count} emails")
            spam_detected.append(word)
    
    if not spam_detected:
        print("   ✅ No spam trigger words detected")
    
    return issues


def print_email_summary(emails):
    """Print summary of all emails"""
    
    print("\n" + "="*80)
    print("📧 EMAILS CREATED AFTER Wed Jan 21 23:54:22 2026 +0500")
    print("="*80)
    print(f"Total emails found: {len(emails)}")
    print(f"Cutoff date (UTC): {CUTOFF_DATE}")
    
    if not emails:
        print("\n⚠️  No emails found after the cutoff date!")
        return
    
    # Status breakdown
    statuses = Counter([e.get('status', 'unknown') for e in emails])
    print("\n📊 Status breakdown:")
    for status, count in statuses.most_common():
        print(f"   • {status}: {count}")
    
    # Type breakdown
    types = Counter([e.get('email_type', 'unknown') for e in emails])
    print("\n📊 Email type breakdown:")
    for email_type, count in types.most_common():
        print(f"   • {email_type}: {count}")
    
    print("\n" + "─"*80)
    print("INDIVIDUAL EMAILS:")
    print("─"*80)
    
    for i, email in enumerate(emails, 1):
        print(f"\n{'━'*80}")
        print(f"📧 EMAIL #{i}")
        print(f"{'━'*80}")
        print(f"TO: {email.get('lead_name', 'N/A')} <{email.get('lead_email', 'N/A')}>")
        print(f"COMPANY: {email.get('lead_company', 'N/A')}")
        print(f"TITLE: {email.get('lead_title', 'N/A')}")
        print(f"INDUSTRY: {email.get('lead_industry', 'N/A')}")
        print(f"STATUS: {email.get('status', 'N/A')}")
        print(f"TYPE: {email.get('email_type', 'N/A')}")
        print(f"CREATED: {email.get('created_at', 'N/A')}")
        print(f"\n📝 SUBJECT: {email.get('subject', 'N/A')}")
        print(f"\n📄 BODY:\n{'-'*40}")
        print(email.get('body', 'NO BODY'))
        print(f"{'-'*40}")
        print(f"Word count: {len(email.get('body', '').split())}")


def print_recommendations(issues):
    """Print recommendations based on issues found"""
    
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
        print("💡 RECOMMENDATIONS:")
        print("─"*80)
        
        if any("opening" in i.lower() for i in issues):
            print("   • Vary openings: 'Hey', 'Yo—', '[Company]...', '[Name]!', or start with observation")
        
        if any("similar company" in i.lower() for i in issues):
            print("   • Use actual case study names when industry matches")
        
        if any("cta" in i.lower() for i in issues):
            print("   • Rotate CTAs: 'interested?', 'make sense?', 'worth exploring?', 'thoughts?'")
        
        if any("new feature" in i.lower() or "vague" in i.lower() for i in issues):
            print("   • Be SPECIFIC about what feature - research each company")
        
        if any("too long" in i.lower() for i in issues):
            print("   • Keep emails to 50-75 words max (LeadGenJay recommendation)")
        
        if any("personalization" in i.lower() for i in issues):
            print("   • Always mention company name or specific observation in the email body")
        
        if any("duplicate subject" in i.lower() for i in issues):
            print("   • Create unique subject lines - personalize with company/name")


def export_to_json(emails, issues):
    """Export analysis results to JSON"""
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, "recent_emails_review.json")
    
    export_data = {
        "analysis_date": datetime.now().isoformat(),
        "cutoff_date": CUTOFF_DATE.isoformat(),
        "total_emails": len(emails),
        "issues_found": len(issues),
        "issues": issues,
        "emails": []
    }
    
    for email in emails:
        export_data["emails"].append({
            "to": email.get('lead_name', 'N/A'),
            "email": email.get('lead_email', 'N/A'),
            "company": email.get('lead_company', 'N/A'),
            "title": email.get('lead_title', 'N/A'),
            "industry": email.get('lead_industry', 'N/A'),
            "status": email.get('status', 'N/A'),
            "type": email.get('email_type', 'N/A'),
            "created_at": str(email.get('created_at', 'N/A')),
            "subject": email.get('subject', 'N/A'),
            "body": email.get('body', 'NO BODY'),
            "word_count": len(email.get('body', '').split())
        })
    
    with open(output_file, 'w') as f:
        json.dump(export_data, f, indent=2, default=str)
    
    print(f"\n📄 Full analysis exported to: {output_file}")


def main():
    """Main function to run the analysis"""
    
    print("\n" + "="*80)
    print("🔎 FETCHING EMAILS FROM DATABASE")
    print("="*80)
    print(f"Cutoff: Wed Jan 21 23:54:22 2026 +0500 (UTC: {CUTOFF_DATE})")
    
    # Fetch emails
    emails = fetch_emails_after_date()
    
    if not emails:
        print(f"\n⚠️  No emails found after {CUTOFF_DATE}")
        print("\nDebug info:")
        total = emails_collection.count_documents({})
        print(f"   Total emails in database: {total}")
        
        # Get the most recent email date
        latest = emails_collection.find_one(sort=[("created_at", -1)])
        if latest:
            print(f"   Most recent email created_at: {latest.get('created_at')}")
        return
    
    # Print email summary
    print_email_summary(emails)
    
    # Analyze patterns
    issues = analyze_patterns(emails)
    
    # Print recommendations
    print_recommendations(issues)
    
    # Export to JSON
    export_to_json(emails, issues)


if __name__ == "__main__":
    main()
