"""
Test the full email pipeline: Generate → Review → Rewrite if needed

This simulates what happens in production when an email goes through
the self-improving quality gate.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_generator import EmailGenerator
from email_reviewer import EmailReviewer, ReviewStatus, format_review_report


def test_full_pipeline(lead: dict, campaign_context: dict, max_rewrites: int = 2):
    """
    Test the full email pipeline for a single lead.
    
    1. Generate initial email
    2. Review it
    3. If fails, rewrite with feedback
    4. Repeat until pass or max_rewrites reached
    """
    generator = EmailGenerator()
    reviewer = EmailReviewer()
    
    print(f"\n{'='*70}")
    print(f"📧 TESTING PIPELINE FOR: {lead['first_name']} at {lead['company']}")
    print(f"   Industry: {lead.get('industry', 'Unknown')}")
    print(f"   Title: {lead.get('title', 'Unknown')}")
    print(f"{'='*70}")
    
    # Step 1: Generate initial email
    print("\n📝 STEP 1: Generating initial email...")
    email = generator.generate_initial_email(lead, campaign_context)
    
    attempt = 0
    max_attempts = max_rewrites + 1
    
    while attempt < max_attempts:
        attempt += 1
        print(f"\n{'─'*70}")
        print(f"🔍 ATTEMPT {attempt}/{max_attempts}: Reviewing email...")
        print(f"{'─'*70}")
        
        print(f"\n   Subject: {email['subject']}")
        print(f"   Body:\n   {email['body'].replace(chr(10), chr(10) + '   ')}")
        
        # Step 2: Review the email
        review = reviewer.review_email(
            email={'subject': email['subject'], 'body': email['body']},
            lead=lead,
            save_review=True  # Store for learning
        )
        
        print(f"\n   📊 Review Results:")
        print(f"      Score: {review.score}/100")
        print(f"      Status: {review.status.value}")
        print(f"      Rewrite needed: {review.rewrite_required}")
        
        if review.rule_violations:
            print(f"\n   🚫 Rule Violations ({len(review.rule_violations)}):")
            for v in review.rule_violations[:3]:
                print(f"      - {v[:70]}...")
        
        if review.issues:
            print(f"\n   ⚠️ Issues ({len(review.issues)}):")
            for issue in review.issues[:3]:
                msg = issue.get('message', str(issue))[:70]
                print(f"      - {msg}...")
        
        # Check if passed
        if not review.rewrite_required:
            print(f"\n   ✅ EMAIL PASSED REVIEW!")
            return {
                'status': 'passed',
                'attempts': attempt,
                'final_email': email,
                'final_score': review.score
            }
        
        # Step 3: Rewrite if we have attempts left
        if attempt < max_attempts:
            print(f"\n   🔄 Rewriting email with feedback...")
            email = reviewer._rewrite_email(
                email={'subject': email['subject'], 'body': email['body']},
                lead=lead,
                review=review,
                campaign_context=campaign_context
            )
        else:
            print(f"\n   ❌ MAX REWRITES REACHED - Marking for manual review")
    
    return {
        'status': 'manual_review',
        'attempts': attempt,
        'final_email': email,
        'final_score': review.score
    }


def run_tests():
    """Run the full pipeline test with multiple leads."""
    
    # Test leads from different industries
    test_leads = [
        {
            'first_name': 'Sarah',
            'company': 'FinanceHub',
            'title': 'CTO',
            'industry': 'FinTech',
            'email': 'sarah@financehub.com'
        },
        {
            'first_name': 'Mike',
            'company': 'HealthFirst',
            'title': 'VP Engineering',
            'industry': 'HealthTech',
            'email': 'mike@healthfirst.com'
        },
        {
            'first_name': 'Lisa',
            'company': 'CloudScale',
            'title': 'Engineering Manager',
            'industry': 'SaaS',
            'email': 'lisa@cloudscale.io'
        },
    ]
    
    campaign_context = {
        'product_service': 'AI-powered development services',
        'value_proposition': 'Ship 3x faster with senior engineers'
    }
    
    results = []
    
    for lead in test_leads:
        result = test_full_pipeline(lead, campaign_context, max_rewrites=2)
        results.append({
            'lead': f"{lead['first_name']} @ {lead['company']}",
            **result
        })
    
    # Summary
    print("\n")
    print("=" * 70)
    print("📊 PIPELINE TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for r in results if r['status'] == 'passed')
    manual = sum(1 for r in results if r['status'] == 'manual_review')
    
    print(f"\n   Total emails tested: {len(results)}")
    print(f"   ✅ Passed: {passed}")
    print(f"   ❌ Manual review needed: {manual}")
    print(f"   Pass rate: {passed/len(results)*100:.1f}%")
    
    print("\n   Individual Results:")
    for r in results:
        emoji = "✅" if r['status'] == 'passed' else "❌"
        print(f"   {emoji} {r['lead']}: {r['status']} (score: {r['final_score']}, attempts: {r['attempts']})")
    
    # Show final emails
    print("\n" + "=" * 70)
    print("📧 FINAL EMAILS")
    print("=" * 70)
    
    for r in results:
        print(f"\n{'─'*70}")
        print(f"TO: {r['lead']}")
        print(f"Status: {r['status']} | Score: {r['final_score']} | Attempts: {r['attempts']}")
        print(f"{'─'*70}")
        print(f"Subject: {r['final_email']['subject']}")
        print(f"\n{r['final_email']['body']}")
    
    # Get reviewer stats
    reviewer = EmailReviewer()
    stats = reviewer.get_review_stats(days=1)
    
    print("\n" + "=" * 70)
    print("📈 REVIEW STATS (Last 24 Hours)")
    print("=" * 70)
    print(f"   Total reviews: {stats['total']}")
    print(f"   Passed: {stats['passed']}")
    print(f"   Failed: {stats['failed']}")
    print(f"   Pass rate: {stats['pass_rate']}%")
    print(f"   Avg score: {stats['avg_score']}")
    
    return results


if __name__ == "__main__":
    print("🚀 Starting Full Pipeline Test")
    print("   Generate → Review → Rewrite → Review → ...")
    results = run_tests()
    print("\n🎉 Test completed!")
