"""Diagnose why we're at 98/300 today — find the bottleneck."""
from database import db
from datetime import datetime, timedelta

now_utc = datetime.utcnow()
today_et_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=19)

print("=" * 60)
print("WHY DIDN'T WE HIT 300? — Bottleneck Analysis")
print("=" * 60)

# 1. How many emails sent today?
total_sent = db["emails"].count_documents({"status": "sent", "sent_at": {"$gte": today_et_start}})
print(f"\n📊 Emails sent today: {total_sent} / 300 target")

# 2. Account-level breakdown — are accounts hitting their caps?
print("\n── ACCOUNT LIMITS ──")
import config
for acct in config.ZOHO_ACCOUNTS:
    email = acct["email"]
    sent = db["emails"].count_documents({
        "status": "sent",
        "from_email": email,
        "sent_at": {"$gte": today_et_start}
    })
    # Check if blocked
    blocked = db["blocked_accounts"].find_one({"email": email})
    blocked_str = f" ⛔ BLOCKED: {blocked.get('reason','')[:50]}" if blocked else ""
    
    # Check reputation
    rep = db["account_reputation"].find_one({"email": email})
    bounce_rate = rep.get("bounce_rate", 0) if rep else 0
    daily_limit = rep.get("adjusted_daily_limit", config.EMAILS_PER_DAY_PER_MAILBOX) if rep else config.EMAILS_PER_DAY_PER_MAILBOX
    
    cap = config.EMAILS_PER_DAY_PER_MAILBOX
    pct = (sent / cap * 100) if cap else 0
    print(f"  {email}: {sent}/{cap} ({pct:.0f}%) | rep_limit={daily_limit} | bounce={bounce_rate:.1%}{blocked_str}")

# 3. Lead availability — are there enough leads?
print("\n── LEAD SUPPLY ──")
total_leads = db["leads"].count_documents({})
with_campaign = db["leads"].count_documents({"campaign_id": {"$exists": True, "$ne": None}})
without_campaign = total_leads - with_campaign

# Leads that haven't been emailed yet
contacted_pipeline = [
    {"$match": {"status": "sent"}},
    {"$group": {"_id": "$lead_id"}},
]
contacted_lead_ids = set(str(r["_id"]) for r in db["emails"].aggregate(contacted_pipeline))

# Pending leads (have campaign_id, not yet contacted, valid email)
from bson import ObjectId
pending_pipeline = [
    {"$match": {
        "campaign_id": {"$exists": True, "$ne": None},
        "email": {"$exists": True, "$ne": ""},
        "email_invalid": {"$ne": True},
    }},
]
all_potential = list(db["leads"].find({
    "campaign_id": {"$exists": True, "$ne": None},
    "email": {"$exists": True, "$ne": "", "$ne": None},
    "email_invalid": {"$ne": True},
}, {"_id": 1, "email": 1}))

pending_count = 0
for l in all_potential:
    lid = str(l["_id"])
    if lid not in contacted_lead_ids:
        pending_count += 1

print(f"  Total leads: {total_leads}")
print(f"  With campaign_id: {with_campaign}")
print(f"  Without campaign_id: {without_campaign}")
print(f"  Already contacted: {len(contacted_lead_ids)}")
print(f"  Pending (campaign + valid email + not contacted): {pending_count}")

# 4. Draft queue — was the queue starved?
print("\n── DRAFT QUEUE ──")
draft_stats = {}
for r in db["email_drafts"].aggregate([{"$group": {"_id": "$status", "count": {"$sum": 1}}}]):
    draft_stats[r["_id"]] = r["count"]
for status, count in sorted(draft_stats.items()):
    print(f"  {status}: {count}")

# How many drafts were created today?
drafts_created_today = db["email_drafts"].count_documents({"created_at": {"$gte": today_et_start}})
print(f"  Created today: {drafts_created_today}")

# 5. Active campaigns
print("\n── ACTIVE CAMPAIGNS ──")
active = list(db["campaigns"].find({"status": "active"}, {"name": 1, "target_criteria": 1, "stats": 1}))
print(f"  Active campaigns: {len(active)}")
for c in active:
    stats = c.get("stats", {})
    name = c.get("name", str(c["_id"]))[:40]
    print(f"    {name}: sent={stats.get('emails_sent', 0)}, leads={stats.get('leads_fetched', 0)}")

