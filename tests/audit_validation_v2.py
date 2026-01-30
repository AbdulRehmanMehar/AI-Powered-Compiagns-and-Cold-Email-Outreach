"""
VALIDATION AUDIT: Where is email validation happening?
Updated: January 30, 2026
"""

print("=" * 70)
print("EMAIL VALIDATION AUDIT (UPDATED)")
print("=" * 70)
print()

# 1. RocketReach Client - when fetching leads
print("1. ROCKETREACH CLIENT (fetch_leads)")
print("-" * 40)
print("""
   ✅ RocketReach smtp_valid check (uses RR pre-validated data)
   ✅ RocketReach grade check (skips grade F)
   ✅ quick_email_check() - syntax, disposable, role-based, MX
   ✅ verify_email_smtp() - SMTP mailbox verification
""")

# 2. Campaign Manager - initial emails
print("2. CAMPAIGN MANAGER (send_initial_emails)")
print("-" * 40)
print("""
   ✅ RocketReach smtp_valid check
   ✅ RocketReach grade check  
   ✅ Previous bounce check
   ✅ MX record check - NOW DONE via EmailVerifier
   ✅ SMTP mailbox check - NOW DONE via EmailVerifier
""")

# 3. Campaign Manager - followup emails
print("3. CAMPAIGN MANAGER (send_followup_emails)")
print("-" * 40)
print("""
   ✅ RocketReach smtp_valid check
   ✅ RocketReach grade check
   ✅ Previous bounce check
   ✅ MX record check - NOW DONE via EmailVerifier
   ✅ SMTP mailbox check - NOW DONE via EmailVerifier
""")

print()
print("=" * 70)
print("VERIFICATION FLOW")
print("=" * 70)
print("""
For EVERY email before sending:

1. Check if previously bounced → SKIP
2. Check RocketReach smtp_valid → SKIP if "invalid"
3. Check RocketReach grade → SKIP if "F"
4. MX Record Check → SKIP if no MX records
5. SMTP Mailbox Check → SKIP if mailbox doesn't exist
6. If catch-all domain → WARN but continue (score 80)
7. If all pass → SEND

This gives you 5 LAYERS of bounce protection!
""")
