#!/usr/bin/env python3
"""Fix all Groq models in MongoDB with proper limits."""
from pymongo import MongoClient
from datetime import datetime

client = MongoClient('mongodb://admin:strongpassword@192.168.1.9:27017/')
db = client['primeoutreachcron']
collection = db['groq_model_limits']

# All models with their correct limits
ALL_MODELS = {
    'groq/compound': {'requests_per_minute': 30, 'requests_per_day': 250, 'tokens_per_minute': 70000, 'tokens_per_day': 10000000, 'priority': 1},
    'groq/compound-mini': {'requests_per_minute': 30, 'requests_per_day': 250, 'tokens_per_minute': 70000, 'tokens_per_day': 10000000, 'priority': 2},
    'llama-3.1-8b-instant': {'requests_per_minute': 30, 'requests_per_day': 14400, 'tokens_per_minute': 6000, 'tokens_per_day': 500000, 'priority': 3},
    'llama-3.3-70b-versatile': {'requests_per_minute': 30, 'requests_per_day': 1000, 'tokens_per_minute': 12000, 'tokens_per_day': 100000, 'priority': 4},
    'qwen/qwen3-32b': {'requests_per_minute': 60, 'requests_per_day': 1000, 'tokens_per_minute': 6000, 'tokens_per_day': 500000, 'priority': 5},
    'meta-llama/llama-4-maverick-17b-128e-instruct': {'requests_per_minute': 30, 'requests_per_day': 1000, 'tokens_per_minute': 6000, 'tokens_per_day': 500000, 'priority': 6},
    'meta-llama/llama-4-scout-17b-16e-instruct': {'requests_per_minute': 30, 'requests_per_day': 1000, 'tokens_per_minute': 30000, 'tokens_per_day': 500000, 'priority': 7},
    'openai/gpt-oss-120b': {'requests_per_minute': 30, 'requests_per_day': 1000, 'tokens_per_minute': 8000, 'tokens_per_day': 200000, 'priority': 8},
    'moonshotai/kimi-k2-instruct': {'requests_per_minute': 60, 'requests_per_day': 1000, 'tokens_per_minute': 10000, 'tokens_per_day': 300000, 'priority': 9},
    'allam-2-7b': {'requests_per_minute': 30, 'requests_per_day': 7000, 'tokens_per_minute': 6000, 'tokens_per_day': 500000, 'priority': 10},
}

today = datetime.utcnow().strftime('%Y-%m-%d')

print("Updating all models with proper limits...")
for model, limits in ALL_MODELS.items():
    result = collection.update_one(
        {'model': model},
        {
            '$set': {
                'limits': limits,
                'updated_at': datetime.utcnow()
            },
            '$setOnInsert': {
                'model': model,
                'usage': {
                    'date': today,
                    'requests_today': 0,
                    'tokens_today': 0,
                    'minute_requests': []
                }
            }
        },
        upsert=True
    )
    print(f'  ✅ {model}: {limits["tokens_per_day"]:,} tokens/day')

print()
print("=" * 60)
print("TOTAL DAILY CAPACITY:")
print("=" * 60)
total_tokens = sum(m['tokens_per_day'] for m in ALL_MODELS.values())
total_requests = sum(m['requests_per_day'] for m in ALL_MODELS.values())
print(f"  Tokens/day:   {total_tokens:,}")
print(f"  Requests/day: {total_requests:,}")
