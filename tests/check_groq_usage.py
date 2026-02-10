#!/usr/bin/env python
"""Check current Groq API usage stats"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_generator import get_rate_limiter, GROQ_MODEL_LIMITS, GROQ_FALLBACK_CHAIN

def main():
    print()
    print('╔══════════════════════════════════════════════════════════════════╗')
    print('║                    GROQ API USAGE STATS                          ║')
    print('╚══════════════════════════════════════════════════════════════════╝')
    print()
    
    limiter = get_rate_limiter()
    stats = limiter.get_usage_stats()
    
    total_used = 0
    total_limit = 0
    
    for model in GROQ_FALLBACK_CHAIN:
        if model not in stats:
            continue
        
        data = stats[model]
        total_used += data['daily_used']
        total_limit += data['daily_limit']
        
        # Progress bar
        bar_len = int(data['percent_used'] / 5)
        bar = '█' * bar_len + '░' * (20 - bar_len)
        
        # Status indicator
        if data['percent_used'] >= 90:
            status = '🔴'
        elif data['percent_used'] >= 70:
            status = '🟡'
        else:
            status = '🟢'
        
        print(f'{status} {model}')
        print(f'   [{bar}] {data["percent_used"]:>5.1f}%')
        print(f'   {data["daily_used"]:>6,} / {data["daily_limit"]:>6,} used')
        print(f'   {data["daily_remaining"]:>6,} remaining')
        print()
    
    # Total
    print('─' * 70)
    total_pct = (total_used / total_limit * 100) if total_limit > 0 else 0
    print(f'📊 TOTAL: {total_used:,} / {total_limit:,} ({total_pct:.1f}%)')
    print(f'   Combined capacity remaining: {total_limit - total_used:,} requests')
    print()
    
    # Fallback chain status
    print('🔄 Fallback Chain:')
    for i, model in enumerate(GROQ_FALLBACK_CHAIN):
        data = stats.get(model, {'daily_remaining': 0})
        arrow = ' → ' if i < len(GROQ_FALLBACK_CHAIN) - 1 else ''
        status = '✓' if data['daily_remaining'] > 0 else '✗'
        print(f'   {status} {model} ({data["daily_remaining"]:,} left){arrow}')
    print()


if __name__ == '__main__':
    main()
