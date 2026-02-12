#!/usr/bin/env python3
"""
Cold Email System v2 — Entry Point

Usage:
    python main_v2.py

Environment:
    Set SCHEDULER_MODE=async in your .env or stack.env to use this.
    The Dockerfile checks SCHEDULER_MODE and picks the right entry point.
"""

import asyncio
import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    print("=" * 60)
    print("  Cold Email System v2 — AsyncIO Scheduler")
    print("=" * 60)
    print()

    # Pre-flight checks
    try:
        import config
        if not config.ZOHO_ACCOUNTS:
            print("❌ No Zoho accounts configured. Check ZOHO_EMAILS env var.")
            sys.exit(1)

        if not config.DATABASE_URL:
            print("❌ DATABASE_URL not set.")
            sys.exit(1)

        # Verify MongoDB connectivity
        from database import db
        db.command("ping")
        print("✅ MongoDB connected")

        # Verify async dependencies
        try:
            import aiosmtplib
            print("✅ aiosmtplib available")
        except ImportError:
            print("❌ aiosmtplib not installed. Run: pip install aiosmtplib")
            sys.exit(1)

        try:
            import aiohttp
            print("✅ aiohttp available")
        except ImportError:
            print("⚠️  aiohttp not installed (alerts will be disabled)")

        print(f"✅ {len(config.ZOHO_ACCOUNTS)} email accounts loaded")
        print(f"✅ LLM provider: {config.LLM_PROVIDER}")
        print()

        # ── Feasibility check for GLOBAL_DAILY_TARGET ──
        if config.GLOBAL_DAILY_TARGET > 0:
            n_accounts = len(config.ZOHO_ACCOUNTS)
            target = config.GLOBAL_DAILY_TARGET
            per_account = -(-target // n_accounts)  # ceil division
            window_hours = config.SENDING_HOUR_END - config.SENDING_HOUR_START
            window_min = window_hours * 60
            avg_delay = (config.MIN_DELAY_BETWEEN_EMAILS + config.MAX_DELAY_BETWEEN_EMAILS) / 2
            max_sends_per_account = int(window_min / avg_delay) if avg_delay > 0 else 0
            max_total = max_sends_per_account * n_accounts

            print(f"📊 Global daily target: {target} emails")
            print(f"   Accounts: {n_accounts} → ~{per_account}/account/day")
            print(f"   Send window: {window_hours}h ({window_min} min)")
            print(f"   Delay: {config.MIN_DELAY_BETWEEN_EMAILS}-{config.MAX_DELAY_BETWEEN_EMAILS} min (avg {avg_delay})")
            print(f"   Max achievable/account: ~{max_sends_per_account}")
            print(f"   Max achievable total: ~{max_total}")

            if max_total < target:
                # Calculate recommended delay to actually hit target
                needed_per_account = per_account
                recommended_max_delay = int(window_min / needed_per_account)
                recommended_min_delay = max(3, recommended_max_delay - 5)
                print()
                print(f"   ⚠️  WARNING: Current delays too high to reach {target}/day!")
                print(f"   ⚠️  With {avg_delay}min avg delay, max is ~{max_total}/day")
                print(f"   💡 Recommended: MIN_DELAY_BETWEEN_EMAILS={recommended_min_delay}")
                print(f"   💡 Recommended: MAX_DELAY_BETWEEN_EMAILS={recommended_max_delay}")
                print()
            else:
                print(f"   ✅ Config can achieve target ({max_total} ≥ {target})")
            print()

    except Exception as e:
        print(f"❌ Pre-flight check failed: {e}")
        sys.exit(1)

    # Import and run the scheduler
    from v2.scheduler import main as scheduler_main
    asyncio.run(scheduler_main())


if __name__ == "__main__":
    main()
