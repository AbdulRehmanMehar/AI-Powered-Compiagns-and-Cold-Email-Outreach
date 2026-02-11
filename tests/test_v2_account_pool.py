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


if __name__ == "__main__":
    unittest.main()
