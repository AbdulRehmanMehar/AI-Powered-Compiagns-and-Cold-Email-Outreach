#!/usr/bin/env python3
from database import SchedulerConfig
from datetime import datetime

# Increase max_leads to account for 14% conversion rate
new_campaigns = [
    {
        'name': 'morning_campaign',
        'description': 'Morning Autonomous Campaign',
        'autonomous': True,
        'schedule_time': '09:00',
        'days': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
        'max_leads': 100,
        'enabled': True
    },
    {
        'name': 'midday_campaign',
        'description': 'Midday Autonomous Campaign',
        'autonomous': True,
        'schedule_time': '12:00',
        'days': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
        'max_leads': 100,
        'enabled': True
    },
    {
        'name': 'afternoon_campaign',
        'description': 'Afternoon Autonomous Campaign',
        'autonomous': True,
        'schedule_time': '15:00',
        'days': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
        'max_leads': 100,
        'enabled': True
    }
]

SchedulerConfig._collection.update_one(
    {'config_type': 'main'},
    {'$set': {
        'scheduled_campaigns': new_campaigns,
        'updated_at': datetime.utcnow()
    }}
)

print('✅ Updated max_leads: 28 → 100 per campaign')
print()
print('Expected outcome (based on 14% historical conversion):')
print('  - 3 campaigns × 100 leads = 300 leads fetched/day')
print('  - 300 × 14% = ~42 emails sent/day')
print()
print('This is conservative for warmup. Monitor for 3-5 days, then:')
print('  - If conversion improves: keep at 100')
print('  - If still 14%: increase to 150 (= 63 emails/day)')
print('  - Target: 200 leads/campaign (= 84 emails/day)')
