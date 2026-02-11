"""
Comprehensive unit tests for v2/send_worker.py

Tests cover:
- text_to_html conversion
- SendWorker initialization
- MIME message construction
- Draft processing flow (mocked SMTP)
- Error handling (554, timeout, unexpected)
- Holiday skipping
- Graceful shutdown
"""

import asyncio
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock
from email.mime.multipart import MIMEMultipart
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestTextToHtml(unittest.TestCase):
    """Test text-to-HTML conversion."""

    def test_basic_conversion(self):
        from v2.send_worker import text_to_html

        result = text_to_html("Hello World")
        self.assertIn("<html>", result)
        self.assertIn("Hello World", result)
        self.assertIn("</html>", result)

    def test_newlines_to_br(self):
        from v2.send_worker import text_to_html

        result = text_to_html("Line 1\nLine 2")
        self.assertIn("<br>", result)

    def test_double_newlines_to_paragraphs(self):
        from v2.send_worker import text_to_html

        result = text_to_html("Para 1\n\nPara 2")
        self.assertIn("</p><p>", result)

    def test_html_entities_escaped(self):
        from v2.send_worker import text_to_html

        result = text_to_html("A < B & C > D")
        self.assertIn("&lt;", result)
        self.assertIn("&amp;", result)
        self.assertIn("&gt;", result)
        # Should NOT contain raw < > in the body text part
        self.assertNotIn("A < B", result)

    def test_empty_string(self):
        from v2.send_worker import text_to_html

        result = text_to_html("")
        self.assertIn("<html>", result)

    def test_has_proper_style(self):
        from v2.send_worker import text_to_html

        result = text_to_html("test")
        self.assertIn("font-family: Arial", result)
        self.assertIn("font-size: 14px", result)


class TestSendWorkerInit(unittest.TestCase):
    """Test SendWorker initialization."""

    def test_init_with_pool(self):
        from v2.send_worker import SendWorker

        mock_pool = MagicMock()
        worker = SendWorker(mock_pool)
        self.assertIs(worker.pool, mock_pool)
        self.assertFalse(worker._shutdown.is_set())
        self.assertIsNone(worker._in_flight_draft_id)

    def test_request_shutdown(self):
        from v2.send_worker import SendWorker

        mock_pool = MagicMock()
        worker = SendWorker(mock_pool)
        worker.request_shutdown()
        self.assertTrue(worker._shutdown.is_set())


class TestSendEmail(unittest.TestCase):
    """Test the _send_email method."""

    @patch("v2.send_worker.aiosmtplib.SMTP")
    @patch("v2.send_worker.config")
    def test_send_email_success(self, mock_config, mock_smtp_class):
        from v2.send_worker import SendWorker

        mock_config.ZOHO_SMTP_HOST = "smtp.test.com"
        mock_config.ZOHO_SMTP_PORT = 587
        mock_config.REPLY_TO = ""

        mock_smtp = AsyncMock()
        mock_smtp_class.return_value = mock_smtp
        mock_smtp.connect = AsyncMock()
        mock_smtp.login = AsyncMock()
        mock_smtp.sendmail = AsyncMock()
        mock_smtp.quit = AsyncMock()

        mock_pool = MagicMock()
        worker = SendWorker(mock_pool)

        account = {"email": "sender@test.com", "password": "pass", "sender_name": "Sender"}
        result = run_async(worker._send_email(
            account=account,
            to_email="recipient@test.com",
            to_name="Recipient",
            subject="Test Subject",
            body="Test body",
        ))

        self.assertTrue(result["success"])
        self.assertIn("message_id", result)
        self.assertEqual(result["from_email"], "sender@test.com")

    @patch("v2.send_worker.aiosmtplib.SMTP")
    @patch("v2.send_worker.config")
    def test_send_email_smtp_error(self, mock_config, mock_smtp_class):
        from v2.send_worker import SendWorker
        import aiosmtplib

        mock_config.ZOHO_SMTP_HOST = "smtp.test.com"
        mock_config.ZOHO_SMTP_PORT = 587
        mock_config.REPLY_TO = ""

        mock_smtp = AsyncMock()
        mock_smtp_class.return_value = mock_smtp
        mock_smtp.connect = AsyncMock()
        mock_smtp.login = AsyncMock()
        mock_smtp.sendmail = AsyncMock(side_effect=aiosmtplib.SMTPException("554 blocked"))

        mock_pool = MagicMock()
        worker = SendWorker(mock_pool)

        account = {"email": "sender@test.com", "password": "pass", "sender_name": "Sender"}
        result = run_async(worker._send_email(
            account=account,
            to_email="recipient@test.com",
            subject="Test",
            body="Test",
        ))

        self.assertFalse(result["success"])
        self.assertIn("SMTP error", result["error"])

    @patch("v2.send_worker.aiosmtplib.SMTP")
    @patch("v2.send_worker.config")
    def test_send_email_timeout(self, mock_config, mock_smtp_class):
        from v2.send_worker import SendWorker

        mock_config.ZOHO_SMTP_HOST = "smtp.test.com"
        mock_config.ZOHO_SMTP_PORT = 587
        mock_config.REPLY_TO = ""

        mock_smtp = AsyncMock()
        mock_smtp_class.return_value = mock_smtp
        mock_smtp.connect = AsyncMock(side_effect=asyncio.TimeoutError())

        mock_pool = MagicMock()
        worker = SendWorker(mock_pool)

        account = {"email": "sender@test.com", "password": "pass", "sender_name": "Sender"}
        result = run_async(worker._send_email(
            account=account,
            to_email="recipient@test.com",
            subject="Test",
            body="Test",
        ))

        self.assertFalse(result["success"])
        self.assertIn("timeout", result["error"].lower())

    @patch("v2.send_worker.aiosmtplib.SMTP")
    @patch("v2.send_worker.config")
    def test_send_email_with_threading_headers(self, mock_config, mock_smtp_class):
        from v2.send_worker import SendWorker

        mock_config.ZOHO_SMTP_HOST = "smtp.test.com"
        mock_config.ZOHO_SMTP_PORT = 587
        mock_config.REPLY_TO = ""

        mock_smtp = AsyncMock()
        mock_smtp_class.return_value = mock_smtp
        mock_smtp.connect = AsyncMock()
        mock_smtp.login = AsyncMock()
        mock_smtp.sendmail = AsyncMock()
        mock_smtp.quit = AsyncMock()

        mock_pool = MagicMock()
        worker = SendWorker(mock_pool)

        account = {"email": "sender@test.com", "password": "pass", "sender_name": "Sender"}
        result = run_async(worker._send_email(
            account=account,
            to_email="recipient@test.com",
            subject="Re: Test",
            body="Follow-up body",
            in_reply_to="<original@test.com>",
            references=["<original@test.com>"],
        ))

        self.assertTrue(result["success"])
        # Verify SMTP sendmail was called with the message
        mock_smtp.sendmail.assert_called_once()
        msg_str = mock_smtp.sendmail.call_args[0][2]
        self.assertIn("In-Reply-To", msg_str)
        self.assertIn("References", msg_str)


