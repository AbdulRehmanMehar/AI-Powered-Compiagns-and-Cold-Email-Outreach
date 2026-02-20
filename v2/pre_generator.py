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
    campaigns_collection,
    db,
    emails_collection,
    leads_collection,
)
from email_verifier import EmailVerifier, VerificationStatus

logger = logging.getLogger("coldemails.pre_generator")

# ── Lead-replenishment & draft-activation thresholds ─────────────────
# Trigger a RocketReach fetch when a campaign has fewer than this many
# ready drafts AND fewer than this many unprocessed leads in the DB.
READY_LOW_THRESHOLD        = 50     # ready_to_send drafts below this → check further
PENDING_LOW_THRESHOLD      = 30     # unprocessed leads below this → fetch from RocketReach
FETCH_AMOUNT               = 200    # leads to request per replenishment call
MIN_FETCH_INTERVAL_SECS    = 7_200  # 2 h cooldown per campaign between RocketReach calls
REPLENISH_CHECK_INTERVAL   = 300    # only scan campaigns every 5 min
DRAFT_ACTIVATION_INTERVAL  = 1_800  # only scan for new draft campaigns every 30 min

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
        icp_template: str = None,
        is_icp: bool = None,
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
            "icp_template": icp_template,
            "is_icp": is_icp,
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

        # Auto-replenishment state
        self._last_fetch_times: Dict[str, datetime] = {}   # cid → last RocketReach call
        self._last_replenish_check: Optional[datetime] = None
        self._last_draft_check: Optional[datetime] = None
        self._activating_campaigns: Set[str] = set()  # guard against concurrent activations

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

        cycle_number = 0
        while not shutdown_event.is_set():
            try:
                cycle_number += 1
                cycle_generated = 0
                cycle_failed = 0
                cycle_skipped = 0
                campaign_stats: Dict[str, Dict] = {}  # cid -> per-campaign counters

                # ── Get active campaigns ──────────────────────────────
                active = Campaign.get_active_campaigns()
                if not active:
                    logger.warning("continuous_pregen: no active campaigns found — sleeping 120s")
                    await self._sleep_or_shutdown(shutdown_event, 120)
                    continue

                logger.info(
                    f"pregen_cycle_start: cycle={cycle_number} "
                    f"active_campaigns={len(active)}"
                )

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

                # Log lead-distribution summary across campaigns
                if pending:
                    dist_parts = [
                        f"{cid[:8]}={len(leads)}"
                        for cid, leads in leads_by_campaign.items()
                    ]
                    logger.info(
                        f"pregen_pending_leads: total={len(pending)} "
                        f"across {len(leads_by_campaign)} campaign(s): "
                        + " | ".join(dist_parts)
                    )
                else:
                    total_leads_in_db = leads_collection.count_documents({})
                    total_drafts = email_drafts_collection.count_documents(
                        {"status": {"$nin": [DraftStatus.FAILED, DraftStatus.SKIPPED]}}
                    )
                    logger.info(
                        f"pregen_pending_leads: total=0 (no unprocessed leads) — "
                        f"db_leads={total_leads_in_db} existing_drafts={total_drafts}"
                    )

                # ── Process each campaign ─────────────────────────────
                for campaign in active:
                    if shutdown_event.is_set():
                        break

                    cid = str(campaign["_id"])
                    c_name = str(campaign.get("name", ""))[:40]
                    campaign_stats[cid] = {"generated": 0, "failed": 0, "skipped": 0}

                    # Per-campaign queue depth for context
                    c_ready = email_drafts_collection.count_documents(
                        {"campaign_id": campaign["_id"], "status": DraftStatus.READY}
                    )

                    # Step 1: Initial drafts for pending leads
                    campaign_leads = leads_by_campaign.get(cid, [])
                    if campaign_leads:
                        logger.info(
                            f"pregen_initial_start: campaign={cid[:8]}... "
                            f"name={c_name!r} leads={len(campaign_leads)} ready_queue={c_ready}"
                        )
                        stats = await self.generate_initial_drafts(
                            cid, campaign_leads, max_rewrites=2
                        )
                        campaign_stats[cid]["generated"] += stats.get("generated", 0)
                        campaign_stats[cid]["failed"]    += stats.get("failed", 0)
                        campaign_stats[cid]["skipped"]   += stats.get("skipped", 0)
                        cycle_generated += stats.get("generated", 0)
                        cycle_failed    += stats.get("failed", 0)
                        cycle_skipped   += stats.get("skipped", 0)
                    else:
                        logger.debug(
                            f"pregen_no_pending_leads: campaign={cid[:8]}... "
                            f"name={c_name!r} ready_queue={c_ready}"
                        )

                    # Step 2: Followup drafts
                    f_stats = await self.generate_followup_drafts(cid)
                    campaign_stats[cid]["generated"] += f_stats.get("generated", 0)
                    campaign_stats[cid]["failed"]    += f_stats.get("failed", 0)
                    campaign_stats[cid]["skipped"]   += f_stats.get("skipped", 0)
                    cycle_generated += f_stats.get("generated", 0)
                    cycle_failed    += f_stats.get("failed", 0)
                    cycle_skipped   += f_stats.get("skipped", 0)

                    if f_stats.get("generated", 0) or f_stats.get("failed", 0):
                        logger.info(
                            f"pregen_followup_result: campaign={cid[:8]}... "
                            f"generated={f_stats.get('generated', 0)} "
                            f"failed={f_stats.get('failed', 0)} "
                            f"skipped={f_stats.get('skipped', 0)}"
                        )

                # ── Housekeeping ──────────────────────────────────────
                EmailDraft.cleanup_stale_claimed(timeout_minutes=30)

                # ── Auto-replenishment ────────────────────────────────
                # Fetch more leads from RocketReach when a campaign's
                # pipeline runs dry, and activate new ICP draft campaigns
                # without manual intervention.
                await self._replenish_leads_if_needed(shutdown_event, cm, active)
                await self._activate_draft_campaigns(shutdown_event, cm)

                # ── Adaptive sleep ────────────────────────────────────
                ready = EmailDraft.get_ready_count()
                draft_stats = EmailDraft.get_stats()

                if cycle_generated > 0:
                    per_campaign_summary = " | ".join(
                        f"{cid[:8]}=+{cs['generated']}"
                        for cid, cs in campaign_stats.items()
                        if cs["generated"] > 0
                    )
                    logger.info(
                        f"pregen_cycle_complete: cycle={cycle_number} "
                        f"generated={cycle_generated} failed={cycle_failed} "
                        f"skipped={cycle_skipped} ready_queue={ready} "
                        f"all_statuses={draft_stats} "
                        f"per_campaign=[{per_campaign_summary}]"
                    )
                    # Generated drafts — check again soon
                    sleep_secs = 30
                else:
                    logger.info(
                        f"pregen_cycle_idle: cycle={cycle_number} "
                        f"ready_queue={ready} failed={cycle_failed} "
                        f"skipped={cycle_skipped} sleeping=120s"
                    )
                    # Nothing to do — wait 2 min before rechecking
                    sleep_secs = 120

                await self._sleep_or_shutdown(shutdown_event, sleep_secs)

            except Exception as e:
                logger.error(f"continuous_pregen_error: cycle={cycle_number} {e}", exc_info=True)
                await self._sleep_or_shutdown(shutdown_event, 60)

        logger.info(f"continuous_pregen_stopped: ran {cycle_number} cycles")

    # ── Auto-replenishment methods ───────────────────────────────────

    async def _replenish_leads_if_needed(
        self,
        shutdown_event: asyncio.Event,
        cm,
        active_campaigns: List[Dict],
    ) -> None:
        """
        For every active campaign that is running low on both ready drafts
        AND unprocessed leads in the DB, fetch more leads from RocketReach.

        Guardrails:
        - Only runs every REPLENISH_CHECK_INTERVAL seconds (not every 30 s cycle).
        - Per-campaign cooldown of MIN_FETCH_INTERVAL_SECS to avoid hammering
          the RocketReach API.
        """
        now = datetime.utcnow()
        if (
            self._last_replenish_check is not None
            and (now - self._last_replenish_check).total_seconds() < REPLENISH_CHECK_INTERVAL
        ):
            return
        self._last_replenish_check = now

        logger.info(
            f"replenish_scan_start: checking {len(active_campaigns)} active campaign(s) "
            f"(thresholds: ready<{READY_LOW_THRESHOLD}, unprocessed<{PENDING_LOW_THRESHOLD})"
        )
        triggered_count = 0
        skipped_healthy = 0

        for campaign in active_campaigns:
            if shutdown_event.is_set():
                break
            cid = str(campaign["_id"])
            c_name = str(campaign.get("name", ""))[:40]

            # Fast-path: enough ready drafts → skip the heavier DB queries
            ready = email_drafts_collection.count_documents(
                {"campaign_id": campaign["_id"], "status": DraftStatus.READY}
            )
            if ready >= READY_LOW_THRESHOLD:
                skipped_healthy += 1
                logger.debug(
                    f"replenish_skip_healthy: campaign={cid[:8]}... "
                    f"name={c_name!r} ready={ready} (>= threshold {READY_LOW_THRESHOLD})"
                )
                continue

            # Count leads that haven't been drafted yet for this campaign
            all_lead_ids = set(
                str(d["_id"])
                for d in leads_collection.find(
                    {"campaign_id": campaign["_id"]}, {"_id": 1}
                )
            )
            drafted_lead_ids = set(
                str(d["lead_id"])
                for d in email_drafts_collection.find(
                    {
                        "campaign_id": campaign["_id"],
                        "status": {"$nin": [DraftStatus.FAILED, DraftStatus.SKIPPED]},
                    },
                    {"lead_id": 1},
                )
            )
            total_leads = len(all_lead_ids)
            unprocessed = len(all_lead_ids - drafted_lead_ids)

            logger.info(
                f"replenish_assessment: campaign={cid[:8]}... name={c_name!r} "
                f"ready={ready} total_leads={total_leads} unprocessed={unprocessed} "
                f"drafted={len(drafted_lead_ids)}"
            )

            if unprocessed >= PENDING_LOW_THRESHOLD:
                logger.info(
                    f"replenish_not_needed: campaign={cid[:8]}... "
                    f"unprocessed={unprocessed} >= threshold {PENDING_LOW_THRESHOLD} — "
                    f"pipeline will recover on its own"
                )
                continue

            # Per-campaign rate-limit guard
            last_fetch = self._last_fetch_times.get(cid)
            if last_fetch:
                elapsed = (now - last_fetch).total_seconds()
                if elapsed < MIN_FETCH_INTERVAL_SECS:
                    remaining_min = (MIN_FETCH_INTERVAL_SECS - elapsed) / 60
                    logger.info(
                        f"replenish_rate_limited: campaign={cid[:8]}... "
                        f"name={c_name!r} last_fetch={last_fetch.strftime('%H:%M UTC')} "
                        f"cooldown_remaining={remaining_min:.0f}min"
                    )
                    continue

            # Both thresholds breached — fetch more leads
            triggered_count += 1
            logger.info(
                f"replenish_triggered: campaign={cid[:8]}... name={c_name!r} "
                f"ready={ready} unprocessed={unprocessed} — "
                f"fetching {FETCH_AMOUNT} leads from RocketReach"
            )
            try:
                leads_fetched = await asyncio.to_thread(
                    cm.fetch_leads_for_campaign, cid, FETCH_AMOUNT
                )
                count = len(leads_fetched) if leads_fetched else 0
                self._last_fetch_times[cid] = datetime.utcnow()
                logger.info(
                    f"replenish_complete: campaign={cid[:8]}... name={c_name!r} "
                    f"fetched={count} new_total_leads={total_leads + count}"
                )
            except Exception as e:
                logger.error(
                    f"replenish_error: campaign={cid[:8]}... name={c_name!r} — {e}",
                    exc_info=True,
                )

        logger.info(
            f"replenish_scan_complete: campaigns_checked={len(active_campaigns)} "
            f"healthy_skipped={skipped_healthy} triggered={triggered_count}"
        )

    async def _activate_draft_campaigns(
        self,
        shutdown_event: asyncio.Event,
        cm,
    ) -> None:
        """
        Detect campaigns in 'draft' status that have target_criteria configured
        and fetch leads for them, then set them to 'active' automatically.

        This is what would have handled the Feb 17-19 ICP change campaigns
        without requiring manual intervention — the system now self-heals.

        Guardrails:
        - Only runs every DRAFT_ACTIVATION_INTERVAL seconds.
        - Per-campaign cooldown of MIN_FETCH_INTERVAL_SECS.
        - _activating_campaigns set prevents concurrent duplicate activations.
        """
        now = datetime.utcnow()
        if (
            self._last_draft_check is not None
            and (now - self._last_draft_check).total_seconds() < DRAFT_ACTIVATION_INTERVAL
        ):
            return
        self._last_draft_check = now

        # Only consider campaigns that have target_criteria with job titles configured
        draft_campaigns = list(
            campaigns_collection.find(
                {
                    "status": Campaign.STATUS_DRAFT,
                    "target_criteria.current_title": {"$exists": True, "$ne": []},
                }
            )
        )

        if not draft_campaigns:
            logger.debug("draft_activation_scan: no draft campaigns with configured criteria")
            return

        logger.info(
            f"draft_activation_scan: found {len(draft_campaigns)} draft campaign(s) "
            f"with configured criteria — evaluating each"
        )
        for campaign in draft_campaigns:
            c_name = str(campaign.get("name", ""))[:40]
            logger.info(
                f"  draft_candidate: {str(campaign['_id'])[:8]}... "
                f"name={c_name!r} "
                f"created={str(campaign.get('created_at', '?'))[:16]}"
            )

        activated_count = 0
        for campaign in draft_campaigns:
            if shutdown_event.is_set():
                break
            cid = str(campaign["_id"])
            c_name = str(campaign.get("name", ""))[:40]

            # Guard against concurrent processing of the same campaign
            if cid in self._activating_campaigns:
                logger.debug(
                    f"draft_activation_skip_concurrent: {cid[:8]}... "
                    f"name={c_name!r} — already activating"
                )
                continue

            lead_count = leads_collection.count_documents(
                {"campaign_id": campaign["_id"]}
            )

            if lead_count > 0:
                # Already has leads fetched — just flip it active
                Campaign.update_status(cid, Campaign.STATUS_ACTIVE)
                activated_count += 1
                logger.info(
                    f"draft_activated_existing_leads: {cid[:8]}... "
                    f"name={c_name!r} leads={lead_count} — set to active immediately"
                )
                continue

            # Per-campaign rate-limit guard (avoid spamming RocketReach on errors)
            last_fetch = self._last_fetch_times.get(cid)
            if last_fetch:
                elapsed = (now - last_fetch).total_seconds()
                if elapsed < MIN_FETCH_INTERVAL_SECS:
                    remaining_min = (MIN_FETCH_INTERVAL_SECS - elapsed) / 60
                    logger.info(
                        f"draft_activation_rate_limited: {cid[:8]}... "
                        f"name={c_name!r} cooldown_remaining={remaining_min:.0f}min"
                    )
                    continue

            self._activating_campaigns.add(cid)
            logger.info(
                f"draft_activation_start: {cid[:8]}... name={c_name!r} "
                f"leads_in_db=0 — fetching {FETCH_AMOUNT} leads from RocketReach"
            )
            try:
                leads_fetched = await asyncio.to_thread(
                    cm.fetch_leads_for_campaign, cid, FETCH_AMOUNT
                )
                count = len(leads_fetched) if leads_fetched else 0
                self._last_fetch_times[cid] = datetime.utcnow()

                # Activate regardless — even 0 leads means the campaign is
                # configured; it will get more on the next replenishment cycle
                Campaign.update_status(cid, Campaign.STATUS_ACTIVE)
                activated_count += 1
                logger.info(
                    f"draft_activated: {cid[:8]}... name={c_name!r} "
                    f"fetched={count} status=draft->active"
                )
            except Exception as e:
                logger.error(
                    f"draft_activation_error: {cid[:8]}... name={c_name!r} — {e}",
                    exc_info=True,
                )
            finally:
                self._activating_campaigns.discard(cid)

        logger.info(
            f"draft_activation_complete: candidates={len(draft_campaigns)} "
            f"activated={activated_count}"
        )

    # ── Draft generation methods ─────────────────────────────────────

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

        skip_reasons: Dict[str, int] = {
            "draft_exists": 0, "dnc": 0, "already_contacted": 0,
            "email_invalid_flag": 0, "verify_failed": 0, "catch_all": 0,
        }

        for i, lead in enumerate(leads, 1):
            lead_id = str(lead["_id"])
            to_email = lead.get("email", "")
            lead_name = (
                f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip() or "?"
            )

            logger.debug(
                f"initial_lead_eval: [{i}/{len(leads)}] lead={lead_id[:8]}... "
                f"email={to_email} name={lead_name!r}"
            )

            # Skip if draft already exists
            if EmailDraft.has_draft_for_lead(lead_id, campaign_id, "initial"):
                skip_reasons["draft_exists"] += 1
                stats["skipped"] += 1
                logger.debug(f"initial_skip_draft_exists: {to_email} lead={lead_id[:8]}...")
                continue

            # Skip DNC
            if DoNotContact.is_blocked(to_email):
                skip_reasons["dnc"] += 1
                stats["skipped"] += 1
                logger.info(f"initial_skip_dnc: {to_email} lead={lead_id[:8]}...")
                continue

            # Skip already contacted
            if Email.has_been_contacted_by_email(to_email):
                skip_reasons["already_contacted"] += 1
                stats["skipped"] += 1
                logger.info(f"initial_skip_already_contacted: {to_email} lead={lead_id[:8]}...")
                continue

            # ── EMAIL VERIFICATION: Skip invalid emails BEFORE generating ──
            if lead.get("email_invalid"):
                skip_reasons["email_invalid_flag"] += 1
                stats["skipped"] += 1
                logger.info(
                    f"initial_skip_invalid_flag: {to_email} lead={lead_id[:8]}... "
                    f"reason={lead.get('invalid_reason', 'pre-marked invalid')!r}"
                )
                continue

            # Check if we have recent verification (within 7 days)
            verification_date = lead.get("verification_date")
            needs_reverify = True
            if verification_date:
                age_days = (datetime.now() - verification_date).days
                if age_days <= 7 and lead.get("verification_status") == "valid":
                    needs_reverify = False
                    logger.debug(
                        f"initial_verify_cached: {to_email} "
                        f"age={age_days}d status=valid — skipping re-verify"
                    )

            if needs_reverify:
                logger.debug(f"initial_verify_start: {to_email} lead={lead_id[:8]}...")
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

                    logger.info(
                        f"initial_verify_result: {to_email} lead={lead_id[:8]}... "
                        f"status={verification.status.value} score={verification.score} "
                        f"reason={verification.reason!r}"
                    )

                    if verification.status == VerificationStatus.INVALID:
                        skip_reasons["verify_failed"] += 1
                        Lead.mark_invalid_email(lead_id, f"Verification failed: {verification.reason}")
                        stats["skipped"] += 1
                        logger.info(
                            f"initial_skip_verify_failed: {to_email} lead={lead_id[:8]}... "
                            f"reason={verification.reason!r}"
                        )
                        continue
                    elif verification.status == VerificationStatus.RISKY:
                        if verification.checks.get("is_catch_all"):
                            skip_reasons["catch_all"] += 1
                            Lead.mark_invalid_email(lead_id, f"Catch-all domain: {verification.reason}")
                            stats["skipped"] += 1
                            logger.info(
                                f"initial_skip_catch_all: {to_email} lead={lead_id[:8]}... "
                                f"reason={verification.reason!r}"
                            )
                            continue
                        logger.warning(
                            f"initial_verify_risky: {to_email} lead={lead_id[:8]}... "
                            f"reason={verification.reason!r} — proceeding anyway"
                        )
                except Exception as e:
                    logger.error(
                        f"initial_verify_error: {to_email} lead={lead_id[:8]}... {e} "
                        f"— proceeding (may be network issue)"
                    )

            try:
                _icp_template = campaign_context.get("icp_template")
                _is_icp = bool(_icp_template)

                draft_id = EmailDraft.create(
                    lead_id=lead_id,
                    campaign_id=campaign_id,
                    email_type="initial",
                    to_email=to_email,
                    to_name=lead.get("first_name"),
                    icp_template=_icp_template,
                    is_icp=_is_icp,
                )
                logger.debug(
                    f"initial_draft_placeholder: draft={draft_id[:8]}... "
                    f"lead={lead_id[:8]}... email={to_email}"
                )

                # Generate email
                email_data = self._generator.generate_initial_email(
                    lead=lead,
                    campaign_context=campaign_context
                )
                if not email_data:
                    EmailDraft.mark_failed(draft_id, "Generation returned None")
                    stats["failed"] += 1
                    logger.error(
                        f"initial_generation_none: draft={draft_id[:8]}... "
                        f"lead={lead_id[:8]}... email={to_email}"
                    )
                    continue

                subject = email_data.get("subject", "")
                body = email_data.get("body", "")
                logger.debug(
                    f"initial_generated_raw: draft={draft_id[:8]}... "
                    f"subject={subject[:60]!r} body_len={len(body)}"
                )

                # Review + rewrite loop
                final_subject, final_body, score = self._review_and_rewrite(
                    subject, body, lead, campaign_context, max_rewrites
                )

                if score >= 70:
                    EmailDraft.mark_ready(draft_id, final_subject, final_body, score)
                    stats["generated"] += 1
                    logger.info(
                        f"initial_draft_ready: draft={draft_id[:8]}... "
                        f"lead={lead_id[:8]}... email={to_email} "
                        f"score={score} subject={final_subject[:60]!r}"
                    )
                else:
                    EmailDraft.mark_review_failed(
                        draft_id, score, f"Best score {score} < 70"
                    )
                    stats["failed"] += 1
                    logger.warning(
                        f"initial_draft_review_failed: draft={draft_id[:8]}... "
                        f"lead={lead_id[:8]}... email={to_email} "
                        f"best_score={score} subject={final_subject[:60]!r}"
                    )

            except Exception as e:
                logger.error(
                    f"initial_draft_exception: lead={lead_id[:8]}... email={to_email} — {e}",
                    exc_info=True,
                )
                try:
                    EmailDraft.mark_failed(draft_id, str(e)[:500])
                except Exception:
                    pass
                stats["failed"] += 1

        logger.info(
            f"initial_draft_generation_complete: campaign={campaign_id[:8]}... "
            f"generated={stats['generated']} failed={stats['failed']} "
            f"skipped={stats['skipped']} skip_breakdown={skip_reasons}"
        )
        return stats

    async def generate_followup_drafts(self, campaign_id: str) -> Dict:
        """Pre-generate follow-up email drafts."""
        return await asyncio.to_thread(
            self._generate_followup_drafts_sync, campaign_id
        )

    def _generate_followup_drafts_sync(self, campaign_id: str) -> Dict:
        self._ensure_initialized()
        stats = {"generated": 0, "failed": 0, "skipped": 0}
        skip_reasons: Dict[str, int] = {
            "lead_not_found": 0, "dnc": 0, "max_followups": 0, "draft_exists": 0,
        }
        logger.debug(f"followup_draft_generation_start: campaign={campaign_id[:8]}...")

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

            logger.debug(
                f"followup_eligible: campaign={campaign_id[:8]}... "
                f"delay_days={delay_days} eligible_leads={len(pending)}"
            )

            for item in pending:
                lead_id = str(item["_id"])
                lead = Lead.get_by_id(lead_id)
                if not lead:
                    skip_reasons["lead_not_found"] += 1
                    stats["skipped"] += 1
                    logger.warning(
                        f"followup_skip_lead_not_found: lead={lead_id[:8]}... "
                        f"campaign={campaign_id[:8]}..."
                    )
                    continue

                to_email = lead.get("email", "")
                if DoNotContact.is_blocked(to_email):
                    skip_reasons["dnc"] += 1
                    stats["skipped"] += 1
                    logger.info(
                        f"followup_skip_dnc: {to_email} lead={lead_id[:8]}..."
                    )
                    continue

                email_count = item.get("email_count", 1)
                followup_number = email_count  # 1 = first follow-up, 2 = second

                if followup_number > config.MAX_FOLLOWUPS:
                    skip_reasons["max_followups"] += 1
                    stats["skipped"] += 1
                    logger.debug(
                        f"followup_skip_max_reached: {to_email} lead={lead_id[:8]}... "
                        f"email_count={email_count} max={config.MAX_FOLLOWUPS}"
                    )
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
                    skip_reasons["draft_exists"] += 1
                    stats["skipped"] += 1
                    logger.debug(
                        f"followup_skip_draft_exists: {to_email} lead={lead_id[:8]}... \"\n                        f\"followup_number={followup_number}\""
                    )
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
                    logger.debug(
                        f"followup_draft_placeholder: draft={draft_id[:8]}... "
                        f"lead={lead_id[:8]}... email={to_email} "
                        f"type={email_type} followup_number={followup_number}"
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
                        logger.error(
                            f"followup_generation_none: draft={draft_id[:8]}... "
                            f"lead={lead_id[:8]}... email={to_email} type={email_type}"
                        )
                        continue

                    subject = email_data.get("subject", "")
                    body = email_data.get("body", "")

                    final_subject, final_body, score = self._review_and_rewrite(
                        subject, body, lead, campaign_context, max_rewrites=2
                    )

                    if score >= 70:
                        EmailDraft.mark_ready(draft_id, final_subject, final_body, score)
                        stats["generated"] += 1
                        logger.info(
                            f"followup_draft_ready: draft={draft_id[:8]}... "
                            f"lead={lead_id[:8]}... email={to_email} "
                            f"type={email_type} followup_number={followup_number} "
                            f"score={score} subject={final_subject[:60]!r}"
                        )
                    else:
                        EmailDraft.mark_review_failed(
                            draft_id, score, f"Best score {score} < 70"
                        )
                        stats["failed"] += 1
                        logger.warning(
                            f"followup_draft_review_failed: draft={draft_id[:8]}... "
                            f"lead={lead_id[:8]}... email={to_email} "
                            f"type={email_type} best_score={score} "
                            f"subject={final_subject[:60]!r}"
                        )

                except Exception as e:
                    logger.error(
                        f"followup_draft_exception: lead={lead_id[:8]}... "
                        f"email={to_email} type={email_type} — {e}",
                        exc_info=True,
                    )
                    try:
                        EmailDraft.mark_failed(draft_id, str(e)[:500])
                    except Exception:
                        pass
                    stats["failed"] += 1

        logger.info(
            f"followup_draft_generation_complete: campaign={campaign_id[:8]}... "
            f"generated={stats['generated']} failed={stats['failed']} "
            f"skipped={stats['skipped']} skip_breakdown={skip_reasons}"
        )
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
