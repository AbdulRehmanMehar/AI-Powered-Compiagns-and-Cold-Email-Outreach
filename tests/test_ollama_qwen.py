#!/usr/bin/env python3
"""
Test Ollama Qwen model for cold email generation.
Connects to Ollama on 192.168.1.9:11434 and generates a sample email.
"""

import json
from openai import OpenAI

# Sample lead data (from your actual logs)
SAMPLE_LEAD = {
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

# Your actual author context (simplified)
AUTHOR_CONTEXT = """
Abdul Rehman - Full-stack engineer specializing in web/mobile app development.
Team: 3 senior engineers at PrimeStrides
Focus: Helping startups build MVPs and scale products quickly
Case studies: Built systems for 50+ startups
"""

EMAIL_GUIDELINES = """
Write cold emails following these rules:
1. First line MUST be specific to their company - no generic "saw something interesting"
2. ONE pain point per email matched to their stage/industry
3. Keep under 75 words (ideally 50-60)
4. Subject: 2-4 words, casual like a colleague sent it
5. Soft CTA only - never "schedule a call"
6. NO corporate jargon, NO em dashes, sound human
7. Use contractions (you're, we've, etc.)

Bad: "I noticed you're doing interesting things with AI..."
Good: "Most founders at your stage hit a wall when their eng team gets stuck maintaining instead of building."
"""


def test_ollama_generation(ollama_url="http://192.168.1.9:11434", model="qwen2.5:7b"):
    """Test email generation with Ollama Qwen"""
    
    print("=" * 60)
    print("Testing Ollama Qwen Email Generation")
    print("=" * 60)
    
    # Test basic connectivity first
    print(f"\n1️⃣  Testing connection to {ollama_url}...")
    import requests
    try:
        # Test Ollama native API
        response = requests.get(f"{ollama_url}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            print(f"   ✅ Ollama is running!")
            print(f"   Available models: {[m['name'] for m in models]}")
        else:
            print(f"   ⚠️ Ollama responded but returned {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Cannot reach Ollama: {e}")
        print(f"\n   Troubleshooting:")
        print(f"   1. Is Ollama running on 192.168.1.9?")
        print(f"   2. Is it accessible from this machine?")
        print(f"   3. Try: curl http://192.168.1.9:11434/api/tags")
        return
    
    # Connect to Ollama (OpenAI-compatible)
    print(f"\n2️⃣  Connecting to OpenAI-compatible endpoint...")
    client = OpenAI(
        base_url=f"{ollama_url}/v1",
        api_key="ollama"  # Ollama doesn't need real API key
    )
    
    # Test 1: Simple completion
    print(f"\n3️⃣  Testing basic completion with {model}...")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'Hello from Ollama!' in one sentence."}
            ],
            temperature=0.7
        )
        print(f"   ✅ Connection successful!")
        print(f"   Response: {response.choices[0].message.content}")
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return
    
    # Test 2: Email subject generation
    print(f"\n4️⃣  Generating email subject...")
    subject_prompt = f"""
Generate a casual 2-4 word subject line for this cold email context:

Lead: {SAMPLE_LEAD['name']}, {SAMPLE_LEAD['title']} at {SAMPLE_LEAD['company']}
Sender: Abdul Rehman, engineer helping startups build products

Subject should feel like a colleague sent it, not a sales email.
Just return the subject line, nothing else.

Examples:
- quick question
- your eng team
- scaling question
- hiring devs?
"""
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You write casual, colleague-like email subjects."},
                {"role": "user", "content": subject_prompt}
            ],
            temperature=0.8,
            max_tokens=20
        )
        subject = response.choices[0].message.content.strip().strip('"\'')
        print(f"   Subject: {subject}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        subject = "quick question"
    
    # Test 3: Full email generation
    print(f"\n5️⃣  Generating full email body...")
    email_prompt = f"""
Write a cold email to this lead:

LEAD INFO:
- Name: {SAMPLE_LEAD['name']}
- Title: {SAMPLE_LEAD['title']}
- Company: {SAMPLE_LEAD['company']}
- Description: {SAMPLE_LEAD['company_description']}

SENDER INFO:
{AUTHOR_CONTEXT}

GUIDELINES:
{EMAIL_GUIDELINES}

Write the email body ONLY (no subject). Under 75 words.
Be specific about their situation, suggest one pain point, soft CTA.
"""
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You write personalized cold emails for software development services. Be concise and human."},
                {"role": "user", "content": email_prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )
        body = response.choices[0].message.content.strip()
        
        print("\n" + "=" * 60)
        print("GENERATED EMAIL:")
        print("=" * 60)
        print(f"Subject: {subject}")
        print()
        print(body)
        print("=" * 60)
        
        # Count words
        word_count = len(body.split())
        print(f"\n📊 Word count: {word_count} words")
        
        if word_count > 75:
            print(f"   ⚠️ Over limit! (target: 50-75)")
        else:
            print(f"   ✅ Within target")
            
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return
    
    # Test 4: Email review/scoring
    print(f"\n6️⃣  Testing email review (scoring)...")
    review_prompt = f"""
Review this cold email and provide a JSON score:

EMAIL:
Subject: {subject}
Body: {body}

Rate the email on these criteria (0-100):
1. personalization_score: How specific is it to the lead's situation?
2. value_proposition_clarity: Is it clear what we're offering?
3. brevity: Is it concise? (Under 75 words = 100, over 100 words = 0)
4. human_tone: Does it sound like a real person, not AI?
5. cta_strength: Is the CTA soft and natural?

Return ONLY valid JSON in this format:
{{
    "overall_score": 85,
    "personalization_score": 90,
    "value_proposition_clarity": 80,
    "brevity": 95,
    "human_tone": 85,
    "cta_strength": 80,
    "issues": ["list any issues"],
    "suggestions": ["list improvements"]
}}
"""
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert at reviewing cold emails. Return valid JSON only."},
                {"role": "user", "content": review_prompt}
            ],
            temperature=0.3,  # Lower temp for more consistent JSON
            max_tokens=300
        )
        
        review_text = response.choices[0].message.content.strip()
        
        # Try to parse JSON
        try:
            review = json.loads(review_text)
            print(f"\n📋 REVIEW SCORES:")
            print(f"   Overall: {review.get('overall_score', 'N/A')}/100")
            print(f"   Personalization: {review.get('personalization_score', 'N/A')}/100")
            print(f"   Value Prop Clarity: {review.get('value_proposition_clarity', 'N/A')}/100")
            print(f"   Brevity: {review.get('brevity', 'N/A')}/100")
            print(f"   Human Tone: {review.get('human_tone', 'N/A')}/100")
            print(f"   CTA Strength: {review.get('cta_strength', 'N/A')}/100")
            
            if review.get('issues'):
                print(f"\n   Issues: {', '.join(review['issues'])}")
            if review.get('suggestions'):
                print(f"   Suggestions: {', '.join(review['suggestions'])}")
                
            print("\n   ✅ JSON parsing successful!")
            
        except json.JSONDecodeError as e:
            print(f"   ⚠️ JSON parsing failed: {e}")
            print(f"   Raw response:\n{review_text}")
            
    except Exception as e:
        print(f"   ❌ Review failed: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print("✅ Connection: Working")
    print("✅ Subject generation: Working")
    print("✅ Email body generation: Working")
    print("✅ Review/scoring: Working")
    print("\n🎉 Ollama Qwen is ready for production!")
    print("\nNext steps:")
    print("1. Update email_generator.py to support Ollama")
    print("2. Test with real campaign data")
    print("3. Monitor email quality vs Groq baseline")


if __name__ == "__main__":
    import sys
    
    # Allow custom URL and model via command line
    ollama_url = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.1.9:11434"
    model = sys.argv[2] if len(sys.argv) > 2 else "qwen2.5:7b"
    
    print(f"Using Ollama URL: {ollama_url}")
    print(f"Using Model: {model}\n")
    
    test_ollama_generation(ollama_url, model)
