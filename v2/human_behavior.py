"""
Human-Like Sending Behavior Module

Implements all the patterns that make our sending look like a real human:
- Session-based sending (2-3 sessions/day/account, not continuous)
- Gaussian jitter on cooldowns
- Time-of-day send rate variation
- US holiday calendar
- Reply-aware pausing
- Recipient domain throttling
"""

import logging
import random
import math
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import pytz

import config

logger = logging.getLogger("coldemails.human_behavior")


# ==============================================================================
# US Federal Holiday Calendar
# ==============================================================================

def _thanksgiving(year: int) -> date:
    """4th Thursday of November"""
    nov1 = date(year, 11, 1)
    # weekday(): 0=Mon ... 6=Sun; Thursday=3
    offset = (3 - nov1.weekday()) % 7
    first_thu = nov1 + timedelta(days=offset)
    return first_thu + timedelta(weeks=3)


def _memorial_day(year: int) -> date:
    """Last Monday of May"""
    may31 = date(year, 5, 31)
    offset = (may31.weekday() - 0) % 7  # Monday=0
    return may31 - timedelta(days=offset)


def _labor_day(year: int) -> date:
    """First Monday of September"""
    sep1 = date(year, 9, 1)
    offset = (0 - sep1.weekday()) % 7
    return sep1 + timedelta(days=offset)


def _mlk_day(year: int) -> date:
    """3rd Monday of January"""
    jan1 = date(year, 1, 1)
    offset = (0 - jan1.weekday()) % 7
    first_mon = jan1 + timedelta(days=offset)
    return first_mon + timedelta(weeks=2)


def _presidents_day(year: int) -> date:
    """3rd Monday of February"""
    feb1 = date(year, 2, 1)
    offset = (0 - feb1.weekday()) % 7
    first_mon = feb1 + timedelta(days=offset)
    return first_mon + timedelta(weeks=2)


def get_us_holidays(year: int) -> Dict[date, str]:
    """Get all US federal holidays + quiet days for a given year"""
    holidays = {
        date(year, 1, 1): "New Year's Day",
        _mlk_day(year): "Martin Luther King Jr. Day",
        _presidents_day(year): "Presidents' Day",
        _memorial_day(year): "Memorial Day",
        date(year, 6, 19): "Juneteenth",
        date(year, 7, 4): "Independence Day",
        _labor_day(year): "Labor Day",
        date(year, 11, 11): "Veterans Day",
        _thanksgiving(year): "Thanksgiving",
        _thanksgiving(year) + timedelta(days=1): "Day After Thanksgiving",
        date(year, 12, 24): "Christmas Eve",
        date(year, 12, 25): "Christmas Day",
        date(year, 12, 31): "New Year's Eve",
    }
    return holidays


def is_holiday(target_date: date = None) -> Tuple[bool, Optional[str]]:
    """Check if a date is a US holiday (or quiet day adjacent to one)"""
    if target_date is None:
        tz = pytz.timezone(config.TARGET_TIMEZONE)
        target_date = datetime.now(tz).date()

    holidays = get_us_holidays(target_date.year)
    if target_date in holidays:
        logger.info(f"holiday_detected: {target_date} — {holidays[target_date]}")
        return True, holidays[target_date]
    return False, None


# ==============================================================================
# Time-of-Day Multiplier
# ==============================================================================

# Multiplier applied to the base cooldown at different hours of the day.
# Higher multiplier = longer delays = fewer emails.
# Pattern: mild variation to stay human-like without destroying throughput.
# Old values (1.2/2.0/1.3/1.5) cut capacity by ~40%. Flattened to max 1.15.
TIME_OF_DAY_MULTIPLIERS = {
    7: 1.1,    # 07:00-08:00 — Early, slightly slower
    8: 1.05,   # 08:00-09:00 — Warming up
    9: 1.0,    # 09:00-10:00 — Fresh start, normal pace
    10: 1.0,   # 10:00-11:00 — Still energetic
    11: 1.05,  # 11:00-12:00 — Slight pre-lunch slowdown
    12: 1.15,  # 12:00-13:00 — Lunch — mild slow, not a dead hour
    13: 1.05,  # 13:00-14:00 — Post-lunch, nearly normal
    14: 1.0,   # 14:00-15:00 — Back to normal
    15: 1.0,   # 15:00-16:00 — Afternoon push
    16: 1.05,  # 16:00-17:00 — Slight wind-down
    17: 1.1,   # 17:00-18:00 — Late afternoon
    18: 1.15,  # 18:00-19:00 — End of extended day
}


