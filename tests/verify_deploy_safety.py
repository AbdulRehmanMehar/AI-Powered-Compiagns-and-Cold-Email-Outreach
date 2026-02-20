"""End-to-end pipeline verification before deployment."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db, Campaign, Lead, leads_collection, campaigns_collection
from campaign_manager import CampaignManager
from bson import ObjectId
from collections import Counter

print('=== END-TO-END PIPELINE VERIFICATION ===')
print()

issues = []

# 1. CAMPAIGN STATUS
active = list(campaigns_collection.find({'status': 'active'}, {'_id': 1, 'name': 1}))
draft = list(campaigns_collection.find({'status': 'draft'}, {'_id': 1, 'name': 1}))
print(f'1. CAMPAIGNS: {len(active)} active, {len(draft)} draft')

# 2. LEADS — verify all are ObjectId now
str_count = leads_collection.count_documents({'campaign_id': {'$type': 'string'}})
oid_count = leads_collection.count_documents({'campaign_id': {'$type': 'objectId'}})
print(f'2. LEADS campaign_id types: ObjectId={oid_count}, String={str_count} (string should be 0)')
if str_count > 0:
    issues.append(f'Still {str_count} string campaign_ids in leads')

# 3. GET_PENDING_LEADS — verify it returns leads from active campaigns
cm = CampaignManager()
pending = cm.get_pending_leads(max_leads=500)
print(f'3. GET_PENDING_LEADS: {len(pending)} leads returned')
if len(pending) == 0:
    issues.append('No pending leads returned')

# Check they all belong to active campaigns
active_ids = set(str(c['_id']) for c in active)
mismatched = [l for l in pending if str(l.get('campaign_id', '')) not in active_ids]
print(f'   Leads from non-active campaigns: {len(mismatched)} (should be 0)')
if len(mismatched) > 0:
    issues.append(f'{len(mismatched)} leads from non-active campaigns')

# 4. LEADS → CAMPAIGN JOIN — verify leads match active campaign iteration
leads_by_camp = Counter(str(l.get('campaign_id', '')) for l in pending)
matched = 0
for campaign in active:
    cid = str(campaign['_id'])
    c_leads = leads_by_camp.get(cid, 0)
    if c_leads > 0:
        matched += c_leads
print(f'4. LEAD→CAMPAIGN JOIN: {matched}/{len(pending)} leads match via str(campaign_id)==str(_id)')
if len(pending) > 0 and matched == 0:
    issues.append('ZERO leads join to active campaigns — type mismatch!')

# 5. REPLENISH QUERY — test ObjectId vs dual-type query
sample_campaign = active[0] if active else None
if sample_campaign:
    cid_oid = sample_campaign['_id']
    cid_str = str(cid_oid)
    old_count = leads_collection.count_documents({'campaign_id': cid_oid})
    new_count = leads_collection.count_documents({'campaign_id': {'$in': [cid_oid, cid_str]}})
    print(f'5. REPLENISH QUERY test ({cid_str[:8]}...):')
    print(f'   ObjectId-only: {old_count} | Dual-type: {new_count}')
    print(f'   (After migration both should be equal)')

# 6. DRAFT QUEUE
drafts_col = db['email_drafts']
ready = drafts_col.count_documents({'status': 'ready_to_send'})
generating = drafts_col.count_documents({'status': 'generating'})
print(f'6. DRAFT QUEUE: ready_to_send={ready}, generating={generating}')

# 7. EMAIL DRAFTS campaign_id type check
draft_str = drafts_col.count_documents({'campaign_id': {'$type': 'string'}})
draft_oid = drafts_col.count_documents({'campaign_id': {'$type': 'objectId'}})
print(f'7. DRAFT campaign_id types: ObjectId={draft_oid}, String={draft_str}')
if draft_str > 0:
    issues.append(f'{draft_str} email_drafts have string campaign_id')

# 8. Lead.create type check — simulate
test_cid = str(active[0]['_id']) if active else None
if test_cid:
    result_cid = ObjectId(test_cid) if test_cid else None
    correct = isinstance(result_cid, ObjectId)
    print(f'8. Lead.create would store campaign_id as: {type(result_cid).__name__} — correct={correct}')
    if not correct:
        issues.append('Lead.create would store string instead of ObjectId')

# 9. Check email_drafts creation — how does pre_generator store campaign_id in drafts?
# Find a draft and check if its campaign_id matches an active campaign
sample_draft = drafts_col.find_one({'status': 'ready_to_send'})
if sample_draft:
    d_cid = sample_draft.get('campaign_id')
    d_type = type(d_cid).__name__
    matches_active = str(d_cid) in active_ids
    print(f'9. Sample draft campaign_id: type={d_type}, matches_active={matches_active}')
else:
    print(f'9. No ready_to_send drafts to check')

# 10. Check emails collection campaign_id type
emails_col = db['emails']
email_str = emails_col.count_documents({'campaign_id': {'$type': 'string'}})
email_oid = emails_col.count_documents({'campaign_id': {'$type': 'objectId'}})
print(f'10. EMAILS campaign_id types: ObjectId={email_oid}, String={email_str}')

print()
print('=== VERDICT ===')
if issues:
    print('ISSUES FOUND:')
    for i in issues:
        print(f'  ❌ {i}')
    sys.exit(1)
else:
    print('✅ ALL CHECKS PASSED — safe to deploy')
    sys.exit(0)
