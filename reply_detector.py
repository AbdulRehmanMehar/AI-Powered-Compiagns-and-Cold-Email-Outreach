"""
Reply Detection System
Checks Zoho inbox for replies and updates lead status

NOTE: Requires IMAP to be enabled in Zoho Mail settings:
1. Go to Zoho Mail → Settings → Mail Accounts
2. Select your account → IMAP Access
3. Toggle IMAP Access to ON
"""

import imaplib
import email
from email.header import decode_header
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime, timedelta
import re
import config
from database import Email, Lead, Campaign, emails_collection, leads_collection, DoNotContact


# Auto-reply/Out-of-office patterns (subject and body)
AUTO_REPLY_PATTERNS = [
    # Subject patterns
    r"out of (office|town)",
    r"automatic reply",
    r"auto[\-\s]?reply",
    r"away from (office|email|my desk)",
    r"on vacation",
    r"on holiday",
    r"on leave",
    r"currently away",
    r"out of the office",
    r"will be out",
    r"limited access",
    r"maternity leave",
    r"paternity leave",
    r"sabbatical",
    r"ooo:",
    r"auto-?response",
    r"\[auto\]",
]

# Patterns that indicate a permanent state (should add to do-not-contact)
PERMANENT_AUTO_REPLY_PATTERNS = [
    r"no longer (with|at|employed)",
    r"left (the company|the organization|this position)",
    r"is no longer (working|employed)",
    r"has left",
    r"moved on from",
    r"this email (address )?(is )?no longer (active|monitored|in use)",
    r"this (mailbox|inbox) is (not|no longer) (monitored|active)",
]

# Unsubscribe request patterns (in body)
UNSUBSCRIBE_PATTERNS = [
    r"unsubscribe",
    r"remove me",
    r"opt[\-\s]?out",
    r"stop (emailing|contacting|sending)",
    r"don'?t (email|contact|message)",
    r"take me off",
    r"no longer interested",
    r"not interested",
    r"please stop",
    r"do not contact",
    r"remove from (your )?(list|mailing)",
    r"never (email|contact)",
]


