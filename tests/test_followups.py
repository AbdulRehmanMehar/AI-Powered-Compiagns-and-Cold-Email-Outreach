#!/usr/bin/env python3
"""
Test Follow-up Email Generation (LeadGenJay Style)

This tests that ALL follow-up emails follow LeadGenJay's principles:
- Email 2: Same thread, add value (not "just following up")
- Email 3: New thread, different angle, front-end offer
- Breakup: "Should I reach out to someone else?" approach
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_generator import EmailGenerator
import json

def test_followups():
    generator = EmailGenerator()

    # Test lead
    lead = {
        'first_name': 'Sarah',
        'full_name': 'Sarah Chen',
        'title': 'CTO',
        'company': 'FinFlow',
        'industry': 'FinTech'
    }

    context = {
        'single_pain_point': 'shipping AI features fast',
        'front_end_offer': 'free architecture review'
    }

    # Simulate previous emails
    previous_emails = [
        {'subject': 'quick question', 'body': 'initial email body here...'}
    ]

    print('=' * 60)
    print('TESTING FOLLOW-UP EMAILS (LeadGenJay Style)')
    print('=' * 60)

    # Test Follow-up #2 (same thread)
    print('\n📧 FOLLOW-UP #2 (Same Thread):')
    print('-' * 40)
    followup2 = generator._generate_followup_same_thread(lead, context, previous_emails)
    print(f"Subject: {followup2['subject']}")
    print(f"Body:\n{followup2['body']}")
    print(f"Word count: {len(followup2['body'].split())}")
    
    # Check for banned patterns
    banned = ['just following up', 'circling back', 'bumping this', 'checking in']
    body_lower = followup2['body'].lower()
    for pattern in banned:
        if pattern in body_lower:
            print(f"⚠️  WARNING: Contains banned pattern '{pattern}'")

    # Test Follow-up #3 (new thread)
    print('\n📧 FOLLOW-UP #3 (New Thread - Front End Offer):')
    print('-' * 40)
    previous_emails.append(followup2)
    followup3 = generator._generate_followup_new_thread(lead, context, previous_emails)
    print(f"Subject: {followup3['subject']}")
    print(f"Body:\n{followup3['body']}")
    print(f"Word count: {len(followup3['body'].split())}")
    print(f"New thread: {followup3.get('new_thread', False)}")

    # Test Breakup Email
    print('\n📧 BREAKUP EMAIL:')
    print('-' * 40)
    previous_emails.append(followup3)
    breakup = generator._generate_breakup_email(lead, context, previous_emails)
    print(f"Subject: {breakup['subject']}")
    print(f"Body:\n{breakup['body']}")
    print(f"Word count: {len(breakup['body'].split())}")

    print('\n' + '=' * 60)
    print('✅ ALL FOLLOW-UPS GENERATED')
    print('=' * 60)

if __name__ == '__main__':
    test_followups()
