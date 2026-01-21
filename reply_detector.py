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
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta
import re
import config
from database import Email, Lead, Campaign, emails_collection, leads_collection


class ReplyDetector:
    """Detect replies in Zoho inbox and update campaign status"""
    
    def __init__(self):
        self.accounts = config.ZOHO_ACCOUNTS
        self.imap_host = "imap.zoho.com"
        self.imap_port = 993
        self._connections: Dict[str, imaplib.IMAP4_SSL] = {}
        self._failed_accounts: Set[str] = set()  # Track accounts that failed to connect
    
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
                        
                        # Check if this is from a lead we emailed
                        if from_addr in sent_to_addresses:
                            results["replies_found"] += 1
                            
                            # Update lead status
                            lead = Lead.get_by_email(from_addr)
                            if lead:
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
                                    "received_in": account["email"]
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
        Check for bounced emails
        
        Args:
            since_days: Check emails from the last N days
        
        Returns:
            Dict with bounces found
        """
        results = {
            "bounces_found": 0,
            "leads_updated": 0,
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
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                            
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
                                    results["details"].append({
                                        "email": bounced_email,
                                        "lead_name": lead.get("full_name", "Unknown")
                                    })
                                    
                                    print(f"   📭 Bounce detected: {bounced_email}")
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
    
    print("Checking for replies...")
    results = detector.check_replies(since_days=7)
    print(f"\nResults: {results['replies_found']} replies, {results['leads_updated']} leads updated")
    
    print("\nChecking for bounces...")
    bounces = detector.check_bounces(since_days=7)
    print(f"Results: {bounces['bounces_found']} bounces found")
