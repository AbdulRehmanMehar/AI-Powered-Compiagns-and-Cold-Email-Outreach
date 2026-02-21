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

        print(f"✅ {len(config.PRODUCTION_ACCOUNTS)} production accounts loaded ({config.PRIMARY_SENDER_MODE} mode)")
        print(f"✅ LLM provider: {config.LLM_PROVIDER}")
        print()

        # ── Feasibility check for GLOBAL_DAILY_TARGET ──
        if config.GLOBAL_DAILY_TARGET > 0:
            n_accounts = len(config.PRODUCTION_ACCOUNTS)
            target = config.GLOBAL_DAILY_TARGET
            per_account_target = -(-target // n_accounts)  # ceil division
            window_hours = config.SENDING_HOUR_END - config.SENDING_HOUR_START
            window_min = window_hours * 60
            avg_delay = (config.MIN_DELAY_BETWEEN_EMAILS + config.MAX_DELAY_BETWEEN_EMAILS) / 2

            # Account for time-of-day multipliers (weighted average across send window)
            from v2.human_behavior import TIME_OF_DAY_MULTIPLIERS
            multipliers = [TIME_OF_DAY_MULTIPLIERS.get(h, 1.0)
                           for h in range(config.SENDING_HOUR_START, config.SENDING_HOUR_END)]
            avg_multiplier = sum(multipliers) / len(multipliers) if multipliers else 1.0
            effective_delay = avg_delay * avg_multiplier

            # Account for warmup cap
            warmup_cap = config.WARMUP_WEEK4_LIMIT if config.WARMUP_ENABLED else config.EMAILS_PER_DAY_PER_MAILBOX
            throughput_per_account = int(window_min / effective_delay) if effective_delay > 0 else 0
            effective_per_account = min(throughput_per_account, warmup_cap)
            max_total = effective_per_account * n_accounts

            print(f"📊 Global daily target: {target} emails")
            print(f"   Accounts: {n_accounts} → ~{per_account_target}/account/day needed")
            print(f"   Send window: {window_hours}h ({window_min} min)")
            print(f"   Base delay: {config.MIN_DELAY_BETWEEN_EMAILS}-{config.MAX_DELAY_BETWEEN_EMAILS} min (avg {avg_delay:.1f})")
            print(f"   Avg time-of-day multiplier: {avg_multiplier:.2f}x → effective avg {effective_delay:.1f} min")
            print(f"   Warmup cap (week 4+): {warmup_cap}/account/day")
            print(f"   Throughput/account: ~{throughput_per_account} (cooldown) → capped at {effective_per_account} (warmup)")
            print(f"   Max achievable total: ~{max_total}")

            if max_total < target:
                # Calculate what's needed
                needed_per_account = per_account_target
                recommended_eff_delay = window_min / needed_per_account
                recommended_base = recommended_eff_delay / avg_multiplier
                recommended_max_delay = int(recommended_base + 3)
                recommended_min_delay = max(3, int(recommended_base - 3))
                print()
                print(f"   ⚠️  WARNING: Cannot reach {target}/day!")
                print(f"   ⚠️  Effective capacity is ~{max_total}/day")
                if effective_per_account == warmup_cap and throughput_per_account > warmup_cap:
                    print(f"   ⚠️  Bottleneck: warmup cap ({warmup_cap}) — raise WARMUP_WEEK4_LIMIT to ≥{needed_per_account}")
                else:
                    print(f"   💡 Recommended: MIN_DELAY={recommended_min_delay}, MAX_DELAY={recommended_max_delay}")
                print()
            else:
                buffer_pct = ((max_total - target) / target) * 100
                print(f"   ✅ Can achieve target ({max_total} ≥ {target}, {buffer_pct:.0f}% buffer)")
            print()

    except Exception as e:
        print(f"❌ Pre-flight check failed: {e}")
        sys.exit(1)

    # Import and run the scheduler
    from v2.scheduler import main as scheduler_main
    asyncio.run(scheduler_main())


if __name__ == "__main__":
    main()
