#!/usr/bin/env python3
"""
Bidirectional warmup email system for domain reputation building.

Phases:
1. SEND: Zoho accounts → Gmail test accounts (with Message-ID threading)
2. MONITOR: Check Gmail IMAP for new emails from Zoho senders
3. REPLY: Generate contextual replies using Groq
4. SEND_REPLY: Reply back via Gmail SMTP (maintains thread)

Runs 3-4x daily asynchronously, completely non-blocking.

Usage:
    python3 warmup_bidirectional.py  # Single cycle
    
    Or integrate into scheduler:
    asyncio.create_task(run_bidirectional_warmup_cycle())
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import logging
from typing import Optional, List, Dict, Tuple
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid, parsedate_to_datetime
import email as email_module
from email.header import decode_header
from concurrent.futures import ThreadPoolExecutor
import random

import aiosmtplib
from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError

from database import db
from groq import Groq
import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MongoDB collections
emails_col = db['emails']
warmup_threads_col = db['warmup_threads']
warmup_email_drafts_col = db['warmup_email_drafts']  # SEPARATE: Only for warmup (never campaign drafts)

# Groq client for reply generation and warmup email generation
client = Groq(api_key=config.GROQ_API_KEY)

# Thread pool for IMAP operations (blocking)
imap_executor = ThreadPoolExecutor(max_workers=4)


def get_email_provider(email_address: str) -> Tuple[str, str, int, str, int, int]:
    """
    Detect email provider and return SMTP/IMAP host, port, and IMAP timeout.
    Returns: (provider, smtp_host, smtp_port, imap_host, imap_port, imap_timeout_seconds)
    
    Outlook IMAP is slower than Gmail, so higher timeout.
    """
    domain = email_address.split('@')[1].lower()
    
    if 'gmail' in domain:
        return 'gmail', config.GMAIL_SMTP_HOST, config.GMAIL_SMTP_PORT, config.GMAIL_IMAP_HOST, config.GMAIL_IMAP_PORT, 10
    elif 'outlook' in domain or 'hotmail' in domain or 'office365' in domain:
        # Outlook/Hotmail/Office365 IMAP is slower - use 20 second timeout
        return 'outlook', config.OUTLOOK_SMTP_HOST, config.OUTLOOK_SMTP_PORT, config.OUTLOOK_IMAP_HOST, config.OUTLOOK_IMAP_PORT, 20
    else:
        # Fallback to Gmail for unknown providers
        logger.warning(f"Unknown email provider for {email_address}, using Gmail settings")
        return 'unknown', config.GMAIL_SMTP_HOST, config.GMAIL_SMTP_PORT, config.GMAIL_IMAP_HOST, config.GMAIL_IMAP_PORT, 10


async def send_warmup_email(
    from_account: dict,
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    in_reply_to: Optional[str] = None
) -> Dict:
    """
    Send warmup email from Zoho account to test Gmail account.
    Includes threading headers for conversation continuity.
    """
    from_email = from_account["email"]
    from_name = from_account.get("sender_name", "DM")

    if not html_body:
        html_body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html_body = html_body.replace("\n", "<br>\n")
        html_body = f"<html><body>{html_body}</body></html>"

    try:
        # Build MIME message
        msg = MIMEMultipart("alternative")
        
        # Generate Message-ID for thread tracking
        message_id = make_msgid(domain=from_email.split('@')[1])
        
        msg["From"] = formataddr((from_name, from_email))
        msg["To"] = formataddr((to_name, to_email))
        msg["Subject"] = subject
        msg["Message-ID"] = message_id
        msg["Date"] = email_module.utils.formatdate(localtime=True)
        
        # If replying to an existing email, maintain thread
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # Send via Zoho SMTP
        async with aiosmtplib.SMTP(
            hostname=config.ZOHO_SMTP_HOST,
            port=config.ZOHO_SMTP_PORT,
            start_tls=True
        ) as smtp:
            await smtp.login(from_email, from_account["password"])
            await smtp.send_message(msg)

        logger.info(f"✅ Warmup send: {from_email} → {to_email}")
        
        return {
            "success": True,
            "message_id": message_id,
            "from_email": from_email,
            "to_email": to_email,
            "subject": subject,
            "sent_at": datetime.utcnow()
        }
    except Exception as e:
        logger.error(f"❌ Warmup send failed: {from_email} → {to_email}: {e}")
        return {
            "success": False,
            "error": str(e),
            "from_email": from_email,
            "to_email": to_email
        }


async def check_gmail_imap(warmup_account: dict) -> List[Dict]:
    """
    Connect to Gmail IMAP and fetch new emails from Zoho senders.
    Runs in thread pool to avoid blocking async event loop.
    Returns list of new emails with full headers.
    With timeout to prevent hangs.
    """
    email = warmup_account["email"]
    app_password = warmup_account["app_password"]
    
    if not app_password:
        logger.warning(f"⚠️  No app password for {email}, skipping IMAP check")
        return []

    def _check_imap_sync() -> List[Dict]:
        """Synchronous IMAP operations (runs in thread pool)"""
        provider, _, _, imap_host, imap_port, imap_timeout = get_email_provider(email)
        
        try:
            logger.debug(f"Connecting to {provider} IMAP ({email}) with {imap_timeout}s timeout...")
            # Connect via IMAP with provider-specific timeout
            imap = IMAPClient(imap_host, port=imap_port, use_uid=True, ssl=True, timeout=imap_timeout)
            imap.login(email, app_password)
            
            emails_found = []
            spam_msg_ids = []  # Track spam emails to move later
            
            # Define provider-specific folders to check
            if provider == 'gmail':
                folders_to_check = [
                    ('INBOX', 'inbox'),
                    ('[Gmail]/Spam', 'spam'),
                ]
            elif provider == 'outlook':
                folders_to_check = [
                    ('INBOX', 'inbox'),
                    ('Junk', 'spam'),
                ]
            else:
                # Unknown provider - just check INBOX
                folders_to_check = [('INBOX', 'inbox')]
            
            for folder_name, folder_type in folders_to_check:
                try:
                    imap.select_folder(folder_name, readonly=False)
                    
                    # Search for unseen emails - will filter by sender after fetching
                    message_ids = imap.search('UNSEEN')
                    
                    if not message_ids:
                        continue
                    
                    # Limit to recent 50 emails per folder to avoid processing tons of old mail
                    message_ids = sorted(message_ids)[-50:] if len(message_ids) > 50 else message_ids
                    
                    logger.info(f"📧 Checking {len(message_ids)} emails in {folder_name} ({folder_type})")
                    
                    # Fetch emails
                    response = imap.fetch(message_ids, ['RFC822', 'FLAGS'])
                    
                    for msg_id, data in response.items():
                        try:
                            msg = email_module.message_from_bytes(data[b'RFC822'])
                            
                            # Extract headers
                            from_header = msg.get('From', '')
                            from_email_addr = email_module.utils.parseaddr(from_header)[1]  # Extract only email
                            subject = msg.get('Subject', '')
                            message_id = msg.get('Message-ID', '')
                            in_reply_to = msg.get('In-Reply-To', '')
                            body = ""
                            
                            # Extract body (prefer plain text)
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                            
                            # Filter: only process emails from Zoho domains
                            zoho_domains = ['primestrides.com', 'theabdulrehman.com']
                            is_from_zoho = any(domain in from_email_addr for domain in zoho_domains)
                            
                            if is_from_zoho:
                                emails_found.append({
                                    "msg_id": msg_id,
                                    "from_email": from_email_addr,
                                    "subject": subject,
                                    "body": body,
                                    "message_id": message_id,
                                    "in_reply_to": in_reply_to,
                                    "to_email": email,  # Which warmup account received this
                                    "folder": folder_type,  # Track where email was found
                                    "received_at": datetime.utcnow()
                                })
                                
                                # Track spam emails to auto-move to INBOX (mark as not spam)
                                if folder_type == "spam":
                                    spam_msg_ids.append(msg_id)
                                
                                # Log folder placement for reputation tracking
                                emoji = "📬" if folder_type == "inbox" else "⚠️ SPAM" if folder_type == "spam" else "📨"
                                logger.info(f"  {emoji} {from_email_addr}: {subject}")
                        
                        except Exception as e:
                            logger.error(f"Failed to parse email {msg_id}: {e}")
                            continue
                    
                    # Mark as read (don't process twice)
                    if emails_found:
                        imap.set_flags(message_ids, [b'\\Seen'])
                
                except Exception as folder_error:
                    # Folder doesn't exist for this provider, skip
                    logger.debug(f"Folder {folder_name} not found or error: {folder_error}")
                    continue
            
            # AUTO-MARK-AS-NOT-SPAM: Move spam emails to INBOX (simulates user marking "Not Spam")
            if spam_msg_ids:
                try:
                    spam_folder = '[Gmail]/Spam' if provider == 'gmail' else 'Junk' if provider == 'outlook' else None
                    
                    if spam_folder:
                        imap.select_folder(spam_folder, readonly=False)
                        # Move emails from spam folder to INBOX
                        imap.move(spam_msg_ids, 'INBOX')
                        logger.info(f"✅ Auto-moved {len(spam_msg_ids)} emails from {spam_folder} → INBOX (marking as not spam)\n")
                except Exception as move_error:
                    logger.warning(f"⚠️  Could not auto-move spam emails: {move_error}")
                    pass
            
            imap.logout()
            return emails_found
            
        except IMAPClientError as e:
            error_msg = str(e).lower()
            # Outlook/Hotmail disabled basic auth for IMAP - skip gracefully
            if 'basicauthblocked' in error_msg or 'logon' in error_msg:
                logger.warning(f"⚠️  {provider.upper()} IMAP auth blocked for {email}")
                logger.debug(f"   SOLUTION: Enable 2-step verification (2FA) on the account:")
                logger.debug(f"   1. Go to Microsoft account security: https://account.microsoft.com/security")
                logger.debug(f"   2. Enable 'Two-step verification' if not already enabled")
                logger.debug(f"   3. Regenerate app password from 'App passwords' section")
                logger.debug(f"   4. Re-test IMAP (requires 2FA to be active)")
            else:
                logger.error(f"❌ IMAP connection error for {email}: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected error checking IMAP for {email}: {e}")
            return []
    
    # Run blocking IMAP operations in thread pool with 30 second timeout
    try:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(imap_executor, _check_imap_sync),
            timeout=30.0  # 30 second timeout
        )
    except asyncio.TimeoutError:
        logger.warning(f"⚠️  IMAP check for {email} timed out (30s), skipping")
        return []


async def generate_reply(
    original_from: str,
    original_subject: str,
    original_body: str
) -> str:
    """
    Generate contextual reply using Groq.
    Keeps reply brief, professional, and engaging.
    """
    try:
        prompt = f"""You are an engaged business professional replying to an email.

