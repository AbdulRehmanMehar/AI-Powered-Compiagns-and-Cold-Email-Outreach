import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import Optional, List, Dict
import config
import time
import random
from datetime import datetime
import pytz


class ZohoEmailSender:
    """Send emails through multiple Zoho SMTP accounts with rotation, warm-up, and limits"""
    
    def __init__(self):
        self.smtp_host = config.ZOHO_SMTP_HOST
        self.smtp_port = config.ZOHO_SMTP_PORT
        self.accounts = config.ZOHO_ACCOUNTS
        self.rotation_strategy = config.EMAIL_ROTATION_STRATEGY
        self.emails_per_account = config.EMAILS_PER_ACCOUNT
        self.reply_to = config.REPLY_TO
        
        # Daily limits
        self.emails_per_day = config.EMAILS_PER_DAY_PER_MAILBOX
        
        # Warm-up settings
        self.warmup_enabled = config.WARMUP_ENABLED
        self.warmup_limits = {
            1: config.WARMUP_WEEK1_LIMIT,  # Week 1: very low
            2: config.WARMUP_WEEK2_LIMIT,  # Week 2: increasing
            3: config.WARMUP_WEEK3_LIMIT,  # Week 3: ramping up
            4: config.WARMUP_WEEK4_LIMIT,  # Week 4+: normal
        }
        
        # Sending hours (in target timezone, e.g., America/New_York)
        self.target_timezone = pytz.timezone(config.TARGET_TIMEZONE)
        self.send_hour_start = config.SENDING_HOUR_START
        self.send_hour_end = config.SENDING_HOUR_END
        self.send_on_weekends = config.SEND_ON_WEEKENDS
        
        # Track current account and usage
        self._current_account_index = 0
        self._emails_sent_current_account = 0
        self._connections: Dict[str, smtplib.SMTP] = {}  # email -> connection
        
        # Load blocked accounts from database (persistent across restarts)
        from database import BlockedAccounts
        BlockedAccounts.cleanup_expired()  # Clear expired blocks on startup
        
        if not self.accounts:
            raise ValueError("No Zoho email accounts configured. Check ZOHO_EMAILS in .env")
        
        print(f"📧 Loaded {len(self.accounts)} email account(s): {', '.join(a['email'] for a in self.accounts)}")
        print(f"   ⏰ Sending hours: {self.send_hour_start}:00 - {self.send_hour_end}:00")
        print(f"   🔥 Warm-up: {'enabled' if self.warmup_enabled else 'disabled'}")
    
    def _get_daily_limit_for_account(self, account_email: str) -> int:
        """Get the daily send limit for an account based on its age (warm-up)"""
        if not self.warmup_enabled:
            return self.emails_per_day
        
        from database import SendingStats
        age_days = SendingStats.get_account_age_days(account_email)
        
        # Determine which week we're in
        week = (age_days // 7) + 1
        
        if week >= 4:
            limit = self.warmup_limits[4]
        else:
            limit = self.warmup_limits.get(week, self.warmup_limits[1])
        
        return min(limit, self.emails_per_day)
    
    def _can_send_now(self) -> tuple[bool, str]:
        """Check if we can send emails right now (time of day, day of week in target timezone)"""
        # Get current time in target timezone (e.g., America/New_York)
        now_utc = datetime.now(pytz.UTC)
        now_target = now_utc.astimezone(self.target_timezone)
        current_hour = now_target.hour
        day_of_week = now_target.weekday()  # 0=Monday, 6=Sunday
        tz_name = now_target.strftime('%Z')  # EST or EDT
        
        # Check weekend
        if day_of_week >= 5 and not self.send_on_weekends:
            return False, f"⏸️ Weekend in {tz_name} - sending paused"
        
        # Check business hours
        if current_hour < self.send_hour_start:
            return False, f"⏸️ Too early ({current_hour}:00 {tz_name}) - starts at {self.send_hour_start}:00"
        if current_hour >= self.send_hour_end:
            return False, f"⏸️ Too late ({current_hour}:00 {tz_name}) - ended at {self.send_hour_end}:00"
        
        return True, f"✅ Within sending hours ({current_hour}:00 {tz_name})"
    
    def _can_account_send(self, account_email: str) -> tuple[bool, str, int]:
        """Check if a specific account can send more emails today"""
        from database import SendingStats
        
        sends_today = SendingStats.get_sends_today(account_email)
        daily_limit = self._get_daily_limit_for_account(account_email)
        remaining = daily_limit - sends_today
        
        if remaining <= 0:
            return False, f"Daily limit reached ({sends_today}/{daily_limit})", remaining
        
        return True, f"Can send ({sends_today}/{daily_limit} used)", remaining
    
    def _get_next_account(self) -> Optional[Dict[str, str]]:
        """Get the next account to use based on rotation strategy and limits"""
        from database import BlockedAccounts
        
        # Filter out blocked accounts AND accounts at daily limit
        available_accounts = []
        blocked_count = 0
        
        for account in self.accounts:
            email = account["email"]
            
            # Skip blocked accounts (persistent in database)
            if BlockedAccounts.is_blocked(email):
                blocked_until = BlockedAccounts.get_blocked_until(email)
                if blocked_until:
                    print(f"   ⏳ {email} blocked until {blocked_until.strftime('%Y-%m-%d %H:%M')} UTC")
                blocked_count += 1
                continue
            
            # Check daily limit
            can_send, reason, remaining = self._can_account_send(email)
            if can_send:
                available_accounts.append((account, remaining))
        
        if not available_accounts:
            # Check if all accounts are blocked vs at limit
            if blocked_count == len(self.accounts):
                print("   ⚠️ All accounts are blocked by Zoho! Waiting for cooldown to expire...")
                return None
            else:
                print("   🛑 All accounts have reached their daily sending limit!")
                return None
        
        if len(available_accounts) == 1:
            return available_accounts[0][0]
        
        if self.rotation_strategy == "random":
            return random.choice(available_accounts)[0]
        
        # Round-robin with emails_per_account limit
        if self._emails_sent_current_account >= self.emails_per_account:
            self._current_account_index = (self._current_account_index + 1) % len(self.accounts)
            self._emails_sent_current_account = 0
        
        # Find next available account in round-robin
        attempts = 0
        while attempts < len(self.accounts):
            account = self.accounts[self._current_account_index]
            email = account["email"]
            
            if not BlockedAccounts.is_blocked(email):
                can_send, _, _ = self._can_account_send(email)
                if can_send:
                    return account
            
            self._current_account_index = (self._current_account_index + 1) % len(self.accounts)
            self._emails_sent_current_account = 0
            attempts += 1
        
        return None
    
    def _mark_account_blocked(self, email: str, error_message: str = None):
        """Mark an account as blocked (554 error from Zoho) - persisted to database"""
        from database import BlockedAccounts
        BlockedAccounts.mark_blocked(email, error_message)
        # Force rotation to next account
        self._emails_sent_current_account = self.emails_per_account
    
    def _get_connection(self, account: Dict[str, str]) -> Optional[smtplib.SMTP]:
        """Get or create SMTP connection for an account"""
        email = account["email"]
        
        # Check if we have an existing connection
        if email in self._connections:
            try:
                # Test if connection is still alive
                self._connections[email].noop()
                return self._connections[email]
            except:
                # Connection dead, remove it
                try:
                    self._connections[email].quit()
                except:
                    pass
                del self._connections[email]
        
        # Create new connection
        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()
            server.login(email, account["password"])
            self._connections[email] = server
            print(f"   Connected to Zoho as {email}")
            return server
        except Exception as e:
            print(f"   Failed to connect as {email}: {e}")
            return None
    
    def disconnect_all(self):
        """Close all SMTP connections"""
        for email, server in self._connections.items():
            try:
                server.quit()
            except:
                pass
        self._connections = {}
    
    def send_email(self,
                   to_email: str,
                   subject: str,
                   body: str,
                   to_name: str = None,
                   html_body: str = None,
                   cc: List[str] = None,
                   bcc: List[str] = None,
                   reply_to: str = None,
                   from_account: Dict[str, str] = None,
                   bypass_time_check: bool = False) -> dict:
        """
        Send an email through Zoho (auto-rotates accounts)
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Plain text email body
            to_name: Recipient name (optional)
            html_body: HTML version of email body (optional)
            cc: List of CC addresses (optional)
            bcc: List of BCC addresses (optional)
            reply_to: Reply-to address (optional)
            from_account: Specific account to use (optional, auto-selects if not provided)
            bypass_time_check: Skip business hours check (for testing)
        
        Returns:
            Dict with 'success', 'message'/'error', 'from_email', and optionally 'skip_reason'
        """
        from database import SendingStats
        
        # Check if within sending hours
        if not bypass_time_check:
            can_send_now, time_reason = self._can_send_now()
            if not can_send_now:
                return {"success": False, "error": time_reason, "from_email": None, "skip_reason": "time"}
        
        # Get account to use (checks daily limits internally)
        account = from_account or self._get_next_account()
        
        if account is None:
            # Differentiate between "all blocked" vs "daily limit" for clearer ops/debugging
            from database import BlockedAccounts
            blocked_count = sum(1 for a in self.accounts if BlockedAccounts.is_blocked(a["email"]))

            if blocked_count == len(self.accounts):
                return {
                    "success": False,
                    "error": "All accounts are blocked by Zoho (cooldown active)",
                    "from_email": None,
                    "skip_reason": "blocked",
                }

            # If at least one account is unblocked, then it's most likely daily limits
            any_unblocked_can_send = False
            for a in self.accounts:
                email = a["email"]
                if BlockedAccounts.is_blocked(email):
                    continue
                can_send, _, _ = self._can_account_send(email)
                if can_send:
                    any_unblocked_can_send = True
                    break

            return {
                "success": False,
                "error": "All accounts have reached their daily sending limit" if not any_unblocked_can_send else "No available account",
                "from_email": None,
                "skip_reason": "limit" if not any_unblocked_can_send else "unavailable",
            }
        
        from_email = account["email"]
        from_name = account["sender_name"]
        
        # Track usage for rotation BEFORE attempting (so we rotate on attempts, not just successes)
        self._emails_sent_current_account += 1
        
        try:
            # Create message
            if html_body:
                msg = MIMEMultipart('alternative')
                msg.attach(MIMEText(body, 'plain'))
                msg.attach(MIMEText(html_body, 'html'))
            else:
                msg = MIMEText(body, 'plain')
            
            # Set headers
            msg['Subject'] = subject
            msg['From'] = formataddr((from_name, from_email))
            
            if to_name:
                msg['To'] = formataddr((to_name, to_email))
            else:
                msg['To'] = to_email
            
            msg['Reply-To'] = reply_to or self.reply_to or from_email
            
            if cc:
                msg['Cc'] = ', '.join(cc)
            
            # Build recipient list
            recipients = [to_email]
            if cc:
                recipients.extend(cc)
            if bcc:
                recipients.extend(bcc)
            
            # Get connection
            server = self._get_connection(account)
            if not server:
                return {"success": False, "error": f"Failed to connect as {from_email}", "from_email": from_email}
            
            # Send email
            server.sendmail(from_email, recipients, msg.as_string())
            
            # Track the send for daily limits
            SendingStats.increment_send(from_email)
            
            # Get updated stats for display
            sends_today = SendingStats.get_sends_today(from_email)
            daily_limit = self._get_daily_limit_for_account(from_email)
            
            print(f"   ✉️  Sent to {to_email} (from {from_email}) [{sends_today}/{daily_limit} today]")
            return {"success": True, "message": f"Email sent to {to_email}", "from_email": from_email}
            
        except smtplib.SMTPException as e:
            error_msg = f"SMTP error sending to {to_email}: {str(e)}"
            print(f"   ❌ {error_msg}")
            
            # Check if account is blocked by Zoho (554 error)
            error_code = getattr(e, 'smtp_code', None) or (e.args[0] if e.args and isinstance(e.args[0], int) else None)
            if error_code == 554 or '554' in str(e):
                self._mark_account_blocked(from_email, str(e))
            
            # Remove dead connection
            if from_email in self._connections:
                del self._connections[from_email]
            
            return {"success": False, "error": error_msg, "from_email": from_email}
        except Exception as e:
            error_msg = f"Error sending to {to_email}: {str(e)}"
            print(f"   ❌ {error_msg}")
            return {"success": False, "error": error_msg, "from_email": from_email}
    
    def send_bulk_emails(self,
                         emails: List[dict],
                         delay_seconds: float = 2.0) -> dict:
        """
        Send multiple emails with rate limiting and account rotation
        
        Args:
            emails: List of email dicts with keys:
                - to_email (required)
                - subject (required)
                - body (required)
                - to_name (optional)
                - html_body (optional)
            delay_seconds: Delay between emails
        
        Returns:
            Dict with 'sent', 'failed', 'results', and 'accounts_used'
        """
        
        results = {
            "sent": 0,
            "failed": 0,
            "results": [],
            "accounts_used": {}
        }
        
        try:
            for i, email_data in enumerate(emails):
                result = self.send_email(
                    to_email=email_data["to_email"],
                    subject=email_data["subject"],
                    body=email_data["body"],
                    to_name=email_data.get("to_name"),
                    html_body=email_data.get("html_body")
                )
                
                if result["success"]:
                    results["sent"] += 1
                    # Track which account sent what
                    from_email = result.get("from_email", "unknown")
                    results["accounts_used"][from_email] = results["accounts_used"].get(from_email, 0) + 1
                else:
                    results["failed"] += 1
                
                results["results"].append({
                    "to_email": email_data["to_email"],
                    **result
                })
                
                # Rate limiting delay (except for last email)
                if i < len(emails) - 1:
                    time.sleep(delay_seconds)
        finally:
            self.disconnect_all()
        
        return results
    
    def send_test_email(self, to_email: str) -> dict:
        """Send test emails from all configured accounts"""
        
        results = []
        
        for account in self.accounts:
            subject = f"Test Email from {account['email']}"
            body = f"""Hi,

This is a test email from your cold email automation system.

Sent from: {account['email']}
Sender name: {account['sender_name']}

If you received this email, this account is configured correctly!

Best,
Your Automation System"""
            
            result = self.send_email(
                to_email=to_email,
                subject=subject,
                body=body,
                from_account=account
            )
            results.append(result)
        
        self.disconnect_all()
        
        # Return summary
        success_count = sum(1 for r in results if r["success"])
        return {
            "success": success_count == len(self.accounts),
            "message": f"Sent {success_count}/{len(self.accounts)} test emails",
            "details": results
        }
    
    def list_accounts(self):
        """Print configured accounts with their daily limits and usage"""
        from database import SendingStats
        
        print(f"\n📧 Configured Email Accounts ({len(self.accounts)}):\n")
        
        total_available = 0
        for i, account in enumerate(self.accounts, 1):
            email = account["email"]
            sends_today = SendingStats.get_sends_today(email)
            daily_limit = self._get_daily_limit_for_account(email)
            remaining = max(0, daily_limit - sends_today)
            total_available += remaining
            
            # Get account age for warm-up display
            age_days = SendingStats.get_account_age_days(email)
            week = (age_days // 7) + 1
            
            from database import BlockedAccounts
            status = "🔴 blocked" if BlockedAccounts.is_blocked(email) else "🟢 active"
            warmup_info = f"(week {week})" if self.warmup_enabled else ""
            
            print(f"   {i}. {email} ({account['sender_name']})")
            print(f"      {status} | {sends_today}/{daily_limit} sent today | {remaining} remaining {warmup_info}")
        
        print(f"\n   📊 Total remaining capacity today: {total_available} emails")
        print(f"   ⚙️  Rotation: {self.rotation_strategy}, {self.emails_per_account} per batch")
        print(f"   ⏰ Hours: {self.send_hour_start}:00-{self.send_hour_end}:00")
        print(f"   🔥 Warm-up: {'enabled' if self.warmup_enabled else 'disabled'}")
    
    def get_sending_status(self) -> dict:
        """Get current sending status for all accounts"""
        from database import SendingStats
        
        can_send_now, time_reason = self._can_send_now()
        
        accounts_status = []
        total_remaining = 0
        
        for account in self.accounts:
            email = account["email"]
            sends_today = SendingStats.get_sends_today(email)
            daily_limit = self._get_daily_limit_for_account(email)
            remaining = max(0, daily_limit - sends_today)
            age_days = SendingStats.get_account_age_days(email)
            
            from database import BlockedAccounts
            blocked = BlockedAccounts.is_blocked(email)

            # Only count capacity from accounts we can actually use right now
            if not blocked:
                total_remaining += remaining

            accounts_status.append({
                "email": email,
                "sends_today": sends_today,
                "daily_limit": daily_limit,
                "remaining": remaining,
                "age_days": age_days,
                "week": (age_days // 7) + 1,
                "blocked": blocked
            })
        
        return {
            "can_send_now": can_send_now,
            "time_reason": time_reason,
            "total_remaining": total_remaining,
            "warmup_enabled": self.warmup_enabled,
            "accounts": accounts_status
        }
    
    def connect(self):
        """Legacy method - connects first account for backward compatibility"""
        if self.accounts:
            return self._get_connection(self.accounts[0]) is not None
        return False
    
    def disconnect(self):
        """Legacy method - disconnects all"""
        self.disconnect_all()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect_all()


def text_to_html(text: str) -> str:
    """Convert plain text email to basic HTML"""
    
    # Escape HTML characters
    html = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # Convert newlines to <br>
    html = html.replace('\n\n', '</p><p>').replace('\n', '<br>')
    
    # Wrap in basic HTML structure
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333; }}
        p {{ margin: 0 0 1em 0; }}
    </style>
</head>
<body>
    <p>{html}</p>
</body>
</html>"""
    
    return html


# Example usage
if __name__ == "__main__":
    sender = ZohoEmailSender()
    
    # List accounts
    sender.list_accounts()
    
    # Test all accounts
    # result = sender.send_test_email("your-test-email@example.com")
    # print(f"Test result: {result}")
