from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import time
import random
import logging

from database import Lead, Email, Campaign
from rocketreach_client import RocketReachClient
from email_generator import EmailGenerator
from email_reviewer import EmailReviewer, ReviewStatus, format_review_report
from zoho_sender import ZohoEmailSender, text_to_html
import config

# Module logger
logger = logging.getLogger(__name__)


def get_random_delay() -> int:
    """Get random delay between emails in seconds (from config)"""
    min_delay = config.MIN_DELAY_BETWEEN_EMAILS * 60  # Convert to seconds
    max_delay = config.MAX_DELAY_BETWEEN_EMAILS * 60
    return random.randint(min_delay, max_delay)


class CampaignManager:
    """Orchestrates the entire cold email campaign"""
    
    def __init__(self, enable_review: bool = True, max_rewrites: int = 2):
        self.rocketreach = RocketReachClient()
        self.email_generator = EmailGenerator()
        self.email_sender = ZohoEmailSender()
        self.email_reviewer = EmailReviewer() if enable_review else None
        self.enable_review = enable_review
        self.max_rewrites = max_rewrites
    
    def create_campaign(self,
                        name: str,
                        description: str,
                        target_criteria: Dict[str, Any],
                        campaign_context: Dict[str, Any]) -> str:
        """
        Create a new campaign
        
        Args:
            name: Campaign name
            description: Campaign description
            target_criteria: RocketReach search criteria
            campaign_context: Context for email generation (product_service, value_proposition, etc.)
        
        Returns:
            Campaign ID
        """
        campaign_id = Campaign.create(
            name=name,
            description=description,
            target_criteria={
                **target_criteria,
                "campaign_context": campaign_context
            }
        )
        
        print(f"Created campaign: {name} (ID: {campaign_id})")
        return campaign_id
    
    def fetch_leads_for_campaign(self,
                                  campaign_id: str,
                                  max_leads: int = 50) -> List[Dict]:
        """
        Fetch leads from RocketReach for a campaign
        
        Args:
            campaign_id: Campaign ID
            max_leads: Maximum number of leads to fetch
        
        Returns:
            List of lead dicts
        """
        campaign = Campaign.get_by_id(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign not found: {campaign_id}")
        
        criteria = campaign.get("target_criteria", {})
        
        print(f"Fetching leads for campaign: {campaign['name']}")
        print(f"Criteria: {criteria}")
        
        # Get already-contacted emails to exclude
        contacted_emails = Email.get_contacted_emails()
        print(f"   Excluding {len(contacted_emails)} already-contacted emails")
        
        # Fetch from RocketReach (pass exclude list to skip at source)
        raw_leads = self.rocketreach.fetch_leads(criteria, max_leads, exclude_emails=contacted_emails)
        
        # Save to database
        saved_leads = []
        for lead_data in raw_leads:
            email = lead_data.get("email")
            if email:
                lead_id = Lead.create(lead_data)
                lead = Lead.get_by_id(lead_id)
                saved_leads.append(lead)
        
        # Update campaign stats
        Campaign.increment_stat(campaign_id, "total_leads", len(saved_leads))
        
        print(f"Fetched and saved {len(saved_leads)} leads")
        return saved_leads
    
    def _review_and_rewrite_if_needed(self,
                                       email_content: Dict[str, str],
                                       lead: Dict[str, Any],
                                       campaign_context: Dict[str, Any]) -> tuple:
        """
        Review email and rewrite if it fails quality checks.
        
        Returns:
            (email_content, passed) - The final email and whether it passed review
        """
        if not self.email_reviewer:
            return email_content, True
        
        attempt = 0
        current_email = email_content
        
        while attempt <= self.max_rewrites:
            attempt += 1
            
            # Review the email
            review = self.email_reviewer.review_email(
                email=current_email,
                lead=lead,
                save_review=True  # Store for learning
            )
            
            if not review.rewrite_required:
                if review.status == ReviewStatus.PASS:
                    print(f"   ✅ Email passed review (score: {review.score})")
                else:
                    print(f"   ⚠️ Email passed with warnings (score: {review.score})")
                return current_email, True
            
            # Failed - log issues
            print(f"   ❌ Review failed (attempt {attempt}/{self.max_rewrites + 1}, score: {review.score})")
            for violation in review.rule_violations[:2]:
                print(f"      🚫 {violation}")
            
            if attempt > self.max_rewrites:
                # Max rewrites exhausted
                return current_email, False
            
            # Rewrite with feedback
            print(f"   🔄 Rewriting email with feedback...")
            current_email = self.email_reviewer._rewrite_email(
                email=current_email,
                lead=lead,
                review=review,
                campaign_context=campaign_context
            )
        
        return current_email, False
    
    def send_initial_emails(self,
                            campaign_id: str,
                            leads: List[Dict] = None,
                            dry_run: bool = False) -> Dict[str, Any]:
        """
        Send initial emails to leads in a campaign
        
        Args:
            campaign_id: Campaign ID
            leads: List of leads (if None, fetches all leads for campaign)
            dry_run: If True, generate emails but don't send
        
        Returns:
            Results summary
        """
        campaign = Campaign.get_by_id(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign not found: {campaign_id}")
        
        campaign_context = campaign.get("target_criteria", {}).get("campaign_context", {})
        
        if leads is None:
            leads = Lead.get_all()
        
        results = {
            "total": len(leads),
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "skipped_limit": 0,
            "skipped_time": 0,
            "details": []
        }
        
        # Connect to SMTP server
        if not dry_run:
            if not self.email_sender.connect():
                return {"error": "Failed to connect to email server"}
        
        try:
            for lead in leads:
                lead_id = str(lead["_id"])
                lead_email = lead.get("email", "")
                
                # DEDUPLICATION CHECK 1: Already emailed in this campaign
                existing_emails = Email.get_by_lead_and_campaign(lead_id, campaign_id)
                if existing_emails:
                    print(f"⏭️  Skipping {lead_email} - already emailed in this campaign")
                    results["skipped"] += 1
                    continue
                
                # DEDUPLICATION CHECK 2: Email address already contacted (any campaign)
                if Email.has_been_contacted_by_email(lead_email):
                    print(f"⏭️  Skipping {lead_email} - already contacted in another campaign")
                    results["skipped"] += 1
                    continue
                
                # SPAM PREVENTION: Check weekly limit
                if not Email.can_email_lead(lead_id, max_emails_per_week=3):
                    print(f"⏭️  Skipping {lead_email} - hit weekly email limit")
                    results["skipped"] += 1
                    continue
                
                # Generate personalized email
                print(f"📧 Generating email for {lead['full_name']} ({lead['email']})...")
                email_content = self.email_generator.generate_initial_email(
                    lead=lead,
                    campaign_context=campaign_context
                )
                
                # QUALITY GATE: Review email before sending
                if self.enable_review:
                    email_content, review_passed = self._review_and_rewrite_if_needed(
                        email_content=email_content,
                        lead=lead,
                        campaign_context=campaign_context
                    )
                    
                    if not review_passed:
                        print(f"   🚫 Email failed review after {self.max_rewrites} rewrites - marking for manual review")
                        results["manual_review"] = results.get("manual_review", 0) + 1
                        results["details"].append({
                            "lead_email": lead["email"],
                            "subject": email_content.get("subject", "N/A"),
                            "status": "manual_review_required",
                            "reason": "Failed quality review"
                        })
                        continue  # Skip to next lead
                
                # Create email record
                email_id = Email.create(
                    lead_id=lead_id,
                    campaign_id=campaign_id,
                    subject=email_content["subject"],
                    body=email_content["body"],
                    email_type="initial",
                    followup_number=0
                )
                
                if dry_run:
                    print(f"[DRY RUN] Would send to {lead['email']}:")
                    print(f"  Subject: {email_content['subject']}")
                    results["sent"] += 1
                    results["details"].append({
                        "lead_email": lead["email"],
                        "subject": email_content["subject"],
                        "status": "dry_run"
                    })
                else:
                    # Send the email
                    result = self.email_sender.send_email(
                        to_email=lead["email"],
                        subject=email_content["subject"],
                        body=email_content["body"],
                        to_name=lead.get("full_name"),
                        html_body=text_to_html(email_content["body"])
                    )
                    
                    # Check if we hit limits or time restrictions
                    if not result["success"]:
                        skip_reason = result.get("skip_reason")
                        
                        if skip_reason == "limit":
                            print(f"   🛑 Daily limit reached - stopping campaign for today")
                            results["skipped_limit"] += 1
                            # Don't mark as failed - we'll retry tomorrow
                            # Delete the pending email record
                            from database import emails_collection
                            from bson import ObjectId
                            emails_collection.delete_one({"_id": ObjectId(email_id)})
                            break  # Stop the campaign for today
                        
                        elif skip_reason == "time":
                            print(f"   ⏸️ Outside sending hours - stopping campaign")
                            results["skipped_time"] += 1
                            # Delete the pending email record
                            from database import emails_collection
                            from bson import ObjectId
                            emails_collection.delete_one({"_id": ObjectId(email_id)})
                            break  # Stop the campaign
                        
                        elif skip_reason == "cooldown":
                            # All accounts are in cooldown - wait and retry
                            wait_seconds = result.get("wait_seconds", 60)
                            print(f"   ⏳ All accounts in cooldown, waiting {wait_seconds // 60}m {wait_seconds % 60}s...")
                            time.sleep(wait_seconds + 5)  # Add 5 seconds buffer
                            # Don't increment failed - retry this lead
                            continue
                        
                        else:
                            # Actual send failure
                            Email.mark_failed(email_id, result.get("error", "Unknown error"))
                            results["failed"] += 1
                            results["details"].append({
                                "lead_email": lead["email"],
                                "subject": email_content["subject"],
                                "status": "failed",
                                "error": result.get("error")
                            })
                    else:
                        Email.mark_sent(email_id)
                        Campaign.increment_stat(campaign_id, "emails_sent")
                        results["sent"] += 1
                        results["details"].append({
                            "lead_email": lead["email"],
                            "subject": email_content["subject"],
                            "status": "sent"
                        })
                        # No delay needed here - the per-account cooldown handles rate limiting
                        # Next email will use a different account (rotation)
        
        finally:
            if not dry_run:
                self.email_sender.disconnect()
        
        # Activate campaign if not already active
        if campaign["status"] == Campaign.STATUS_DRAFT:
            Campaign.update_status(campaign_id, Campaign.STATUS_ACTIVE)
        
        print(f"\nResults: Sent {results['sent']}, Failed {results['failed']}, Skipped {results['skipped']}")
        return results
    
    def send_followup_emails(self,
                             campaign_id: str,
                             dry_run: bool = False) -> Dict[str, Any]:
        """
        Send follow-up emails following expert strategy:
        - Email 2 (followup_number=1): Same thread, add value, Day 3
        - Email 3 (followup_number=2): NEW thread, different angle, Day 6
        
        Max 2 follow-ups (3 total emails) per expert advice - shorter sequences = less spam
        
        Args:
            campaign_id: Campaign ID
            dry_run: If True, generate emails but don't send
        
        Returns:
            Results summary
        """
        campaign = Campaign.get_by_id(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign not found: {campaign_id}")
        
        campaign_context = campaign.get("target_criteria", {}).get("campaign_context", {})
        
        # Get leads needing follow-up with proper delay handling
        pending_followups = Email.get_pending_followups(
            campaign_id,
            config.FOLLOWUP_DELAY_DAYS
        )
        
        results = {
            "total": len(pending_followups),
            "sent": 0,
            "failed": 0,
            "skipped_max_reached": 0,
            "details": []
        }
        
        if not pending_followups:
            print("No follow-ups needed at this time")
            return results
        
        print(f"Found {len(pending_followups)} leads needing follow-up")
        
        # Connect to SMTP server
        if not dry_run:
            if not self.email_sender.connect():
                return {"error": "Failed to connect to email server"}
        
        try:
            for followup_data in pending_followups:
                lead_id = str(followup_data["_id"])
                lead = Lead.get_by_id(lead_id)
                
                if not lead:
                    continue
                
                # Get previous emails for context
                previous_emails = Email.get_by_lead_and_campaign(lead_id, campaign_id)
                previous_content = [
                    {"subject": e["subject"], "body": e["body"]}
                    for e in previous_emails
                ]
                
                followup_number = len(previous_emails)
                
                # Expert advice: Max 2 follow-ups (3 total emails)
                if followup_number > config.MAX_FOLLOWUPS:
                    results["skipped_max_reached"] += 1
                    continue
                
                # Generate follow-up email (handles same thread vs new thread internally)
                print(f"Generating follow-up #{followup_number} for {lead['full_name']}...")
                email_content = self.email_generator.generate_followup_email(
                    lead=lead,
                    campaign_context=campaign_context,
                    previous_emails=previous_content,
                    followup_number=followup_number
                )
                
                # Check if this is a new thread (follow-up #2/email #3)
                is_new_thread = email_content.get("new_thread", False)
                if is_new_thread:
                    print(f"  → Starting NEW thread (different angle)")
                
                # Create email record
                email_id = Email.create(
                    lead_id=lead_id,
                    campaign_id=campaign_id,
                    subject=email_content["subject"],
                    body=email_content["body"],
                    email_type="followup" if not is_new_thread else "followup_new_thread",
                    followup_number=followup_number
                )
                
                if dry_run:
                    print(f"[DRY RUN] Would send follow-up to {lead['email']}:")
                    print(f"  Subject: {email_content['subject']}")
                    results["sent"] += 1
                else:
                    # Send the email
                    result = self.email_sender.send_email(
                        to_email=lead["email"],
                        subject=email_content["subject"],
                        body=email_content["body"],
                        to_name=lead.get("full_name"),
                        html_body=text_to_html(email_content["body"])
                    )
                    
                    if result["success"]:
                        Email.mark_sent(email_id)
                        Campaign.increment_stat(campaign_id, "emails_sent")
                        results["sent"] += 1
                        results["details"].append({
                            "lead_email": lead["email"],
                            "followup_number": followup_number,
                            "status": "sent"
                        })
                        # No delay needed - per-account cooldown handles rate limiting
                    else:
                        # Check if we hit limits or time restrictions
                        skip_reason = result.get("skip_reason")
                        
                        if skip_reason == "limit":
                            print(f"   🛑 Daily limit reached - stopping follow-ups for today")
                            results["skipped_limit"] = results.get("skipped_limit", 0) + 1
                            # Delete the pending email record
                            from database import emails_collection
                            from bson import ObjectId
                            emails_collection.delete_one({"_id": ObjectId(email_id)})
                            break
                        
                        elif skip_reason == "time":
                            print(f"   ⏸️ Outside sending hours - stopping follow-ups")
                            results["skipped_time"] = results.get("skipped_time", 0) + 1
                            from database import emails_collection
                            from bson import ObjectId
                            emails_collection.delete_one({"_id": ObjectId(email_id)})
                            break
                        
                        elif skip_reason == "cooldown":
                            # All accounts in cooldown - wait and retry
                            wait_seconds = result.get("wait_seconds", 60)
                            print(f"   ⏳ All accounts in cooldown, waiting {wait_seconds // 60}m {wait_seconds % 60}s...")
                            time.sleep(wait_seconds + 5)
                            continue  # Retry this lead
                        
                        else:
                            Email.mark_failed(email_id, result.get("error", "Unknown error"))
                            results["failed"] += 1
                            results["details"].append({
                                "lead_email": lead["email"],
                                "followup_number": followup_number,
                                "status": "failed",
                                "error": result.get("error")
                            })
        
        finally:
            if not dry_run:
                self.email_sender.disconnect()
        
        print(f"\nFollow-up Results: Sent {results['sent']}, Failed {results['failed']}")
        return results
    
    def run_campaign(self,
                     campaign_id: str,
                     fetch_new_leads: bool = True,
                     max_leads: int = 50,
                     send_initial: bool = True,
                     send_followups: bool = True,
                     dry_run: bool = False) -> Dict[str, Any]:
        """
        Run a complete campaign cycle
        
        Args:
            campaign_id: Campaign ID
            fetch_new_leads: Whether to fetch new leads from RocketReach
            max_leads: Maximum leads to fetch
            send_initial: Whether to send initial emails
            send_followups: Whether to send follow-up emails
            dry_run: If True, don't actually send emails
        
        Returns:
            Combined results
        """
        # Always fetch leads if requested; only gate the actual sending by time/limits.
        status = self.email_sender.get_sending_status()
        results: Dict[str, Any] = {
            "campaign_id": campaign_id,
            "leads_fetched": 0,
            "initial_emails": {},
            "followup_emails": {},
            "remaining_capacity": status["total_remaining"]
        }
        
        # Fetch new leads
        if fetch_new_leads:
            leads = self.fetch_leads_for_campaign(campaign_id, max_leads)
            results["leads_fetched"] = len(leads)

        # Decide whether sending is allowed right now
        sending_allowed = True
        skip_reason: Optional[str] = None
        if not status["can_send_now"] and not dry_run:
            sending_allowed = False
            skip_reason = status["time_reason"]
            print(f"⏸️ {skip_reason}")
        elif status["total_remaining"] == 0 and not dry_run:
            sending_allowed = False
            skip_reason = "All accounts unavailable (blocked or at daily limit)"
            print("🛑 All accounts unavailable (blocked or at daily limit)")
        
        # Send initial emails (delay is now handled internally using config)
        if send_initial:
            if sending_allowed:
                results["initial_emails"] = self.send_initial_emails(
                    campaign_id,
                    dry_run=dry_run
                )
            else:
                results["initial_emails"] = {"skipped": True, "reason": skip_reason}
        
        # Send follow-ups (delay is now handled internally using config)
        if send_followups:
            if sending_allowed:
                results["followup_emails"] = self.send_followup_emails(
                    campaign_id,
                    dry_run=dry_run
                )
            else:
                results["followup_emails"] = {"skipped": True, "reason": skip_reason}
        
        return results
    
    def get_campaign_stats(self, campaign_id: str) -> Dict[str, Any]:
        """Get statistics for a campaign"""
        campaign = Campaign.get_by_id(campaign_id)
        if not campaign:
            return {"error": "Campaign not found"}
        
        return {
            "name": campaign["name"],
            "status": campaign["status"],
            "created_at": campaign["created_at"],
            "stats": campaign.get("stats", {})
        }
    
    def retry_failed_emails(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Retry sending failed emails that are eligible for retry.
        
        Failed emails are retried up to 3 times with increasing delays:
        - 1st retry: after 1 hour
        - 2nd retry: after 6 hours  
        - 3rd retry: after 24 hours
        
        Args:
            dry_run: If True, don't actually send emails
            
        Returns:
            Dict with retry results
        """
        from database import FailedEmails
        
        print("\n" + "="*60)
        print("🔄 RETRY FAILED EMAILS")
        print("="*60)
        
        # Get eligible emails for retry
        emails_to_retry = FailedEmails.get_emails_to_retry()
        
        if not emails_to_retry:
            print("   ✅ No failed emails eligible for retry")
            return {"retried": 0, "succeeded": 0, "failed_again": 0}
        
        print(f"   📧 Found {len(emails_to_retry)} email(s) to retry")
        
        results = {
            "retried": 0,
            "succeeded": 0,
            "failed_again": 0,
            "details": []
        }
        
        for email in emails_to_retry:
            lead = email.get("lead", {})
            retry_count = email.get("retry_count", 0)
            
            print(f"\n   🔄 Retry #{retry_count + 1} for {lead.get('email', 'unknown')}")
            
            if dry_run:
                print(f"      [DRY RUN] Would retry sending to {lead.get('email')}")
                results["retried"] += 1
                continue
            
            # Attempt to send
            result = self.email_sender.send_email(
                to_email=lead.get("email"),
                subject=email.get("subject", "Follow up"),
                body=email.get("body", ""),
                to_name=lead.get("full_name"),
                html_body=text_to_html(email.get("body", ""))
            )
            
            results["retried"] += 1
            
            if result["success"]:
                FailedEmails.mark_retry_attempt(str(email["_id"]), success=True)
                results["succeeded"] += 1
                results["details"].append({
                    "email": lead.get("email"),
                    "status": "succeeded",
                    "retry_count": retry_count + 1
                })
                print(f"      ✅ Retry succeeded!")
            else:
                FailedEmails.mark_retry_attempt(str(email["_id"]), success=False, error=result.get("error"))
                results["failed_again"] += 1
                results["details"].append({
                    "email": lead.get("email"),
                    "status": "failed_again",
                    "retry_count": retry_count + 1,
                    "error": result.get("error")
                })
                print(f"      ❌ Retry failed: {result.get('error')}")
            
            # Rate limiting between retries
            if results["retried"] < len(emails_to_retry):
                delay = get_random_delay()
                print(f"      ⏳ Waiting {delay // 60}m before next retry...")
                time.sleep(delay)
        
        print(f"\n   📊 Retry Summary: {results['succeeded']}/{results['retried']} succeeded")
        return results
    
    def get_blocked_accounts_status(self) -> List[Dict]:
        """Get list of currently blocked email accounts"""
        from database import BlockedAccounts
        return BlockedAccounts.get_all_blocked()
    
    def get_failed_email_stats(self) -> Dict:
        """Get statistics about failed emails"""
        from database import FailedEmails
        return FailedEmails.get_retry_stats()


# Example usage
if __name__ == "__main__":
    manager = CampaignManager()
    
    # Example: Create a campaign
    campaign_id = manager.create_campaign(
        name="Tech Startup CEOs - Q1 2026",
        description="Outreach to tech startup CEOs for Prime Strides services",
        target_criteria={
            "current_title": ["CEO", "Founder", "Co-Founder"],
            "industry": ["Technology", "Software"],
            "location": ["United States"]
        },
        campaign_context={
            "product_service": "AI-powered growth marketing services",
            "value_proposition": "help tech startups scale their customer acquisition by 3x in 90 days",
            "company_name": "Prime Strides",
            "call_to_action": "schedule a free 15-minute strategy call",
            "sender_name": "The Prime Strides Team",
            "additional_context": "We specialize in working with early-stage startups and have helped 50+ companies achieve product-market fit."
        }
    )
    
    print(f"\nCampaign created with ID: {campaign_id}")
    print("\nTo run the campaign:")
    print(f"  manager.run_campaign('{campaign_id}', dry_run=True)  # Test run")
    print(f"  manager.run_campaign('{campaign_id}')  # Actual run")
