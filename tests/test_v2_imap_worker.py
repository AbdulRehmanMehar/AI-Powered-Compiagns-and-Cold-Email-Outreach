"""
Comprehensive unit tests for v2/imap_worker.py

Tests cover:
- Email address extraction
- Subject decoding (including encoded headers)
- Email body extraction (multipart and plain)
- Auto-reply detection (temporary + permanent)
- Unsubscribe request detection
- Bounce detection (soft + hard)
- Pattern completeness validation
- ImapWorker initialization + shutdown
"""

import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestExtractEmailAddress(unittest.TestCase):
    """Test email address extraction from From header."""

    def test_angle_bracket_format(self):
        from v2.imap_worker import _extract_email_address

        result = _extract_email_address("John Doe <john@example.com>")
        self.assertEqual(result, "john@example.com")

    def test_plain_email(self):
        from v2.imap_worker import _extract_email_address

        result = _extract_email_address("john@example.com")
        self.assertEqual(result, "john@example.com")

    def test_quoted_name(self):
        from v2.imap_worker import _extract_email_address

        result = _extract_email_address('"Doe, John" <john@example.com>')
        self.assertEqual(result, "john@example.com")

    def test_empty_string(self):
        from v2.imap_worker import _extract_email_address

        result = _extract_email_address("")
        self.assertEqual(result, "")

    def test_none_input(self):
        from v2.imap_worker import _extract_email_address

        result = _extract_email_address(None)
        self.assertEqual(result, "")

    def test_case_normalized(self):
        from v2.imap_worker import _extract_email_address

        result = _extract_email_address("TEST@EXAMPLE.COM")
        self.assertEqual(result, "test@example.com")


class TestDecodeSubject(unittest.TestCase):
    """Test email subject decoding."""

    def test_plain_subject(self):
        from v2.imap_worker import _decode_subject

        self.assertEqual(_decode_subject("Hello World"), "Hello World")

    def test_none_subject(self):
        from v2.imap_worker import _decode_subject

        self.assertEqual(_decode_subject(None), "")

    def test_utf8_encoded(self):
        from v2.imap_worker import _decode_subject

        # RFC 2047 encoded subject
        result = _decode_subject("=?utf-8?B?SGVsbG8gV29ybGQ=?=")
        self.assertEqual(result, "Hello World")


class TestGetEmailBody(unittest.TestCase):
    """Test email body extraction."""

    def test_plain_text_message(self):
        from v2.imap_worker import _get_email_body
        import email

        msg = email.message_from_string(
            "From: test@test.com\r\nContent-Type: text/plain\r\n\r\nHello body"
        )
        body = _get_email_body(msg)
        self.assertIn("Hello body", body)

    def test_multipart_message(self):
        from v2.imap_worker import _get_email_body
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText("Plain text body", "plain"))
        msg.attach(MIMEText("<html>HTML body</html>", "html"))

        body = _get_email_body(msg)
        self.assertIn("Plain text body", body)


class TestAutoReplyDetection(unittest.TestCase):
    """Test auto-reply pattern matching."""

    def test_temporary_ooo(self):
        from v2.imap_worker import _is_auto_reply

        is_ar, is_permanent = _is_auto_reply("Out of Office: Gone till Monday", "")
        self.assertTrue(is_ar)
        self.assertFalse(is_permanent)

    def test_permanent_ooo(self):
        from v2.imap_worker import _is_auto_reply

        is_ar, is_permanent = _is_auto_reply("", "I am no longer with the company.")
        self.assertTrue(is_ar)
        self.assertTrue(is_permanent)

    def test_automatic_reply_subject(self):
        from v2.imap_worker import _is_auto_reply

        is_ar, _ = _is_auto_reply("Automatic Reply: Re: Meeting", "")
        self.assertTrue(is_ar)

    def test_on_vacation(self):
        from v2.imap_worker import _is_auto_reply

        is_ar, _ = _is_auto_reply("On Vacation", "I'm on vacation until next week.")
        self.assertTrue(is_ar)

    def test_not_auto_reply(self):
        from v2.imap_worker import _is_auto_reply

        is_ar, _ = _is_auto_reply("Re: Your proposal", "Thanks for reaching out.")
        self.assertFalse(is_ar)

    def test_has_left_company(self):
        from v2.imap_worker import _is_auto_reply

        is_ar, is_permanent = _is_auto_reply(
            "", "John has left the company effective March 1."
        )
        self.assertTrue(is_ar)
        self.assertTrue(is_permanent)

    def test_mailbox_no_longer_active(self):
        from v2.imap_worker import _is_auto_reply

        is_ar, is_permanent = _is_auto_reply(
            "", "This email address is no longer active."
        )
        self.assertTrue(is_ar)
        self.assertTrue(is_permanent)

    def test_maternity_leave(self):
        from v2.imap_worker import _is_auto_reply

        is_ar, _ = _is_auto_reply("", "I am currently on maternity leave.")
        self.assertTrue(is_ar)

    def test_ooo_prefix(self):
        from v2.imap_worker import _is_auto_reply

        is_ar, _ = _is_auto_reply("OOO: Back next week", "")
        self.assertTrue(is_ar)

    def test_limited_access(self):
        from v2.imap_worker import _is_auto_reply

        is_ar, _ = _is_auto_reply("", "I have limited access to email this week.")
        self.assertTrue(is_ar)


