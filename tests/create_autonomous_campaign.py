#!/usr/bin/env python3
"""Create autonomous campaign for production."""
import sys
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

from pymongo import MongoClient
from datetime import datetime

client = MongoClient('mongodb://admin:strongpassword@192.168.1.9:27017/')
db = client['primeoutreachcron']

# Create autonomous campaign using the ctos_at_capacity ICP
campaign = {
    'name': 'CTOs At Capacity - Autonomous',
    'description': 'Target CTOs and VPs of Engineering at scaling companies',
    'autonomous': True,
    'icp_template': 'ctos_at_capacity',
    'max_leads_per_run': 15,
    'status': 'active',
    'created_at': datetime.utcnow(),
    'last_run': None,
    'criteria': {
        'current_title': ['CTO', 'VP of Engineering', 'Head of Engineering', 'Engineering Director'],
        'location': ['United States', 'Canada', 'United Kingdom'],
    },
    'campaign_context': {
        'product_service': 'senior engineering team for 8-week sprints',
        'single_pain_point': 'team is stretched thin and cant hire fast enough',
        'unique_angle': 'senior engineers who hit the ground running - no 3-month ramp up',
        'case_study': {
            'company_hint': 'an enterprise company',
            'result_short': '3.2x faster deploys, 41% cost cut',
            'timeline': '12 weeks'
        },
        'front_end_offer': 'free technical roadmap session'
    }
}

# Check if already exists
existing = db['campaigns'].find_one({'name': campaign['name']})
if existing:
    print(f'Campaign already exists: {existing["_id"]}')
else:
    result = db['campaigns'].insert_one(campaign)
    print(f'Created autonomous campaign: {result.inserted_id}')

# Verify
count = db['campaigns'].count_documents({'autonomous': True})
print(f'Total autonomous campaigns: {count}')

# Show all autonomous campaigns
print('\nAutonomous campaigns:')
for c in db['campaigns'].find({'autonomous': True}):
    print(f'  - {c["name"]} (max_leads: {c.get("max_leads_per_run", "not set")})')
