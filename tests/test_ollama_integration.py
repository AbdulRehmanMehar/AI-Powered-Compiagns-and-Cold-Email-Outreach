#!/usr/bin/env python3
"""
Quick test to verify Ollama integration with EmailGenerator.
Run this to test Ollama before changing LLM_PROVIDER in production.
"""

import os
import sys

# Set Ollama as provider for this test
os.environ['LLM_PROVIDER'] = 'ollama'
os.environ['OLLAMA_BASE_URL'] = sys.argv[1] if len(sys.argv) > 1 else 'http://192.168.1.9:11434'
os.environ['OLLAMA_MODEL'] = sys.argv[2] if len(sys.argv) > 2 else 'qwen2.5:7b'

print(f"Testing EmailGenerator with Ollama")
print(f"URL: {os.environ['OLLAMA_BASE_URL']}")
print(f"Model: {os.environ['OLLAMA_MODEL']}\n")

from email_generator import EmailGenerator

# Sample lead (from your logs)
test_lead = {
    "_id": "test123",
    "name": "Tyler Finn",
    "email": "tfinn2000@gmail.com",
    "title": "Co-Founder and CEO",
    "company": "Stealth Startup",
    "company_description": "Tech/software company, perfect fit for our services",
    "enrichment": {
        "company_summary": "Early-stage tech startup",
        "personalization_hooks": []
    }
}

test_context = {
    "icp_id": "startup_founders_funded",
    "icp_name": "Startup Founders (Funded)",
    "personalization_level": "high"
}

print("=" * 60)
print("1️⃣  Initializing EmailGenerator with Ollama...")
print("=" * 60)

try:
    generator = EmailGenerator()
    print("\n✅ EmailGenerator initialized successfully!\n")
except Exception as e:
    print(f"\n❌ Failed to initialize: {e}")
    sys.exit(1)

print("=" * 60)
print("2️⃣  Generating initial email...")
print("=" * 60)

try:
    result = generator.generate_initial_email(test_lead, test_context)
    
    print("\n✅ EMAIL GENERATED SUCCESSFULLY!\n")
    print("=" * 60)
    print("SUBJECT:", result.get('subject', 'N/A'))
    print("=" * 60)
    print(result.get('body', 'N/A'))
    print("=" * 60)
    
    # Show metadata
    print("\n📊 Metadata:")
    print(f"   Personalization: {result.get('personalization_level', 'N/A')}")
    print(f"   Review score: {result.get('review_score', 'N/A')}")
    print(f"   Review attempts: {result.get('review_attempts', 'N/A')}")
    
    # Count words
    body = result.get('body', '')
    word_count = len(body.split())
    print(f"   Word count: {word_count}")
    
    if word_count > 75:
        print(f"   ⚠️ Over target (should be <75 words)")
    else:
        print(f"   ✅ Within target")
    
    print("\n🎉 Ollama integration is working!")
    print("\nTo use Ollama in production:")
    print("1. Update .env: LLM_PROVIDER=ollama")
    print(f"2. Update .env: OLLAMA_BASE_URL={os.environ['OLLAMA_BASE_URL']}")
    print(f"3. Update .env: OLLAMA_MODEL={os.environ['OLLAMA_MODEL']}")
    print("4. Restart the application")
    
except Exception as e:
    print(f"\n❌ Email generation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
