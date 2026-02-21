"""
Async IMAP Worker — Check replies + bounces across all accounts concurrently.

Replicates reply_detector.py's logic using aioimaplib for native async IMAP.
Falls back to synchronous imaplib via asyncio.to_thread() if aioimaplib
has compatibility issues with Zoho.

Key features:
- All 8 accounts checked concurrently (not serially)
- Same regex patterns as legacy reply_detector.py
- Same handling: auto-replies, unsubscribes, permanent OOO, hard bounces
- Updates same MongoDB collections (emails, leads, do_not_contact)
"""

import asyncio
import imaplib
import email as email_lib
import logging
import re
from datetime import datetime, timedelta
from email.header import decode_header
from typing import Dict, List, Optional, Set, Tuple

import config
from database import (
    Campaign,
    DoNotContact,
    Email,
    Lead,
    db,
    emails_collection,
    leads_collection,
)

# Track processed IMAP message UIDs to prevent double-detection of bounces/replies
_processed_uids_collection = db["imap_processed_uids"]
_processed_uids_collection.create_index(
    [("account_email", 1), ("uid", 1)], unique=True
)
_processed_uids_collection.create_index(
    "processed_at", expireAfterSeconds=60 * 60 * 24 * 14  # auto-delete after 14 days
)

logger = logging.getLogger("coldemails.imap_worker")

# ── Pattern lists (identical to reply_detector.py) ────────────────────

AUTO_REPLY_PATTERNS = [
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

PERMANENT_AUTO_REPLY_PATTERNS = [
    r"no longer (with|at|employed)",
    r"left (the company|the organization|this position)",
    r"is no longer (working|employed)",
    r"has left",
    r"moved on from",
    r"this email (address )?(is )?no longer (active|monitored|in use)",
    r"this (mailbox|inbox) is (not|no longer) (monitored|active)",
]

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

BOUNCE_INDICATORS = [
    "mailer-daemon",
    "postmaster",
    "mail delivery",
    "delivery failure",
    "undeliverable",
    "returned mail",
    "delivery status notification",
]

HARD_BOUNCE_INDICATORS = [
    "user unknown",
    "user not found",
    "no such user",
    "mailbox not found",
    "invalid recipient",
    "recipient rejected",
    "address rejected",
    "does not exist",
    "mailbox unavailable",
    "550",
    "551",
    "552",
    "553",
    "554",
]


# ── Helper functions ─────────────────────────────────────────────────

def _decode_subject(subject: str) -> str:
    if subject is None:
        return ""
    decoded_parts = decode_header(subject)
    result = ""
    for part, enc in decoded_parts:
        if isinstance(part, bytes):
            result += part.decode(enc or "utf-8", errors="ignore")
        else:
            result += part
    return result


def _extract_email_address(from_header: str) -> str:
    if not from_header:
        return ""
    m = re.search(r"<([^>]+)>", from_header)
    if m:
        return m.group(1).lower()
    m = re.search(r"[\w\.-]+@[\w\.-]+", from_header)
    if m:
        return m.group(0).lower()
    return from_header.lower()


def _get_email_body(msg) -> str:
    body = ""
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="ignore")
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="ignore")
    except Exception:
        pass
    return body


def _is_auto_reply(subject: str, body: str) -> Tuple[bool, bool]:
    text = f"{subject} {body}".lower()
    for pattern in PERMANENT_AUTO_REPLY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True, True
    for pattern in AUTO_REPLY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True, False
    return False, False


def _is_unsubscribe_request(subject: str, body: str) -> bool:
    text = f"{subject} {body}".lower()
    for pattern in UNSUBSCRIBE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


# ── Core IMAP checking (synchronous, run via to_thread) ──────────────

def _get_sent_email_addresses() -> Set[str]:
    """Get all email addresses we've sent to (same as reply_detector.py).
    
    Filters out warmup emails (which have no lead_id since they're not campaign emails).
    """
    sent_emails = emails_collection.find(
        {
            "status": {"$in": [Email.STATUS_SENT, Email.STATUS_OPENED]},
            "lead_id": {"$exists": True}  # Skip warmup emails (no lead_id)
        },
        {"lead_id": 1},
    )
    lead_ids = [e["lead_id"] for e in sent_emails]
    if not lead_ids:
        return set()
    
    leads = leads_collection.find({"_id": {"$in": lead_ids}}, {"email": 1})
    return {lead["email"].lower() for lead in leads if lead.get("email")}


