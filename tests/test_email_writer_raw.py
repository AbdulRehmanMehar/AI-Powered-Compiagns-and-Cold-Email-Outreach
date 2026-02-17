#!/usr/bin/env python3
"""
Test the email writer WITHOUT any postprocessing.
Generates emails for real leads from DB and shows raw AI output.

Usage:
    python3 tests/test_email_writer_raw.py              # Generate 3 test emails
    python3 tests/test_email_writer_raw.py --count 5    # Generate 5 test emails
    python3 tests/test_email_writer_raw.py --lead-id X  # Generate for specific lead
"""

import sys
import os
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from email_generator import EmailGenerator


def get_test_leads(count=3, lead_id=None):
    """Get real leads from DB for testing."""
    if lead_id:
        from bson import ObjectId
        lead = db.leads.find_one({'_id': ObjectId(lead_id)})
        return [lead] if lead else []
    
    # Get leads that haven't been emailed yet, with valid companies
    pipeline = [
        {'$match': {
            'company': {'$exists': True, '$ne': None, '$ne': ''},
            'first_name': {'$exists': True, '$ne': None, '$ne': ''},
            'email': {'$exists': True, '$ne': None, '$ne': ''},
        }},
        {'$sample': {'size': count}}
    ]
    return list(db.leads.aggregate(pipeline))


def get_campaign_context():
    """Get a campaign context from DB."""
    campaign = db.campaigns.find_one({})
    if campaign:
        return {
            'name': campaign.get('name', 'default'),
            'description': campaign.get('description', ''),
            'target_audience': campaign.get('target_audience', ''),
            'value_proposition': campaign.get('value_proposition', ''),
            'cta_options': campaign.get('cta_options', []),
        }
    # Fallback
    return {
        'name': 'test_campaign',
        'description': 'Test campaign',
        'target_audience': 'Tech startup founders and CTOs',
        'value_proposition': 'Expert engineering teams',
    }


def check_formatting(body):
    """Analyze formatting quality of generated email."""
    issues = []
    good = []
    
    if not body:
        return ['EMPTY BODY'], []
    
    # Check paragraph breaks
    if '\n\n' in body:
        break_count = body.count('\n\n')
        good.append(f"Has {break_count} paragraph break(s)")
    else:
        issues.append("NO paragraph breaks - wall of text")
    
    # Check line count
    lines = [l for l in body.split('\n') if l.strip()]
    if len(lines) >= 3:
        good.append(f"{len(lines)} content lines")
    else:
        issues.append(f"Only {len(lines)} line(s) - may look flat")
    
    # Check word count
    words = len(body.split())
    if 25 <= words <= 75:
        good.append(f"{words} words (ideal range)")
    elif words < 25:
        issues.append(f"Too short: {words} words")
    else:
        issues.append(f"Too long: {words} words (target <75)")
    
    # Check for em dashes
    if '—' in body:
        issues.append("Contains em dash (—) - AI tell")
    else:
        good.append("No em dashes")
    
    # Check for AI-y words
    ai_words = ['leverage', 'utilize', 'delve', 'robust', 'seamless', 
                 'pivotal', 'harness', 'foster', 'bolster', 'myriad',
                 'furthermore', 'moreover', 'innovative', 'cutting-edge']
    found_ai = [w for w in ai_words if w in body.lower()]
    if found_ai:
        issues.append(f"AI words found: {', '.join(found_ai)}")
    else:
        good.append("No AI-y words")
    
    # Check greeting format
    first_line = body.split('\n')[0].lower().strip()
    if first_line.startswith('hey ') or first_line.startswith('hi '):
        good.append("Natural greeting")
    elif any(first_line.startswith(p) for p in ['i noticed', 'i saw', 'i hope', 'i\'m reaching']):
        issues.append(f"Robotic opener: '{first_line[:40]}'")
    
    # Check for signature
    last_line = body.split('\n')[-1].strip().lower()
    if last_line in ['abdul', 'ali', 'usama', 'bilal', 'abdulrehman']:
        good.append(f"Has signature: {last_line}")
    
    # Check CTA ends with ?
    cta_keywords = ['worth', 'thoughts', 'make sense', 'curious', 'interested', 
                     'want me to', 'open to', 'sound', 'crazy or']
    for line in reversed(body.split('\n')):
        line_stripped = line.strip().lower()
        if any(kw in line_stripped for kw in cta_keywords):
            if line.strip().endswith('?'):
                good.append("CTA ends with ?")
            else:
                issues.append("CTA missing question mark")
            break
    
    return issues, good


