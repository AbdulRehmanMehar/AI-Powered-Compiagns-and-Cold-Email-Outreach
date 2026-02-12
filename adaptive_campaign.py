"""
Adaptive Campaign Runner — Ensures GLOBAL_DAILY_TARGET is hit by fetching enough leads
to account for skips (bounces, DNC, invalid emails, verification failures, etc.)

This replaces the fixed max_leads approach with dynamic fetching that monitors:
- How many drafts are ready to send
- How many emails sent today
- Skip rate from verification/DNC/bounces
- Adjusts fetch size to compensate for rejections

Key logic:
- Target: GLOBAL_DAILY_TARGET (e.g., 300)
- Skip rate: ~20-30% (bounces, DNC, invalid, verification failures)
- Fetch multiplier: 1.4x target to account for skips
- Monitors draft queue and refills throughout the day
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List

import config
from database import Campaign, db, Email
from campaign_manager import CampaignManager

logger = logging.getLogger("coldemails.adaptive_campaign")

email_drafts_collection = db["email_drafts"]


class AdaptiveCampaignRunner:
    """
    Runs campaigns with adaptive lead fetching to hit daily targets.
    
    Instead of fetching fixed batches (e.g., 28 leads), dynamically calculates
    how many leads to fetch based on:
    - Daily target (GLOBAL_DAILY_TARGET)
    - Already sent today
    - Ready drafts in queue
    - Historical skip rate
    """
    
    def __init__(self):
        self.campaign_manager = CampaignManager()
        self.target_daily = config.GLOBAL_DAILY_TARGET
        # Assume 25% skip rate (conservative estimate)
        self.skip_multiplier = 1.35
        
    def get_daily_progress(self) -> Dict:
        """Get current progress toward daily target."""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Emails sent today
        sent_today = Email.count_sent_since(today_start)
        
        # Ready drafts (pending send)
        ready_drafts = email_drafts_collection.count_documents({"status": "ready"})
        
        # Pending leads (no draft yet, no email sent)
        cm = CampaignManager()
        pending_leads = len(cm.get_pending_leads(max_leads=1000))
        
        # Calculate what we still need
        total_pipeline = sent_today + ready_drafts
        remaining_needed = max(0, self.target_daily - total_pipeline)
        
        return {
            "sent_today": sent_today,
            "ready_drafts": ready_drafts,
            "pending_leads": pending_leads,
            "total_pipeline": total_pipeline,
            "remaining_needed": remaining_needed,
            "target": self.target_daily,
            "on_track": total_pipeline >= self.target_daily * 0.8,  # 80% threshold
        }
    
    def calculate_leads_to_fetch(self) -> int:
        """
        Calculate how many leads to fetch to hit daily target.
        
        Accounts for:
        - Leads already in pipeline
        - Skip rate (bounces, DNC, verification failures)
        - Buffer for safety
        """
        progress = self.get_daily_progress()
        
        if progress["remaining_needed"] <= 0:
            logger.info(f"Daily target already met: {progress['total_pipeline']}/{self.target_daily}")
            return 0
        
        # Need to fetch remaining, adjusted for skip rate
        # e.g., need 100 more → fetch 135 to account for 25% skips
        leads_to_fetch = int(progress["remaining_needed"] * self.skip_multiplier)
        
        # Add small buffer (10%)
        leads_to_fetch = int(leads_to_fetch * 1.1)
        
        # Cap at reasonable limits
        leads_to_fetch = min(leads_to_fetch, 500)  # RocketReach API limit
        leads_to_fetch = max(leads_to_fetch, 50)   # Minimum viable batch
        
        logger.info(
            f"Calculated fetch size: {leads_to_fetch} leads "
            f"(need {progress['remaining_needed']}, skip multiplier {self.skip_multiplier})"
        )
        
        return leads_to_fetch
    
    def run_adaptive_campaign(self, campaign_rotation: bool = True) -> Dict:
        """
        Run campaigns adaptively to hit daily target.
        
        Args:
            campaign_rotation: If True, cycles through active campaigns.
                              If False, uses autonomous mode.
        
        Returns:
            Dict with results and statistics
        """
        progress = self.get_daily_progress()
        logger.info(f"Daily progress: {progress['sent_today']}/{self.target_daily} sent, "
                   f"{progress['ready_drafts']} drafts ready")
        
        if progress["remaining_needed"] <= 0:
            return {
                "status": "target_met",
                "sent_today": progress["sent_today"],
                "ready_drafts": progress["ready_drafts"],
                "message": f"Daily target already met ({progress['total_pipeline']}/{self.target_daily})"
            }
        
        # Calculate how many leads to fetch
        fetch_size = self.calculate_leads_to_fetch()
        
        if campaign_rotation:
            # Cycle through active campaigns
            result = self._run_rotating_campaigns(fetch_size)
        else:
            # Use autonomous mode
            result = self.campaign_manager.run_autonomous_campaign(
                max_leads=fetch_size,
                dry_run=False
            )
        
        # Check progress after fetching
        new_progress = self.get_daily_progress()
        
        return {
            "status": "success",
            "fetched_leads": fetch_size,
            "sent_today": new_progress["sent_today"],
            "ready_drafts": new_progress["ready_drafts"],
            "total_pipeline": new_progress["total_pipeline"],
            "remaining_needed": new_progress["remaining_needed"],
            "on_track": new_progress["on_track"],
            "result": result,
        }
    
    def _run_rotating_campaigns(self, total_leads_needed: int) -> Dict:
        """
        Distribute lead fetching across multiple active campaigns.
        
        Instead of fetching all leads from one campaign, rotate through
        active campaigns to diversify targeting.
        """
        active_campaigns = Campaign.get_active_campaigns()
        
        if not active_campaigns:
            logger.warning("No active campaigns found")
            return {"error": "No active campaigns"}
        
        # Distribute leads across campaigns
        leads_per_campaign = max(20, total_leads_needed // len(active_campaigns))
        
        results = []
        total_fetched = 0
        
        for campaign in active_campaigns[:5]:  # Limit to 5 campaigns per run
            if total_fetched >= total_leads_needed:
                break
            
            campaign_id = str(campaign["_id"])
            campaign_name = campaign.get("name", "Unknown")
            
            logger.info(f"Fetching {leads_per_campaign} leads from: {campaign_name}")
            
            try:
                # Fetch leads for this campaign
                leads = self.campaign_manager.fetch_leads_for_campaign(
                    campaign_id=campaign_id,
                    max_leads=leads_per_campaign
                )
                
                total_fetched += len(leads)
                results.append({
                    "campaign": campaign_name,
                    "fetched": len(leads)
                })
                
            except Exception as e:
                logger.error(f"Failed to fetch leads for {campaign_name}: {e}")
                results.append({
                    "campaign": campaign_name,
                    "error": str(e)
                })
        
        return {
            "campaigns_run": len(results),
            "total_fetched": total_fetched,
            "details": results
        }
    
    def should_run_campaign(self) -> bool:
        """Check if we should run a campaign now (are we below target?)."""
        progress = self.get_daily_progress()
        
        # Run if we're below 90% of target
        threshold = self.target_daily * 0.9
        should_run = progress["total_pipeline"] < threshold
        
        if should_run:
            logger.info(f"Campaign should run: {progress['total_pipeline']} < {threshold}")
        else:
            logger.info(f"Skipping campaign: {progress['total_pipeline']} >= {threshold}")
        
        return should_run


# Convenience functions for scheduler integration

def run_adaptive_campaign_check() -> Dict:
    """
    Check if we need to fetch more leads and do so if needed.
    Safe to call multiple times per day.
    """
    runner = AdaptiveCampaignRunner()
    
    if not runner.should_run_campaign():
        progress = runner.get_daily_progress()
        return {
            "status": "skipped",
            "reason": "target_nearly_met",
            "progress": progress
        }
    
    return runner.run_adaptive_campaign(campaign_rotation=True)


def get_campaign_health() -> Dict:
    """Get health metrics for monitoring."""
    runner = AdaptiveCampaignRunner()
    progress = runner.get_daily_progress()
    
    health = {
        "healthy": progress["on_track"],
        "sent_today": progress["sent_today"],
        "target": runner.target_daily,
        "progress_pct": (progress["total_pipeline"] / runner.target_daily * 100) if runner.target_daily > 0 else 0,
        "ready_drafts": progress["ready_drafts"],
        "pending_leads": progress["pending_leads"],
    }
    
    return health
