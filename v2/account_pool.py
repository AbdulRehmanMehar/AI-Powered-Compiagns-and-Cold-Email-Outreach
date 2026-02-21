"""
Account Pool — Async-safe account management with reputation scoring.

Wraps existing database.py classes (SendingStats, AccountCooldown,
BlockedAccounts, AccountMetadata) with per-account asyncio.Lock and
adds reputation scoring + warm-down logic.

Key guarantee: At most ONE SMTP connection per account at any given time,
enforced by asyncio.Lock. MongoDB's findOneAndUpdate provides atomic
claiming even if multiple processes share the same DB.
"""

import asyncio
import logging
import math
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytz

import config
from database import (
    AccountCooldown,
    AccountMetadata,
    BlockedAccounts,
    SendingStats,
    Email,
    db,
)
from v2.human_behavior import get_human_cooldown_minutes, domain_tracker

logger = logging.getLogger("coldemails.account_pool")

# Collection for reputation tracking
_reputation_collection = db["account_reputation"]
_reputation_collection.create_index("account_email", unique=True)


class AccountReputation:
    """
    Track per-account sending reputation based on rolling 7-day metrics.

    Score 0-100:
        100 = Perfect (no bounces, good reply rate)
         70 = Threshold — below this the account is auto-paused
          0 = Terrible (many bounces, spam complaints)
    """

    PAUSE_THRESHOLD = 20
    WARNING_THRESHOLD = 40

    @staticmethod
    def compute_score(account_email: str, window_days: int = 3) -> dict:
        """
        Compute reputation score for an account based on recent activity.
        Reduced from 7 to 3 days to focus on recent performance.

        Returns dict with score and breakdown.
        """
        from database import emails_collection
        import pytz
        import config
        
        tz = pytz.timezone(config.TARGET_TIMEZONE)
        cutoff = datetime.now(tz).replace(tzinfo=None) - timedelta(days=window_days)

        pipeline = [
            {
                "$match": {
                    "from_email": account_email,
                    "sent_at": {"$gte": cutoff},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_sent": {"$sum": 1},
                    "bounced": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$status", Email.STATUS_BOUNCED]},
                                1,
                                0,
                            ]
                        }
                    },
                    "replied": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$status", Email.STATUS_REPLIED]},
                                1,
                                0,
                            ]
                        }
                    },
                    "failed": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$status", Email.STATUS_FAILED]},
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
        ]

        results = list(emails_collection.aggregate(pipeline))
        if not results or results[0]["total_sent"] == 0:
            logger.debug("reputation_no_activity", extra={"account": account_email})
            return {
                "score": 100,
                "total_sent": 0,
                "bounce_rate": 0.0,
                "reply_rate": 0.0,
                "fail_rate": 0.0,
                "reason": "No recent activity — default good",
            }

        r = results[0]
        total = r["total_sent"]
        bounce_rate = r["bounced"] / total
        reply_rate = r["replied"] / total
        fail_rate = r["failed"] / total

        # Score calculation:
        # Start at 100, subtract for bad metrics, add for good ones
        score = 100.0

        # Bounces are most damaging (but more reasonable for cold email)
        if bounce_rate > 0.05:
            score -= (bounce_rate - 0.05) * 1000  # 7% bounce = -20

        # Failures (SMTP errors) - lighter penalty  
        if fail_rate > 0.05:
            score -= (fail_rate - 0.05) * 300  # 8% fail = -9

        # Good reply rate is a positive signal (+10 per 1% reply rate)
        score += reply_rate * 1000  # 5% reply rate = +50

        # Block history penalty
        block_count = BlockedAccounts._collection.find_one(
            {"account_email": account_email}
        )
        if block_count and block_count.get("block_count", 0) > 0:
            score -= block_count["block_count"] * 10

        score = max(0, min(100, score))

        reason_parts = []
        if bounce_rate > 0.05:
            reason_parts.append(f"bounce {bounce_rate:.1%}")
        if fail_rate > 0.05:
            reason_parts.append(f"fail {fail_rate:.1%}")
        if reply_rate > 0.02:
            reason_parts.append(f"reply {reply_rate:.1%} (good)")
        reason = ", ".join(reason_parts) if reason_parts else "Normal"

        return {
            "score": round(score),
            "total_sent": total,
            "bounce_rate": round(bounce_rate, 4),
            "reply_rate": round(reply_rate, 4),
            "fail_rate": round(fail_rate, 4),
            "reason": reason,
        }

    @staticmethod
    def save_score(account_email: str, score_data: dict):
        """Persist the computed score to MongoDB."""
        logger.info(
            "reputation_saved",
            extra={
                "account": account_email,
                "score": score_data.get("score"),
                "reason": score_data.get("reason"),
            },
        )
        _reputation_collection.update_one(
            {"account_email": account_email},
            {
                "$set": {
                    **score_data,
                    "account_email": account_email,
                    "computed_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )

    @staticmethod
    def get_saved_score(account_email: str) -> Optional[dict]:
        return _reputation_collection.find_one({"account_email": account_email})

    @staticmethod
    def refresh_all():
        """Recompute and save reputation for all accounts."""
        logger.info(f"reputation_refresh_start: {len(config.PRODUCTION_ACCOUNTS)} accounts")
        for acct in config.PRODUCTION_ACCOUNTS:
            email = acct["email"]
            data = AccountReputation.compute_score(email)
            AccountReputation.save_score(email, data)
            if data["score"] < AccountReputation.WARNING_THRESHOLD:
                logger.warning(
                    f"low_reputation: {email} score={data['score']} reason={data['reason']}",
                )
        logger.info("reputation_refresh_complete")


class WarmDown:
    """
    After an account gets unblocked, gradually ramp back up.
    Day 1: 3 emails, Day 2: 5, Day 3: 10, Day 4+: normal.
    """

    RAMP_SCHEDULE = {0: 3, 1: 5, 2: 10}  # days_since_unblock -> limit

    @staticmethod
    def get_warmdown_limit(account_email: str) -> Optional[int]:
        """
        If this account was recently unblocked, return a reduced daily limit.
        Returns None if no warm-down is active (use normal limit).
        """
        record = BlockedAccounts._collection.find_one({"account_email": account_email})
        if not record:
            return None

        blocked_until = record.get("blocked_until")
        if not blocked_until:
            return None

        # If still blocked, return 0
        now = datetime.utcnow()
        if blocked_until > now:
            return 0

        # Days since unblock
        days_since = (now - blocked_until).days
        limit = WarmDown.RAMP_SCHEDULE.get(days_since)
        if limit is not None:
            logger.info(
                "warmdown_active",
                extra={"account": account_email, "days_since_unblock": days_since, "limit": limit},
            )
        return limit


class AccountPool:
    """
    Async-safe pool of Zoho email accounts.

    Features:
    - Per-account asyncio.Lock (prevents concurrent SMTP on same account)
    - Respects daily limits, warmup, cooldowns, blocks
    - Reputation scoring (auto-pauses degraded accounts)
    - Warm-down after unblock
    - Human-like cooldown calculation
    """

    def __init__(self):
        self.accounts: List[Dict[str, str]] = config.PRODUCTION_ACCOUNTS
        self._locks: Dict[str, asyncio.Lock] = {}
        self.target_tz = pytz.timezone(config.TARGET_TIMEZONE)

        # Clean up expired blocks on startup
        BlockedAccounts.cleanup_expired()

        logger.info(
            "account_pool_init",
            extra={"account_count": len(self.accounts)},
        )

    def _get_lock(self, account_email: str) -> asyncio.Lock:
        """Get or create the lock for an account."""
        if account_email not in self._locks:
            self._locks[account_email] = asyncio.Lock()
        return self._locks[account_email]

    def _get_daily_limit(self, account_email: str) -> int:
        """
        Get daily limit considering warmup + warm-down + global target.

        Priority order:
        1. Warm-down limit (if recently unblocked) — always wins
        2. Warmup limit (if account is young) — caps the account
        3. Global target distribution (if GLOBAL_DAILY_TARGET > 0)
        4. EMAILS_PER_DAY_PER_MAILBOX fallback

        The final limit is also hard-capped at 500 (Zoho's absolute max).
        """
        ZOHO_HARD_CAP = 500

        # Check warm-down first (recently unblocked accounts)
        wd_limit = WarmDown.get_warmdown_limit(account_email)
        if wd_limit is not None:
            return wd_limit

        # Warmup limit (for young accounts)
        warmup_limit = None
        if config.WARMUP_ENABLED:
            age_days = SendingStats.get_account_age_days(account_email)
            week = (age_days // 7) + 1

            warmup_limits = {
                1: config.WARMUP_WEEK1_LIMIT,
                2: config.WARMUP_WEEK2_LIMIT,
                3: config.WARMUP_WEEK3_LIMIT,
                4: config.WARMUP_WEEK4_LIMIT,
            }

            if week >= 4:
                warmup_limit = warmup_limits[4]
            else:
                warmup_limit = warmup_limits.get(week, warmup_limits[1])

        # Global target distribution
        if config.GLOBAL_DAILY_TARGET > 0:
            active_count = len([
                a for a in self.accounts
                if not BlockedAccounts.is_blocked(a["email"])
            ])
            if active_count > 0:
                per_account_from_target = math.ceil(config.GLOBAL_DAILY_TARGET / active_count)
            else:
                per_account_from_target = 0

            # Start from the global-derived limit
            limit = per_account_from_target

            # Warmup still constrains young accounts
            if warmup_limit is not None:
                limit = min(limit, warmup_limit)

            # Never exceed Zoho's hard cap
            final = min(limit, ZOHO_HARD_CAP)

            logger.debug(
                "daily_limit_calculated",
                extra={
                    "account": account_email,
                    "global_target": config.GLOBAL_DAILY_TARGET,
                    "active_accounts": active_count,
                    "per_account_from_target": per_account_from_target,
                    "warmup_limit": warmup_limit,
                    "final": final,
                },
            )
            return final

        # No global target — use legacy per-mailbox cap
        if warmup_limit is not None:
            final = min(warmup_limit, config.EMAILS_PER_DAY_PER_MAILBOX)
        else:
            final = config.EMAILS_PER_DAY_PER_MAILBOX

        final = min(final, ZOHO_HARD_CAP)
        logger.debug(
            "daily_limit_calculated",
            extra={"account": account_email, "warmup_limit": warmup_limit, "final": final},
        )
        return final

    def _can_send_now(self) -> Tuple[bool, str]:
        """Check business hours + weekday in target timezone."""
        now = datetime.now(pytz.UTC).astimezone(self.target_tz)
        hour = now.hour
        dow = now.weekday()  # 0=Mon, 6=Sun

        if dow >= 5 and not config.SEND_ON_WEEKENDS:
            return False, f"Weekend ({now.strftime('%A')}) — paused"
        if hour < config.SENDING_HOUR_START:
            return False, f"Too early ({hour}:00) — starts {config.SENDING_HOUR_START}:00"
        if hour >= config.SENDING_HOUR_END:
            return False, f"Too late ({hour}:00) — ended {config.SENDING_HOUR_END}:00"
        return True, f"OK ({hour}:00 {now.strftime('%Z')})"

    def get_account_status(self, account_email: str) -> dict:
        """Full status for one account."""
        sends_today = SendingStats.get_sends_today(account_email)
        daily_limit = self._get_daily_limit(account_email)
        is_blocked = BlockedAccounts.is_blocked(account_email)
        is_available = AccountCooldown.is_available(account_email)
        secs_left = AccountCooldown.get_seconds_until_available(account_email)

        return {
            "email": account_email,
            "sends_today": sends_today,
            "daily_limit": daily_limit,
            "remaining": max(0, daily_limit - sends_today),
            "blocked": is_blocked,
            "cooldown_available": is_available,
            "cooldown_seconds_left": secs_left,
        }

    async def acquire_account(
        self,
        preferred_email: str = None,
        to_email: str = None,
    ) -> Optional[Dict[str, str]]:
        """
        Acquire the next available account (with its asyncio lock held).

        This method:
        1. Checks business hours
        2. Filters blocked / limit-reached / cooldown accounts
        3. Checks recipient domain throttling
        4. Returns account dict + acquires its asyncio.Lock

        Caller MUST call release_account() when done!

        Args:
            preferred_email: Prefer a specific account (for follow-up thread consistency)
            to_email: Recipient email (for domain throttling)

        Returns:
            Account dict {"email": ..., "password": ..., "sender_name": ...} or None
        """
        can_send, reason = self._can_send_now()
        if not can_send:
            logger.debug("outside_sending_hours", extra={"reason": reason})
            return None

        # Recipient domain throttling
        if to_email and not domain_tracker.can_send_to(to_email):
            logger.info(
                "domain_throttled",
                extra={"to_email": to_email},
            )
            return None

        # Try preferred account first (for thread consistency)
        if preferred_email:
            acct = self._find_account(preferred_email)
            if acct and self._is_eligible(preferred_email):
                lock = self._get_lock(preferred_email)
                if not lock.locked():
                    await lock.acquire()
                    logger.info(f"account_acquired_preferred: {preferred_email} → {to_email}")
                    return acct

        # Collect eligible accounts
        eligible = []
        for acct in self.accounts:
            email = acct["email"]
            if self._is_eligible(email):
                eligible.append(acct)

        if not eligible:
            logger.warning(f"no_accounts_available: 0/{len(self.accounts)} eligible")
            return None

        logger.debug("eligible_accounts", extra={"count": len(eligible), "total": len(self.accounts)})

        # Shuffle for distribution, then try to acquire lock
        random.shuffle(eligible)
        for acct in eligible:
            lock = self._get_lock(acct["email"])
            if not lock.locked():
                await lock.acquire()
                logger.info(f"account_acquired: {acct['email']} → {to_email}")
                return acct

        # All eligible accounts are currently locked (in-flight sends)
        logger.debug("all_accounts_locked")
        return None

    def release_account(self, account_email: str):
        """Release the asyncio.Lock for this account after sending."""
        lock = self._get_lock(account_email)
        if lock.locked():
            lock.release()

    def _get_dynamic_cooldown(self) -> int:
        """
        Calculate cooldown based on how far behind/ahead we are for the day.

        If we're on-pace or ahead → use normal human-like cooldown.
        If we're behind → shorten cooldown to catch up (min 3 min for deliverability).
        If target is met → use normal cooldown.

        This is the KEY feature that makes mid-window deployments survivable:
        after a restart, the system detects it's behind and accelerates.
        """
        if config.GLOBAL_DAILY_TARGET <= 0:
            return get_human_cooldown_minutes()

        now = datetime.now(self.target_tz)
        hour = now.hour + now.minute / 60.0

        # Hours remaining in today's window
        hours_left = max(0.25, config.SENDING_HOUR_END - hour)

        # Total sent today (across all accounts)
        # Use per-account sums with target timezone (consistent with get_sends_today)
        total_sent = sum(
            SendingStats.get_sends_today(a["email"]) for a in self.accounts
        )
        remaining = config.GLOBAL_DAILY_TARGET - total_sent

        if remaining <= 0:
            # Target already met — normal pace for any stragglers
            return get_human_cooldown_minutes()

        # How many active (non-blocked) accounts do we have?
        active = len([
            a for a in self.accounts
            if not BlockedAccounts.is_blocked(a["email"])
        ])
        active = max(1, active)

        # Required sends per hour across all accounts to hit target
        required_per_hour = remaining / hours_left

        # Required sends per account per hour
        per_acct_per_hour = required_per_hour / active

        # Convert to cooldown: 60 min / sends_per_hour = minutes_between_sends
        if per_acct_per_hour > 0:
            ideal_cooldown = 60.0 / per_acct_per_hour
        else:
            ideal_cooldown = get_human_cooldown_minutes()

        # Clamp: never faster than 3 min (deliverability floor),
        #         never slower than 20 min (or we won't finish)
        FLOOR = 3
        CEILING = 20
        dynamic = int(max(FLOOR, min(CEILING, ideal_cooldown)))

        # Compare with normal cooldown — use whichever is SHORTER
        # (we only accelerate, never artificially slow down)
        normal = get_human_cooldown_minutes()
        chosen = min(dynamic, normal)

        if chosen < normal:
            logger.info(
                f"dynamic_pace_catchup: sent={total_sent} remaining={remaining} "
                f"hours_left={hours_left:.1f} cooldown={chosen}min (normal={normal}min) "
                f"rate={required_per_hour:.1f}/hr",
            )

        return chosen

    async def record_send(self, account_email: str, to_email: str = None):
        """
        Record a successful send — update stats, cooldown, domain tracker.
        Called AFTER the SMTP send succeeds.
        
        Uses dynamic pacing: if behind target, shortens cooldowns to catch up.
        Bounce-aware: if bounce rate is elevated, lengthens cooldown to protect reputation.
        """
        # Increment daily counter (atomic $inc)
        SendingStats.increment_send(account_email)

        # Dynamic pacing — accelerates if behind daily target
        cooldown_min = self._get_dynamic_cooldown()
        
        # Check recent bounce rate for this account and auto-throttle
        # Bounce protection OVERRIDES catch-up acceleration (safety first)
        saved_rep = AccountReputation.get_saved_score(account_email)
        if saved_rep and saved_rep.get("bounce_rate", 0) > 0.03:
            from v2.human_behavior import get_bounce_slowdown_multiplier
            slowdown = get_bounce_slowdown_multiplier(saved_rep["bounce_rate"])
            if slowdown > 1.0:
                cooldown_min = int(cooldown_min * slowdown)
        
        AccountCooldown.record_send(account_email, cooldown_min)

        # Track recipient domain
        if to_email:
            domain_tracker.record_send(to_email)

        logger.info(f"send_recorded: {account_email} cooldown={cooldown_min}min to={to_email}")

    def mark_blocked(self, account_email: str, error_msg: str = None):
        """Mark account as blocked (e.g. 554 from Zoho)."""
        BlockedAccounts.mark_blocked(account_email, error_msg)
        logger.error(f"account_blocked: {account_email} error={error_msg}")

    def get_wait_time(self) -> int:
        """
        Seconds until any account becomes available.
        Returns -1 if ALL accounts exhausted for today.
        Returns 0 if one is available now.
        """
        eligible_emails = []
        for acct in self.accounts:
            email = acct["email"]
            if BlockedAccounts.is_blocked(email):
                continue
            sends = SendingStats.get_sends_today(email)
            limit = self._get_daily_limit(email)
            if sends < limit:
                eligible_emails.append(email)

        if not eligible_emails:
            return -1

        _, secs = AccountCooldown.get_soonest_available(eligible_emails)
        return secs

    def get_all_status(self) -> List[dict]:
        """Get status for every account."""
        return [self.get_account_status(a["email"]) for a in self.accounts]

    # ── internal helpers ─────────────────────────────────────────────

    def _find_account(self, email: str) -> Optional[Dict[str, str]]:
        for a in self.accounts:
            if a["email"] == email:
                return a
        return None

    def _is_eligible(self, account_email: str) -> bool:
        """Check if account can send right now (not blocked, under limit, cooldown expired)."""
        if BlockedAccounts.is_blocked(account_email):
            logger.debug("account_ineligible_blocked", extra={"account": account_email})
            return False

        sends = SendingStats.get_sends_today(account_email)
        limit = self._get_daily_limit(account_email)
        if sends >= limit:
            logger.debug(
                "account_ineligible_limit",
                extra={"account": account_email, "sends": sends, "limit": limit},
            )
            return False

        if not AccountCooldown.is_available(account_email):
            logger.debug("account_ineligible_cooldown", extra={"account": account_email})
            return False

        # Reputation check
        saved = AccountReputation.get_saved_score(account_email)
        if saved and saved.get("score", 100) < AccountReputation.PAUSE_THRESHOLD:
            logger.warning(
                "account_paused_reputation",
                extra={"account": account_email, "score": saved["score"]},
            )
            return False

        return True
