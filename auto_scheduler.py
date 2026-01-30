"""
Automated Scheduler System
Handles auto campaign creation, email sending, and follow-ups
"""

import schedule
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
import threading
import pytz

from campaign_manager import CampaignManager
from email_generator import EmailGenerator
from reply_detector import ReplyDetector
from database import Campaign, Email, campaigns_collection
import config


def get_target_time() -> datetime:
    """Get current time in target timezone (US Eastern)"""
    tz = pytz.timezone(config.TARGET_TIMEZONE)
    return datetime.now(tz)


def get_target_time_str(fmt: str = "%Y-%m-%d %H:%M %Z") -> str:
    """Get formatted current time in target timezone"""
    return get_target_time().strftime(fmt)


class AutoScheduler:
    """
    Automated scheduler for:
    - Creating campaigns on a schedule
    - Sending initial emails
    - Sending follow-up emails
    - Checking for replies
    """
    
    def __init__(self):
        self.manager = CampaignManager()
        self.generator = EmailGenerator()
        self.reply_detector = ReplyDetector()
        self._running = False
        self._scheduled_campaigns: List[Dict] = []
    
    def add_scheduled_campaign(self,
                               description: str = None,
                               icp_template: str = None,
                               autonomous: bool = False,
                               schedule_time: str = "09:00",
                               days: List[str] = None,
                               max_leads: int = 20,
                               enabled: bool = True) -> Dict:
        """
        Add a campaign to be created automatically on schedule.
        
        THREE MODES (in order of recommendation):
        
        1. autonomous=True (RECOMMENDED)
           AI analyzes performance data and picks the best ICP automatically.
           No human input needed. System learns and improves over time.
        
        2. icp_template="template_name"
           Use a specific pre-defined ICP template.
           Good when you want to target a specific audience.
        
        3. description="plain text"
           Legacy mode. AI guesses targeting from description.
           Less reliable than ICP templates.
        
        Args:
            description: Campaign description (legacy mode)
            icp_template: Specific ICP template name
            autonomous: If True, AI selects best ICP automatically (RECOMMENDED)
            schedule_time: Time to run (HH:MM format)
            days: Days to run on
            max_leads: Max leads per run
            enabled: Whether active
        
        Returns:
            Scheduled campaign config
        """
        if not description and not icp_template and not autonomous:
            raise ValueError("Must provide 'description', 'icp_template', or set 'autonomous=True'")
        
        campaign_config = {
            "id": len(self._scheduled_campaigns) + 1,
            "description": description,
            "icp_template": icp_template,
            "autonomous": autonomous,  # NEW: Fully autonomous mode
            "schedule_time": schedule_time,
            "days": days or ["monday", "tuesday", "wednesday", "thursday", "friday"],
            "max_leads": max_leads,
            "enabled": enabled,
            "created_at": datetime.utcnow().isoformat(),
            "last_run": None,
            "campaign_ids": []
        }
        
        self._scheduled_campaigns.append(campaign_config)
        return campaign_config
    
    def _run_scheduled_campaign(self, config: Dict):
        """Run a scheduled campaign creation"""
        if not config.get("enabled"):
            return
        
        # Use target timezone for day check
        now = get_target_time()
        today = now.strftime("%A").lower()
        if today not in [d.lower() for d in config.get("days", [])]:
            return
        
        icp_template = config.get("icp_template")
        description = config.get("description")
        
        print(f"\n{'='*50}")
        print(f"[{get_target_time_str()}] Running scheduled campaign")
        if icp_template:
            print(f"   🎯 ICP Template: {icp_template}")
        else:
            print(f"   Description: {description}")
        print(f"{'='*50}\n")
        
        try:
            # Check for autonomous mode
            autonomous = config.get("autonomous", False)
            
            if autonomous:
                # FULLY AUTONOMOUS: AI selects the best ICP
                print("🤖 Running in AUTONOMOUS mode - AI will select ICP")
                results = self.manager.run_autonomous_campaign(
                    max_leads=config['max_leads'],
                    dry_run=False
                )
                campaign_id = results.get("campaign_id")
                icp_template = results.get("icp_template")
                
            elif icp_template:
                # Specific ICP template requested
                results = self.manager.run_icp_campaign(
                    icp_template=icp_template,
                    max_leads=config['max_leads'],
                    dry_run=False
                )
                
                if "error" in results:
                    print(f"❌ ICP campaign failed: {results['error']}")
                    return
                
                campaign_id = results.get("campaign_id")
                
            else:
                # Legacy: Use AI to create campaign config from description
                campaign_config = self.generator.determine_icp_and_criteria(description)
                
                # Create campaign with date suffix
                date_suffix = datetime.now().strftime("%Y-%m-%d")
                campaign_name = f"{campaign_config['campaign_name']} - {date_suffix}"
                
                campaign_id = self.manager.create_campaign(
                    name=campaign_name,
                    description=campaign_config['target_description'],
                    target_criteria=campaign_config['search_criteria'],
                    campaign_context=campaign_config['campaign_context']
                )
                
                # Run the campaign
                results = self.manager.run_campaign(
                    campaign_id=campaign_id,
                    fetch_new_leads=True,
                    max_leads=config['max_leads'],
                    send_initial=True,
                    send_followups=False,
                    dry_run=False
                )
            
            # Update config
            config['last_run'] = datetime.utcnow().isoformat()
            if campaign_id:
                config['campaign_ids'].append(campaign_id)
            
            print(f"\n✅ Scheduled campaign completed")
            print(f"   Campaign ID: {campaign_id}")
            print(f"   Leads: {results.get('leads_fetched', 0)}")
            sent = results.get('sent', results.get('initial_emails', {}).get('sent', 0))
            print(f"   Emails sent: {sent}")
            if icp_template:
                print(f"   ICP Template: {icp_template}")
            
        except Exception as e:
            print(f"❌ Scheduled campaign failed: {e}")
    
    def check_replies_task(self):
        """Task to check for replies across all accounts"""
        print(f"\n[{get_target_time_str()}] 📬 Checking for replies...")
        
        try:
            results = self.reply_detector.check_replies(since_days=1)
            
            if results['replies_found'] > 0:
                print(f"   Found {results['replies_found']} replies!")
                for detail in results['details']:
                    print(f"   - {detail['lead_name']}: {detail['subject']}")
            else:
                print(f"   No new replies")
            
            # Also check bounces
            bounces = self.reply_detector.check_bounces(since_days=1)
            if bounces['bounces_found'] > 0:
                print(f"   Found {bounces['bounces_found']} bounces")
                
        except Exception as e:
            print(f"   Error checking replies: {e}")
    
    def send_followups_task(self):
        """Task to send follow-up emails for all active campaigns"""
        print(f"\n[{get_target_time_str()}] 📧 Checking for follow-ups...")
        
        active_campaigns = Campaign.get_active_campaigns()
        
        if not active_campaigns:
            print("   No active campaigns")
            return
        
        total_sent = 0
        total_failed = 0
        
        for campaign in active_campaigns:
            campaign_id = str(campaign["_id"])
            
            try:
                results = self.manager.send_followup_emails(campaign_id)
                sent = results.get('sent', 0)
                failed = results.get('failed', 0)
                
                if sent > 0 or failed > 0:
                    print(f"   {campaign['name']}: Sent {sent}, Failed {failed}")
                
                total_sent += sent
                total_failed += failed
                
            except Exception as e:
                print(f"   Error in {campaign['name']}: {e}")
        
        if total_sent > 0:
            print(f"\n   ✅ Total follow-ups sent: {total_sent}")
    
    def send_initial_emails_task(self):
        """Task to send initial emails for draft campaigns"""
        print(f"\n[{get_target_time_str()}] 📧 Sending initial emails for pending campaigns...")
        
        # Find campaigns in draft status with leads but no emails sent
        draft_campaigns = list(campaigns_collection.find({
            "status": Campaign.STATUS_DRAFT,
            "stats.total_leads": {"$gt": 0},
            "stats.emails_sent": 0
        }))
        
        if not draft_campaigns:
            print("   No pending campaigns to send")
            return
        
        for campaign in draft_campaigns:
            campaign_id = str(campaign["_id"])
            
            try:
                print(f"   Sending for: {campaign['name']}")
                results = self.manager.send_initial_emails(campaign_id)
                print(f"   → Sent: {results.get('sent', 0)}, Failed: {results.get('failed', 0)}")
                
            except Exception as e:
                print(f"   Error: {e}")
    
    def _run_missed_campaigns(self):
        """Run any campaigns that were scheduled earlier today but missed"""
        now = get_target_time()
        today = now.strftime("%A").lower()
        current_time = now.strftime("%H:%M")
        
        missed = []
        for sc in self._scheduled_campaigns:
            if not sc.get("enabled"):
                continue
            
            # Check if today is a scheduled day
            if today not in [d.lower() for d in sc.get("days", [])]:
                continue
            
            # Check if scheduled time has passed
            scheduled_time = sc.get("schedule_time", "09:00")
            if scheduled_time <= current_time:
                # Check if already run today
                last_run = sc.get("last_run")
                if last_run:
                    last_run_date = datetime.fromisoformat(last_run).date()
                    if last_run_date == now.date():
                        continue  # Already ran today
                
                missed.append(sc)
        
        if missed:
            print(f"\n🔄 Found {len(missed)} missed campaign(s) for today - running now...")
            for sc in missed:
                print(f"   • {sc['description']} (was scheduled for {sc['schedule_time']})")
                self._run_scheduled_campaign(sc)
        else:
            print(f"\n✅ No missed campaigns to catch up on")
    
    def start(self,
              check_replies_interval_hours: int = 2,
              followup_check_interval_hours: int = 6,
              initial_emails_interval_hours: int = 1):
        """
        Start the automated scheduler
        
        Args:
            check_replies_interval_hours: How often to check for replies
            followup_check_interval_hours: How often to check for follow-ups
            initial_emails_interval_hours: How often to send pending initial emails
        """
        target_tz = pytz.timezone(config.TARGET_TIMEZONE)
        local_tz = datetime.now().astimezone().tzinfo or pytz.UTC
        
        print("\n" + "="*60)
        print("🚀 AUTOMATED SCHEDULER STARTED")
        print("="*60)
        print(f"\n🌍 Timezone: {config.TARGET_TIMEZONE}")
        print(f"   Current time in target TZ: {get_target_time_str()}")
        print(f"\n📋 Schedule:")
        print(f"   • Check replies: Every {check_replies_interval_hours} hours")
        print(f"   • Send follow-ups: Every {followup_check_interval_hours} hours")
        print(f"   • Send initial emails: Every {initial_emails_interval_hours} hours")
        
        if self._scheduled_campaigns:
            print(f"\n📅 Scheduled Campaigns ({len(self._scheduled_campaigns)}):")
            for sc in self._scheduled_campaigns:
                if sc['enabled']:
                    print(f"   • {sc['description']}")
                    print(f"     → {sc['schedule_time']} {config.TARGET_TIMEZONE} on {', '.join(sc['days'])}")
                    print(f"     → Max {sc['max_leads']} leads per run")
        
        print(f"\n⏰ Press Ctrl+C to stop")
        print("="*60 + "\n")
        
        # Schedule regular tasks
        schedule.every(check_replies_interval_hours).hours.do(self.check_replies_task)
        schedule.every(followup_check_interval_hours).hours.do(self.send_followups_task)
        schedule.every(initial_emails_interval_hours).hours.do(self.send_initial_emails_task)
        
        # Schedule campaign creation tasks
        # Note: schedule library uses server local time, so we convert from target TZ
        for sc in self._scheduled_campaigns:
            if sc['enabled']:
                # Convert schedule time from target timezone to local server time
                schedule_time_str = sc['schedule_time']  # e.g., "09:00"
                hour, minute = map(int, schedule_time_str.split(':'))
                
                # Create a datetime in target timezone
                today = datetime.now(target_tz).date()
                target_dt = target_tz.localize(
                    datetime(today.year, today.month, today.day, hour, minute)
                )
                
                # Convert to local server time
                local_dt = target_dt.astimezone(local_tz)
                local_time_str = local_dt.strftime("%H:%M")
                
                print(f"📌 Scheduling '{sc['description'][:30]}...' at {schedule_time_str} EST (= {local_time_str} server time)")
                
                schedule.every().day.at(local_time_str).do(
                    self._run_scheduled_campaign, sc
                )
        
        # Run initial checks
        self.check_replies_task()
        self.send_followups_task()
        
        # Run any missed campaigns from earlier today
        self._run_missed_campaigns()
        
        self._running = True
        
        while self._running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except KeyboardInterrupt:
                print("\n\n⏹️  Scheduler stopped")
                self._running = False
                break
    
    def stop(self):
        """Stop the scheduler"""
        self._running = False