class TestUnsubscribeDetection(unittest.TestCase):
    """Test unsubscribe pattern matching."""

    def test_unsubscribe(self):
        from v2.imap_worker import _is_unsubscribe_request

        self.assertTrue(_is_unsubscribe_request("", "Please unsubscribe me."))

    def test_remove_me(self):
        from v2.imap_worker import _is_unsubscribe_request

        self.assertTrue(_is_unsubscribe_request("Remove me", ""))

    def test_opt_out(self):
        from v2.imap_worker import _is_unsubscribe_request

        self.assertTrue(_is_unsubscribe_request("", "I'd like to opt-out from future emails."))

    def test_stop_emailing(self):
        from v2.imap_worker import _is_unsubscribe_request

        self.assertTrue(_is_unsubscribe_request("", "Please stop emailing me."))

    def test_not_interested(self):
        from v2.imap_worker import _is_unsubscribe_request

        self.assertTrue(_is_unsubscribe_request("Not interested", ""))

    def test_do_not_contact(self):
        from v2.imap_worker import _is_unsubscribe_request

        self.assertTrue(_is_unsubscribe_request("", "Please do not contact me again."))

    def test_normal_reply(self):
        from v2.imap_worker import _is_unsubscribe_request

        self.assertFalse(_is_unsubscribe_request(
            "Re: Partnership opportunity",
            "Yes, I'd be interested in learning more."
        ))

    def test_take_me_off(self):
        from v2.imap_worker import _is_unsubscribe_request

        self.assertTrue(_is_unsubscribe_request("", "Take me off your list."))


class TestBounceIndicators(unittest.TestCase):
    """Test bounce pattern completeness."""

    def test_bounce_indicators_exist(self):
        from v2.imap_worker import BOUNCE_INDICATORS

        self.assertIn("mailer-daemon", BOUNCE_INDICATORS)
        self.assertIn("postmaster", BOUNCE_INDICATORS)
        self.assertIn("delivery failure", BOUNCE_INDICATORS)
        self.assertIn("undeliverable", BOUNCE_INDICATORS)

    def test_hard_bounce_indicators_exist(self):
        from v2.imap_worker import HARD_BOUNCE_INDICATORS

        self.assertIn("user unknown", HARD_BOUNCE_INDICATORS)
        self.assertIn("mailbox not found", HARD_BOUNCE_INDICATORS)
        self.assertIn("550", HARD_BOUNCE_INDICATORS)
        self.assertIn("554", HARD_BOUNCE_INDICATORS)

    def test_all_indicators_lowercase(self):
        from v2.imap_worker import BOUNCE_INDICATORS, HARD_BOUNCE_INDICATORS

        for ind in BOUNCE_INDICATORS:
            self.assertEqual(ind, ind.lower(), f"Indicator not lowercase: {ind}")
        for ind in HARD_BOUNCE_INDICATORS:
            self.assertEqual(ind, ind.lower(), f"Indicator not lowercase: {ind}")