# 6. Adaptive campaign — did it fetch enough leads?
print("\n── ADAPTIVE CAMPAIGN RUNS TODAY ──")
# Check scheduler_config for adaptive settings
sched = db["scheduler_config"].find_one({"_id": "default"})
if sched:
    print(f"  Global daily target: {sched.get('global_daily_target', 'not set')}")

# 7. Timing analysis — sending window utilization
print("\n── SENDING WINDOW UTILIZATION ──")
hour_pipeline = [
    {"$match": {"status": "sent", "sent_at": {"$gte": today_et_start}}},
    {"$group": {"_id": {"$hour": "$sent_at"}, "count": {"$sum": 1}}},
    {"$sort": {"_id": 1}},
]
by_hour = list(db["emails"].aggregate(hour_pipeline))
send_hours = []
for h in by_hour:
    utc_h = h["_id"]
    et_h = (utc_h - 5) % 24
    send_hours.append((et_h, h["count"]))
    bar = "█" * h["count"]
    print(f"  {et_h:02d}:00 ET: {h['count']:3d} {bar}")

if send_hours:
    first_h = min(h for h, _ in send_hours)
    last_h = max(h for h, _ in send_hours)
    window_hours = last_h - first_h + 1
    avg_per_hour = total_sent / window_hours if window_hours else 0
    needed_per_hour = 300 / 8  # 8-hour window
    print(f"\n  Active window: {first_h}:00 - {last_h+1}:00 ET ({window_hours} hours)")
    print(f"  Avg rate: {avg_per_hour:.1f} emails/hour")
    print(f"  Needed rate: {needed_per_hour:.1f} emails/hour for 300/day")

# 8. Cooldown analysis
print("\n── COOLDOWN CONFIG ──")
print(f"  MIN_DELAY: {config.MIN_DELAY_BETWEEN_EMAILS} min")
print(f"  MAX_DELAY: {config.MAX_DELAY_BETWEEN_EMAILS} min")
avg_delay = (config.MIN_DELAY_BETWEEN_EMAILS + config.MAX_DELAY_BETWEEN_EMAILS) / 2
max_per_acct_per_hour = 60 / avg_delay
num_accounts = len(config.ZOHO_ACCOUNTS)
theoretical_max = max_per_acct_per_hour * num_accounts * 8  # 8hr window
print(f"  Avg delay: {avg_delay} min → {max_per_acct_per_hour:.1f} emails/acct/hour")
print(f"  Accounts: {num_accounts}")
print(f"  Theoretical max (8hr window): {theoretical_max:.0f} emails/day")
print(f"  Per-mailbox cap: {config.EMAILS_PER_DAY_PER_MAILBOX}")
print(f"  Cap-limited max: {config.EMAILS_PER_DAY_PER_MAILBOX * num_accounts}/day")

# 9. Summary
print("\n" + "=" * 60)
print("BOTTLENECK SUMMARY")
print("=" * 60)
bottlenecks = []
if pending_count < 200:
    bottlenecks.append(f"🔴 LEAD STARVATION: Only {pending_count} pending leads (need 300+)")
if draft_stats.get("ready_to_send", 0) < 50 and drafts_created_today < 100:
    bottlenecks.append(f"🔴 DRAFT STARVATION: Only {draft_stats.get('ready_to_send', 0)} ready, {drafts_created_today} created today")
if config.EMAILS_PER_DAY_PER_MAILBOX * num_accounts < 300:
    bottlenecks.append(f"🔴 ACCOUNT CAP: {config.EMAILS_PER_DAY_PER_MAILBOX} × {num_accounts} = {config.EMAILS_PER_DAY_PER_MAILBOX * num_accounts} < 300")
if theoretical_max < 300:
    bottlenecks.append(f"🔴 COOLDOWN TOO SLOW: {avg_delay}min avg → max {theoretical_max:.0f}/day")
if not bottlenecks:
    bottlenecks.append("🟢 No obvious bottleneck — check logs for errors")
for b in bottlenecks:
    print(f"  {b}")
