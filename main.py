#!/usr/bin/env python3
"""
Cold Email Automation System for PrimeStrides
==============================================

Simple commands - AI handles the rest.

Usage:
    python main.py create "target startup founders needing AI"
    python main.py run <campaign_id>
    python main.py run <campaign_id> --dry-run
    python main.py followups <campaign_id>
    python main.py list
    python main.py stats <campaign_id>
    python main.py test-email <email>
    python main.py scheduler
"""

import argparse
import json
import sys
import logging
from datetime import datetime

from campaign_manager import CampaignManager
from rocketreach_client import RocketReachClient
from zoho_sender import ZohoEmailSender
from email_generator import EmailGenerator
from database import Campaign, Lead, Email

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def create_campaign_smart(description: str):
    """Create a campaign using AI to determine everything"""
    print(f"\n🚀 Creating campaign: \"{description}\"\n")
    print("AI is analyzing target audience and crafting strategy...\n")
    
    # Use AI to determine ICP and criteria
    generator = EmailGenerator()
    config = generator.determine_icp_and_criteria(description)
    
    print(f"📊 Campaign Analysis:")
    print(f"   Name: {config['campaign_name']}")
    print(f"   Target: {config['target_description']}")
    print(f"\n🎯 Search Criteria:")
    print(f"   Titles: {', '.join(config['search_criteria'].get('current_title', []))}")
    print(f"   Industries: {', '.join(config['search_criteria'].get('industry', []))}")
    print(f"   Location: {', '.join(config['search_criteria'].get('location', ['United States']))}")
    print(f"\n💡 Campaign Strategy:")
    print(f"   Value Prop: {config['campaign_context'].get('value_proposition', '')}")
    print(f"   Angle: {config['campaign_context'].get('angle', '')}")
    print(f"   Proof Point: {config['campaign_context'].get('proof_point', '')}")
    
    # Create the campaign
    manager = CampaignManager()
    campaign_id = manager.create_campaign(
        name=config['campaign_name'],
        description=config['target_description'],
        target_criteria=config['search_criteria'],
        campaign_context=config['campaign_context']
    )
    
    print(f"\n✅ Campaign created!")
    print(f"   ID: {campaign_id}")
    print(f"\n📧 Next steps:")
    print(f"   1. Test run:  python main.py run {campaign_id} --dry-run --max-leads 3")
    print(f"   2. Real run:  python main.py run {campaign_id} --max-leads 10")


def run_campaign(campaign_id: str, dry_run: bool = False, max_leads: int = 50,
                 skip_fetch: bool = False, skip_initial: bool = False):
    """Run a campaign"""
    manager = CampaignManager()
    
    campaign = Campaign.get_by_id(campaign_id)
    if not campaign:
        print(f"❌ Campaign not found: {campaign_id}")
        return
    
    print(f"\n🚀 Running Campaign: {campaign['name']}")
    if dry_run:
        print("   (DRY RUN - no emails will be sent)\n")
    else:
        print()
    
    results = manager.run_campaign(
        campaign_id=campaign_id,
        fetch_new_leads=not skip_fetch,
        max_leads=max_leads,
        send_initial=not skip_initial,
        send_followups=not skip_initial,  # Only send followups if not skipping initial
        dry_run=dry_run
    )
    
    print(f"\n📊 Results:")
    print(f"   Leads fetched: {results.get('leads_fetched', 0)}")
    
    if results.get('initial_emails'):
        ie = results['initial_emails']
        print(f"   Initial emails - Sent: {ie.get('sent', 0)}, Failed: {ie.get('failed', 0)}, Skipped: {ie.get('skipped', 0)}")
    
    if results.get('followup_emails'):
        fe = results['followup_emails']
        print(f"   Follow-ups - Sent: {fe.get('sent', 0)}, Failed: {fe.get('failed', 0)}")


def send_followups(campaign_id: str, dry_run: bool = False):
    """Send follow-up emails only"""
    manager = CampaignManager()
    
    print(f"\n📧 Sending Follow-ups")
    if dry_run:
        print("   (DRY RUN - no emails will be sent)\n")
    
    results = manager.send_followup_emails(campaign_id, dry_run=dry_run)
    
    print(f"\n📊 Results: Sent {results.get('sent', 0)}, Failed {results.get('failed', 0)}")


