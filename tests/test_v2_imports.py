#!/usr/bin/env python3
"""Quick import test for all v2 modules."""
import sys
sys.path.insert(0, '.')

print("Testing v2 module imports...")

from v2.human_behavior import (
    is_holiday, get_human_cooldown_minutes, plan_daily_sessions,
    should_skip_send, domain_tracker, RecipientDomainTracker,
    get_time_of_day_multiplier, apply_jitter, get_us_holidays
)
print("  v2.human_behavior OK")

from v2.alerts import send_alert, AlertLevel, send_daily_summary
print("  v2.alerts OK")

from v2.pre_generator import EmailDraft, DraftStatus, PreGenerator
print("  v2.pre_generator OK")

from v2.account_pool import AccountPool, AccountReputation, WarmDown
print("  v2.account_pool OK")

from v2.imap_worker import ImapWorker
print("  v2.imap_worker OK")

from v2.send_worker import SendWorker, text_to_html
print("  v2.send_worker OK")

# Test key functions
h, name = is_holiday()
print(f"\n  Holiday today: {h} ({name})")

cd = get_human_cooldown_minutes()
print(f"  Sample cooldown: {cd} min")

sessions = plan_daily_sessions()
print(f"  Planned sessions: {sessions}")

m = get_time_of_day_multiplier(12)
print(f"  Lunch multiplier: {m}x")

# Test text_to_html
html = text_to_html("Hello World\n\nSecond paragraph")
assert "<p>" in html
print("  text_to_html OK")

# Test domain tracker
dt = RecipientDomainTracker(max_per_domain=2)
assert dt.can_send_to("user@example.com") == True
dt.record_send("user@example.com")
dt.record_send("user2@example.com")
assert dt.can_send_to("user3@example.com") == False
print("  RecipientDomainTracker OK")

# Test holidays
holidays = get_us_holidays(2026)
assert len(holidays) >= 10
print(f"  US holidays 2026: {len(holidays)} dates")

print("\nALL v2 IMPORTS AND TESTS PASSED")
