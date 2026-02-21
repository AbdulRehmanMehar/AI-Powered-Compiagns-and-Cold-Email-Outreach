#!/usr/bin/env python3
"""
Setup test warm-up campaign for domain reputation building.

Fetches existing email drafts and sends them immediately to test addresses.
Uses real email content from your campaigns — completely legitimate.

Marks sent emails in MongoDB immediately. No waiting for send_worker.

Usage:
    python3 tests/setup_warmup_campaign.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from datetime import datetime, time

import aiosmtplib

from database import db
from bson import ObjectId
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

email_drafts_col = db['email_drafts']
emails_col = db['emails']

def text_to_html(text: str) -> str:
    """Convert plain text email to basic HTML."""
    html = text.replace("&", "&amp;")
    html = html.replace("<", "&lt;")
    html = html.replace(">", "&gt;")
    html = html.replace("\n", "<br>\n")
    return f"<html><body>{html}</body></html>"

async def send_email(account: dict, to_email: str, to_name: str, subject: str, body: str, html_body: str = None) -> dict:
    """Send email via aiosmtplib to test address."""
    from_email = account["email"]
    from_name = account.get("sender_name", from_email)
    
    try:
        # Build MIME message
        if html_body:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain"))
            msg.attach(MIMEText(html_body, "html"))
        else:
            # Auto-generate HTML from plain text
            auto_html = text_to_html(body)
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain"))
            msg.attach(MIMEText(auto_html, "html"))
        
        # Generate Message-ID
        domain = from_email.split("@")[1] if "@" in from_email else "primestrides.com"
        message_id = make_msgid(domain=domain)
        msg["Message-ID"] = message_id
        
        # Standard headers
        msg["Subject"] = subject
        msg["From"] = formataddr((from_name, from_email))
        msg["To"] = formataddr((to_name, to_email)) if to_name else to_email
        msg["Reply-To"] = config.REPLY_TO or from_email
        
        # Send via aiosmtplib
        logger.debug(f"Connecting to {config.ZOHO_SMTP_HOST}:{config.ZOHO_SMTP_PORT} as {from_email}")
        
        smtp = aiosmtplib.SMTP(
            hostname=config.ZOHO_SMTP_HOST,
            port=config.ZOHO_SMTP_PORT,
            timeout=60,
            start_tls=True,
        )
        
        await smtp.connect()
        await smtp.login(from_email, account["password"])
        await smtp.sendmail(from_email, [to_email], msg.as_string())
        await smtp.quit()
        
        logger.info(f"✅ Email sent: {from_email} → {to_email}")
        
        return {
            "success": True,
            "message_id": message_id,
            "from_email": from_email,
        }
    
    except Exception as e:
        logger.error(f"❌ SMTP error sending to {to_email}: {e}")
        return {
            "success": False,
            "error": str(e),
            "from_email": from_email,
        }


# Test email addresses (from env or defaults)
test_emails = os.getenv('WARMUP_EMAILS', 'mehars.6925@gmail.com,abdrehman6925@gmail.com,webdeveloper.6925@gmail.com,mehars.6925@hotmail.com,mehars.6925@outlook.com,abdrehman6925@outlook.com').split(',')
test_emails = [e.strip() for e in test_emails if e.strip()]

async def run_warmup_sends():
    """Fetch accounts, drafts, and send immediately."""
    print(f"\n=== WARM-UP TEST — SENDING IMMEDIATELY ===\n")
    print(f"Test email addresses: {test_emails}\n")

    # Get Zoho accounts from config
    accounts = config.ZOHO_ACCOUNTS
    
    if not accounts:
        print("❌ No Zoho accounts configured.")
        print("   Set ZOHO_EMAILS, ZOHO_PASSWORDS in environment")
        return 0
    
    print(f"✅ Found {len(accounts)} accounts configured\n")
    
    # Fetch existing high-quality drafts to clone
    existing_drafts = list(email_drafts_col.find(
        {
            'status': 'ready_to_send',
            'quality_score': {'$gte': 70}
        },
        sort=[('created_at', -1)],
        limit=3  # Get a few different templates
    ))
    
    if not existing_drafts:
        print("❌ No ready-to-send drafts found. System needs to generate drafts first.")
        print("   Check back after the pre_generator has created some drafts.")
        return False
    
    print(f"✅ Found {len(existing_drafts)} draft templates\n")
    
    # Send to each test email using rotating accounts
    total_sent = 0
    for idx, test_email in enumerate(test_emails):
        print(f"📧 {test_email}:")
        
        # Rotate through accounts
        account = accounts[idx % len(accounts)]
        source_draft = existing_drafts[idx % len(existing_drafts)]
        
        # Send the email
        result = await send_email(
            account=account,
            to_email=test_email,
            to_name="Test User",
            subject=source_draft.get('subject', ''),
            body=source_draft.get('body', ''),
            html_body=source_draft.get('html_body'),
        )
        
        if result["success"]:
            total_sent += 1
            message_id = result["message_id"]
            from_email = result["from_email"]
            
            # Create Email record in MongoDB to track this send
            email_doc = {
                'lead_id': ObjectId(),
                'campaign_id': source_draft['campaign_id'],
                'to_email': test_email,
                'subject': source_draft.get('subject', ''),
                'body': source_draft.get('body', ''),
                'email_type': 'warmup_test',
                'followup_number': 0,
                'from_email': from_email,
                'message_id': message_id,
                'status': 'sent',
                'is_icp': False,
                'created_at': datetime.utcnow(),
                'sent_at': datetime.utcnow(),
            }
            emails_col.insert_one(email_doc)
            print(f"   ✅ Email sent and recorded in MongoDB")
        else:
            print(f"   ❌ Send failed: {result.get('error', 'Unknown error')}")

    return total_sent

# Main
if __name__ == "__main__":
    try:
        total = asyncio.run(run_warmup_sends())
        
        print(f"\n{'='*60}")
        print(f"WARMUP COMPLETE")
        print(f"{'='*60}")
        print(f"""
✅ Sent {total} test emails immediately

How it works:
  1. Emails use REAL content from your existing campaigns
  2. Recipients: test addresses (mehars.6925@gmail.com, etc)
  3. Sent from: rotating Zoho accounts
  4. Status: All recorded in MongoDB emails collection

What to do:
  ✓ Check Gmail inbox/spam folder for test emails
  ✓ If in SPAM → mark "Not Spam" to train Gmail
  ✓ If in INBOX → great! Domain reputation is good
  ✓ Monitor for 7-10 days as Gmail learns your patterns

Monitoring:
  - Watch MongoDB emails collection: db.emails.find({{email_type: 'warmup_test'}})
  - Check for bounces/failures
  - After 1 week: should see better deliverability on production emails
  - After 2 weeks: ready to increase sending volume (MAX_REPLENISH_PER_CYCLE=3)

✨ These are legitimate emails — you can send these on a schedule anytime!
""")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

