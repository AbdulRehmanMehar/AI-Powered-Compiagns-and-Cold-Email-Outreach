#!/usr/bin/env python
"""Verify rate limiter is used across all modules"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print('🔍 Checking rate limiter usage across system...\n')

from email_generator import get_rate_limiter, EmailGenerator
from email_reviewer import EmailReviewer
from lead_enricher import LeadEnricher
from icp_manager import ICPManager

# Get the global rate limiter
rl1 = get_rate_limiter()

results = []

# EmailGenerator
print('📧 EmailGenerator:')
eg = EmailGenerator()
has_rl = eg.rate_limiter is not None
same = eg.rate_limiter is rl1
print(f'   rate_limiter: {"✅ YES" if has_rl else "❌ NO"}')
print(f'   same instance: {"✅ YES" if same else "❌ NO"}')
results.append(('EmailGenerator', has_rl and same))

# EmailReviewer
print('\n📋 EmailReviewer:')
er = EmailReviewer()
has_rl = er.rate_limiter is not None
same = er.rate_limiter is rl1
print(f'   rate_limiter: {"✅ YES" if has_rl else "❌ NO"}')
print(f'   same instance: {"✅ YES" if same else "❌ NO"}')
results.append(('EmailReviewer', has_rl and same))

# LeadEnricher
print('\n🔍 LeadEnricher:')
le = LeadEnricher()
has_rl = le.rate_limiter is not None
same = le.rate_limiter is rl1
print(f'   rate_limiter: {"✅ YES" if has_rl else "❌ NO"}')
print(f'   same instance: {"✅ YES" if same else "❌ NO"}')
results.append(('LeadEnricher', has_rl and same))

# ICPManager
print('\n🎯 ICPManager:')
im = ICPManager()
has_rl = im.rate_limiter is not None
same = im.rate_limiter is rl1
print(f'   rate_limiter: {"✅ YES" if has_rl else "❌ NO"}')
print(f'   same instance: {"✅ YES" if same else "❌ NO"}')
results.append(('ICPManager', has_rl and same))

# Summary
print('\n' + '='*50)
print('📊 Summary:')
print(f'   DB Collection: groq_model_limits')
print(f'   Models tracked: {len(rl1.get_all_models())}')

all_ok = all(r[1] for r in results)
if all_ok:
    print('\n✅ All modules using shared DB-backed rate limiter!')
else:
    print('\n❌ Some modules NOT using rate limiter:')
    for name, ok in results:
        if not ok:
            print(f'   - {name}')
