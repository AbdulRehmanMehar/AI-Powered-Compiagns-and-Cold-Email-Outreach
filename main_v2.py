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

    except Exception as e:
        print(f"❌ Pre-flight check failed: {e}")
        sys.exit(1)

    # Import and run the scheduler
    from v2.scheduler import main as scheduler_main
    asyncio.run(scheduler_main())


if __name__ == "__main__":
    main()