def _check_account_replies(
    account: Dict[str, str],
    sent_to_addresses: Set[str],
    since_days: int = 7,
) -> Dict:
    """
    Check one account's INBOX for replies/bounces.
    Runs synchronously — meant to be called via asyncio.to_thread().
    """
    result = {
        "account": account["email"],
        "replies": 0,
        "auto_replies": 0,
        "unsubscribes": 0,
        "bounces": 0,
        "dnc_added": 0,
        "errors": [],
    }

    since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")

    try:
        mail = imaplib.IMAP4_SSL(
            config.PRODUCTION_IMAP_HOST, config.PRODUCTION_IMAP_PORT, timeout=30
        )
        mail.login(account["email"], account["password"])
        logger.debug("imap_connected", extra={"account": account["email"]})
    except (TimeoutError, OSError) as e:
        logger.error("imap_connection_timeout", extra={"account": account["email"], "error": str(e)})
        result["errors"].append(f"Connection timeout: {e}")
        return result
    except imaplib.IMAP4.error as e:
        logger.error("imap_auth_error", extra={"account": account["email"], "error": str(e)})
        result["errors"].append(f"IMAP error: {e}")
        return result
    except Exception as e:
        logger.error("imap_unexpected_error", extra={"account": account["email"], "error": str(e)})
        result["errors"].append(f"Unexpected: {e}")
        return result

    try:
        mail.select("INBOX")
        status, messages = mail.search(None, f"(SINCE {since_date})")
        if status != "OK":
            return result

        email_ids = messages[0].split()
        logger.info(
            "imap_scan",
            extra={
                "account": account["email"],
                "emails_found": len(email_ids),
                "since": since_date,
            },
        )

        # Fetch UIDs for deduplication (so we don't re-process the same messages)
        uid_status, uid_data = mail.uid("search", None, f"(SINCE {since_date})")
        uid_list = uid_data[0].split() if uid_status == "OK" and uid_data[0] else []
        uid_map = dict(zip(email_ids, uid_list))  # seq_num → UID

        for eid in email_ids:
            try:
                # Skip already-processed messages
                msg_uid = uid_map.get(eid, eid).decode("utf-8", errors="ignore") if isinstance(uid_map.get(eid, eid), bytes) else str(uid_map.get(eid, eid))
                if _processed_uids_collection.find_one(
                    {"account_email": account["email"], "uid": msg_uid}
                ):
                    continue

                status, msg_data = mail.fetch(eid, "(RFC822)")
                if status != "OK":
                    continue

                msg = email_lib.message_from_bytes(msg_data[0][1])
                from_addr = _extract_email_address(msg.get("From", ""))
                subject = _decode_subject(msg.get("Subject", ""))
                body = _get_email_body(msg)

                # ── Classify and handle the message ──

                if from_addr not in sent_to_addresses:
                    # Check for bounces even if not from a lead
                    _check_for_bounce(
                        from_addr, subject, body, result
                    )

                elif DoNotContact.is_blocked(from_addr):
                    pass  # Already on DNC, nothing to do

                else:
                    lead = Lead.get_by_email(from_addr)
                    if lead:
                        # Auto-reply check
                        is_ar, is_permanent = _is_auto_reply(subject, body)
                        if is_ar:
                            result["auto_replies"] += 1
                            if is_permanent:
                                if DoNotContact.add(
                                    from_addr,
                                    DoNotContact.REASON_AUTO_REPLY,
                                    f"Auto-reply: {subject[:100]}",
                                ):
                                    result["dnc_added"] += 1
                                logger.info(f"Permanent OOO from {from_addr}")
                            else:
                                logger.info(f"Temp OOO from {from_addr}")

                        # Unsubscribe check
                        elif _is_unsubscribe_request(subject, body):
                            result["unsubscribes"] += 1
                            if DoNotContact.add(
                                from_addr,
                                DoNotContact.REASON_UNSUBSCRIBE,
                                f"Unsubscribe: {subject[:100]}",
                            ):
                                result["dnc_added"] += 1
                            logger.info(f"Unsubscribe from {from_addr}")

                        else:
                            # Real reply!
                            result["replies"] += 1
                            update_result = emails_collection.update_many(
                                {
                                    "lead_id": lead["_id"],
                                    "status": {"$ne": Email.STATUS_REPLIED},
                                },
                                {
                                    "$set": {
                                        "status": Email.STATUS_REPLIED,
                                        "replied_at": datetime.utcnow(),
                                    }
                                },
                            )
                            if update_result.modified_count > 0:
                                campaign_emails = emails_collection.find(
                                    {"lead_id": lead["_id"]}
                                )
                                for ce in campaign_emails:
                                    Campaign.increment_stat(
                                        str(ce["campaign_id"]), "emails_replied"
                                    )
                            logger.info(
                                "reply_detected",
                                extra={
                                    "from": from_addr,
                                    "subject": subject[:50],
                                    "account": account["email"],
                                },
                            )

                # ── Mark this UID as processed (ALL paths) ──
                try:
                    _processed_uids_collection.update_one(
                        {"account_email": account["email"], "uid": msg_uid},
                        {"$set": {"processed_at": datetime.utcnow()}},
                        upsert=True,
                    )
                except Exception:
                    pass  # duplicate key is fine

            except Exception as e:
                # Skip individual email parse errors silently
                continue

    except Exception as e:
        result["errors"].append(f"Scan error: {e}")
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    logger.info(
        "imap_account_complete",
        extra={
            "account": account["email"],
            "replies": result["replies"],
            "bounces": result["bounces"],
            "auto_replies": result["auto_replies"],
            "unsubscribes": result["unsubscribes"],
            "dnc_added": result["dnc_added"],
        },
    )
    return result