class ReplyDetector:
    """Detect replies in Zoho inbox and update campaign status"""
    
    def __init__(self):
        self.accounts = config.ZOHO_ACCOUNTS
        self.imap_host = "imap.zoho.com"
        self.imap_port = 993
        self._connections: Dict[str, imaplib.IMAP4_SSL] = {}
        self._failed_accounts: Set[str] = set()  # Track accounts that failed to connect
    
    def _is_auto_reply(self, subject: str, body: str) -> Tuple[bool, bool]:
        """
        Check if an email is an auto-reply/out-of-office message.
        
        Returns:
            (is_auto_reply, is_permanent) - is_permanent means they left the company etc.
        """
        text = f"{subject} {body}".lower()
        
        # Check for permanent auto-reply (left company etc)
        for pattern in PERMANENT_AUTO_REPLY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True, True
        
        # Check for temporary auto-reply (vacation, OOO)
        for pattern in AUTO_REPLY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True, False
        
        # Check email headers that indicate auto-reply
        # (These would be checked in the actual email parsing)
        
        return False, False
    
    def _is_unsubscribe_request(self, subject: str, body: str) -> bool:
        """Check if an email is an unsubscribe request"""
        text = f"{subject} {body}".lower()
        
        for pattern in UNSUBSCRIBE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    def _get_email_body(self, msg) -> str:
        """Extract plain text body from email message"""
        body = ""
        try:
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode('utf-8', errors='ignore')
                            break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode('utf-8', errors='ignore')
        except Exception:
            pass
        return body
    
    def connect(self, account: Dict[str, str]) -> Optional[imaplib.IMAP4_SSL]:
        """Connect to IMAP server for an account"""
        email_addr = account["email"]
        
        # Skip if we already know this account can't connect
        if email_addr in self._failed_accounts:
            return None
        
        if email_addr in self._connections:
            try:
                self._connections[email_addr].noop()
                return self._connections[email_addr]
            except:
                pass
        
        try:
            mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            mail.login(email_addr, account["password"])
            self._connections[email_addr] = mail
            print(f"   ✅ Connected to inbox: {email_addr}")
            return mail
        except imaplib.IMAP4.error as e:
            error_msg = str(e)
            if "IMAP" in error_msg.upper():
                print(f"   ⚠️  {email_addr}: IMAP not enabled (enable in Zoho Mail Settings → IMAP Access)")
            else:
                print(f"   ❌ {email_addr}: {e}")
            self._failed_accounts.add(email_addr)
            return None
        except Exception as e:
            print(f"   ❌ {email_addr}: {e}")
            self._failed_accounts.add(email_addr)
            return None
    
    def disconnect_all(self):
        """Close all IMAP connections"""
        for email_addr, conn in self._connections.items():
            try:
                conn.logout()
            except:
                pass
        self._connections = {}
    
    def _decode_subject(self, subject: str) -> str:
        """Decode email subject"""
        if subject is None:
            return ""
        
        decoded_parts = decode_header(subject)
        decoded_subject = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                decoded_subject += part.decode(encoding or 'utf-8', errors='ignore')
            else:
                decoded_subject += part
        return decoded_subject
    
    def _extract_email_address(self, from_header: str) -> str:
        """Extract email address from From header"""
        if not from_header:
            return ""
        
        # Try to extract email from format "Name <email@domain.com>"
        match = re.search(r'<([^>]+)>', from_header)
        if match:
            return match.group(1).lower()
        
        # Maybe it's just the email
        match = re.search(r'[\w\.-]+@[\w\.-]+', from_header)
        if match:
            return match.group(0).lower()
        
        return from_header.lower()
    
    def _get_sent_email_addresses(self) -> Set[str]:
        """Get all email addresses we've sent to"""
        sent_emails = emails_collection.find(
            {"status": {"$in": [Email.STATUS_SENT, Email.STATUS_OPENED]}},
            {"lead_id": 1}
        )
        
        lead_ids = [e["lead_id"] for e in sent_emails]
        leads = leads_collection.find({"_id": {"$in": lead_ids}}, {"email": 1})
        
        return {lead["email"].lower() for lead in leads if lead.get("email")}
    
    def check_replies(self, 
                      since_days: int = 7,
                      folder: str = "INBOX") -> Dict[str, any]:
        """
        Check all accounts for replies from leads
        
        Now also detects:
        - Auto-replies/Out-of-office messages (logged but not counted as real replies)
        - Unsubscribe requests (adds to do-not-contact list)
        - Permanent auto-replies like "no longer with company" (adds to do-not-contact)
        
        Args:
            since_days: Check emails from the last N days
            folder: IMAP folder to check
        
        Returns:
            Dict with replies found and leads updated
        """
        results = {
            "replies_found": 0,
            "leads_updated": 0,
            "accounts_checked": 0,
            "accounts_failed": 0,
            "auto_replies_found": 0,
            "unsubscribe_requests": 0,
            "do_not_contact_added": 0,
            "details": []
        }
        
        # Get all email addresses we've sent to
        sent_to_addresses = self._get_sent_email_addresses()
        
        if not sent_to_addresses:
            print("   No sent emails found to check replies for")
            return results
        
        print(f"   Checking replies from {len(sent_to_addresses)} leads...")
        
        # Calculate date to search from
        since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
        
        for account in self.accounts:
            mail = self.connect(account)
            if not mail:
                results["accounts_failed"] += 1
                continue
            
            results["accounts_checked"] += 1
            
            try:
                # Select inbox
                mail.select(folder)
                
                # Search for emails since date
                search_criteria = f'(SINCE {since_date})'
                status, messages = mail.search(None, search_criteria)
                
                if status != "OK":
                    continue
                
                email_ids = messages[0].split()
                print(f"   📥 {account['email']}: {len(email_ids)} emails since {since_date}")
                
                for email_id in email_ids:
                    try:
                        # Fetch email
                        status, msg_data = mail.fetch(email_id, "(RFC822)")
                        if status != "OK":
                            continue
                        
                        # Parse email
                        msg = email.message_from_bytes(msg_data[0][1])
                        from_addr = self._extract_email_address(msg.get("From", ""))
                        subject = self._decode_subject(msg.get("Subject", ""))
                        date_str = msg.get("Date", "")
                        body = self._get_email_body(msg)
                        
                        # Check if this is from a lead we emailed
                        if from_addr in sent_to_addresses:
                            # First check if already on do-not-contact list
                            if DoNotContact.is_blocked(from_addr):
                                continue
                            
                            lead = Lead.get_by_email(from_addr)
                            if not lead:
                                continue
                            
                            # Check for auto-reply/OOO
                            is_auto_reply, is_permanent = self._is_auto_reply(subject, body)
                            
                            if is_auto_reply:
                                results["auto_replies_found"] += 1
                                
                                if is_permanent:
                                    # "No longer with company" etc - add to do-not-contact
                                    if DoNotContact.add(from_addr, DoNotContact.REASON_AUTO_REPLY, 
                                                       f"Auto-reply: {subject[:100]}"):
                                        results["do_not_contact_added"] += 1
                                    print(f"   🏢 Permanent OOO from {lead.get('full_name', from_addr)}: {subject[:40]}...")
                                else:
                                    # Temporary OOO - just log it, don't count as reply
                                    print(f"   ✈️  OOO from {lead.get('full_name', from_addr)}: {subject[:40]}...")
                                
                                results["details"].append({
                                    "from": from_addr,
                                    "subject": subject[:50],
                                    "lead_name": lead.get("full_name", "Unknown"),
                                    "received_in": account["email"],
                                    "type": "permanent_ooo" if is_permanent else "auto_reply"
                                })
                                continue  # Don't count as real reply
                            
                            # Check for unsubscribe request
                            if self._is_unsubscribe_request(subject, body):
                                results["unsubscribe_requests"] += 1
                                
                                # Add to do-not-contact list
                                if DoNotContact.add(from_addr, DoNotContact.REASON_UNSUBSCRIBE,
                                                   f"Unsubscribe request: {subject[:100]}"):
                                    results["do_not_contact_added"] += 1
                                
                                print(f"   🚫 Unsubscribe request from {lead.get('full_name', from_addr)}")
                                
                                results["details"].append({
                                    "from": from_addr,
                                    "subject": subject[:50],
                                    "lead_name": lead.get("full_name", "Unknown"),
                                    "received_in": account["email"],
                                    "type": "unsubscribe"
                                })
                                continue  # Don't count as positive reply
                            
                            # This is a real reply!
                            results["replies_found"] += 1
                            
                            # Mark all emails to this lead as replied
                            update_result = emails_collection.update_many(
                                {"lead_id": lead["_id"], "status": {"$ne": Email.STATUS_REPLIED}},
                                {"$set": {
                                    "status": Email.STATUS_REPLIED,
                                    "replied_at": datetime.utcnow()
                                }}
                            )
                            
                            if update_result.modified_count > 0:
                                results["leads_updated"] += 1
                                
                                # Update campaign stats
                                campaign_emails = emails_collection.find({"lead_id": lead["_id"]})
                                for ce in campaign_emails:
                                    Campaign.increment_stat(str(ce["campaign_id"]), "emails_replied")
                            
                            results["details"].append({
                                "from": from_addr,
                                "subject": subject[:50],
                                "lead_name": lead.get("full_name", "Unknown"),
                                "received_in": account["email"],
                                "type": "reply"
                            })
                            
                            print(f"   📬 Reply from {lead.get('full_name', from_addr)}: {subject[:40]}...")
                    
                    except Exception as e:
                        continue
            
            except Exception as e:
                print(f"   Error checking {account['email']}: {e}")
        
        self.disconnect_all()
        return results
    
    def check_bounces(self, since_days: int = 7) -> Dict[str, any]:
        """
        Check for bounced emails and add to do-not-contact list.
        
        Args:
            since_days: Check emails from the last N days
        
        Returns:
            Dict with bounces found
        """
        results = {
            "bounces_found": 0,
            "leads_updated": 0,
            "do_not_contact_added": 0,
            "details": []
        }
        
        bounce_indicators = [
            "mailer-daemon",
            "postmaster",
            "mail delivery",
            "delivery failure",
            "undeliverable",
            "returned mail",
            "delivery status notification"
        ]
        
        # Hard bounce indicators (permanent failures - should add to do-not-contact)
        hard_bounce_indicators = [
            "user unknown",
            "user not found",
            "no such user",
            "mailbox not found",
            "invalid recipient",
            "recipient rejected",
            "address rejected",
            "does not exist",
            "mailbox unavailable",
            "550",  # Common permanent failure code
            "551",
            "552",
            "553",
            "554",
        ]
        
        since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
        
        for account in self.accounts:
            mail = self.connect(account)
            if not mail:
                continue
            
            try:
                mail.select("INBOX")
                status, messages = mail.search(None, f'(SINCE {since_date})')
                
                if status != "OK":
                    continue
                
                for email_id in messages[0].split():
                    try:
                        status, msg_data = mail.fetch(email_id, "(RFC822)")
                        if status != "OK":
                            continue
                        
                        msg = email.message_from_bytes(msg_data[0][1])
                        from_addr = self._extract_email_address(msg.get("From", "")).lower()
                        subject = self._decode_subject(msg.get("Subject", "")).lower()
                        
                        # Check if this looks like a bounce
                        is_bounce = any(ind in from_addr or ind in subject for ind in bounce_indicators)
                        
                        if is_bounce:
                            # Try to extract the original recipient
                            body = self._get_email_body(msg).lower()
                            
                            # Check if it's a hard bounce (permanent failure)
                            full_text = f"{subject} {body}"
                            is_hard_bounce = any(ind in full_text for ind in hard_bounce_indicators)
                            
                            # Find email addresses in the body
                            bounced_emails = re.findall(r'[\w\.-]+@[\w\.-]+', body)
                            
                            for bounced_email in bounced_emails:
                                lead = Lead.get_by_email(bounced_email.lower())
                                if lead:
                                    results["bounces_found"] += 1
                                    
                                    # Mark emails as bounced
                                    emails_collection.update_many(
                                        {"lead_id": lead["_id"]},
                                        {"$set": {"status": Email.STATUS_BOUNCED}}
                                    )
                                    
                                    results["leads_updated"] += 1
                                    
                                    # Add hard bounces to do-not-contact list
                                    if is_hard_bounce:
                                        if DoNotContact.add(bounced_email.lower(), 
                                                          DoNotContact.REASON_HARD_BOUNCE,
                                                          f"Hard bounce: {subject[:100]}"):
                                            results["do_not_contact_added"] += 1
                                    
                                    results["details"].append({
                                        "email": bounced_email,
                                        "lead_name": lead.get("full_name", "Unknown"),
                                        "hard_bounce": is_hard_bounce
                                    })
                                    
                                    bounce_type = "hard" if is_hard_bounce else "soft"
                                    print(f"   📭 Bounce ({bounce_type}): {bounced_email}")
                                    break
                    
                    except Exception as e:
                        continue
            
            except Exception as e:
                print(f"   Error checking bounces in {account['email']}: {e}")
        
        self.disconnect_all()
        return results


# Example usage
if __name__ == "__main__":
    detector = ReplyDetector()
    
    print("Checking for replies (including auto-replies and unsubscribes)...")
    results = detector.check_replies(since_days=7)
    print(f"\nReplies: {results['replies_found']} real replies, {results['leads_updated']} leads updated")
    print(f"Auto-replies: {results['auto_replies_found']}")
    print(f"Unsubscribes: {results['unsubscribe_requests']}")
    print(f"Added to do-not-contact: {results['do_not_contact_added']}")
    
    print("\nChecking for bounces...")
    bounces = detector.check_bounces(since_days=7)
    print(f"Bounces: {bounces['bounces_found']} found, {bounces['do_not_contact_added']} added to do-not-contact")
