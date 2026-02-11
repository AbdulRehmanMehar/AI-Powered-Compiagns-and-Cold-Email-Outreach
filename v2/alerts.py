"""
Alerting Module — Sends notifications via webhook (Slack, Discord, Telegram).

Supports:
- Critical alerts (all accounts blocked, high bounce rate)
- Warning alerts (account reputation low, quota near limit)
- Info (daily summary)
- Custom messages

Configuration via env vars:
    ALERT_WEBHOOK_URL=https://hooks.slack.com/services/...
    ALERT_CHANNEL=slack  (or 'discord', 'telegram')
    DAILY_SUMMARY_ENABLED=true
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Optional

import pytz

import config
from database import Email, SendingStats, DoNotContact, emails_collection

logger = logging.getLogger("coldemails.alerts")

# ── Config ───────────────────────────────────────────────────────────

ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
ALERT_CHANNEL = os.getenv("ALERT_CHANNEL", "slack").lower()
DAILY_SUMMARY_ENABLED = os.getenv("DAILY_SUMMARY_ENABLED", "true").lower() == "true"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


class AlertLevel:
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


async def send_alert(
    message: str,
    level: str = AlertLevel.INFO,
    title: str = None,
) -> bool:
    """
    Send an alert via the configured webhook.

    Args:
        message: Alert body text
        level: AlertLevel.CRITICAL / WARNING / INFO
        title: Optional title/heading

    Returns:
        True if sent successfully, False otherwise
    """
    if not ALERT_WEBHOOK_URL:
        logger.debug(f"Alert skipped (no webhook): [{level}] {message[:80]}")
        return False

    try:
        import aiohttp

        emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(level, "📢")
        heading = title or f"{emoji} Cold Email System — {level.upper()}"

        if ALERT_CHANNEL == "slack":
            payload = _build_slack_payload(heading, message, level)
        elif ALERT_CHANNEL == "discord":
            payload = _build_discord_payload(heading, message, level)
        elif ALERT_CHANNEL == "telegram":
            payload = _build_telegram_payload(heading, message)
        else:
            payload = _build_slack_payload(heading, message, level)  # default

        # Determine URL
        url = ALERT_WEBHOOK_URL
        if ALERT_CHANNEL == "telegram":
            url = f"https://api.telegram.org/bot{ALERT_WEBHOOK_URL}/sendMessage"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status in (200, 204):
                    logger.info(f"Alert sent: [{level}] {(title or message)[:60]}")
                    return True
                else:
                    body = await resp.text()
                    logger.error(f"Alert webhook returned {resp.status}: {body[:200]}")
                    return False

    except ImportError:
        logger.warning("aiohttp not installed — alerts disabled")
        return False
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")
        return False


def _build_slack_payload(title: str, message: str, level: str) -> dict:
    color = {
        "critical": "#FF0000",
        "warning": "#FFA500",
        "info": "#36A64F",
    }.get(level, "#808080")

    return {
        "attachments": [
            {
                "color": color,
                "title": title,
                "text": message,
                "footer": "Cold Email System",
                "ts": int(datetime.utcnow().timestamp()),
            }
        ]
    }


def _build_discord_payload(title: str, message: str, level: str) -> dict:
    color = {
        "critical": 0xFF0000,
        "warning": 0xFFA500,
        "info": 0x36A64F,
    }.get(level, 0x808080)

    return {
        "embeds": [
            {
                "title": title,
                "description": message,
                "color": color,
                "timestamp": datetime.utcnow().isoformat(),
            }
        ]
    }


def _build_telegram_payload(title: str, message: str) -> dict:
    return {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"*{title}*\n\n{message}",
        "parse_mode": "Markdown",
    }


# ── Pre-built alert functions ────────────────────────────────────────


async def alert_all_accounts_blocked():
    await send_alert(
        message=(
            "ALL sending accounts are blocked by Zoho!\n"
            "No emails can be sent until blocks expire.\n"
            "Check blocked_accounts collection for details."
        ),
        level=AlertLevel.CRITICAL,
        title="🚨 ALL ACCOUNTS BLOCKED",
    )


async def alert_high_bounce_rate(bounce_rate: float, account: str = None):
    msg = f"Bounce rate is {bounce_rate:.1%}"
    if account:
        msg += f" for account {account}"
    msg += "\nSending has been slowed down automatically."

    await send_alert(
        message=msg,
        level=AlertLevel.WARNING,
        title="⚠️ High Bounce Rate",
    )


async def alert_account_reputation_low(account: str, score: int, reason: str):
    await send_alert(
        message=(
            f"Account `{account}` reputation score: {score}/100\n"
            f"Reason: {reason}\n"
            f"Account has been auto-paused."
        ),
        level=AlertLevel.WARNING,
        title="⚠️ Account Reputation Low",
    )


async def alert_quota_near_limit(account: str, sends_today: int, daily_limit: int):
    pct = (sends_today / daily_limit * 100) if daily_limit > 0 else 100
    await send_alert(
        message=f"Account `{account}`: {sends_today}/{daily_limit} sent today ({pct:.0f}%)",
        level=AlertLevel.INFO,
        title="ℹ️ Quota Near Limit",
    )


async def send_daily_summary():
    """Generate and send a daily summary of email operations."""
    if not DAILY_SUMMARY_ENABLED:
        logger.debug("daily_summary_disabled")
        return

    logger.info("daily_summary_generating")

    try:
        tz = pytz.timezone(config.TARGET_TIMEZONE)
        now = datetime.now(tz)

        # Gather stats
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        all_sends = SendingStats.get_all_sends_today()
        total_sent = sum(all_sends.values())

        # Count today's bounces and replies
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_replies = emails_collection.count_documents({
            "status": Email.STATUS_REPLIED,
            "replied_at": {"$gte": today_start},
        })
        today_bounces = emails_collection.count_documents({
            "status": Email.STATUS_BOUNCED,
            "sent_at": {"$gte": today_start},
        })

        # DNC stats
        dnc_count = DoNotContact.count()

        # Build message
        lines = [
            f"📅 Date: {now.strftime('%A, %B %d, %Y')}",
            "",
            "📊 **Sending Summary**",
            f"• Total emails sent today: {total_sent}",
            f"• Replies received today: {today_replies}",
            f"• Bounces today: {today_bounces}",
            f"• Do-Not-Contact list size: {dnc_count}",
            "",
            "📧 **Per-Account Breakdown**",
        ]

        for email_addr, count in sorted(all_sends.items()):
            lines.append(f"• {email_addr}: {count} sent")

        if not all_sends:
            lines.append("• No emails sent today")

        # Reply rate
        total_all_time = emails_collection.count_documents(
            {"status": {"$in": [Email.STATUS_SENT, Email.STATUS_REPLIED]}}
        )
        total_replies_all = emails_collection.count_documents(
            {"status": Email.STATUS_REPLIED}
        )
        if total_all_time > 0:
            rate = total_replies_all / total_all_time * 100
            lines.append(f"\n📈 All-time reply rate: {rate:.1f}% ({total_replies_all}/{total_all_time})")

        message = "\n".join(lines)
        await send_alert(message, AlertLevel.INFO, "📋 Daily Email Summary")

    except Exception as e:
        logger.error(f"Failed to generate daily summary: {e}", exc_info=True)
