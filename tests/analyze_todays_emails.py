#!/usr/bin/env python3
"""
Fetch and analyze all emails written today.
Logs full email bodies, then performs quality analysis:
  - Paragraph spacing (line breaks)
  - Curiosity / engagement hooks
  - Length, tone, CTA quality
  - Formatting issues
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from database import emails_collection, leads_collection
import json

def fetch_todays_emails():
    """Fetch all emails created today (UTC)."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    emails = list(emails_collection.find(
        {"created_at": {"$gte": today_start}},
        {"subject": 1, "body": 1, "email_type": 1, "followup_number": 1,
         "to_email": 1, "from_email": 1, "lead_id": 1, "campaign_id": 1,
         "status": 1, "created_at": 1}
    ).sort("created_at", 1))
    
    return emails


def analyze_email(email, index):
    """Analyze a single email for quality issues."""
    body = email.get("body", "")
    subject = email.get("subject", "")
    email_type = email.get("email_type", "unknown")
    followup_num = email.get("followup_number", 0)
    
    issues = []
    warnings = []
    
    # ── Paragraph spacing ──
    paragraphs = body.split("\n\n")
    single_lines = body.split("\n")
    
    if len(paragraphs) <= 1 and len(single_lines) > 2:
        issues.append("NO_PARAGRAPH_BREAKS: Body has multiple lines but NO blank lines between paragraphs")
    elif len(paragraphs) <= 2 and len(single_lines) > 4:
        warnings.append(f"FEW_PARAGRAPH_BREAKS: Only {len(paragraphs)} paragraphs but {len(single_lines)} lines")
    
    # Check for consecutive lines without blank line separation
    consecutive_text_lines = 0
    max_consecutive = 0
    for line in single_lines:
        if line.strip():
            consecutive_text_lines += 1
            max_consecutive = max(max_consecutive, consecutive_text_lines)
        else:
            consecutive_text_lines = 0
    
    if max_consecutive > 4:
        issues.append(f"WALL_OF_TEXT: {max_consecutive} consecutive lines without a blank line")
    
    # ── Curiosity / engagement ──
    curiosity_markers = [
        "?",  # questions
        "curious", "wonder", "imagine", "what if",
        "noticed", "caught my eye", "saw that", "came across",
        "interesting", "intriguing",
        "thought of you", "reminded me",
        "quick question", "honest question",
    ]
    
    body_lower = body.lower()
    question_count = body.count("?")
    curiosity_hits = [m for m in curiosity_markers if m in body_lower]
    
    if question_count == 0:
        issues.append("NO_QUESTIONS: Zero question marks — no curiosity or engagement hooks")
    elif question_count == 1 and email_type == "initial":
        warnings.append("LOW_QUESTIONS: Only 1 question in initial email")
    
    if len(curiosity_hits) <= 1:
        warnings.append(f"LOW_CURIOSITY: Only {len(curiosity_hits)} curiosity markers found")
    
    # ── Length analysis ──
    word_count = len(body.split())
    if word_count > 150:
        issues.append(f"TOO_LONG: {word_count} words (should be under 120 for cold email)")
    elif word_count > 120:
        warnings.append(f"SLIGHTLY_LONG: {word_count} words")
    elif word_count < 30:
        warnings.append(f"TOO_SHORT: {word_count} words")
    
    # ── CTA check ──
    cta_markers = ["calendar", "call", "chat", "meet", "schedule", "time", "open to",
                   "worth", "interested", "link", "15 min", "quick call", "hop on"]
    cta_hits = [m for m in cta_markers if m in body_lower]
    if not cta_hits:
        issues.append("NO_CTA: No clear call-to-action detected")
    
    # ── Spam words ──
    spam_words = ["guaranteed", "free", "act now", "limited time", "exclusive offer",
                  "click here", "buy now", "discount", "unbeatable", "amazing deal"]
    spam_hits = [w for w in spam_words if w in body_lower]
    if spam_hits:
        issues.append(f"SPAM_WORDS: Found spammy language: {spam_hits}")
    
    # ── Generic / templated feel ──
    generic_phrases = [
        "i hope this email finds you well",
        "i hope you're doing well",
        "i wanted to reach out",
        "i'm reaching out because",
        "i came across your company",
        "i noticed your company",
    ]
    generic_hits = [p for p in generic_phrases if p in body_lower]
    if generic_hits:
        warnings.append(f"GENERIC_OPENER: Uses overused phrases: {generic_hits}")
    
    # ── Subject line ──
    subject_words = len(subject.split())
    if subject_words > 6:
        warnings.append(f"LONG_SUBJECT: '{subject}' ({subject_words} words, aim for 2-4)")
    if subject.lower() == subject and not any(c.isupper() for c in subject):
        pass  # lowercase subjects are fine for cold email
    if "!" in subject:
        warnings.append(f"EXCLAMATION_SUBJECT: Subject has '!' — may trigger spam filters")
    
    # ── Signature ──
    if not body.strip().endswith(("abdul", "Abdul", "abdulrehman", "Abdulrehman", "AR")):
        last_line = body.strip().split("\n")[-1].strip().lower()
        if not any(name in last_line for name in ["abdul", "abdulrehman", "ali", "usama", "bilal"]):
            warnings.append("NO_SIGNATURE: Email doesn't end with a name")
    
    return {
        "issues": issues,
        "warnings": warnings,
        "stats": {
            "paragraphs": len(paragraphs),
            "lines": len(single_lines),
            "max_consecutive_lines": max_consecutive,
            "word_count": word_count,
            "question_count": question_count,
            "curiosity_markers": curiosity_hits,
            "cta_markers": cta_hits,
        }
    }


