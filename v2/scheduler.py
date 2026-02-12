"""
V2 Async Scheduler — Orchestrates all workers in a single AsyncIO event loop.

Replaces auto_scheduler.py with:
- APScheduler for cron-like triggers with missed-job handling
- Concurrent IMAP checking (all 8 accounts in parallel)
- Pre-generation pipeline running during off-hours
- Send worker processing drafts during business hours
- Campaign creation via asyncio.to_thread (wraps legacy CampaignManager)
- Graceful shutdown on SIGTERM / SIGINT
- Daily summary alerts

Architecture:
    ┌──────────────────────────────────────────┐
    │           AsyncIO Event Loop             │
    │                                          │
    │  ┌────────────┐  ┌────────────────────┐  │
    │  │ APScheduler│  │   SendWorker       │  │
    │  │ (triggers) │  │   (draft → SMTP)   │  │
    │  └─────┬──────┘  └────────────────────┘  │
    │        │                                 │
    │  ┌─────┴────────────────────────────┐    │
    │  │  Scheduled Tasks:                │    │
    │  │  • check_replies (every 30 min)  │    │
    │  │  • campaign (09:30, 14:30 ET)    │    │
    │  │  • reputation (daily)            │    │
    │  │  • daily_summary (17:00 ET)      │    │
    │  │  • pre_generate (17:30 ET)       │    │
    │  └──────────────────────────────────┘    │
    │                                          │
    │  ┌─────────────┐  ┌───────────────────┐  │
    │  │ AccountPool │  │  ImapWorker       │  │
    │  │ (locks +    │  │  (concurrent      │  │
    │  │  reputation)│  │   reply/bounce)   │  │
    │  └─────────────┘  └───────────────────┘  │
    └──────────────────────────────────────────┘
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, Optional

import pytz

# ── Logging setup ────────────────────────────────────────────────────

LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s %(message)s"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("v2_scheduler.log", mode="a"),
    ],
)
logger = logging.getLogger("coldemails.scheduler")

# ── Imports (after logging is configured) ────────────────────────────

import config
from database import (
    BlockedAccounts,
    Campaign,
    Email,
    SchedulerConfig,
    SendingStats,
    db,
)
from v2.account_pool import AccountPool, AccountReputation
from v2.alerts import (
    AlertLevel,
    alert_all_accounts_blocked,
    alert_high_bounce_rate,
    send_alert,
    send_daily_summary,
)
from v2.human_behavior import is_holiday, plan_daily_sessions
from v2.imap_worker import ImapWorker
from v2.pre_generator import EmailDraft, PreGenerator
from v2.send_worker import SendWorker


class AsyncScheduler:
    """
    Main orchestrator for the v2 cold email system.

    Lifecycle:
        scheduler = AsyncScheduler()
        await scheduler.start()   # blocks until SIGTERM/SIGINT
    """

    def __init__(self):
        self.pool = AccountPool()
        self.send_worker = SendWorker(self.pool)
        self.imap_worker = ImapWorker(since_days=7)
        self.pre_generator = PreGenerator()
        self.tz = pytz.timezone(config.TARGET_TIMEZONE)

        # Campaign manager (synchronous, run via to_thread)
        self._campaign_manager = None
        self._campaign_lock = asyncio.Lock()

        # Shutdown handling
        self._shutdown = asyncio.Event()
        self._tasks: list = []

    def _get_campaign_manager(self):
        """Lazy-init CampaignManager (heavy object)."""
        if self._campaign_manager is None:
            from campaign_manager import CampaignManager
            self._campaign_manager = CampaignManager()
        return self._campaign_manager

    async def start(self):
        """
        Main entry point. Sets up signal handlers, starts all workers,
        runs until shutdown signal.
        """
        logger.info("=" * 60)
        logger.info("Cold Email System v2 — Starting")
        logger.info("=" * 60)
        logger.info(f"Timezone: {config.TARGET_TIMEZONE}")
        logger.info(f"Accounts: {len(config.ZOHO_ACCOUNTS)}")
        logger.info(f"Sending hours: {config.SENDING_HOUR_START}:00 - {config.SENDING_HOUR_END}:00")
        logger.info(f"Daily limit/mailbox: {config.EMAILS_PER_DAY_PER_MAILBOX}")
        logger.info(f"Warmup: {'ON' if config.WARMUP_ENABLED else 'OFF'}")

        # Register signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_signal, sig)

        # Startup sequence
        await self._startup_phase()

        # Launch persistent workers
        self._tasks = [
            asyncio.create_task(self.send_worker.run(), name="send_worker"),
            asyncio.create_task(self.imap_worker.run_periodic(interval_minutes=30), name="imap_worker"),
            asyncio.create_task(self._scheduler_loop(), name="scheduler_loop"),
            asyncio.create_task(self._heartbeat_loop(), name="heartbeat"),
        ]

        logger.info("All workers launched — system running")

        # Wait for shutdown
        await self._shutdown.wait()

        # Graceful shutdown
        await self._graceful_shutdown()

    async def _startup_phase(self):
        """Run startup checks (same as legacy Phase 1-4 but concurrent)."""
        logger.info("── Startup Phase ──")

        # Clean expired blocks
        BlockedAccounts.cleanup_expired()

        # Release stale drafts
        EmailDraft.cleanup_stale_claimed()

        # Check holiday
        is_hol, hol_name = is_holiday()
        if is_hol:
            logger.warning(f"Today is {hol_name} — sending will be paused")

        # Initial IMAP check (replies + bounces)
        logger.info("Checking replies and bounces...")
        imap_results = await self.imap_worker.check_all()
        logger.info(
            f"IMAP: {imap_results['total_replies']} replies, "
            f"{imap_results['total_bounces']} bounces"
        )

        # Refresh account reputations
        await asyncio.to_thread(AccountReputation.refresh_all)

        # Log account status
        for status in self.pool.get_all_status():
            logger.info(
                f"  {status['email']}: "
                f"{status['sends_today']}/{status['daily_limit']} sent, "
                f"{'BLOCKED' if status['blocked'] else 'OK'}"
            )

        # Log draft queue
        draft_stats = EmailDraft.get_stats()
        logger.info(f"Draft queue: {draft_stats}")

        logger.info("── Startup Complete ──")

    async def _scheduler_loop(self):
        """
        Cron-like loop that triggers tasks at specific times.
        Checks every 60 seconds what needs to run.
        """
        logger.info("Scheduler loop started")

        # Track what we've run today to avoid duplicates
        last_run_dates: Dict[str, str] = {}

        while not self._shutdown.is_set():
            try:
                now = datetime.now(self.tz)
                today_str = now.strftime("%Y-%m-%d")
                current_time = now.strftime("%H:%M")
                current_hour = now.hour
                current_minute = now.minute

                # ── Scheduled campaign runs ──────────────────────────
                sched_config = SchedulerConfig.get_config()
                campaigns = sched_config.get("scheduled_campaigns", [])

                for camp in campaigns:
                    if not camp.get("enabled", True):
                        continue

                    # Check day of week
                    today_name = now.strftime("%A").lower()
                    allowed_days = [d.lower() for d in camp.get("days", [])]
                    if allowed_days and today_name not in allowed_days:
                        continue

                    # Check time (match HH:MM)
                    sched_time = camp.get("schedule_time", "")
                    run_key = f"campaign_{camp['name']}_{today_str}"

                    if current_time == sched_time and run_key not in last_run_dates:
                        last_run_dates[run_key] = today_str
                        asyncio.create_task(
                            self._run_campaign(camp),
                            name=f"campaign_{camp['name']}",
                        )

                # ── Daily reputation refresh (at 08:00) ──────────────
                rep_key = f"reputation_{today_str}"
                if current_hour == 8 and current_minute == 0 and rep_key not in last_run_dates:
                    last_run_dates[rep_key] = today_str
                    asyncio.create_task(
                        asyncio.to_thread(AccountReputation.refresh_all),
                        name="reputation_refresh",
                    )

                # ── Adaptive Campaign Check (every 2 hours during send window) ──
                # Runs at: 09:00, 11:00, 13:00, 15:00
                # Ensures we hit GLOBAL_DAILY_TARGET by fetching more leads if needed
                if config.GLOBAL_DAILY_TARGET > 0:
                    adaptive_hours = [9, 11, 13, 15]
                    if current_hour in adaptive_hours and current_minute == 0:
                        adaptive_key = f"adaptive_{today_str}_{current_hour}"
                        if adaptive_key not in last_run_dates:
                            last_run_dates[adaptive_key] = today_str
                            asyncio.create_task(
                                self._run_adaptive_campaign(),
                                name=f"adaptive_campaign_{current_hour}",
                            )

                # ── Daily summary (at 17:00) ─────────────────────────
                summary_key = f"summary_{today_str}"
                if current_hour == 17 and current_minute == 0 and summary_key not in last_run_dates:
                    last_run_dates[summary_key] = today_str
                    asyncio.create_task(
                        send_daily_summary(),
                        name="daily_summary",
                    )

                # ── Pre-generation (at 17:30 — after sending window) ─
                pregen_key = f"pregen_{today_str}"
                if current_hour == 17 and current_minute == 30 and pregen_key not in last_run_dates:
                    last_run_dates[pregen_key] = today_str
                    asyncio.create_task(
                        self._run_pre_generation(),
                        name="pre_generation",
                    )

                # ── Cleanup old run tracking (keep only today) ────────
                last_run_dates = {
                    k: v for k, v in last_run_dates.items() if v == today_str
                }

            except Exception as e:
                logger.error(f"Scheduler loop error: {e}", exc_info=True)

            # Sleep for 60 seconds or until shutdown
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=60)
                break
            except asyncio.TimeoutError:
                continue

        logger.info("Scheduler loop stopped")

    async def _run_campaign(self, camp_config: Dict):
        """
        Run a scheduled campaign via the legacy CampaignManager.
        Uses asyncio.to_thread() to not block the event loop.
        """
        name = camp_config.get("name", "unknown")
        max_leads = camp_config.get("max_leads", 15)

        # Only one campaign at a time
        if self._campaign_lock.locked():
            logger.warning(f"Campaign {name} skipped — another campaign is running")
            return

        async with self._campaign_lock:
            logger.info(f"Starting campaign: {name} (max_leads={max_leads})")

            try:
                is_hol, hol_name = is_holiday()
                if is_hol:
                    logger.info(f"Campaign {name} skipped — holiday ({hol_name})")
                    return

                manager = self._get_campaign_manager()

                if camp_config.get("autonomous", False):
                    result = await asyncio.to_thread(
                        manager.run_autonomous_campaign,
                        max_leads=max_leads,
                        dry_run=False,
                    )
                else:
                    # Non-autonomous: send follow-ups for all active campaigns
                    active_campaigns = Campaign.get_active_campaigns()
                    result = []
                    for ac in active_campaigns:
                        cid = str(ac["_id"])
                        r = await asyncio.to_thread(
                            manager.send_followup_emails, cid
                        )
                        result.append(r)

                logger.info(
                    f"Campaign {name} completed",
                    extra={"result": str(result)[:200] if result else "None"},
                )

            except Exception as e:
                logger.error(f"Campaign {name} failed: {e}", exc_info=True)
                await send_alert(
                    f"Campaign `{name}` failed:\n```{str(e)[:300]}```",
                    AlertLevel.CRITICAL,
                )

    async def _run_adaptive_campaign(self):
        """
        Adaptive campaign runner — checks if we're on track for GLOBAL_DAILY_TARGET
        and fetches more leads if needed (accounting for skips/bounces/DNC).
        
        CRITICAL: Also triggers pre-generation immediately after fetching leads
        so drafts are ready to send (not waiting until 17:30).
        """
        try:
            from adaptive_campaign import run_adaptive_campaign_check
            
            logger.info("Running adaptive campaign check...")
            result = await asyncio.to_thread(run_adaptive_campaign_check)
            
            if result["status"] == "skipped":
                logger.info(f"Adaptive campaign skipped: {result.get('reason')}")
                return
            elif result["status"] == "target_met":
                logger.info(f"Daily target already met: {result.get('message')}")
                return
            
            # Leads were fetched — now generate drafts immediately
            logger.info(
                f"Adaptive campaign completed: "
                f"fetched {result.get('fetched_leads', 0)} leads, "
                f"{result.get('sent_today', 0)}/{config.GLOBAL_DAILY_TARGET} sent today"
            )
            
            # CRITICAL: Trigger pre-generation NOW so drafts are ready to send
            logger.info("Triggering pre-generation for newly fetched leads...")
            await self._run_pre_generation()
            
        except Exception as e:
            logger.error(f"Adaptive campaign failed: {e}", exc_info=True)

    async def _run_pre_generation(self):
        """
        Run pre-generation for both initial emails and followups.
        
        CRITICAL: Must generate initial drafts for newly fetched leads,
        not just followups for existing campaigns.
        """
        logger.info("Starting pre-generation run")

        try:
            # Get active campaigns
            active = Campaign.get_active_campaigns()
            if not active:
                logger.info("No active campaigns for pre-generation")
                return

            total_stats = {"generated": 0, "failed": 0, "skipped": 0, "initial": 0, "followups": 0}

            for campaign in active:
                cid = str(campaign["_id"])
                
                # ── STEP 1: Generate INITIAL drafts for pending leads ──
                # Get pending leads for this campaign (no email sent yet)
                cm = self._get_campaign_manager()
                pending = await asyncio.to_thread(cm.get_pending_leads, max_leads=200)
                
                # Filter to only this campaign's leads
                campaign_leads = [
                    l for l in pending 
                    if str(l.get("campaign_id")) == cid
                ]
                
                if campaign_leads:
                    logger.info(f"Generating {len(campaign_leads)} initial drafts for campaign {cid}")
                    initial_stats = await self.pre_generator.generate_initial_drafts(
                        campaign_id=cid,
                        leads=campaign_leads,
                        max_rewrites=2
                    )
                    total_stats["initial"] += initial_stats.get("generated", 0)
                    total_stats["generated"] += initial_stats.get("generated", 0)
                    total_stats["failed"] += initial_stats.get("failed", 0)
                    total_stats["skipped"] += initial_stats.get("skipped", 0)

                # ── STEP 2: Generate FOLLOWUP drafts ──
                followup_stats = await self.pre_generator.generate_followup_drafts(cid)
                total_stats["followups"] += followup_stats.get("generated", 0)
                total_stats["generated"] += followup_stats.get("generated", 0)
                total_stats["failed"] += followup_stats.get("failed", 0)
                total_stats["skipped"] += followup_stats.get("skipped", 0)

            logger.info(
                "Pre-generation complete",
                extra=total_stats,
            )

        except Exception as e:
            logger.error(f"Pre-generation failed: {e}", exc_info=True)

    async def _heartbeat_loop(self):
        """Write heartbeat to MongoDB every 5 minutes for health monitoring."""
        heartbeat_collection = db["heartbeat"]

        while not self._shutdown.is_set():
            try:
                now = datetime.utcnow()
                heartbeat_collection.update_one(
                    {"_id": "v2_scheduler"},
                    {
                        "$set": {
                            "last_heartbeat": now,
                            "pid": os.getpid(),
                            "version": "v2",
                        }
                    },
                    upsert=True,
                )
            except Exception as e:
                logger.error(f"Heartbeat write failed: {e}")

            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=300)
                break
            except asyncio.TimeoutError:
                continue

    def _handle_signal(self, sig):
        """Handle SIGTERM / SIGINT for graceful shutdown."""
        logger.info(f"Received signal {sig.name} — initiating graceful shutdown")
        self._shutdown.set()

    async def _graceful_shutdown(self):
        """
        Graceful shutdown:
        1. Signal all workers to stop
        2. Wait for in-flight operations (max 15s)
        3. Release resources
        """
        logger.info("── Graceful Shutdown ──")

        # Signal workers
        self.send_worker.request_shutdown()
        self.imap_worker.request_shutdown()

        # Wait for tasks to finish (with timeout)
        if self._tasks:
            done, pending = await asyncio.wait(
                self._tasks, timeout=15, return_when=asyncio.ALL_COMPLETED
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Final heartbeat
        try:
            db["heartbeat"].update_one(
                {"_id": "v2_scheduler"},
                {"$set": {"status": "stopped", "stopped_at": datetime.utcnow()}},
            )
        except Exception:
            pass

        logger.info("Shutdown complete")


async def main():
    """Entry point for the v2 scheduler."""
    scheduler = AsyncScheduler()
    await scheduler.start()