class TestCheckForBounce(unittest.TestCase):
    """Test bounce detection logic."""

    def test_hard_bounce_detected(self):
        from v2.imap_worker import _check_for_bounce

        result = {
            "bounces": 0, "dnc_added": 0,
            "replies": 0, "auto_replies": 0, "unsubscribes": 0, "errors": [],
            "account": "test@test.com",
        }

        with patch("v2.imap_worker.Lead") as mock_lead, \
             patch("v2.imap_worker.emails_collection") as mock_emails, \
             patch("v2.imap_worker.DoNotContact") as mock_dnc:
            mock_lead.get_by_email.return_value = {"_id": "lead123"}
            mock_lead.mark_invalid_email.return_value = None
            mock_dnc.add.return_value = True
            mock_emails.update_many.return_value = MagicMock()

            _check_for_bounce(
                "mailer-daemon@test.com",
                "Mail Delivery Failure",
                "The email for user@invalid.com: 550 User unknown",
                result,
            )

        self.assertEqual(result["bounces"], 1)
        self.assertEqual(result["dnc_added"], 1)

    def test_soft_bounce_no_dnc(self):
        from v2.imap_worker import _check_for_bounce

        result = {
            "bounces": 0, "dnc_added": 0,
            "replies": 0, "auto_replies": 0, "unsubscribes": 0, "errors": [],
            "account": "test@test.com",
        }

        with patch("v2.imap_worker.Lead") as mock_lead, \
             patch("v2.imap_worker.emails_collection") as mock_emails, \
             patch("v2.imap_worker.DoNotContact") as mock_dnc:
            mock_lead.get_by_email.return_value = {"_id": "lead123"}
            mock_lead.mark_invalid_email.return_value = None
            mock_emails.update_many.return_value = MagicMock()

            _check_for_bounce(
                "mailer-daemon@test.com",
                "Mail Delivery Failure",
                "Temporary failure for user@temp.com - mailbox full",
                result,
            )

        self.assertEqual(result["bounces"], 1)
        # Soft bounce should NOT add to DNC
        mock_dnc.add.assert_not_called()

    def test_non_bounce_ignored(self):
        from v2.imap_worker import _check_for_bounce

        result = {"bounces": 0, "dnc_added": 0}
        _check_for_bounce("user@normal.com", "Re: Hello", "Normal reply body", result)
        self.assertEqual(result["bounces"], 0)


class TestImapWorkerInit(unittest.TestCase):
    """Test ImapWorker initialization."""

    @patch("v2.imap_worker.config")
    def test_init_defaults(self, mock_config):
        from v2.imap_worker import ImapWorker

        mock_config.ZOHO_ACCOUNTS = [
            {"email": "a@test.com", "password": "p"},
            {"email": "b@test.com", "password": "p"},
        ]

        worker = ImapWorker(since_days=7)
        self.assertEqual(len(worker.accounts), 2)
        self.assertEqual(worker.since_days, 7)
        self.assertFalse(worker._shutdown.is_set())

    @patch("v2.imap_worker.config")
    def test_shutdown(self, mock_config):
        from v2.imap_worker import ImapWorker

        mock_config.ZOHO_ACCOUNTS = []
        worker = ImapWorker()
        worker.request_shutdown()
        self.assertTrue(worker._shutdown.is_set())


class TestAutoReplyPatterns(unittest.TestCase):
    """Validate pattern lists for completeness and correctness."""

    def test_auto_reply_patterns_count(self):
        from v2.imap_worker import AUTO_REPLY_PATTERNS

        self.assertGreater(len(AUTO_REPLY_PATTERNS), 10)

    def test_permanent_patterns_count(self):
        from v2.imap_worker import PERMANENT_AUTO_REPLY_PATTERNS

        self.assertGreater(len(PERMANENT_AUTO_REPLY_PATTERNS), 4)

    def test_unsubscribe_patterns_count(self):
        from v2.imap_worker import UNSUBSCRIBE_PATTERNS

        self.assertGreater(len(UNSUBSCRIBE_PATTERNS), 8)

    def test_all_patterns_are_valid_regex(self):
        """Every pattern should compile without errors."""
        import re
        from v2.imap_worker import (
            AUTO_REPLY_PATTERNS,
            PERMANENT_AUTO_REPLY_PATTERNS,
            UNSUBSCRIBE_PATTERNS,
        )

        for p in AUTO_REPLY_PATTERNS + PERMANENT_AUTO_REPLY_PATTERNS + UNSUBSCRIBE_PATTERNS:
            try:
                re.compile(p, re.IGNORECASE)
            except re.error as e:
                self.fail(f"Invalid regex pattern '{p}': {e}")


if __name__ == "__main__":
    unittest.main()
