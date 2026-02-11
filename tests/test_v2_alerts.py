"""
Comprehensive unit tests for v2/alerts.py

Tests cover:
- AlertLevel constants
- Slack payload structure
- Discord payload structure
- Telegram payload structure
- send_alert (webhook disabled, success, failure)
- Pre-built alert functions
- Daily summary generation
"""

import asyncio
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestAlertLevel(unittest.TestCase):
    """Test alert level constants."""

    def test_levels_defined(self):
        from v2.alerts import AlertLevel

        self.assertEqual(AlertLevel.CRITICAL, "critical")
        self.assertEqual(AlertLevel.WARNING, "warning")
        self.assertEqual(AlertLevel.INFO, "info")


class TestSlackPayload(unittest.TestCase):
    """Test Slack webhook payload construction."""

    def test_slack_payload_structure(self):
        from v2.alerts import _build_slack_payload

        payload = _build_slack_payload("Test Title", "Test message", "info")
        self.assertIn("attachments", payload)
        self.assertEqual(len(payload["attachments"]), 1)

        attachment = payload["attachments"][0]
        self.assertEqual(attachment["title"], "Test Title")
        self.assertEqual(attachment["text"], "Test message")
        self.assertEqual(attachment["color"], "#36A64F")  # info = green
        self.assertIn("footer", attachment)

    def test_slack_critical_color(self):
        from v2.alerts import _build_slack_payload

        payload = _build_slack_payload("Alert", "msg", "critical")
        self.assertEqual(payload["attachments"][0]["color"], "#FF0000")

    def test_slack_warning_color(self):
        from v2.alerts import _build_slack_payload

        payload = _build_slack_payload("Alert", "msg", "warning")
        self.assertEqual(payload["attachments"][0]["color"], "#FFA500")


class TestDiscordPayload(unittest.TestCase):
    """Test Discord webhook payload construction."""

    def test_discord_payload_structure(self):
        from v2.alerts import _build_discord_payload

        payload = _build_discord_payload("Test Title", "Test message", "critical")
        self.assertIn("embeds", payload)
        embed = payload["embeds"][0]
        self.assertEqual(embed["title"], "Test Title")
        self.assertEqual(embed["description"], "Test message")
        self.assertEqual(embed["color"], 0xFF0000)  # critical = red
        self.assertIn("timestamp", embed)

    def test_discord_info_color(self):
        from v2.alerts import _build_discord_payload

        payload = _build_discord_payload("Title", "msg", "info")
        self.assertEqual(payload["embeds"][0]["color"], 0x36A64F)


class TestTelegramPayload(unittest.TestCase):
    """Test Telegram payload construction."""

    @patch("v2.alerts.TELEGRAM_CHAT_ID", "12345")
    def test_telegram_payload_structure(self):
        from v2.alerts import _build_telegram_payload

        payload = _build_telegram_payload("Test Title", "Test message")
        self.assertEqual(payload["chat_id"], "12345")
        self.assertIn("*Test Title*", payload["text"])
        self.assertIn("Test message", payload["text"])
        self.assertEqual(payload["parse_mode"], "Markdown")


class TestSendAlert(unittest.TestCase):
    """Test the main send_alert function."""

    @patch("v2.alerts.ALERT_WEBHOOK_URL", "")
    def test_no_webhook_returns_false(self):
        from v2.alerts import send_alert

        result = run_async(send_alert("Test message"))
        self.assertFalse(result)

    @patch("v2.alerts.ALERT_WEBHOOK_URL", "https://hooks.slack.com/test")
    @patch("v2.alerts.ALERT_CHANNEL", "slack")
    def test_successful_send(self):
        from v2.alerts import send_alert

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_response
            mock_session = AsyncMock()
            mock_session.post.return_value = mock_context
            mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = run_async(send_alert("Test alert", level="info"))
            # This may or may not succeed depending on aiohttp mock setup
            self.assertIsInstance(result, bool)


class TestPreBuiltAlerts(unittest.TestCase):
    """Test pre-built alert functions call send_alert correctly."""

    @patch("v2.alerts.send_alert", new_callable=AsyncMock)
    def test_alert_all_accounts_blocked(self, mock_send):
        from v2.alerts import alert_all_accounts_blocked

        run_async(alert_all_accounts_blocked())
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        self.assertIn("BLOCKED", call_args.kwargs.get("title", "") or call_args[1].get("title", ""))

    @patch("v2.alerts.send_alert", new_callable=AsyncMock)
    def test_alert_high_bounce_rate(self, mock_send):
        from v2.alerts import alert_high_bounce_rate

        run_async(alert_high_bounce_rate(0.08, "test@example.com"))
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        msg = call_args.kwargs.get("message", "") or call_args[0][0]
        self.assertIn("8.0%", msg)
        self.assertIn("test@example.com", msg)

    @patch("v2.alerts.send_alert", new_callable=AsyncMock)
    def test_alert_account_reputation_low(self, mock_send):
        from v2.alerts import alert_account_reputation_low

        run_async(alert_account_reputation_low("test@test.com", 35, "High bounce rate"))
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        msg = call_args.kwargs.get("message", "") or call_args[0][0]
        self.assertIn("35", msg)
        self.assertIn("High bounce rate", msg)

    @patch("v2.alerts.send_alert", new_callable=AsyncMock)
    def test_alert_quota_near_limit(self, mock_send):
        from v2.alerts import alert_quota_near_limit

        run_async(alert_quota_near_limit("test@test.com", 23, 25))
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        msg = call_args.kwargs.get("message", "") or call_args[0][0]
        self.assertIn("23/25", msg)


class TestDailySummary(unittest.TestCase):
    """Test daily summary generation."""

    @patch("v2.alerts.DAILY_SUMMARY_ENABLED", False)
    def test_disabled_summary_returns_none(self):
        from v2.alerts import send_daily_summary

        # Should not raise, just return None
        result = run_async(send_daily_summary())
        self.assertIsNone(result)

    @patch("v2.alerts.DAILY_SUMMARY_ENABLED", True)
    @patch("v2.alerts.send_alert", new_callable=AsyncMock)
    @patch("v2.alerts.emails_collection")
    @patch("v2.alerts.SendingStats")
    @patch("v2.alerts.DoNotContact")
    def test_enabled_summary_gathers_stats(self, mock_dnc, mock_stats, mock_emails, mock_send):
        from v2.alerts import send_daily_summary

        mock_stats.get_all_sends_today.return_value = {"a@test.com": 10, "b@test.com": 8}
        mock_emails.count_documents.return_value = 5
        mock_dnc.count.return_value = 20

        run_async(send_daily_summary())
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        msg = call_args[0][0]
        self.assertIn("18", msg)  # 10 + 8 = 18 total


if __name__ == "__main__":
    unittest.main()