def main():
    print("=" * 70)
    print("  EMAIL ANALYSIS — Today's Emails")
    print(f"  Date: {datetime.utcnow().strftime('%Y-%m-%d')} (UTC)")
    print("=" * 70)
    
    emails = fetch_todays_emails()
    
    if not emails:
        # Try yesterday if today is empty (timezone difference)
        yesterday_start = (datetime.utcnow() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        emails = list(emails_collection.find(
            {"created_at": {"$gte": yesterday_start}},
            {"subject": 1, "body": 1, "email_type": 1, "followup_number": 1,
             "to_email": 1, "from_email": 1, "lead_id": 1, "campaign_id": 1,
             "status": 1, "created_at": 1}
        ).sort("created_at", 1))
        if emails:
            print(f"\n  (No emails today, showing yesterday's {len(emails)} emails)\n")
        else:
            print("\n  No emails found for today or yesterday.\n")
            return
    
    print(f"\n  Total emails found: {len(emails)}\n")
    
    # Count by type
    type_counts = {}
    for e in emails:
        t = e.get("email_type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"  By type: {type_counts}\n")
    
    # ── Analyze each email ──
    all_issues = []
    all_warnings = []
    
    for i, email in enumerate(emails):
        analysis = analyze_email(email, i)
        body = email.get("body", "")
        subject = email.get("subject", "")
        email_type = email.get("email_type", "unknown")
        followup_num = email.get("followup_number", 0)
        to_email = email.get("to_email", "?")
        from_email = email.get("from_email", "?")
        created = email.get("created_at", "?")
        
        all_issues.extend(analysis["issues"])
        all_warnings.extend(analysis["warnings"])
        
        type_label = email_type
        if followup_num > 0:
            type_label = f"followup #{followup_num}"
        
        print("─" * 70)
        print(f"  EMAIL #{i+1} | {type_label} | {created}")
        print(f"  To: {to_email} | From: {from_email}")
        print(f"  Subject: {subject}")
        print(f"  Stats: {analysis['stats']['word_count']} words, "
              f"{analysis['stats']['paragraphs']} paragraphs, "
              f"{analysis['stats']['question_count']} questions")
        print("─" * 70)
        
        # Print body with visible formatting
        print()
        for line_num, line in enumerate(body.split("\n"), 1):
            if line.strip() == "":
                print(f"  {line_num:2d} | [BLANK LINE]")
            else:
                print(f"  {line_num:2d} | {line}")
        print()
        
        # Issues
        if analysis["issues"]:
            for issue in analysis["issues"]:
                print(f"  🔴 {issue}")
        if analysis["warnings"]:
            for warning in analysis["warnings"]:
                print(f"  🟡 {warning}")
        if not analysis["issues"] and not analysis["warnings"]:
            print(f"  🟢 No issues found")
        print()
    
    # ── Summary ──
    print("=" * 70)
    print("  AGGREGATE ANALYSIS")
    print("=" * 70)
    
    # Count issue frequency
    issue_freq = {}
    for issue in all_issues:
        key = issue.split(":")[0]
        issue_freq[key] = issue_freq.get(key, 0) + 1
    
    warning_freq = {}
    for warning in all_warnings:
        key = warning.split(":")[0]
        warning_freq[key] = warning_freq.get(key, 0) + 1
    
    print(f"\n  Total emails: {len(emails)}")
    print(f"  Total issues: {len(all_issues)}")
    print(f"  Total warnings: {len(all_warnings)}")
    
    if issue_freq:
        print(f"\n  🔴 Issues by frequency:")
        for issue, count in sorted(issue_freq.items(), key=lambda x: -x[1]):
            pct = count / len(emails) * 100
            print(f"     {issue}: {count}/{len(emails)} ({pct:.0f}%)")
    
    if warning_freq:
        print(f"\n  🟡 Warnings by frequency:")
        for warning, count in sorted(warning_freq.items(), key=lambda x: -x[1]):
            pct = count / len(emails) * 100
            print(f"     {warning}: {count}/{len(emails)} ({pct:.0f}%)")
    
    # ── Paragraph break analysis ──
    print(f"\n  📊 Paragraph break analysis:")
    no_breaks = sum(1 for e in emails if len(e.get("body", "").split("\n\n")) <= 1)
    few_breaks = sum(1 for e in emails if 1 < len(e.get("body", "").split("\n\n")) <= 2)
    good_breaks = sum(1 for e in emails if len(e.get("body", "").split("\n\n")) > 2)
    print(f"     No paragraph breaks: {no_breaks}/{len(emails)}")
    print(f"     1-2 paragraph breaks: {few_breaks}/{len(emails)}")
    print(f"     Good spacing (3+): {good_breaks}/{len(emails)}")
    
    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
