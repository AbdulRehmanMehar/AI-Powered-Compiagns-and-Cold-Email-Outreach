"""Test the self-improving email reviewer."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_reviewer import EmailReviewer, format_review_report

def test_reviewer():
    print("✅ Imports work!")

    reviewer = EmailReviewer()
    print("✅ EmailReviewer initialized!")

    # Test with a GOOD email (no AI tells)
    test_email = {
        'subject': 'random thought',
        'body': '''quick q for you. how is TestCorp handling scaling right now?

shipping fast while keeping code clean is brutal. a SaaS company we worked with hit 3.2x faster deploys in 8 weeks.

worth a quick chat?'''
    }

    test_lead = {
        'first_name': 'Mike',
        'company': 'TestCorp',
        'title': 'CTO',
        'industry': 'SaaS'
    }

    print("\n📝 Testing GOOD email...")
    review = reviewer.review_email(test_email, test_lead, save_review=False)
    print(f"   Score: {review.score}")
    print(f"   Status: {review.status.value}")
    print(f"   Rewrite needed: {review.rewrite_required}")
    if review.issues:
        print(f"   Issues ({len(review.issues)}):")
        for issue in review.issues[:5]:
            print(f"      - {issue.get('message', str(issue))[:80]}")
    
    # Test with a BAD email
    bad_email = {
        'subject': 'Partnership Opportunity - Let\'s Connect!',
        'body': '''I hope this email finds you well! I noticed your company is doing great things.

I'm reaching out because I'd love to leverage our innovative solution to streamline your operations.

Would you be interested in scheduling a quick call? Let me know!'''
    }
    
    print("\n📝 Testing BAD email...")
    bad_review = reviewer.review_email(bad_email, test_lead, save_review=True)  # Save this one for learning!
    print(f"   Score: {bad_review.score}")
    print(f"   Status: {bad_review.status.value}")
    print(f"   Rewrite needed: {bad_review.rewrite_required}")
    print(f"   Rule violations: {len(bad_review.rule_violations)}")
    for v in bad_review.rule_violations[:3]:
        print(f"      🚫 {v}")

    # Test stats
    print("\n📊 REVIEW STATS (Last 7 Days):")
    stats = reviewer.get_review_stats(days=7)
    print(f"   Total Reviews: {stats['total']}")
    print(f"   Passed: {stats['passed']} ({stats['pass_rate']}%)")
    print(f"   Failed: {stats['failed']}")
    print(f"   Avg Score: {stats['avg_score']}")

    # Test improvement prompt
    print("\n📚 SELF-IMPROVEMENT PROMPT:")
    improvement = reviewer.get_improvement_prompt(days=14)
    if improvement:
        print(improvement)
    else:
        print("   No failures recorded yet - nothing to learn from!")

    print("\n🎉 All tests passed!")


if __name__ == "__main__":
    test_reviewer()
