# Cold Email System — Improvement Plan

> **Date:** February 11, 2026
> **Status:** Approved — Implementation Strategy Finalized
> **Goal:** Parallel follow-ups + campaigns, human-like behavior, production hardening
> **Approach:** Non-disruptive parallel files in `v2/`, feature-flagged via `SCHEDULER_MODE` env var

---

## Table of Contents

1. [Architecture Overhaul: AsyncIO Parallel Execution](#1-architecture-overhaul-asyncio-parallel-execution)
2. [Zoho Configuration Fixes (Immediate)](#2-zoho-configuration-fixes-immediate)
3. [Human-Like Sending Behavior](#3-human-like-sending-behavior)
4. [Pre-Generation Pipeline (Decouple LLM from SMTP)](#4-pre-generation-pipeline-decouple-llm-from-smtp)
5. [Account Safety & Self-Healing](#5-account-safety--self-healing)
6. [Infrastructure & Docker Hardening](#6-infrastructure--docker-hardening)
7. [Observability & Alerting](#7-observability--alerting)
8. [Code Quality & Thread Safety](#8-code-quality--thread-safety)
9. [Implementation Priority & Phases](#9-implementation-priority--phases)
10. [Non-Disruptive Implementation Strategy](#10-non-disruptive-implementation-strategy)
11. [Module Dependency Map](#11-module-dependency-map)
12. [Rollback & Cutover Plan](#12-rollback--cutover-plan)

---

## 1. Architecture Overhaul: AsyncIO Parallel Execution

### Problem

Everything runs **serially in one thread**. The startup sequence alone is:

```
Phase 1 → IMAP reply check (8 accounts × 30s timeout = up to 4 min)
Phase 2 → Follow-ups (N campaigns × M leads × [12-30s Ollama + 3s SMTP] each)
Phase 3 → Missed campaigns (lead fetch + enrichment + generation + sending)
Phase 4 → Health check
Main Loop → schedule.run_pending() every 60s
```

A follow-up round with 10 leads blocks the scheduler for **3-5 hours**. Scheduled campaigns at 09:00/12:00/15:00 EST can be missed entirely because the follow-up task from 6 hours ago is still running.

### Proposed Architecture

```
┌──────────────────────────────────────────────────────┐
│                  AsyncIO Event Loop                  │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │  IMAP Worker  │  │  Send Worker  │  │  Campaign  │ │
│  │  (replies +   │  │  (processes   │  │  Creator   │ │
│  │   bounces)    │  │   send queue) │  │  (schedule)│ │
│  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘ │
│         │                 │                 │        │
│  ┌──────┴─────────────────┴─────────────────┴──────┐ │
│  │              Send Queue (asyncio.Queue)          │ │
│  │  Items: {to, subject, body, from_account, ...}   │ │
│  └──────────────────────┬──────────────────────────┘ │
│                         │                            │
│  ┌──────────────────────┴──────────────────────────┐ │
│  │         Account Pool (per-account locks)         │ │
│  │  account1: Lock + cooldown timer                 │ │
│  │  account2: Lock + cooldown timer                 │ │
│  │  ...                                             │ │
│  │  account8: Lock + cooldown timer                 │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐                  │
│  │  Pre-Gen      │  │  Scheduler   │                  │
│  │  Worker       │  │  (cron-like  │                  │
│  │  (Ollama)     │  │   triggers)  │                  │
│  └──────────────┘  └──────────────┘                  │
└──────────────────────────────────────────────────────┘
```

### Key Components

| Component | Responsibility | Concurrency |
|-----------|---------------|-------------|
| **Scheduler** | Triggers tasks at configured times (replaces `schedule` library) | Single — drives the event loop |
| **IMAP Worker** | Checks replies + bounces across 8 accounts | 8 concurrent IMAP connections (one per account) |
| **Pre-Gen Worker** | Generates emails via Ollama, places ready-to-send items in queue | 1 at a time (Ollama is single-model) |
| **Send Worker** | Pulls from send queue, acquires account lock, sends via SMTP | Up to 8 concurrent (one per account) |
| **Campaign Creator** | Fetches leads, enriches, classifies ICP, queues initial emails | 1 at a time |
| **Account Pool** | Per-account asyncio.Lock + cooldown tracking | Thread-safe via MongoDB |

### What This Enables

- ✅ Follow-ups and new campaigns run **simultaneously** (different accounts)
- ✅ IMAP checking happens **in parallel** with SMTP sending
- ✅ Ollama generation runs **while waiting** for account cooldowns
- ✅ Scheduled campaigns **never miss their time slot**
- ✅ One slow IMAP account doesn't block the other 7
- ✅ System remains responsive while processing large batches

### What This Does NOT Change

- ❌ Still **one SMTP connection per account** at a time (Zoho safety)
- ❌ Still **20-35 min cooldown** between sends from same account (human-like)
- ❌ Still **25 emails/day per mailbox** cap (deliverability choice)
- ❌ Still **9 AM - 5 PM EST** sending window (business hours)

### Key Design Decisions

1. **`asyncio` not `threading`** — Avoids GIL contention, cleaner async SMTP/IMAP, better for I/O-bound work
2. **`aiosmtplib`** replaces `smtplib` — Native async SMTP with timeout support
3. **`aioimaplib`** replaces `imaplib` — Native async IMAP
4. **`apscheduler`** replaces `schedule`** — AsyncIO-native scheduler with cron triggers, missed job handling, job persistence
5. **Send Queue** — Decouples email generation from sending; pre-generated emails wait in queue for account availability
6. **Per-account `asyncio.Lock`** — Prevents same account from having concurrent SMTP connections

### Migration Risk

| Risk | Mitigation |
|------|-----------|
| New async libraries may behave differently | Test with real Zoho accounts before deploy |
| Race conditions on MongoDB counters | `$inc` is atomic; AccountCooldown already uses upsert |
| Ollama HTTP calls need async | Use `aiohttp` instead of `requests` |
| Error in one task crashes event loop | Each task wrapped in try/except, errors logged, task restarted |

---

## 2. Zoho Configuration Fixes (Immediate)

These are **wrong right now** and should be fixed regardless of the architecture change.

### 2a. Wrong SMTP Server

**Current:** `smtp.zoho.com:587` (free/personal accounts)
**Should be:** `smtppro.zoho.com:587` (paid organization accounts with custom domains)

Both `primestrides.com` and `theabdulrehman.com` are paid organization domains. Using the free server may cause:
- Lower sending reputation
- Different rate limit treatment
- Potential "relaying disallowed" errors

**Files to change:**
- `config.py` — Default `ZOHO_SMTP_HOST`
- `stack.env` — Add `ZOHO_SMTP_HOST=smtppro.zoho.com`

### 2b. Wrong IMAP Server

**Current:** `imap.zoho.com:993` (hardcoded in `reply_detector.py`)
**Should be:** `imappro.zoho.com:993` (paid organization accounts)

**Files to change:**
- `reply_detector.py` line 79 — Change `self.imap_host = "imap.zoho.com"` to use config
- `config.py` — Add `ZOHO_IMAP_HOST` config variable

### 2c. EMAILS_PER_ACCOUNT vs EMAILS_PER_DAY_PER_MAILBOX Confusion

Two separate settings control email limits:
- `EMAILS_PER_ACCOUNT = 5` (in stack.env) — Emails before rotating to next account
- `EMAILS_PER_DAY_PER_MAILBOX = 25` — Total daily cap per account

The first setting rotates accounts after 5 emails, but with 20-35 min cooldown per account, it's effectively irrelevant. Consider removing `EMAILS_PER_ACCOUNT` and relying solely on the cooldown-based rotation that already works in `_get_next_account()`.

---

## 3. Human-Like Sending Behavior

**This is the most critical section.** Zoho can permanently block accounts that exhibit bot-like patterns. Every improvement must pass this test: *"Would a human do this?"*

### 3a. Randomized Send Timing (Jitter)

**Current:** Fixed 20-35 min cooldown between sends per account.
**Problem:** A human doesn't send emails at perfectly spaced 27-minute intervals.

**Improvement:**
- Add **Gaussian jitter** to cooldown: base ± 30% random deviation
- Occasionally skip a send window entirely (human takes a break)
- Vary the send rate throughout the day:
  - Morning (9-11 AM): Higher activity (humans are fresh)
  - Lunch (12-1 PM): Lower activity
  - Afternoon (2-4 PM): Medium activity
  - Late afternoon (4-5 PM): Winding down

```
Time-of-day multiplier:
  09:00-11:00 → 1.0x (normal delay)
  11:00-12:00 → 1.2x (slightly slower)
  12:00-13:00 → 2.0x (lunch break — half speed)
  13:00-14:00 → 1.3x (post-lunch slow)
  14:00-16:00 → 1.0x (back to normal)
  16:00-17:00 → 1.5x (winding down)
```

### 3b. Session-Based Sending (Not Continuous)

**Current:** System sends emails non-stop from 9 AM to 5 PM with only cooldown gaps.
**Problem:** No human sits at their desk sending cold emails for 8 straight hours.

**Improvement:** Implement "sending sessions":
- Each account does 2-3 sending sessions per day
- Each session: 3-7 emails over 1-2 hours
- Between sessions: 1-3 hours of silence
- Total daily emails naturally stays under 25

Example day for one account:
```
09:15 - 10:45  → Session 1: Send 5 emails (with 15-25 min gaps)
10:45 - 13:00  → Break (2h 15m)
13:20 - 14:30  → Session 2: Send 4 emails (with 15-20 min gaps)
14:30 - 15:45  → Break (1h 15m)
15:45 - 16:30  → Session 3: Send 3 emails (with 12-18 min gaps)
```

### 3c. Account Persona Consistency

**Current:** Any account can send any email. Account rotation is purely mechanical.
**Problem:** Humans have patterns — they don't switch personas randomly.

**Improvement:**
- Assign accounts to campaign types (Account 1-4 → Campaign A, Account 5-8 → Campaign B)
- Follow-ups MUST come from the original sender (already implemented ✅)
- Same account sends all emails in a single "session" (don't rotate mid-session)

### 3d. Weekend & Holiday Awareness

**Current:** `SEND_ON_WEEKENDS = false` (good ✅)
**Missing:** US holidays. No one sends cold emails on Thanksgiving, Christmas, etc.

**Improvement:** Add a holiday calendar:
- US Federal holidays (Thanksgiving, Christmas, New Year's, July 4th, Labor Day, Memorial Day)
- Optional "quiet days" (day before/after holidays)
- Configurable via `scheduler_config.json`

### 3e. Reply-Aware Sending Speed

**Current:** System sends at the same rate regardless of replies.
**Problem:** A human who gets a reply would slow down to respond, not keep blasting.

**Improvement:**
- When a reply is detected → pause that account for 30-60 min (simulate reading/responding)
- If bounce rate exceeds 5% in a day → slow down all accounts by 50%
- If spam complaint detected → pause all sending for 2 hours

---

## 4. Pre-Generation Pipeline (Decouple LLM from SMTP)

### Problem

Currently, for each lead:
1. Generate email via Ollama (12-30s) ← **LLM bottleneck**
2. Review email quality (5-10s)
3. Create SMTP connection (2-3s)
4. Send email (1-2s)
5. Close connection

Steps 1-2 block the SMTP pipeline. With 8 accounts available, 7 sit idle while Ollama generates for one lead.

### Solution: Two-Phase Pipeline

**Phase 1 — Pre-Generation (Async, runs ahead of time)**
```
For each lead needing an email:
  1. Enrich lead (crawl company website) → cache
  2. Classify ICP → cache
  3. Generate email via Ollama → store in "email_drafts" collection
  4. Review email quality → store score
  5. If quality < 70 → regenerate (up to 3x)
  6. Mark draft as "ready_to_send"
```

**Phase 2 — Sending (Async, respects all limits)**
```
Loop:
  1. Pick next "ready_to_send" draft from queue
  2. Acquire account lock
  3. Send via SMTP (2-3s)
  4. Release account lock
  5. Mark draft as "sent"
```

### Benefits

- Ollama can pre-generate **all** follow-ups during off-hours (5 PM - 9 AM)
- Sending phase is fast (2-3s per email, no LLM wait)
- If Ollama goes down during pre-gen, sending continues from existing drafts
- Quality review happens before sending window opens
- Enables true parallel sending across all 8 accounts

### New MongoDB Collection: `email_drafts`

```json
{
  "_id": ObjectId,
  "lead_id": ObjectId,
  "campaign_id": ObjectId,
  "email_type": "initial" | "followup" | "followup_new_thread",
  "followup_number": 0 | 1 | 2,
  "subject": "...",
  "body": "...",
  "html_body": "...",
  "from_account": "ali@primestrides.com",
  "in_reply_to": "...",
  "references": ["..."],
  "quality_score": 85,
  "review_passed": true,
  "status": "generating" | "ready_to_send" | "sending" | "sent" | "failed",
  "created_at": ISODate,
  "scheduled_send_at": ISODate,
  "sent_at": ISODate
}
```

---

## 5. Account Safety & Self-Healing

### 5a. Reputation Scoring Per Account

**Problem:** All accounts are treated equally. Some might have degraded reputation.
**Solution:** Track per-account reputation metrics:

```
For each account, track rolling 7-day stats:
- Bounce rate (target: < 3%)
- Reply rate (higher = healthier)
- Spam complaint rate (target: 0%)
- Emails sent / daily limit used
- Days since last block/cooldown

Reputation score = weighted combination
If score drops below threshold → auto-pause account for 24-48h
```

### 5b. Automatic Warm-Down

**Current:** If an account gets blocked, it's blocked for a fixed time.
**Improvement:** After unblocking, gradually ramp BACK up:
- Day 1 after unblock: 3 emails
- Day 2: 5 emails
- Day 3: 10 emails
- Day 4+: Normal limit

### 5c. Domain-Level Diversity

**Current:** 8 accounts across 2 domains (primestrides.com, theabdulrehman.com).
**Risk:** If Zoho blocks one domain, 4 accounts go down simultaneously.

**Improvement:**
- Track sends per domain, not just per account
- Balance sending across domains
- If one domain shows issues, shift load to the other
- Alert when domain concentration exceeds 60% of daily sends

### 5d. Recipient Domain Throttling

**Current:** No awareness of how many emails go to the same recipient domain.
**Problem:** Sending 10 cold emails to @google.com in one day looks spammy to Google.

**Improvement:**
- Max 3 emails per recipient domain per day across all accounts
- Spread emails to same domain across different hours
- Track recipient domains in MongoDB

---

## 6. Infrastructure & Docker Hardening

### 6a. Remove ELK Network Dependency

**Current:** `docker-compose.yml` declares `elk: external: true`.
**Problem:** Container won't start if ELK network doesn't exist.

**Fix:** Remove the `elk` network or make it optional:
```yaml
networks:
  app-network:
    driver: bridge
  # Remove elk network entirely
```

### 6b. Add `.dockerignore` for Secrets

**Current:** No `.dockerignore` — `stack.env` with all credentials gets copied into the Docker image.
**Fix:** Create `.dockerignore`:
```
stack.env
.env
*.env
.git
venv/
__pycache__/
tests/
docs/
data/
*.log
*.json
!requirements.txt
!scheduler_config.json
!scheduler_config.example.json
```

### 6c. Hardcoded IP Fallbacks

**Current:** `config.py` has `OLLAMA_BASE_URL` defaulting to `http://192.168.1.9:11434`.
**Problem:** This only works on your specific network.

**Fix:** Change defaults to `http://localhost:11434` in config.py. Docker containers should always set the env var explicitly (which they do via `stack.env`).

### 6d. Health Check Improvement

**Current:** Health check only pings MongoDB.
**Improvement:** Also check:
- Ollama connectivity
- At least 1 Zoho account can authenticate
- Scheduler is running (not stuck)
- Write a heartbeat timestamp to MongoDB; health check verifies it's recent

### 6e. Graceful Shutdown

**Current:** `KeyboardInterrupt` handler in main loop.
**Missing:** Docker `SIGTERM` handling. When Docker stops the container, in-flight emails may be lost.

**Improvement:**
- Catch `SIGTERM` signal
- Finish current email send (don't start new ones)
- Flush any pending logs
- Save scheduler state
- Exit cleanly within Docker's 10s stop grace period

---

## 7. Observability & Alerting

### 7a. Structured JSON Logging

**Current:** `print()` statements everywhere.
**Problem:** Logs are human-readable but not machine-parsable. Can't filter, search, or alert on specific events.

**Improvement:** Replace all `print()` with structured logging:
```python
import logging
import json

logger = logging.getLogger("coldemails")

# Instead of:
print(f"   ✉️  Sent to {to_email} (from {from_email}) [{sends_today}/{daily_limit} today]")

# Use:
logger.info("email_sent", extra={
    "to_email": to_email,
    "from_email": from_email,
    "sends_today": sends_today,
    "daily_limit": daily_limit,
    "campaign_id": campaign_id,
    "lead_id": lead_id
})
```

**Benefits:**
- Can pipe JSON logs to any monitoring system (Datadog, CloudWatch, etc.)
- Filter logs by account, campaign, lead, event type
- Calculate metrics (send rate, error rate) from logs
- Still human-readable with a formatter

### 7b. Metrics Collection

Track these metrics in MongoDB (or a time-series DB):
- Emails sent per hour / per account
- Bounce rate (rolling 24h, 7-day)
- Reply rate per campaign
- Ollama generation time (p50, p95, p99)
- SMTP connection time
- Queue depth (pre-gen drafts waiting to send)
- Account utilization (% of daily limit used)

### 7c. Alert System

**Current:** Health check prints to console. No one sees it unless watching logs.
**Improvement:** Add real alerting:
- **Critical:** All accounts blocked → send alert (email from a reserved account, or webhook)
- **Warning:** Bounce rate > 5% → slow down and alert
- **Info:** Daily summary at 5 PM EST → emails sent, replied, bounced per campaign

Options:
- Slack webhook (simplest)
- Telegram bot
- Discord webhook
- Dedicated alerting email account (separate from sending accounts)

---

## 8. Code Quality & Thread Safety

### 8a. MongoDB Connection Pooling

**Current:** Single `MongoClient()` instance shared globally.
**Good:** PyMongo's `MongoClient` is thread-safe and maintains its own connection pool.
**Action:** No change needed for MongoDB — it's already safe for concurrent access.

### 8b. Atomic Operations for Counters

**Current:** `SendingStats.increment_send()` uses `$inc` — already atomic ✅.
**Current:** `AccountCooldown.record_send()` uses `update_one` with `upsert` — already atomic ✅.
**Action:** No change needed for these specific operations.

### 8c. Race Condition: Account Selection

**Current:** `_get_next_account()` reads cooldown status, then sends. Between read and send, another task could select the same account.

**Fix:** Use MongoDB's `findOneAndUpdate` to atomically claim an account:
```python
# Atomically claim the next available account
claimed = cooldowns.find_one_and_update(
    {"account_email": {"$in": eligible}, "available_at": {"$lte": now}},
    {"$set": {"claimed_by": task_id, "claimed_at": now}},
    return_document=ReturnDocument.AFTER
)
```

### 8d. Eliminate Global State in ZohoEmailSender

**Current:** `ZohoEmailSender` tracks `_current_account_index`, `_emails_sent_current_account`, and `_connections` as instance variables.

**Problem:** In async architecture, multiple tasks sharing one `ZohoEmailSender` instance would corrupt these.

**Fix:** Move all mutable state to MongoDB (already partially done with `SendingStats` and `AccountCooldown`). The sender should be stateless — it reads state from DB, performs the send, writes state back to DB.

### 8e. Remove Dead Code

- `send_bulk_emails()` in `zoho_sender.py` — Not used anywhere, bypasses cooldown/rotation
- `connect()` method in `zoho_sender.py` — Legacy, no longer needed with fresh-connection approach
- `send_initial_emails_task()` in `auto_scheduler.py` — Sends for "draft" campaigns but campaigns are created and sent atomically in `_run_scheduled_campaign()`

### 8f. Consolidate Config Sources

**Current:** Settings come from 3 places:
1. `config.py` (env vars with defaults)
2. `scheduler_config.json` (campaign schedules, has its own `max_emails_per_day_per_mailbox: 25` and `min_delay_minutes: 7`)
3. `stack.env` (Docker env vars)

**Problem:** `scheduler_config.json` has `min_delay_minutes: 7` but `config.py` defaults to `MIN_DELAY_BETWEEN_EMAILS=20`. Which one wins? (Answer: config.py, because scheduler_config.json values for delay are not loaded anywhere — they're just notes.)

**Fix:** Single source of truth. Either:
- Remove duplicate settings from `scheduler_config.json`, OR
- Load `scheduler_config.json` settings into `config.py` at startup

---

## 9. Implementation Priority & Phases

### Phase 0: Immediate Fixes (1 hour, no architecture change)

| # | Task | Risk | Impact |
|---|------|------|--------|
| 1 | Change SMTP to `smtppro.zoho.com` | Low | Better deliverability |
| 2 | Change IMAP to `imappro.zoho.com` | Low | Better connectivity |
| 3 | Remove `elk` network from docker-compose | Low | Container starts reliably |
| 4 | Add `.dockerignore` | Low | Secrets not baked into image |
| 5 | Fix hardcoded IP in `config.py` default | Low | Portability |

### Phase 1: Pre-Generation Pipeline (1-2 days)

| # | Task | Risk | Impact |
|---|------|------|--------|
| 1 | Create `email_drafts` collection | Low | Foundation for decoupling |
| 2 | Add pre-generation logic (Ollama generates drafts ahead of time) | Medium | Eliminates LLM bottleneck during send |
| 3 | Modify send flow to pull from drafts queue | Medium | Faster sending |
| 4 | Pre-generate during off-hours (5 PM - 9 AM) | Low | Max throughput during send window |

### Phase 2: AsyncIO Core (2-3 days)

| # | Task | Risk | Impact |
|---|------|------|--------|
| 1 | Install `aiosmtplib`, `aioimaplib`, `apscheduler`, `aiohttp` | Low | Dependencies |
| 2 | Create async `ZohoSenderAsync` class | High | Core sending change |
| 3 | Create async `ReplyDetectorAsync` class | Medium | Parallel IMAP |
| 4 | Create async `OllamaClient` (aiohttp) | Medium | Async generation |
| 5 | Build Account Pool with per-account `asyncio.Lock` | Medium | Prevents concurrent same-account sends |
| 6 | Build Send Queue (`asyncio.Queue`) | Low | Decouples gen from send |
| 7 | Rewrite `auto_scheduler.py` with `apscheduler` + async tasks | High | Core orchestration change |
| 8 | Graceful shutdown (SIGTERM handler) | Low | Clean Docker stops |

### Phase 3: Human-Like Behavior (1-2 days)

| # | Task | Risk | Impact |
|---|------|------|--------|
| 1 | Session-based sending (2-3 sessions/day/account) | Medium | Most human-like improvement |
| 2 | Time-of-day send rate variation | Low | Natural patterns |
| 3 | Gaussian jitter on cooldowns | Low | Avoid machine-like precision |
| 4 | Reply-aware pausing | Low | React to engagement |
| 5 | Holiday calendar | Low | Don't send on Thanksgiving |
| 6 | Recipient domain throttling | Medium | Avoid domain-level blocks |

### Phase 4: Safety & Observability (1-2 days)

| # | Task | Risk | Impact |
|---|------|------|--------|
| 1 | Per-account reputation scoring | Medium | Auto-pause degraded accounts |
| 2 | Auto warm-down after unblock | Low | Safer recovery |
| 3 | Domain-level send balancing | Low | Reduce domain risk |
| 4 | Structured JSON logging | Medium | Operability |
| 5 | Alerting (Slack/Telegram webhook) | Low | Know when things break |
| 6 | Daily summary reports | Low | Business visibility |

### Phase 5: Code Cleanup

| # | Task | Risk | Impact |
|---|------|------|--------|
| 1 | Atomic account claiming (findOneAndUpdate) | Low | Race condition fix |
| 2 | Stateless ZohoEmailSender | Medium | Thread safety |
| 3 | Remove dead code | Low | Cleanliness |
| 4 | Consolidate config sources | Low | Less confusion |
| 5 | Move remaining root test files to `tests/` | Low | Project hygiene |

---

## Current vs. Improved — Side-by-Side

| Aspect | Current | After All Phases |
|--------|---------|-----------------|
| **Task execution** | Serial (one thread) | Parallel (AsyncIO event loop) |
| **Follow-ups block campaigns?** | Yes — for hours | No — independent tasks |
| **IMAP checks block sending?** | Yes — up to 4 min | No — separate async worker |
| **Ollama blocks SMTP?** | Yes — 12-30s per email | No — pre-generated drafts |
| **Sending pattern** | Machine-like 27-min intervals | Human-like sessions with jitter |
| **Account selection** | Round-robin (race-prone) | Atomic claim from MongoDB |
| **SMTP server** | `smtp.zoho.com` (free) | `smtppro.zoho.com` (paid) |
| **IMAP server** | `imap.zoho.com` (free) | `imappro.zoho.com` (paid) |
| **Error visibility** | print() to stdout | Structured JSON + alerts |
| **Account health** | Block/unblock binary | Reputation scoring + warm-down |
| **Recipient diversity** | No awareness | Domain-level throttling |
| **Holiday handling** | None | US holiday calendar |
| **Docker secrets** | Baked into image | .dockerignore excludes them |
| **Shutdown** | Abrupt on container stop | Graceful SIGTERM handling |

---

## Questions for Your Review

1. **Phase 0 fixes** — Should I apply these immediately? They're safe, independent changes.
2. **Pre-generation timing** — Do you want Ollama to pre-generate during off-hours only, or also fill gaps during the day?
3. **Session pattern** — Do the 2-3 sessions/day/account numbers feel right, or should it be more/fewer?
4. **Alerting channel** — Slack, Telegram, Discord, or email for alerts?
5. **Domain throttling** — Is 3 emails/recipient domain/day the right cap?
6. **Which phase to start with?** — I recommend Phase 0 → Phase 1 → Phase 3 → Phase 2 → Phase 4 (get immediate fixes + pre-gen pipeline + human behavior before the big async rewrite).

---

## 10. Non-Disruptive Implementation Strategy

> **Approved:** February 11, 2026
> **Core Principle:** Create NEW files alongside old ones. Old system keeps running. A single env var `SCHEDULER_MODE=async` switches to the new one.

### 10a. Parallel File Structure

All new code lives in a `v2/` directory. **Zero existing files are modified** (except Phase 0 config fixes). The old system is never touched.

```
coldemails/
├── auto_scheduler.py          ← UNTOUCHED (legacy entry point)
├── campaign_manager.py        ← UNTOUCHED
├── zoho_sender.py             ← UNTOUCHED
├── reply_detector.py          ← UNTOUCHED (except IMAP host from config)
├── config.py                  ← MINOR additions (new config vars)
├── database.py                ← MINOR additions (new collections)
│
├── v2/                        ← ALL NEW CODE GOES HERE
│   ├── __init__.py
│   ├── scheduler.py           ← New async entry point (replaces auto_scheduler.py)
│   ├── send_worker.py         ← Async SMTP sender (wraps zoho_sender logic)
│   ├── imap_worker.py         ← Async IMAP checker (wraps reply_detector logic)
│   ├── pre_generator.py       ← Drafts pipeline (Ollama pre-gen)
│   ├── account_pool.py        ← Per-account locks + reputation
│   ├── human_behavior.py      ← Sessions, jitter, holidays, domain throttle
│   └── alerts.py              ← Webhook alerting
│
├── main_v2.py                 ← New entry point: python main_v2.py
├── Dockerfile                 ← Modify CMD based on SCHEDULER_MODE
```

### 10b. How It Works Without Disturbing Anything

1. **Old system stays 100% intact.** Not a single line changes in `auto_scheduler.py`, `campaign_manager.py`, or `zoho_sender.py`. If the new code fails, revert to old by changing one env var.

2. **New modules REUSE existing logic, not replace it.** For example, `v2/send_worker.py` doesn't rewrite SMTP logic — it wraps `aiosmtplib` with the same headers, Message-ID, threading, and error handling that `zoho_sender.py` already does. Same for `v2/imap_worker.py` wrapping `reply_detector.py`'s bounce/reply patterns.

3. **Shared MongoDB is the bridge.** Both old and new systems read/write the same collections (`emails`, `leads`, `campaigns`, `sending_stats`, `account_cooldowns`, `blocked_accounts`). The new `email_drafts` collection is additive — the old system simply ignores it.

4. **Config additions are backward-compatible.** New env vars like `SCHEDULER_MODE`, `ZOHO_IMAP_HOST`, `ALERT_WEBHOOK_URL` all have defaults that make the old system behave identically if they're absent.

5. **Docker switching is a one-line change:**

```dockerfile
# In Dockerfile — dynamic entry point
CMD ["sh", "-c", "if [ \"$SCHEDULER_MODE\" = 'async' ]; then python main_v2.py; else python auto_scheduler.py; fi"]
```

### 10c. The CampaignManager Problem — Solved With `asyncio.to_thread()`

`campaign_manager.py` is a 1,400-line monolith that does lead fetching, enrichment, ICP classification, email generation, review, AND sending — all in tight serial loops. Rewriting it is too risky.

**Solution:** The v2 async scheduler runs it in a thread pool:

```python
# In v2/scheduler.py
async def run_campaign_task(self, config):
    # Run the synchronous CampaignManager in a thread pool
    # This doesn't block the async event loop
    result = await asyncio.to_thread(
        self.manager.run_autonomous_campaign,
        max_leads=config['max_leads'],
        dry_run=False
    )
    return result
```

`campaign_manager.py` stays 100% synchronous. It runs in a background thread. The async event loop continues processing IMAP checks, follow-up sends, and pre-generation **in parallel**. This is the **least disruptive** approach.

The ONLY thing that changes: campaign creation no longer blocks follow-ups and reply checking. They run concurrently.

### 10d. Phase-by-Phase — What Changes Where

#### Phase 0: Immediate Fixes (touch existing files, safe changes only)

| Change | File | Risk |
|--------|------|------|
| SMTP default → `smtppro.zoho.com` | `config.py` | None — env var overrides |
| Add `ZOHO_IMAP_HOST` config var | `config.py` (add 2 lines) | None — default is current value |
| Use `config.ZOHO_IMAP_HOST` instead of hardcoded | `reply_detector.py` line 79 | None — same value unless env changes |
| OLLAMA default → `localhost` | `config.py` | None — Docker uses env var |
| Remove `elk` network | `docker-compose.yml` | None — wasn't working |
| Create `.dockerignore` | New file | None — only affects builds |
| Add `ZOHO_SMTP_HOST=smtppro.zoho.com` | `stack.env` | Low — correct server for paid plan |
| Add `ZOHO_IMAP_HOST=imappro.zoho.com` | `stack.env` | Low — correct server for paid plan |

**Nothing behavioral changes.** System does exactly what it did before, just connecting to the correct paid-plan servers.

#### Phase 1: Pre-Generation Pipeline (new files only)

| New File | Purpose |
|----------|---------|
| `v2/__init__.py` | Package marker |
| `v2/pre_generator.py` | Pulls leads needing emails from MongoDB, calls existing `EmailGenerator` + `EmailReviewer`, stores drafts in `email_drafts` collection |
| `database.py` additions | Add `EmailDraft` class + `email_drafts` collection (~80 lines) |

**Key detail:** `pre_generator.py` imports and uses the existing `EmailGenerator` and `EmailReviewer` classes directly. No duplication. It just orchestrates them differently — generate first, send later.

The old system doesn't know about `email_drafts` and doesn't care. Pre-gen can run as a standalone script during off-hours: `python -m v2.pre_generator`.

#### Phase 2: AsyncIO Core (new files only)

| New File | Purpose |
|----------|---------|
| `v2/scheduler.py` | `apscheduler` async scheduler — replaces `schedule` library. Runs IMAP worker, send worker, pre-gen worker, campaign creator as concurrent async tasks |
| `v2/send_worker.py` | `aiosmtplib`-based sender. Reads from `email_drafts` queue. Per-account `asyncio.Lock`. Same email format/headers as `zoho_sender.py` |
| `v2/imap_worker.py` | `aioimaplib`-based reply/bounce checker. Same regex patterns as `reply_detector.py`. Checks all 8 accounts concurrently |
| `v2/account_pool.py` | Account management — locks, cooldowns, reputation scoring. Wraps existing `SendingStats`, `AccountCooldown`, `BlockedAccounts` from `database.py` |
| `main_v2.py` | Entry point — `python main_v2.py` |

**Key detail:** `v2/send_worker.py` reads the **same** MongoDB collections (`sending_stats`, `account_cooldowns`, `blocked_accounts`) as the old `zoho_sender.py`. The old warmup logic, daily limits, and blocked account tracking all carry over automatically because it's the same data.

**Campaign creation still uses `CampaignManager`** — the v2 scheduler calls `self.manager.run_autonomous_campaign()` exactly like the old scheduler does. The difference is the v2 scheduler runs it inside `asyncio.to_thread()` so it doesn't block other tasks.

#### Phase 3: Human-Like Behavior (new file, config additions)

| New File | Purpose |
|----------|---------|
| `v2/human_behavior.py` | Session planner, jitter calculator, holiday calendar, time-of-day multiplier, recipient domain throttling |

This is consumed by `v2/send_worker.py` and `v2/account_pool.py`. It doesn't touch any old code.

New config vars (all with safe defaults):
- `SESSION_COUNT_PER_DAY=3`
- `SESSION_EMAILS_MIN=3`, `SESSION_EMAILS_MAX=7`
- `ENABLE_JITTER=true`
- `ENABLE_HOLIDAY_CALENDAR=true`
- `MAX_EMAILS_PER_RECIPIENT_DOMAIN=3`

#### Phase 4: Safety & Observability (new file, config additions)

| New File | Purpose |
|----------|---------|
| `v2/alerts.py` | Webhook alerts (Slack/Telegram/Discord), daily summary |

New config vars:
- `ALERT_WEBHOOK_URL` (Slack/Discord webhook)
- `ALERT_CHANNEL=slack` (or `telegram`, `discord`)
- `DAILY_SUMMARY_ENABLED=true`

### 10e. New Dependencies

| New Dependency | Purpose | Required Phase |
|----------------|---------|----------------|
| `aiosmtplib` | Async SMTP | Phase 2 |
| `aioimaplib` | Async IMAP | Phase 2 |
| `apscheduler>=4.0` | Async cron scheduler | Phase 2 |
| `aiohttp` | Async HTTP (Ollama calls) | Phase 1 |

These get added to `requirements.txt` — they don't conflict with existing sync libraries. Both `smtplib` and `aiosmtplib` can coexist.

### 10f. Testing Strategy

1. **Phase 0** — Deploy to production directly. These are config-level changes.
2. **Phase 1** — Run `python -m v2.pre_generator` manually on the host. Verify drafts appear in MongoDB. Old system ignores them.
3. **Phase 2** — Run `python main_v2.py` **locally** (not in Docker) against the same MongoDB. Watch it process the pre-generated drafts. Old system stays in Docker. Both can coexist because they share MongoDB and respect the same account cooldowns.
4. **Phase 3-4** — Layer on top of Phase 2. Test locally first.
5. **Cutover** — Set `SCHEDULER_MODE=async` in `stack.env`, rebuild Docker image, deploy. If anything breaks, set `SCHEDULER_MODE=legacy`, redeploy.

---

## 11. Module Dependency Map

Complete dependency graph of the current system. This map was used to design the non-disruptive implementation strategy.

### 11a. Entry Point Chain

```
Dockerfile
  └── CMD: python auto_scheduler.py

auto_scheduler.py (ENTRY POINT — 702 lines)
  ├── CampaignManager  ← campaign_manager.py (1,403 lines)
  │   ├── RocketReachClient        ← rocketreach_client.py
  │   ├── EmailGenerator           ← email_generator.py (2,744 lines)
  │   │   └── primestrides_context   (COMPANY_CONTEXT, ICP_TEMPLATES, CASE_STUDIES)
  │   ├── EmailReviewer            ← email_reviewer.py (1,438 lines)
  │   │   └── email_generator        (humanize_email, get_llm_client, etc.)
  │   ├── EmailVerifier            ← email_verifier.py
  │   ├── ZohoEmailSender          ← zoho_sender.py (761 lines)
  │   ├── lead_enricher              (enrich_lead_sync, get_enrichment_for_email)
  │   │   └── email_generator        (get_llm_client, etc.)
  │   ├── database                   (Lead, Email, Campaign, DoNotContact, etc.)
  │   └── config
  ├── EmailGenerator
  ├── ReplyDetector  ← reply_detector.py (538 lines)
  │   ├── database                   (Email, Lead, Campaign, DoNotContact)
  │   └── config
  ├── database                       (Campaign, Email, campaigns_collection)
  └── config
```

### 11b. Key Coupling Points

| Coupling | Location | Impact on v2 |
|----------|----------|--------------|
| `CampaignManager.__init__()` directly creates `ZohoEmailSender()`, `EmailGenerator()`, `EmailReviewer()`, `RocketReachClient()` | `campaign_manager.py` lines 30-55 | v2 wraps entire `CampaignManager` in `asyncio.to_thread()` — no need to decouple |
| `auto_scheduler.AutoScheduler.__init__()` creates `CampaignManager()`, `EmailGenerator()`, `ReplyDetector()` | `auto_scheduler.py` lines 1-30 | v2 has its own scheduler — doesn't touch this |
| `self.email_sender.send_email()` used in 3 places | `campaign_manager.py` lines 845, 1117, 1326 | v2's `send_worker.py` replaces these with `aiosmtplib` |
| `self.email_sender.disconnect()` in 2 places | `campaign_manager.py` | v2 uses fresh connections (no disconnect needed) |
| `self.email_sender.accounts` accessed | `campaign_manager.py` line 1098 | For follow-up sender matching — v2 reads from config directly |
| `self.imap_host = "imap.zoho.com"` hardcoded | `reply_detector.py` line 79 | Phase 0 fix: use `config.ZOHO_IMAP_HOST` |

### 11c. MongoDB Collections (Shared Between v1 and v2)

| Collection | Used By | Thread-Safe? |
|------------|---------|-------------|
| `leads` | campaign_manager, lead_enricher, reply_detector | ✅ |
| `emails` | campaign_manager, zoho_sender, reply_detector | ✅ |
| `campaigns` | campaign_manager, auto_scheduler, reply_detector | ✅ |
| `sending_stats` | zoho_sender (`$inc` atomic) | ✅ |
| `account_cooldowns` | zoho_sender (upsert-based) | ✅ |
| `blocked_accounts` | zoho_sender (upsert-based) | ✅ |
| `do_not_contact` | campaign_manager, reply_detector | ✅ |
| `email_drafts` | **NEW** — v2 only (old system ignores) | ✅ |

### 11d. Instance-Level Mutable State (Must Be Eliminated for v2)

| State Variable | Class | Current Location | v2 Approach |
|----------------|-------|-----------------|-------------|
| `_current_account_index` | `ZohoEmailSender` | Instance var | MongoDB atomic claim (`findOneAndUpdate`) |
| `_emails_sent_current_account` | `ZohoEmailSender` | Instance var | Read from `sending_stats` collection |
| `_connections` dict | `ZohoEmailSender` | Instance var | Fresh connections per send (already done) |
| `_rate_limit_tracker` | `ZohoEmailSender` | Instance var | MongoDB `account_cooldowns` (already there) |

---

## 12. Rollback & Cutover Plan

### 12a. Rollback at Any Phase

At every phase, rollback is:

```bash
# In stack.env
SCHEDULER_MODE=legacy    # ← one line change

# Redeploy
docker-compose down && docker-compose up -d --build
```

The old `auto_scheduler.py` runs exactly as before. The `v2/` directory sits there doing nothing.

### 12b. Cutover Procedure

```bash
# 1. Verify v2 works locally
SCHEDULER_MODE=async python main_v2.py  # test locally against MongoDB

# 2. Stop old system
docker-compose down

# 3. Set mode in stack.env
SCHEDULER_MODE=async

# 4. Build and deploy
docker-compose up -d --build

# 5. Monitor logs for 30 minutes
docker logs -f autonomouscoldemails

# 6. If anything breaks — instant rollback
# Change SCHEDULER_MODE=legacy in stack.env
# docker-compose down && docker-compose up -d --build
```

### 12c. Coexistence During Testing

During Phase 1-2 testing, **both systems can run simultaneously**:

- Old system runs in Docker (production)
- New v2 runs locally on the host (testing)
- Both read/write the same MongoDB
- Both respect the same `account_cooldowns` and `sending_stats`
- No double-sending because account locks are in MongoDB

This allows safe testing with real data without stopping production.

### 12d. Phase Completion Checklist

| Phase | Completion Criteria | Rollback Possible? |
|-------|--------------------|-----------|
| Phase 0 | SMTP/IMAP connects to `*pro.zoho.com`, `.dockerignore` exists | ✅ Revert env vars |
| Phase 1 | `email_drafts` collection populated, drafts quality verified | ✅ Old system ignores drafts |
| Phase 2 | v2 scheduler sends emails from drafts, IMAP checks work async | ✅ Switch `SCHEDULER_MODE=legacy` |
| Phase 3 | Session-based sending active, jitter applied, holidays respected | ✅ Switch `SCHEDULER_MODE=legacy` |
| Phase 4 | Alerts firing to Slack/Telegram, daily summary sent, reputation tracked | ✅ Switch `SCHEDULER_MODE=legacy` |
| Phase 5 | Dead code removed, config consolidated, root test files moved | ⚠️ Code cleanup — no rollback needed |
