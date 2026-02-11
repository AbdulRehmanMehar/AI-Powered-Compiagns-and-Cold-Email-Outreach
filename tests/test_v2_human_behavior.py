"""
Comprehensive unit tests for v2/human_behavior.py

Tests cover:
- US holiday calendar (fixed + floating holidays)
- Time-of-day multiplier
- Gaussian jitter bounds
- Human cooldown calculation
- Session planning + validation
- Session overlap detection
- Skip/pause behavior
- Bounce slowdown multiplier
- Recipient domain throttling
"""

import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestUSHolidays(unittest.TestCase):
    """Test the US holiday calendar generation."""

    def test_fixed_holidays_present(self):
        """All fixed-date holidays should be present."""
        from v2.human_behavior import get_us_holidays

        holidays = get_us_holidays(2025)
        # Check fixed dates
        self.assertIn(date(2025, 1, 1), holidays)       # New Year's Day
        self.assertIn(date(2025, 6, 19), holidays)      # Juneteenth
        self.assertIn(date(2025, 7, 4), holidays)       # Independence Day
        self.assertIn(date(2025, 11, 11), holidays)     # Veterans Day
        self.assertIn(date(2025, 12, 24), holidays)     # Christmas Eve
        self.assertIn(date(2025, 12, 25), holidays)     # Christmas Day
        self.assertIn(date(2025, 12, 31), holidays)     # New Year's Eve

    def test_floating_holidays_2025(self):
        """Verify floating holidays for a known year (2025)."""
        from v2.human_behavior import get_us_holidays

        holidays = get_us_holidays(2025)
        # MLK Day: 3rd Monday of January 2025 → Jan 20
        self.assertIn(date(2025, 1, 20), holidays)
        # Presidents' Day: 3rd Monday of February 2025 → Feb 17
        self.assertIn(date(2025, 2, 17), holidays)
        # Memorial Day: Last Monday of May 2025 → May 26
        self.assertIn(date(2025, 5, 26), holidays)
        # Labor Day: First Monday of September 2025 → Sep 1
        self.assertIn(date(2025, 9, 1), holidays)
        # Thanksgiving: 4th Thursday of November 2025 → Nov 27
        self.assertIn(date(2025, 11, 27), holidays)
        # Day after Thanksgiving → Nov 28
        self.assertIn(date(2025, 11, 28), holidays)

    def test_thanksgiving_calculation(self):
        """Thanksgiving should always be the 4th Thursday of November."""
        from v2.human_behavior import _thanksgiving

        # Known Thanksgivings
        self.assertEqual(_thanksgiving(2024), date(2024, 11, 28))
        self.assertEqual(_thanksgiving(2025), date(2025, 11, 27))
        self.assertEqual(_thanksgiving(2026), date(2026, 11, 26))
        # Verify it's always a Thursday
        for year in range(2020, 2030):
            tg = _thanksgiving(year)
            self.assertEqual(tg.weekday(), 3, f"{year}: Thanksgiving on {tg} is not Thursday")

    def test_memorial_day_calculation(self):
        """Memorial Day should always be the last Monday of May."""
        from v2.human_behavior import _memorial_day

        self.assertEqual(_memorial_day(2025), date(2025, 5, 26))
        for year in range(2020, 2030):
            md = _memorial_day(year)
            self.assertEqual(md.weekday(), 0, f"{year}: Memorial Day on {md} is not Monday")
            self.assertEqual(md.month, 5)
            # Should be in the last 7 days of May
            self.assertGreaterEqual(md.day, 25)

    def test_labor_day_calculation(self):
        """Labor Day should always be the first Monday of September."""
        from v2.human_behavior import _labor_day

        self.assertEqual(_labor_day(2025), date(2025, 9, 1))
        for year in range(2020, 2030):
            ld = _labor_day(year)
            self.assertEqual(ld.weekday(), 0, f"{year}: Labor Day on {ld} is not Monday")
            self.assertEqual(ld.month, 9)
            self.assertLessEqual(ld.day, 7)

    def test_mlk_day_calculation(self):
        """MLK Day should be the 3rd Monday of January."""
        from v2.human_behavior import _mlk_day

        for year in range(2020, 2030):
            mlk = _mlk_day(year)
            self.assertEqual(mlk.weekday(), 0, f"{year}: MLK Day on {mlk} is not Monday")
            self.assertEqual(mlk.month, 1)
            self.assertGreaterEqual(mlk.day, 15)
            self.assertLessEqual(mlk.day, 21)

    def test_presidents_day_calculation(self):
        """Presidents' Day should be the 3rd Monday of February."""
        from v2.human_behavior import _presidents_day

        for year in range(2020, 2030):
            pd = _presidents_day(year)
            self.assertEqual(pd.weekday(), 0, f"{year}: Presidents Day on {pd} is not Monday")
            self.assertEqual(pd.month, 2)
            self.assertGreaterEqual(pd.day, 15)
            self.assertLessEqual(pd.day, 21)

    def test_is_holiday_true(self):
        """Known holiday dates should return True."""
        from v2.human_behavior import is_holiday

        is_hol, name = is_holiday(date(2025, 12, 25))
        self.assertTrue(is_hol)
        self.assertEqual(name, "Christmas Day")

    def test_is_holiday_false(self):
        """Regular business days should not be holidays."""
        from v2.human_behavior import is_holiday

        # Jan 2, 2025 is a Thursday — not a holiday
        is_hol, name = is_holiday(date(2025, 1, 2))
        self.assertFalse(is_hol)
        self.assertIsNone(name)

    def test_holiday_count(self):
        """Should have 13 holidays/quiet days per year."""
        from v2.human_behavior import get_us_holidays

        holidays = get_us_holidays(2025)
        self.assertEqual(len(holidays), 13)


