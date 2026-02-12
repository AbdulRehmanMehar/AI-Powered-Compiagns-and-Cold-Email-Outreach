import os
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL")

# LLM Provider (Groq, OpenAI, or Ollama)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()  # "groq", "openai", or "ollama"

# Groq (RECOMMENDED - faster and cheaper)
# Model options:
#   - llama-3.3-70b-versatile: Best quality, follows instructions well, 1K requests/day
#   - llama-3.1-70b-versatile: Great quality, 1K requests/day
#   - llama-3.1-8b-instant: POOR instruction following, 14.4K requests/day
#   - meta-llama/llama-4-scout-17b-16e-instruct: Newer model, 1K requests/day
# NOTE: The 8B model is terrible at following complex prompts!
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")  # Quality over quantity

# OpenAI (fallback when Groq rate limited)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# Ollama (local LLM server - unlimited, no rate limits)
# Example: http://192.168.1.9:11434 or http://localhost:11434
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.1.9:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")  # Other options: qwen2.5:14b (needs 8.7GB RAM), llama3.1:8b

# RocketReach
ROCKETREACH_API_KEY = os.getenv("ROCKETREACH_API_KEY")

# RocketReach Search Settings - Optimize for lead volume
ROCKETREACH_MAX_PAGE_SIZE = int(os.getenv("ROCKETREACH_MAX_PAGE_SIZE", "100"))  # Max per API call
ROCKETREACH_FETCH_MULTIPLIER = float(os.getenv("ROCKETREACH_FETCH_MULTIPLIER", "3"))  # Fetch 3x leads to account for filtering
ROCKETREACH_RETRY_WITHOUT_KEYWORDS = os.getenv("ROCKETREACH_RETRY_WITHOUT_KEYWORDS", "true").lower() == "true"  # Fallback to broader search

# Zoho Email - Multiple Accounts Support
def parse_email_accounts() -> List[Dict[str, str]]:
    """Parse multiple email accounts from environment"""
    emails = os.getenv("ZOHO_EMAILS", os.getenv("ZOHO_EMAIL", "")).split(",")
    passwords = os.getenv("ZOHO_PASSWORDS", os.getenv("ZOHO_PASSWORD", "")).split(",")
    names = os.getenv("ZOHO_SENDER_NAMES", "PrimeStrides Team").split(",")
    
    accounts = []
    for i, email in enumerate(emails):
        email = email.strip()
        if email:
            accounts.append({
                "email": email,
                "password": passwords[i].strip() if i < len(passwords) else passwords[0].strip(),
                "sender_name": names[i].strip() if i < len(names) else names[0].strip()
            })
    return accounts

ZOHO_ACCOUNTS = parse_email_accounts()
ZOHO_SMTP_HOST = os.getenv("ZOHO_SMTP_HOST", "smtppro.zoho.com")
ZOHO_SMTP_PORT = int(os.getenv("ZOHO_SMTP_PORT", "587"))
ZOHO_IMAP_HOST = os.getenv("ZOHO_IMAP_HOST", "imappro.zoho.com")
ZOHO_IMAP_PORT = int(os.getenv("ZOHO_IMAP_PORT", "993"))

# Email rotation
EMAIL_ROTATION_STRATEGY = os.getenv("EMAIL_ROTATION_STRATEGY", "round-robin")  # "round-robin" or "random"
EMAILS_PER_ACCOUNT = int(os.getenv("EMAILS_PER_ACCOUNT", "5"))

# Domain throttling — max emails to a single recipient domain per day
# Prevents sending too many emails to the same company/ESP in one day
# With 300/day target, 3 is too tight for diverse domains — 5 is a safer default
MAX_EMAILS_PER_RECIPIENT_DOMAIN = int(os.getenv("MAX_EMAILS_PER_RECIPIENT_DOMAIN", "5"))

# Legacy single account support (for backward compatibility)
ZOHO_EMAIL = ZOHO_ACCOUNTS[0]["email"] if ZOHO_ACCOUNTS else ""
ZOHO_PASSWORD = ZOHO_ACCOUNTS[0]["password"] if ZOHO_ACCOUNTS else ""