def show_stats(campaign_id: str):
    """Show campaign statistics"""
    manager = CampaignManager()
    stats = manager.get_campaign_stats(campaign_id)
    
    if "error" in stats:
        print(f"❌ {stats['error']}")
        return
    
    print(f"\n📊 Campaign: {stats['name']}")
    print(f"   Status: {stats['status']}")
    print(f"   Created: {stats['created_at']}")
    print(f"\n   Stats:")
    for key, value in stats.get('stats', {}).items():
        print(f"   - {key.replace('_', ' ').title()}: {value}")


def list_campaigns():
    """List all campaigns"""
    from database import campaigns_collection
    
    campaigns = list(campaigns_collection.find().sort("created_at", -1))
    
    if not campaigns:
        print("\n📭 No campaigns yet. Create one with:")
        print('   python main.py create "target startup founders"')
        return
    
    print(f"\n📋 Campaigns ({len(campaigns)})\n")
    
    for c in campaigns:
        status_emoji = {"draft": "📝", "active": "🟢", "paused": "⏸️", "completed": "✅"}.get(c['status'], "❓")
        print(f"{status_emoji} {c['name']}")
        print(f"   ID: {c['_id']}")
        print(f"   Status: {c['status']} | Leads: {c.get('stats', {}).get('total_leads', 0)} | Sent: {c.get('stats', {}).get('emails_sent', 0)}")
        print()


def test_email(to_email: str):
    """Send test emails from all configured accounts"""
    sender = ZohoEmailSender()
    
    print(f"\n📧 Sending test emails to {to_email} from all accounts...")
    result = sender.send_test_email(to_email)
    
    print(f"\n{result['message']}")
    if result.get("details"):
        for detail in result["details"]:
            status = "✅" if detail["success"] else "❌"
            print(f"   {status} {detail['from_email']}")


def list_accounts():
    """List all configured email accounts"""
    sender = ZohoEmailSender()
    sender.list_accounts()


def test_rocketreach():
    """Test RocketReach connection"""
    client = RocketReachClient()
    
    print("\n🔍 Testing RocketReach API...")
    credits = client.check_credits()
    
    if "error" in credits:
        print(f"❌ Error: {credits['error']}")
    else:
        print("✅ RocketReach API connected!")
        print(f"   {json.dumps(credits, indent=2)}")


def preview_email(description: str):
    """Preview what an email would look like for a campaign"""
    print(f"\n🔍 Generating preview for: \"{description}\"\n")
    
    generator = EmailGenerator()
    
    # Get ICP and criteria
    config = generator.determine_icp_and_criteria(description)
    
    # Create a sample lead
    sample_lead = {
        "first_name": "Alex",
        "full_name": "Alex Johnson",
        "title": config['search_criteria'].get('current_title', ['CEO'])[0],
        "company": "Example Corp",
        "industry": config['search_criteria'].get('industry', ['Technology'])[0],
        "location": "San Francisco"
    }
    
    # Generate email
    email = generator.generate_initial_email(sample_lead, config['campaign_context'])
    
    print(f"📧 Sample Email to: {sample_lead['first_name']} ({sample_lead['title']} at {sample_lead['company']})")
    print(f"\n   Subject: {email['subject']}")
    print(f"\n   Body:")
    for line in email['body'].split('\n'):
        print(f"   {line}")
    
    print(f"\n💡 This email targets: {config['target_description']}")