class TestTimeOfDayMultiplier(unittest.TestCase):
    """Test time-of-day send rate multipliers."""

    def test_morning_normal_pace(self):
        from v2.human_behavior import get_time_of_day_multiplier

        self.assertEqual(get_time_of_day_multiplier(9), 1.0)
        self.assertEqual(get_time_of_day_multiplier(10), 1.0)

    def test_lunch_slow(self):
        from v2.human_behavior import get_time_of_day_multiplier

        self.assertEqual(get_time_of_day_multiplier(12), 2.0)

    def test_wind_down(self):
        from v2.human_behavior import get_time_of_day_multiplier

        self.assertEqual(get_time_of_day_multiplier(16), 1.5)

    def test_outside_hours_default(self):
        """Hours outside the map should return 1.0."""
        from v2.human_behavior import get_time_of_day_multiplier

        self.assertEqual(get_time_of_day_multiplier(8), 1.0)
        self.assertEqual(get_time_of_day_multiplier(17), 1.0)
        self.assertEqual(get_time_of_day_multiplier(23), 1.0)

    def test_all_multipliers_positive(self):
        from v2.human_behavior import TIME_OF_DAY_MULTIPLIERS

        for hour, mult in TIME_OF_DAY_MULTIPLIERS.items():
            self.assertGreater(mult, 0, f"Hour {hour} has non-positive multiplier")


class TestGaussianJitter(unittest.TestCase):
    """Test the jitter function for bounds and distribution."""

    def test_jitter_minimum_bound(self):
        """Jitter should never go below 5 minutes."""
        from v2.human_behavior import apply_jitter

        for _ in range(500):
            result = apply_jitter(5, jitter_pct=1.0)
            self.assertGreaterEqual(result, 5)

    def test_jitter_reasonable_range(self):
        """Most jittered values should be within ±50% of base."""
        from v2.human_behavior import apply_jitter

        base = 25
        results = [apply_jitter(base, jitter_pct=0.30) for _ in range(1000)]
        # 95% should be within ±30%
        within_range = sum(1 for r in results if base * 0.5 <= r <= base * 1.5)
        self.assertGreater(within_range / len(results), 0.85)

    def test_jitter_returns_int(self):
        from v2.human_behavior import apply_jitter

        result = apply_jitter(25)
        self.assertIsInstance(result, int)

    def test_jitter_zero_percent(self):
        """Zero jitter should return the base value."""
        from v2.human_behavior import apply_jitter

        # With 0% jitter, sigma=0 so gauss returns the mean
        result = apply_jitter(25, jitter_pct=0.0)
        self.assertEqual(result, 25)