# Email Settings
FROM_NAME = os.getenv("FROM_NAME", "PrimeStrides Team")
REPLY_TO = os.getenv("REPLY_TO", ZOHO_EMAIL)

# Follow-up Settings (Expert strategy: 2-3 emails max, short sequences = less spam)
# Email 1: Initial (Day 0)
# Email 2: Same thread follow-up (Day 3) - add value, don't just bump
# Email 3: NEW thread, different angle (Day 6) - optional, lower friction offer
FOLLOWUP_1_DELAY_DAYS = int(os.getenv("FOLLOWUP_1_DELAY_DAYS", "3"))  # Same thread
FOLLOWUP_2_DELAY_DAYS = int(os.getenv("FOLLOWUP_2_DELAY_DAYS", "6"))  # New thread
MAX_FOLLOWUPS = int(os.getenv("MAX_FOLLOWUPS", "2"))  # 2 max (total 3 emails)

# Legacy support
FOLLOWUP_DELAY_DAYS = FOLLOWUP_1_DELAY_DAYS

# Email Verification - ALWAYS ENABLED (reduces bounces from ~40% to <5%)
# These are hardcoded to True because verification is critical for deliverability
VERIFY_EMAILS = True  # Always verify emails before sending
VERIFY_MX_RECORDS = True  # Always check MX records exist
VERIFY_SMTP = True  # Always do SMTP verification (catches invalid mailboxes)
SKIP_ROLE_BASED_EMAILS = os.getenv("SKIP_ROLE_BASED_EMAILS", "true").lower() == "true"
SKIP_PROBLEMATIC_TLDS = os.getenv("SKIP_PROBLEMATIC_TLDS", "true").lower() == "true"

# Sending limits (Expert advice: 30-50 per mailbox per day with proper warmup)
EMAILS_PER_DAY_PER_MAILBOX = int(os.getenv("EMAILS_PER_DAY_PER_MAILBOX", "50"))
MIN_DELAY_BETWEEN_EMAILS = int(os.getenv("MIN_DELAY_BETWEEN_EMAILS", "8"))   # minutes — 8-14 min avg = ~42 sends/account/8h
MAX_DELAY_BETWEEN_EMAILS = int(os.getenv("MAX_DELAY_BETWEEN_EMAILS", "14"))  # minutes — safe for warmed accounts

# Global daily target (0 = disabled, uses per-mailbox limit only)
# When set, distributes target evenly across active accounts.
# Per-account limit = ceil(GLOBAL_DAILY_TARGET / active_accounts)
# Still respects warmup/warm-down and never exceeds Zoho's 500/account hard cap.
# Example: GLOBAL_DAILY_TARGET=300 with 6 accounts → 50/account/day
GLOBAL_DAILY_TARGET = int(os.getenv("GLOBAL_DAILY_TARGET", "0"))

# Warm-up Schedule (CRITICAL to avoid blocks)
# Week 1: 5 emails/day/account
# Week 2: 12 emails/day/account  
# Week 3: 25 emails/day/account
# Week 4+: 45 emails/day/account (supports 300/day ÷ 8 accounts = 38 + buffer)
WARMUP_ENABLED = os.getenv("WARMUP_ENABLED", "true").lower() == "true"
WARMUP_WEEK1_LIMIT = int(os.getenv("WARMUP_WEEK1_LIMIT", "5"))
WARMUP_WEEK2_LIMIT = int(os.getenv("WARMUP_WEEK2_LIMIT", "12"))
WARMUP_WEEK3_LIMIT = int(os.getenv("WARMUP_WEEK3_LIMIT", "25"))
WARMUP_WEEK4_LIMIT = int(os.getenv("WARMUP_WEEK4_LIMIT", "45"))

# Sending hours (US Eastern business hours: 9 AM - 5 PM)
# Uses America/New_York timezone which auto-handles EST/EDT
TARGET_TIMEZONE = os.getenv("TARGET_TIMEZONE", "America/New_York")
SENDING_HOUR_START = int(os.getenv("SENDING_HOUR_START", "9"))    # 9 AM in target timezone
SENDING_HOUR_END = int(os.getenv("SENDING_HOUR_END", "17"))       # 5 PM in target timezone
SEND_ON_WEEKENDS = os.getenv("SEND_ON_WEEKENDS", "false").lower() == "true"
