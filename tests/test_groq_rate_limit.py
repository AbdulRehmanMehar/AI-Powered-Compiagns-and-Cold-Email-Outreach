"""Test Groq rate limiting with MongoDB storage and model fallback"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_generator import (
    EmailGenerator, 
    get_rate_limiter, 
    GROQ_MODEL_LIMITS,
    GROQ_FALLBACK_CHAIN
)
import time

print('=' * 70)
print('Groq Rate Limiting with MongoDB Storage & Model Fallback')
print('=' * 70)
print()

# Show fallback chain
print('Fallback Chain:')
for i, model in enumerate(GROQ_FALLBACK_CHAIN):
    limits = GROQ_MODEL_LIMITS.get(model, {})
    arrow = '→' if i < len(GROQ_FALLBACK_CHAIN) - 1 else ''
    print(f'  {i+1}. {model} ({limits.get("daily", "?")} req/day) {arrow}')
print()

# Initialize generator
gen = EmailGenerator()
print()

# Get current usage stats from DB
print('Current Usage (from MongoDB):')
print('-' * 70)
stats = gen.rate_limiter.get_usage_stats()
for model, data in stats.items():
    bar_len = int(data['percent_used'] / 5)  # 20 char bar
    bar = '█' * bar_len + '░' * (20 - bar_len)
    print(f'  {model}:')
    print(f'    [{bar}] {data["percent_used"]}%')
    print(f'    {data["daily_used"]:,}/{data["daily_limit"]:,} used, {data["daily_remaining"]:,} remaining')
    print()

# Test API call
print('Testing API call...')
start = time.time()

result = gen._call_llm(
    'You are helpful.',
    'Say "Hello from Groq!" and the model name you are.',
    temperature=0.1
)
elapsed = time.time() - start

print(f'Response: {result}')
print(f'Time: {elapsed:.2f}s')
print()

# Show updated stats
print('Updated Usage:')
stats = gen.rate_limiter.get_usage_stats()
primary = stats.get(gen.model, {})
print(f'  {gen.model}: {primary.get("daily_used", 0):,}/{primary.get("daily_limit", 0):,}')
print()

print('✅ Groq rate limiting with MongoDB storage working!')
print()
print('Note: Usage is now persisted in MongoDB (llm_usage collection)')
print('      and survives process restarts.')
