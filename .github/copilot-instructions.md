# GitHub Copilot Instructions for Cold Email System

## Project Context
This is an autonomous cold email outreach system using AI-powered email generation, RocketReach for lead discovery, and multi-account sending (Zoho or Gmail via sender mode switching). The system uses MongoDB for data persistence and follows expert cold email strategies. Includes an automated bidirectional warmup system for building domain reputation.

## CRITICAL: System Architecture Rules

### MongoDB is the Source of Truth
**NEVER assume configuration comes from JSON files. ALL configuration is in MongoDB:**

- ✅ **Campaign configuration**: `campaigns` collection in MongoDB
- ✅ **Scheduler config**: `scheduler_config` collection in MongoDB  
- ✅ **Lead data**: `leads` collection in MongoDB
- ✅ **Email records**: `emails` collection in MongoDB
- ✅ **Account reputation**: `account_reputation` collection in MongoDB
- ❌ **NOT** scheduler_config.json (this is legacy/example only)

**Before making assumptions about how campaigns work:**
1. Check `db.campaigns.find()` for campaign configuration
2. Check `db.scheduler_config.find_one({'_id': 'default'})` for schedule
3. Never read scheduler_config.json as if it's the active config

### Lead Pipeline & Skip Logic
The system automatically skips leads that are:
- In do-not-contact list (DNC)
- Previously bounced (`email_invalid: true`)
- Failed email verification (MX/SMTP)
- Already contacted
- "Stealth Startup" or placeholder company names

**When implementing features that depend on lead counts:**
- Account for ~20-30% skip rate due to verification/DNC/bounces
- If target is 300 emails/day, system needs to fetch 400+ leads to account for skips

### Sender Mode & Account Routing
**The system has two sender modes controlled by `PRIMARY_SENDER_MODE` env var:**

- `zoho` (default): Uses `config.ZOHO_ACCOUNTS` (8 Zoho accounts), Zoho SMTP/IMAP
- `warmup`: Uses `config.WARMUP_ACCOUNTS` (Gmail accounts), Gmail SMTP/IMAP

**CRITICAL: Always use `config.PRODUCTION_ACCOUNTS` in pipeline code, NOT `config.ZOHO_ACCOUNTS`:**

- ✅ `config.PRODUCTION_ACCOUNTS` — dynamically resolves based on sender mode
- ✅ `config.PRODUCTION_SMTP_HOST` / `config.PRODUCTION_SMTP_PORT` — mode-aware
- ✅ `config.PRODUCTION_IMAP_HOST` / `config.PRODUCTION_IMAP_PORT` — mode-aware
- ❌ `config.ZOHO_ACCOUNTS` — only use when you explicitly need Zoho accounts (e.g., warmup_bidirectional.py which always sends FROM Zoho)

**The campaign pipeline must NEVER be disabled regardless of sender mode.** All workers (IMAP, send, pre-generator, campaign scheduler) always launch.

### Warmup System Architecture
**Bidirectional warmup (`warmup_bidirectional.py`) builds domain reputation:**

- Sends business-like emails FROM `config.ZOHO_ACCOUNTS` TO Gmail test accounts
- Monitors test account inboxes via IMAP for incoming warmup emails
- Generates contextual AI replies using Groq (llama-3.3-70b-versatile)
- Auto-moves emails from spam → inbox to train spam filters
- Runs every 4 hours as background task in `v2/scheduler.py`

**Warmup uses separate collections — never mix with campaign data:**
- `warmup_email_drafts` — pre-generated warmup templates (NOT `email_drafts`)
- `warmup_threads` — conversation threading for warmup emails
- Warmup `emails` records have `email_type: "warmup"` and NO `lead_id`

**When querying emails collection, always filter appropriately:**
- Campaign queries: add `"lead_id": {"$exists": True}` to exclude warmup records
- Warmup queries: add `"email_type": "warmup"` filter

### V2 Pipeline Architecture
**The v2 async pipeline (`main_v2.py` → `v2/scheduler.py`) is the recommended entry point:**

- `v2/scheduler.py` — Async orchestrator, launches all workers + warmup loop
- `v2/pre_generator.py` — Draft pre-generation (lazy-loads EmailGenerator, CampaignManager)
- `v2/send_worker.py` — Async SMTP sender using `config.PRODUCTION_ACCOUNTS`
- `v2/imap_worker.py` — Async IMAP reply/bounce detection with per-account timeouts
- `v2/account_pool.py` — Account rotation with reputation tracking

**Non-blocking design:** IMAP startup has 60s overall timeout + 30s per-account timeout. If IMAP fails, system continues with other workers.

## Core Development Guidelines

### 1. Virtual Environment Management
**CRITICAL: Always activate the virtual environment before running any Python scripts**

```bash
# Before running ANY Python command:
source .venv/bin/activate  # macOS/Linux
# OR
.venv\Scripts\activate     # Windows

# Then run your script:
python script_name.py
```

**When suggesting commands:**
- ✅ Always prefix with `source .venv/bin/activate &&`
- ✅ Check if .venv exists before running scripts
- ❌ Never run `python3` or `pip3` globally without venv activation

### 2. File Organization Rules

#### Test Files → `tests/` directory
- All test files MUST go in `tests/`
- Naming convention: `test_*.py` or `*_test.py`
- Helper/utility test scripts: `check_*.py`, `verify_*.py`, `debug_*.py`, `analyze_*.py`
- Never create test files in project root

#### Documentation → `docs/` directory  
- All `.md` documentation files go in `docs/`
- Exception: `README.md` stays in root
- Analysis reports, setup guides, monitoring docs → `docs/`
- Keep root clean and minimal

#### Utility Scripts → `utils/` directory
- Helper scripts, one-off migrations, fixes → `utils/`
- Data processing, cleanup scripts → `utils/`

