"""Check if the self-improvement system is learning from past reviews."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_reviewer import EmailReviewer
from email_generator import EmailGenerator
from database import email_reviews_collection

reviewer = EmailReviewer()

# Check what's stored
stats = reviewer.get_review_stats(days=7)
print('📊 REVIEW STATS (Last 7 Days):')
print(f'   Total reviews stored: {stats["total"]}')
print(f'   Passed: {stats["passed"]}')
print(f'   Failed: {stats["failed"]}')
print(f'   Avg score: {stats["avg_score"]}')

# Check recent reviews in DB
reviews = list(email_reviews_collection.find().sort('created_at', -1).limit(5))
print(f'\n📝 RECENT REVIEWS IN DB ({len(reviews)} shown):')
for r in reviews:
    company = r.get('lead_company', '?')
    print(f'   - Score: {r.get("score", "?")} | Status: {r.get("status", "?")} | Company: {company}')

# Check the improvement prompt
print('\n📚 CURRENT IMPROVEMENT PROMPT:')
prompt = reviewer.get_improvement_prompt(days=7)
if prompt:
    print(prompt[:1500] + '...' if len(prompt) > 1500 else prompt)
else:
    print('   (No improvement prompt - not enough failures)')

# Verify it's being used in generation
print('\n🔄 VERIFYING LEARNING IS INJECTED INTO GENERATOR:')
generator = EmailGenerator()
# The generator prints "📚 Including learnings from past reviews" when it uses the prompt
