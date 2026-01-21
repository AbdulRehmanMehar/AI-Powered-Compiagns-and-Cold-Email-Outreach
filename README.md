# Cold Email Automation System

A fully automated cold email outreach system using AI-powered email generation, RocketReach for lead discovery, and multi-account Zoho for sending. Based on expert cold email strategies from Eric Nowoslawski and LeadGenJay.

## Features

- 🔍 **RocketReach Integration**: Search and fetch leads based on job titles, industries, locations
- 🤖 **AI-Powered Emails**: GPT-4o generates personalized emails following expert strategies
- 📧 **Multi-Account Zoho**: Rotates across 5 email accounts for higher deliverability
- 🔄 **Smart Follow-ups**: Day 3 (same thread) + Day 6 (new thread with different angle)
- 📊 **Campaign Management**: Track campaigns, leads, and email statistics
- 💾 **MongoDB Storage**: Persists all data for tracking and deduplication
- ⏰ **Fully Automated**: Runs on schedule with no manual intervention
- �️ **Global Deduplication**: Never emails the same person twice across any campaign
- 🐳 **Dockerized**: Ready for Portainer deployment

---

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials (see Configuration section below)
```

### 2. Configure Campaign Schedule

```bash
cp scheduler_config.example.json scheduler_config.json
```

Edit `scheduler_config.json` to define your campaigns:

```json
{
  "scheduled_campaigns": [
    {
      "description": "Target healthcare and medical technology companies that need software development",
      "schedule_time": "09:00",
      "days": ["monday", "wednesday", "friday"],
      "max_leads": 15,
      "enabled": true
    },
    {
      "description": "Target fintech startups looking to build mobile apps or web platforms",
      "schedule_time": "10:00",
      "days": ["tuesday", "thursday"],
      "max_leads": 15,
      "enabled": true
    }
  ],
  "settings": {
    "timezone": "Asia/Karachi",
    "pause_weekends": true,
    "max_emails_per_day_per_mailbox": 25
  }
}
```

**Campaign fields:**
| Field | Description |
|-------|-------------|
| `description` | Plain English description - AI determines targeting, pain points, and email copy |
| `schedule_time` | When to run (HH:MM, 24hr format) |
| `days` | Which days to run (lowercase) |
| `max_leads` | Maximum leads to fetch per run |
| `enabled` | Set to `false` to disable without deleting |

### 3. Start the System

**Docker (Recommended):**
```bash
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

**Local Development:**
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python auto_scheduler.py
```

---

## End-to-End Flow

### 1. Startup
```
scheduler_config.json → AutoScheduler loads campaign templates
                      → Checks for missed campaigns (runs them immediately)
                      → Schedules future campaigns at their designated times
```

### 2. Campaign Execution (at scheduled time or on catch-up)
```
Campaign Template (e.g., "Target SaaS founders building MVPs")
    ↓
EmailGenerator.determine_icp_and_criteria()
    → GPT-4o analyzes description
    → Returns: search criteria, pain point, case study, unique angle
    ↓
CampaignManager.create_campaign()
    → Saves campaign to MongoDB (campaigns collection)
    ↓
RocketReachClient.search_leads()
    → Fetches leads matching criteria (titles, industries, location)
    → Skips anyone already contacted (global deduplication)
    → Validates email format before saving
    → Saves new leads to MongoDB (leads collection)
    ↓
For each lead:
    EmailGenerator.generate_initial_email()
        → GPT-4o writes personalized email (<75 words, curiosity-first)
        → Returns: subject + body
    ↓
    ZohoSender.send_email()
        → Picks next account (round-robin across 5 accounts)
        → Sends via Zoho SMTP
        → Saves to MongoDB (emails collection) with status + timestamps
```

### 3. Follow-up Loop (every 6 hours)
```
CampaignManager.send_followup_emails()
    ↓
For each campaign:
    Find emails where:
        - status = "sent" (not replied/bounced)
        - followup_count < 2
        - last_sent_at > 3 days ago (followup 1) or > 6 days ago (followup 2)
    ↓
    EmailGenerator.generate_followup_email()
        → Followup 1: Same thread (Re: subject), adds value
        → Followup 2: NEW thread, different angle, lower friction
    ↓
    ZohoSender.send_email() or send_reply()
    → Updates email record in MongoDB
```

### 4. Reply Detection (every 2 hours, requires paid Zoho IMAP)
```
ReplyDetector.check_replies()
    → IMAP connects to each Zoho account
    → Searches for replies to sent emails
    → Marks email status = "replied" in MongoDB
    → Stops further follow-ups for that lead
```

### 5. Data Model
```
MongoDB: primeoutreachcron
├── campaigns    {name, status, target_criteria, campaign_context, stats}
├── leads        {email, name, company, title, campaign_id, contacted}
└── emails       {lead_id, campaign_id, subject, body, status, followup_count, sent_at}
```

### 6. Sending Limits
- 5 Zoho accounts rotating
- 25 emails/day/account = 125 total/day
- 7-12 min random delay between emails
- Weekends paused

### Visual Flow
```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│ scheduler_config│────▶│ AI generates │────▶│ RocketReach │
│    (50 ICPs)    │     │   criteria   │     │ fetches leads│
└─────────────────┘     └──────────────┘     └──────┬──────┘
                                                    │
                        ┌───────────────────────────┘
                        ▼
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│    MongoDB      │◀───▶│ AI writes    │────▶│ Zoho sends  │
│ (campaigns,     │     │   emails     │     │  (5 accts)  │
│  leads, emails) │     └──────────────┘     └─────────────┘
└─────────────────┘
        ▲                                           │
        │           ┌──────────────┐                │
        └───────────│  Follow-ups  │◀───────────────┘
                    │  (Day 3 & 6) │
                    └──────────────┘