### 3. Project Structure

```
coldemails/
├── .github/
│   └── copilot-instructions.md    # This file
├── .venv/                          # Virtual environment
├── tests/                          # All test files
│   ├── test_*.py
│   ├── check_*.py
│   ├── verify_*.py
│   └── debug_*.py
├── docs/                           # All documentation
│   ├── setup/
│   ├── monitoring/
│   └── analysis/
├── utils/                          # Utility scripts
│   ├── migrations/
│   └── fixes/
├── v2/                             # Async v2 pipeline
│   ├── scheduler.py
│   ├── pre_generator.py
│   ├── send_worker.py
│   ├── imap_worker.py
│   └── account_pool.py
├── data/                           # Data files
├── main_v2.py                      # V2 entry point (recommended)
├── main.py                         # CLI interface
├── campaign_manager.py
├── email_generator.py
├── warmup_bidirectional.py         # Warmup system
├── auto_scheduler.py               # Legacy scheduler
├── config.py                       # Config + PRODUCTION_ACCOUNTS routing
└── README.md                       # Root readme only
```

### 4. Code Quality Standards

#### Error Handling
- Always handle `None` values before calling methods like `.lower()`, `.strip()`, etc.
- Use: `(variable or "").lower()` instead of `variable.lower()`
- Add try-except blocks for external API calls
- Log errors with context

#### Database Operations
- Always use proper MongoDB queries with error handling
- Update lead/email status atomically
- Use transactions for multi-document updates
- Index frequently queried fields

#### API Integrations
- Implement rate limiting for all external APIs
- Add retry logic with exponential backoff
- Monitor quota usage proactively
- Have fallback providers ready

### 5. Logging & Monitoring

```python
# Always use structured logging
import logging
logger = logging.getLogger(__name__)

# Good:
logger.info(f"Email sent to {email}", extra={
    'lead_id': lead_id,
    'campaign_id': campaign_id,
    'from_email': from_email
})

# Bad:
print(f"Sent email to {email}")
```

### 6. Testing Requirements

- Write tests for all new features
- Test error cases, not just happy paths
- Mock external API calls (Groq, RocketReach, Zoho)
- Test database operations with fixtures
- Run tests before committing: `pytest tests/`

### 7. Deployment & Operations

#### Before Starting Scheduler
```bash
# 1. Activate venv
source .venv/bin/activate

# 2. Check dependencies
pip install -r requirements.txt

# 3. Verify MongoDB connection
python -c "from database import db; db.command('ping')"

# 4. Check API quotas
python tests/check_groq_usage.py

# 5. Start v2 pipeline (recommended)
python main_v2.py

# OR start legacy scheduler
python auto_scheduler.py
```

#### Process Management
- Use `nohup` or `screen` for background processes
- Implement auto-restart on failure (cron job or systemd)
- Monitor process health regularly
- Log all crashes for debugging

### 8. Security Best Practices

- Never commit `.env` files
- Store credentials in environment variables
- Use `.env.example` for documentation
- Rotate API keys regularly
- Sanitize email content before sending

### 9. Performance Guidelines

- Cache enrichment data (company info, personalization hooks)
- Batch database operations where possible
- Limit email sending rate (respect warm-up limits)
- Monitor API response times
- Use connection pooling for MongoDB

### 10. Common Pitfalls to Avoid

❌ **Don't:**
- Run Python scripts without activating venv
- Create test files in project root
- Call `.lower()` on potentially None values
- Ignore API rate limits
- Send emails without verification
- Skip error logging
- Hardcode configuration values

✅ **Do:**
- Always activate venv first
- Organize files by type (tests/, docs/, utils/)
- Handle None values defensively
- Monitor API quotas proactively
- Verify email deliverability before sending
- Log all errors with context
- Use config.py and environment variables

## Quick Reference Commands

```bash
# Setup
source .venv/bin/activate
pip install -r requirements.txt

# Testing
pytest tests/
python tests/test_email_flow.py

# Utilities
python tests/check_groq_usage.py
python tests/check_last_sends.py
python tests/emergency_diagnostic.py

# Operations
python main_v2.py                            # Start v2 async pipeline (recommended)
python auto_scheduler.py                     # Start legacy scheduler
tail -f scheduler.log                        # Monitor logs
ps aux | grep 'main_v2\|auto_scheduler'      # Check if running
```

## Emergency Procedures

### System Down?
1. Check process: `ps aux | grep auto_scheduler`
2. Check logs: `tail -100 scheduler.log`
3. Check API quota: `python tests/check_groq_usage.py`
4. Check MongoDB: `python tests/emergency_diagnostic.py`
5. Fix and restart: `python main_v2.py`

### No Emails Sending?
1. Verify leads exist: `python tests/check_last_sends.py`
2. Check API quota exhaustion
3. Check for code errors in logs
4. Verify sender credentials (Zoho or Gmail app passwords)
5. Check email account daily limits
6. Check PRIMARY_SENDER_MODE matches intended accounts

## AI Model Context

- **Campaign Email Generator:** Uses Ollama (qwen2.5:7b) or Groq (llama-3.3-70b-versatile) via LLM_PROVIDER env
- **Email Reviewer:** Validates quality before sending (score ≥ 70)
- **Lead Enricher:** Crawls company websites for personalization
- **ICP Classifier:** TK Kader framework for lead qualification
- **Warmup Templates/Replies:** Uses Groq explicitly (llama-3.3-70b-versatile) — not LLM_PROVIDER

## Contact & Support

- System Owner: Abdul Rehman Mehar
- Emergency: Check `docs/CRITICAL_FAILURE_ANALYSIS.md`
- Setup Guide: `docs/OLLAMA_SETUP.md`
- Monitoring: `docs/ELK_MONITORING.md`