def check_replies():
    """Check inbox for replies"""
    from reply_detector import ReplyDetector
    
    print("\n📬 Checking for replies across all accounts...")
    print("   (Requires IMAP enabled in Zoho: Settings → Mail Accounts → IMAP Access)\n")
    
    detector = ReplyDetector()
    results = detector.check_replies(since_days=7)
    
    print(f"\n📊 Results:")
    print(f"   Accounts checked: {results.get('accounts_checked', 0)}")
    if results.get('accounts_failed', 0) > 0:
        print(f"   Accounts failed (enable IMAP): {results['accounts_failed']}")
    print(f"   Replies found: {results['replies_found']}")
    print(f"   Leads updated: {results['leads_updated']}")
    
    if results['details']:
        print(f"\n   Recent replies:")
        for detail in results['details']:
            print(f"   • {detail['lead_name']} ({detail['from']})")
            print(f"     Subject: {detail['subject']}")
    
    # Check bounces too
    if results.get('accounts_checked', 0) > 0:
        print("\n📭 Checking for bounces...")
        bounces = detector.check_bounces(since_days=7)
        print(f"   Bounces found: {bounces['bounces_found']}")
    
    if results.get('accounts_failed', 0) == len(detector.accounts):
        print("\n⚠️  No accounts could connect. Enable IMAP in Zoho for each account:")
        print("   1. Go to mail.zoho.com")
        print("   2. Settings (gear icon) → Mail Accounts")
        print("   3. Select account → IMAP Access → Toggle ON")


def run_auto_scheduler(config_file: str = None):
    """Run the full automated scheduler"""
    from auto_scheduler import AutoScheduler, SchedulerConfig
    
    scheduler = AutoScheduler()
    
    # Load config if provided
    if config_file:
        try:
            with open(config_file, 'r') as f:
                campaigns = json.load(f)
                for c in campaigns:
                    scheduler.add_scheduled_campaign(**c)
        except Exception as e:
            print(f"Error loading config: {e}")
    else:
        # Load from default location
        saved = SchedulerConfig.load()
        for c in saved:
            scheduler._scheduled_campaigns.append(c)
    
    scheduler.start(
        check_replies_interval_hours=2,
        followup_check_interval_hours=6,
        initial_emails_interval_hours=1
    )


def add_scheduled_campaign(description: str, time: str, days: str, max_leads: int):
    """Add a campaign to the scheduler"""
    from auto_scheduler import SchedulerConfig
    
    campaigns = SchedulerConfig.load()
    
    new_campaign = {
        "id": len(campaigns) + 1,
        "description": description,
        "schedule_time": time,
        "days": [d.strip().lower() for d in days.split(",")],
        "max_leads": max_leads,
        "enabled": True,
        "created_at": datetime.utcnow().isoformat(),
        "last_run": None,
        "campaign_ids": []
    }
    
    campaigns.append(new_campaign)
    SchedulerConfig.save(campaigns)
    
    print(f"\n✅ Scheduled campaign added!")
    print(f"   Description: {description}")
    print(f"   Time: {time}")
    print(f"   Days: {days}")
    print(f"   Max leads: {max_leads}")
    print(f"\n   Run 'python main.py auto-scheduler' to start")


def list_scheduled_campaigns():
    """List all scheduled campaigns"""
    from auto_scheduler import SchedulerConfig
    
    campaigns = SchedulerConfig.load()
    
    if not campaigns:
        print("\n📭 No scheduled campaigns.")
        print("   Add one with: python main.py schedule-add \"description\" --time 09:00 --days mon,wed,fri")
        return
    
    print(f"\n📅 Scheduled Campaigns ({len(campaigns)})\n")
    
    for c in campaigns:
        status = "🟢" if c.get('enabled', True) else "⏸️"
        print(f"{status} [{c['id']}] {c['description']}")
        print(f"   Time: {c['schedule_time']} on {', '.join(c['days'])}")
        print(f"   Max leads: {c['max_leads']}")
        if c.get('last_run'):
            print(f"   Last run: {c['last_run']}")
        print()


def run_scheduler():
    """Run the automated scheduler for follow-ups (legacy)"""
    # Redirect to the new auto scheduler
    run_auto_scheduler()


