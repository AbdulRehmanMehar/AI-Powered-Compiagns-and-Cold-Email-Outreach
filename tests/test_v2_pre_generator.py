"""
Comprehensive unit tests for v2/pre_generator.py

Tests cover:
- EmailDraft CRUD operations (create, mark_ready, mark_failed, etc.)
- Draft lifecycle transitions
- Atomic claim_next_ready
- Stale draft cleanup
- Draft stats aggregation
- has_draft_for_lead deduplication
- PreGenerator._review_and_rewrite logic
- Initial draft generation flow
- Follow-up draft generation flow
"""

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call
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


class TestDraftStatus(unittest.TestCase):
    """Test DraftStatus constants."""

    def test_all_statuses_defined(self):
        from v2.pre_generator import DraftStatus

        self.assertEqual(DraftStatus.GENERATING, "generating")
        self.assertEqual(DraftStatus.REVIEW_FAILED, "review_failed")
        self.assertEqual(DraftStatus.READY, "ready_to_send")
        self.assertEqual(DraftStatus.CLAIMED, "claimed")
        self.assertEqual(DraftStatus.SENT, "sent")
        self.assertEqual(DraftStatus.FAILED, "failed")
        self.assertEqual(DraftStatus.SKIPPED, "skipped")

    def test_statuses_are_unique(self):
        from v2.pre_generator import DraftStatus

        statuses = [
            DraftStatus.GENERATING, DraftStatus.REVIEW_FAILED,
            DraftStatus.READY, DraftStatus.CLAIMED, DraftStatus.SENT,
            DraftStatus.FAILED, DraftStatus.SKIPPED,
        ]
        self.assertEqual(len(statuses), len(set(statuses)))


class TestEmailDraftCreate(unittest.TestCase):
    """Test EmailDraft.create."""

    @patch("v2.pre_generator.email_drafts_collection")
    def test_create_returns_string_id(self, mock_coll):
        from v2.pre_generator import EmailDraft

        mock_result = MagicMock()
        mock_result.inserted_id = ObjectId()
        mock_coll.insert_one.return_value = mock_result

        draft_id = EmailDraft.create(
            lead_id=str(ObjectId()),
            campaign_id=str(ObjectId()),
            email_type="initial",
            to_email="test@example.com",
        )
        self.assertIsInstance(draft_id, str)
        self.assertEqual(len(draft_id), 24)  # ObjectId hex length

    @patch("v2.pre_generator.email_drafts_collection")
    def test_create_sets_generating_status(self, mock_coll):
        from v2.pre_generator import EmailDraft, DraftStatus

        mock_result = MagicMock()
        mock_result.inserted_id = ObjectId()
        mock_coll.insert_one.return_value = mock_result

        EmailDraft.create(
            lead_id=str(ObjectId()),
            campaign_id=str(ObjectId()),
            email_type="initial",
        )

        call_args = mock_coll.insert_one.call_args
        doc = call_args[0][0]
        self.assertEqual(doc["status"], DraftStatus.GENERATING)
        self.assertIsNotNone(doc["created_at"])

    @patch("v2.pre_generator.email_drafts_collection")
    def test_create_stores_all_fields(self, mock_coll):
        from v2.pre_generator import EmailDraft

        mock_result = MagicMock()
        mock_result.inserted_id = ObjectId()
        mock_coll.insert_one.return_value = mock_result

        lead_id = str(ObjectId())
        campaign_id = str(ObjectId())

        EmailDraft.create(
            lead_id=lead_id,
            campaign_id=campaign_id,
            email_type="followup",
            followup_number=1,
            to_email="john@example.com",
            to_name="John",
            subject="Test Subject",
            body="Test body",
            in_reply_to="<msg123@example.com>",
            references=["<msg123@example.com>"],
        )

        doc = mock_coll.insert_one.call_args[0][0]
        self.assertEqual(doc["email_type"], "followup")
        self.assertEqual(doc["followup_number"], 1)
        self.assertEqual(doc["to_email"], "john@example.com")
        self.assertEqual(doc["to_name"], "John")
        self.assertEqual(doc["subject"], "Test Subject")
        self.assertEqual(doc["in_reply_to"], "<msg123@example.com>")


