import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, make_msgid
from typing import Optional, List, Dict
import config
import time
import random
from datetime import datetime
import pytz


class SMTP2GOEmailSender:
    """Send emails through multiple SMTP2GO accounts with rotation, warm-up, and limits.

    Drop-in replacement for ZohoEmailSender — identical public API.
    Key differences vs Zoho:
    - SMTP host: mail.smtp2go.com (port 2525 / TLS on 587 / SSL on 465)
    - No Zoho-specific 554 blocking behaviour (SMTP2GO doesn't hard-block accounts)
    - Hard cap is 1 000 per account/day (configurable via SMTP2GO plan; set conservatively below)
    - Reply-To defaults to GMAIL_IMAP_ACCOUNT so all replies go to the shared Gmail inbox
    """

    # SMTP2GO doesn't impose a hard 500-per-day cap the way Zoho does.
    # We keep a safety cap; raise it to match your SMTP2GO plan allowance.
    SMTP2GO_DAILY_HARD_CAP = 1000

    def __init__(self):
        self.smtp_host = config.SMTP2GO_SMTP_HOST
        self.smtp_port = config.SMTP2GO_SMTP_PORT
        self.accounts = config.SMTP2GO_ACCOUNTS
        self.rotation_strategy = config.EMAIL_ROTATION_STRATEGY
        self.emails_per_account = config.EMAILS_PER_ACCOUNT
        # Reply-To: use the shared Gmail inbox so replies are centralised
        self.reply_to = config.REPLY_TO

        # Daily limits
        self.emails_per_day = config.EMAILS_PER_DAY_PER_MAILBOX

        # Warm-up settings
        self.warmup_enabled = config.WARMUP_ENABLED
        self.warmup_limits = {
            1: config.WARMUP_WEEK1_LIMIT,
            2: config.WARMUP_WEEK2_LIMIT,
            3: config.WARMUP_WEEK3_LIMIT,
            4: config.WARMUP_WEEK4_LIMIT,
        }

        # Sending hours (in target timezone, e.g., America/New_York)
        self.target_timezone = pytz.timezone(config.TARGET_TIMEZONE)
        self.send_hour_start = config.SENDING_HOUR_START
        self.send_hour_end = config.SENDING_HOUR_END
        self.send_on_weekends = config.SEND_ON_WEEKENDS

        # Track current account and usage
        self._current_account_index = 0
        self._emails_sent_current_account = 0
        self._connections: Dict[str, smtplib.SMTP] = {}

        # Load blocked accounts from database
        from database import BlockedAccounts
        BlockedAccounts.cleanup_expired()

        if not self.accounts:
            raise ValueError("No SMTP2GO accounts configured. Check SMTP2GO_ACCOUNTS in .env")

        print(f"📧 SMTP2GO: Loaded {len(self.accounts)} account(s): {', '.join(a['email'] for a in self.accounts)}")
        print(f"   ⏰ Sending hours: {self.send_hour_start}:00 - {self.send_hour_end}:00")
        print(f"   🔥 Warm-up: {'enabled' if self.warmup_enabled else 'disabled'}")
        print(f"   📬 Reply-To: {self.reply_to}")

    # ── Daily limit helpers ──────────────────────────────────────────

    def _get_daily_limit_for_account(self, account_email: str) -> int:
        """Get daily send limit considering warmup schedule."""
        if not self.warmup_enabled:
            return min(self.emails_per_day, self.SMTP2GO_DAILY_HARD_CAP)

        from database import SendingStats
        age_days = SendingStats.get_account_age_days(account_email)
        week = (age_days // 7) + 1

        if week >= 4:
            limit = self.warmup_limits[4]
        else:
            limit = self.warmup_limits.get(week, self.warmup_limits[1])

        return min(limit, self.emails_per_day, self.SMTP2GO_DAILY_HARD_CAP)

    def _can_send_now(self) -> tuple[bool, str]:
        """Check business hours / day-of-week in target timezone."""
        now_utc = datetime.now(pytz.UTC)
        now_target = now_utc.astimezone(self.target_timezone)
        current_hour = now_target.hour
        day_of_week = now_target.weekday()
        tz_name = now_target.strftime('%Z')

        if day_of_week >= 5 and not self.send_on_weekends:
            return False, f"⏸️ Weekend in {tz_name} - sending paused"
        if current_hour < self.send_hour_start:
            return False, f"⏸️ Too early ({current_hour}:00 {tz_name}) - starts at {self.send_hour_start}:00"
        if current_hour >= self.send_hour_end:
            return False, f"⏸️ Too late ({current_hour}:00 {tz_name}) - ended at {self.send_hour_end}:00"

        return True, f"✅ Within sending hours ({current_hour}:00 {tz_name})"

    def _can_account_send(self, account_email: str) -> tuple[bool, str, int]:
        """Check if a specific account can send more emails today."""
        from database import SendingStats
        sends_today = SendingStats.get_sends_today(account_email)
        daily_limit = self._get_daily_limit_for_account(account_email)
        remaining = daily_limit - sends_today

        if remaining <= 0:
            return False, f"Daily limit reached ({sends_today}/{daily_limit})", remaining
        return True, f"Can send ({sends_today}/{daily_limit} used)", remaining

    # ── Account rotation ─────────────────────────────────────────────

    def _get_next_account(self, respect_cooldown: bool = True) -> Optional[Dict[str, str]]:
        """Get the next available account based on rotation strategy."""
        from database import BlockedAccounts, AccountCooldown

        available_accounts = []
        blocked_count = 0
        cooldown_count = 0
        limit_count = 0

        for account in self.accounts:
            email = account["email"]

            if BlockedAccounts.is_blocked(email):
                blocked_until = BlockedAccounts.get_blocked_until(email)
                if blocked_until:
                    print(f"   ⏳ {email} blocked until {blocked_until.strftime('%Y-%m-%d %H:%M')} UTC")
                blocked_count += 1
                continue

            can_send, reason, remaining = self._can_account_send(email)
            if not can_send:
                limit_count += 1
                continue

            if respect_cooldown and not AccountCooldown.is_available(email):
                cooldown_count += 1
                continue

            available_accounts.append((account, remaining))

        if not available_accounts:
            if blocked_count == len(self.accounts):
                print("   ⚠️ All SMTP2GO accounts are blocked!")
            elif limit_count == len(self.accounts) - blocked_count:
                print("   🛑 All accounts have reached their daily sending limit!")
            return None

        if len(available_accounts) == 1:
            return available_accounts[0][0]

        if self.rotation_strategy == "random":
            return random.choice(available_accounts)[0]

        # Round-robin
        for account, remaining in available_accounts:
            return account

        return available_accounts[0][0] if available_accounts else None

    def get_wait_time_for_next_account(self) -> int:
        """Seconds until the next account is available. -1 = none available today."""
        from database import BlockedAccounts, AccountCooldown

        eligible_emails = []
        for a in self.accounts:
            email = a["email"]
            if BlockedAccounts.is_blocked(email):
                continue
            can_send, _, _ = self._can_account_send(email)
            if can_send:
                eligible_emails.append(email)

        if not eligible_emails:
            return -1

        _, seconds = AccountCooldown.get_soonest_available(eligible_emails)
        return seconds

    def _record_send_cooldown(self, account_email: str):
        """Start cooldown timer for this account after a send."""
        from database import AccountCooldown
        cooldown_minutes = random.randint(config.MIN_DELAY_BETWEEN_EMAILS, config.MAX_DELAY_BETWEEN_EMAILS)
        AccountCooldown.record_send(account_email, cooldown_minutes)

    def _mark_account_blocked(self, email: str, error_message: str = None):
        """Mark account as temporarily blocked (persistent in database)."""
        from database import BlockedAccounts
        BlockedAccounts.mark_blocked(email, error_message)
        self._emails_sent_current_account = self.emails_per_account

    # ── SMTP connection ──────────────────────────────────────────────

    def _get_connection(self, account: Dict[str, str]) -> Optional[smtplib.SMTP]:
        """Create a fresh SMTP connection for an account.

        Always creates a new connection — LLM-based generation takes 30-40s
        between sends, which can cause idle connections to be dropped.
        """
        email = account["email"]

        # Close any stale connection first
        if email in self._connections:
            try:
                self._connections[email].quit()
            except Exception:
                pass
            del self._connections[email]

        import time as _time
        _start = _time.time()
        try:
            print(f"   📡 [{email}] Connecting to {self.smtp_host}:{self.smtp_port}...")
            server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=60)
            elapsed = _time.time() - _start
            print(f"   📡 [{email}] TCP connected ({elapsed:.1f}s), starting TLS...")
            server.starttls()
            elapsed = _time.time() - _start
            print(f"   📡 [{email}] TLS ready ({elapsed:.1f}s), logging in...")
            server.login(email, account["password"])
            elapsed = _time.time() - _start
            print(f"   ✅ [{email}] Connected and authenticated ({elapsed:.1f}s)")
            return server
        except (TimeoutError, OSError) as e:
            elapsed = _time.time() - _start
            print(f"   ⏱️  [{email}] SMTP timeout after {elapsed:.1f}s: {e}")
            return None
        except Exception as e:
            elapsed = _time.time() - _start
            print(f"   ❌ [{email}] SMTP failed after {elapsed:.1f}s: {e}")
            return None

    def disconnect_all(self):
        """Close all open SMTP connections."""
        for email, server in self._connections.items():
            try:
                server.quit()
            except Exception:
                pass
        self._connections = {}

    # ── Public API ───────────────────────────────────────────────────

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
                   bypass_time_check: bool = False,
                   in_reply_to: str = None,
                   references: List[str] = None) -> dict:
        """
        Send an email via SMTP2GO (auto-rotates accounts).

        Identical public signature to ZohoEmailSender.send_email().

        Returns:
            Dict with 'success', 'message'/'error', 'from_email', 'message_id',
            and optionally 'skip_reason' / 'wait_seconds'.
        """
        from database import SendingStats, AccountCooldown

        # Business hours check
        if not bypass_time_check:
            can_send_now, time_reason = self._can_send_now()
            if not can_send_now:
                return {"success": False, "error": time_reason, "from_email": None, "skip_reason": "time"}

        # Handle a specific requested account
        if from_account:
            from database import BlockedAccounts
            account_email = from_account["email"]

            if BlockedAccounts.is_blocked(account_email):
                print(f"  ⚠️  Original sender {account_email} is blocked, using rotation")
                from_account = None
            else:
                can_send, reason, remaining = self._can_account_send(account_email)
                if not can_send:
                    print(f"  ⚠️  Original sender {account_email} at limit ({reason}), using rotation")
                    from_account = None
                elif not AccountCooldown.is_available(account_email):
                    wait_time = AccountCooldown.get_seconds_until_available(account_email)
                    if wait_time <= 60:
                        import time
                        time.sleep(wait_time + 1)
                    else:
                        print(f"  ⚠️  Original sender {account_email} in cooldown, using rotation")
                        from_account = None

        account = from_account or self._get_next_account(respect_cooldown=True)

        if account is None:
            from database import BlockedAccounts
            blocked_count = sum(1 for a in self.accounts if BlockedAccounts.is_blocked(a["email"]))

            if blocked_count == len(self.accounts):
                return {
                    "success": False,
                    "error": "All accounts are blocked (cooldown active)",
                    "from_email": None,
                    "skip_reason": "blocked",
                }

            accounts_at_limit = 0
            accounts_in_cooldown = 0

            for a in self.accounts:
                email = a["email"]
                if BlockedAccounts.is_blocked(email):
                    continue
                can_send, _, _ = self._can_account_send(email)
                if not can_send:
                    accounts_at_limit += 1
                elif not AccountCooldown.is_available(email):
                    accounts_in_cooldown += 1

            if accounts_at_limit == len(self.accounts) - blocked_count:
                return {
                    "success": False,
                    "error": "All accounts have reached their daily sending limit",
                    "from_email": None,
                    "skip_reason": "limit",
                }

            if accounts_in_cooldown > 0:
                wait_seconds = self.get_wait_time_for_next_account()
                return {
                    "success": False,
                    "error": f"All accounts in cooldown, wait {wait_seconds}s",
                    "from_email": None,
                    "skip_reason": "cooldown",
                    "wait_seconds": wait_seconds,
                }

            return {
                "success": False,
                "error": "No available account",
                "from_email": None,
                "skip_reason": "unavailable",
            }

        from_email = account["email"]
        from_name = account["sender_name"]
        self._emails_sent_current_account += 1

        try:
            if html_body:
                msg = MIMEMultipart('alternative')
                msg.attach(MIMEText(body, 'plain'))
                msg.attach(MIMEText(html_body, 'html'))
            else:
                msg = MIMEText(body, 'plain')

            domain = from_email.split('@')[1] if '@' in from_email else 'primestrides.com'
            message_id = make_msgid(domain=domain)
            msg['Message-ID'] = message_id

            if in_reply_to:
                msg['In-Reply-To'] = in_reply_to
                if references:
                    msg['References'] = ' '.join(references)
                else:
                    msg['References'] = in_reply_to

            msg['Subject'] = subject
            msg['From'] = formataddr((from_name, from_email))

            if to_name:
                msg['To'] = formataddr((to_name, to_email))
            else:
                msg['To'] = to_email

            # Always set Reply-To so leads reply to the Gmail IMAP inbox
            msg['Reply-To'] = reply_to or self.reply_to or from_email

            if cc:
                msg['Cc'] = ', '.join(cc)

            recipients = [to_email]
            if cc:
                recipients.extend(cc)
            if bcc:
                recipients.extend(bcc)

            import time as _time
            print(f"   📤 Preparing to send to {to_email} via {from_email} (SMTP2GO)...")
            server = self._get_connection(account)
            if not server:
                return {"success": False, "error": f"Failed to connect as {from_email}", "from_email": from_email}

            _send_start = _time.time()
            server.sock.settimeout(60)
            print(f"   📤 Sending email to {to_email}...")
            server.sendmail(from_email, recipients, msg.as_string())
            _send_elapsed = _time.time() - _send_start
            print(f"   📤 Email transmitted ({_send_elapsed:.1f}s), closing connection...")

            try:
                server.quit()
            except Exception:
                pass
            print(f"   📤 Connection closed cleanly")

            SendingStats.increment_send(from_email)
            self._record_send_cooldown(from_email)

            sends_today = SendingStats.get_sends_today(from_email)
            daily_limit = self._get_daily_limit_for_account(from_email)

            print(f"   ✉️  Sent to {to_email} (from {from_email}) [{sends_today}/{daily_limit} today]")
            return {
                "success": True,
                "message": f"Email sent to {to_email}",
                "from_email": from_email,
                "message_id": message_id,
            }

        except smtplib.SMTPException as e:
            error_msg = f"SMTP error sending to {to_email}: {str(e)}"
            print(f"   ❌ {error_msg}")

            # SMTP2GO uses 421/450/550 for temporary/permanent failures.
            # Map explicit permanent failures to the same blocked-account logic
            # so the rest of the system can gracefully rotate away.
            error_code = getattr(e, 'smtp_code', None) or (
                e.args[0] if e.args and isinstance(e.args[0], int) else None
            )
            # Treat 550 / 554 as a hard account-level block (misconfig or quota)
            if error_code in (550, 554) or any(str(c) in str(e) for c in ('550', '554')):
                self._mark_account_blocked(from_email, str(e))
                return {
                    "success": False,
                    "error": error_msg,
                    "from_email": from_email,
                    "recipient_invalid": True,
                    "error_code": error_code,
                }

            try:
                server.quit()
            except Exception:
                pass

            return {"success": False, "error": error_msg, "from_email": from_email}

        except Exception as e:
            error_msg = f"Error sending to {to_email}: {str(e)}"
            print(f"   ❌ {error_msg}")
            try:
                server.quit()
            except Exception:
                pass
            return {"success": False, "error": error_msg, "from_email": from_email}

    def send_bulk_emails(self,
                         emails: List[dict],
                         delay_seconds: float = 2.0) -> dict:
        """Send multiple emails with rate limiting and account rotation."""
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
                    html_body=email_data.get("html_body"),
                )

                if result["success"]:
                    results["sent"] += 1
                    from_email = result.get("from_email", "unknown")
                    results["accounts_used"][from_email] = results["accounts_used"].get(from_email, 0) + 1
                else:
                    results["failed"] += 1

                results["results"].append({"to_email": email_data["to_email"], **result})

                if i < len(emails) - 1:
                    time.sleep(delay_seconds)
        finally:
            self.disconnect_all()

        return results

    def send_test_email(self, to_email: str) -> dict:
        """Send test emails from all configured SMTP2GO accounts."""
        results = []

        for account in self.accounts:
            subject = f"Test Email from {account['email']} (via SMTP2GO)"
            body = f"""Hi,

This is a test email from your cold email automation system using SMTP2GO.

Sent from: {account['email']}
Sender name: {account['sender_name']}
SMTP host: {self.smtp_host}:{self.smtp_port}

If you received this, SMTP2GO is configured correctly!

Best,
Your Automation System"""

            result = self.send_email(
                to_email=to_email,
                subject=subject,
                body=body,
                from_account=account,
                bypass_time_check=True,
            )
            results.append(result)

        self.disconnect_all()

        success_count = sum(1 for r in results if r["success"])
        return {
            "success": success_count == len(self.accounts),
            "message": f"Sent {success_count}/{len(self.accounts)} test emails via SMTP2GO",
            "details": results,
        }

    def list_accounts(self):
        """Print configured SMTP2GO accounts with daily limits and usage."""
        from database import SendingStats

        print(f"\n📧 SMTP2GO Accounts ({len(self.accounts)}):\n")

        total_available = 0
        for i, account in enumerate(self.accounts, 1):
            email = account["email"]
            sends_today = SendingStats.get_sends_today(email)
            daily_limit = self._get_daily_limit_for_account(email)
            remaining = max(0, daily_limit - sends_today)
            total_available += remaining
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
        """Get current sending status for all accounts."""
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

            if not blocked:
                total_remaining += remaining

            accounts_status.append({
                "email": email,
                "sends_today": sends_today,
                "daily_limit": daily_limit,
                "remaining": remaining,
                "age_days": age_days,
                "week": (age_days // 7) + 1,
                "blocked": blocked,
            })

        return {
            "can_send_now": can_send_now,
            "time_reason": time_reason,
            "total_remaining": total_remaining,
            "warmup_enabled": self.warmup_enabled,
            "accounts": accounts_status,
        }

    def connect(self):
        """Try to connect to at least one available account. Returns True on success."""
        from database import BlockedAccounts

        for account in self.accounts:
            email = account["email"]

            if BlockedAccounts.is_blocked(email):
                continue

            can_send, _, _ = self._can_account_send(email)
            if not can_send:
                continue

            connection = self._get_connection(account)
            if connection is not None:
                return True

        print("   ⚠️  No SMTP2GO accounts available or all failed to connect")
        return False

    def disconnect(self):
        """Alias for disconnect_all."""
        self.disconnect_all()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect_all()


# ── Backward-compatibility alias ─────────────────────────────────────
# Code that imports ZohoEmailSender from zoho_sender.py can be updated to
# import from here using the alias, or campaign_manager / main.py can import
# SMTP2GOEmailSender as EmailSender directly.
ZohoEmailSender = SMTP2GOEmailSender


def text_to_html(text: str) -> str:
    """Convert plain text email to basic HTML. Identical to zoho_sender.text_to_html."""
    html = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    html = html.replace('\n\n', '</p><p>').replace('\n', '<br>')
    return f"""<!DOCTYPE html>
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


if __name__ == "__main__":
    sender = SMTP2GOEmailSender()
    sender.list_accounts()