```

---

## Expert Email Strategy (Implemented)

Based on Eric Nowoslawski's 90-page doc and LeadGenJay's masterclass:

| Rule | Implementation |
|------|----------------|
| Subject: 2-4 words, colleague-like | NO "Quick question", YES "saw something" |
| First line = curiosity builder | NO "I noticed...", YES "random question—" |
| Under 75 words | Enforced in AI prompts |
| ONE pain point only | AI picks single pain from campaign context |
| Specific case studies | Real numbers: "43% reduction in 8 weeks" |
| Max 3 emails total | Initial + 2 follow-ups, then stop |
| Email 2: Same thread | Adds value, not "just following up" |
| Email 3: NEW thread | Different subject, different angle |
| Soft CTA only | "worth a quick chat?" not "schedule a call" |

---

## Quick Start

### Docker (Recommended)

```bash
# Clone and configure
cp .env.example .env
# Edit .env with your credentials

# Start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

### Local Development

```bash
# Install dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your credentials

# Run scheduler
python auto_scheduler.py
```

---

## Configuration

### Environment Variables (.env)

```env
DATABASE_URL=mongodb://admin:password@192.168.1.9:27017/primeoutreachcron?authSource=admin
OPENAI_API_KEY=sk-...
ROCKETREACH_API_KEY=...

# Multiple Zoho accounts (comma-separated, same order)
ZOHO_EMAILS=hello@domain.com,info@domain.com,ali@domain.com
ZOHO_PASSWORDS=pass1,pass2,pass3
ZOHO_SENDER_NAMES=Ahmed,Abdul,Ali

EMAIL_ROTATION_STRATEGY=round-robin
EMAILS_PER_ACCOUNT=5
```

---

## Deduplication

The system guarantees you **never email the same person twice**:

| Stage | Protection |
|-------|------------|
| RocketReach fetch | Checks DB for already-contacted emails before expensive lookups |
| Email validation | Skips malformed emails (domains without @) |
| Campaign level | Double-checks before each send |
| Database | Unique index on email field |

---

## Manual CLI Commands

```bash
# Test email sending
python main.py test-email your@email.com

# Test RocketReach
python main.py test-rocketreach

# Create campaign manually
python main.py create-campaign

# Run campaign
python main.py run <campaign_id> --max-leads 10

# Dry run (no emails sent)
python main.py run <campaign_id> --dry-run

# Send follow-ups only
python main.py followups <campaign_id>

# View stats
python main.py stats <campaign_id>

# List campaigns
python main.py list
```

---

## Project Structure

```
coldemails/
├── auto_scheduler.py            # Main entry - fully automated scheduler
├── campaign_manager.py          # Campaign orchestration
├── email_generator.py           # AI email generation (expert strategies)
├── primestrides_context.py      # Case studies, ICP templates
├── rocketreach_client.py        # Lead discovery API
├── zoho_sender.py               # Multi-account email sending
├── reply_detector.py            # IMAP reply checking
├── database.py                  # MongoDB models
├── config.py                    # Environment config
├── main.py                      # CLI interface
├── scheduler_config.json        # Your campaign schedule (create from example)
├── scheduler_config.example.json # Template for campaign schedule
├── Dockerfile                   # Container build
├── docker-compose.yml           # Portainer-compatible deployment
├── .env                         # Credentials (create from example)
└── .env.example                 # Template for credentials
```

---

## Troubleshooting

### IMAP Warnings
```
⚠️ IMAP not enabled
```
This is expected on Zoho free plan. Reply detection requires paid Zoho with IMAP enabled.

### MongoDB Connection
Ensure `extra_hosts: host.docker.internal:host-gateway` is in docker-compose.yml for Docker to reach host MongoDB.

### Zoho Auth Errors
Use App-Specific Passwords from Zoho Account → Security → App Passwords.

### RocketReach Limits
Check credits at rocketreach.co. System deduplicates leads to avoid wasting credits.

---

## Writing Campaign Descriptions

The `description` field in `scheduler_config.json` is analyzed by AI to determine:
- **Target titles**: CEO, CTO, Founder, VP Engineering, etc.
- **Industries**: SaaS, FinTech, HealthTech, etc.
- **Pain points**: What problem they likely have
- **Email copy**: Personalized based on their situation

**Good descriptions:**
```
"Target fintech startups looking to build mobile apps or web platforms"
"Target healthcare companies that need HIPAA-compliant software development"
"Target SaaS founders who recently raised seed funding and need to ship fast"
"Target CTOs at growing startups whose engineering teams are stretched thin"
```

**Bad descriptions:**
```
"Send emails to tech companies"  # Too vague
"CEOs"  # No context about their needs
```

The more specific your description, the better the targeting and email personalization.
