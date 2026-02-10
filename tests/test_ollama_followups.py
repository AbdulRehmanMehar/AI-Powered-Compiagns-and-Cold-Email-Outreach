#!/usr/bin/env python3
"""
Test Ollama/Qwen-powered follow-up email generation.
Tests all 3 follow-up types: same-thread, new-thread, breakup.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_generator import EmailGenerator
import json

def test_followups():
    gen = EmailGenerator()
    
    test_leads = [
        {
            "first_name": "Marcus",
            "full_name": "Marcus Rivera",
            "title": "CTO",
            "company": "DataVault",
            "industry": "FinTech",
            "location": "New York"
        },
        {
            "first_name": "Priya",
            "full_name": "Priya Sharma",
            "title": "VP of Engineering",
            "company": "HealthSync",
            "industry": "HealthTech",
            "location": "San Francisco"
        },
        {
            "first_name": "Jake",
            "full_name": "Jake Williams",
            "title": "CEO & Co-Founder",
            "company": "BuildOS",
            "industry": "Construction Tech",
            "location": "Austin"
        },
    ]
    
    previous_emails = [{
        "subject": "quick question",
        "body": "marcus - noticed DataVault is scaling the analytics team. we helped a series b fintech cut onboarding time by 60% in 8 weeks. want the playbook?",
        "followup_number": 0
    }]
    
    context = {
        "single_pain_point": "engineering bandwidth",
        "front_end_offer": "free technical architecture review"
    }
    
    print("=" * 70)
    print("🧪 TESTING OLLAMA/QWEN FOLLOW-UP GENERATION")
    print("=" * 70)
    
    all_pass = True
    
    for lead in test_leads:
        print(f"\n{'='*70}")
        print(f"👤 Lead: {lead['first_name']} ({lead['title']} at {lead['company']})")
        print(f"{'='*70}")
        
        # Test 1: Same-thread follow-up
        print(f"\n📧 Follow-up #1 (Same Thread):")
        print("-" * 40)
        try:
            result1 = gen._generate_followup_same_thread(lead, context, previous_emails)
            print(f"Subject: {result1['subject']}")
            print(f"Body:\n{result1['body']}")
            words = len(result1['body'].split())
            print(f"\n📊 Word count: {words}")
            
            # Quality checks
            checks = []
            checks.append(("Subject has Re:", result1['subject'].startswith("Re:")))
            checks.append(("Under 50 words", words < 50))
            checks.append(("No 'just following up'", "just following up" not in result1['body'].lower()))
            checks.append(("Has content", len(result1['body'].strip()) > 20))
            
            for name, passed in checks:
                status = "✅" if passed else "❌"
                print(f"  {status} {name}")
                if not passed:
                    all_pass = False
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            all_pass = False
        
        # Test 2: New-thread follow-up
        print(f"\n📧 Follow-up #2 (New Thread):")
        print("-" * 40)
        try:
            result2 = gen._generate_followup_new_thread(lead, context, previous_emails)
            print(f"Subject: {result2['subject']}")
            print(f"Body:\n{result2['body']}")
            words = len(result2['body'].split())
            print(f"\n📊 Word count: {words}")
            
            checks = []
            checks.append(("New thread flag", result2.get('new_thread') == True))
            checks.append(("Under 60 words", words < 60))
            checks.append(("Has first name", lead['first_name'].lower() in result2['body'].lower()))
            checks.append(("Has content", len(result2['body'].strip()) > 20))
            
            for name, passed in checks:
                status = "✅" if passed else "❌"
                print(f"  {status} {name}")
                if not passed:
                    all_pass = False
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            all_pass = False
        
        # Test 3: Breakup email
        print(f"\n📧 Breakup Email:")
        print("-" * 40)
        try:
            result3 = gen._generate_breakup_email(lead, context, previous_emails)
            print(f"Subject: {result3['subject']}")
            print(f"Body:\n{result3['body']}")
            words = len(result3['body'].split())
            print(f"\n📊 Word count: {words}")
            
            checks = []
            checks.append(("New thread flag", result3.get('new_thread') == True))
            checks.append(("Under 50 words", words < 50))
            checks.append(("Has first name", lead['first_name'].lower() in result3['body'].lower()))
            checks.append(("Has content", len(result3['body'].strip()) > 20))
            
            for name, passed in checks:
                status = "✅" if passed else "❌"
                print(f"  {status} {name}")
                if not passed:
                    all_pass = False
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            all_pass = False
    
    print(f"\n{'='*70}")
    if all_pass:
        print("🎉 ALL TESTS PASSED - Ollama/Qwen follow-ups working!")
    else:
        print("⚠️ SOME CHECKS FAILED - review output above")
    print(f"{'='*70}")

if __name__ == "__main__":
    test_followups()
