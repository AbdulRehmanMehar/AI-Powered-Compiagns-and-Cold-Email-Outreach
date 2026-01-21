"""
Email Analysis Script
Fetches emails from the database and analyzes them against cold email best practices
from the strategy documents (Eric Nowoslawski's 90-page doc, LeadGenJay's masterclass)
"""

from pymongo import MongoClient
from datetime import datetime
from typing import Dict, List, Any
from openai import OpenAI
import config
import json
from bson import ObjectId

# Connect to database
client = MongoClient(config.DATABASE_URL)
db = client.get_database()
emails_collection = db["emails"]
leads_collection = db["leads"]
campaigns_collection = db["campaigns"]


def fetch_all_emails_with_details() -> List[Dict[str, Any]]:
    """Fetch all emails with associated lead and campaign information"""
    
    pipeline = [
        {
            "$lookup": {
                "from": "leads",
                "localField": "lead_id",
                "foreignField": "_id",
                "as": "lead"
            }
        },
        {
            "$lookup": {
                "from": "campaigns",
                "localField": "campaign_id",
                "foreignField": "_id",
                "as": "campaign"
            }
        },
        {
            "$unwind": {"path": "$lead", "preserveNullAndEmptyArrays": True}
        },
        {
            "$unwind": {"path": "$campaign", "preserveNullAndEmptyArrays": True}
        },
        {
            "$project": {
                "_id": 1,
                "subject": 1,
                "body": 1,
                "email_type": 1,
                "followup_number": 1,
                "status": 1,
                "created_at": 1,
                "sent_at": 1,
                "lead_email": "$lead.email",
                "lead_name": "$lead.full_name",
                "lead_company": "$lead.company",
                "lead_title": "$lead.title",
                "campaign_name": "$campaign.name"
            }
        },
        {
            "$sort": {"created_at": -1}
        }
    ]
    
    return list(emails_collection.aggregate(pipeline))


def get_email_statistics() -> Dict[str, Any]:
    """Get overall email statistics"""
    
    stats = {
        "total_emails": emails_collection.count_documents({}),
        "sent_emails": emails_collection.count_documents({"status": "sent"}),
        "pending_emails": emails_collection.count_documents({"status": "pending"}),
        "replied_emails": emails_collection.count_documents({"status": "replied"}),
        "failed_emails": emails_collection.count_documents({"status": "failed"}),
        "initial_emails": emails_collection.count_documents({"email_type": "initial"}),
        "followup_emails": emails_collection.count_documents({"email_type": "followup"}),
    }
    
    # Calculate reply rate if there are sent emails
    if stats["sent_emails"] > 0:
        stats["reply_rate"] = round((stats["replied_emails"] / stats["sent_emails"]) * 100, 2)
    else:
        stats["reply_rate"] = 0
    
    return stats


# Cold email best practices based on strategy documents
COLD_EMAIL_BEST_PRACTICES = """
Based on Eric Nowoslawski's 90-page document and LeadGenJay's masterclass:

SUBJECT LINE RULES:
1. 2-4 words MAX
2. Must look like it's from a colleague or friend
3. NO: "Quick question", "Partnership", "Intro", "[Company] + [Company]", corporate language
4. YES: "{first_name}?", "thought about this", "re: {company}", "saw something"

FIRST LINE (Preview Text) RULES:
1. Must create CURIOSITY, not pitch
2. NO: "I noticed your company...", "I'm reaching out because...", "My name is..."
3. YES: "saw something interesting on {company}'s site", "random question", "this might be off base but"

BODY RULES:
1. Under 75-100 words total (75 is better)
2. ONE pain point only - not a list
3. Include specific case study with REAL numbers (3.72x not 4x)
4. Sound like a human, not a template
5. 6th grade reading level, no jargon
6. No corporate buzzwords: leverage, synergy, streamline, incentivize

CTA RULES:
1. Super soft, low friction
2. NO: "Let's schedule a call", "Are you free Tuesday?", "Can we hop on a call?"
3. YES: "worth a quick chat?", "make sense to connect?", "open to hearing more?"

THINGS TO AVOID:
1. "I hope this finds you well"
2. "reaching out" or "touching base"
3. Listing multiple services
4. Links (especially in first email)
5. Images
6. Unsubscribe links (unless required)
7. Open tracking pixels
8. More than 4-5 sentences
9. Sounding salesy or desperate
10. Guarantees or over-promising

FOLLOW-UP RULES:
1. Max 2-3 emails in sequence (short sequences = less spam)
2. Email 2: Same thread, add GENUINE value (not "just following up")
3. Email 3: NEW thread, different subject, different angle
4. Never say "just following up", "circling back", "bumping this"
5. Never guilt trip

DELIVERABILITY:
1. 30 emails per day per mailbox max (some go up to 50)
2. 10-minute delay between emails
3. Warm domains for 3-4 weeks before sending
4. Domain age matters - older is better
5. 2-5 inboxes per domain
"""


