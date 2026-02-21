#!/usr/bin/env python3
"""
Bidirectional warmup scheduler runner.
Executes warmup_bidirectional.py 3-4 times per day.

Usage:
    # Run single cycle
    python3 run_warmup_cycle.py
    
    # Schedule via cron (add to crontab):
    0 7 * * * cd /home/abdul/Documents/PrimeStrides/coldemails && source venv/bin/activate && python3 run_warmup_cycle.py >> warmup.log 2>&1
    0 12 * * * cd /home/abdul/Documents/PrimeStrides/coldemails && source venv/bin/activate && python3 run_warmup_cycle.py >> warmup.log 2>&1
    0 17 * * * cd /home/abdul/Documents/PrimeStrides/coldemails && source venv/bin/activate && python3 run_warmup_cycle.py >> warmup.log 2>&1
    0 22 * * * cd /home/abdul/Documents/PrimeStrides/coldemails && source venv/bin/activate && python3 run_warmup_cycle.py >> warmup.log 2>&1

    Or integrate into existing auto_scheduler.py for async execution.
"""

import sys
import os
import asyncio
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from warmup_bidirectional import run_bidirectional_warmup_cycle

def main():
    print(f"\n{'='*70}")
    print(f"WARMUP CYCLE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*70}\n")
    
    try:
        result = asyncio.run(run_bidirectional_warmup_cycle())
        
        print(f"\n{'='*70}")
        print(f"WARMUP SUMMARY")
        print(f"{'='*70}")
        print(f"  Emails sent:     {result.get('sent', 0)}")
        print(f"  Replies sent:    {result.get('replies', 0)}")
        print(f"  Total activity:  {result.get('total_activity', 0)}")
        print(f"  Timestamp:       {result.get('timestamp', 'N/A')}")
        print(f"{'='*70}\n")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
