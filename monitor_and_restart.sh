#!/bin/bash
# Monitor and auto-restart cold email scheduler

LOG_FILE="/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails/restart.log"
SCHEDULER_DIR="/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails"
SCHEDULER_LOG="/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails/scheduler.log"

# Check if scheduler is running
if ! ps aux | grep -q "[a]uto_scheduler.py"; then
    echo "$(date): Scheduler not running, restarting..." | tee -a "$LOG_FILE"
    cd "$SCHEDULER_DIR"
    nohup python3 auto_scheduler.py > "$SCHEDULER_LOG" 2>&1 &
    echo "$(date): Scheduler restarted with PID $!" | tee -a "$LOG_FILE"
else
    echo "$(date): Scheduler is running" >> "$LOG_FILE"
fi