def main():
    parser = argparse.ArgumentParser(description='Test email writer without postprocessing')
    parser.add_argument('--count', type=int, default=3, help='Number of test emails to generate')
    parser.add_argument('--lead-id', type=str, help='Specific lead ID to test')
    args = parser.parse_args()
    
    print("=" * 70)
    print("EMAIL WRITER TEST (NO POSTPROCESSING)")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Get test leads
    leads = get_test_leads(count=args.count, lead_id=args.lead_id)
    if not leads:
        print("\nNo leads found! Check database.")
        return
    
    print(f"\nTesting with {len(leads)} lead(s)...")
    
    # Get campaign context
    campaign_ctx = get_campaign_context()
    print(f"Campaign: {campaign_ctx.get('name', 'unknown')}")
    
    # Initialize generator
    print("\nInitializing email generator...")
    generator = EmailGenerator()
    
    results = {
        'total': 0,
        'success': 0,
        'failed': 0,
        'formatting_good': 0,
        'formatting_issues': 0,
    }
    
    all_issues_summary = []
    
    for i, lead in enumerate(leads, 1):
        print(f"\n{'=' * 70}")
        print(f"EMAIL {i}/{len(leads)}")
        print(f"{'=' * 70}")
        print(f"  Lead: {lead.get('first_name', 'Unknown')} {lead.get('last_name', '')}")
        print(f"  Company: {lead.get('company', 'Unknown')}")
        print(f"  Title: {lead.get('title', 'Unknown')}")
        print(f"  Industry: {lead.get('industry', 'Unknown')}")
        print(f"  Email: {lead.get('email', 'Unknown')}")
        
        results['total'] += 1
        
        try:
            # Generate email - this now has ZERO postprocessing
            email = generator.generate_initial_email(
                lead=lead,
                campaign_context=campaign_ctx,
                include_review_learnings=False  # Skip review DB lookup for speed
            )
            
            if not email:
                print(f"\n  RESULT: Skipped (None returned)")
                results['failed'] += 1
                continue
            
            subject = email.get('subject', '')
            body = email.get('body', '')
            
            results['success'] += 1
            
            # Display the raw email
            print(f"\n  SUBJECT: \"{subject}\"")
            print(f"\n  BODY (raw - no postprocessing):")
            print(f"  {'─' * 50}")
            for line in body.split('\n'):
                print(f"  | {line}")
            print(f"  {'─' * 50}")
            
            # Analyze formatting
            issues, good = check_formatting(body)
            
            print(f"\n  FORMATTING CHECK:")
            for g in good:
                print(f"    ✅ {g}")
            for issue in issues:
                print(f"    ❌ {issue}")
            
            if issues:
                results['formatting_issues'] += 1
                all_issues_summary.append({
                    'lead': f"{lead.get('first_name', '')} @ {lead.get('company', '')}",
                    'issues': issues
                })
            else:
                results['formatting_good'] += 1
                
        except Exception as e:
            print(f"\n  ERROR: {e}")
            results['failed'] += 1
    
    # Final summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total attempts:      {results['total']}")
    print(f"  Successful:          {results['success']}")
    print(f"  Failed:              {results['failed']}")
    print(f"  Formatting perfect:  {results['formatting_good']}")
    print(f"  Formatting issues:   {results['formatting_issues']}")
    
    if all_issues_summary:
        print(f"\n  ISSUES FOUND:")
        for item in all_issues_summary:
            print(f"    {item['lead']}:")
            for issue in item['issues']:
                print(f"      - {issue}")
    
    if results['formatting_good'] == results['success'] and results['success'] > 0:
        print(f"\n  ✅ ALL EMAILS PROPERLY FORMATTED - AI prompts working correctly!")
    elif results['success'] > 0:
        pct = results['formatting_issues'] / results['success'] * 100
        print(f"\n  ⚠️  {pct:.0f}% of emails have formatting issues")
    
    print()


if __name__ == "__main__":
    main()