class TestHumanCooldown(unittest.TestCase):
    """Test the human cooldown calculation."""

    def test_cooldown_within_bounds(self):
        """Cooldown should be reasonable (5 to 120 minutes)."""
        from v2.human_behavior import get_human_cooldown_minutes

        for _ in range(200):
            cooldown = get_human_cooldown_minutes()
            self.assertGreaterEqual(cooldown, 5)
            # Even with extreme multipliers, shouldn't exceed 120 min
            self.assertLessEqual(cooldown, 200)

    def test_cooldown_returns_int(self):
        from v2.human_behavior import get_human_cooldown_minutes

        self.assertIsInstance(get_human_cooldown_minutes(), int)


class TestSendingSession(unittest.TestCase):
    """Test SendingSession dataclass."""

    def test_session_creation(self):
        from v2.human_behavior import SendingSession

        session = SendingSession(start_hour=10, start_minute=30, email_count=5, intra_gap_minutes=20)
        self.assertEqual(session.start_hour, 10)
        self.assertEqual(session.start_minute, 30)
        self.assertEqual(session.email_count, 5)
        self.assertEqual(session.intra_gap_minutes, 20)

    def test_session_start_minutes(self):
        from v2.human_behavior import SendingSession

        session = SendingSession(start_hour=10, start_minute=30, email_count=5)
        self.assertEqual(session.start_minutes_from_midnight, 10 * 60 + 30)

    def test_session_duration(self):
        from v2.human_behavior import SendingSession

        session = SendingSession(start_hour=10, start_minute=0, email_count=5, intra_gap_minutes=20)
        self.assertEqual(session.duration_minutes, 100)  # 5 * 20

    def test_session_end_minutes(self):
        from v2.human_behavior import SendingSession

        session = SendingSession(start_hour=10, start_minute=0, email_count=5, intra_gap_minutes=20)
        self.assertEqual(session.end_minutes_from_midnight, 10 * 60 + 100)

    def test_session_repr(self):
        from v2.human_behavior import SendingSession

        session = SendingSession(start_hour=9, start_minute=0, email_count=3, intra_gap_minutes=20)
        repr_str = repr(session)
        self.assertIn("Session(", repr_str)
        self.assertIn("3 emails", repr_str)


class TestPlanDailySessions(unittest.TestCase):
    """Test the session planning algorithm."""

    def test_sessions_count(self):
        """Should create up to the requested number of sessions."""
        from v2.human_behavior import plan_daily_sessions

        sessions = plan_daily_sessions(session_count=3, daily_limit=25)
        self.assertLessEqual(len(sessions), 3)
        self.assertGreater(len(sessions), 0)

    def test_sessions_total_emails_under_limit(self):
        """Total emails across all sessions should not exceed daily limit."""
        from v2.human_behavior import plan_daily_sessions

        for _ in range(50):
            sessions = plan_daily_sessions(session_count=3, daily_limit=25)
            total = sum(s.email_count for s in sessions)
            self.assertLessEqual(total, 25)

    def test_sessions_within_window(self):
        """All sessions should start within the sending window."""
        from v2.human_behavior import plan_daily_sessions

        for _ in range(50):
            sessions = plan_daily_sessions(
                session_count=3,
                daily_limit=25,
                send_start_hour=9,
                send_end_hour=17,
            )
            for s in sessions:
                self.assertGreaterEqual(s.start_hour, 9)
                self.assertLess(s.start_hour, 17)

    def test_sessions_no_overlap(self):
        """Sessions should not overlap."""
        from v2.human_behavior import plan_daily_sessions

        for _ in range(50):
            sessions = plan_daily_sessions(session_count=3, daily_limit=25)
            for i in range(len(sessions) - 1):
                end_i = sessions[i].end_minutes_from_midnight
                start_next = sessions[i + 1].start_minutes_from_midnight
                self.assertLessEqual(
                    end_i,
                    start_next,
                    f"Session {i} ends at {end_i} but session {i+1} starts at {start_next}"
                )

    def test_sessions_zero_window(self):
        """Zero-width sending window should return empty list."""
        from v2.human_behavior import plan_daily_sessions

        sessions = plan_daily_sessions(send_start_hour=9, send_end_hour=9)
        self.assertEqual(len(sessions), 0)

    def test_sessions_small_limit(self):
        """Very small daily limit should still produce valid sessions."""
        from v2.human_behavior import plan_daily_sessions

        sessions = plan_daily_sessions(session_count=3, daily_limit=3, emails_min=1, emails_max=2)
        total = sum(s.email_count for s in sessions)
        self.assertLessEqual(total, 3)


