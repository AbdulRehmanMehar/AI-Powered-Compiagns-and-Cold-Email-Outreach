#!/usr/bin/env python3
"""Debug the improvement prompt generation."""
import re
from email_reviewer import EmailReviewer

reviewer = EmailReviewer()
recent_failures = reviewer.get_recent_reviews(days=14, only_failures=True, limit=50)

print(f'Recent failures fetched: {len(recent_failures)}')

# Manually replicate the logic
violation_counts = {}
skipped = 0

for review in recent_failures:
    violations = review.get('rule_violations', [])
    
    # Check if AI review failed
    has_ai_fail = any('AI review failed' in str(v) for v in violations if v)
    if has_ai_fail:
        skipped += 1
        continue
    
    for violation in violations:
        if not violation:
            continue
        v_str = str(violation)
        if 'banned phrase' in v_str.lower():
            match = re.search(r"'([^']+)'", v_str)
            if match:
                v_key = f"NEVER use: '{match.group(1)}'"
                violation_counts[v_key] = violation_counts.get(v_key, 0) + 1
        elif 'em dash' in v_str.lower():
            v_key = "NEVER use em dashes (—)"
            violation_counts[v_key] = violation_counts.get(v_key, 0) + 1
        elif 'spammy pattern' in v_str.lower():
            match = re.search(r"'([^']+)'", v_str)
            if match:
                v_key = f"NEVER use in subject: '{match.group(1)}'"
                violation_counts[v_key] = violation_counts.get(v_key, 0) + 1

print(f'Skipped (AI review failed): {skipped}')
print(f'\nViolation counts:')
for v, c in sorted(violation_counts.items(), key=lambda x: -x[1]):
    print(f'  {c}x: {v}')
