FROM python:3.11-slim

LABEL maintainer="PrimeStrides <hello@primestrides.com>"
LABEL description="Cold Email Automation System"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Karachi

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check — verifies MongoDB is reachable
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "from database import db; db.command('ping')" || exit 1

# Entry point — SCHEDULER_MODE=async runs v2, anything else runs legacy
CMD ["sh", "-c", "if [ \"$SCHEDULER_MODE\" = 'async' ]; then python main_v2.py; else python auto_scheduler.py; fi"]
