import json

# Restore from backup
with open('scheduler_config.backup.json') as f:
    config = json.load(f)

campaigns = config['scheduled_campaigns']
weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
times = ['09:00', '12:00', '15:00']

# Create 15 unique day/time slots
slots = [(d, t) for d in weekdays for t in times]

# Select 15 campaigns - every 3rd for diversity  
selected_indices = list(range(0, min(len(campaigns), 50), 3))[:15]

# Build new campaign list
new_campaigns = []
for i, camp in enumerate(campaigns):
    c = camp.copy()
    if i in selected_indices:
        slot_idx = selected_indices.index(i)
        day, time = slots[slot_idx]
        c['days'] = [day]
        c['schedule_time'] = time
        c['max_leads'] = 28
        c['enabled'] = True
    else:
        c['enabled'] = False
    new_campaigns.append(c)

config['scheduled_campaigns'] = new_campaigns

with open('scheduler_config.json', 'w') as f:
    json.dump(config, f, indent=2)

# Verify
active = [c for c in new_campaigns if c.get('enabled')]
print(f'✅ Optimized scheduler configuration')
print(f'   Active campaigns: {len(active)}')
print(f'   Disabled campaigns: {len(new_campaigns) - len(active)}')
print()
for day in weekdays:
    day_camps = [c for c in active if day in c['days']]
    if day_camps:
        times_str = ', '.join(sorted(set(c['schedule_time'] for c in day_camps)))
        print(f'   {day.capitalize():12}: {len(day_camps)} campaigns at {times_str}')
print()
print(f'   Expected: 3 campaigns/day × 28 leads = 84 emails/day')
print(f'   Capacity: 8 accounts × 12 emails = 96 emails/day')
print(f'   Utilization: 88%')
