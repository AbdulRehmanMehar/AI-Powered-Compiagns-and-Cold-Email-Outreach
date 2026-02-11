"""
Integration tests for the v2 cold email system.

Tests the end-to-end flows across multiple modules working together:
- Draft creation → claim → send → record flow
- Account pool → eligibility → acquire → release cycle
- IMAP worker → reply/bounce → DNC updates
- Human behavior → session planning → send decisions
- Pre-generator → review → ready/failed transitions
- Scheduler lifecycle (startup, loop, shutdown)
"""

import asyncio
import unittest
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from bson import ObjectId
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestDraftToSendFlow(unittest.TestCase):
    """
    Integration: Draft lifecycle from creation through send.
    Tests the interaction between PreGenerator, EmailDraft, SendWorker.
    """

    @patch("v2.pre_generator.email_drafts_collection")
    def test_create_mark_ready_claim_send(self, mock_coll):
        """Full lifecycle: create → mark_ready → claim → mark_sent."""
        from v2.pre_generator import EmailDraft, DraftStatus

        draft_oid = ObjectId()
        mock_coll.insert_one.return_value = MagicMock(inserted_id=draft_oid)

        # Step 1: Create
        draft_id = EmailDraft.create(
            lead_id=str(ObjectId()),
            campaign_id=str(ObjectId()),
            email_type="initial",
            to_email="lead@example.com",
            to_name="Lead",
        )
        self.assertEqual(draft_id, str(draft_oid))

        # Step 2: Mark ready
        EmailDraft.mark_ready(draft_id, "Great Subject", "Great body", 85)
        update_call = mock_coll.update_one.call_args
        self.assertEqual(update_call[0][1]["$set"]["status"], DraftStatus.READY)

        # Step 3: Claim (simulate findOneAndUpdate)
        mock_coll.find_one_and_update.return_value = {
            "_id": draft_oid,
            "to_email": "lead@example.com",
            "email_type": "initial",
            "status": DraftStatus.CLAIMED,
            "subject": "Great Subject",
            "body": "Great body",
        }
        claimed = EmailDraft.claim_next_ready()
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["status"], DraftStatus.CLAIMED)

        # Step 4: Mark sent
        mock_coll.update_one.reset_mock()
        EmailDraft.mark_sent(draft_id, "<msg@test.com>", "sender@test.com")
        update_call = mock_coll.update_one.call_args
        self.assertEqual(update_call[0][1]["$set"]["status"], DraftStatus.SENT)

    @patch("v2.pre_generator.email_drafts_collection")
    def test_failed_draft_lifecycle(self, mock_coll):
        """Draft that fails: create → mark_failed."""
        from v2.pre_generator import EmailDraft, DraftStatus

        mock_coll.insert_one.return_value = MagicMock(inserted_id=ObjectId())

        draft_id = EmailDraft.create(
            lead_id=str(ObjectId()),
            campaign_id=str(ObjectId()),
            email_type="initial",
            to_email="lead@example.com",
        )

        EmailDraft.mark_failed(draft_id, "Generation returned None")
        update_call = mock_coll.update_one.call_args
        self.assertEqual(update_call[0][1]["$set"]["status"], DraftStatus.FAILED)
        self.assertEqual(update_call[0][1]["$inc"]["retry_count"], 1)

    @patch("v2.pre_generator.email_drafts_collection")
    def test_crashed_draft_cleanup(self, mock_coll):
        """Draft claimed but never sent (crash) → cleanup releases it."""
        from v2.pre_generator import EmailDraft, DraftStatus

        mock_coll.insert_one.return_value = MagicMock(inserted_id=ObjectId())
        mock_coll.update_many.return_value = MagicMock(modified_count=2)

        # Simulate: 2 drafts were claimed 45 min ago (stale)
        EmailDraft.cleanup_stale_claimed(timeout_minutes=30)
        mock_coll.update_many.assert_called_once()
        call_args = mock_coll.update_many.call_args
        query = call_args[0][0]
        self.assertEqual(query["status"], DraftStatus.CLAIMED)
        update = call_args[0][1]
        self.assertEqual(update["$set"]["status"], DraftStatus.READY)


