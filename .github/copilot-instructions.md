# GitHub Copilot Instructions for Cold Email System

## Project Context
This is an autonomous cold email outreach system using AI-powered email generation, RocketReach for lead discovery, and multi-account Zoho for sending. The system uses MongoDB for data persistence and follows expert cold email strategies.

## Core Development Guidelines

### 1. Virtual Environment Management
**CRITICAL: Always activate the virtual environment before running any Python scripts**

```bash
# Before running ANY Python command:
source venv/bin/activate  # macOS/Linux
# OR
venv\Scripts\activate     # Windows

# Then run your script:
python script_name.py
```

**When suggesting commands:**
- ✅ Always prefix with `source venv/bin/activate &&`
- ✅ Check if venv exists before running scripts
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
├── venv/                           # Virtual environment
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
├── data/                           # Data files
├── main.py                         # Core application files
├── campaign_manager.py
├── email_generator.py
├── auto_scheduler.py
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
source venv/bin/activate

# 2. Check dependencies
pip install -r requirements.txt

# 3. Verify MongoDB connection
python -c "from database import db; db.command('ping')"

# 4. Check API quotas
python tests/check_groq_usage.py

# 5. Start scheduler
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
source venv/bin/activate
pip install -r requirements.txt

# Testing
pytest tests/
python tests/test_email_flow.py

# Utilities
python tests/check_groq_usage.py
python tests/check_last_sends.py
python tests/emergency_diagnostic.py

# Operations
python auto_scheduler.py                    # Start scheduler
tail -f scheduler.log                       # Monitor logs
ps aux | grep auto_scheduler                # Check if running
```

## Emergency Procedures

### System Down?
1. Check process: `ps aux | grep auto_scheduler`
2. Check logs: `tail -100 scheduler.log`
3. Check API quota: `python tests/check_groq_usage.py`
4. Check MongoDB: `python tests/emergency_diagnostic.py`
5. Fix and restart: `python auto_scheduler.py`

### No Emails Sending?
1. Verify leads exist: `python tests/check_last_sends.py`
2. Check API quota exhaustion
3. Check for code errors in logs
4. Verify Zoho credentials
5. Check email account daily limits

## AI Model Context

- **Email Generator:** Uses Groq (llama-3.3-70b-versatile, groq/compound chain)
- **Email Reviewer:** Validates quality before sending (score ≥ 70)
- **Lead Enricher:** Crawls company websites for personalization
- **ICP Classifier:** TK Kader framework for lead qualification

## Contact & Support

- System Owner: Abdul Rehman Mehar
- Emergency: Check `docs/CRITICAL_FAILURE_ANALYSIS.md`
- Setup Guide: `docs/OLLAMA_SETUP.md`
- Monitoring: `docs/ELK_MONITORING.md`