def get_time_of_day_multiplier(hour: int = None) -> float:
    """
    Get the send rate multiplier for the current hour.
    Returns 1.0 for normal speed, >1.0 for slower, <1.0 for faster.
    """
    if hour is None:
        tz = pytz.timezone(config.TARGET_TIMEZONE)
        hour = datetime.now(tz).hour
    return TIME_OF_DAY_MULTIPLIERS.get(hour, 1.0)


# ==============================================================================
# Gaussian Jitter for Cooldowns
# ==============================================================================

def apply_jitter(base_minutes: int, jitter_pct: float = 0.30) -> int:
    """
    Apply Gaussian jitter to a cooldown value.

    Args:
        base_minutes: The base cooldown in minutes (e.g. 25)
        jitter_pct: Maximum deviation as a fraction (0.30 = ±30%)

    Returns:
        Jittered cooldown in minutes (always >= 5)
    """
    sigma = base_minutes * jitter_pct / 2  # 2σ ≈ 95% within range
    jittered = random.gauss(base_minutes, sigma)
    result = max(5, int(round(jittered)))
    logger.debug("jitter_applied", extra={"base": base_minutes, "jitter_pct": jitter_pct, "result": result})
    return result


def get_human_cooldown_minutes() -> int:
    """
    Calculate a human-like cooldown between sends from the same account.

    Combines:
    1. Base cooldown from config (MIN/MAX delay)
    2. Time-of-day multiplier
    3. Bounce-rate slowdown multiplier (auto-throttle if bounces spike)
    4. Gaussian jitter

    Returns:
        Cooldown in minutes
    """
    base = random.randint(config.MIN_DELAY_BETWEEN_EMAILS, config.MAX_DELAY_BETWEEN_EMAILS)
    multiplier = get_time_of_day_multiplier()
    adjusted = int(base * multiplier)
    result = apply_jitter(adjusted)
    logger.debug(
        "cooldown_calculated",
        extra={"base": base, "multiplier": multiplier, "adjusted": adjusted, "final": result},
    )
    return result


# ==============================================================================
# Session-Based Sending
# ==============================================================================

class SendingSession:
    """
    Represents a sending session for one account.

    A session is a block of time where an account sends a burst of emails
    with short cooldowns, followed by a long break before the next session.
    """

    def __init__(self,
                 start_hour: int,
                 start_minute: int,
                 email_count: int,
                 intra_gap_minutes: int = 20):
        self.start_hour = start_hour
        self.start_minute = start_minute
        self.email_count = email_count
        self.intra_gap_minutes = intra_gap_minutes  # average gap between emails in session

    @property
    def start_minutes_from_midnight(self) -> int:
        return self.start_hour * 60 + self.start_minute

    @property
    def duration_minutes(self) -> int:
        return self.email_count * self.intra_gap_minutes

    @property
    def end_minutes_from_midnight(self) -> int:
        return self.start_minutes_from_midnight + self.duration_minutes

    def __repr__(self):
        sh = f"{self.start_hour:02d}:{self.start_minute:02d}"
        eh_total = self.end_minutes_from_midnight
        eh = f"{eh_total // 60:02d}:{eh_total % 60:02d}"
        return f"Session({sh}-{eh}, {self.email_count} emails)"


