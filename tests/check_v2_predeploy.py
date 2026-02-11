#!/usr/bin/env python3
"""
V2 Pre-Deployment Verification Script

Run this BEFORE switching to v2 in production. It validates:
1. MongoDB connectivity
2. SchedulerConfig campaigns have required fields (name, autonomous, etc.)
3. All Zoho accounts can authenticate (SMTP + IMAP)
4. Python async deps are installed
5. email_drafts collection is accessible
6. Account reputation collection is accessible
7. v2 modules all import cleanly
8. Dry-run of the scheduler startup phase (no sends)

Usage:
    source venv/bin/activate
    python tests/check_v2_predeploy.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Formatting helpers ───────────────────────────────────────────────

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

passed = 0
failed = 0
warnings = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  {GREEN}✅ {msg}{RESET}")


def fail(msg):
    global failed
    failed += 1
    print(f"  {RED}❌ {msg}{RESET}")


def warn(msg):
    global warnings
    warnings += 1
    print(f"  {YELLOW}⚠️  {msg}{RESET}")


def section(title):
    print(f"\n{BOLD}{'─' * 50}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'─' * 50}{RESET}")


# ── 1. MongoDB Connectivity ─────────────────────────────────────────

section("1. MongoDB Connectivity")

try:
    from database import db
    result = db.command("ping")
    if result.get("ok") == 1.0:
        ok("MongoDB ping successful")
    else:
        fail(f"MongoDB ping returned: {result}")
except Exception as e:
    fail(f"MongoDB connection failed: {e}")
    print(f"\n{RED}Cannot continue without MongoDB. Exiting.{RESET}")
    sys.exit(1)


# ── 2. Config Validation ────────────────────────────────────────────

section("2. Config Validation")

try:
    import config

    if config.DATABASE_URL:
        ok(f"DATABASE_URL set")
    else:
        fail("DATABASE_URL not set")

    if config.ZOHO_ACCOUNTS and len(config.ZOHO_ACCOUNTS) > 0:
        ok(f"{len(config.ZOHO_ACCOUNTS)} Zoho accounts loaded")
    else:
        fail("No Zoho accounts configured")

    if config.ZOHO_SMTP_HOST:
        ok(f"SMTP host: {config.ZOHO_SMTP_HOST}:{config.ZOHO_SMTP_PORT}")
    else:
        fail("ZOHO_SMTP_HOST not set")

    if config.ZOHO_IMAP_HOST:
        ok(f"IMAP host: {config.ZOHO_IMAP_HOST}:{config.ZOHO_IMAP_PORT}")
    else:
        fail("ZOHO_IMAP_HOST not set")

    ok(f"LLM provider: {config.LLM_PROVIDER}")
    ok(f"Timezone: {config.TARGET_TIMEZONE}")
    ok(f"Sending hours: {config.SENDING_HOUR_START}:00 - {config.SENDING_HOUR_END}:00")
    ok(f"Daily limit/mailbox: {config.EMAILS_PER_DAY_PER_MAILBOX}")
    ok(f"Warmup: {'ON' if config.WARMUP_ENABLED else 'OFF'}")

except Exception as e:
    fail(f"Config import failed: {e}")


# ── 3. SchedulerConfig (DB campaigns) ───────────────────────────────

section("3. SchedulerConfig — DB Campaign Schema")

try:
    from database import SchedulerConfig

    sched_config = SchedulerConfig.get_config()
    campaigns = sched_config.get("scheduled_campaigns", [])

    if not campaigns:
        fail("No scheduled_campaigns in DB config")
    else:
        ok(f"Found {len(campaigns)} scheduled campaigns in DB")

    enabled_count = 0
    schema_issues = []

    required_fields = ["name", "schedule_time", "days"]
    recommended_fields = ["autonomous", "max_leads", "enabled", "description"]

    for i, camp in enumerate(campaigns):
        # Check required fields
        for field in required_fields:
            if field not in camp:
                schema_issues.append(f"Campaign #{i} missing required field '{field}': {camp.get('description', camp.get('name', 'unnamed'))[:50]}")

        # Check recommended fields
        for field in recommended_fields:
            if field not in camp:
                schema_issues.append(f"Campaign #{i} missing recommended field '{field}': {camp.get('name', 'unnamed')}")

        if camp.get("enabled", False):
            enabled_count += 1

        # Validate name won't cause KeyError in scheduler
        if "name" in camp:
            name = camp["name"]
            if not isinstance(name, str) or not name.strip():
                schema_issues.append(f"Campaign #{i} has empty/invalid 'name'")

        # Validate days are lowercase strings
        days = camp.get("days", [])
        valid_days = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
        for d in days:
            if d.lower() not in valid_days:
                schema_issues.append(f"Campaign #{i} '{camp.get('name', '?')}' has invalid day: {d}")

        # Validate schedule_time format HH:MM
        stime = camp.get("schedule_time", "")
        if stime and (":" not in stime or len(stime) != 5):
            schema_issues.append(f"Campaign #{i} '{camp.get('name', '?')}' has invalid schedule_time: {stime}")

    if schema_issues:
        for issue in schema_issues:
            fail(issue)
    else:
        ok("All campaigns have required schema fields")

    if enabled_count > 0:
        ok(f"{enabled_count} campaigns are enabled")
    else:
        warn("No campaigns are enabled — v2 won't run any campaigns until you enable some")

    # Show enabled campaigns
    print(f"\n  {BOLD}Enabled campaigns:{RESET}")
    for camp in campaigns:
        if camp.get("enabled", False):
            name = camp.get("name", "unnamed")
            auto = "autonomous" if camp.get("autonomous", False) else "followup-only"
            days = ", ".join(camp.get("days", []))
            stime = camp.get("schedule_time", "?")
            leads = camp.get("max_leads", "?")
            print(f"    • {name} ({auto}) — {stime} on {days}, max {leads} leads")

except Exception as e:
    fail(f"SchedulerConfig check failed: {e}")


# ── 4. Python Async Dependencies ────────────────────────────────────

section("4. Async Dependencies")

try:
    import aiosmtplib
    ok(f"aiosmtplib {aiosmtplib.__version__}")
except ImportError:
    fail("aiosmtplib not installed — run: pip install aiosmtplib")

try:
    import aiohttp
    ok(f"aiohttp {aiohttp.__version__}")
except ImportError:
    warn("aiohttp not installed — alerts will be disabled. Run: pip install aiohttp")

try:
    import pytz
    ok("pytz available")
except ImportError:
    fail("pytz not installed")

try:
    import asyncio
    ok("asyncio available")
except ImportError:
    fail("asyncio not available (Python too old?)")


# ── 5. V2 Module Imports ────────────────────────────────────────────

section("5. V2 Module Imports")

modules = [
    "v2",
    "v2.human_behavior",
    "v2.account_pool",
    "v2.pre_generator",
    "v2.send_worker",
    "v2.imap_worker",
    "v2.alerts",
    "v2.scheduler",
]

for mod in modules:
    try:
        __import__(mod)
        ok(f"import {mod}")
    except Exception as e:
        fail(f"import {mod} — {e}")


# ── 6. MongoDB Collections ──────────────────────────────────────────

section("6. MongoDB Collections")

required_collections = [
    "emails",
    "leads",
    "campaigns",
    "sending_stats",
    "account_cooldowns",
    "blocked_accounts",
    "scheduler_config",
]

v2_collections = [
    "email_drafts",
    "account_reputation",
    "heartbeat",
]

existing = db.list_collection_names()

for coll in required_collections:
    if coll in existing:
        count = db[coll].estimated_document_count()
        ok(f"{coll}: {count:,} documents")
    else:
        fail(f"{coll}: collection missing")

for coll in v2_collections:
    if coll in existing:
        count = db[coll].estimated_document_count()
        ok(f"{coll} (v2): {count:,} documents")
    else:
        # These get created on first use, so just a warning
        warn(f"{coll} (v2): will be created on first run")


# ── 7. Zoho Account Authentication ──────────────────────────────────

section("7. Zoho Account Authentication (SMTP)")

print(f"  Testing SMTP connections to {config.ZOHO_SMTP_HOST}:{config.ZOHO_SMTP_PORT}...")

import smtplib

for acct in config.ZOHO_ACCOUNTS:
    email = acct["email"]
    try:
        smtp = smtplib.SMTP(config.ZOHO_SMTP_HOST, config.ZOHO_SMTP_PORT, timeout=15)
        smtp.starttls()
        smtp.login(email, acct["password"])
        smtp.quit()
        ok(f"SMTP auth: {email}")
    except smtplib.SMTPAuthenticationError as e:
        fail(f"SMTP auth FAILED: {email} — {e}")
    except (TimeoutError, OSError) as e:
        warn(f"SMTP timeout: {email} — {e}")
    except Exception as e:
        warn(f"SMTP error: {email} — {e}")

section("8. Zoho Account Authentication (IMAP)")

print(f"  Testing IMAP connections to {config.ZOHO_IMAP_HOST}:{config.ZOHO_IMAP_PORT}...")

import imaplib

for acct in config.ZOHO_ACCOUNTS:
    email = acct["email"]
    try:
        imap = imaplib.IMAP4_SSL(config.ZOHO_IMAP_HOST, config.ZOHO_IMAP_PORT, timeout=15)
        imap.login(email, acct["password"])
        imap.logout()
        ok(f"IMAP auth: {email}")
    except imaplib.IMAP4.error as e:
        fail(f"IMAP auth FAILED: {email} — {e}")
    except (TimeoutError, OSError) as e:
        warn(f"IMAP timeout: {email} — {e}")
    except Exception as e:
        warn(f"IMAP error: {email} — {e}")


# ── 9. Account Health Check ─────────────────────────────────────────

section("9. Account Health (Blocks, Reputation, Stats)")

from database import BlockedAccounts, SendingStats

for acct in config.ZOHO_ACCOUNTS:
    email = acct["email"]
    blocked = BlockedAccounts.is_blocked(email)
    sends = SendingStats.get_sends_today(email)

    status_parts = []
    if blocked:
        status_parts.append(f"{RED}BLOCKED{RESET}")
    else:
        status_parts.append(f"{GREEN}OK{RESET}")
    status_parts.append(f"{sends} sent today")

    # Check reputation
    rep_doc = db["account_reputation"].find_one({"account_email": email})
    if rep_doc:
        score = rep_doc.get("score", "?")
        if isinstance(score, (int, float)) and score < 60:
            status_parts.append(f"{RED}rep={score}{RESET}")
        elif isinstance(score, (int, float)) and score < 80:
            status_parts.append(f"{YELLOW}rep={score}{RESET}")
        else:
            status_parts.append(f"rep={score}")
    else:
        status_parts.append("rep=new")

    print(f"  {'❌' if blocked else '✅'} {email}: {' | '.join(status_parts)}")
    if blocked:
        failed += 1
    else:
        passed += 1


# ── 10. Legacy Scheduler Conflict Check ─────────────────────────────

section("10. Legacy Scheduler Conflict Check")

import subprocess

try:
    result = subprocess.run(
        ["pgrep", "-f", "auto_scheduler"],
        capture_output=True, text=True, timeout=5
    )
    if result.returncode == 0:
        pids = result.stdout.strip().split("\n")
        warn(f"Legacy auto_scheduler.py is running (PIDs: {', '.join(pids)})")
        warn("You MUST stop it before starting v2: pkill -f auto_scheduler")
    else:
        ok("Legacy auto_scheduler.py is NOT running")
except Exception:
    warn("Could not check for legacy scheduler process")


# ── 11. Dry-Run: v2 Startup Phase ───────────────────────────────────

section("11. Dry-Run: V2 Startup Phase (read-only)")

try:
    import asyncio
    from v2.account_pool import AccountPool, AccountReputation
    from v2.pre_generator import EmailDraft
    from v2.human_behavior import is_holiday, plan_daily_sessions
    from v2.imap_worker import ImapWorker

    # Holiday check
    is_hol, hol_name = is_holiday()
    if is_hol:
        warn(f"Today is {hol_name} — sending will be paused")
    else:
        ok("Not a holiday today")

    # Plan sessions (doesn't touch DB)
    sessions = plan_daily_sessions(
        session_count=3,
        daily_limit=config.EMAILS_PER_DAY_PER_MAILBOX
    )
    ok(f"Session planner works: {len(sessions)} sessions planned")
    for s in sessions:
        print(f"    • {s}")

    # AccountPool init
    pool = AccountPool()
    ok(f"AccountPool initialized: {len(pool.accounts)} accounts")

    # Account statuses
    for status in pool.get_all_status():
        remaining = status["remaining"]
        label = f"{status['email']}: {status['sends_today']}/{status['daily_limit']} sent, {remaining} remaining"
        if status["blocked"]:
            warn(f"{label} — BLOCKED")
        else:
            ok(label)

    # Draft queue
    draft_stats = EmailDraft.get_stats()
    ready = EmailDraft.get_ready_count()
    ok(f"Draft queue: {draft_stats}, ready_to_send={ready}")

    # Clean up expired blocks
    BlockedAccounts.cleanup_expired()
    ok("Expired blocks cleaned")

    # Stale claims released
    EmailDraft.cleanup_stale_claimed()
    ok("Stale claimed drafts released")

except Exception as e:
    fail(f"Dry-run startup failed: {e}")
    import traceback
    traceback.print_exc()


# ── Summary ──────────────────────────────────────────────────────────

section("SUMMARY")

total = passed + failed + warnings
print(f"""
  {GREEN}Passed:   {passed}{RESET}
  {RED}Failed:   {failed}{RESET}
  {YELLOW}Warnings: {warnings}{RESET}
  Total:    {total}
""")

if failed == 0:
    print(f"{GREEN}{BOLD}  ✅ ALL CHECKS PASSED — Ready to deploy v2!{RESET}")
    print(f"""
  {BOLD}Deployment steps:{RESET}
  1. Stop legacy scheduler:  pkill -f auto_scheduler
  2. Set env var:            export SCHEDULER_MODE=async
  3. Start v2:               python main_v2.py
     (or rebuild Docker:     docker compose up -d --build)
  4. Monitor logs:           tail -f v2_scheduler.log
  5. Verify heartbeat:       python -c "from database import db; print(db.heartbeat.find_one({{'_id': 'v2_scheduler'}}))"
""")
elif failed <= 3:
    print(f"{YELLOW}{BOLD}  ⚠️  MOSTLY READY — Fix {failed} issue(s) above before deploying.{RESET}")
else:
    print(f"{RED}{BOLD}  ❌ NOT READY — Fix {failed} issues above before deploying.{RESET}")

sys.exit(0 if failed == 0 else 1)
