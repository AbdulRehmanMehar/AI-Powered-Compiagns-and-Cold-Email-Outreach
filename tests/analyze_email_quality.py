"""
Improved Email Analysis Script
Analyzes emails against LeadGenJay's actual guidelines with meaningful checks
"""

from pymongo import MongoClient
from datetime import datetime
from typing import Dict, List, Any
import config
import json
import re

client = MongoClient(config.DATABASE_URL)
db = client.get_database()
emails_collection = db["emails"]
leads_collection = db["leads"]


def fetch_emails_with_bodies(limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch emails with their actual content"""
    
    pipeline = [
        {"$lookup": {
            "from": "leads",
            "localField": "lead_id",
            "foreignField": "_id",
            "as": "lead"
        }},
        {"$unwind": {"path": "$lead", "preserveNullAndEmptyArrays": True}},
        {"$project": {
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
        }},
        {"$sort": {"created_at": -1}},
        {"$limit": limit}
    ]
    
    return list(emails_collection.aggregate(pipeline))


def analyze_email_quality(email: Dict) -> Dict[str, Any]:
    """
    Analyze email against LeadGenJay's ACTUAL guidelines:
    
    1. Subject: 2-4 words, looks like colleague
    2. First line: Specific curiosity, NOT generic "saw something interesting"
    3. Body: Under 75 words, one pain point
    4. CTA: Soft, not "schedule a call"
    5. No banned phrases
    6. Relevant case study (not same one for everyone)
    """
    
    subject = email.get("subject", "")
    body = email.get("body", "")
    company = email.get("lead_company", "")
    
    issues = []
    warnings = []
    good = []
    score = 100
    
    # === SUBJECT LINE CHECKS ===
    subject_words = len(subject.split())
    if subject_words > 4:
        issues.append(f"❌ Subject too long ({subject_words} words) - max 4")
        score -= 15
    elif subject_words >= 2:
        good.append(f"✅ Good subject length ({subject_words} words)")
    
    bad_subjects = ["quick question", "partnership", "intro", "introduction", "opportunity"]
    if any(bs in subject.lower() for bs in bad_subjects):
        issues.append("❌ Subject uses burned/bad pattern")
        score -= 20
    
    # === FIRST LINE CHECKS (Preview text) ===
    first_line = body.split('\n')[0].strip() if body else ""
    
    # Check for generic "saw something" without specifics
    if "saw something" in first_line.lower() and company.lower() not in first_line.lower():
        if not any(specific in first_line.lower() for specific in ["ai", "tool", "product", "feature", "launch"]):
            issues.append("❌ Generic 'saw something' without specifics - this is a lie")
            score -= 25
    
    # Check for bad opening patterns
    bad_opens = [
        "i hope this finds you",
        "i'm reaching out",
        "i noticed your company",
        "my name is",
        "i wanted to"
    ]
    if any(bo in first_line.lower() for bo in bad_opens):
        issues.append(f"❌ Opens with banned phrase")
        score -= 20
    
    # Check if first line mentions something SPECIFIC
    if company.lower() in first_line.lower() or any(word in first_line.lower() for word in ["ai", "tool", "launch", "product", "feature", "growth", "team"]):
        good.append("✅ First line is specific to company/product")
    else:
        warnings.append("⚠️ First line could be more specific")
        score -= 5
    
    # === BODY LENGTH ===
    word_count = len(body.split())
    if word_count > 100:
        issues.append(f"❌ Too long ({word_count} words) - should be under 75")
        score -= 20
    elif word_count > 75:
        warnings.append(f"⚠️ Slightly long ({word_count} words) - ideal is under 75")
        score -= 5
    else:
        good.append(f"✅ Good length ({word_count} words)")
    
    # === BANNED PHRASES ===
    banned = [
        "leverage", "synergy", "streamline", "incentivize",
        "just following up", "circling back", "touching base",
        "reaching out", "i hope this email"
    ]
    found_banned = [b for b in banned if b in body.lower()]
    if found_banned:
        issues.append(f"❌ Contains banned phrase(s): {', '.join(found_banned)}")
        score -= 10 * len(found_banned)
    
    # === CTA CHECK ===
    bad_ctas = ["schedule a call", "hop on a call", "book a meeting", "are you free", "calendar"]
    good_ctas = ["worth a chat", "make sense", "open to", "interested", "worth exploring"]
    
    if any(bc in body.lower() for bc in bad_ctas):
        issues.append("❌ CTA too aggressive - never 'schedule a call'")
        score -= 15
    
    if any(gc in body.lower() for gc in good_ctas):
        good.append("✅ Uses soft CTA")
    
    # === CASE STUDY CHECK ===
    case_studies_mentioned = []
    if "roboapply" in body.lower():
        case_studies_mentioned.append("RoboApply")
    if "stratmap" in body.lower():
        case_studies_mentioned.append("StratMap")
    if "timpl" in body.lower():
        case_studies_mentioned.append("Timpl")
    if "fintech" in body.lower():
        case_studies_mentioned.append("Fintech client")
    if "health" in body.lower():
        case_studies_mentioned.append("HealthTech client")
    
    if len(case_studies_mentioned) > 1:
        issues.append(f"❌ Multiple case studies - should be ONE: {case_studies_mentioned}")
        score -= 10
    elif len(case_studies_mentioned) == 1:
        good.append(f"✅ Single case study: {case_studies_mentioned[0]}")
    
    # Check case study has specific numbers
    if re.search(r'\d+\.?\d*[x%]|\d+ weeks?|\d+ months?', body):
        good.append("✅ Includes specific numbers")
    else:
        warnings.append("⚠️ Could include more specific numbers")
    
    score = max(0, min(100, score))
    
    return {
        "email_id": str(email.get("_id", "")),
        "subject": subject,
        "lead": f"{email.get('lead_name', 'Unknown')} at {email.get('lead_company', 'Unknown')}",
        "word_count": word_count,
        "score": score,
        "grade": "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 50 else "F",
        "issues": issues,
        "warnings": warnings,
        "good": good,
        "status": email.get("status", "unknown")
    }


def check_for_duplicate_sends() -> Dict[str, int]:
    """Check if same leads are being emailed multiple times (spam behavior)"""
    
    pipeline = [
        {"$match": {"status": {"$in": ["sent", "failed"]}}},
        {"$group": {
            "_id": "$lead_id",
            "count": {"$sum": 1}
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    duplicates = list(emails_collection.aggregate(pipeline))
    
    return {
        "leads_emailed_multiple_times": len(duplicates),
        "worst_offenders": [{"lead_id": str(d["_id"]), "emails_sent": d["count"]} for d in duplicates[:5]]
    }


def run_full_analysis():
    """Run complete analysis and print report"""
    
    emails = fetch_emails_with_bodies(50)
    
    print("\n" + "="*80)
    print("📧 LEADGENJAY-ALIGNED EMAIL QUALITY ANALYSIS")
    print("="*80)
    
    if not emails:
        print("\n❌ No emails found in database")
        return
    
    print(f"\nAnalyzing {len(emails)} most recent emails...\n")
    
    # Analyze each email
    analyses = [analyze_email_quality(email) for email in emails]
    
    # Calculate stats
    avg_score = sum(a["score"] for a in analyses) / len(analyses)
    grade_counts = {}
    for a in analyses:
        grade_counts[a["grade"]] = grade_counts.get(a["grade"], 0) + 1
    
    # Collect all issues
    all_issues = []
    for a in analyses:
        all_issues.extend(a["issues"])
    
    issue_counts = {}
    for issue in all_issues:
        simple = issue.split("-")[0].strip() if "-" in issue else issue[:50]
        issue_counts[simple] = issue_counts.get(simple, 0) + 1
    
    # Print summary
    print("📊 OVERALL SCORES:")
    print(f"   Average Score: {avg_score:.1f}/100")
    print(f"   Grade Distribution: A={grade_counts.get('A', 0)}, B={grade_counts.get('B', 0)}, C={grade_counts.get('C', 0)}, F={grade_counts.get('F', 0)}")
    
    print("\n🔴 TOP ISSUES:")
    sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
    for issue, count in sorted_issues[:7]:
        print(f"   {issue}: {count} emails")
    
    # Check for spam behavior
    print("\n🚨 SPAM CHECK:")
    duplicates = check_for_duplicate_sends()
    if duplicates["leads_emailed_multiple_times"] > 0:
        print(f"   ❌ {duplicates['leads_emailed_multiple_times']} leads emailed multiple times!")
        for offender in duplicates["worst_offenders"]:
            print(f"      - Lead emailed {offender['emails_sent']} times")
    else:
        print("   ✅ No duplicate sends detected")
    
    # Show sample emails
    print("\n" + "-"*80)
    print("📝 SAMPLE EMAIL ANALYSIS (5 emails):")
    print("-"*80)
    
    for i, a in enumerate(analyses[:5], 1):
        print(f"\n{'─'*60}")
        print(f"Email #{i}: {a['lead']}")
        print(f"Subject: \"{a['subject']}\"")
        print(f"Score: {a['score']}/100 (Grade: {a['grade']})")
        print(f"Words: {a['word_count']}")
        
        if a['good']:
            print(f"Good: {' | '.join(a['good'][:3])}")
        if a['issues']:
            print(f"Issues: {' | '.join(a['issues'][:3])}")
        if a['warnings']:
            print(f"Warnings: {' | '.join(a['warnings'][:2])}")
    
    # Export
    export_data = {
        "analysis_date": datetime.utcnow().isoformat(),
        "summary": {
            "total_analyzed": len(analyses),
            "average_score": round(avg_score, 1),
            "grades": grade_counts
        },
        "top_issues": sorted_issues[:10],
        "duplicate_sends": duplicates,
        "emails": analyses
    }
    
    with open("email_quality_report.json", "w") as f:
        json.dump(export_data, f, indent=2, default=str)
    
    print(f"\n\n📄 Full report saved to: email_quality_report.json")
    print("="*80)


if __name__ == "__main__":
    run_full_analysis()