class TestEmailDraftTransitions(unittest.TestCase):
    """Test draft status transition methods."""

    @patch("v2.pre_generator.email_drafts_collection")
    def test_mark_ready(self, mock_coll):
        from v2.pre_generator import EmailDraft, DraftStatus

        draft_id = str(ObjectId())
        EmailDraft.mark_ready(draft_id, "Subject", "Body text", 85)

        mock_coll.update_one.assert_called_once()
        call_args = mock_coll.update_one.call_args
        update_doc = call_args[0][1]["$set"]
        self.assertEqual(update_doc["status"], DraftStatus.READY)
        self.assertEqual(update_doc["quality_score"], 85)
        self.assertTrue(update_doc["review_passed"])
        self.assertEqual(update_doc["subject"], "Subject")

    @patch("v2.pre_generator.email_drafts_collection")
    def test_mark_review_failed(self, mock_coll):
        from v2.pre_generator import EmailDraft, DraftStatus

        draft_id = str(ObjectId())
        EmailDraft.mark_review_failed(draft_id, 45, "Score too low")

        call_args = mock_coll.update_one.call_args
        update_doc = call_args[0][1]["$set"]
        self.assertEqual(update_doc["status"], DraftStatus.REVIEW_FAILED)
        self.assertEqual(update_doc["quality_score"], 45)
        self.assertFalse(update_doc["review_passed"])

    @patch("v2.pre_generator.email_drafts_collection")
    def test_mark_sent(self, mock_coll):
        from v2.pre_generator import EmailDraft, DraftStatus

        draft_id = str(ObjectId())
        EmailDraft.mark_sent(draft_id, "<msg@test.com>", "sender@test.com")

        call_args = mock_coll.update_one.call_args
        update_doc = call_args[0][1]["$set"]
        self.assertEqual(update_doc["status"], DraftStatus.SENT)
        self.assertEqual(update_doc["smtp_message_id"], "<msg@test.com>")
        self.assertEqual(update_doc["actual_from_email"], "sender@test.com")

    @patch("v2.pre_generator.email_drafts_collection")
    def test_mark_failed_increments_retry(self, mock_coll):
        from v2.pre_generator import EmailDraft, DraftStatus

        draft_id = str(ObjectId())
        EmailDraft.mark_failed(draft_id, "SMTP timeout")

        call_args = mock_coll.update_one.call_args
        update = call_args[0][1]
        self.assertEqual(update["$set"]["status"], DraftStatus.FAILED)
        self.assertEqual(update["$set"]["error_message"], "SMTP timeout")
        self.assertEqual(update["$inc"]["retry_count"], 1)

    @patch("v2.pre_generator.email_drafts_collection")
    def test_release_claimed(self, mock_coll):
        from v2.pre_generator import EmailDraft, DraftStatus

        draft_id = str(ObjectId())
        EmailDraft.release_claimed(draft_id)

        call_args = mock_coll.update_one.call_args
        query = call_args[0][0]
        self.assertEqual(query["status"], DraftStatus.CLAIMED)
        update_doc = call_args[0][1]["$set"]
        self.assertEqual(update_doc["status"], DraftStatus.READY)


class TestEmailDraftClaim(unittest.TestCase):
    """Test atomic claim operation."""

    @patch("v2.pre_generator.email_drafts_collection")
    def test_claim_returns_doc(self, mock_coll):
        from v2.pre_generator import EmailDraft, DraftStatus

        mock_doc = {
            "_id": ObjectId(),
            "to_email": "test@example.com",
            "email_type": "initial",
            "status": DraftStatus.CLAIMED,
        }
        mock_coll.find_one_and_update.return_value = mock_doc

        result = EmailDraft.claim_next_ready()
        self.assertIsNotNone(result)
        self.assertEqual(result["to_email"], "test@example.com")

    @patch("v2.pre_generator.email_drafts_collection")
    def test_claim_returns_none_when_empty(self, mock_coll):
        from v2.pre_generator import EmailDraft

        mock_coll.find_one_and_update.return_value = None
        result = EmailDraft.claim_next_ready()
        self.assertIsNone(result)

    @patch("v2.pre_generator.email_drafts_collection")
    def test_claim_with_from_account(self, mock_coll):
        from v2.pre_generator import EmailDraft, DraftStatus

        mock_coll.find_one_and_update.return_value = {"_id": ObjectId(), "to_email": "t@t.com", "email_type": "initial"}

        EmailDraft.claim_next_ready(from_account="sender@test.com")
        call_args = mock_coll.find_one_and_update.call_args
        query = call_args[0][0]
        self.assertEqual(query["from_account"], "sender@test.com")
        self.assertEqual(query["status"], DraftStatus.READY)


class TestEmailDraftCleanup(unittest.TestCase):
    """Test stale draft cleanup."""

    @patch("v2.pre_generator.email_drafts_collection")
    def test_cleanup_stale_drafts(self, mock_coll):
        from v2.pre_generator import EmailDraft

        mock_result = MagicMock()
        mock_result.modified_count = 3
        mock_coll.update_many.return_value = mock_result

        EmailDraft.cleanup_stale_claimed(timeout_minutes=30)

        mock_coll.update_many.assert_called_once()
        call_args = mock_coll.update_many.call_args
        query = call_args[0][0]
        self.assertEqual(query["status"], "claimed")
        self.assertIn("claimed_at", query)


class TestEmailDraftStats(unittest.TestCase):
    """Test draft statistics aggregation."""

    @patch("v2.pre_generator.email_drafts_collection")
    def test_get_stats(self, mock_coll):
        from v2.pre_generator import EmailDraft

        mock_coll.aggregate.return_value = iter([
            {"_id": "ready_to_send", "count": 10},
            {"_id": "sent", "count": 50},
            {"_id": "failed", "count": 2},
        ])

        stats = EmailDraft.get_stats()
        self.assertEqual(stats["ready_to_send"], 10)
        self.assertEqual(stats["sent"], 50)
        self.assertEqual(stats["failed"], 2)

    @patch("v2.pre_generator.email_drafts_collection")
    def test_get_ready_count(self, mock_coll):
        from v2.pre_generator import EmailDraft

        mock_coll.count_documents.return_value = 7
        self.assertEqual(EmailDraft.get_ready_count(), 7)


