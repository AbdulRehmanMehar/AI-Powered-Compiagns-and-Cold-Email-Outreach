"""
Pre-Generation Pipeline — Decouple LLM generation from SMTP sending.

Generates email drafts (initial + follow-up) ahead of time using the
existing EmailGenerator and EmailReviewer classes, then stores them in
the `email_drafts` MongoDB collection. The send_worker picks up
ready-to-send drafts and delivers them via SMTP.

Can run during off-hours (5 PM → 9 AM) so the sending window (9-5) is
100% SMTP-fast with no LLM bottleneck.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

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
            "draft_created",
            extra={
                "draft_id": draft_id,
                "lead_id": lead_id,
                "campaign_id": campaign_id,
                "email_type": email_type,
                "to_email": to_email,
            },
        )
        return draft_id

    @staticmethod
    def mark_ready(draft_id: str, subject: str, body: str, quality_score: int, html_body: str = None):
        logger.info(
            "draft_marked_ready",
            extra={"draft_id": draft_id, "quality_score": quality_score, "subject": subject[:60]},
        )
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
        logger.warning(
            "draft_review_failed",
            extra={"draft_id": draft_id, "quality_score": quality_score, "error": error},
        )
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
    def claim_next_ready(from_account: str = None) -> Optional[Dict]:
        """
        Atomically claim the next ready-to-send draft.
        Uses findOneAndUpdate to prevent race conditions.
        """
        query = {"status": DraftStatus.READY}
        if from_account:
            query["from_account"] = from_account

        doc = email_drafts_collection.find_one_and_update(
            query,
            {
                "$set": {
                    "status": DraftStatus.CLAIMED,
                    "claimed_at": datetime.utcnow(),
                }
            },
            sort=[("scheduled_send_at", 1), ("created_at", 1)],
            return_document=True,
        )
        if doc:
            logger.info(
                "draft_claimed",
                extra={"draft_id": str(doc["_id"]), "to_email": doc.get("to_email"), "type": doc.get("email_type")},
            )
        else:
            logger.debug("no_ready_drafts")
        return doc

    @staticmethod
    def mark_sent(draft_id: str, message_id: str = None, from_email: str = None):
        logger.info(
            "draft_marked_sent",
            extra={"draft_id": draft_id, "from_email": from_email, "message_id": (message_id or "")[:40]},
        )
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
        logger.error("draft_marked_failed", extra={"draft_id": draft_id, "error": error[:200]})
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
        logger.info("draft_released", extra={"draft_id": draft_id})
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

    def _ensure_initialized(self):
        """Lazy-init the heavy generator/reviewer objects."""
        if self._generator is None:
            from email_generator import EmailGenerator
            from email_reviewer import EmailReviewer

            self._generator = EmailGenerator()
            self._reviewer = EmailReviewer()

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
            "initial_draft_generation_start",
            extra={"campaign_id": campaign_id, "lead_count": len(leads), "max_rewrites": max_rewrites},
        )

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
                email_data = self._generator.generate_cold_email(lead)
                if not email_data:
                    EmailDraft.mark_failed(draft_id, "Generation returned None")
                    stats["failed"] += 1
                    continue

                subject = email_data.get("subject", "")
                body = email_data.get("body", "")

                # Review + rewrite loop
                final_subject, final_body, score = self._review_and_rewrite(
                    subject, body, lead, max_rewrites
                )

                if score >= 70:
                    EmailDraft.mark_ready(draft_id, final_subject, final_body, score)
                    stats["generated"] += 1
                    logger.info(
                        "draft_generated",
                        extra={
                            "lead_id": lead_id,
                            "score": score,
                            "type": "initial",
                        },
                    )
                else:
                    EmailDraft.mark_review_failed(
                        draft_id, score, f"Best score {score} < 70"
                    )
                    stats["failed"] += 1

            except Exception as e:
                logger.error(f"Draft generation failed for {to_email}: {e}")
                stats["failed"] += 1

        logger.info("initial_draft_generation_complete", extra=stats)
        return stats

    async def generate_followup_drafts(self, campaign_id: str) -> Dict:
        """Pre-generate follow-up email drafts."""
        return await asyncio.to_thread(
            self._generate_followup_drafts_sync, campaign_id
        )

    def _generate_followup_drafts_sync(self, campaign_id: str) -> Dict:
        self._ensure_initialized()
        stats = {"generated": 0, "failed": 0, "skipped": 0}
        logger.info("followup_draft_generation_start", extra={"campaign_id": campaign_id})

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
                        previous_emails=prev_sent,
                        followup_number=followup_number,
                        new_thread=(email_type == "followup_new_thread"),
                    )

                    if not email_data:
                        EmailDraft.mark_failed(draft_id, "Follow-up generation returned None")
                        stats["failed"] += 1
                        continue

                    subject = email_data.get("subject", "")
                    body = email_data.get("body", "")

                    final_subject, final_body, score = self._review_and_rewrite(
                        subject, body, lead, max_rewrites=2
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
                    stats["failed"] += 1

        logger.info("followup_draft_generation_complete", extra=stats)
        return stats

    def _review_and_rewrite(
        self, subject: str, body: str, lead: Dict, max_rewrites: int
    ) -> tuple:
        """
        Review an email and rewrite if needed. Returns (subject, body, score).
        Mirrors CampaignManager._review_and_rewrite_if_needed logic.
        """
        best_subject = subject
        best_body = body
        best_score = 0

        for attempt in range(max_rewrites + 1):
            try:
                review = self._reviewer.review_email(
                    subject=best_subject,
                    body=best_body,
                    lead=lead,
                )
                score = review.get("overall_score", 0)
                logger.debug(
                    "review_attempt",
                    extra={"attempt": attempt + 1, "score": score, "best_score": best_score},
                )

                if score > best_score:
                    best_score = score
                    best_subject = best_subject
                    best_body = best_body

                if score >= 70:
                    return best_subject, best_body, score

                # Try to rewrite if score is low and we have attempts left
                if attempt < max_rewrites:
                    rewritten = self._reviewer.rewrite_email(
                        subject=best_subject,
                        body=best_body,
                        lead=lead,
                        review=review,
                    )
                    if rewritten:
                        best_subject = rewritten.get("subject", best_subject)
                        best_body = rewritten.get("body", best_body)

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
