#!/usr/bin/env python3
"""Check the last emails sent from the database."""

from database import db
from datetime import datetime, timedelta

# Find last sent emails
leads = list(db.leads.find(
    {'status': 'sent', 'initial_sent_at': {'$exists': True}}
).sort('initial_sent_at', -1).limit(20))

print("=" * 80)
print("LAST 20 EMAILS SENT")
print("=" * 80)

if not leads:
    print("❌ NO EMAILS FOUND IN DATABASE")
else:
    for i, lead in enumerate(leads, 1):
        sent_at = lead.get('initial_sent_at', 'N/A')
        email = lead.get('email', 'N/A')
        name = lead.get('name', 'N/A')
        from_email = lead.get('from_email', 'N/A')
        print(f"{i}. {sent_at} - {name} ({email}) from {from_email}")

# Check pending leads
print("\n" + "=" * 80)
pending = db.leads.count_documents({'status': 'pending'})
sent = db.leads.count_documents({'status': 'sent'})
replied = db.leads.count_documents({'status': 'replied'})
bounced = db.leads.count_documents({'status': 'bounced'})
invalid = db.leads.count_documents({'status': 'invalid'})

print(f"LEAD STATUS SUMMARY:")
print(f"  📝 Pending: {pending}")
print(f"  ✅ Sent: {sent}")
print(f"  💬 Replied: {replied}")
print(f"  ⚠️  Bounced: {bounced}")
print(f"  ❌ Invalid: {invalid}")
print("=" * 80)