class TestAccountAcquireRelease(unittest.TestCase):
    """
    Integration: Account acquire → send → record → release cycle.
    Tests AccountPool + human_behavior domain tracker interaction.
    """

    @patch("v2.account_pool.WarmDown")
    @patch("v2.account_pool.AccountReputation")
    @patch("v2.account_pool.AccountCooldown")
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.domain_tracker")
    @patch("v2.account_pool.config")
    def test_acquire_send_release_cycle(
        self, mock_config, mock_tracker, mock_blocked, mock_stats, mock_cooldown, mock_rep, mock_warmdown
    ):
        from v2.account_pool import AccountPool

        mock_config.ZOHO_ACCOUNTS = [
            {"email": "a@test.com", "password": "p", "sender_name": "A"},
        ]
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.SENDING_HOUR_START = 9
        mock_config.SENDING_HOUR_END = 17
        mock_config.SEND_ON_WEEKENDS = True
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 25
        mock_config.WARMUP_ENABLED = False
        mock_blocked.cleanup_expired.return_value = None
        mock_blocked.is_blocked.return_value = False
        mock_stats.get_sends_today.return_value = 5
        mock_stats.get_account_age_days.return_value = 30
        mock_cooldown.is_available.return_value = True
        mock_rep.get_saved_score.return_value = {"score": 90}
        mock_rep.PAUSE_THRESHOLD = 40
        mock_tracker.can_send_to.return_value = True
        mock_warmdown.get_warmdown_limit.return_value = None

        pool = AccountPool()

        async def test():
            # Force business hours
            with patch.object(pool, "_can_send_now", return_value=(True, "OK")):
                # Acquire
                account = await pool.acquire_account(to_email="target@example.com")
                self.assertIsNotNone(account)
                self.assertEqual(account["email"], "a@test.com")

                # Release
                pool.release_account("a@test.com")

                # Record send
                await pool.record_send("a@test.com", "target@example.com")
                mock_stats.increment_send.assert_called_with("a@test.com")
                mock_tracker.record_send.assert_called_with("target@example.com")

        run_async(test())


class TestHumanBehaviorIntegration(unittest.TestCase):
    """
    Integration: Human behavior functions used together
    for a realistic send decision flow.
    """

    def test_session_plan_and_check(self):
        """Plan sessions, then verify time checks against them."""
        from v2.human_behavior import plan_daily_sessions, is_within_session, next_session_start

        sessions = plan_daily_sessions(
            session_count=2,
            daily_limit=10,
            send_start_hour=9,
            send_end_hour=17,
        )
        self.assertGreater(len(sessions), 0)

        # Check: time within the first session should be True
        first = sessions[0]
        in_session_time = datetime(
            2025, 1, 6,
            first.start_hour,
            first.start_minute + 1,  # 1 min after start
        )
        in_session, curr = is_within_session(sessions, in_session_time)
        self.assertTrue(in_session)

        # Check: time before all sessions should be False
        early = datetime(2025, 1, 6, 7, 0)
        in_session, _ = is_within_session(sessions, early)
        self.assertFalse(in_session)

    def test_holiday_and_skip_combined(self):
        """Holiday check + skip probability combined."""
        from v2.human_behavior import is_holiday, should_skip_send

        # Not a holiday
        is_hol, _ = is_holiday(date(2025, 1, 2))
        self.assertFalse(is_hol)

        # If not a holiday, skip check still works
        skip = should_skip_send(skip_probability=0.0)
        self.assertFalse(skip)

    def test_bounce_rate_affects_cooldown_flow(self):
        """High bounce rate should slow everything down."""
        from v2.human_behavior import get_bounce_slowdown_multiplier, apply_jitter

        base_cooldown = 25
        multiplier = get_bounce_slowdown_multiplier(0.08)  # 8% bounce
        self.assertEqual(multiplier, 2.0)

        slowed = int(base_cooldown * multiplier)
        self.assertEqual(slowed, 50)  # Double the cooldown

        # Jitter the slowed value
        jittered = apply_jitter(slowed)
        self.assertGreaterEqual(jittered, 5)


class TestImapBounceFlowIntegration(unittest.TestCase):
    """
    Integration: Bounce detection → Lead marking → DNC addition.
    Tests _check_for_bounce end-to-end effects.
    """

    @patch("v2.imap_worker.DoNotContact")
    @patch("v2.imap_worker.Lead")
    @patch("v2.imap_worker.emails_collection")
    def test_hard_bounce_marks_lead_and_dnc(self, mock_emails, mock_lead, mock_dnc):
        from v2.imap_worker import _check_for_bounce

        mock_lead.get_by_email.return_value = {"_id": "lead123"}
        mock_lead.mark_invalid_email.return_value = None
        mock_dnc.add.return_value = True
        mock_dnc.REASON_HARD_BOUNCE = "hard_bounce"
        mock_emails.update_many.return_value = MagicMock()

        result = {
            "bounces": 0, "dnc_added": 0,
            "replies": 0, "auto_replies": 0, "unsubscribes": 0, "errors": [],
            "account": "test@test.com",
        }

        _check_for_bounce(
            "mailer-daemon@bouncer.com",
            "Delivery Failure Notification",
            "The following recipient could not be reached: baduser@company.com 550 User unknown",
            result,
        )

        # Verify the full chain
        self.assertEqual(result["bounces"], 1)
        self.assertEqual(result["dnc_added"], 1)
        mock_lead.get_by_email.assert_called()
        mock_lead.mark_invalid_email.assert_called_once()
        mock_dnc.add.assert_called_once()
        mock_emails.update_many.assert_called_once()