def main():
    parser = argparse.ArgumentParser(
        description="PrimeStrides Cold Email Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py create "target startup founders needing AI"
  python main.py preview "target e-commerce companies"
  python main.py run <campaign_id> --dry-run
  
  # Scheduling
  python main.py schedule-add "target CTOs" --time 09:00 --days mon,wed,fri
  python main.py schedule-list
  python main.py auto-scheduler
  
  # Reply detection
  python main.py check-replies
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    
    # Create campaign (smart)
    create_parser = subparsers.add_parser("create", help="Create a campaign (AI determines targeting)")
    create_parser.add_argument("description", help="Describe who you want to target")
    
    # Preview email
    preview_parser = subparsers.add_parser("preview", help="Preview what emails would look like")
    preview_parser.add_argument("description", help="Describe the target audience")
    
    # Run campaign
    run_parser = subparsers.add_parser("run", help="Run a campaign")
    run_parser.add_argument("campaign_id", help="Campaign ID")
    run_parser.add_argument("--dry-run", action="store_true", help="Don't send emails")
    run_parser.add_argument("--max-leads", type=int, default=50, help="Max leads to fetch")
    run_parser.add_argument("--skip-fetch", action="store_true", help="Skip fetching new leads")
    run_parser.add_argument("--skip-initial", action="store_true", help="Only send follow-ups")
    
    # Follow-ups only
    followup_parser = subparsers.add_parser("followups", help="Send follow-ups only")
    followup_parser.add_argument("campaign_id", help="Campaign ID")
    followup_parser.add_argument("--dry-run", action="store_true", help="Don't send emails")
    
    # Stats
    stats_parser = subparsers.add_parser("stats", help="View campaign stats")
    stats_parser.add_argument("campaign_id", help="Campaign ID")
    
    # List campaigns
    subparsers.add_parser("list", help="List all campaigns")
    
    # List email accounts
    subparsers.add_parser("accounts", help="List configured email accounts")
    
    # Test email
    test_email_parser = subparsers.add_parser("test-email", help="Send test email from all accounts")
    test_email_parser.add_argument("email", help="Email address")
    
    # Test RocketReach
    subparsers.add_parser("test-rocketreach", help="Test RocketReach API")
    
    # Check replies
    subparsers.add_parser("check-replies", help="Check inbox for replies and bounces")
    
    # Schedule add
    schedule_add_parser = subparsers.add_parser("schedule-add", help="Add a scheduled campaign")
    schedule_add_parser.add_argument("description", help="Campaign description")
    schedule_add_parser.add_argument("--time", default="09:00", help="Time to run (HH:MM)")
    schedule_add_parser.add_argument("--days", default="monday,wednesday,friday", help="Days to run (comma-separated)")
    schedule_add_parser.add_argument("--max-leads", type=int, default=20, help="Max leads per run")
    
    # Schedule list
    subparsers.add_parser("schedule-list", help="List scheduled campaigns")
    
    # Auto scheduler (full automation)
    auto_scheduler_parser = subparsers.add_parser("auto-scheduler", help="Run full automation (replies, follow-ups, scheduled campaigns)")
    auto_scheduler_parser.add_argument("--config", help="Path to scheduler config JSON")
    
    # Legacy scheduler
    subparsers.add_parser("scheduler", help="Run follow-up scheduler (legacy)")
    
    args = parser.parse_args()
    
    if args.command == "create":
        create_campaign_smart(args.description)
    elif args.command == "preview":
        preview_email(args.description)
    elif args.command == "run":
        run_campaign(
            args.campaign_id,
            dry_run=args.dry_run,
            max_leads=args.max_leads,
            skip_fetch=args.skip_fetch,
            skip_initial=args.skip_initial
        )
    elif args.command == "followups":
        send_followups(args.campaign_id, dry_run=args.dry_run)
    elif args.command == "stats":
        show_stats(args.campaign_id)
    elif args.command == "list":
        list_campaigns()
    elif args.command == "accounts":
        list_accounts()
    elif args.command == "test-email":
        test_email(args.email)
    elif args.command == "test-rocketreach":
        test_rocketreach()
    elif args.command == "check-replies":
        check_replies()
    elif args.command == "schedule-add":
        add_scheduled_campaign(args.description, args.time, args.days, args.max_leads)
    elif args.command == "schedule-list":
        list_scheduled_campaigns()
    elif args.command == "auto-scheduler":
        run_auto_scheduler(getattr(args, 'config', None))
    elif args.command == "scheduler":
        run_scheduler()
    else:
        parser.print_help()
        print("\n💡 Quick start:")
        print('   python main.py create "target startup founders needing AI integration"')
        print('   python main.py auto-scheduler  # Full automation')


if __name__ == "__main__":
    main()