Original message from {original_from}:
Subject: {original_subject}

Message:
{original_body}

Generate a brief, professional, 1-2 sentence reply that:
- Shows you read their email
- Asks one engaging follow-up question
- Is warm and conversational (not robotic)
- Is suitable for a B2B outreach context

Reply with ONLY the email body text, nothing else. No subject line, no greeting."""

        response = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=150
        )
        
        reply_text = response.choices[0].message.content.strip()
        logger.info(f"✅ Generated reply via Groq")
        return reply_text
        
    except Exception as e:
        logger.error(f"❌ Failed to generate reply via Groq: {e}")
        # Fallback simple reply
        return "Thanks for your message! Looking forward to our conversation."


async def send_reply_email(
    from_warmup_account: dict,
    original_from: str,
    subject: str,
    body: str,
    message_id: str
) -> Dict:
    """
    Send reply email via Gmail/Outlook SMTP.
    Maintains thread by setting In-Reply-To and References.
    """
    from_email = from_warmup_account["email"]
    app_password = from_warmup_account["app_password"]
    
    if not app_password:
        return {"success": False, "error": "No app password available"}
    
    provider, smtp_host, smtp_port, _, _, _ = get_email_provider(from_email)
    
    try:
        # Build MIME message
        msg = MIMEMultipart("alternative")
        
        new_message_id = make_msgid(domain=from_email.split('@')[1])
        
        msg["From"] = from_email
        msg["To"] = original_from
        msg["Subject"] = subject if subject.startswith("Re:") else f"Re: {subject}"
        msg["Message-ID"] = new_message_id
        msg["In-Reply-To"] = message_id
        msg["References"] = message_id
        msg["Date"] = email_module.utils.formatdate(localtime=True)
        
        # Plain text version
        msg.attach(MIMEText(body, "plain"))
        
        # HTML version
        html_body = body.replace("\n", "<br>\n")
        msg.attach(MIMEText(f"<html><body>{html_body}</body></html>", "html"))
        
        # Send via provider SMTP
        async with aiosmtplib.SMTP(hostname=smtp_host, port=smtp_port, start_tls=True) as smtp:
            await smtp.login(from_email, app_password)
            await smtp.send_message(msg)
        
        logger.info(f"✅ Reply sent: {from_email} → {original_from}")
        
        return {
            "success": True,
            "message_id": new_message_id,
            "from_email": from_email,
            "to_email": original_from,
            "sent_at": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to send reply from {from_email} to {original_from}: {e}")
        return {"success": False, "error": str(e)}


async def process_incoming_email(email_data: Dict) -> None:
    """
    Process incoming email and send reply if appropriate.
    Records folder placement for reputation tracking.
    """
    from_email = email_data["from_email"]
    subject = email_data["subject"]
    body = email_data["body"]
    message_id = email_data["message_id"]
    to_email = email_data["to_email"]
    folder = email_data.get("folder", "inbox")  # Track where email was found
    
    # Check if this is from one of our Zoho senders
    zoho_domains = ['primestrides.com', 'theabdulrehman.com']
    is_from_zoho = any(domain in from_email for domain in zoho_domains)
    
    if not is_from_zoho:
        logger.debug(f"Skipping email from non-Zoho sender: {from_email}")
        return
    
    # Find which warmup account to reply from
    # Choose different account than the original sender to seem more natural
    reply_from_account = None
    for acc in config.WARMUP_ACCOUNTS:
        if acc["email"] == to_email:
            reply_from_account = acc
            break
    
    if not reply_from_account:
        logger.warning(f"No warmup account found for {to_email}")
        return
    
    # Generate contextual reply
    reply_body = await generate_reply(from_email, subject, body)
    
    # Send reply
    result = await send_reply_email(
        reply_from_account,
        from_email,
        subject,
        reply_body,
        message_id
    )
    
    if result["success"]:
        # Record in MongoDB
        warmup_threads_col.insert_one({
            "type": "reply",
            "from_email": to_email,
            "to_email": from_email,
            "original_message_id": message_id,
            "reply_message_id": result["message_id"],
            "subject": subject,
            "received_from_folder": folder,  # Track where we found the original email
            "created_at": datetime.utcnow(),
            "cycle": datetime.utcnow().isoformat()
        })


async def generate_warmup_templates(count: int = 5) -> List[Dict]:
    """
    Generate warmup email templates using Groq.
    Returns list of templates with subject and body.
    Uses Groq explicitly (not LLM_PROVIDER).
    """
    templates = []
    
    prompts = [
        "Write a professional but friendly cold email subject line and body (~100 words) for outreach to SaaS founders. Keep it warm and conversational.",
        "Write a cold email subject and body (~100 words) introducing a B2B service. Be concise, warm, and focus on one key benefit.",
        "Generate a cold email template (~100 words) for reaching out to business leaders. Use a casual, genuine tone.",
        "Write a cold outreach email (~100 words) that asks a thoughtful question about their business. Keep it short and personable.",
        "Create a cold email subject and body (~100 words) that opens with a specific insight about their industry. Be warm and human."
    ]
    
    try:
        for idx, prompt in enumerate(prompts[:count]):
            response = client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[{
                    "role": "user",
                    "content": prompt
                }],
                temperature=0.8,
                max_tokens=200
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse subject and body from response
            lines = content.split('\n')
            subject = lines[0] if lines else "Quick intro"
            body = '\n'.join(lines[1:]).strip() if len(lines) > 1 else content
            
            # Clean up
            subject = subject.replace('Subject:', '').replace('Subject :', '').strip()
            body = body.replace('Body:', '').replace('Body :', '').strip()
            
            template = {
                "subject": subject[:100],  # Cap at 100 chars
                "body": body,
                "created_at": datetime.utcnow(),
                "generated_via": "groq"
            }
            
            templates.append(template)
            logger.debug(f"Generated warmup template {idx + 1}/{count}: {subject[:50]}...")
        
        return templates
        
    except Exception as e:
        logger.error(f"❌ Failed to generate warmup templates: {e}")
        # Fallback templates
        return [
            {
                "subject": "Quick question about your company",
                "body": "Hi there,\n\nI came across your company and was impressed by what you're doing. I had a quick question about your current workflow — would love to chat.\n\nBest regards",
                "created_at": datetime.utcnow(),
                "generated_via": "fallback"
            },
            {
                "subject": "Thought you'd find this interesting",
                "body": "Hi,\n\nShort note — I think there's an opportunity here that aligned with your team's goals. Worth a quick conversation?\n\nLooking forward",
                "created_at": datetime.utcnow(),
                "generated_via": "fallback"
            }
        ]


async def fetch_and_send_initial_emails() -> int:
    """
    Fetch/generate warmup email templates and send to warmup accounts.
    Uses SEPARATE warmup_email_drafts collection (never campaign drafts).
    Returns count of emails sent.
    """
    if not config.WARMUP_ACCOUNTS:
        logger.warning("⚠️  No warmup accounts configured")
        return 0
    
    if not config.ZOHO_ACCOUNTS:
        logger.warning("⚠️  No Zoho accounts configured")
        return 0
    
    # Fetch warmup templates from SEPARATE collection (not campaign drafts)
    drafts = list(warmup_email_drafts_col.find({
        "created_at": {"$gte": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)}
    }).limit(5))
    
    # If no templates generated today, generate fresh ones
    if not drafts:
        logger.info("📝 Generating fresh warmup templates via Groq...")
        templates = await generate_warmup_templates(count=5)
        # Store in warmup collection
        if templates:
            warmup_email_drafts_col.insert_many(templates)
            drafts = templates
        else:
            logger.warning("⚠️  Could not generate warmup templates")
            return 0
    
    logger.info(f"\n=== BIDIRECTIONAL WARMUP CYCLE ===")
    logger.info(f"✅ Found {len(config.ZOHO_ACCOUNTS)} Zoho accounts")
    logger.info(f"✅ Found {len(config.WARMUP_ACCOUNTS)} test accounts")
    logger.info(f"✅ Found {len(drafts)} warmup templates (SEPARATE collection - no campaign conflict)\n")
    
    sent_count = 0
    
    # Send one email per warmup account, with RANDOMIZED account pairing
    # Shuffle Zoho accounts to prevent ISP pattern detection
    zoho_accounts_shuffled = config.ZOHO_ACCOUNTS.copy()
    random.shuffle(zoho_accounts_shuffled)
    
    # Send one email per warmup account, rotating through Zoho accounts and drafts
    for idx, warmup_account in enumerate(config.WARMUP_ACCOUNTS):
        # Use shuffled Zoho accounts to avoid predictable patterns
        zoho_account = zoho_accounts_shuffled[idx % len(zoho_accounts_shuffled)]
        draft = drafts[idx % len(drafts)]
        
        result = await send_warmup_email(
            from_account=zoho_account,
            to_email=warmup_account["email"],
            to_name="Test User",
            subject=draft["subject"],
            body=draft["body"],
            html_body=draft.get("html_body")
        )
        
        if result["success"]:
            # Record in MongoDB
            emails_col.insert_one({
                "from_email": result["from_email"],
                "to_email": result["to_email"],
                "subject": result["subject"],
                "status": "sent",
                "email_type": "warmup_bidirectional",
                "message_id": result["message_id"],
                "sent_at": result["sent_at"],
                "created_at": datetime.utcnow()
            })
            sent_count += 1
    
    logger.info(f"✅ Sent {sent_count} warmup emails\n")
    return sent_count


async def check_and_reply_to_emails() -> Dict:
    """
    Monitor warmup test accounts for new emails from Zoho senders.
    Checks INBOX and SPAM folders to track placement rate.
    Generates and sends contextual replies.
    
    Returns dict with reply count and placement stats.
    """
    if not config.WARMUP_ACCOUNTS:
        logger.warning("⚠️  No warmup accounts configured")
        return {"replies": 0, "inbox": 0, "spam": 0}
    
    logger.info("📬 Checking for incoming emails...\n")
    
    all_emails = []
    inbox_placement = 0
    spam_placement = 0
    
    # Check each warmup account for new emails (with timeout per account)
    for warmup_account in config.WARMUP_ACCOUNTS:
        try:
            # Timeout per account: 15 seconds (Gmail is fast, Outlook might be slower)
            result = await asyncio.wait_for(
                check_gmail_imap(warmup_account),
                timeout=15
            )
            
            for email_data in result:
                all_emails.append(email_data)
                
                # Track placement
                if email_data.get("folder") == "inbox":
                    inbox_placement += 1
                elif email_data.get("folder") == "spam":
                    spam_placement += 1
        except asyncio.TimeoutError:
            logger.warning(f"⏱️  IMAP timeout for {warmup_account['email']} (check manually)")
        except Exception as e:
            logger.error(f"❌ Error checking {warmup_account['email']}: {e}")
    
    if not all_emails:
        logger.info(f"✅ No new warmup emails to process\n")
        return {"replies": 0, "inbox": inbox_placement, "spam": spam_placement}
    
    logger.info(f"📧 Found {len(all_emails)} emails for processing:")
    logger.info(f"   📥 INBOX: {inbox_placement}")
    logger.info(f"   ⚠️  SPAM: {spam_placement}\n")
    
    # Process each email and send reply
    replies_sent = 0
    for email_data in all_emails:
        await process_incoming_email(email_data)
        replies_sent += 1
    
    logger.info(f"✅ Generated {replies_sent} replies\n")
    
    return {
        "replies": replies_sent,
        "inbox": inbox_placement,
        "spam": spam_placement
    }


async def run_bidirectional_warmup_cycle() -> Dict:
    """
    Complete bidirectional warmup cycle:
    1. Send initial warmup emails from Zoho → Gmail (shuffled accounts prevent patterns)
    2. Check INBOX and SPAM folders for replies
    3. Send contextual replies back
    4. Track spam placement rate for reputation monitoring
    
    Returns summary of activity including spam placement stats.
    """
    logger.info("=" * 60)
    logger.info("BIDIRECTIONAL WARMUP CYCLE STARTED")
    logger.info("=" * 60)
    
    try:
        # Phase 1: Send initial emails (with randomized account pairing)
        send_count = await fetch_and_send_initial_emails()
        
        # Wait a bit for replies (won't be immediate, but check anyway)
        await asyncio.sleep(2)
        
        # Phase 2: Check for replies and auto-respond (monitors both inbox and spam)
        reply_result = await check_and_reply_to_emails()
        reply_count = reply_result.get("replies", 0)
        inbox_count = reply_result.get("inbox", 0)
        spam_count = reply_result.get("spam", 0)
        
        summary = {
            "sent": send_count,
            "replies": reply_count,
            "placement": {
                "inbox": inbox_count,
                "spam": spam_count,
                "spam_rate": f"{(spam_count / (inbox_count + spam_count) * 100):.1f}%" if (inbox_count + spam_count) > 0 else "N/A"
            },
            "total_activity": send_count + reply_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info("=" * 60)
        logger.info(f"CYCLE COMPLETE")
        logger.info(f"  📤 Sent: {summary['sent']}")
        logger.info(f"  📥 Replies: {summary['replies']}")
        logger.info(f"  📬 INBOX: {inbox_count} | ⚠️ SPAM: {spam_count} ({summary['placement']['spam_rate']})")
        logger.info("=" * 60)
        
        return summary
        
    except Exception as e:
        logger.error(f"❌ Bidirectional warmup cycle failed: {e}", exc_info=True)
        return {
            "error": str(e), 
            "sent": 0, 
            "replies": 0,
            "placement": {"inbox": 0, "spam": 0, "spam_rate": "N/A"}
        }


if __name__ == "__main__":
    # Run single cycle
    result = asyncio.run(run_bidirectional_warmup_cycle())
    print(f"\n📊 Result: {result}")
