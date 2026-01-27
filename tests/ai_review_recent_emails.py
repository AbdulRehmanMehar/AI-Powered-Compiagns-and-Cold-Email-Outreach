"""
Review Recent Emails with AI Reviewer

Fetches all emails created after Wed Jan 21 23:54:22 2026 +0500 from the database
and runs them through the production-ready AI reviewer.

Generates detailed reports on:
- Pass/fail rates
- Common issues
- Specific violations
- Rewrite recommendations
"""

import os
import sys
from datetime import datetime
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
import config
from email_reviewer import EmailReviewer, ReviewStatus, format_review_report

# Connect to database
client = MongoClient(config.DATABASE_URL)
db = client.get_database()
emails_collection = db["emails"]
leads_collection = db["leads"]

# Cutoff date: Wed Jan 21 23:54:22 2026 +0500 = Jan 21, 2026 18:54:22 UTC
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
                "lead_first_name": "$lead.first_name",
                "lead_company": "$lead.company",
                "lead_title": "$lead.title",
                "lead_industry": "$lead.industry"
            }
        },
        {"$sort": {"created_at": 1}}
    ]
    
    return list(emails_collection.aggregate(pipeline))


def run_ai_review():
    """Run AI review on all recent emails"""
    
    print("\n" + "="*80)
    print("🤖 AI-POWERED EMAIL REVIEW")
    print("="*80)
    print(f"Cutoff: Wed Jan 21 23:54:22 2026 +0500 (UTC: {CUTOFF_DATE})")
    print("Using LeadGenJay / Eric Nowoslawski guidelines...")
    
    # Fetch emails
    emails = fetch_emails_after_date()
    
    if not emails:
        print(f"\n⚠️  No emails found after {CUTOFF_DATE}")
        return
    
    print(f"\n📧 Found {len(emails)} emails to review\n")
    
    # Initialize reviewer
    reviewer = EmailReviewer()
    
    # Track results
    results = {
        "total": len(emails),
        "passed": 0,
        "failed": 0,
        "warnings": 0,
        "total_score": 0,
        "reviews": [],
        "common_issues": {},
        "common_violations": {},
        "failed_emails": [],
        "passed_emails": []
    }
    
    # Review each email
    for i, email_doc in enumerate(emails, 1):
        email = {
            "subject": email_doc.get("subject", ""),
            "body": email_doc.get("body", "")
        }
        
        lead = {
            "first_name": email_doc.get("lead_first_name", ""),
            "full_name": email_doc.get("lead_name", ""),
            "company": email_doc.get("lead_company", ""),
            "title": email_doc.get("lead_title", ""),
            "industry": email_doc.get("lead_industry", ""),
            "email": email_doc.get("lead_email", "")
        }
        
        # Run review
        review = reviewer.review_email(email, lead, email_doc.get("email_type", "initial"))
        
        # Track results
        results["total_score"] += review.score
        
        review_data = {
            "lead_name": lead.get("full_name", "Unknown"),
            "lead_email": lead.get("email", "Unknown"),
            "company": lead.get("company", "Unknown"),
            "subject": email.get("subject", ""),
            "status": review.status.value,
            "score": review.score,
            "issues": review.issues,
            "violations": review.rule_violations,
            "suggestions": review.suggestions,
            "ai_feedback": review.ai_feedback
        }
        results["reviews"].append(review_data)
        
        if review.status == ReviewStatus.PASS:
            results["passed"] += 1
            results["passed_emails"].append(review_data)
        elif review.status == ReviewStatus.FAIL:
            results["failed"] += 1
            results["failed_emails"].append(review_data)
        else:
            results["warnings"] += 1
        
        # Track common issues
        for issue in review.issues:
            issue_type = issue.get("type", "unknown")
            results["common_issues"][issue_type] = results["common_issues"].get(issue_type, 0) + 1
        
        for violation in review.rule_violations:
            # Extract key from violation string
            key = violation[:50]
            results["common_violations"][key] = results["common_violations"].get(key, 0) + 1
        
        # Print progress
        status_emoji = "✅" if review.status == ReviewStatus.PASS else "❌" if review.status == ReviewStatus.FAIL else "⚠️"
        print(f"   [{i}/{len(emails)}] {status_emoji} {review.score}/100 - {lead.get('full_name', 'Unknown')} @ {lead.get('company', 'Unknown')}")
    
    # Calculate averages
    results["average_score"] = results["total_score"] / len(emails) if emails else 0
    results["pass_rate"] = (results["passed"] / len(emails) * 100) if emails else 0
    
    # Print summary
    print_summary(results)
    
    # Export detailed results
    export_results(results)
    
    return results


