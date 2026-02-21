"""
V2 Async Scheduler — Orchestrates all workers in a single AsyncIO event loop.

Replaces auto_scheduler.py with:
- APScheduler for cron-like triggers with missed-job handling
- Concurrent IMAP checking (all 8 accounts in parallel)
- Continuous pre-generation pipeline (always running in background)
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
    │  │  • campaign (configurable)       │    │
    │  │  • reputation (daily 08:00)      │    │
    │  │  • daily_summary (17:00 ET)      │    │
    │  │  • adaptive_campaign (2hr cycle) │    │
    │  └──────────────────────────────────┘    │
    │                                          │
    │  ┌─────────────┐  ┌───────────────────┐  │
    │  │ AccountPool │  │  ImapWorker       │  │
    │  │ (locks +    │  │  (concurrent      │  │
    │  │  reputation)│  │   reply/bounce)   │  │
    │  └─────────────┘  └───────────────────┘  │
    │                                          │
    │  ┌──────────────────────────────────────┐│
    │  │ PreGenerator (continuous background) ││
    │  │ Keeps draft queue populated 24/7     ││
    │  └──────────────────────────────────────┘│
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

# Warmup system (separate module, runs every 4 hours)
try:
    from warmup_bidirectional import run_bidirectional_warmup_cycle
    WARMUP_AVAILABLE = config.WARMUP_ACCOUNTS and len(config.WARMUP_ACCOUNTS) > 0
except ImportError:
    WARMUP_AVAILABLE = False
    logger.warning("⚠️  warmup_bidirectional module not available")
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
        logger.info(f"Sender mode: {config.PRIMARY_SENDER_MODE.upper()}")
        logger.info(f"Accounts: {len(config.PRODUCTION_ACCOUNTS)} ({config.PRIMARY_SENDER_MODE})")
        logger.info(f"Sending hours: {config.SENDING_HOUR_START}:00 - {config.SENDING_HOUR_END}:00")
        logger.info(f"Hard cap/mailbox: {config.EMAILS_PER_DAY_PER_MAILBOX}")
        logger.info(f"Warmup: {'ON (week4+ cap=' + str(config.WARMUP_WEEK4_LIMIT) + ')' if config.WARMUP_ENABLED else 'OFF'}")
        logger.info(f"Warmup Bidirectional: {'ON' if WARMUP_AVAILABLE else 'OFF (no test accounts configured)'}")
        logger.info(f"Cooldown: {config.MIN_DELAY_BETWEEN_EMAILS}-{config.MAX_DELAY_BETWEEN_EMAILS} min base")
        if config.GLOBAL_DAILY_TARGET > 0:
            logger.info(f"Global target: {config.GLOBAL_DAILY_TARGET}/day → ~{-(-config.GLOBAL_DAILY_TARGET // len(config.PRODUCTION_ACCOUNTS))}/account")

        # Register signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_signal, sig)

        # Startup sequence (non-blocking IMAP check)
        await self._startup_phase()

        # Launch ALL persistent workers regardless of mode
        self._tasks = [
            asyncio.create_task(self.send_worker.run(), name="send_worker"),
            asyncio.create_task(self.imap_worker.run_periodic(interval_minutes=30), name="imap_worker"),
            asyncio.create_task(self.pre_generator.run_continuous(self._shutdown), name="pre_generator"),
            asyncio.create_task(self._scheduler_loop(), name="scheduler_loop"),
            asyncio.create_task(self._heartbeat_loop(), name="heartbeat"),
        ]

        # Warmup bidirectional (every 4 hours) — alongside campaigns
        if WARMUP_AVAILABLE:
            self._tasks.append(
                asyncio.create_task(self._warmup_loop(), name="warmup_worker")
            )
            logger.info("🔥 Warmup bidirectional: ENABLED (every 4 hours)")

        logger.info(f"Workers launched: {[t.get_name() for t in self._tasks]}")

        # Wait for shutdown
        await self._shutdown.wait()

        # Graceful shutdown
        await self._graceful_shutdown()

    async def _startup_phase(self):
        """Run startup checks (non-blocking IMAP)."""
        logger.info("── Startup Phase ──")

        # Clean expired blocks
        BlockedAccounts.cleanup_expired()

        # Release stale drafts
        EmailDraft.cleanup_stale_claimed()

        # Check holiday
        is_hol, hol_name = is_holiday()
        if is_hol:
            logger.warning(f"Today is {hol_name} — sending will be paused")

        # Initial IMAP check — non-blocking with 60s timeout so startup
        # never hangs (e.g. slow Gmail IMAP on warmup accounts).
        logger.info("Checking replies and bounces (60s timeout)...")
        try:
            imap_results = await asyncio.wait_for(
                self.imap_worker.check_all(), timeout=60
            )
            logger.info(
                f"IMAP: {imap_results['total_replies']} replies, "
                f"{imap_results['total_bounces']} bounces"
            )
        except asyncio.TimeoutError:
            logger.warning("IMAP startup check timed out (60s) — continuing, periodic check will retry")

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

        # Log pacing status — shows catch-up plan after restart
        now = datetime.now(self.tz)
        can_send, reason = self.pool._can_send_now()
        total_sent = sum(
            SendingStats.get_sends_today(a["email"]) for a in self.pool.accounts
        )
        remaining = max(0, config.GLOBAL_DAILY_TARGET - total_sent)
        hours_left = max(0, config.SENDING_HOUR_END - now.hour - now.minute / 60.0)

        if can_send and remaining > 0 and hours_left > 0:
            required_rate = remaining / hours_left
            active_accts = len([
                a for a in self.pool.accounts
                if not BlockedAccounts.is_blocked(a["email"])
            ])
            ideal_cooldown = 60.0 / (required_rate / max(1, active_accts))
            logger.info(
                f"── Pacing: {total_sent}/{config.GLOBAL_DAILY_TARGET} sent, "
                f"{remaining} remaining in {hours_left:.1f}h → "
                f"need {required_rate:.0f}/hr → "
                f"~{min(20, max(3, int(ideal_cooldown)))} min cooldown (dynamic)"
            )
        elif not can_send:
            logger.info(f"── Outside sending window: {reason}")
        else:
            logger.info(f"── Target met: {total_sent}/{config.GLOBAL_DAILY_TARGET} sent today")

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
                # Runs at: 07:00, 09:00, 11:00, 13:00, 15:00, 17:00
                # Ensures we hit GLOBAL_DAILY_TARGET by fetching more leads if needed
                if config.GLOBAL_DAILY_TARGET > 0:
                    adaptive_hours = [7, 9, 11, 13, 15, 17]
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
        Run a scheduled campaign — LEAD FETCHING ONLY.

        The legacy code used to generate AND send emails directly here,
        bypassing the draft pipeline. Now this only fetches fresh leads
        via RocketReach / ICP templates. The continuous pre-generator
        + send_worker handle drafting and sending.
        """
        name = camp_config.get("name", "unknown")
        max_leads = camp_config.get("max_leads", 15)

        # Only one campaign at a time
        if self._campaign_lock.locked():
            logger.warning(f"Campaign {name} skipped — another campaign is running")
            return

        async with self._campaign_lock:
            logger.info(f"Starting campaign (lead-fetch only): {name} (max_leads={max_leads})")

            try:
                is_hol, hol_name = is_holiday()
                if is_hol:
                    logger.info(f"Campaign {name} skipped — holiday ({hol_name})")
                    return

                manager = self._get_campaign_manager()

                # Only fetch leads — do NOT generate or send emails.
                # The pre-generator picks up new leads automatically.
                from database import SchedulerConfig
                selection = await asyncio.to_thread(
                    SchedulerConfig.select_icp_for_autonomous_run
                )
                selected_icp = selection["selected_icp"]

                logger.info(
                    f"Campaign {name}: fetching leads for ICP '{selected_icp}' "
                    f"(reason: {selection.get('selection_reason', 'N/A')})"
                )

                # Create campaign + fetch leads from RocketReach
                campaign_id = await asyncio.to_thread(
                    manager.create_campaign_from_icp, selected_icp
                )
                leads = await asyncio.to_thread(
                    manager.fetch_leads_for_campaign, campaign_id, max_leads
                )

                logger.info(
                    f"Campaign {name} completed — fetched {len(leads) if leads else 0} leads "
                    f"(ICP: {selected_icp}, campaign_id: {campaign_id}). "
                    f"Pre-generator will draft emails automatically."
                )

                # Record the run
                if leads:
                    await asyncio.to_thread(
                        SchedulerConfig.record_icp_run,
                        icp_template=selected_icp,
                        campaign_id=campaign_id,
                        leads_sent=0,  # We don't send here anymore
                        results={
                            "leads_fetched": len(leads),
                            "sent": 0,
                            "errors": 0,
                            "selection_mode": selection.get("selection_mode", "unknown"),
                            "note": "lead-fetch only, draft pipeline handles sending",
                        },
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
            
            # Leads were fetched — log and let continuous pre-gen handle drafting
            logger.info(
                f"Adaptive campaign completed: "
                f"fetched {result.get('fetched_leads', 0)} leads, "
                f"{result.get('sent_today', 0)}/{config.GLOBAL_DAILY_TARGET} sent today"
            )
            
        except Exception as e:
            logger.error(f"Adaptive campaign failed: {e}", exc_info=True)

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

    async def _warmup_loop(self):
        """
        Run bidirectional warmup cycle every 4 hours (non-blocking).
        
        Completely independent from campaign sending:
        - Generates templates via Groq
        - Sends to test Gmail accounts from Zoho
        - Monitors IMAP for placement (inbox vs spam)
        - Auto-replies with contextual messages
        
        Doesn't interfere with campaign pipeline (separate collection).
        """
        first_run = True
        warmup_interval_seconds = 4 * 3600  # 4 hours
        
        while not self._shutdown.is_set():
            try:
                if first_run:
                    logger.info("🔥 Starting bidirectional warmup cycle...")
                    first_run = False
                
                # Run warmup cycle (non-blocking)
                result = await run_bidirectional_warmup_cycle()
                
                # Log results
                sent = result.get("sent", 0)
                replies = result.get("replies", 0)
                placement = result.get("placement", {})
                inbox = placement.get("inbox", 0)
                spam = placement.get("spam", 0)
                spam_rate = placement.get("spam_rate", "N/A")
                
                logger.info(
                    f"🔥 Warmup cycle complete: "
                    f"sent={sent} replies={replies} "
                    f"inbox={inbox} spam={spam} ({spam_rate})"
                )
                
            except Exception as e:
                logger.error(f"❌ Warmup cycle failed: {e}", exc_info=True)
            
            # Wait for next cycle (4 hours) or until shutdown
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(), 
                    timeout=warmup_interval_seconds
                )
                break  # Shutdown requested
            except asyncio.TimeoutError:
                continue  # Next cycle

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
