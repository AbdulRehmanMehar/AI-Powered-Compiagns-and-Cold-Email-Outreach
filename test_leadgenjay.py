#!/usr/bin/env python3
"""Test LeadGenJay-style emails with unusual industries"""

from email_generator import EmailGenerator

generator = EmailGenerator()

# Completely different leads to stress test
leads = [
    {'first_name': 'Rachel', 'company': 'Petly', 'title': 'Founder', 'industry': 'Pet Tech'},
    {'first_name': 'James', 'company': 'Lawbit', 'title': 'CEO', 'industry': 'Legal Tech'},
    {'first_name': 'Priya', 'company': 'EduPath', 'title': 'CTO', 'industry': 'EdTech'},
    {'first_name': 'Marcus', 'company': 'GreenFleet', 'title': 'VP Engineering', 'industry': 'Logistics / Sustainability'},
    {'first_name': 'Elena', 'company': 'TasteMaker', 'title': 'CEO', 'industry': 'Food & Beverage Tech'},
]

for lead in leads:
    print('='*70)
    print(f"{lead['first_name']} at {lead['company']} ({lead['title']}) - {lead['industry']}")
    print('='*70)
    
    result = generator.generate_initial_email(lead, campaign_context={'name': 'Test'})
    
    print(f"Case study: {result.get('case_study_used', 'unknown')}")
    print(f"Subject: {result['subject']}")
    print()
    print(result['body'])
    print(f"\nWords: {len(result['body'].split())}")
    print()