def print_summary(results):
    """Print summary of review results"""
    
    print("\n" + "="*80)
    print("📊 AI REVIEW SUMMARY")
    print("="*80)
    
    print(f"\n📈 OVERALL STATISTICS:")
    print(f"   Total emails reviewed: {results['total']}")
    print(f"   ✅ Passed: {results['passed']} ({results['passed']/results['total']*100:.1f}%)")
    print(f"   ❌ Failed: {results['failed']} ({results['failed']/results['total']*100:.1f}%)")
    print(f"   ⚠️  Warnings: {results['warnings']} ({results['warnings']/results['total']*100:.1f}%)")
    print(f"   📊 Average Score: {results['average_score']:.1f}/100")
    
    # Grade interpretation
    avg = results['average_score']
    if avg >= 85:
        grade = "A - Excellent"
    elif avg >= 75:
        grade = "B - Good"
    elif avg >= 65:
        grade = "C - Needs Improvement"
    elif avg >= 50:
        grade = "D - Poor"
    else:
        grade = "F - Critical Issues"
    print(f"   📝 Grade: {grade}")
    
    # Common issues
    print(f"\n🔍 MOST COMMON ISSUES:")
    sorted_issues = sorted(results["common_issues"].items(), key=lambda x: x[1], reverse=True)
    for issue_type, count in sorted_issues[:10]:
        pct = count / results['total'] * 100
        print(f"   • {issue_type}: {count} emails ({pct:.0f}%)")
    
    # Common violations
    if results["common_violations"]:
        print(f"\n🚫 MOST COMMON RULE VIOLATIONS:")
        sorted_violations = sorted(results["common_violations"].items(), key=lambda x: x[1], reverse=True)
        for violation, count in sorted_violations[:5]:
            pct = count / results['total'] * 100
            print(f"   • {violation}... ({count} emails, {pct:.0f}%)")
    
    # Sample failed emails
    if results["failed_emails"]:
        print(f"\n❌ SAMPLE FAILED EMAILS (showing up to 3):")
        for email in results["failed_emails"][:3]:
            print(f"\n   {'─'*60}")
            print(f"   To: {email['lead_name']} @ {email['company']}")
            print(f"   Subject: {email['subject']}")
            print(f"   Score: {email['score']}/100")
            print(f"   Violations: {len(email['violations'])}")
            for v in email['violations'][:2]:
                print(f"      • {v}")
            if email['ai_feedback']:
                print(f"   AI Feedback: {email['ai_feedback'][:150]}...")
    
    # Recommendations
    print(f"\n💡 TOP RECOMMENDATIONS:")
    recommendations = set()
    for review in results["reviews"]:
        for suggestion in review.get("suggestions", [])[:2]:
            recommendations.add(suggestion)
    
    for i, rec in enumerate(list(recommendations)[:5], 1):
        print(f"   {i}. {rec}")


def export_results(results):
    """Export detailed results to JSON"""
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, "ai_email_review_results.json")
    
    # Prepare export data
    export_data = {
        "review_date": datetime.now().isoformat(),
        "cutoff_date": CUTOFF_DATE.isoformat(),
        "total_emails": results["total"],
        "passed": results["passed"],
        "failed": results["failed"],
        "warnings": results["warnings"],
        "average_score": round(results["average_score"], 2),
        "pass_rate": round(results["pass_rate"], 2),
        "common_issues": dict(sorted(results["common_issues"].items(), key=lambda x: x[1], reverse=True)),
        "common_violations": dict(sorted(results["common_violations"].items(), key=lambda x: x[1], reverse=True)),
        "failed_emails": results["failed_emails"],
        "passed_emails": results["passed_emails"][:10],  # Sample of passed
        "all_reviews": results["reviews"]
    }
    
    with open(output_file, 'w') as f:
        json.dump(export_data, f, indent=2, default=str)
    
    print(f"\n📄 Detailed results exported to: {output_file}")


if __name__ == "__main__":
    run_ai_review()
