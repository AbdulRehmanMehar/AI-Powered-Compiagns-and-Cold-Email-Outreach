#!/usr/bin/env python3
"""Check the size of review prompts to understand 413 errors."""
import sys
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

from email_reviewer import COLD_EMAIL_GUIDELINES

# Count tokens approximately (1 token ≈ 4 chars for English)
chars = len(COLD_EMAIL_GUIDELINES)
approx_tokens = chars // 4

print("=" * 60)
print("PROMPT SIZE ANALYSIS")
print("=" * 60)
print()
print(f"COLD_EMAIL_GUIDELINES:")
print(f"  Characters: {chars:,}")
print(f"  Approx tokens: {approx_tokens:,}")
print()

# Additional overhead from system prompt, user prompt, etc.
# Estimate: ~2000 chars for the wrapper
additional_overhead = 2000
total_estimate = chars + additional_overhead

print(f"Total prompt estimate: ~{total_estimate:,} chars (~{total_estimate//4:,} tokens)")
print()
print("Groq API limits:")
print("  - compound/compound-mini: strict rate limits")
print("  - Some models: 8k context limit")
print("  - 413 'Request Entity Too Large' = prompt exceeded model's max input")
print()
print("The review prompt is quite large because it includes:")
print("  1. Full COLD_EMAIL_GUIDELINES (~140 lines)")
print("  2. AI writing detection instructions")
print("  3. Lead context (name, company, title, industry)")
print("  4. The email being reviewed")
print("  5. JSON schema for output")
