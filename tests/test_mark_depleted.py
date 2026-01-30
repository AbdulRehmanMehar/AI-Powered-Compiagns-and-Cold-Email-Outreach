"""Test that mark_model_depleted correctly prevents model selection."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_generator import get_rate_limiter

def test_mark_depleted():
    rl = get_rate_limiter()
    
    print('=== TESTING mark_model_depleted ===\n')
    
    # Use a test model
    model = 'meta-llama/llama-4-scout-17b-16e-instruct'
    
    # Check current state
    data = rl._get_cached(model)
    usage = data.get('usage', {})
    print(f'BEFORE: {model}')
    print(f'  requests_today: {usage.get("requests_today", 0)}')
    print(f'  tokens_today: {usage.get("tokens_today", 0)}')
    
    can_proceed, wait, reason = rl.check_limit(model)
    print(f'  can_proceed: {can_proceed} ({reason})\n')
    
    # Mark as depleted
    print('Simulating 429 rate limit error...')
    rl.mark_model_depleted(model, '429_rate_limit_test')
    print()
    
    # Check after
    data = rl._get_cached(model)
    usage = data.get('usage', {})
    print(f'AFTER: {model}')
    print(f'  requests_today: {usage.get("requests_today", 0)} (limit: {data.get("requests_per_day", 0)})')
    print(f'  tokens_today: {usage.get("tokens_today", 0)} (limit: {data.get("tokens_per_day", 0)})')
    print(f'  depleted_reason: {usage.get("depleted_reason", "N/A")}')
    
    can_proceed, wait, reason = rl.check_limit(model)
    print(f'  can_proceed: {can_proceed} ({reason})\n')
    
    if not can_proceed:
        print('✅ Model correctly rejected after being marked depleted!')
    else:
        print('❌ BUG: Model still being selected after depletion!')
    
    # Also verify it won't be returned by get_best_available_model
    print('\n--- Checking get_best_available_model ---')
    best = rl.get_best_available_model(model)
    if best != model:
        print(f'✅ get_best_available_model returned {best} (not depleted {model})')
    else:
        print(f'❌ BUG: get_best_available_model returned depleted model {model}')

if __name__ == '__main__':
    test_mark_depleted()