def _check_for_bounce(from_addr: str, subject: str, body: str, result: Dict):
    """Check if an email is a bounce notification."""
    from_lower = from_addr.lower()
    subject_lower = subject.lower()

    is_bounce = any(
        ind in from_lower or ind in subject_lower for ind in BOUNCE_INDICATORS
    )
    if not is_bounce:
        return

    body_lower = body.lower()
    full_text = f"{subject_lower} {body_lower}"
    is_hard = any(ind in full_text for ind in HARD_BOUNCE_INDICATORS)

    bounced_emails = re.findall(r"[\w\.-]+@[\w\.-]+", body_lower)
    for bounced_email in bounced_emails:
        lead = Lead.get_by_email(bounced_email)
        if not lead:
            continue

        result["bounces"] += 1
        lead_id = str(lead["_id"])

        emails_collection.update_many(
            {"lead_id": lead["_id"]},
            {"$set": {"status": Email.STATUS_BOUNCED}},
        )

        bounce_type = "hard" if is_hard else "soft"
        Lead.mark_invalid_email(lead_id, f"{bounce_type.title()} bounce detected")

        if is_hard:
            if DoNotContact.add(
                bounced_email.lower(),
                DoNotContact.REASON_HARD_BOUNCE,
                f"Hard bounce: {subject[:100]}",
            ):
                result["dnc_added"] += 1

        logger.info(
            "bounce_detected",
            extra={
                "email": bounced_email,
                "type": bounce_type,
            },
        )
        break  # one bounce per notification


class ImapWorker:
    """
    Async IMAP worker that checks all accounts concurrently.

    Usage:
        worker = ImapWorker()
        results = await worker.check_all()
    """

    def __init__(self, since_days: int = 7):
        self.accounts = config.PRODUCTION_ACCOUNTS
        self.since_days = since_days
        self._shutdown = asyncio.Event()

    async def check_all(self) -> Dict:
        """
        Check all accounts for replies + bounces concurrently.
        Each account runs in its own thread.
        """
        sent_to = await asyncio.to_thread(_get_sent_email_addresses)
        if not sent_to:
            logger.info("No sent emails to check replies for")
            return {"total_replies": 0, "total_bounces": 0, "accounts": []}

        logger.info(
            "imap_check_start",
            extra={
                "accounts": len(self.accounts),
                "tracking": len(sent_to),
            },
        )

        # Run all accounts concurrently (30s timeout per account)
        async def _check_with_timeout(account):
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(
                        _check_account_replies,
                        account,
                        sent_to,
                        self.since_days,
                    ),
                    timeout=30,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "imap_account_timeout",
                    extra={"account": account["email"], "timeout": 30},
                )
                return {
                    "account": account["email"],
                    "replies": 0, "auto_replies": 0,
                    "unsubscribes": 0, "bounces": 0, "dnc_added": 0,
                    "errors": ["Timeout after 30s"],
                }

        tasks = [_check_with_timeout(account) for account in self.accounts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        total = {
            "total_replies": 0,
            "total_auto_replies": 0,
            "total_unsubscribes": 0,
            "total_bounces": 0,
            "total_dnc_added": 0,
            "accounts_checked": 0,
            "accounts_failed": 0,
            "accounts": [],
        }

        for r in results:
            if isinstance(r, Exception):
                total["accounts_failed"] += 1
                logger.error(f"IMAP check failed: {r}")
                continue

            total["accounts_checked"] += 1
            total["total_replies"] += r["replies"]
            total["total_auto_replies"] += r["auto_replies"]
            total["total_unsubscribes"] += r["unsubscribes"]
            total["total_bounces"] += r["bounces"]
            total["total_dnc_added"] += r["dnc_added"]

            if r["errors"]:
                total["accounts_failed"] += 1

            total["accounts"].append(r)

        logger.info(
            "imap_check_complete",
            extra={
                "replies": total["total_replies"],
                "bounces": total["total_bounces"],
                "unsubscribes": total["total_unsubscribes"],
                "checked": total["accounts_checked"],
                "failed": total["accounts_failed"],
            },
        )

        return total

    async def run_periodic(self, interval_minutes: int = 30):
        """Run IMAP checks periodically until shutdown."""
        logger.info(
            "imap_periodic_start",
            extra={"interval_min": interval_minutes},
        )

        while not self._shutdown.is_set():
            try:
                await self.check_all()
            except Exception as e:
                logger.error(f"Periodic IMAP check failed: {e}", exc_info=True)

            # Wait for the interval or until shutdown
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(),
                    timeout=interval_minutes * 60,
                )
                break  # shutdown was signaled
            except asyncio.TimeoutError:
                continue  # interval elapsed, loop again

        logger.info("imap_periodic_stopped")

    def request_shutdown(self):
        self._shutdown.set()
