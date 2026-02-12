from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import time
import random
import logging
from bson import ObjectId

from database import Lead, Email, Campaign, DoNotContact, emails_collection, leads_collection
from rocketreach_client import RocketReachClient
from email_generator import EmailGenerator
from email_reviewer import EmailReviewer, ReviewStatus, format_review_report
from email_verifier import EmailVerifier, VerificationStatus
from zoho_sender import ZohoEmailSender, text_to_html
from lead_enricher import enrich_lead_sync, get_enrichment_for_email
import config

# Module logger
logger = logging.getLogger(__name__)

# Global email verifier instance (reused for efficiency)
_email_verifier = None

def get_email_verifier() -> EmailVerifier:
    """Get or create the email verifier instance"""
    global _email_verifier
    if _email_verifier is None:
        # skip_smtp_verify=False means we DO full SMTP verification
        _email_verifier = EmailVerifier(smtp_timeout=10, skip_smtp_verify=False)
        print("🔍 Email verifier initialized (MX + SMTP checks enabled)")
    return _email_verifier


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
    
    def create_campaign_from_icp(self, 
                                  icp_template: str,
                                  custom_context: Dict[str, Any] = None) -> str:
        """
        Create a campaign directly from an ICP template.
        
        This is the recommended way to create campaigns as it:
        1. Uses pre-defined ICP criteria optimized for RocketReach
        2. Ensures leads fetched are likely to be ICP matches
        3. Tracks which ICP template the campaign uses
        
        Args:
            icp_template: Name of ICP template (e.g., 'startup_founders_funded')
            custom_context: Optional overrides for campaign context
        
        Returns:
            Campaign ID
        """
        from icp_manager import ICPManager
        
        manager = ICPManager()
        campaign_config = manager.generate_campaign_from_icp(icp_template, custom_context)
        
        if "error" in campaign_config:
            raise ValueError(campaign_config["error"])
        
        campaign_id = self.create_campaign(
            name=campaign_config["name"],
            description=campaign_config["description"],
            target_criteria=campaign_config["target_criteria"],
            campaign_context=campaign_config["campaign_context"]
        )
        
        print(f"🎯 Campaign created from ICP template: {icp_template}")
        return campaign_id
    
    def get_pending_leads(self, max_leads: int = 50) -> List[Dict[str, Any]]:
        """
        Get leads that have been fetched but never sent an email.
        
        These are leads that:
        1. Exist in the leads collection
        2. Have NO corresponding email record (or only failed/pending records)
        3. Are not in the do-not-contact list
        4. Were created on or after Jan 29, 2026 (after system enhancements)
        
        Uses FIFO ordering (oldest first) so no leads are forgotten.
        
        Returns:
            List of leads waiting to be contacted
        """
        # Only process leads created after system enhancements (Jan 29, 2026)
        cutoff_date = datetime(2026, 1, 29, 0, 0, 0)
        
        # Get all lead IDs that have been successfully sent an email
        sent_lead_ids = set(emails_collection.distinct(
            "lead_id", 
            {"status": {"$in": ["sent", "opened", "replied"]}}
        ))
        
        # Find leads without sent emails - OLDEST FIRST (FIFO)
        # Only include leads created after cutoff date
        # Exclude leads already marked as invalid (bounced, failed verification, RocketReach invalid)
        pending_leads = []
        query = {
            "created_at": {"$gte": cutoff_date},
            "email_invalid": {"$ne": True}
        }
        
        # Placeholder company names that indicate incomplete lead data
        INVALID_COMPANY_NAMES = {
            "stealth startup", "stealth mode", "stealth", "stealth company",
            "undisclosed", "n/a", "none", "unknown", "confidential",
            "private company", "stealth mode startup",
        }
        
        for lead in leads_collection.find(query).sort("created_at", 1).limit(max_leads * 3):
            lead_id = str(lead["_id"])
            email = lead.get("email", "")
            company = (lead.get("company") or lead.get("company_name") or "").strip()
            
            # Skip if already contacted
            if lead_id in sent_lead_ids:
                continue
            # Skip if no email
            if not email:
                continue
            # Skip if in do-not-contact list
            if DoNotContact.is_blocked(email):
                continue
            # Skip placeholder company names (e.g. from Harmonic.AI/RocketReach)
            if company.lower() in INVALID_COMPANY_NAMES or not company:
                continue
                
            pending_leads.append(lead)
            if len(pending_leads) >= max_leads:
                break
        
        return pending_leads
    
    def resume_pending_leads(self, 
                             max_leads: int = 15, 
                             dry_run: bool = False) -> Dict[str, Any]:
        """
        Resume sending emails to leads that were fetched but never contacted.
        
        This ensures no leads are forgotten when campaigns are interrupted
        (e.g., by sending hour restrictions or rate limits).
        
        Returns:
            Results summary
        """
        print(f"\n{'='*60}")
        print(f"🔄 RESUMING PENDING LEADS")
        print(f"{'='*60}")
        
        pending_leads = self.get_pending_leads(max_leads)
        
        if not pending_leads:
            print("✅ No pending leads found - all leads have been contacted!")
            return {
                "resumed": True,
                "pending_count": 0,
                "sent": 0,
                "message": "No pending leads to resume"
            }
        
        print(f"📋 Found {len(pending_leads)} leads waiting to be contacted")
        
        # Group by campaign to get proper context
        leads_by_campaign = {}
        for lead in pending_leads:
            campaign_id = lead.get("campaign_id", "unknown")
            if campaign_id not in leads_by_campaign:
                leads_by_campaign[campaign_id] = []
            leads_by_campaign[campaign_id].append(lead)
        
        total_sent = 0
        total_failed = 0
        
        for campaign_id, leads in leads_by_campaign.items():
            # Get campaign context
            campaign = Campaign.get_by_id(campaign_id) if campaign_id and campaign_id != "unknown" else None
            
            # If campaign was deleted, treat as orphan leads
            if campaign is None and campaign_id != "unknown":
                print(f"\n⚠️  Campaign {campaign_id} no longer exists - treating leads as orphans")
                campaign_id = "unknown"
            
            if campaign:
                campaign_context = campaign.get("target_criteria", {}).get("campaign_context", {})
                print(f"\n📧 Processing {len(leads)} leads from campaign: {campaign.get('name', campaign_id)}")
            else:
                # Use default context for orphan leads
                campaign_context = {}
                print(f"\n📧 Processing {len(leads)} leads (no campaign context)")
            
            # Send emails to these leads
            results = self.send_initial_emails(campaign_id, leads, dry_run=dry_run)
            total_sent += results.get("sent", 0)
            total_failed += results.get("failed", 0)
            
            # Check if we hit time restriction
            if results.get("skipped_time", 0) > 0:
                print(f"   ⏸️ Hit sending hours restriction - will continue later")
                break
        
        print(f"\n{'='*60}")
        print(f"✅ RESUME COMPLETE: {total_sent} emails sent, {total_failed} failed")
        print(f"{'='*60}\n")
        
        return {
            "resumed": True,
            "pending_count": len(pending_leads),
            "sent": total_sent,
            "failed": total_failed,
            "campaigns_processed": len(leads_by_campaign)
        }
    
    def run_icp_campaign(self,
                         icp_template: str,
                         max_leads: int = 15,
                         dry_run: bool = False,
                         custom_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        End-to-end campaign execution from an ICP template.
        
        This is the simplest way to run a campaign:
        1. Creates campaign from ICP template
        2. Fetches leads matching ICP criteria from RocketReach
        3. Generates and sends personalized emails
        4. Tracks ICP status on every lead and email
        
        Args:
            icp_template: Name of ICP template
            max_leads: Maximum leads to fetch
            dry_run: If True, generate but don't send
            custom_context: Optional campaign context overrides
        
        Returns:
            Results summary
        """
        from icp_manager import ICPManager
        from primestrides_context import ICP_TEMPLATES
        
        # Validate ICP template exists
        if icp_template not in ICP_TEMPLATES:
            available = list(ICP_TEMPLATES.keys())
            return {"error": f"Unknown ICP template: {icp_template}", "available": available}
        
        print(f"\n{'='*60}")
        print(f"🎯 RUNNING ICP CAMPAIGN: {icp_template}")
        print(f"{'='*60}")
        
        # Step 1: Create campaign
        campaign_id = self.create_campaign_from_icp(icp_template, custom_context)
        
        # Step 2: Fetch leads (using ICP-optimized search criteria)
        leads = self.fetch_leads_for_campaign(campaign_id, max_leads)
        
        if not leads:
            return {
                "campaign_id": campaign_id,
                "icp_template": icp_template,
                "leads_fetched": 0,
                "message": "No leads found matching ICP criteria"
            }
        
        # Step 3: Send emails (with ICP tracking)
        results = self.send_initial_emails(campaign_id, leads, dry_run=dry_run)
        
        # Add ICP context to results
        results["campaign_id"] = campaign_id
        results["icp_template"] = icp_template
        results["leads_fetched"] = len(leads)
        
        print(f"\n{'='*60}")
        print(f"✅ ICP CAMPAIGN COMPLETE: {results.get('sent', 0)} emails sent")
        print(f"{'='*60}\n")
        
        return results
    
    def run_autonomous_campaign(self,
                                 max_leads: int = 15,
                                 dry_run: bool = False,
                                 resume_pending_first: bool = True) -> Dict[str, Any]:
        """
        FULLY AUTONOMOUS CAMPAIGN EXECUTION
        
        This method requires ZERO human input. It:
        1. FIRST: Checks for pending leads that need to be contacted
        2. Analyzes historical ICP performance
        3. Selects the best ICP template automatically
        4. Fetches leads matching that ICP
        5. Generates and sends personalized emails
        6. Tracks everything for future optimization
        
        The system learns over time:
        - High-performing ICPs get more usage
        - Underperforming ICPs get less
        - Untested ICPs get explored
        
        Args:
            max_leads: Maximum leads to fetch
            dry_run: If True, generate but don't send
            resume_pending_first: If True, resume pending leads before new campaigns
        
        Returns:
            Results summary including which ICP was selected and why
        """
        from database import SchedulerConfig
        
        print(f"\n{'='*60}")
        print(f"🤖 AUTONOMOUS CAMPAIGN - NO HUMAN INPUT REQUIRED")
        print(f"{'='*60}")
        
        # STEP 0: Check for pending leads first (leads fetched but never contacted)
        if resume_pending_first:
            pending_leads = self.get_pending_leads(max_leads)
            if pending_leads:
                print(f"\n⚠️ Found {len(pending_leads)} PENDING LEADS waiting to be contacted!")
                print(f"   Resuming pending leads before starting new campaign...")
                
                resume_results = self.resume_pending_leads(max_leads=max_leads, dry_run=dry_run)
                
                # If we sent any emails or hit time limit, return early
                if resume_results.get("sent", 0) > 0 or resume_results.get("skipped_time", 0) > 0:
                    resume_results["autonomous"] = True
                    resume_results["action"] = "resumed_pending_leads"
                    return resume_results
        
        # Step 1: AI selects the best ICP based on performance data (MongoDB)
        selection = SchedulerConfig.select_icp_for_autonomous_run()
        selected_icp = selection["selected_icp"]
        selection_reason = selection["selection_reason"]
        selection_mode = selection["selection_mode"]
        
        print(f"\n🎯 AI Selected ICP: {selected_icp}")
        print(f"   Reason: {selection_reason}")
        print(f"   Mode: {selection_mode} (exploration vs exploitation)")
        print(f"   Today's runs: {selection.get('icps_excluded_today', [])}\n")
        
        # Step 2: Run the campaign with selected ICP
        results = self.run_icp_campaign(
            icp_template=selected_icp,
            max_leads=max_leads,
            dry_run=dry_run
        )
        
        # Step 3: Record the run in MongoDB (for future autonomous decisions)
        if not dry_run:
            SchedulerConfig.record_icp_run(
                icp_template=selected_icp,
                campaign_id=results.get("campaign_id"),
                leads_sent=results.get("sent", 0),
                results={
                    "leads_fetched": results.get("leads_fetched", 0),
                    "sent": results.get("sent", 0),
                    "errors": results.get("send_errors", 0),
                    "selection_mode": selection_mode
                }
            )
        
        # Add autonomous selection metadata
        results["autonomous"] = True
        results["icp_template"] = selected_icp
        results["selection_reason"] = selection_reason
        results["selection_mode"] = selection_mode
        
        return results
    
    def run_autonomous_daily_plan(self,
                                   num_campaigns: int = 3,
                                   leads_per_campaign: int = 15,
                                   dry_run: bool = False) -> Dict[str, Any]:
        """
        FULLY AUTONOMOUS DAILY CAMPAIGN PLAN
        
        Executes multiple campaigns in one day with intelligent ICP rotation:
        1. Analyzes all ICP performance
        2. Creates a balanced plan (exploit winners + explore new)
        3. Executes campaigns with delays between them
        4. Reports aggregate results
        
        This is the main entry point for fully automated daily operations.
        
        Args:
            num_campaigns: How many campaigns to run today
            leads_per_campaign: Leads per campaign
            dry_run: If True, generate but don't send
        
        Returns:
            Aggregate results for all campaigns
        """
        from icp_manager import ICPManager
        import time
        
        print(f"\n{'='*60}")
        print(f"🤖 AUTONOMOUS DAILY PLAN - {num_campaigns} CAMPAIGNS")
        print(f"{'='*60}")
        
        icp_manager = ICPManager()
        plan = icp_manager.get_autonomous_campaign_plan(num_campaigns)
        
        print(f"\n📋 Today's Campaign Plan:")
        for i, campaign in enumerate(plan):
            print(f"   {i+1}. {campaign.get('campaign_context', {}).get('icp_template', 'unknown')}")
            print(f"      Reason: {campaign.get('selection_reason', 'N/A')}")
        print()
        
        # Execute each campaign
        all_results = {
            "total_campaigns": num_campaigns,
            "total_leads": 0,
            "total_sent": 0,
            "campaigns": []
        }
        
        for i, campaign_config in enumerate(plan):
            icp_template = campaign_config.get("campaign_context", {}).get("icp_template")
            
            print(f"\n--- Campaign {i+1}/{num_campaigns}: {icp_template} ---")
            
            results = self.run_icp_campaign(
                icp_template=icp_template,
                max_leads=leads_per_campaign,
                dry_run=dry_run
            )
            
            results["selection_reason"] = campaign_config.get("selection_reason")
            all_results["campaigns"].append(results)
            all_results["total_leads"] += results.get("leads_fetched", 0)
            all_results["total_sent"] += results.get("sent", 0)
            
            # Delay between campaigns (if not last and not dry run)
            if i < num_campaigns - 1 and not dry_run:
                delay_mins = 30  # 30 min between campaigns
                print(f"\n⏳ Waiting {delay_mins} minutes before next campaign...")
                time.sleep(delay_mins * 60)
        
        print(f"\n{'='*60}")
        print(f"✅ DAILY PLAN COMPLETE")
        print(f"   Campaigns: {num_campaigns}")
        print(f"   Total Leads: {all_results['total_leads']}")
        print(f"   Total Sent: {all_results['total_sent']}")
        print(f"{'='*60}\n")
        
        return all_results
    
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
        
        # Save to database with campaign association
        saved_leads = []
        for lead_data in raw_leads:
            email = lead_data.get("email")
            if email:
                lead_id = Lead.create(lead_data, campaign_id=campaign_id)
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
        # Safety check: ensure we have valid input
        if not email_content or not isinstance(email_content, dict):
            print(f"   ⚠️ Invalid email_content input - skipping review")
            return email_content or {"subject": "Error", "body": "Error generating email"}, False
        
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
            rewritten = self.email_reviewer._rewrite_email(
                email=current_email,
                lead=lead,
                review=review,
                campaign_context=campaign_context
            )
            
            # Defensive check: ensure rewrite returned valid email dict
            if rewritten and isinstance(rewritten, dict) and rewritten.get("subject") and rewritten.get("body"):
                current_email = rewritten
            else:
                print(f"   ⚠️ Rewrite returned invalid result, keeping previous version")
                # Keep current_email as-is
        
        return current_email, False
    
    def send_initial_emails(self,
                            campaign_id: str,
                            leads: List[Dict] = None,
                            dry_run: bool = False) -> Dict[str, Any]:
        """
        Send initial emails to leads in a campaign
        
        Args:
            campaign_id: Campaign ID (can be "unknown" for orphan leads)
            leads: List of leads (if None, fetches all leads for campaign)
            dry_run: If True, generate emails but don't send
        
        Returns:
            Results summary
        """
        # Handle orphan leads (no campaign association)
        if campaign_id == "unknown" or campaign_id is None:
            campaign = None
            campaign_context = {}
            # Create a temporary campaign for tracking purposes
            temp_campaign_id = str(ObjectId())
            campaign_id = temp_campaign_id
            print(f"   📝 Created temporary campaign ID for orphan leads: {campaign_id[:8]}...")
        else:
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
        
        # Note: No upfront connect() check needed - send_email() handles connections
        # per-email with automatic rotation. This prevents false failures when one
        # account temporarily fails but others are available.
        
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
                
                # DO-NOT-CONTACT CHECK: Skip emails on the blocklist (unsubscribes, complaints, hard bounces)
                if DoNotContact.is_blocked(lead_email):
                    reason = DoNotContact.get_reason(lead_email)
                    print(f"🚫 Skipping {lead_email} - on do-not-contact list (reason: {reason})")
                    results["skipped"] += 1
                    results["skipped_do_not_contact"] = results.get("skipped_do_not_contact", 0) + 1
                    continue
                
                # INVALID EMAIL CHECK: Skip emails previously marked as invalid
                if lead.get("email_invalid"):
                    reason = lead.get("email_invalid_reason", "unknown")
                    print(f"⛔ Skipping {lead_email} - marked invalid ({reason})")
                    results["skipped"] += 1
                    results["skipped_invalid"] = results.get("skipped_invalid", 0) + 1
                    continue
                
                # EMAIL VERIFICATION CHECK: Skip leads with known-invalid emails from RocketReach
                raw_data = lead.get("raw_data", {})
                rr_emails = raw_data.get("emails", [])
                email_is_invalid = False
                for e in rr_emails:
                    if isinstance(e, dict) and e.get("email") == lead_email:
                        smtp_valid = (e.get("smtp_valid") or "").lower()
                        grade = e.get("grade", "")
                        if smtp_valid == "invalid" or grade == "F":
                            print(f"⛔ Skipping {lead_email} - RocketReach marked INVALID (smtp_valid={smtp_valid}, grade={grade})")
                            email_is_invalid = True
                            results["skipped"] += 1
                            results["skipped_invalid"] = results.get("skipped_invalid", 0) + 1
                            # Mark in DB so this lead is never re-checked
                            Lead.mark_invalid_email(lead_id, f"RocketReach INVALID (smtp_valid={smtp_valid}, grade={grade})")
                            break
                if email_is_invalid:
                    continue
                
                # BOUNCE CHECK: Skip leads that have bounced before (from any campaign)
                bounced_email = emails_collection.find_one({
                    'lead_id': ObjectId(lead_id),
                    'status': 'bounced'
                })
                if bounced_email:
                    print(f"⛔ Skipping {lead_email} - previously bounced")
                    results["skipped"] += 1
                    results["skipped_bounced"] = results.get("skipped_bounced", 0) + 1
                    # Also mark lead as invalid so future lookups are faster
                    Lead.mark_invalid_email(lead_id, "Email bounced")
                    continue
                
                # MX/SMTP VERIFICATION: Verify email is deliverable before sending
                verifier = get_email_verifier()
                verification = verifier.verify(lead_email)
                
                # Store verification results for tracking
                Lead.update_verification_status(
                    lead_id=lead_id,
                    verification_status=verification.status.value,
                    verification_score=verification.score,
                    verification_reason=verification.reason,
                    verification_checks=verification.checks
                )
                
                if verification.status == VerificationStatus.INVALID:
                    print(f"⛔ Skipping {lead_email} - failed MX/SMTP verification: {verification.reason}")
                    results["skipped"] += 1
                    results["skipped_invalid_mx_smtp"] = results.get("skipped_invalid_mx_smtp", 0) + 1
                    # Mark as invalid so we don't retry
                    Lead.mark_invalid_email(lead_id, f"Verification failed: {verification.reason}")
                    continue
                elif verification.status == VerificationStatus.RISKY:
                    print(f"⚠️  Warning: {lead_email} is risky (score: {verification.score}) - {verification.reason}")
                    # Continue but log the warning
                
                # SPAM PREVENTION: Check weekly limit
                if not Email.can_email_lead(lead_id, max_emails_per_week=3):
                    print(f"⏭️  Skipping {lead_email} - hit weekly email limit")
                    results["skipped"] += 1
                    continue
                
                # LEAD ENRICHMENT: Crawl company website for REAL personalization data
                # This replaces fake "I saw you're doing X" with actual observations
                enrichment = get_enrichment_for_email(lead)
                if not enrichment.get('has_enrichment'):
                    print(f"   🔍 Enriching lead data from company website...")
                    try:
                        enrich_result = enrich_lead_sync(lead)
                        if not enrich_result.get('error'):
                            # Reload lead to get enrichment data
                            lead = Lead.get_by_id(lead_id)
                            print(f"   ✅ Enriched: {len(enrich_result.get('personalization_hooks', []))} personalization hooks found")
                        else:
                            print(f"   ⚠️ Enrichment failed: {enrich_result.get('error')} - will use fallback")
                    except Exception as e:
                        print(f"   ⚠️ Enrichment error: {e} - will use fallback")
                else:
                    print(f"   ✅ Using cached enrichment data")
                
                # ICP CLASSIFICATION: Classify lead before generating email (TK Kader Framework)
                icp_classification = self.email_generator.classify_lead_icp(lead)
                is_icp = icp_classification.get("is_icp", False)
                icp_template = icp_classification.get("icp_template")
                icp_score = icp_classification.get("icp_score", 0)
                
                if is_icp:
                    print(f"   ✅ ICP Match (score: {icp_score}): {', '.join(icp_classification.get('icp_reasons', [])[:2])}")
                else:
                    print(f"   ⚠️ Non-ICP Lead (score: {icp_score}): {', '.join(icp_classification.get('non_icp_reasons', [])[:1])}")
                
                # Update lead with ICP classification
                Lead.update_icp_classification(
                    lead_id=lead_id,
                    is_icp=is_icp,
                    icp_template=icp_template,
                    icp_score=icp_score,
                    icp_reasons=icp_classification.get("icp_reasons", [])
                )
                
                # GATE: Skip non-ICP leads to save API quota and protect sender reputation
                if not is_icp:
                    print(f"   ⏭️ Skipping non-ICP lead (score {icp_score} < 0.5 threshold)")
                    results["skipped"] += 1
                    results["skipped_non_icp"] = results.get("skipped_non_icp", 0) + 1
                    continue
                
                # Generate personalized email
                print(f"📧 Generating email for {lead['full_name']} ({lead['email']})...")
                email_content = self.email_generator.generate_initial_email(
                    lead=lead,
                    campaign_context=campaign_context
                )
                
                # Safety check: ensure we have valid email content
                if not email_content or not isinstance(email_content, dict):
                    print(f"   ⚠️ Email generation returned None/invalid - skipping lead")
                    results["failed"] += 1
                    continue
                
                # QUALITY GATE: Review email before sending
                if self.enable_review:
                    email_content, review_passed = self._review_and_rewrite_if_needed(
                        email_content=email_content,
                        lead=lead,
                        campaign_context=campaign_context
                    )
                    
                    # Safety check: _review_and_rewrite_if_needed should never return None, but handle it
                    if email_content is None:
                        print(f"   ⚠️ Review returned None - skipping lead")
                        results["failed"] += 1
                        continue
                    
                    if not review_passed:
                        print(f"   🚫 Email failed review after {self.max_rewrites} rewrites - marking for manual review")
                        results["manual_review"] = results.get("manual_review", 0) + 1
                        subject = email_content.get("subject", "N/A") if isinstance(email_content, dict) else "N/A"
                        results["details"].append({
                            "lead_email": lead["email"],
                            "subject": subject,
                            "status": "manual_review_required",
                            "reason": "Failed quality review"
                        })
                        continue  # Skip to next lead
                
                # Final safety check before creating email record
                if not email_content or not isinstance(email_content, dict) or not email_content.get("subject") or not email_content.get("body"):
                    print(f"   ⚠️ Invalid email content (missing subject/body) - skipping lead")
                    results["failed"] += 1
                    continue
                
                # Create email record with ICP tracking
                email_id = Email.create(
                    lead_id=lead_id,
                    campaign_id=campaign_id,
                    subject=email_content["subject"],
                    body=email_content["body"],
                    email_type="initial",
                    followup_number=0,
                    to_email=lead["email"],
                    is_icp=is_icp,
                    icp_template=icp_template
                )
                
                if dry_run:
                    print(f"[DRY RUN] Would send to {lead['email']}:")
                    print(f"  Subject: {email_content['subject']}")
                    results["sent"] += 1
                    results["details"].append({
                        "lead_email": lead["email"],
                        "subject": email_content["subject"],
                        "status": "dry_run",
                        "is_icp": is_icp,
                        "icp_score": icp_score
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
                            emails_collection.delete_one({"_id": ObjectId(email_id)})
                            break  # Stop the campaign for today
                        
                        elif skip_reason == "time":
                            print(f"   ⏸️ Outside sending hours - stopping campaign")
                            results["skipped_time"] += 1
                            # Delete the pending email record
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
                            
                            # If Zoho flagged recipient as invalid (554 error), mark lead
                            if result.get("recipient_invalid"):
                                Lead.mark_invalid_email(lead_id, f"Zoho blocked: {result.get('error', 'Invalid recipient')}")
                                print(f"   ⚠️ Marked {lead_email} as invalid - Zoho blocked send")
                            
                            results["details"].append({
                                "lead_email": lead["email"],
                                "subject": email_content["subject"],
                                "status": "failed",
                                "error": result.get("error")
                            })
                    else:
                        # Store which account sent this email + Message-ID for follow-up threading
                        Email.mark_sent(
                            email_id, 
                            from_email=result.get("from_email"),
                            message_id=result.get("message_id")
                        )
                        Campaign.increment_stat(campaign_id, "emails_sent")
                        results["sent"] += 1
                        results["details"].append({
                            "lead_email": lead["email"],
                            "subject": email_content["subject"],
                            "status": "sent",
                            "from_email": result.get("from_email")
                        })
                        # No delay needed here - the per-account cooldown handles rate limiting
                        # Next email will use a different account (rotation)
        
        finally:
            if not dry_run:
                self.email_sender.disconnect()
        
        # Activate campaign if not already active (skip for orphan leads with no campaign)
        if campaign and campaign.get("status") == Campaign.STATUS_DRAFT:
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
            # Don't print anything - caller will handle summary
            return results
        
        print(f"Found {len(pending_followups)} leads needing follow-up")
        
        # CLEANUP: Delete orphaned pending follow-up records (created but never sent)
        # These accumulate when send_email fails without proper cleanup
        orphaned = emails_collection.delete_many({
            "status": Email.STATUS_PENDING,
            "email_type": {"$regex": "followup"},
            "created_at": {"$lt": datetime.utcnow() - timedelta(hours=1)}
        })
        if orphaned.deleted_count > 0:
            print(f"   🧹 Cleaned {orphaned.deleted_count} orphaned follow-up records")
        
        try:
            for followup_data in pending_followups:
                lead_id = str(followup_data["_id"])
                lead = Lead.get_by_id(lead_id)
                
                if not lead:
                    continue
                
                lead_email = lead.get("email", "")
                
                # DO-NOT-CONTACT CHECK: Skip emails on the blocklist
                if DoNotContact.is_blocked(lead_email):
                    reason = DoNotContact.get_reason(lead_email)
                    print(f"🚫 Skipping followup for {lead_email} - on do-not-contact list (reason: {reason})")
                    results["skipped_do_not_contact"] = results.get("skipped_do_not_contact", 0) + 1
                    continue
                
                # BOUNCE CHECK: Skip leads that have bounced before (even if inconclusive in RR)
                bounced_email = emails_collection.find_one({
                    'lead_id': ObjectId(lead_id),
                    'status': 'bounced'
                })
                if bounced_email:
                    print(f"⛔ Skipping followup for {lead_email} - previously bounced")
                    results["skipped_bounced"] = results.get("skipped_bounced", 0) + 1
                    continue
                
                # EMAIL VERIFICATION CHECK: Skip leads with known-invalid emails from RocketReach
                raw_data = lead.get("raw_data", {})
                rr_emails = raw_data.get("emails", [])
                email_is_invalid = False
                for e in rr_emails:
                    if isinstance(e, dict) and e.get("email") == lead_email:
                        smtp_valid = (e.get("smtp_valid") or "").lower()
                        grade = e.get("grade", "")
                        if smtp_valid == "invalid" or grade == "F":
                            print(f"⛔ Skipping followup for {lead_email} - RocketReach marked INVALID")
                            email_is_invalid = True
                            results["skipped_invalid"] = results.get("skipped_invalid", 0) + 1
                            break
                if email_is_invalid:
                    continue
                
                # MX/SMTP VERIFICATION: Verify email is deliverable before sending followup
                verifier = get_email_verifier()
                verification = verifier.verify(lead_email)
                if verification.status == VerificationStatus.INVALID:
                    print(f"⛔ Skipping followup for {lead_email} - failed MX/SMTP verification: {verification.reason}")
                    results["skipped_invalid_mx_smtp"] = results.get("skipped_invalid_mx_smtp", 0) + 1
                    continue
                elif verification.status == VerificationStatus.RISKY:
                    print(f"⚠️  Warning: {lead_email} is risky (score: {verification.score}) - {verification.reason}")
                
                # LEAD ENRICHMENT: Ensure we have enrichment data for follow-up personalization
                enrichment = get_enrichment_for_email(lead)
                if not enrichment.get('has_enrichment'):
                    try:
                        enrich_result = enrich_lead_sync(lead)
                        if not enrich_result.get('error'):
                            lead = Lead.get_by_id(lead_id)  # Reload with enrichment
                    except Exception:
                        pass  # Continue without enrichment
                
                # Get previous emails for context - ONLY count SENT emails for follow-up number
                # (pending/failed records should NOT inflate the count)
                all_emails = Email.get_by_lead_and_campaign(lead_id, campaign_id)
                previous_emails = [e for e in all_emails if e.get('status') == Email.STATUS_SENT]
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
                
                # Get ICP status from lead (already classified during initial email)
                is_icp = lead.get("is_icp")
                icp_template = lead.get("icp_template")
                
                # Create email record with ICP tracking
                email_id = Email.create(
                    lead_id=lead_id,
                    campaign_id=campaign_id,
                    subject=email_content["subject"],
                    body=email_content["body"],
                    email_type="followup" if not is_new_thread else "followup_new_thread",
                    followup_number=followup_number,
                    to_email=lead["email"],
                    is_icp=is_icp,
                    icp_template=icp_template
                )
                
                if dry_run:
                    print(f"[DRY RUN] Would send follow-up to {lead['email']}:")
                    print(f"  Subject: {email_content['subject']}")
                    results["sent"] += 1
                else:
                    # Get the original sender account for this lead (thread consistency)
                    original_sender = Email.get_sender_for_lead(lead_id, campaign_id)
                    from_account = None
                    if original_sender:
                        # Find the account dict for this email
                        for acc in self.email_sender.accounts:
                            if acc["email"] == original_sender:
                                from_account = acc
                                print(f"  → Using original sender: {original_sender}")
                                break
                    
                    # Get threading info for same-thread follow-ups
                    # For new threads, we don't use In-Reply-To/References
                    in_reply_to = None
                    references = None
                    if not is_new_thread:
                        thread_info = Email.get_thread_info(lead_id, campaign_id)
                        in_reply_to = thread_info.get("in_reply_to")
                        references = thread_info.get("references")
                        if in_reply_to:
                            print(f"  → Threading: replying to {in_reply_to[:30]}...")
                    
                    # Send the email (uses original sender if found, otherwise rotates)
                    print(f"  → Sending follow-up to {lead['email']}...")
                    result = self.email_sender.send_email(
                        to_email=lead["email"],
                        subject=email_content["subject"],
                        body=email_content["body"],
                        to_name=lead.get("full_name"),
                        html_body=text_to_html(email_content["body"]),
                        from_account=from_account,
                        in_reply_to=in_reply_to,
                        references=references
                    )
                    
                    if result["success"]:
                        Email.mark_sent(
                            email_id, 
                            from_email=result.get("from_email"),
                            message_id=result.get("message_id")
                        )
                        Campaign.increment_stat(campaign_id, "emails_sent")
                        results["sent"] += 1
                        results["details"].append({
                            "lead_email": lead["email"],
                            "followup_number": followup_number,
                            "status": "sent",
                            "from_email": result.get("from_email")
                        })
                        print(f"  ✅ Follow-up #{followup_number} sent to {lead['email']}")
                    else:
                        # Check if we hit limits or time restrictions
                        skip_reason = result.get("skip_reason")
                        error_msg = result.get("error", "Unknown error")
                        print(f"  ⚠️ Follow-up send failed: {error_msg} (skip_reason={skip_reason})")
                        
                        if skip_reason == "limit":
                            print(f"   🛑 Daily limit reached - stopping follow-ups for today")
                            results["skipped_limit"] = results.get("skipped_limit", 0) + 1
                            emails_collection.delete_one({"_id": ObjectId(email_id)})
                            break
                        
                        elif skip_reason == "time":
                            print(f"   ⏸️ Outside sending hours - stopping follow-ups")
                            results["skipped_time"] = results.get("skipped_time", 0) + 1
                            emails_collection.delete_one({"_id": ObjectId(email_id)})
                            break
                        
                        elif skip_reason == "cooldown":
                            # All accounts in cooldown - wait and retry
                            wait_seconds = result.get("wait_seconds", 60)
                            print(f"   ⏳ All accounts in cooldown, waiting {wait_seconds // 60}m {wait_seconds % 60}s...")
                            # Delete the pending record - will be recreated on retry
                            emails_collection.delete_one({"_id": ObjectId(email_id)})
                            time.sleep(wait_seconds + 5)
                            continue  # Retry this lead
                        
                        else:
                            # Non-recoverable failure - delete the pending record to prevent orphans
                            print(f"   ❌ Non-recoverable: {error_msg}")
                            emails_collection.delete_one({"_id": ObjectId(email_id)})
                            results["failed"] += 1
                            results["details"].append({
                                "lead_email": lead["email"],
                                "followup_number": followup_number,
                                "status": "failed",
                                "error": error_msg
                            })
        
        except Exception as e:
            print(f"   ❌ Exception in follow-up processing: {e}")
            import traceback
            traceback.print_exc()
        
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