def plan_daily_sessions(
    session_count: int = 3,
    emails_min: int = 3,
    emails_max: int = 7,
    daily_limit: int = 25,
    send_start_hour: int = None,
    send_end_hour: int = None,
) -> List[SendingSession]:
    """
    Plan sending sessions for one account for today.

    Creates `session_count` sessions spread across the sending window,
    each with a random number of emails, totaling at most `daily_limit`.

    Args:
        session_count: Number of sessions (2-4)
        emails_min: Min emails per session
        emails_max: Max emails per session
        daily_limit: Max total emails for the day
        send_start_hour: Start of sending window (default: config)
        send_end_hour: End of sending window (default: config)

    Returns:
        List of SendingSession objects
    """
    start_h = send_start_hour or config.SENDING_HOUR_START
    end_h = send_end_hour or config.SENDING_HOUR_END

    total_window = (end_h - start_h) * 60  # minutes in the sending window
    if total_window <= 0:
        return []

    # Decide email counts per session
    counts = []
    remaining = daily_limit
    for i in range(session_count):
        if remaining <= 0:
            break
        count = random.randint(emails_min, min(emails_max, remaining))
        counts.append(count)
        remaining -= count

    if not counts:
        return []

    actual_sessions = len(counts)

    # Average intra-email gap
    avg_gap = random.randint(
        config.MIN_DELAY_BETWEEN_EMAILS,
        config.MAX_DELAY_BETWEEN_EMAILS,
    )

    # Estimate total active time
    total_active = sum(c * avg_gap for c in counts)
    total_break = max(0, total_window - total_active)

    # Divide break time into gaps between sessions (including before first)
    gap_slots = actual_sessions + 1
    break_per_slot = total_break // gap_slots if gap_slots > 0 else 0

    sessions = []
    cursor = start_h * 60  # minutes from midnight
    logger.debug(
        "planning_sessions",
        extra={"session_count": actual_sessions, "email_counts": counts, "window": f"{start_h}:00-{end_h}:00"},
    )

    for i, count in enumerate(counts):
        # Add jittered break before this session
        jittered_break = apply_jitter(break_per_slot, jitter_pct=0.40) if break_per_slot > 5 else break_per_slot
        cursor += jittered_break

        s_hour = cursor // 60
        s_min = cursor % 60

        # Don't start a session after the send window
        if s_hour >= end_h:
            break

        session = SendingSession(
            start_hour=s_hour,
            start_minute=s_min,
            email_count=count,
            intra_gap_minutes=avg_gap,
        )
        sessions.append(session)
        cursor += session.duration_minutes

    logger.info(
        f"sessions_planned: {len(sessions)} sessions, "
        f"{sum(s.email_count for s in sessions)} emails: {[repr(s) for s in sessions]}",
    )
    return sessions


def is_within_session(sessions: List[SendingSession], now: datetime = None) -> Tuple[bool, Optional[SendingSession]]:
    """
    Check if the current time falls within any planned session.

    Returns:
        (is_in_session, current_session_or_None)
    """
    if now is None:
        tz = pytz.timezone(config.TARGET_TIMEZONE)
        now = datetime.now(tz)

    current_minutes = now.hour * 60 + now.minute
    for session in sessions:
        if session.start_minutes_from_midnight <= current_minutes <= session.end_minutes_from_midnight:
            return True, session
    return False, None


def next_session_start(sessions: List[SendingSession], now: datetime = None) -> Optional[datetime]:
    """Get the datetime of the next upcoming session start."""
    if now is None:
        tz = pytz.timezone(config.TARGET_TIMEZONE)
        now = datetime.now(tz)

    current_minutes = now.hour * 60 + now.minute
    for session in sessions:
        if session.start_minutes_from_midnight > current_minutes:
            return now.replace(
                hour=session.start_hour,
                minute=session.start_minute,
                second=0,
                microsecond=0,
            )
    return None  # All sessions done for today


# ==============================================================================
# Occasional Break Skipping
# ==============================================================================

def should_skip_send(skip_probability: float = 0.05) -> bool:
    """
    Occasionally skip a send opportunity to simulate a human taking a break.
    Default 5% chance to skip.
    """
    skip = random.random() < skip_probability
    if skip:
        logger.info(f"human_break_skip: probability={skip_probability}")
    return skip


# ==============================================================================
# Reply-Aware Pausing
# ==============================================================================

def get_reply_pause_seconds() -> int:
    """
    When a reply is detected, pause the sending account for a random
    duration to simulate the human reading and responding.

    Returns:
        Pause duration in seconds (30-90 minutes)
    """
    pause = random.randint(30 * 60, 90 * 60)
    logger.info(f"reply_pause: {pause // 60} min ({pause}s)")
    return pause


def get_bounce_slowdown_multiplier(bounce_rate: float) -> float:
    """
    If bounce rate is high, slow down all sending.

    Args:
        bounce_rate: Bounce rate as a fraction (e.g. 0.05 = 5%)

    Returns:
        Multiplier (1.0 = normal, 2.0 = half speed, etc.)
    """
    if bounce_rate >= 0.10:
        multiplier = 3.0  # 10%+ bounce → very slow
    elif bounce_rate >= 0.05:
        multiplier = 2.0  # 5%+ bounce → half speed
    elif bounce_rate >= 0.03:
        multiplier = 1.5  # 3%+ bounce → slightly slower
    else:
        multiplier = 1.0
    if multiplier > 1.0:
        logger.warning(f"bounce_slowdown: rate={bounce_rate:.2%} multiplier={multiplier}x")
    return multiplier