class TestSchedulerLifecycle(unittest.TestCase):
    """
    Integration: Scheduler startup → loop → shutdown.
    Tests AsyncScheduler with mocked dependencies.
    """

    @patch("v2.scheduler.Campaign")
    @patch("v2.scheduler.SchedulerConfig")
    @patch("v2.scheduler.BlockedAccounts")
    @patch("v2.scheduler.AccountReputation")
    @patch("v2.scheduler.EmailDraft")
    @patch("v2.scheduler.is_holiday")
    @patch("v2.scheduler.config")
    def test_startup_phase(
        self, mock_config, mock_holiday, mock_draft, mock_rep, mock_blocked,
        mock_sched_config, mock_campaign
    ):
        from v2.scheduler import AsyncScheduler

        mock_config.ZOHO_ACCOUNTS = []
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.SENDING_HOUR_START = 9
        mock_config.SENDING_HOUR_END = 17
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 25
        mock_config.WARMUP_ENABLED = False

        mock_blocked.cleanup_expired.return_value = None
        mock_holiday.return_value = (False, None)
        mock_draft.cleanup_stale_claimed.return_value = None
        mock_draft.get_stats.return_value = {"ready_to_send": 5}
        mock_rep.refresh_all.return_value = None

        scheduler = AsyncScheduler()

        # Mock imap_worker.check_all
        scheduler.imap_worker.check_all = AsyncMock(return_value={
            "total_replies": 2, "total_bounces": 1,
        })

        run_async(scheduler._startup_phase())
        # Should have cleaned blocks, drafts, checked IMAP, refreshed reputation
        mock_blocked.cleanup_expired.assert_called_once()
        mock_draft.cleanup_stale_claimed.assert_called_once()
        scheduler.imap_worker.check_all.assert_called_once()

    @patch("v2.scheduler.config")
    @patch("v2.scheduler.BlockedAccounts")
    @patch("v2.scheduler.db")
    def test_graceful_shutdown(self, mock_db, mock_blocked, mock_config):
        from v2.scheduler import AsyncScheduler

        mock_config.ZOHO_ACCOUNTS = []
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.SENDING_HOUR_START = 9
        mock_config.SENDING_HOUR_END = 17
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 25
        mock_config.WARMUP_ENABLED = False
        mock_blocked.cleanup_expired.return_value = None

        scheduler = AsyncScheduler()
        scheduler.send_worker.request_shutdown()
        scheduler.imap_worker.request_shutdown()

        run_async(scheduler._graceful_shutdown())
        # Heartbeat should be updated
        mock_db.__getitem__.return_value.update_one.assert_called()


class TestAllModulesImport(unittest.TestCase):
    """Smoke test: verify all v2 modules can be imported together."""

    def test_all_imports(self):
        from v2 import human_behavior
        from v2 import account_pool
        from v2 import pre_generator
        from v2 import send_worker
        from v2 import imap_worker
        from v2 import alerts
        from v2 import scheduler

        # Verify key classes exist
        self.assertTrue(hasattr(human_behavior, "SendingSession"))
        self.assertTrue(hasattr(account_pool, "AccountPool"))
        self.assertTrue(hasattr(pre_generator, "EmailDraft"))
        self.assertTrue(hasattr(send_worker, "SendWorker"))
        self.assertTrue(hasattr(imap_worker, "ImapWorker"))
        self.assertTrue(hasattr(alerts, "send_alert"))
        self.assertTrue(hasattr(scheduler, "AsyncScheduler"))


class TestDomainThrottlingAcrossModules(unittest.TestCase):
    """
    Integration: domain_tracker is a global singleton shared across modules.
    Verify send_worker and account_pool both reference it.
    """

    def test_domain_tracker_is_singleton(self):
        from v2.human_behavior import domain_tracker as tracker1
        from v2.account_pool import domain_tracker as tracker2

        # Both should reference the same object
        self.assertIs(tracker1, tracker2)


class TestReviewRewriteFlow(unittest.TestCase):
    """
    Integration: PreGenerator review + rewrite cycle with score thresholds.
    """

    def test_review_pass_on_first_try(self):
        from v2.pre_generator import PreGenerator

        pg = PreGenerator()
        pg._reviewer = MagicMock()
        pg._reviewer.review_email.return_value = {"overall_score": 80}

        subj, body, score = pg._review_and_rewrite(
            "Initial Subject", "Initial body", {"first_name": "Test"}, max_rewrites=3
        )
        self.assertGreaterEqual(score, 70)
        # Should not call rewrite since score >= 70
        pg._reviewer.rewrite_email.assert_not_called()

    def test_review_fails_all_rewrites(self):
        from v2.pre_generator import PreGenerator

        pg = PreGenerator()
        pg._reviewer = MagicMock()
        pg._reviewer.review_email.return_value = {"overall_score": 40}
        pg._reviewer.rewrite_email.return_value = {
            "subject": "Rewritten Subject",
            "body": "Rewritten body",
        }

        subj, body, score = pg._review_and_rewrite(
            "Bad Subject", "Bad body", {"first_name": "Test"}, max_rewrites=2
        )
        self.assertLess(score, 70)
        self.assertEqual(pg._reviewer.rewrite_email.call_count, 2)


if __name__ == "__main__":
    unittest.main()
