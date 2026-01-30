"""Test MongoDB-based scheduler configuration"""
import sys
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

from database import SchedulerConfig

def test_scheduler_config():
    print("=== MONGODB SCHEDULER CONFIG ===")
    
    # Initialize default config
    config = SchedulerConfig.get_config()
    settings = SchedulerConfig.get_settings()
    
    print(f"Mode: {config.get('mode')}")
    print(f"Campaigns: {len(config.get('scheduled_campaigns', []))}")
    
    for c in config.get('scheduled_campaigns', []):
        mode = "autonomous" if c.get("autonomous") else "manual"
        print(f"  - {c.get('name')}: {c.get('schedule_time')} ({mode})")
    
    print()
    print("=== SETTINGS ===")
    print(f"Timezone: {settings.get('timezone')}")
    print(f"Exploration rate: {settings.get('exploration_rate')}")
    print(f"Min days between same ICP: {settings.get('min_days_between_same_icp')}")
    
    print()
    print("=== AUTONOMOUS ICP SELECTION ===")
    selection = SchedulerConfig.select_icp_for_autonomous_run()
    print(f"Selected: {selection['selected_icp']}")
    print(f"Reason: {selection['selection_reason']}")
    print(f"Mode: {selection['selection_mode']}")
    
    print()
    print("Top scored ICPs:")
    for icp, info in list(selection['all_scores'].items())[:5]:
        print(f"  {icp}: score={info['score']:.0f} ({info['reason']})")
    
    print()
    print("=== RUN HISTORY ===")
    runs_today = SchedulerConfig.get_runs_today()
    print(f"Runs today: {len(runs_today)}")
    
    recent_icps = SchedulerConfig.get_icps_used_recently(days=7)
    print(f"ICPs used in last 7 days: {recent_icps}")
    
    print()
    print("✅ MongoDB scheduler config working!")


if __name__ == "__main__":
    test_scheduler_config()