def analyze_email_alignment(email: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze a single email against best practices"""
    
    subject = email.get("subject", "")
    body = email.get("body", "")
    email_type = email.get("email_type", "initial")
    
    issues = []
    positives = []
    score = 100  # Start with perfect score, deduct for issues
    
    # SUBJECT LINE ANALYSIS
    subject_words = len(subject.split())
    if subject_words > 4:
        issues.append(f"Subject too long ({subject_words} words) - should be 2-4 words")
        score -= 10
    elif subject_words <= 4:
        positives.append(f"Good subject length ({subject_words} words)")
    
    # Check for bad subject patterns
    bad_subject_patterns = [
        "quick question", "partnership", "intro", "introduction", 
        "opportunity", "touching base", "following up", "collaboration"
    ]
    for pattern in bad_subject_patterns:
        if pattern.lower() in subject.lower():
            issues.append(f"Subject contains bad pattern: '{pattern}'")
            score -= 15
    
    # FIRST LINE ANALYSIS
    first_line = body.split('\n')[0] if body else ""
    bad_first_line_patterns = [
        "i noticed your company", "i'm reaching out", "my name is",
        "i hope this finds you", "i wanted to", "i hope this email"
    ]
    for pattern in bad_first_line_patterns:
        if pattern.lower() in first_line.lower():
            issues.append(f"First line contains pitch pattern: '{pattern}'")
            score -= 15
    
    # BODY LENGTH ANALYSIS
    word_count = len(body.split())
    if word_count > 100:
        issues.append(f"Email too long ({word_count} words) - should be under 100 words, ideally 75")
        score -= 20
    elif word_count <= 75:
        positives.append(f"Good email length ({word_count} words)")
    elif word_count <= 100:
        positives.append(f"Acceptable email length ({word_count} words)")
    
    # Check for corporate buzzwords
    buzzwords = [
        "leverage", "synergy", "streamline", "incentivize", "optimize",
        "revolutionary", "cutting-edge", "world-class", "best-in-class",
        "scalable solution", "holistic approach", "paradigm"
    ]
    found_buzzwords = [bw for bw in buzzwords if bw.lower() in body.lower()]
    if found_buzzwords:
        issues.append(f"Contains corporate buzzwords: {', '.join(found_buzzwords)}")
        score -= 5 * len(found_buzzwords)
    
    # Check for bad CTA patterns
    bad_cta_patterns = [
        "schedule a call", "hop on a call", "are you free",
        "let me know when", "book a meeting", "calendar link"
    ]
    for pattern in bad_cta_patterns:
        if pattern.lower() in body.lower():
            issues.append(f"CTA too aggressive: '{pattern}'")
            score -= 10
    
    # Check for good CTA patterns
    good_cta_patterns = [
        "worth a chat", "make sense", "open to", "interested in hearing",
        "would it help", "curious if", "worth exploring"
    ]
    has_soft_cta = any(pattern.lower() in body.lower() for pattern in good_cta_patterns)
    if has_soft_cta:
        positives.append("Uses soft, low-friction CTA")
    
    # Check for bad phrases
    bad_phrases = [
        "just following up", "circling back", "touching base",
        "i know you're busy", "sorry to bother", "reaching out"
    ]
    for phrase in bad_phrases:
        if phrase.lower() in body.lower():
            issues.append(f"Contains discouraged phrase: '{phrase}'")
            score -= 10
    
    # Check for personalization indicators
    if "{" in body or "{{" in body:
        positives.append("Contains personalization variables")
    
    # Ensure score doesn't go below 0
    score = max(0, score)
    
    return {
        "email_id": str(email.get("_id", "")),
        "subject": subject,
        "lead_name": email.get("lead_name", "Unknown"),
        "lead_company": email.get("lead_company", "Unknown"),
        "email_type": email_type,
        "word_count": word_count,
        "score": score,
        "issues": issues,
        "positives": positives,
        "status": email.get("status", "unknown")
    }


def analyze_all_emails() -> Dict[str, Any]:
    """Analyze all emails in the database"""
    
    emails = fetch_all_emails_with_details()
    stats = get_email_statistics()
    
    if not emails:
        return {
            "summary": "No emails found in database",
            "stats": stats,
            "analyzed_emails": []
        }
    
    analyzed = [analyze_email_alignment(email) for email in emails]
    
    # Calculate overall alignment score
    if analyzed:
        avg_score = sum(e["score"] for e in analyzed) / len(analyzed)
    else:
        avg_score = 0
    
    # Find most common issues
    all_issues = []
    for email in analyzed:
        all_issues.extend(email["issues"])
    
    issue_counts = {}
    for issue in all_issues:
        # Simplify the issue for grouping
        simple_issue = issue.split(":")[0] if ":" in issue else issue
        issue_counts[simple_issue] = issue_counts.get(simple_issue, 0) + 1
    
    # Sort by frequency
    sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
    
    return {
        "summary": {
            "total_emails_analyzed": len(analyzed),
            "average_alignment_score": round(avg_score, 1),
            "emails_scoring_above_80": len([e for e in analyzed if e["score"] >= 80]),
            "emails_scoring_below_50": len([e for e in analyzed if e["score"] < 50]),
        },
        "stats": stats,
        "common_issues": sorted_issues[:10],  # Top 10 issues
        "analyzed_emails": analyzed,
        "best_practices_reference": COLD_EMAIL_BEST_PRACTICES
    }


def print_analysis_report(analysis: Dict[str, Any]):
    """Print a formatted analysis report"""
    
    print("\n" + "="*80)
    print("📧 COLD EMAIL ALIGNMENT ANALYSIS REPORT")
    print("="*80)
    
    # Database Stats
    stats = analysis.get("stats", {})
    print("\n📊 DATABASE STATISTICS:")
    print(f"  • Total Emails: {stats.get('total_emails', 0)}")
    print(f"  • Sent: {stats.get('sent_emails', 0)}")
    print(f"  • Pending: {stats.get('pending_emails', 0)}")
    print(f"  • Replied: {stats.get('replied_emails', 0)}")
    print(f"  • Failed: {stats.get('failed_emails', 0)}")
    print(f"  • Reply Rate: {stats.get('reply_rate', 0)}%")
    
    # Summary
    summary = analysis.get("summary", {})
    if isinstance(summary, str):
        print(f"\n⚠️  {summary}")
        return
    
    print("\n📈 ALIGNMENT ANALYSIS SUMMARY:")
    print(f"  • Total Emails Analyzed: {summary.get('total_emails_analyzed', 0)}")
    print(f"  • Average Alignment Score: {summary.get('average_alignment_score', 0)}/100")
    print(f"  • Emails Scoring Above 80: {summary.get('emails_scoring_above_80', 0)}")
    print(f"  • Emails Scoring Below 50: {summary.get('emails_scoring_below_50', 0)}")
    
    # Common Issues
    common_issues = analysis.get("common_issues", [])
    if common_issues:
        print("\n⚠️  MOST COMMON ISSUES:")
        for issue, count in common_issues:
            print(f"  • {issue}: {count} occurrences")
    
    # Sample of analyzed emails
    analyzed_emails = analysis.get("analyzed_emails", [])
    if analyzed_emails:
        print("\n📝 SAMPLE EMAIL ANALYSIS (First 5):")
        for i, email in enumerate(analyzed_emails[:5], 1):
            print(f"\n  Email {i}:")
            print(f"    Subject: {email.get('subject', 'N/A')[:50]}...")
            print(f"    To: {email.get('lead_name', 'N/A')} at {email.get('lead_company', 'N/A')}")
            print(f"    Type: {email.get('email_type', 'N/A')}")
            print(f"    Word Count: {email.get('word_count', 0)}")
            print(f"    Score: {email.get('score', 0)}/100")
            
            if email.get('positives'):
                print(f"    ✅ Positives: {', '.join(email['positives'][:3])}")
            if email.get('issues'):
                print(f"    ❌ Issues: {', '.join(email['issues'][:3])}")
    
    print("\n" + "="*80)
    print("📚 Reference: Analysis based on Eric Nowoslawski's 90-page cold email guide")
    print("   and LeadGenJay's $15M cold email masterclass strategies")
    print("="*80 + "\n")


def export_analysis_to_json(analysis: Dict[str, Any], filename: str = "email_analysis_report.json"):
    """Export the full analysis to a JSON file"""
    
    # Convert ObjectIds to strings for JSON serialization
    def convert_objectid(obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: convert_objectid(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_objectid(item) for item in obj]
        return obj
    
    serializable_analysis = convert_objectid(analysis)
    
    with open(filename, 'w') as f:
        json.dump(serializable_analysis, f, indent=2)
    
    print(f"📄 Full analysis exported to: {filename}")


if __name__ == "__main__":
    print("🔍 Connecting to database and analyzing emails...")
    
    try:
        # Run the analysis
        analysis = analyze_all_emails()
        
        # Print the report
        print_analysis_report(analysis)
        
        # Export to JSON
        export_analysis_to_json(analysis)
        
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()
