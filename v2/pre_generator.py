"""
Pre-Generation Pipeline — Decouple LLM generation from SMTP sending.

Generates email drafts (initial + follow-up) ahead of time using the
existing EmailGenerator and EmailReviewer classes, then stores them in
the `email_drafts` MongoDB collection. The send_worker picks up
ready-to-send drafts and delivers them via SMTP.

Runs continuously in the background via `run_continuous()` — no schedule,
no triggers. Just keeps the draft queue populated while the send_worker
handles pacing independently.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from bson import ObjectId

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
from email_verifier import EmailVerifier, VerificationStatus

logger = logging.getLogger("coldemails.pre_generator")

# ── EmailDraft collection ────────────────────────────────────────────
email_drafts_collection = db["email_drafts"]
email_drafts_collection.create_index([("status", 1), ("scheduled_send_at", 1)])
email_drafts_collection.create_index([("lead_id", 1), ("campaign_id", 1)])
email_drafts_collection.create_index("status")


class DraftStatus:
    GENERATING = "generating"
    REVIEW_FAILED = "review_failed"
    READY = "ready_to_send"
    CLAIMED = "claimed"  # send_worker has picked it up
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"  # e.g. lead on DNC after draft was created


class EmailDraft:
    """CRUD for the email_drafts collection."""

    @staticmethod
    def create(
        lead_id: str,
        campaign_id: str,
        email_type: str,
        followup_number: int = 0,
        subject: str = "",
        body: str = "",
        html_body: str = None,
        from_account: str = None,
        in_reply_to: str = None,
        references: List[str] = None,
        quality_score: int = 0,
        review_passed: bool = False,
        to_email: str = None,
        to_name: str = None,
        scheduled_send_at: datetime = None,
    ) -> str:
        doc = {
            "lead_id": ObjectId(lead_id),
            "campaign_id": ObjectId(campaign_id),
            "to_email": to_email,
            "to_name": to_name,
            "email_type": email_type,
            "followup_number": followup_number,
            "subject": subject,
            "body": body,
            "html_body": html_body,
            "from_account": from_account,
            "in_reply_to": in_reply_to,
            "references": references or [],
            "quality_score": quality_score,
            "review_passed": review_passed,
            "status": DraftStatus.GENERATING,
            "created_at": datetime.utcnow(),
            "scheduled_send_at": scheduled_send_at,
            "sent_at": None,
            "error_message": None,
            "retry_count": 0,
        }
        result = email_drafts_collection.insert_one(doc)
        draft_id = str(result.inserted_id)
        logger.info(
            f"draft_created: {draft_id[:8]}... lead={lead_id[:8]}... "
            f"type={email_type} to={to_email}",
        )
        return draft_id

    @staticmethod
    def mark_ready(draft_id: str, subject: str, body: str, quality_score: int, html_body: str = None):
        logger.info(f"draft_marked_ready: {draft_id[:8]}... score={quality_score} subj={subject[:50]}")
        email_drafts_collection.update_one(
            {"_id": ObjectId(draft_id)},
            {
                "$set": {
                    "subject": subject,
                    "body": body,
                    "html_body": html_body,
                    "quality_score": quality_score,
                    "review_passed": True,
                    "status": DraftStatus.READY,
                }
            },
        )

    @staticmethod
    def mark_review_failed(draft_id: str, quality_score: int, error: str = None):
        logger.warning(f"draft_review_failed: {draft_id[:8]}... score={quality_score} error={error}")
        email_drafts_collection.update_one(
            {"_id": ObjectId(draft_id)},
            {
                "$set": {
                    "quality_score": quality_score,
                    "review_passed": False,
                    "status": DraftStatus.REVIEW_FAILED,
                    "error_message": error or "Quality review failed",
                }
            },
        )

    @staticmethod
    def claim_next_ready(from_account: str = None, skip_domains: Set[str] = None) -> Optional[Dict]:
        """
        Atomically claim the next ready-to-send draft.
        Uses findOneAndUpdate to prevent race conditions.

        Args:
            from_account: Optionally restrict to drafts for a specific sender.
            skip_domains: Set of recipient domains to exclude (already
                          saturated by domain throttling).
        """
        query = {"status": DraftStatus.READY}
        if from_account:
            query["from_account"] = from_account

        # Pre-filter drafts whose recipient domain is already saturated today.
        # This prevents the claim→throttle→release infinite loop.
        if skip_domains:
            escaped = [re.escape(d) for d in skip_domains]
            # Match to_email ending with @<domain> (case-insensitive)
            pattern = "@(" + "|".join(escaped) + ")$"
            query["to_email"] = {"$not": {"$regex": pattern, "$options": "i"}}

        doc = email_drafts_collection.find_one_and_update(
            query,
            {
                "$set": {
                    "status": DraftStatus.CLAIMED,
                    "claimed_at": datetime.utcnow(),
                }
            },
            # Priority: followup_number (desc) → scheduled time → creation time
            # Ensures followup #2 (Day 6) → followup #1 (Day 3) → initial emails
            sort=[("followup_number", -1), ("scheduled_send_at", 1), ("created_at", 1)],
            return_document=True,
        )
        if doc:
            logger.info(
                f"draft_claimed: {str(doc['_id'])[:8]}... to={doc.get('to_email')} type={doc.get('email_type')}",
            )
        else:
            logger.debug("no_ready_drafts")
        return doc

    @staticmethod
    def mark_sent(draft_id: str, message_id: str = None, from_email: str = None):
        logger.info(f"draft_marked_sent: {draft_id[:8]}... from={from_email}")
        email_drafts_collection.update_one(
            {"_id": ObjectId(draft_id)},
            {
                "$set": {
                    "status": DraftStatus.SENT,
                    "sent_at": datetime.utcnow(),
                    "smtp_message_id": message_id,
                    "actual_from_email": from_email,
                }
            },
        )

    @staticmethod
    def mark_failed(draft_id: str, error: str):
        logger.error(f"draft_marked_failed: {draft_id[:8]}... error={error[:200]}")
        email_drafts_collection.update_one(
            {"_id": ObjectId(draft_id)},
            {
                "$set": {
                    "status": DraftStatus.FAILED,
                    "error_message": error,
                },
                "$inc": {"retry_count": 1},
            },
        )

    @staticmethod
    def release_claimed(draft_id: str):
        """Release a claimed draft back to ready (e.g. on shutdown)."""
        logger.info(f"draft_released: {draft_id[:8]}...")
        email_drafts_collection.update_one(
            {"_id": ObjectId(draft_id), "status": DraftStatus.CLAIMED},
            {"$set": {"status": DraftStatus.READY}},
        )

    @staticmethod
    def get_ready_count() -> int:
        return email_drafts_collection.count_documents({"status": DraftStatus.READY})

    @staticmethod
    def get_stats() -> Dict:
        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        results = list(email_drafts_collection.aggregate(pipeline))
        return {r["_id"]: r["count"] for r in results}

    @staticmethod
    def has_draft_for_lead(lead_id: str, campaign_id: str, email_type: str, followup_number: int = 0) -> bool:
        """Check if a draft already exists for this lead/campaign/type combo."""
        query = {
            "lead_id": ObjectId(lead_id),
            "campaign_id": ObjectId(campaign_id),
            "email_type": email_type,
            "status": {"$nin": [DraftStatus.FAILED, DraftStatus.SKIPPED]},
        }
        if email_type in ("followup", "followup_new_thread"):
            query["followup_number"] = followup_number
        return email_drafts_collection.count_documents(query) > 0

    @staticmethod
    def cleanup_stale_claimed(timeout_minutes: int = 30):
        """Release drafts that were claimed but never sent (e.g. crash)."""
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        result = email_drafts_collection.update_many(
            {"status": DraftStatus.CLAIMED, "claimed_at": {"$lt": cutoff}},
            {"$set": {"status": DraftStatus.READY}},
        )
        if result.modified_count:
            logger.info(f"Released {result.modified_count} stale claimed drafts")


class PreGenerator:
    """
    Orchestrates email draft generation using existing EmailGenerator
    and EmailReviewer. Runs as an async task via asyncio.to_thread()
    since the underlying generators are synchronous.
    """

    def __init__(self):
        # Lazy imports to avoid circular dependencies
        self._generator = None
        self._reviewer = None
        self._enricher_func = None
        self._cm = None  # CampaignManager (lazy-init)

    def _ensure_initialized(self):
        """Lazy-init the heavy generator/reviewer objects."""
        if self._generator is None:
            from email_generator import EmailGenerator
            from email_reviewer import EmailReviewer

            self._generator = EmailGenerator()
            self._reviewer = EmailReviewer()

    def _get_campaign_manager(self):
        """Lazy-init CampaignManager (heavy, synchronous wrapper around MongoDB)."""
        if self._cm is None:
            from campaign_manager import CampaignManager
            self._cm = CampaignManager()
        return self._cm

    @staticmethod
    async def _sleep_or_shutdown(event: asyncio.Event, seconds: float):
        """Sleep for `seconds`, or return early if shutdown is signaled."""
        try:
            await asyncio.wait_for(event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def run_continuous(self, shutdown_event: asyncio.Event):
        """
        Run pre-generation continuously as a background task.

        Loop: get pending leads → generate drafts → sleep → repeat.

        The send_worker handles pacing/scheduling independently — this just
        keeps the draft queue populated so the send_worker never starves.
        """
        logger.info("continuous_pregen_started")

        # Let other workers (IMAP, account pool) initialize first
        await self._sleep_or_shutdown(shutdown_event, 15)

        while not shutdown_event.is_set():
            try:
                cycle_generated = 0
                cycle_failed = 0
                cycle_skipped = 0

                # ── Get active campaigns ──────────────────────────────
                active = Campaign.get_active_campaigns()
                if not active:
                    logger.debug("continuous_pregen: no active campaigns, sleeping 120s")
                    await self._sleep_or_shutdown(shutdown_event, 120)
                    continue

                # ── Fetch ALL pending leads once, group by campaign ───
                # Request 500 leads; get_pending_leads now skips leads with
                # active drafts so each cycle surfaces new work.
                cm = self._get_campaign_manager()
                pending = await asyncio.to_thread(cm.get_pending_leads, max_leads=500)

                leads_by_campaign: Dict[str, List[Dict]] = {}
                for lead in pending:
                    cid = str(lead.get("campaign_id", ""))
                    if cid:
                        leads_by_campaign.setdefault(cid, []).append(lead)

                # ── Process each campaign ─────────────────────────────
                for campaign in active:
                    if shutdown_event.is_set():
                        break

                    cid = str(campaign["_id"])

                    # Step 1: Initial drafts for pending leads
                    campaign_leads = leads_by_campaign.get(cid, [])
                    if campaign_leads:
                        logger.info(
                            f"continuous_pregen: generating {len(campaign_leads)} "
                            f"initials for campaign {cid[:8]}..."
                        )
                        stats = await self.generate_initial_drafts(
                            cid, campaign_leads, max_rewrites=2
                        )
                        cycle_generated += stats.get("generated", 0)
                        cycle_failed += stats.get("failed", 0)
                        cycle_skipped += stats.get("skipped", 0)

                    # Step 2: Followup drafts
                    f_stats = await self.generate_followup_drafts(cid)
                    cycle_generated += f_stats.get("generated", 0)
                    cycle_failed += f_stats.get("failed", 0)
                    cycle_skipped += f_stats.get("skipped", 0)

                # ── Housekeeping ──────────────────────────────────────
                EmailDraft.cleanup_stale_claimed(timeout_minutes=30)

                # ── Adaptive sleep ────────────────────────────────────
                ready = EmailDraft.get_ready_count()

                if cycle_generated > 0:
                    logger.info(
                        f"continuous_pregen_cycle: generated={cycle_generated} "
                        f"failed={cycle_failed} skipped={cycle_skipped} ready_queue={ready}",
                    )
                    # Generated drafts — check again soon (more leads may arrive)
                    sleep_secs = 30
                else:
                    logger.debug(
                        f"continuous_pregen: idle cycle, "
                        f"{ready} ready in queue, sleeping 120s"
                    )
                    # Nothing to do — wait 2 min before rechecking
                    sleep_secs = 120

                await self._sleep_or_shutdown(shutdown_event, sleep_secs)

            except Exception as e:
                logger.error(f"continuous_pregen_error: {e}", exc_info=True)
                await self._sleep_or_shutdown(shutdown_event, 60)

        logger.info("continuous_pregen_stopped")

    async def generate_initial_drafts(
        self,
        campaign_id: str,
        leads: List[Dict],
        max_rewrites: int = 3,
    ) -> Dict:
        """
        Pre-generate initial email drafts for a list of leads.

        Runs synchronously under asyncio.to_thread().
        """
        result = await asyncio.to_thread(
            self._generate_initial_drafts_sync,
            campaign_id,
            leads,
            max_rewrites,
        )
        return result

    def _generate_initial_drafts_sync(
        self, campaign_id: str, leads: List[Dict], max_rewrites: int
    ) -> Dict:
        self._ensure_initialized()

        stats = {"generated": 0, "failed": 0, "skipped": 0}
        logger.info(
            f"initial_draft_generation_start: campaign={campaign_id[:8]}... "
            f"leads={len(leads)} max_rewrites={max_rewrites}",
        )

        # Fetch campaign_context for email generation
        campaign = Campaign.get_by_id(campaign_id)
        if campaign:
            campaign_context = campaign.get("target_criteria", {}).get("campaign_context", {})
        else:
            campaign_context = {}
            logger.warning(f"Campaign {campaign_id} not found — using empty campaign_context")

        for lead in leads:
            lead_id = str(lead["_id"])
            to_email = lead.get("email", "")

            # Skip if draft already exists
            if EmailDraft.has_draft_for_lead(lead_id, campaign_id, "initial"):
                stats["skipped"] += 1
                continue

            # Skip DNC
            if DoNotContact.is_blocked(to_email):
                stats["skipped"] += 1
                continue

            # Skip already contacted
            if Email.has_been_contacted_by_email(to_email):
                stats["skipped"] += 1
                continue

            # ── EMAIL VERIFICATION: Skip invalid emails BEFORE generating ──
            # Check if lead is already marked invalid
            if lead.get("email_invalid"):
                stats["skipped"] += 1
                logger.debug(f"Skipping {to_email} — already marked invalid")
                continue

            # Check if we have recent verification (within 7 days)
            verification_date = lead.get("verification_date")
            needs_reverify = True
            if verification_date:
                age_days = (datetime.now() - verification_date).days
                if age_days <= 7 and lead.get("verification_status") == "valid":
                    needs_reverify = False

            if needs_reverify:
                # Verify email deliverability
                try:
                    verifier = EmailVerifier(smtp_timeout=10, skip_smtp_verify=False)
                    verification = verifier.verify(to_email)
                    
                    # Store verification results
                    Lead.update_verification_status(
                        lead_id=lead_id,
                        verification_status=verification.status.value,
                        verification_score=verification.score,
                        verification_reason=verification.reason,
                        verification_checks=verification.checks
                    )
                    
                    # Skip invalid emails
                    if verification.status == VerificationStatus.INVALID:
                        logger.info(f"Skipping {to_email} — failed verification: {verification.reason}")
                        Lead.mark_invalid_email(lead_id, f"Verification failed: {verification.reason}")
                        stats["skipped"] += 1
                        continue
                    elif verification.status == VerificationStatus.RISKY:
                        logger.warning(f"Risky email {to_email}: {verification.reason}")
                        # Continue but log warning
                except Exception as e:
                    logger.error(f"Verification failed for {to_email}: {e}")
                    # Don't skip on verification error — might be network issue

            try:
                # Create placeholder draft
                draft_id = EmailDraft.create(
                    lead_id=lead_id,
                    campaign_id=campaign_id,
                    email_type="initial",
                    to_email=to_email,
                    to_name=lead.get("first_name"),
                )

                # Generate email
                email_data = self._generator.generate_initial_email(
                    lead=lead,
                    campaign_context=campaign_context
                )
                if not email_data:
                    EmailDraft.mark_failed(draft_id, "Generation returned None")
                    stats["failed"] += 1
                    continue

                subject = email_data.get("subject", "")
                body = email_data.get("body", "")

                # Review + rewrite loop
                final_subject, final_body, score = self._review_and_rewrite(
                    subject, body, lead, campaign_context, max_rewrites
                )

                if score >= 70:
                    EmailDraft.mark_ready(draft_id, final_subject, final_body, score)
                    stats["generated"] += 1
                    logger.info(
                        f"draft_generated: lead={lead_id[:8]}... score={score} type=initial",
                    )
                else:
                    EmailDraft.mark_review_failed(
                        draft_id, score, f"Best score {score} < 70"
                    )
                    stats["failed"] += 1

            except Exception as e:
                logger.error(f"Draft generation failed for {to_email}: {e}")
                # Mark the placeholder draft as failed so the lead can be retried
                try:
                    EmailDraft.mark_failed(draft_id, str(e)[:500])
                except Exception:
                    pass
                stats["failed"] += 1

        logger.info(f"initial_draft_generation_complete: {stats}")
        return stats

    async def generate_followup_drafts(self, campaign_id: str) -> Dict:
        """Pre-generate follow-up email drafts."""
        return await asyncio.to_thread(
            self._generate_followup_drafts_sync, campaign_id
        )

    def _generate_followup_drafts_sync(self, campaign_id: str) -> Dict:
        self._ensure_initialized()
        stats = {"generated": 0, "failed": 0, "skipped": 0}
        logger.info(f"followup_draft_generation_start: campaign={campaign_id[:8]}...")

        # Fetch campaign_context for email generation
        campaign = Campaign.get_by_id(campaign_id)
        if campaign:
            campaign_context = campaign.get("target_criteria", {}).get("campaign_context", {})
        else:
            campaign_context = {}
            logger.warning(f"Campaign {campaign_id} not found — using empty campaign_context for followups")

        # Get leads needing follow-up (same logic as campaign_manager)
        for delay_days in [config.FOLLOWUP_1_DELAY_DAYS, config.FOLLOWUP_2_DELAY_DAYS]:
            pending = Email.get_pending_followups(campaign_id, delay_days)

            for item in pending:
                lead_id = str(item["_id"])
                lead = Lead.get_by_id(lead_id)
                if not lead:
                    stats["skipped"] += 1
                    continue

                to_email = lead.get("email", "")
                if DoNotContact.is_blocked(to_email):
                    stats["skipped"] += 1
                    continue

                email_count = item.get("email_count", 1)
                followup_number = email_count  # 1 = first follow-up, 2 = second

                if followup_number > config.MAX_FOLLOWUPS:
                    stats["skipped"] += 1
                    continue

                # Determine email type
                if followup_number == 2:
                    email_type = "followup_new_thread"
                else:
                    email_type = "followup"

                # Skip if draft already exists
                if EmailDraft.has_draft_for_lead(
                    lead_id, campaign_id, email_type, followup_number
                ):
                    stats["skipped"] += 1
                    continue

                try:
                    # Get thread info for same-thread follow-ups
                    thread_info = Email.get_thread_info(lead_id, campaign_id)
                    original_sender = Email.get_sender_for_lead(lead_id, campaign_id)

                    # Get previous emails for context
                    previous_emails = Email.get_by_lead_and_campaign(lead_id, campaign_id)
                    prev_sent = [
                        e for e in previous_emails if e.get("status") == Email.STATUS_SENT
                    ]

                    draft_id = EmailDraft.create(
                        lead_id=lead_id,
                        campaign_id=campaign_id,
                        email_type=email_type,
                        followup_number=followup_number,
                        to_email=to_email,
                        to_name=lead.get("first_name"),
                        from_account=original_sender,
                        in_reply_to=thread_info.get("in_reply_to") if email_type == "followup" else None,
                        references=thread_info.get("references") if email_type == "followup" else None,
                    )

                    # Generate follow-up content
                    email_data = self._generator.generate_followup_email(
                        lead=lead,
                        campaign_context=campaign_context,
                        previous_emails=prev_sent,
                        followup_number=followup_number,
                    )

                    if not email_data:
                        EmailDraft.mark_failed(draft_id, "Follow-up generation returned None")
                        stats["failed"] += 1
                        continue

                    subject = email_data.get("subject", "")
                    body = email_data.get("body", "")

                    final_subject, final_body, score = self._review_and_rewrite(
                        subject, body, lead, campaign_context, max_rewrites=2
                    )

                    if score >= 70:
                        EmailDraft.mark_ready(draft_id, final_subject, final_body, score)
                        stats["generated"] += 1
                    else:
                        EmailDraft.mark_review_failed(
                            draft_id, score, f"Best score {score} < 70"
                        )
                        stats["failed"] += 1

                except Exception as e:
                    logger.error(f"Followup draft failed for {to_email}: {e}")
                    # Mark the placeholder draft as failed so the lead can be retried
                    try:
                        EmailDraft.mark_failed(draft_id, str(e)[:500])
                    except Exception:
                        pass
                    stats["failed"] += 1

        logger.info(f"followup_draft_generation_complete: {stats}")
        return stats

    def _review_and_rewrite(
        self, subject: str, body: str, lead: Dict,
        campaign_context: Dict, max_rewrites: int = 3,
    ) -> tuple:
        """
        Review an email and rewrite if needed. Returns (subject, body, score).
        Mirrors CampaignManager._review_and_rewrite_if_needed logic.
        """
        best_subject = subject
        best_body = body
        best_score = 0

        current_email = {"subject": subject, "body": body}

        for attempt in range(max_rewrites + 1):
            try:
                # review_email takes (email_dict, lead) and returns a ReviewResult object
                review = self._reviewer.review_email(
                    email=current_email,
                    lead=lead,
                    save_review=True,
                )
                score = review.score  # ReviewResult.score (int 0-100)
                logger.debug(
                    "review_attempt",
                    extra={"attempt": attempt + 1, "score": score, "best_score": best_score},
                )

                if score > best_score:
                    best_score = score
                    best_subject = current_email.get("subject", best_subject)
                    best_body = current_email.get("body", best_body)

                if not review.rewrite_required:
                    return best_subject, best_body, score

                # Try to rewrite if score is low and we have attempts left
                if attempt < max_rewrites:
                    rewritten = self._reviewer._rewrite_email(
                        email=current_email,
                        lead=lead,
                        review=review,
                        campaign_context=campaign_context,
                    )
                    if rewritten and isinstance(rewritten, dict) and rewritten.get("subject") and rewritten.get("body"):
                        current_email = rewritten
                    else:
                        logger.debug("Rewrite returned invalid result, keeping previous")

            except Exception as e:
                logger.warning(f"Review attempt {attempt + 1} failed: {e}")
                break

        return best_subject, best_body, best_score


# ── Standalone CLI for manual pre-generation ─────────────────────────
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    print("Email Pre-Generator — Manual Mode")
    print("=" * 50)

    stats = EmailDraft.get_stats()
    print(f"Current draft stats: {stats}")
    print(f"Ready to send: {EmailDraft.get_ready_count()}")
