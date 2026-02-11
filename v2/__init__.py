"""
Cold Email System v2 — Async Architecture

All new modules live here. The legacy system (auto_scheduler.py, campaign_manager.py,
zoho_sender.py, reply_detector.py) is untouched. A single env var SCHEDULER_MODE=async
switches to the new system.

Modules:
    scheduler.py      — AsyncIO event loop + APScheduler cron triggers
    send_worker.py    — Async SMTP sender (aiosmtplib)
    imap_worker.py    — Async IMAP reply/bounce checker (aioimaplib)
    pre_generator.py  — Pre-generate email drafts via Ollama
    account_pool.py   — Per-account locks, reputation, atomic claiming
    human_behavior.py — Session planning, jitter, holidays, domain throttling
    alerts.py         — Webhook alerting (Slack/Telegram/Discord)
"""