def create_scheduler_from_mongodb() -> AutoScheduler:
    """
    Create scheduler from MongoDB configuration.
    
    This is the RECOMMENDED way to run the scheduler - fully autonomous
    with configuration stored in MongoDB so it can be updated dynamically.
    """
    from database import SchedulerConfig as DBSchedulerConfig
    
    scheduler = AutoScheduler()
    
    # Initialize/get config from MongoDB
    db_config = DBSchedulerConfig.get_config()
    settings = DBSchedulerConfig.get_settings()
    
    scheduled_campaigns = db_config.get("scheduled_campaigns", [])
    
    print(f"\n📦 Loading scheduler config from MongoDB...")
    print(f"   Mode: {db_config.get('mode', 'autonomous')}")
    print(f"   Timezone: {settings.get('timezone', 'UTC')}")
    print(f"   Campaigns: {len(scheduled_campaigns)}")
    
    # Load all enabled campaigns from config
    for i, campaign in enumerate(scheduled_campaigns):
        if campaign.get("enabled", True):
            scheduler._scheduled_campaigns.append({
                "id": i + 1,
                "name": campaign.get("name", f"campaign_{i+1}"),
                "description": campaign.get("description"),
                "icp_template": campaign.get("icp_template"),
                "autonomous": campaign.get("autonomous", True),  # Default to autonomous
                "schedule_time": campaign.get("schedule_time", "09:00"),
                "days": campaign.get("days", ["monday", "tuesday", "wednesday", "thursday", "friday"]),
                "max_leads": campaign.get("max_leads", 15),
                "enabled": True,
                "created_at": datetime.utcnow().isoformat(),
                "last_run": None,
                "campaign_ids": []
            })
            
            # Log which mode this campaign uses
            if campaign.get("autonomous", True):
                print(f"   🤖 Campaign #{i+1}: AUTONOMOUS (AI selects ICP)")
            elif campaign.get("icp_template"):
                print(f"   🎯 Campaign #{i+1}: ICP template '{campaign['icp_template']}'")
            else:
                print(f"   📝 Campaign #{i+1}: {campaign.get('description', '')[:50]}...")
    
    return scheduler


