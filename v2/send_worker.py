"""
Async Send Worker — Pulls ready-to-send drafts and delivers via aiosmtplib.

Produces identical email format to zoho_sender.py:
- Same MIMEMultipart structure
- Same Message-ID format (make_msgid with sender domain)
- Same In-Reply-To / References threading headers
- Same text_to_html conversion
- Same error handling (554 → block account)

Key design:
- One SMTP connection per account at a time (enforced by AccountPool locks)
- Fresh connection per send (Zoho drops idle connections)
- Records send stats + cooldown after each send
- Graceful shutdown: finishes in-flight send, releases claimed drafts
"""

import asyncio
import logging
import signal
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiosmtplib

import config
from database import (
    Campaign,
    Email,
    SendingStats,
    emails_collection,
)
from v2.account_pool import AccountPool
from v2.pre_generator import EmailDraft, DraftStatus, email_drafts_collection
from v2.human_behavior import (
    is_holiday,
    should_skip_send,
    get_reply_pause_seconds,
)

logger = logging.getLogger("coldemails.send_worker")


def text_to_html(text: str) -> str:
    """
    Convert plain text email to basic HTML.
    Identical to zoho_sender.text_to_html for consistency.
    """
    html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = html.replace("\n\n", "</p><p>").replace("\n", "<br>")
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