# ==============================================================================
# Recipient Domain Throttling
# ==============================================================================

class RecipientDomainTracker:
    """
    Track how many emails we've sent to each recipient domain today.
    Prevents sending too many emails to the same company/ESP in one day.

    Webmail providers (gmail.com, outlook.com, etc.) are given a much
    higher daily cap because they're not single companies.

    Persisted to MongoDB so counts survive container restarts.
    """

    # Webmail / free-email providers — these are NOT company domains,
    # so the per-domain throttle should be much higher.
    WEBMAIL_PROVIDERS = frozenset({
        "gmail.com", "googlemail.com",
        "outlook.com", "hotmail.com", "live.com", "msn.com",
        "yahoo.com", "ymail.com", "rocketmail.com",
        "aol.com", "aim.com",
        "icloud.com", "me.com", "mac.com",
        "protonmail.com", "proton.me",
        "zoho.com", "zohomail.com",
        "fastmail.com",
        "mail.com", "email.com",
        "gmx.com", "gmx.net",
        "yandex.com", "yandex.ru",
        "tutanota.com", "tuta.io",
    })

    def __init__(self, max_per_domain: int = 3, webmail_multiplier: int = 10):
        self.max_per_domain = max_per_domain
        self.webmail_multiplier = webmail_multiplier
        # MongoDB-backed — collection: domain_send_counts
        from database import db
        self._collection = db["domain_send_counts"]
        self._collection.create_index(
            [("domain", 1), ("date", 1)], unique=True
        )

    def _get_limit(self, domain: str) -> int:
        """Return the daily send limit for a domain."""
        if domain in self.WEBMAIL_PROVIDERS:
            return self.max_per_domain * self.webmail_multiplier
        return self.max_per_domain

    def _today_str(self) -> str:
        """Today's date string in the target timezone."""
        tz = pytz.timezone(config.TARGET_TIMEZONE)
        return datetime.now(tz).strftime("%Y-%m-%d")

    def can_send_to(self, email_address: str) -> bool:
        """Check if we can send another email to this recipient's domain."""
        domain = email_address.split("@")[-1].lower() if "@" in email_address else ""
        if not domain:
            return True
        today = self._today_str()
        record = self._collection.find_one({"domain": domain, "date": today})
        current = record["count"] if record else 0
        limit = self._get_limit(domain)
        allowed = current < limit
        if not allowed:
            logger.info(
                f"domain_throttled: {domain} has {current}/{limit} sends today",
            )
        return allowed

    def record_send(self, email_address: str):
        """Record that we sent an email to this domain (atomic MongoDB upsert)."""
        domain = email_address.split("@")[-1].lower() if "@" in email_address else ""
        if not domain:
            return
        today = self._today_str()
        self._collection.update_one(
            {"domain": domain, "date": today},
            {"$inc": {"count": 1}},
            upsert=True,
        )
        logger.debug(
            "domain_send_recorded",
            extra={"domain": domain, "max": self.max_per_domain},
        )

    def get_count(self, domain: str) -> int:
        """Get current count for a domain."""
        today = self._today_str()
        record = self._collection.find_one({"domain": domain.lower(), "date": today})
        return record["count"] if record else 0

    def get_saturated_domains(self) -> set:
        """
        Return the set of recipient domains that have already reached
        their daily limit today.  Used by claim_next_ready() to pre-filter
        drafts so we never claim→throttle→release the same draft in a loop.
        """
        today = self._today_str()
        # Fetch all domains that have ANY sends today
        cursor = self._collection.find(
            {"date": today},
            {"domain": 1, "count": 1, "_id": 0},
        )
        domains = set()
        for doc in cursor:
            domain = doc["domain"]
            limit = self._get_limit(domain)
            if doc["count"] >= limit:
                domains.add(domain)
        if domains:
            logger.debug(
                f"saturated_domains: {len(domains)} domains at limit "
                f"(sample: {list(domains)[:5]})",
            )
        return domains


# Global instance — shared across the v2 system
domain_tracker = RecipientDomainTracker(
    max_per_domain=int(config.__dict__.get("MAX_EMAILS_PER_RECIPIENT_DOMAIN", 3))
    if hasattr(config, "MAX_EMAILS_PER_RECIPIENT_DOMAIN")
    else 3
)