class TestHasDraftForLead(unittest.TestCase):
    """Test draft deduplication."""

    @patch("v2.pre_generator.email_drafts_collection")
    def test_has_draft_true(self, mock_coll):
        from v2.pre_generator import EmailDraft

        mock_coll.count_documents.return_value = 1
        result = EmailDraft.has_draft_for_lead(
            str(ObjectId()), str(ObjectId()), "initial"
        )
        self.assertTrue(result)

    @patch("v2.pre_generator.email_drafts_collection")
    def test_has_draft_false(self, mock_coll):
        from v2.pre_generator import EmailDraft

        mock_coll.count_documents.return_value = 0
        result = EmailDraft.has_draft_for_lead(
            str(ObjectId()), str(ObjectId()), "initial"
        )
        self.assertFalse(result)

    @patch("v2.pre_generator.email_drafts_collection")
    def test_followup_includes_number(self, mock_coll):
        from v2.pre_generator import EmailDraft

        mock_coll.count_documents.return_value = 0
        EmailDraft.has_draft_for_lead(
            str(ObjectId()), str(ObjectId()), "followup", followup_number=1
        )
        query = mock_coll.count_documents.call_args[0][0]
        self.assertEqual(query["followup_number"], 1)


class TestReviewAndRewrite(unittest.TestCase):
    """Test the review + rewrite loop."""

    def test_high_score_returns_immediately(self):
        from v2.pre_generator import PreGenerator

        pg = PreGenerator()
        pg._reviewer = MagicMock()
        pg._reviewer.review_email.return_value = {"overall_score": 85}

        subj, body, score = pg._review_and_rewrite("Test Subject", "Test body", {}, max_rewrites=3)
        self.assertEqual(score, 85)
        self.assertEqual(subj, "Test Subject")
        # Should only call review once since score >= 70
        pg._reviewer.review_email.assert_called_once()

    def test_rewrite_improves_score(self):
        from v2.pre_generator import PreGenerator

        pg = PreGenerator()
        pg._reviewer = MagicMock()
        pg._reviewer.review_email.side_effect = [
            {"overall_score": 50},
            {"overall_score": 75},
        ]
        pg._reviewer.rewrite_email.return_value = {
            "subject": "Better Subject",
            "body": "Better body",
        }

        subj, body, score = pg._review_and_rewrite("Bad Subject", "Bad body", {}, max_rewrites=2)
        self.assertEqual(score, 75)
        self.assertEqual(subj, "Better Subject")

    def test_max_rewrites_respected(self):
        from v2.pre_generator import PreGenerator

        pg = PreGenerator()
        pg._reviewer = MagicMock()
        pg._reviewer.review_email.return_value = {"overall_score": 30}
        pg._reviewer.rewrite_email.return_value = {
            "subject": "Rewritten",
            "body": "Rewritten body",
        }

        subj, body, score = pg._review_and_rewrite("Subject", "Body", {}, max_rewrites=2)
        # Should attempt max_rewrites + 1 reviews total
        self.assertEqual(pg._reviewer.review_email.call_count, 3)
        self.assertEqual(pg._reviewer.rewrite_email.call_count, 2)
        self.assertEqual(score, 30)

    def test_review_exception_handled(self):
        from v2.pre_generator import PreGenerator

        pg = PreGenerator()
        pg._reviewer = MagicMock()
        pg._reviewer.review_email.side_effect = Exception("API timeout")

        subj, body, score = pg._review_and_rewrite("Subject", "Body", {}, max_rewrites=2)
        self.assertEqual(score, 0)  # Best score remains 0


class TestPreGeneratorInit(unittest.TestCase):
    """Test PreGenerator lazy initialization."""

    def test_initial_none(self):
        from v2.pre_generator import PreGenerator

        pg = PreGenerator()
        self.assertIsNone(pg._generator)
        self.assertIsNone(pg._reviewer)

    @patch("v2.pre_generator.EmailDraft")
    @patch("v2.pre_generator.DoNotContact")
    @patch("v2.pre_generator.Email")
    def test_generate_initial_drafts_skips_dnc(self, mock_email, mock_dnc, mock_draft):
        """Leads on DNC should be skipped."""
        from v2.pre_generator import PreGenerator

        pg = PreGenerator()
        pg._generator = MagicMock()
        pg._reviewer = MagicMock()

        mock_draft.has_draft_for_lead.return_value = False
        mock_dnc.is_blocked.return_value = True  # On DNC

        lead_id = ObjectId()
        leads = [{"_id": lead_id, "email": "blocked@test.com", "first_name": "Test"}]
        stats = run_async(pg.generate_initial_drafts(str(ObjectId()), leads))
        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(stats["generated"], 0)


if __name__ == "__main__":
    unittest.main()