class SendWorker:
    """
    Async worker that continuously processes ready-to-send drafts.

    Lifecycle:
        worker = SendWorker(pool)
        await worker.run()   # runs until shutdown signal
    """

    def __init__(self, account_pool: AccountPool):
        self.pool = account_pool
        self.smtp_host = config.ZOHO_SMTP_HOST
        self.smtp_port = config.ZOHO_SMTP_PORT
        self._shutdown = asyncio.Event()
        self._in_flight_draft_id: Optional[str] = None

    async def run(self):
        """
        Main loop: pull drafts, send them, repeat.
        Exits cleanly when _shutdown is set.
        """
        logger.info("send_worker_started")

        while not self._shutdown.is_set():
            try:
                # Check if it's a holiday
                is_hol, hol_name = is_holiday()
                if is_hol:
                    logger.info("holiday_skip", extra={"holiday": hol_name})
                    await asyncio.sleep(3600)  # check again in an hour
                    continue

                # Occasionally skip a cycle (human-like break)
                if should_skip_send(skip_probability=0.03):
                    logger.debug("human_break_skip")
                    await asyncio.sleep(120)
                    continue

                # Clean up stale claims (from previous crashes)
                EmailDraft.cleanup_stale_claimed(timeout_minutes=30)

                # Monitor draft queue — trigger pre-gen if running low
                await self._check_and_refill_queue()

                # Try to send one draft
                sent = await self._process_one_draft()

                if not sent:
                    # Nothing to send or no accounts available — wait
                    wait_secs = self.pool.get_wait_time()
                    if wait_secs < 0:
                        # All accounts exhausted for today
                        logger.info("all_accounts_exhausted_today")
                        await asyncio.sleep(300)  # check every 5 min
                    elif wait_secs == 0:
                        # No drafts ready — check again shortly
                        await asyncio.sleep(30)
                    else:
                        # Accounts in cooldown — wait for soonest
                        logger.debug(f"waiting {wait_secs}s for account cooldown")
                        await asyncio.sleep(min(wait_secs + 5, 300))

            except asyncio.CancelledError:
                logger.info("send_worker_cancelled")
                break
            except Exception as e:
                logger.error(f"send_worker_error: {e}", exc_info=True)
                await asyncio.sleep(60)

        # Shutdown: release any in-flight draft
        if self._in_flight_draft_id:
            EmailDraft.release_claimed(self._in_flight_draft_id)
            logger.info(f"Released in-flight draft {self._in_flight_draft_id}")

        logger.info("send_worker_stopped")

    async def _check_and_refill_queue(self):
        """
        Monitor draft queue and trigger pre-generation if running low.
        This ensures continuous draft availability during send window.
        """
        # Check queue size
        ready_count = EmailDraft.get_stats().get("ready_to_send", 0)
        
        # Threshold: if < 50 ready drafts, trigger pre-gen
        # This gives us buffer time to generate more before queue empties
        if ready_count < 50:
            # Only trigger if not already running (check last trigger time)
            if not hasattr(self, '_last_pregen_trigger'):
                self._last_pregen_trigger = datetime.utcnow() - timedelta(hours=1)
            
            time_since_last = (datetime.utcnow() - self._last_pregen_trigger).total_seconds()
            
            # Throttle: only trigger once per 15 minutes
            if time_since_last > 900:
                logger.warning(
                    "draft_queue_low_triggering_pregen",
                    extra={"ready_count": ready_count, "threshold": 50}
                )
                
                # Trigger pre-generation in background (don't block send worker)
                try:
                    from v2.pre_generator import PreGenerator
                    from database import Campaign
                    
                    asyncio.create_task(self._run_background_pregen())
                    self._last_pregen_trigger = datetime.utcnow()
                    
                except Exception as e:
                    logger.error(f"Failed to trigger background pre-gen: {e}")

    async def _run_background_pregen(self):
        """Run pre-generation in background without blocking send worker."""
        try:
            from v2.pre_generator import PreGenerator
            from database import Campaign
            from campaign_manager import CampaignManager
            
            pregen = PreGenerator()
            active = Campaign.get_active_campaigns()
            
            if not active:
                logger.info("No active campaigns for background pre-gen")
                return
            
            # Generate for all active campaigns
            for campaign in active[:5]:  # Limit to 5 campaigns per trigger
                cid = str(campaign["_id"])
                
                # Get pending leads for this campaign
                cm = CampaignManager()
                pending = await asyncio.to_thread(cm.get_pending_leads, max_leads=100)
                campaign_leads = [l for l in pending if str(l.get("campaign_id")) == cid]
                
                if campaign_leads:
                    logger.info(f"Background pre-gen: {len(campaign_leads)} leads for campaign {cid}")
                    await pregen.generate_initial_drafts(cid, campaign_leads, max_rewrites=2)
                
                # Also generate followups
                await pregen.generate_followup_drafts(cid)
            
            logger.info("Background pre-generation completed")
            
        except Exception as e:
            logger.error(f"Background pre-gen failed: {e}", exc_info=True)

    async def _process_one_draft(self) -> bool:
        """
        Claim one draft, send it, record results.
        Returns True if a draft was successfully processed (sent or failed).
        Returns False if nothing to do.
        """
        # Claim a draft atomically
        draft = EmailDraft.claim_next_ready()
        if not draft:
            return False

        draft_id = str(draft["_id"])
        self._in_flight_draft_id = draft_id
        to_email = draft.get("to_email", "")
        preferred_account = draft.get("from_account")
        logger.info(
            "processing_draft",
            extra={
                "draft_id": draft_id,
                "to": to_email,
                "type": draft.get("email_type"),
                "followup": draft.get("followup_number", 0),
                "preferred_account": preferred_account,
            },
        )

        try:
            # Acquire an account
            account = await self.pool.acquire_account(
                preferred_email=preferred_account,
                to_email=to_email,
            )

            if not account:
                # No account available right now — release draft back
                EmailDraft.release_claimed(draft_id)
                self._in_flight_draft_id = None
                return False

            from_email = account["email"]

            try:
                # Send the email
                result = await self._send_email(
                    account=account,
                    to_email=to_email,
                    to_name=draft.get("to_name"),
                    subject=draft.get("subject", ""),
                    body=draft.get("body", ""),
                    html_body=draft.get("html_body"),
                    in_reply_to=draft.get("in_reply_to"),
                    references=draft.get("references"),
                )

                if result["success"]:
                    message_id = result.get("message_id")

                    # Mark draft as sent
                    EmailDraft.mark_sent(draft_id, message_id, from_email)

                    # Create the Email record (same as legacy system)
                    email_id = Email.create(
                        lead_id=str(draft["lead_id"]),
                        campaign_id=str(draft["campaign_id"]),
                        subject=draft["subject"],
                        body=draft["body"],
                        email_type=draft.get("email_type", "initial"),
                        followup_number=draft.get("followup_number", 0),
                        to_email=to_email,
                        is_icp=draft.get("is_icp"),
                        icp_template=draft.get("icp_template"),
                    )

                    # Mark Email as sent with message_id + from_email
                    Email.mark_sent(email_id, from_email, message_id)

                    # Update campaign stats
                    Campaign.increment_stat(
                        str(draft["campaign_id"]), "emails_sent"
                    )

                    # Record the send in account pool (stats + cooldown)
                    await self.pool.record_send(from_email, to_email)

                    logger.info(
                        "email_sent",
                        extra={
                            "to": to_email,
                            "from": from_email,
                            "draft_id": draft_id,
                            "type": draft.get("email_type"),
                            "score": draft.get("quality_score"),
                        },
                    )
                    return True

                else:
                    error = result.get("error", "Unknown error")

                    # Check for 554 (account blocked by Zoho)
                    if result.get("error_code") == 554 or "554" in str(error):
                        self.pool.mark_blocked(from_email, error)

                    EmailDraft.mark_failed(draft_id, error)
                    logger.error(
                        "email_send_failed",
                        extra={"to": to_email, "from": from_email, "error": error},
                    )
                    return True  # processed (even though failed)

            finally:
                # Always release the account lock
                self.pool.release_account(from_email)

        except Exception as e:
            EmailDraft.mark_failed(draft_id, str(e))
            logger.error(f"Draft processing error: {e}", exc_info=True)
            return True
        finally:
            self._in_flight_draft_id = None

    async def _send_email(
        self,
        account: Dict[str, str],
        to_email: str,
        to_name: str = None,
        subject: str = "",
        body: str = "",
        html_body: str = None,
        in_reply_to: str = None,
        references: List[str] = None,
    ) -> dict:
        """
        Send one email via aiosmtplib.
        Produces identical output to zoho_sender.send_email().
        """
        from_email = account["email"]
        from_name = account["sender_name"]

        try:
            # Build MIME message (identical to zoho_sender.py)
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

            # Generate Message-ID (same format as zoho_sender)
            domain = from_email.split("@")[1] if "@" in from_email else "primestrides.com"
            message_id = make_msgid(domain=domain)
            msg["Message-ID"] = message_id

            # Threading headers
            if in_reply_to:
                msg["In-Reply-To"] = in_reply_to
                if references:
                    msg["References"] = " ".join(references)
                else:
                    msg["References"] = in_reply_to

            # Standard headers
            msg["Subject"] = subject
            msg["From"] = formataddr((from_name, from_email))
            msg["To"] = formataddr((to_name, to_email)) if to_name else to_email
            msg["Reply-To"] = config.REPLY_TO or from_email

            # Send via aiosmtplib
            logger.debug(f"Connecting to {self.smtp_host}:{self.smtp_port} as {from_email}")

            smtp = aiosmtplib.SMTP(
                hostname=self.smtp_host,
                port=self.smtp_port,
                timeout=60,
                start_tls=True,
            )

            await smtp.connect()
            await smtp.login(from_email, account["password"])
            await smtp.sendmail(from_email, [to_email], msg.as_string())
            await smtp.quit()

            logger.info(
                "smtp_transmitted",
                extra={"to": to_email, "from": from_email, "message_id": message_id[:40]},
            )

            return {
                "success": True,
                "message_id": message_id,
                "from_email": from_email,
            }

        except aiosmtplib.SMTPException as e:
            error_msg = f"SMTP error sending to {to_email}: {e}"
            error_code = getattr(e, "code", None)
            logger.error(
                "smtp_error",
                extra={"to": to_email, "from": from_email, "error_code": error_code, "error": str(e)[:200]},
            )

            return {
                "success": False,
                "error": error_msg,
                "from_email": from_email,
                "error_code": error_code,
            }

        except (asyncio.TimeoutError, OSError) as e:
            return {
                "success": False,
                "error": f"Connection timeout to {to_email}: {e}",
                "from_email": from_email,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error sending to {to_email}: {e}",
                "from_email": from_email,
            }

    def request_shutdown(self):
        """Signal the worker to stop after current send."""
        self._shutdown.set()
