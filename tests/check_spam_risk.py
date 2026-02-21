#!/usr/bin/env python3
"""Analyze spam risk and deliverability metrics."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from datetime import datetime, timedelta

emails_col = db['emails']

# Get the last 24 hours of sent emails
yesterday = datetime.utcnow() - timedelta(days=1)
recent_sent = list(emails_col.find({
    'status': 'sent',
    'sent_at': {'$gte': yesterday}
}))

print(f"=== SPAM RISK ANALYSIS ===\n")
print(f"Emails sent in last 24h: {len(recent_sent)}")
print()

# Check for bounces/complaints
bounces = list(emails_col.find({
    'status': 'bounced',
    'sent_at': {'$gte': yesterday}
}))
complaints = list(emails_col.find({
    'status': 'complaint',
    'sent_at': {'$gte': yesterday}
}))

if bounces:
    bounce_rate = len(bounces) / len(recent_sent) * 100 if recent_sent else 0
    print(f"⚠️  Bounces (24h): {len(bounces)} ({bounce_rate:.1f}%)")
    print(f"   Bounce rate > 5% signals spam folder risk\n")
else:
    print(f"✅ Bounces (24h): 0\n")

if complaints:
    complaint_rate = len(complaints) / len(recent_sent) * 100 if recent_sent else 0
    print(f"⚠️  Complaints (24h): {len(complaints)} ({complaint_rate:.1f}%)")
    print(f"   Any complaints harm reputation\n")
else:
    print(f"✅ Complaints (24h): 0\n")

# Account reputation
accounts_col = db['account_reputation']
accounts = list(accounts_col.find())
print(f"Email Account Reputation:")
for acc in sorted(accounts, key=lambda x: x.get('last_checked', datetime.min), reverse=True):
    email = acc.get('_id', acc.get('email', 'unknown'))
    health = acc.get('health_score', 0)
    status = acc.get('status', 'unknown')
    symbol = '✅' if health >= 0.8 else '⚠️ ' if health >= 0.5 else '❌'
    print(f"  {symbol} {email}: score={health:.2f}, status={status}")

print("\n=== KEY ACTIONABLE FIXES ===")
print("""
1. **Content Quality (MOST CRITICAL)**:
   ✅ Good: "Quick question", "Random thought", "Different angle"
   ❌ Bad: "Urgent", "Limited time", "Click here", "Free", "Make $"
   → Check email_reviewer score distribution
   → Ensure ALL sent emails have score ≥ 70

2. **Authentication (Critical)**:
   → Run: dig primestrides.com TXT | grep -i spf
   → Run: dig theabdulrehman.com TXT | grep -i spf
   → Both should show SPF record
   → Zoho auto-signs DKIM (good)
   → If missing SPF = automatic spam folder

3. **Warm-up (Currently OK)**:
   → You're at ~20/day across 8 accounts = 2.5/account/day (good)
   → Can safely go to 50-100/day total
   → New domains take 2-3 weeks to build reputation

4. **Test Actual Placement**:
   → Send a test email to your own Gmail account from each account
   → Check if it lands in INBOX (good) or PROMOTIONS/SPAM (bad)
   → If in SPAM, there's an auth/reputation issue
   
5. **Monitor IMAP for Feedback**:
   → System already checks for bounces/complaints
   → Keep bounce rate < 2%
   → Remove bounced addresses immediately
   
6. **Avoid Patterns**:
   → Check for pattern-generated emails (gradea@company.com)
   → RocketReach grade F = likely pattern (skip these)
   → Grade A-B only

7. **ISP-Specific Tests**:
   → Gmail: Usually most forgiving if SPF/DKIM correct
   → Outlook: Check Microsoft Smart Network Data Services (SNDS)
   → Corporate: May have whitelist requirements
""")

# Check draft quality
drafts_col = db['email_drafts']
recent_drafts = list(drafts_col.find({
    'status': 'ready_to_send',
    'created_at': {'$gte': yesterday}
}, {'quality_score': 1, 'email_type': 1}))

if recent_drafts:
    avg_score = sum(d.get('quality_score', 0) for d in recent_drafts) / len(recent_drafts)
    low_score = [d for d in recent_drafts if d.get('quality_score', 0) < 70]
    print(f"\n=== DRAFT QUALITY ===")
    print(f"Recent ready_to_send drafts: {len(recent_drafts)}")
    print(f"Average quality score: {avg_score:.1f}")
    if low_score:
        print(f"⚠️  {len(low_score)} drafts below threshold (< 70)")
    else:
        print(f"✅ All drafts above threshold")