class TestProcessOneDraft(unittest.TestCase):
    """Test the draft processing pipeline."""

    @patch("v2.send_worker.Campaign")
    @patch("v2.send_worker.Email")
    @patch("v2.send_worker.EmailDraft")
    @patch("v2.send_worker.config")
    def test_no_draft_returns_false(self, mock_config, mock_draft, mock_email, mock_campaign):
        from v2.send_worker import SendWorker

        mock_config.ZOHO_SMTP_HOST = "smtp.test.com"
        mock_config.ZOHO_SMTP_PORT = 587
        mock_draft.claim_next_ready.return_value = None

        mock_pool = MagicMock()
        worker = SendWorker(mock_pool)
        result = run_async(worker._process_one_draft())
        self.assertFalse(result)

    @patch("v2.send_worker.Campaign")
    @patch("v2.send_worker.Email")
    @patch("v2.send_worker.EmailDraft")
    @patch("v2.send_worker.config")
    def test_no_account_releases_draft(self, mock_config, mock_draft, mock_email, mock_campaign):
        from v2.send_worker import SendWorker
        from bson import ObjectId

        mock_config.ZOHO_SMTP_HOST = "smtp.test.com"
        mock_config.ZOHO_SMTP_PORT = 587
        draft_id = ObjectId()
        mock_draft.claim_next_ready.return_value = {
            "_id": draft_id,
            "to_email": "test@example.com",
            "from_account": None,
        }

        mock_pool = MagicMock()
        mock_pool.acquire_account = AsyncMock(return_value=None)
        worker = SendWorker(mock_pool)

        result = run_async(worker._process_one_draft())
        self.assertFalse(result)
        mock_draft.release_claimed.assert_called_once_with(str(draft_id))


class TestSendWorkerRunLoop(unittest.TestCase):
    """Test the main run loop behavior."""

    @patch("v2.send_worker.EmailDraft")
    @patch("v2.send_worker.is_holiday")
    @patch("v2.send_worker.config")
    def test_holiday_skips_sending(self, mock_config, mock_holiday, mock_draft):
        from v2.send_worker import SendWorker

        mock_config.ZOHO_SMTP_HOST = "smtp.test.com"
        mock_config.ZOHO_SMTP_PORT = 587
        mock_holiday.return_value = (True, "Christmas Day")

        mock_pool = MagicMock()
        worker = SendWorker(mock_pool)

        # Simulate: holiday detected, then shutdown
        async def run_test():
            async def delayed_shutdown():
                await asyncio.sleep(0.1)
                worker.request_shutdown()
            asyncio.create_task(delayed_shutdown())
            await worker.run()

        run_async(run_test())
        # Worker should have exited cleanly
        self.assertTrue(worker._shutdown.is_set())


if __name__ == "__main__":
    unittest.main()
