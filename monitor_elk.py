#!/usr/bin/env python3
"""
ELK Monitoring Dashboard - Query and display key metrics from logs

This script helps you monitor your cold email system by querying
the ELK stack for important metrics and events.

Usage:
    python monitor_elk.py --today           # Show today's stats
    python monitor_elk.py --campaign <id>   # Show campaign details
    python monitor_elk.py --errors          # Show recent errors
"""

import argparse
from datetime import datetime, timedelta
from database import campaigns_collection, emails_collection, SendingStats
from bson import ObjectId


def show_daily_stats():
    """Show daily sending statistics"""
    print("\n" + "="*70)
    print(f"📊 DAILY STATS - {datetime.now().strftime('%Y-%m-%d')}")
    print("="*70)
    
    # Get today's campaigns
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    campaigns_today = list(campaigns_collection.find({
        'created_at': {'$gte': today_start}
    }).sort('created_at', -1))
    
    print(f"\n📧 Campaigns: {len(campaigns_today)}")
    
    total_leads = 0
    total_sent = 0
    
    for camp in campaigns_today:
        stats = camp.get('stats', {})
        leads = stats.get('total_leads', 0)
        sent = stats.get('emails_sent', 0)
        total_leads += leads
        total_sent += sent
        
        created = camp['created_at'].strftime('%H:%M')
        name = camp.get('name', 'Unnamed')[:40]
        print(f"  [{created}] {name}: {leads} leads → {sent} sent")
    
    print(f"\n📈 Totals:")
    print(f"  Leads fetched: {total_leads}")
    print(f"  Emails sent: {total_sent}")
    if total_leads > 0:
        conversion = int(total_sent / total_leads * 100)
        print(f"  Conversion rate: {conversion}%")
    
    # Account usage
    print(f"\n📮 Per-Account Usage:")
    from config import ZOHO_ACCOUNTS
    for account in ZOHO_ACCOUNTS:
        email = account['email']
        sent_today = SendingStats.get_sends_today(email)
        daily_limit = 12  # Week 3 warmup
        print(f"  {email}: {sent_today}/{daily_limit} ({int(sent_today/daily_limit*100)}%)")
    
    # Recent errors
    recent_errors = list(emails_collection.find({
        'status': 'failed',
        'created_at': {'$gte': today_start}
    }).limit(5))
    
    if recent_errors:
        print(f"\n⚠️  Recent Failures: {len(recent_errors)}")
        for err in recent_errors[:3]:
            to_email = err.get('to_email', 'unknown')
            error_msg = err.get('error', 'Unknown error')[:50]
            print(f"  - {to_email}: {error_msg}")


def show_campaign_details(campaign_id: str):
    """Show detailed stats for a specific campaign"""
    try:
        camp = campaigns_collection.find_one({'_id': ObjectId(campaign_id)})
        if not camp:
            print(f"❌ Campaign not found: {campaign_id}")
            return
        
        print("\n" + "="*70)
        print(f"📋 CAMPAIGN DETAILS")
        print("="*70)
        print(f"\nName: {camp.get('name', 'Unnamed')}")
        print(f"Created: {camp['created_at'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Status: {camp.get('status', 'unknown')}")
        
        stats = camp.get('stats', {})
        print(f"\nStats:")
        print(f"  Total leads: {stats.get('total_leads', 0)}")
        print(f"  Emails sent: {stats.get('emails_sent', 0)}")
        print(f"  Opens: {stats.get('opens', 0)}")
        print(f"  Clicks: {stats.get('clicks', 0)}")
        print(f"  Replies: {stats.get('replies', 0)}")
        print(f"  Bounces: {stats.get('bounces', 0)}")
        
        # Get email breakdown
        emails = list(emails_collection.find({'campaign_id': ObjectId(campaign_id)}))
        
        status_counts = {}
        for email in emails:
            status = email.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"\nEmail Status Breakdown:")
        for status, count in sorted(status_counts.items()):
            print(f"  {status}: {count}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


def show_recent_errors():
    """Show recent errors for debugging"""
    print("\n" + "="*70)
    print("⚠️  RECENT ERRORS (Last 24 hours)")
    print("="*70)
    
    since = datetime.utcnow() - timedelta(hours=24)
    
    errors = list(emails_collection.find({
        'status': 'failed',
        'created_at': {'$gte': since}
    }).sort('created_at', -1).limit(20))
    
    if not errors:
        print("\n✅ No errors in the last 24 hours!")
        return
    
    print(f"\nFound {len(errors)} errors:\n")
    
    error_types = {}
    for err in errors:
        error_msg = err.get('error', 'Unknown')
        error_types[error_msg] = error_types.get(error_msg, 0) + 1
    
    print("Error Summary:")
    for error, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  [{count:2}] {error}")
    
    print("\nRecent Failures:")
    for err in errors[:10]:
        time = err['created_at'].strftime('%H:%M:%S')
        to_email = err.get('to_email', 'unknown')
        error_msg = err.get('error', 'Unknown')[:60]
        print(f"  [{time}] {to_email}")
        print(f"         {error_msg}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Monitor cold email system')
    parser.add_argument('--today', action='store_true', help='Show today\'s statistics')
    parser.add_argument('--campaign', help='Show campaign details')
    parser.add_argument('--errors', action='store_true', help='Show recent errors')
    
    args = parser.parse_args()
    
    if args.today or not any([args.campaign, args.errors]):
        show_daily_stats()
    
    if args.campaign:
        show_campaign_details(args.campaign)
    
    if args.errors:
        show_recent_errors()
