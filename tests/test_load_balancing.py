"""Test the load balancing strategy across Groq models."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_generator import get_rate_limiter, GROQ_FALLBACK_CHAIN

def main():
    rl = get_rate_limiter()
    
    print('=== LOAD BALANCING SCORING ===\n')
    
    models = [
        'groq/compound', 
        'groq/compound-mini', 
        'llama-3.3-70b-versatile', 
        'qwen/qwen3-32b', 
        'llama-3.1-8b-instant'
    ]
    
    scores = []
    
    for model in models:
        data = rl._get_cached(model)
        usage = data.get('usage', {})
        
        req_used = usage.get('requests_today', 0)
        req_limit = data.get('requests_per_day', 1000)
        tok_used = usage.get('tokens_today', 0)
        tok_limit = data.get('tokens_per_day', 100000)
        priority = data.get('priority', 99)
        
        # Same logic as get_best_available_model
        if tok_limit >= 10000000:
            remaining_pct = max(0, (req_limit - req_used) / req_limit * 100)
        else:
            req_rem = max(0, (req_limit - req_used) / req_limit * 100)
            tok_rem = max(0, (tok_limit - tok_used) / tok_limit * 100)
            remaining_pct = min(req_rem, tok_rem)
        
        quality_bonus = max(0, 20 - priority * 2)
        score = remaining_pct + quality_bonus
        if remaining_pct < 20:
            score -= 30
        
        scores.append((model, score, remaining_pct, priority, quality_bonus))
        print(f'{model}:')
        print(f'  Remaining: {remaining_pct:.0f}% | Priority: {priority} | Bonus: +{quality_bonus} | Score: {score:.0f}')
    
    print('\n=== MODEL SELECTION ORDER (by score) ===')
    scores.sort(key=lambda x: -x[1])
    for i, (model, score, rem, pri, bonus) in enumerate(scores, 1):
        print(f'{i}. {model} (score: {score:.0f})')
    
    print('\n=== CURRENT DISTRIBUTION ===')
    print(rl.show_load_distribution())
    
    print('\n=== HOW IT WORKS ===')
    print('• Higher score = gets selected first')
    print('• Quality bonus rewards high-priority (low number) models')
    print('• As capacity drops, score drops, load shifts to other models')
    print('• Below 20% capacity: -30 penalty prevents exhaustion')
    print('• Net effect: Load spreads across models while preferring quality')

if __name__ == '__main__':
    main()
