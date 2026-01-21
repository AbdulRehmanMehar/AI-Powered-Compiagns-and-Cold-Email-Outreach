import os
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# RocketReach
ROCKETREACH_API_KEY = os.getenv("ROCKETREACH_API_KEY")

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
ZOHO_SMTP_HOST = os.getenv("ZOHO_SMTP_HOST", "smtp.zoho.com")
ZOHO_SMTP_PORT = int(os.getenv("ZOHO_SMTP_PORT", "587"))

# Email rotation
EMAIL_ROTATION_STRATEGY = os.getenv("EMAIL_ROTATION_STRATEGY", "round-robin")  # "round-robin" or "random"
EMAILS_PER_ACCOUNT = int(os.getenv("EMAILS_PER_ACCOUNT", "5"))

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

# Sending limits (Expert advice: 20-30 per mailbox per day)
EMAILS_PER_DAY_PER_MAILBOX = int(os.getenv("EMAILS_PER_DAY_PER_MAILBOX", "25"))
MIN_DELAY_BETWEEN_EMAILS = int(os.getenv("MIN_DELAY_BETWEEN_EMAILS", "20"))  # minutes (was 7)
MAX_DELAY_BETWEEN_EMAILS = int(os.getenv("MAX_DELAY_BETWEEN_EMAILS", "35"))  # minutes (was 12)

# Warm-up Schedule (CRITICAL to avoid blocks)
# Week 1: 3 emails/day/account
# Week 2: 7 emails/day/account  
# Week 3: 12 emails/day/account
# Week 4+: 20 emails/day/account (max)
WARMUP_ENABLED = os.getenv("WARMUP_ENABLED", "true").lower() == "true"
WARMUP_WEEK1_LIMIT = int(os.getenv("WARMUP_WEEK1_LIMIT", "3"))
WARMUP_WEEK2_LIMIT = int(os.getenv("WARMUP_WEEK2_LIMIT", "7"))
WARMUP_WEEK3_LIMIT = int(os.getenv("WARMUP_WEEK3_LIMIT", "12"))
WARMUP_WEEK4_LIMIT = int(os.getenv("WARMUP_WEEK4_LIMIT", "20"))

# Sending hours (US Eastern business hours: 9 AM - 5 PM)
# Uses America/New_York timezone which auto-handles EST/EDT
TARGET_TIMEZONE = os.getenv("TARGET_TIMEZONE", "America/New_York")
SENDING_HOUR_START = int(os.getenv("SENDING_HOUR_START", "9"))    # 9 AM in target timezone
SENDING_HOUR_END = int(os.getenv("SENDING_HOUR_END", "17"))       # 5 PM in target timezone
SEND_ON_WEEKENDS = os.getenv("SEND_ON_WEEKENDS", "false").lower() == "true"
