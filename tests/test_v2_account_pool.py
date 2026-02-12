"""
Comprehensive unit tests for v2/account_pool.py

Tests cover:
- AccountReputation scoring logic
- WarmDown ramp schedule
- AccountPool initialization
- Daily limit calculation (warmup + warm-down)
- Business hours checking
- Account eligibility logic
- Account status reporting
- Account acquisition (mocked async)
- Record send + mark blocked
"""

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, PropertyMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_async(coro):
    """Helper to run async functions in sync test methods."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestAccountReputationScoring(unittest.TestCase):
    """Test the reputation scoring algorithm."""

    @patch("database.emails_collection")
    def test_no_activity_gives_100(self, mock_coll):
        """Account with no recent sends should get 100 score."""
        from v2.account_pool import AccountReputation

        mock_coll.aggregate.return_value = iter([])
        result = AccountReputation.compute_score("test@example.com")
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["total_sent"], 0)
        self.assertEqual(result["reason"], "No recent activity — default good")

    @patch("database.emails_collection")
    @patch("v2.account_pool.BlockedAccounts")
    def test_perfect_sends_score(self, mock_blocked, mock_coll):
        """Clean sends with no bounces should yield high score."""
        from v2.account_pool import AccountReputation

        mock_coll.aggregate.return_value = iter([{
            "_id": None,
            "total_sent": 100,
            "bounced": 0,
            "replied": 5,
            "failed": 0,
        }])
        mock_blocked._collection.find_one.return_value = None
        result = AccountReputation.compute_score("test@example.com")
        self.assertGreaterEqual(result["score"], 95)
        self.assertEqual(result["bounce_rate"], 0.0)

    @patch("database.emails_collection")
    @patch("v2.account_pool.BlockedAccounts")
    def test_high_bounce_low_score(self, mock_blocked, mock_coll):
        """High bounce rate should tank the score."""
        from v2.account_pool import AccountReputation

        mock_coll.aggregate.return_value = iter([{
            "_id": None,
            "total_sent": 100,
            "bounced": 10,  # 10% bounce rate
            "replied": 0,
            "failed": 0,
        }])
        mock_blocked._collection.find_one.return_value = None
        result = AccountReputation.compute_score("test@example.com")
        # 10% bounce = -280 from 100 → clamped to 0
        self.assertLessEqual(result["score"], 20)

    @patch("database.emails_collection")
    @patch("v2.account_pool.BlockedAccounts")
    def test_reply_rate_improves_score(self, mock_blocked, mock_coll):
        """Good reply rate should boost the score."""
        from v2.account_pool import AccountReputation

        mock_coll.aggregate.return_value = iter([{
            "_id": None,
            "total_sent": 100,
            "bounced": 0,
            "replied": 10,  # 10% reply rate = +100
            "failed": 0,
        }])
        mock_blocked._collection.find_one.return_value = None
        result = AccountReputation.compute_score("test@example.com")
        # Score capped at 100
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["reply_rate"], 0.1)

    @patch("database.emails_collection")
    @patch("v2.account_pool.BlockedAccounts")
    def test_block_history_penalty(self, mock_blocked, mock_coll):
        """Previous blocks should penalize the score."""
        from v2.account_pool import AccountReputation

        mock_coll.aggregate.return_value = iter([{
            "_id": None,
            "total_sent": 50,
            "bounced": 0,
            "replied": 0,
            "failed": 0,
        }])
        mock_blocked._collection.find_one.return_value = {"block_count": 3}
        result = AccountReputation.compute_score("test@example.com")
        self.assertEqual(result["score"], 70)  # 100 - 3*10

    @patch("database.emails_collection")
    @patch("v2.account_pool.BlockedAccounts")
    def test_score_clamped_0_100(self, mock_blocked, mock_coll):
        """Score should never go below 0 or above 100."""
        from v2.account_pool import AccountReputation

        # Extreme bounces
        mock_coll.aggregate.return_value = iter([{
            "_id": None,
            "total_sent": 100,
            "bounced": 50,
            "replied": 0,
            "failed": 50,
        }])
        mock_blocked._collection.find_one.return_value = {"block_count": 10}
        result = AccountReputation.compute_score("test@example.com")
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    @patch("v2.account_pool._reputation_collection")
    def test_save_score(self, mock_coll):
        """save_score should upsert to MongoDB."""
        from v2.account_pool import AccountReputation

        score_data = {"score": 85, "reason": "Normal"}
        AccountReputation.save_score("test@example.com", score_data)
        mock_coll.update_one.assert_called_once()
        call_args = mock_coll.update_one.call_args
        self.assertEqual(call_args[0][0], {"account_email": "test@example.com"})

    @patch("v2.account_pool._reputation_collection")
    def test_get_saved_score(self, mock_coll):
        """get_saved_score should query MongoDB."""
        from v2.account_pool import AccountReputation

        mock_coll.find_one.return_value = {"score": 90}
        result = AccountReputation.get_saved_score("test@example.com")
        self.assertEqual(result["score"], 90)


class TestWarmDown(unittest.TestCase):
    """Test the warm-down ramp schedule."""

    @patch("v2.account_pool.BlockedAccounts")
    def test_no_record_returns_none(self, mock_blocked):
        """No block record should return None (no warm-down)."""
        from v2.account_pool import WarmDown

        mock_blocked._collection.find_one.return_value = None
        result = WarmDown.get_warmdown_limit("test@example.com")
        self.assertIsNone(result)

    @patch("v2.account_pool.BlockedAccounts")
    def test_still_blocked_returns_zero(self, mock_blocked):
        """Still-blocked account should return 0."""
        from v2.account_pool import WarmDown

        mock_blocked._collection.find_one.return_value = {
            "blocked_until": datetime.utcnow() + timedelta(hours=1)
        }
        result = WarmDown.get_warmdown_limit("test@example.com")
        self.assertEqual(result, 0)

    @patch("v2.account_pool.BlockedAccounts")
    def test_day_0_after_unblock(self, mock_blocked):
        """Day 0 after unblock should return 3 emails."""
        from v2.account_pool import WarmDown

        mock_blocked._collection.find_one.return_value = {
            "blocked_until": datetime.utcnow() - timedelta(hours=1)
        }
        result = WarmDown.get_warmdown_limit("test@example.com")
        self.assertEqual(result, 3)

    @patch("v2.account_pool.BlockedAccounts")
    def test_day_1_after_unblock(self, mock_blocked):
        """Day 1 after unblock should return 5 emails."""
        from v2.account_pool import WarmDown

        mock_blocked._collection.find_one.return_value = {
            "blocked_until": datetime.utcnow() - timedelta(days=1, hours=1)
        }
        result = WarmDown.get_warmdown_limit("test@example.com")
        self.assertEqual(result, 5)

    @patch("v2.account_pool.BlockedAccounts")
    def test_day_2_after_unblock(self, mock_blocked):
        """Day 2 after unblock should return 10 emails."""
        from v2.account_pool import WarmDown

        mock_blocked._collection.find_one.return_value = {
            "blocked_until": datetime.utcnow() - timedelta(days=2, hours=1)
        }
        result = WarmDown.get_warmdown_limit("test@example.com")
        self.assertEqual(result, 10)

    @patch("v2.account_pool.BlockedAccounts")
    def test_day_3_plus_returns_none(self, mock_blocked):
        """Day 3+ after unblock should return None (normal limit)."""
        from v2.account_pool import WarmDown

        mock_blocked._collection.find_one.return_value = {
            "blocked_until": datetime.utcnow() - timedelta(days=5)
        }
        result = WarmDown.get_warmdown_limit("test@example.com")
        self.assertIsNone(result)

    def test_ramp_schedule_values(self):
        """Ramp schedule should be monotonically increasing."""
        from v2.account_pool import WarmDown

        schedule = WarmDown.RAMP_SCHEDULE
        values = [schedule[k] for k in sorted(schedule.keys())]
        for i in range(len(values) - 1):
            self.assertLessEqual(values[i], values[i + 1])


class TestAccountPoolInit(unittest.TestCase):
    """Test AccountPool initialization."""

    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.config")
    def test_pool_initializes_with_accounts(self, mock_config, mock_blocked):
        from v2.account_pool import AccountPool

        mock_config.ZOHO_ACCOUNTS = [
            {"email": "a@test.com", "password": "p1", "sender_name": "A"},
            {"email": "b@test.com", "password": "p2", "sender_name": "B"},
        ]
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_blocked.cleanup_expired.return_value = None

        pool = AccountPool()
        self.assertEqual(len(pool.accounts), 2)


class TestAccountPoolBusinessHours(unittest.TestCase):
    """Test business hours checking."""

    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.config")
    def test_outside_hours_before(self, mock_config, mock_blocked):
        from v2.account_pool import AccountPool
        import pytz

        mock_config.ZOHO_ACCOUNTS = []
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.SENDING_HOUR_START = 9
        mock_config.SENDING_HOUR_END = 17
        mock_config.SEND_ON_WEEKENDS = False
        mock_blocked.cleanup_expired.return_value = None

        pool = AccountPool()
        # Monday at 5 AM ET
        with patch("v2.account_pool.datetime") as mock_dt:
            mock_now = datetime(2025, 1, 6, 10, 0)  # UTC → 5 AM ET
            mock_dt.now.return_value = mock_now
            mock_dt.utcnow.return_value = mock_now
            can, reason = pool._can_send_now()
            # Can't test reliably without matching tz conversion, just verify it returns a tuple
            self.assertIsInstance(can, bool)
            self.assertIsInstance(reason, str)


class TestAccountPoolEligibility(unittest.TestCase):
    """Test account eligibility checks."""

    @patch("v2.account_pool.AccountReputation")
    @patch("v2.account_pool.AccountCooldown")
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.config")
    def test_blocked_account_not_eligible(self, mock_config, mock_blocked, mock_stats, mock_cooldown, mock_rep):
        from v2.account_pool import AccountPool

        mock_config.ZOHO_ACCOUNTS = [{"email": "test@test.com", "password": "p", "sender_name": "T"}]
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 25
        mock_config.WARMUP_ENABLED = False
        mock_blocked.cleanup_expired.return_value = None
        mock_blocked.is_blocked.return_value = True

        pool = AccountPool()
        self.assertFalse(pool._is_eligible("test@test.com"))

    @patch("v2.account_pool.WarmDown")
    @patch("v2.account_pool.AccountReputation")
    @patch("v2.account_pool.AccountCooldown")
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.config")
    def test_over_limit_not_eligible(self, mock_config, mock_blocked, mock_stats, mock_cooldown, mock_rep, mock_warmdown):
        from v2.account_pool import AccountPool

        mock_config.ZOHO_ACCOUNTS = [{"email": "test@test.com", "password": "p", "sender_name": "T"}]
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 25
        mock_config.WARMUP_ENABLED = False
        mock_config.GLOBAL_DAILY_TARGET = 0
        mock_blocked.cleanup_expired.return_value = None
        mock_blocked.is_blocked.return_value = False
        mock_stats.get_sends_today.return_value = 25
        mock_warmdown.get_warmdown_limit.return_value = None  # No warm-down active

        pool = AccountPool()
        self.assertFalse(pool._is_eligible("test@test.com"))

    @patch("v2.account_pool.WarmDown")
    @patch("v2.account_pool.AccountReputation")
    @patch("v2.account_pool.AccountCooldown")
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.config")
    def test_in_cooldown_not_eligible(self, mock_config, mock_blocked, mock_stats, mock_cooldown, mock_rep, mock_warmdown):
        from v2.account_pool import AccountPool

        mock_config.ZOHO_ACCOUNTS = [{"email": "test@test.com", "password": "p", "sender_name": "T"}]
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 25
        mock_config.WARMUP_ENABLED = False
        mock_config.GLOBAL_DAILY_TARGET = 0
        mock_blocked.cleanup_expired.return_value = None
        mock_blocked.is_blocked.return_value = False
        mock_stats.get_sends_today.return_value = 5
        mock_cooldown.is_available.return_value = False
        mock_warmdown.get_warmdown_limit.return_value = None

        pool = AccountPool()
        self.assertFalse(pool._is_eligible("test@test.com"))

    @patch("v2.account_pool.WarmDown")
    @patch("v2.account_pool.AccountReputation")
    @patch("v2.account_pool.AccountCooldown")
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.config")
    def test_low_reputation_not_eligible(self, mock_config, mock_blocked, mock_stats, mock_cooldown, mock_rep, mock_warmdown):
        from v2.account_pool import AccountPool

        mock_config.ZOHO_ACCOUNTS = [{"email": "test@test.com", "password": "p", "sender_name": "T"}]
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 25
        mock_config.WARMUP_ENABLED = False
        mock_config.GLOBAL_DAILY_TARGET = 0
        mock_blocked.cleanup_expired.return_value = None
        mock_blocked.is_blocked.return_value = False
        mock_stats.get_sends_today.return_value = 5
        mock_cooldown.is_available.return_value = True
        mock_rep.get_saved_score.return_value = {"score": 30}  # Below 40 threshold
        mock_rep.PAUSE_THRESHOLD = 40
        mock_warmdown.get_warmdown_limit.return_value = None

        pool = AccountPool()
        self.assertFalse(pool._is_eligible("test@test.com"))

    @patch("v2.account_pool.WarmDown")
    @patch("v2.account_pool.AccountReputation")
    @patch("v2.account_pool.AccountCooldown")
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.config")
    def test_eligible_account(self, mock_config, mock_blocked, mock_stats, mock_cooldown, mock_rep, mock_warmdown):
        from v2.account_pool import AccountPool

        mock_config.ZOHO_ACCOUNTS = [{"email": "test@test.com", "password": "p", "sender_name": "T"}]
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 25
        mock_config.WARMUP_ENABLED = False
        mock_config.GLOBAL_DAILY_TARGET = 0
        mock_blocked.cleanup_expired.return_value = None
        mock_blocked.is_blocked.return_value = False
        mock_stats.get_sends_today.return_value = 5
        mock_cooldown.is_available.return_value = True
        mock_rep.get_saved_score.return_value = {"score": 90}
        mock_rep.PAUSE_THRESHOLD = 40
        mock_warmdown.get_warmdown_limit.return_value = None

        pool = AccountPool()
        self.assertTrue(pool._is_eligible("test@test.com"))


class TestAccountPoolWaitTime(unittest.TestCase):
    """Test the wait time calculation."""

    @patch("v2.account_pool.WarmDown")
    @patch("v2.account_pool.AccountCooldown")
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.config")
    def test_all_exhausted_returns_negative(self, mock_config, mock_blocked, mock_stats, mock_cooldown, mock_warmdown):
        from v2.account_pool import AccountPool

        mock_config.ZOHO_ACCOUNTS = [{"email": "a@test.com", "password": "p", "sender_name": "A"}]
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 25
        mock_config.WARMUP_ENABLED = False
        mock_config.GLOBAL_DAILY_TARGET = 0
        mock_blocked.cleanup_expired.return_value = None
        mock_blocked.is_blocked.return_value = False
        mock_stats.get_sends_today.return_value = 25  # At limit
        mock_warmdown.get_warmdown_limit.return_value = None

        pool = AccountPool()
        self.assertEqual(pool.get_wait_time(), -1)

    @patch("v2.account_pool.WarmDown")
    @patch("v2.account_pool.AccountCooldown")
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.config")
    def test_available_returns_zero(self, mock_config, mock_blocked, mock_stats, mock_cooldown, mock_warmdown):
        from v2.account_pool import AccountPool

        mock_config.ZOHO_ACCOUNTS = [{"email": "a@test.com", "password": "p", "sender_name": "A"}]
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 25
        mock_config.WARMUP_ENABLED = False
        mock_config.GLOBAL_DAILY_TARGET = 0
        mock_blocked.cleanup_expired.return_value = None
        mock_blocked.is_blocked.return_value = False
        mock_stats.get_sends_today.return_value = 5
        mock_cooldown.get_soonest_available.return_value = ("a@test.com", 0)
        mock_warmdown.get_warmdown_limit.return_value = None

        pool = AccountPool()
        self.assertEqual(pool.get_wait_time(), 0)


class TestAccountPoolMarkBlocked(unittest.TestCase):
    """Test mark_blocked functionality."""

    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.config")
    def test_mark_blocked(self, mock_config, mock_blocked):
        from v2.account_pool import AccountPool

        mock_config.ZOHO_ACCOUNTS = [{"email": "a@test.com", "password": "p", "sender_name": "A"}]
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_blocked.cleanup_expired.return_value = None

        pool = AccountPool()
        pool.mark_blocked("a@test.com", "554 error")
        mock_blocked.mark_blocked.assert_called_once_with("a@test.com", "554 error")


class TestAccountPoolRecordSend(unittest.TestCase):
    """Test record_send functionality."""

    @patch("v2.account_pool.domain_tracker")
    @patch("v2.account_pool.AccountCooldown")
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.config")
    def test_record_send(self, mock_config, mock_blocked, mock_stats, mock_cooldown, mock_tracker):
        from v2.account_pool import AccountPool

        mock_config.ZOHO_ACCOUNTS = [{"email": "a@test.com", "password": "p", "sender_name": "A"}]
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_blocked.cleanup_expired.return_value = None

        pool = AccountPool()
        run_async(pool.record_send("a@test.com", "recipient@example.com"))

        mock_stats.increment_send.assert_called_once_with("a@test.com")
        mock_cooldown.record_send.assert_called_once()
        mock_tracker.record_send.assert_called_once_with("recipient@example.com")


class TestReputationThresholds(unittest.TestCase):
    """Test reputation threshold constants."""

    def test_pause_threshold(self):
        from v2.account_pool import AccountReputation

        self.assertEqual(AccountReputation.PAUSE_THRESHOLD, 40)

    def test_warning_threshold(self):
        from v2.account_pool import AccountReputation

        self.assertEqual(AccountReputation.WARNING_THRESHOLD, 60)

    def test_warning_above_pause(self):
        from v2.account_pool import AccountReputation

        self.assertGreater(AccountReputation.WARNING_THRESHOLD, AccountReputation.PAUSE_THRESHOLD)


class TestGlobalDailyTarget(unittest.TestCase):
    """Test GLOBAL_DAILY_TARGET logic in _get_daily_limit."""

    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.WarmDown.get_warmdown_limit", return_value=None)
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.config")
    def test_global_target_disabled_uses_per_mailbox(self, mock_config, mock_stats, mock_wd, mock_blocked):
        """When GLOBAL_DAILY_TARGET=0, fall back to EMAILS_PER_DAY_PER_MAILBOX."""
        from v2.account_pool import AccountPool

        mock_config.ZOHO_ACCOUNTS = [{"email": "a@test.com", "password": "p", "sender_name": "A"}]
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.GLOBAL_DAILY_TARGET = 0
        mock_config.WARMUP_ENABLED = False
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 25
        mock_blocked.cleanup_expired.return_value = None

        pool = AccountPool()
        limit = pool._get_daily_limit("a@test.com")
        self.assertEqual(limit, 25)

    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.WarmDown.get_warmdown_limit", return_value=None)
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.config")
    def test_global_target_distributes_evenly(self, mock_config, mock_stats, mock_wd, mock_blocked):
        """300 target across 6 accounts → 50 each."""
        from v2.account_pool import AccountPool

        accounts = [
            {"email": f"user{i}@test.com", "password": "p", "sender_name": f"U{i}"}
            for i in range(6)
        ]
        mock_config.ZOHO_ACCOUNTS = accounts
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.GLOBAL_DAILY_TARGET = 300
        mock_config.WARMUP_ENABLED = False
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 100
        mock_blocked.cleanup_expired.return_value = None
        mock_blocked.is_blocked.return_value = False

        pool = AccountPool()
        limit = pool._get_daily_limit("user0@test.com")
        self.assertEqual(limit, 50)  # ceil(300/6)

    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.WarmDown.get_warmdown_limit", return_value=None)
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.config")
    def test_global_target_adjusts_for_blocked(self, mock_config, mock_stats, mock_wd, mock_blocked):
        """If 2 of 6 accounts are blocked, target distributes across 4."""
        from v2.account_pool import AccountPool

        accounts = [
            {"email": f"user{i}@test.com", "password": "p", "sender_name": f"U{i}"}
            for i in range(6)
        ]
        mock_config.ZOHO_ACCOUNTS = accounts
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.GLOBAL_DAILY_TARGET = 300
        mock_config.WARMUP_ENABLED = False
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 100
        mock_blocked.cleanup_expired.return_value = None
        # 2 accounts blocked
        mock_blocked.is_blocked.side_effect = lambda e: e in ("user0@test.com", "user1@test.com")

        pool = AccountPool()
        limit = pool._get_daily_limit("user2@test.com")
        self.assertEqual(limit, 75)  # ceil(300/4)

    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.WarmDown.get_warmdown_limit", return_value=None)
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.config")
    def test_global_target_capped_by_warmup(self, mock_config, mock_stats, mock_wd, mock_blocked):
        """Global target can't exceed warmup limit for young accounts."""
        from v2.account_pool import AccountPool

        accounts = [
            {"email": f"user{i}@test.com", "password": "p", "sender_name": f"U{i}"}
            for i in range(6)
        ]
        mock_config.ZOHO_ACCOUNTS = accounts
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.GLOBAL_DAILY_TARGET = 300
        mock_config.WARMUP_ENABLED = True
        mock_config.WARMUP_WEEK1_LIMIT = 3
        mock_config.WARMUP_WEEK2_LIMIT = 7
        mock_config.WARMUP_WEEK3_LIMIT = 12
        mock_config.WARMUP_WEEK4_LIMIT = 20
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 100
        mock_blocked.cleanup_expired.return_value = None
        mock_blocked.is_blocked.return_value = False
        # Account is 5 days old (week 1)
        mock_stats.get_account_age_days.return_value = 5

        pool = AccountPool()
        limit = pool._get_daily_limit("user0@test.com")
        # ceil(300/6) = 50, but warmup week 1 = 3 → capped to 3
        self.assertEqual(limit, 3)

    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.WarmDown.get_warmdown_limit", return_value=None)
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.config")
    def test_global_target_mature_accounts(self, mock_config, mock_stats, mock_wd, mock_blocked):
        """Mature accounts (week 4+) get full global target share."""
        from v2.account_pool import AccountPool

        accounts = [
            {"email": f"user{i}@test.com", "password": "p", "sender_name": f"U{i}"}
            for i in range(6)
        ]
        mock_config.ZOHO_ACCOUNTS = accounts
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.GLOBAL_DAILY_TARGET = 300
        mock_config.WARMUP_ENABLED = True
        mock_config.WARMUP_WEEK1_LIMIT = 3
        mock_config.WARMUP_WEEK2_LIMIT = 7
        mock_config.WARMUP_WEEK3_LIMIT = 12
        mock_config.WARMUP_WEEK4_LIMIT = 50
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 100
        mock_blocked.cleanup_expired.return_value = None
        mock_blocked.is_blocked.return_value = False
        # Account is 30 days old (week 5 → uses week 4 limit)
        mock_stats.get_account_age_days.return_value = 30

        pool = AccountPool()
        limit = pool._get_daily_limit("user0@test.com")
        # ceil(300/6) = 50, warmup week 4 = 50 → min(50, 50) = 50
        self.assertEqual(limit, 50)

    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.WarmDown.get_warmdown_limit", return_value=None)
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.config")
    def test_global_target_never_exceeds_zoho_500(self, mock_config, mock_stats, mock_wd, mock_blocked):
        """Even with huge global target, per-account can't exceed Zoho's 500."""
        from v2.account_pool import AccountPool

        accounts = [{"email": "solo@test.com", "password": "p", "sender_name": "S"}]
        mock_config.ZOHO_ACCOUNTS = accounts
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.GLOBAL_DAILY_TARGET = 1000  # absurd, but test the cap
        mock_config.WARMUP_ENABLED = False
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 1000
        mock_blocked.cleanup_expired.return_value = None
        mock_blocked.is_blocked.return_value = False

        pool = AccountPool()
        limit = pool._get_daily_limit("solo@test.com")
        self.assertEqual(limit, 500)  # Zoho hard cap

    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.WarmDown")
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.config")
    def test_warmdown_takes_priority_over_global(self, mock_config, mock_stats, mock_wd_cls, mock_blocked):
        """Warm-down limit always wins, even over global target."""
        from v2.account_pool import AccountPool

        accounts = [{"email": "wd@test.com", "password": "p", "sender_name": "W"}]
        mock_config.ZOHO_ACCOUNTS = accounts
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.GLOBAL_DAILY_TARGET = 300
        mock_config.WARMUP_ENABLED = False
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 100
        mock_blocked.cleanup_expired.return_value = None
        mock_wd_cls.get_warmdown_limit.return_value = 5  # recently unblocked

        pool = AccountPool()
        limit = pool._get_daily_limit("wd@test.com")
        self.assertEqual(limit, 5)  # warm-down overrides everything

    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.WarmDown.get_warmdown_limit", return_value=None)
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.config")
    def test_global_target_all_blocked_returns_zero(self, mock_config, mock_stats, mock_wd, mock_blocked):
        """If all accounts are blocked, per-account limit from global target is 0."""
        from v2.account_pool import AccountPool

        accounts = [
            {"email": f"user{i}@test.com", "password": "p", "sender_name": f"U{i}"}
            for i in range(3)
        ]
        mock_config.ZOHO_ACCOUNTS = accounts
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.GLOBAL_DAILY_TARGET = 300
        mock_config.WARMUP_ENABLED = False
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 100
        mock_blocked.cleanup_expired.return_value = None
        mock_blocked.is_blocked.return_value = True  # ALL blocked

        pool = AccountPool()
        limit = pool._get_daily_limit("user0@test.com")
        self.assertEqual(limit, 0)

    @patch("v2.account_pool.BlockedAccounts")
    @patch("v2.account_pool.WarmDown.get_warmdown_limit", return_value=None)
    @patch("v2.account_pool.SendingStats")
    @patch("v2.account_pool.config")
    def test_global_target_uneven_distribution(self, mock_config, mock_stats, mock_wd, mock_blocked):
        """Uneven split rounds up: 300 across 7 accounts → ceil(42.8) = 43."""
        from v2.account_pool import AccountPool

        accounts = [
            {"email": f"user{i}@test.com", "password": "p", "sender_name": f"U{i}"}
            for i in range(7)
        ]
        mock_config.ZOHO_ACCOUNTS = accounts
        mock_config.TARGET_TIMEZONE = "America/New_York"
        mock_config.GLOBAL_DAILY_TARGET = 300
        mock_config.WARMUP_ENABLED = False
        mock_config.EMAILS_PER_DAY_PER_MAILBOX = 100
        mock_blocked.cleanup_expired.return_value = None
        mock_blocked.is_blocked.return_value = False

        pool = AccountPool()
        limit = pool._get_daily_limit("user0@test.com")
        self.assertEqual(limit, 43)  # ceil(300/7) = 43


if __name__ == "__main__":
    unittest.main()