# LEGACY: JSON-based config (kept for backwards compatibility)
class SchedulerConfigJSON:
    """Load/save scheduler configuration from JSON file (LEGACY)"""
    
    CONFIG_FILE = "scheduler_config.json"
    
    @staticmethod
    def load() -> Dict:
        """Load full config from file"""
        try:
            with open(SchedulerConfigJSON.CONFIG_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"scheduled_campaigns": [], "settings": {}}


def create_scheduler_from_config() -> AutoScheduler:
    """
    LEGACY: Create scheduler from JSON config file.
    Use create_scheduler_from_mongodb() instead for full autonomous operation.
    """
    print("\n⚠️  Using LEGACY JSON config. Consider migrating to MongoDB.")
    
    scheduler = AutoScheduler()
    
    config_data = SchedulerConfigJSON.load()
    scheduled_campaigns = config_data.get("scheduled_campaigns", [])
    
    # Load all enabled campaigns from config
    for i, campaign in enumerate(scheduled_campaigns):
        if campaign.get("enabled", True):
            scheduler._scheduled_campaigns.append({
                "id": i + 1,
                "description": campaign.get("description"),
                "icp_template": campaign.get("icp_template"),
                "autonomous": campaign.get("autonomous", False),
                "schedule_time": campaign.get("schedule_time", "09:00"),
                "days": campaign.get("days", ["monday", "wednesday", "friday"]),
                "max_leads": campaign.get("max_leads", 15),
                "enabled": True,
                "created_at": datetime.utcnow().isoformat(),
                "last_run": None,
                "campaign_ids": []
            })
            
            if campaign.get("autonomous"):
                print(f"   🤖 Campaign #{i+1}: AUTONOMOUS (AI selects ICP)")
            elif campaign.get("icp_template"):
                print(f"   🎯 Campaign #{i+1}: ICP template '{campaign['icp_template']}'")
            else:
                print(f"   📝 Campaign #{i+1}: {campaign.get('description', '')[:50]}...")
    
    return scheduler


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Cold Email Autonomous Scheduler")
    parser.add_argument("--legacy", action="store_true", 
                       help="Use legacy JSON config instead of MongoDB")
    args = parser.parse_args()
    
    if args.legacy:
        # Legacy mode: load from JSON file
        scheduler = create_scheduler_from_config()
    else:
        # RECOMMENDED: Load from MongoDB (fully autonomous)
        scheduler = create_scheduler_from_mongodb()
    
    print(f"📧 Loaded {len(config.ZOHO_ACCOUNTS)} email account(s): {', '.join([a['email'] for a in config.ZOHO_ACCOUNTS])}")
    
    # Start fully automatic - no manual intervention needed
    scheduler.start(
        check_replies_interval_hours=2,
        followup_check_interval_hours=6,
        initial_emails_interval_hours=1
    )