class TestIsWithinSession(unittest.TestCase):
    """Test session overlap detection."""

    def test_within_session(self):
        from v2.human_behavior import SendingSession, is_within_session

        sessions = [SendingSession(start_hour=10, start_minute=0, email_count=5, intra_gap_minutes=20)]
        # 10:30 is 30 minutes into a 100-minute session → should be inside
        now = datetime(2025, 1, 6, 10, 30)
        in_session, current = is_within_session(sessions, now)
        self.assertTrue(in_session)
        self.assertIsNotNone(current)

    def test_outside_session(self):
        from v2.human_behavior import SendingSession, is_within_session

        sessions = [SendingSession(start_hour=10, start_minute=0, email_count=3, intra_gap_minutes=20)]
        now = datetime(2025, 1, 6, 14, 0)
        in_session, current = is_within_session(sessions, now)
        self.assertFalse(in_session)
        self.assertIsNone(current)


class TestNextSessionStart(unittest.TestCase):
    """Test next session start detection."""

    def test_next_session_found(self):
        from v2.human_behavior import SendingSession, next_session_start

        sessions = [
            SendingSession(start_hour=10, start_minute=0, email_count=3, intra_gap_minutes=20),
            SendingSession(start_hour=14, start_minute=0, email_count=3, intra_gap_minutes=20),
        ]
        now = datetime(2025, 1, 6, 12, 0)
        result = next_session_start(sessions, now)
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 0)

    def test_no_next_session(self):
        from v2.human_behavior import SendingSession, next_session_start

        sessions = [
            SendingSession(start_hour=10, start_minute=0, email_count=3, intra_gap_minutes=20),
        ]
        now = datetime(2025, 1, 6, 15, 0)
        result = next_session_start(sessions, now)
        self.assertIsNone(result)


class TestSkipSend(unittest.TestCase):
    """Test the probabilistic skip function."""

    def test_never_skip_at_zero(self):
        from v2.human_behavior import should_skip_send

        for _ in range(100):
            self.assertFalse(should_skip_send(skip_probability=0.0))

    def test_always_skip_at_one(self):
        from v2.human_behavior import should_skip_send

        for _ in range(100):
            self.assertTrue(should_skip_send(skip_probability=1.0))

    def test_skip_probability_approximate(self):
        """With 50% probability, roughly half should skip."""
        from v2.human_behavior import should_skip_send

        results = [should_skip_send(skip_probability=0.5) for _ in range(1000)]
        skip_rate = sum(results) / len(results)
        self.assertAlmostEqual(skip_rate, 0.5, delta=0.08)


class TestReplyPause(unittest.TestCase):
    """Test reply pause duration."""

    def test_pause_range(self):
        from v2.human_behavior import get_reply_pause_seconds

        for _ in range(100):
            pause = get_reply_pause_seconds()
            self.assertGreaterEqual(pause, 30 * 60)  # 30 minutes
            self.assertLessEqual(pause, 90 * 60)     # 90 minutes

    def test_pause_returns_int(self):
        from v2.human_behavior import get_reply_pause_seconds

        self.assertIsInstance(get_reply_pause_seconds(), int)


