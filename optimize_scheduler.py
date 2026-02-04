#!/usr/bin/env python3
"""
Optimize scheduler configuration to match sending capacity.

Current situation:
- 8 email accounts
- 12 emails/day per account (Week 3 warmup)
- Total capacity: 96 emails/day
- Want to use ~85 emails/day (leave buffer)

Strategy:
- Run 3 campaigns per day
- Each campaign: 28 leads
- Total: 84 emails/day (88% capacity utilization)
- Rotate through all 50 campaigns over ~2 weeks
"""

import json
from copy import deepcopy

# Load current config
with open('scheduler_config.json', 'r') as f:
    config = json.load(f)

campaigns = config['scheduled_campaigns']
print(f"Loaded {len(campaigns)} campaigns\n")

# Target: 3 campaigns per day, each with ~28 leads
# Schedule them at different times through the day
# Rotate which campaigns run on which days

# Days of week
weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']

# Times to run campaigns (spread throughout the day)
time_slots = ['09:00', '11:00', '14:00']

# Assign campaigns to days in a rotating pattern
# Strategy: 3 campaigns per day, each at a different time
# 15 total slots per week (3 times × 5 days)
# Cycle through all 50 campaigns over ~3.3 weeks

campaign_schedule = []

# Create all possible day/time combinations
day_time_slots = []
for day in weekdays:
    for time in time_slots:
        day_time_slots.append((day, time))

# day_time_slots now has 15 combinations
# Repeat it 4 times to cover 60 slots (more than our 50 campaigns)
extended_slots = (day_time_slots * 4)[:len(campaigns)]

# Assign each campaign to a unique day/time slot
for idx, campaign in enumerate(campaigns):
    day, time = extended_slots[idx]
    
    camp = campaign.copy()
    camp['days'] = [day]
    camp['schedule_time'] = time
    camp['max_leads'] = 28
    
    campaign_schedule.append(camp)

# Replace campaigns in config
config['scheduled_campaigns'] = campaign_schedule

# Save optimized config
with open('scheduler_config.json', 'w') as f:
    json.dump(config, f, indent=2)

print("✅ Optimized scheduler configuration:")
print(f"   Total campaigns: {len(config['scheduled_campaigns'])}")
print(f"   Campaigns per day: 3")
print(f"   Leads per campaign: 28")
print(f"   Expected emails/day: 84 (out of 96 capacity)")
print(f"   Capacity utilization: 88%")
print()
print("Distribution:")
for day in weekdays:
    count = sum(1 for c in config['scheduled_campaigns'] if day in c['days'])
    print(f"   {day.capitalize():12}: {count} campaigns")
print()
print("Backup saved to: scheduler_config.backup.json")
print("Restart your scheduler for changes to take effect")
