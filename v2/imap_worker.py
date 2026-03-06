"""
Async IMAP Worker — Check replies + bounces from the shared Gmail inbox.

SMTP2GO migration: all sending accounts set Reply-To = GMAIL_IMAP_ACCOUNT,
so replies land in one place. We check only that single Gmail inbox instead
of iterating over all 8 Zoho accounts.

Backward-compatible with reply_detector.py's logic:
- Same regex patterns (auto-reply, unsubscribe, hard-bounce)
- Same MongoDB updates (emails, leads, do_not_contact)
- Single account → simpler concurrency; still runs via asyncio.to_thread
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
    """Get all email addresses we've sent to (same as reply_detector.py)."""
    sent_emails = emails_collection.find(
        {
            "status": {"$in": [Email.STATUS_SENT, Email.STATUS_OPENED]},
            "lead_id": {"$exists": True},
        },
        {"lead_id": 1},
    )
    lead_ids = [e["lead_id"] for e in sent_emails if e.get("lead_id") is not None]
    if not lead_ids:
        return set()
    leads = leads_collection.find({"_id": {"$in": lead_ids}}, {"email": 1})
    return {lead["email"].lower() for lead in leads if lead.get("email")}


def _check_account_replies(
    account: Dict[str, str],
    sent_to_addresses: Set[str],
    since_days: int = 7,
    max_emails: int = 500,
    wall_clock_timeout: int = 120,
) -> Dict:
    """
    Check one account's INBOX for replies/bounces.
    Runs synchronously — meant to be called via asyncio.to_thread().

    Optimised 3-phase approach to avoid hanging on large inboxes:
      Phase 1 — Fetch headers-only (From + Subject) for the most recent
                 `max_emails` messages.  This is fast even on a huge Gmail inbox.
      Phase 2 — Filter down to emails whose From matches a known lead OR looks
                 like a bounce notification.  Typically < 5% of all messages.
      Phase 3 — Fetch full RFC822 only for that small filtered set.

    Additional safeguards:
      - Pre-loads already-processed UIDs from MongoDB in one batch query
        (avoids a per-email round-trip to MongoDB)
      - Stops processing if wall_clock_timeout seconds have elapsed
    """
    import time as _time

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
    deadline = _time.monotonic() + wall_clock_timeout

    # ── Connect ──────────────────────────────────────────────────────
    try:
        mail = imaplib.IMAP4_SSL(
            config.GMAIL_IMAP_HOST, config.GMAIL_IMAP_PORT, timeout=30
        )
        mail.login(account["email"], account["password"])
        logger.debug("imap_connected", extra={"account": account["email"]})
    except (TimeoutError, OSError) as e:
        logger.error("imap_connection_timeout", extra={"account": account["email"], "error": str(e)})
        result["errors"].append(f"Connection timeout: {e}")
        return result
    except imaplib.IMAP4.error as e:
        logger.error("imap_auth_error", extra={"account": account["email"], "error": str(e)})
        result["errors"].append(f"IMAP error (check GMAIL_IMAP_APP_PASSWORD): {e}")
        return result
    except Exception as e:
        logger.error("imap_unexpected_error", extra={"account": account["email"], "error": str(e)})
        result["errors"].append(f"Unexpected: {e}")
        return result

    try:
        mail.select("INBOX")

        # ── Get message IDs and UIDs since date ───────────────────────
        status, messages = mail.search(None, f"(SINCE {since_date})")
        if status != "OK":
            return result

        all_email_ids = messages[0].split()

        # Cap to the most recent max_emails (list is oldest→newest)
        if len(all_email_ids) > max_emails:
            all_email_ids = all_email_ids[-max_emails:]

        # Get UIDs for these email IDs (one IMAP roundtrip)
        uid_status, uid_data = mail.uid("search", None, f"(SINCE {since_date})")
        uid_list = uid_data[0].split() if uid_status == "OK" and uid_data[0] else []
        # uid_list is also oldest→newest; align with our capped slice
        if len(uid_list) > max_emails:
            uid_list = uid_list[-max_emails:]
        uid_map: Dict = {}  # seq_num bytes → uid str
        for eid, uid in zip(all_email_ids, uid_list):
            uid_str = uid.decode("utf-8", errors="ignore") if isinstance(uid, bytes) else str(uid)
            uid_map[eid] = uid_str

        logger.info(
            "imap_scan",
            extra={
                "account": account["email"],
                "emails_found": len(all_email_ids),
                "since": since_date,
                "cap": max_emails,
            },
        )

        # ── Phase 0: Batch-load already-processed UIDs from MongoDB ───
        # One DB round-trip instead of one-per-email
        processed_uids: Set[str] = set()
        for doc in _processed_uids_collection.find(
            {"account_email": account["email"]},
            {"uid": 1, "_id": 0},
        ):
            processed_uids.add(doc["uid"])

        # Build bounce sender keywords for the header-only filter
        bounce_sender_keywords = {"mailer-daemon", "postmaster", "mail delivery"}

        # ── Phase 1: Headers-only fetch ───────────────────────────────
        # Only fetch From + Subject — much faster than full RFC822
        candidates = []  # (eid, uid_str, from_addr, subject)

        for eid in all_email_ids:
            if _time.monotonic() > deadline:
                logger.warning(f"imap_timeout: {account['email']} hit {wall_clock_timeout}s wall-clock limit")
                result["errors"].append(f"Wall-clock timeout after {wall_clock_timeout}s")
                break

            msg_uid = uid_map.get(eid, "")
            if msg_uid in processed_uids:
                continue

            try:
                # Fetch only the From + Subject headers (fast)
                hdr_status, hdr_data = mail.fetch(
                    eid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])"
                )
                if hdr_status != "OK" or not hdr_data or not hdr_data[0]:
                    continue

                raw_hdr = hdr_data[0][1] if isinstance(hdr_data[0], tuple) else b""
                hdr_msg = email_lib.message_from_bytes(raw_hdr)
                from_addr = _extract_email_address(hdr_msg.get("From", ""))
                subject = _decode_subject(hdr_msg.get("Subject", ""))

                # ── Phase 2: Filter — only keep relevant senders ──────
                from_lower = from_addr.lower()
                is_lead_reply = from_addr in sent_to_addresses
                is_bounce = any(kw in from_lower for kw in bounce_sender_keywords)

                if is_lead_reply or is_bounce:
                    candidates.append((eid, msg_uid, from_addr, subject))

            except Exception:
                continue

        logger.info(
            "imap_candidates",
            extra={
                "account": account["email"],
                "candidates": len(candidates),
                "scanned": len(all_email_ids),
            },
        )

        # ── Phase 3: Full RFC822 fetch only for candidate emails ──────
        for eid, msg_uid, from_addr, subject in candidates:
            if _time.monotonic() > deadline:
                result["errors"].append(f"Wall-clock timeout during full-body fetch")
                break

            try:
                status, msg_data = mail.fetch(eid, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue

                msg = email_lib.message_from_bytes(msg_data[0][1])
                body = _get_email_body(msg)

                # ── Classify and handle the message ──────────────────
                if from_addr not in sent_to_addresses:
                    _check_for_bounce(from_addr, subject, body, result)

                elif DoNotContact.is_blocked(from_addr):
                    pass  # Already on DNC

                else:
                    lead = Lead.get_by_email(from_addr)
                    if lead:
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

                # ── Mark UID as processed ────────────────────────────
                try:
                    _processed_uids_collection.update_one(
                        {"account_email": account["email"], "uid": msg_uid},
                        {"$set": {"processed_at": datetime.utcnow()}},
                        upsert=True,
                    )
                    processed_uids.add(msg_uid)
                except Exception:
                    pass  # duplicate key fine

            except Exception:
                continue

        # Also mark all non-candidate (headers-only) emails as processed
        # so we never re-scan them on the next run
        new_uids_to_mark = [
            uid_map[eid] for eid in all_email_ids
            if uid_map.get(eid) and uid_map[eid] not in processed_uids
        ]
        if new_uids_to_mark:
            try:
                _processed_uids_collection.insert_many(
                    [
                        {"account_email": account["email"], "uid": u, "processed_at": datetime.utcnow()}
                        for u in new_uids_to_mark
                    ],
                    ordered=False,
                )
            except Exception:
                pass  # bulk insert may partial-fail on duplicates — fine

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
    Async IMAP worker that checks the shared Gmail inbox for replies + bounces.

    All SMTP2GO sending accounts use GMAIL_IMAP_ACCOUNT as Reply-To, so all
    replies arrive in a single inbox. We check only that one account.

    Usage:
        worker = ImapWorker()
        results = await worker.check_all()
    """

    def __init__(self, since_days: int = 7):
        # Single Gmail account used as Reply-To for all SMTP2GO senders
        self.gmail_account = {
            "email": config.GMAIL_IMAP_ACCOUNT,
            "password": config.GMAIL_IMAP_APP_PASSWORD,
        }
        self.accounts = [self.gmail_account] if config.GMAIL_IMAP_ACCOUNT else []
        self.since_days = since_days
        self._shutdown = asyncio.Event()

    async def check_all(self) -> Dict:
        """
        Check the shared Gmail inbox for replies + bounces.
        Runs in a thread (imaplib is synchronous).

        Hard outer timeout of 180 s so startup is never blocked indefinitely.
        """
        if not self.accounts:
            logger.warning("No Gmail IMAP account configured (GMAIL_IMAP_ACCOUNT not set)")
            return {"total_replies": 0, "total_bounces": 0, "accounts": []}

        sent_to = await asyncio.to_thread(_get_sent_email_addresses)
        if not sent_to:
            logger.info("No sent emails to check replies for")
            return {"total_replies": 0, "total_bounces": 0, "accounts": []}

        logger.info(
            "imap_check_start",
            extra={
                "inbox": self.gmail_account["email"],
                "tracking": len(sent_to),
            },
        )

        # Single Gmail inbox — one task, with a hard outer timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    asyncio.to_thread(
                        _check_account_replies,
                        self.gmail_account,
                        sent_to,
                        self.since_days,
                    ),
                    return_exceptions=True,
                ),
                timeout=180,  # never block startup for more than 3 min
            )
        except asyncio.TimeoutError:
            logger.warning("imap_check_all_timeout: Gmail IMAP scan exceeded 180s, skipping")
            return {
                "total_replies": 0,
                "total_bounces": 0,
                "total_dnc_added": 0,
                "accounts_checked": 0,
                "accounts_failed": 1,
                "accounts": [],
            }

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
