#!/usr/bin/env python3
"""Update MongoDB scheduler config to maximize sending capacity"""

from database import SchedulerConfig
from datetime import datetime

# Update to maximize capacity: 3 campaigns per day, 28 leads each
new_campaigns = [
    {
        "name": "morning_campaign",
        "description": "Morning Autonomous Campaign",
        "autonomous": True,
        "schedule_time": "09:00",
        "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "max_leads": 28,
        "enabled": True
    },
    {
        "name": "midday_campaign",
        "description": "Midday Autonomous Campaign",
        "autonomous": True,
        "schedule_time": "12:00",
        "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "max_leads": 28,
        "enabled": True
    },
    {
        "name": "afternoon_campaign",
        "description": "Afternoon Autonomous Campaign",
        "autonomous": True,
        "schedule_time": "15:00",
        "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "max_leads": 28,
        "enabled": True
    }
]

# Update MongoDB
result = SchedulerConfig._collection.update_one(
    {"config_type": "main"},
    {"$set": {
        "scheduled_campaigns": new_campaigns,
        "updated_at": datetime.utcnow()
    }}
)

print("✅ Updated MongoDB scheduler config:")
print(f"   Modified: {result.modified_count} document")
print(f"   Campaigns per day: 3 (9am, 12pm, 3pm)")
print(f"   Leads per campaign: 28")
print(f"   Mode: Autonomous (AI selects best ICP)")
print(f"   Expected emails/day: 84 (vs 96 capacity)")
print()

# Verify
config = SchedulerConfig.get_config()
print("Current config in MongoDB:")
for i, camp in enumerate(config['scheduled_campaigns'], 1):
    print(f"   {i}. {camp['name']}: {camp['schedule_time']}, {camp['max_leads']} leads")
print()
print("🔄 Restart your scheduler for changes to take effect")
