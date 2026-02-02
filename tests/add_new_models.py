#!/usr/bin/env python3
"""Add new Groq models to MongoDB."""
from pymongo import MongoClient
from datetime import datetime

client = MongoClient('mongodb://admin:strongpassword@192.168.1.9:27017/')
db = client['primeoutreachcron']
collection = db['groq_model_limits']

today = datetime.utcnow().strftime('%Y-%m-%d')

# New models to add
new_models = {
    'openai/gpt-oss-120b': {'requests_per_minute': 30, 'requests_per_day': 1000, 'tokens_per_minute': 8000, 'tokens_per_day': 200000, 'priority': 8},
    'moonshotai/kimi-k2-instruct': {'requests_per_minute': 60, 'requests_per_day': 1000, 'tokens_per_minute': 10000, 'tokens_per_day': 300000, 'priority': 9},
    'allam-2-7b': {'requests_per_minute': 30, 'requests_per_day': 7000, 'tokens_per_minute': 6000, 'tokens_per_day': 500000, 'priority': 10},
}

print("Adding new models to MongoDB...")
for model, limits in new_models.items():
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
    status = 'added' if result.upserted_id else 'updated'
    print(f'  {model}: {status}')

print()
print('Current model inventory:')
for doc in collection.find({}, {'model': 1, 'limits.tokens_per_day': 1, '_id': 0}).sort('limits.priority', 1):
    model = doc['model']
    tokens = doc.get('limits', {}).get('tokens_per_day', 'unknown')
    if isinstance(tokens, (int, float)):
        print(f'  {model}: {tokens:,.0f} tokens/day')
    else:
        print(f'  {model}: {tokens} tokens/day')