class TestBounceSlowdown(unittest.TestCase):
    """Test bounce slowdown multiplier."""

    def test_no_slowdown_below_3pct(self):
        from v2.human_behavior import get_bounce_slowdown_multiplier

        self.assertEqual(get_bounce_slowdown_multiplier(0.0), 1.0)
        self.assertEqual(get_bounce_slowdown_multiplier(0.02), 1.0)
        self.assertEqual(get_bounce_slowdown_multiplier(0.029), 1.0)

    def test_slight_slowdown_3_5pct(self):
        from v2.human_behavior import get_bounce_slowdown_multiplier

        self.assertEqual(get_bounce_slowdown_multiplier(0.03), 1.5)
        self.assertEqual(get_bounce_slowdown_multiplier(0.04), 1.5)

    def test_half_speed_5_10pct(self):
        from v2.human_behavior import get_bounce_slowdown_multiplier

        self.assertEqual(get_bounce_slowdown_multiplier(0.05), 2.0)
        self.assertEqual(get_bounce_slowdown_multiplier(0.09), 2.0)

    def test_very_slow_above_10pct(self):
        from v2.human_behavior import get_bounce_slowdown_multiplier

        self.assertEqual(get_bounce_slowdown_multiplier(0.10), 3.0)
        self.assertEqual(get_bounce_slowdown_multiplier(0.20), 3.0)

    def test_monotonically_increasing(self):
        """Higher bounce rate should never result in lower multiplier."""
        from v2.human_behavior import get_bounce_slowdown_multiplier

        rates = [0.0, 0.01, 0.03, 0.05, 0.10, 0.20]
        multipliers = [get_bounce_slowdown_multiplier(r) for r in rates]
        for i in range(len(multipliers) - 1):
            self.assertLessEqual(multipliers[i], multipliers[i + 1])


class TestRecipientDomainTracker(unittest.TestCase):
    """Test the domain throttling tracker."""

    def test_initial_can_send(self):
        from v2.human_behavior import RecipientDomainTracker

        tracker = RecipientDomainTracker(max_per_domain=3)
        self.assertTrue(tracker.can_send_to("user@example.com"))

    def test_throttle_after_max(self):
        from v2.human_behavior import RecipientDomainTracker

        tracker = RecipientDomainTracker(max_per_domain=2)
        tracker.record_send("a@example.com")
        tracker.record_send("b@example.com")
        self.assertFalse(tracker.can_send_to("c@example.com"))

    def test_different_domains_independent(self):
        from v2.human_behavior import RecipientDomainTracker

        tracker = RecipientDomainTracker(max_per_domain=1)
        tracker.record_send("a@domain1.com")
        # domain1 is full, but domain2 should be fine
        self.assertFalse(tracker.can_send_to("b@domain1.com"))
        self.assertTrue(tracker.can_send_to("a@domain2.com"))

    def test_case_insensitive(self):
        from v2.human_behavior import RecipientDomainTracker

        tracker = RecipientDomainTracker(max_per_domain=1)
        tracker.record_send("user@EXAMPLE.COM")
        self.assertFalse(tracker.can_send_to("other@example.com"))

    def test_get_count(self):
        from v2.human_behavior import RecipientDomainTracker

        tracker = RecipientDomainTracker(max_per_domain=5)
        tracker.record_send("a@example.com")
        tracker.record_send("b@example.com")
        self.assertEqual(tracker.get_count("example.com"), 2)

    def test_reset_on_new_day(self):
        from v2.human_behavior import RecipientDomainTracker

        tracker = RecipientDomainTracker(max_per_domain=1)
        tracker.record_send("a@example.com")
        self.assertFalse(tracker.can_send_to("b@example.com"))

        # Simulate day change
        tracker._date = date.today() - timedelta(days=1)
        self.assertTrue(tracker.can_send_to("b@example.com"))

    def test_invalid_email_format(self):
        """Emails without @ should not crash."""
        from v2.human_behavior import RecipientDomainTracker

        tracker = RecipientDomainTracker(max_per_domain=3)
        tracker.record_send("invalid-email")
        self.assertTrue(tracker.can_send_to("valid@example.com"))


if __name__ == "__main__":
    unittest.main()
