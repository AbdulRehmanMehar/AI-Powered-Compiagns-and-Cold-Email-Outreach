"""Check if bounced emails are properly excluded from followups"""
import sys
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

from database import Email, emails_collection, leads_collection
from bson import ObjectId
import config

# Get all campaigns
from database import campaigns_collection
campaigns = list(campaigns_collection.find({}))

print("=" * 60)
print("CHECKING FOLLOWUP EXCLUSION OF BOUNCED EMAILS")
print("=" * 60)

for campaign in campaigns:
    campaign_id = str(campaign['_id'])
    campaign_name = campaign.get('name', 'Unknown')
    
    print(f"\nCampaign: {campaign_name}")
    
    # Get pending followups
    pending = Email.get_pending_followups(campaign_id, config.FOLLOWUP_DELAY_DAYS)
    
    # Check if any bounced leads are in the pending list
    bounced_in_pending = 0
    for p in pending:
        lead_id = p['_id']
        # Check if this lead has any bounced emails
        bounced = emails_collection.find_one({
            'lead_id': lead_id,
            'campaign_id': ObjectId(campaign_id),
            'status': 'bounced'
        })
        if bounced:
            bounced_in_pending += 1
            lead = leads_collection.find_one({'_id': lead_id})
            print(f"  ⚠️ BOUNCED LEAD IN PENDING FOLLOWUPS: {lead.get('email') if lead else 'unknown'}")
    
    print(f"  Pending followups: {len(pending)}")
    print(f"  Bounced leads in pending: {bounced_in_pending}")

# Also check: leads where ANY email bounced
print("\n" + "=" * 60)
print("LEADS WITH BOUNCED EMAILS")
print("=" * 60)

bounced_leads = emails_collection.distinct('lead_id', {'status': 'bounced'})
print(f"Total leads with at least one bounce: {len(bounced_leads)}")

# Check if these leads are in any pending followup
for campaign in campaigns:
    campaign_id = str(campaign['_id'])
    pending = Email.get_pending_followups(campaign_id, config.FOLLOWUP_DELAY_DAYS)
    pending_lead_ids = [p['_id'] for p in pending]
    
    overlap = set(pending_lead_ids) & set(bounced_leads)
    if overlap:
        print(f"\n⚠️ Campaign '{campaign.get('name')}' has {len(overlap)} bounced leads in followup queue!")
        for lead_id in list(overlap)[:5]:
            lead = leads_collection.find_one({'_id': lead_id})
            print(f"   - {lead.get('email') if lead else 'unknown'}")
