#!/usr/bin/env python3
"""Sanity check of key components."""
import sys
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

print('=== SANITY CHECK ===\n')

# 1. Check imports work
try:
    from campaign_manager import CampaignManager
    from email_generator import EmailGenerator, GroqRateLimiter, GROQ_FALLBACK_CHAIN
    from email_reviewer import EmailReviewer
    from database import Lead, Campaign, Email
    print('✅ All imports work')
except Exception as e:
    print(f'❌ Import error: {e}')

# 2. Check fallback chain has no blocked models
blocked = ['allam-2-7b', 'moonshotai/kimi-k2-instruct']
for model in GROQ_FALLBACK_CHAIN:
    if model in blocked:
        print(f'❌ Blocked model in fallback chain: {model}')
        break
else:
    print(f'✅ Fallback chain clean ({len(GROQ_FALLBACK_CHAIN)} models)')

# 3. Check pending leads query works
cm = CampaignManager()
try:
    pending = cm.get_pending_leads(max_leads=5)
    print(f'✅ Pending leads query works ({len(pending)} found)')
except Exception as e:
    print(f'❌ Pending leads error: {e}')

# 4. Check rate limiter
rl = GroqRateLimiter()
try:
    model = rl.get_best_available_model()
    print(f'✅ Rate limiter works (best model: {model})')
except Exception as e:
    print(f'❌ Rate limiter error: {e}')

# 5. Check DB models are clean
from database import groq_limits_collection
db_models = [d['model'] for d in groq_limits_collection.find()]
for m in blocked:
    if m in db_models:
        print(f'❌ Blocked model in DB: {m}')
        break
else:
    print(f'✅ DB models clean ({len(db_models)} models)')

print('\n=== CHECK COMPLETE ===')
