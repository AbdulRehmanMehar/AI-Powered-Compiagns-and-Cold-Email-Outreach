# ELK Monitoring Setup for Cold Email System

## Current Setup

Your app already has GELF logging configured in `docker-compose.yml`:

```yaml
logging:
  driver: gelf
  options:
    gelf-address: ${GELF_ADDRESS}
    tag: "{{.Name}}"
```

All Docker container logs are sent to your ELK stack automatically.

## Enhanced Logging

### 1. Enable Structured JSON Logging

Update your app to use structured logging for better ELK queries:

```python
# In auto_scheduler.py or main entry point
from utils.elk_logging import setup_elk_logging

# Enable structured JSON logs
setup_elk_logging(level="INFO", structured=True)
```

### 2. Add Event Tracking

Use the new logging helpers to track key events:

```python
from utils.elk_logging import log_campaign_event, log_email_event, log_performance_metric

# Log campaign events
log_campaign_event(
    'campaign_started',
    campaign_id=campaign_id,
    campaign_name=name,
    max_leads=100,
    icp_template=icp
)

# Log email events
log_email_event(
    'email_sent',
    to_email=lead_email,
    from_email=sender_email,
    campaign_id=campaign_id,
    subject=subject
)

# Log metrics
log_performance_metric(
    'lead_conversion_rate',
    value=sent/fetched*100,
    unit='percent',
    campaign_id=campaign_id
)
```

## Kibana Dashboards

### Key Metrics to Monitor

1. **Email Sending Rate**
   - Query: `event_type:"email_sent" AND @timestamp:[now-24h TO now]`
   - Visualization: Line chart over time
   - Aggregation: Count per hour

2. **Conversion Rate**
   - Query: `metric_name:"lead_conversion_rate"`
   - Visualization: Gauge or line chart
   - Alert if < 10%

3. **Account Usage**
   - Query: `from_email:* AND event_type:"email_sent"`
   - Visualization: Pie chart by from_email
   - Shows distribution across 8 accounts

4. **Error Rate**
   - Query: `level:"ERROR" OR event_type:"email_failed"`
   - Visualization: Bar chart by error type
   - Alert if spike > 10/hour

5. **Campaign Performance**
   - Query: `event_type:"campaign_started" OR event_type:"campaign_completed"`
   - Visualization: Table with metrics
   - Fields: campaign_id, leads_fetched, emails_sent, duration

### Sample Kibana Queries

```
# Today's sent emails
@timestamp:[now/d TO now] AND event_type:"email_sent"

# Failed emails
level:"ERROR" AND event_type:"email_failed"

# Specific campaign
campaign_id:"abc123"

# Account hitting limits
from_email:"info@primestrides.com" AND (event_type:"limit_reached" OR message:*limit*)

# Slow operations (> 30 seconds)
metric_name:*duration* AND metric_value:>30
```

## Monitoring Scripts

### Quick Stats (No Kibana Required)

```bash
# Today's summary
python monitor_elk.py --today

# Campaign details
python monitor_elk.py --campaign <campaign_id>

# Recent errors
python monitor_elk.py --errors
```

### Set Up Alerts

Create alerts in Kibana for:

1. **High Error Rate**: > 10 errors in 1 hour
2. **Low Conversion**: < 10% conversion rate for 3 consecutive campaigns
3. **Account Limits**: Any account hits daily limit before 3pm EST
4. **Service Down**: No logs for > 5 minutes

## Environment Variables

Add to your `.env`:

```bash
# Logging config
LOG_LEVEL=INFO
ENABLE_STRUCTURED_LOGGING=true
GELF_ADDRESS=udp://your-logstash-host:12201
```

## Deployment

1. Update your application to use new logging:
   ```bash
   # No code changes needed, just restart
   docker-compose restart coldemails
   ```

2. Logs will automatically flow to ELK via GELF

3. Access Kibana to create dashboards:
   - Go to Kibana → Discover
   - Create index pattern: `logstash-*`
   - Set time field: `@timestamp`

## Next Steps

1. **Today**: Monitor using `python monitor_elk.py --today`
2. **Tomorrow**: Check Kibana for structured logs
3. **Week 1**: Create dashboards for key metrics
4. **Week 2**: Set up alerts for anomalies

Would you like me to integrate the structured logging into your existing code now?
