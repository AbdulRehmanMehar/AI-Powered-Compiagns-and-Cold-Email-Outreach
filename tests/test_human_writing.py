"""Test email generation for AI tells."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_generator import EmailGenerator, humanize_email

def test_humanize():
    """Test the humanize function."""
    print("Testing humanize_email function:")
    print("=" * 60)
    
    test_texts = [
        'random question— how is your team handling scaling?',
        'Furthermore, we can help you leverage AI.',
        'This is a pivotal moment—delve into the possibilities.',
        'Interestingly, a SaaS company utilized our robust solution.',
        "It's worth noting that we foster innovation.",
    ]
    
    for text in test_texts:
        result = humanize_email(text)
        print(f"BEFORE: {text}")
        print(f"AFTER:  {result}")
        print("-" * 60)

def test_email_generation():
    """Test actual email generation."""
    print("\n\nTesting email generation (checking for AI tells):")
    print("=" * 70)
    
    gen = EmailGenerator()

    test_leads = [
        {'first_name': 'Sarah', 'company': 'FinanceHub', 'title': 'CTO', 'industry': 'FinTech', 'email': 'sarah@finhub.com'},
        {'first_name': 'Mike', 'company': 'HealthFirst', 'title': 'VP Engineering', 'industry': 'HealthTech', 'email': 'mike@healthfirst.com'},
    ]

    context = {
        'product_service': 'AI development services',
        'value_proposition': 'Ship faster with senior AI engineers'
    }

    ai_words = ['delve', 'leverage', 'utilize', 'robust', 'seamless', 'pivotal', 
                'furthermore', 'moreover', 'additionally', 'importantly']

    for lead in test_leads:
        email = gen.generate_initial_email(lead, context)
        print(f"\n📧 TO: {lead['first_name']} at {lead['company']}")
        print(f"Subject: {email['subject']}")
        print(f"Body:\n{email['body']}")
        
        # Check for AI tells
        full_text = email['subject'] + ' ' + email['body']
        has_em_dash = '—' in full_text or '–' in full_text
        found_ai_words = [w for w in ai_words if w in full_text.lower()]
        
        print(f"\n✓ Em dash check: {'❌ FOUND' if has_em_dash else '✅ Clean'}")
        print(f"✓ AI words check: {'❌ FOUND: ' + ', '.join(found_ai_words) if found_ai_words else '✅ Clean'}")
        print("-" * 70)


if __name__ == "__main__":
    test_humanize()
    test_email_generation()
    print("\n🎉 Tests completed!")
