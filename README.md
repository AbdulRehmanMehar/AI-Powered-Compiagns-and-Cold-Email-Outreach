# Cold Email Automation System

A **fully autonomous** cold email outreach system that requires **ZERO human input**. Uses AI-powered ICP selection, RocketReach for lead discovery, and multi-account Zoho for sending. Based on LeadGenJay's framework and TK Kader's ICP methodology.

## 🚀 What Makes This Different

**Traditional cold email systems** require you to:
- Manually define target audiences
- Write campaign descriptions
- Decide which ICP to target today
- Monitor and adjust based on results

**This system** does ALL of that automatically:
- 🤖 **AI selects the best ICP** based on historical performance data
- 📊 **Learns over time** - high-performing ICPs get more usage
- 🔄 **Rotates intelligently** - avoids audience burnout
- 🎯 **Tracks everything** - ICP performance, reply rates, conversions

---

## Features

- 🤖 **Fully Autonomous**: AI selects ICP, generates campaigns, sends emails - no human input
- 🎯 **ICP Framework**: TK Kader's methodology - 10x better, data-backed, tracked through GTM
- 📊 **Performance Learning**: Multi-armed bandit algorithm balances exploration vs exploitation
- 🔍 **RocketReach Integration**: Automatic lead sourcing based on ICP criteria
- ✍️ **LeadGenJay Emails**: 4-line framework, under 75 words, question-based pain points
- ✅ **Quality Gate**: AI reviewer scores emails before sending
- 📧 **Multi-Account Sending**: Rotates across Zoho or Gmail accounts (mode-switchable)
- 🔥 **Domain Warmup**: Bidirectional warmup system builds sender reputation automatically
- 🔄 **Smart Follow-ups**: Day 3 (same thread) + Day 6 (new thread, different angle)
- 🧵 **Email Threading**: Proper Message-ID/In-Reply-To headers for thread grouping
- 🛡️ **Global Deduplication**: Never emails same person twice across ANY campaign
- ✅ **Email Verification**: MX + SMTP verification reduces bounces to ~0%
- 💾 **MongoDB Storage**: All config, campaigns, leads, analytics in database
- 🐳 **Dockerized**: Ready for production deployment

---

## Quick Start

### Option 1: V2 Async Pipeline (Recommended)

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 2. Start the v2 async system
python main_v2.py
```

### Option 2: Legacy Scheduler

```bash
# Start the legacy synchronous scheduler
python auto_scheduler.py
```

The system will:
- Initialize default config in MongoDB
- Select best ICP based on performance data
- Create campaigns automatically
- Fetch leads from RocketReach
- Generate and send emails
- Track results and learn
- Run warmup cycles (if configured)

### Option 2: Docker Deployment

```bash
docker compose up -d
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     FULLY AUTONOMOUS COLD EMAIL SYSTEM                       │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   MongoDB        │     │  Auto Scheduler  │     │   ICP Manager    │
│   ─────────────  │◄───►│  ─────────────── │◄───►│   ────────────── │
│   • Config       │     │  • Runs on time  │     │  • Selects ICP   │
│   • ICP History  │     │  • Catches up    │     │  • Tracks perf   │
│   • Analytics    │     │  • Autonomous    │     │  • Learns        │
└──────────────────┘     └────────┬─────────┘     └──────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CAMPAIGN EXECUTION FLOW                              │
│                                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │ 1. SELECT   │───►│ 2. CREATE   │───►│ 3. FETCH    │───►│ 4. VERIFY   │  │
│  │    ICP      │    │   CAMPAIGN  │    │   LEADS     │    │   EMAILS    │  │
│  │             │    │             │    │             │    │             │  │
│  │ AI picks    │    │ From ICP    │    │ RocketReach │    │ MX + SMTP   │  │
│  │ best ICP    │    │ template    │    │ with ICP    │    │ validation  │  │
│  └─────────────┘    └─────────────┘    │ criteria    │    └─────────────┘  │
│                                        └─────────────┘                      │
│                                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │ 5. ENRICH   │───►│ 6. CLASSIFY │───►│ 7. GENERATE │───►│ 8. REVIEW   │  │
│  │    LEADS    │    │    ICP      │    │   EMAIL     │    │   QUALITY   │  │
│  │             │    │             │    │             │    │             │  │
│  │ Scrape      │    │ Score lead  │    │ LeadGenJay  │    │ Score 0-100 │  │
│  │ websites    │    │ against ICP │    │ 4-line      │    │ Rewrite if  │  │
│  └─────────────┘    └─────────────┘    │ framework   │    │ needed      │  │
│                                        └─────────────┘    └─────────────┘  │
│                                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │ 9. SEND     │───►│ 10. TRACK   │───►│ 11. FOLLOW  │───►│ 12. LEARN   │  │
│  │    EMAIL    │    │    RESULTS  │    │     UP      │    │             │  │
│  │             │    │             │    │             │    │             │  │
│  │ Zoho multi- │    │ MongoDB     │    │ Day 3 + 6   │    │ Feed back   │  │
│  │ account     │    │ analytics   │    │ threading   │    │ to ICP      │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    │ selection   │  │
│                                                           └─────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The Autonomous Pipeline

### Phase 1: ICP Selection (AI-Driven)

```
┌─────────────────────────────────────────────────────────────────┐
│                    AUTONOMOUS ICP SELECTION                      │
│                    (Multi-Armed Bandit Algorithm)                │
└─────────────────────────────────────────────────────────────────┘

Input:
├── Historical performance data (reply rates by ICP template)
├── Run history (when each ICP was last used)
├── Exploration rate setting (default 30%)
└── Min days between same ICP (default 2)

Algorithm:
┌─────────────────────────────────────────────────────────────────┐
│ For each ICP template:                                          │
│   if never_tested:                                              │
│     score = 50 + recency_bonus  (explore untested)              │
│   elif sent < 20:                                               │
│     score = 30 + reply_rate * 2 + recency_bonus  (learning)     │
│   else:                                                         │
│     score = reply_rate * 10 - overuse_penalty  (exploit)        │
│                                                                 │
│ if random() < exploration_rate:                                 │
│   select from top 3 (weighted random)  # Explore               │
│ else:                                                           │
│   select highest score  # Exploit                               │
└─────────────────────────────────────────────────────────────────┘

Output:
└── Selected ICP template (e.g., "startup_founders_funded")
```

### Phase 2: Campaign Creation

```
ICP Template: startup_founders_funded
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CAMPAIGN GENERATED                            │
├─────────────────────────────────────────────────────────────────┤
│ Name: Campaign: Startup Founders Funded                         │
│ ICP Template: startup_founders_funded                           │
│                                                                 │
│ Search Criteria (for RocketReach):                              │
│   current_title: [CEO, Founder, Co-Founder, CTO]                │
│   location: [United States, Canada, United Kingdom]             │
│   keywords: [Technology, Software, SaaS, FinTech, HealthTech,   │
│              recently raised, hiring engineers]                  │
│                                                                 │
│ Email Context:                                                  │
│   pain_point: "need to ship fast but can't find reliable..."    │
│   case_study: hr_tech_ai (43% faster processing)                │
│   front_end_offer: "free 30-min architecture review"            │
└─────────────────────────────────────────────────────────────────┘
```

### Phase 3: Lead Sourcing (RocketReach)

```
┌─────────────────────────────────────────────────────────────────┐
│                    ROCKETREACH SEARCH                            │
└─────────────────────────────────────────────────────────────────┘

Search Criteria → RocketReach API
    │
    ├── Pagination tracked per criteria hash
    │   └── Same ICP = same criteria = continues from last offset
    │
    ├── Global deduplication
    │   └── Excludes 147+ already-contacted emails
    │
    └── Results: Fresh leads matching ICP criteria

Example Flow:
📍 Starting RocketReach search from offset 1
🔍 Searching offset 1-16 (total available: 347,453)
✓ Found: John Smith - john@startup.com
✓ Found: Jane Doe - jane@techco.io
💾 Saved search offset: 16 for next time
```

### Phase 4: Email Verification

```
┌─────────────────────────────────────────────────────────────────┐
│                    VERIFICATION LAYERS                           │
└─────────────────────────────────────────────────────────────────┘

Layer 1: Quick Checks (instant)
├── Syntax validation
├── Disposable domain detection
├── Role-based email detection (info@, support@)
├── Problematic TLD check (.ru, .cn, .in)
└── Large company domain block (google.com)

Layer 2: MX Verification (~1 second)
└── Domain can receive email

Layer 3: SMTP Verification (~3 seconds)
└── Mailbox actually exists

Result: ~0% bounce rate (vs 40% without verification)
```

### Phase 5: Lead Enrichment

```
┌─────────────────────────────────────────────────────────────────┐
│                    LEAD ENRICHMENT                               │
└─────────────────────────────────────────────────────────────────┘

For each lead:
    1. Crawl company website
    2. Extract personalization hooks:
       - Recent news/launches
       - Tech stack signals
       - Hiring patterns
       - Product features
    3. Store in MongoDB for email generation

Example:
🔍 Enriching lead from https://startup.com
✅ Enriched: 3 personalization hooks found
   - "Just launched new API product"
   - "Hiring 5 engineers"
   - "Series A announced"
```

### Phase 6: ICP Classification

```
┌─────────────────────────────────────────────────────────────────┐
│                    ICP SCORING (TK Kader Framework)              │
└─────────────────────────────────────────────────────────────────┘

Scoring Components:
├── Title Match (40%): Decision-maker title vs ICP definition
├── Company Signals (30%): Tech company, right size, industry
├── Enrichment Data (20%): Hiring, funding, growth signals
└── Template Match (10%): Matches specific ICP template

Output:
├── is_icp: true/false
├── icp_score: 0.0 - 1.0
├── icp_template: "startup_founders_funded"
└── icp_reasons: ["Decision-maker title", "Tech company"]

Example:
✅ ICP Match (score: 0.75): Decision-maker title: CEO, Tech company
⚠️ Non-ICP Lead (score: 0.35): Not clearly a tech company
```

### Phase 7: Email Generation (LeadGenJay Framework)

```
┌─────────────────────────────────────────────────────────────────┐
│                    LEADGENJAY 4-LINE FRAMEWORK                   │
└─────────────────────────────────────────────────────────────────┘

LINE 1: PREVIEW TEXT (shows before opening)
├── Must sound like a friend texting
├── Must NOT reveal it's a pitch
└── ✅ "hey tom, quick one."

LINE 2: POKE THE BEAR (ask a QUESTION)
├── About a universal pain they'll recognize
└── ✅ "still doing deploys manually or did you automate that?"

LINE 3: CASE STUDY (real, specific numbers)
├── Must be TRUE (never fabricate)
└── ✅ "helped an hr startup cut processing 43% in 8 weeks."

LINE 4: SOFT CTA
├── Low friction, conversational
└── ✅ "thoughts?"

Rules Enforced:
├── Under 75 words total
├── No em dashes (—) - #1 AI tell
├── No corporate words (leverage, optimize, streamline)
├── No "I noticed..." or "I saw you're..."
└── Real case studies only (anti-hallucination protection)
```

### Phase 8: Quality Review

```
┌─────────────────────────────────────────────────────────────────┐
│                    QUALITY GATE                                  │
└─────────────────────────────────────────────────────────────────┘

Review Process:
1. Score email against LeadGenJay guidelines (0-100)
2. Check for violations:
   - Word count > 75
   - AI writing patterns
   - Banned phrases
   - Fabricated case studies
3. Decision:
   - Score >= 70: ✅ Pass
   - Score < 70: 🔄 Rewrite with feedback (max 2 attempts)
   - Still fails: ❌ Skip lead

Example:
📋 Email reviewer using: GROQ (llama-3.3-70b-versatile)
⚠️ Email passed with warnings (score: 76)
```

### Phase 9: Email Sending

```
┌─────────────────────────────────────────────────────────────────┐
│                    MULTI-ACCOUNT ZOHO SENDING                    │
└─────────────────────────────────────────────────────────────────┘

Account Rotation:
├── 8 email accounts configured
├── Round-robin rotation
├── 25 emails/day/account limit
├── 7-12 min cooldown between sends
└── Automatic failover if account exhausted

Email Threading:
├── Initial: New Message-ID generated
├── Followup 1: Same thread (In-Reply-To + References headers)
└── Followup 2: NEW thread (fresh Message-ID, different angle)

Sending Hours: 9:00 AM - 5:00 PM (US Eastern)
```

### Phase 10: Follow-up Sequence

```
┌─────────────────────────────────────────────────────────────────┐
│                    FOLLOW-UP SEQUENCE                            │
└─────────────────────────────────────────────────────────────────┘

Day 0: Initial Email
├── LeadGenJay 4-line framework
└── Fresh Message-ID

Day 3: Follow-up 1 (Same Thread)
├── Reply to original (In-Reply-To header)
├── Add value, don't just "bump"
├── Under 50 words
└── References original Message-ID

Day 6: Follow-up 2 (NEW Thread)
├── Completely different subject line
├── Different angle/offer
├── Fresh Message-ID
└── Under 60 words

Max 3 emails total, then stop.
```

### Phase 11: Analytics & Learning

```
┌─────────────────────────────────────────────────────────────────┐
│                    ICP PERFORMANCE TRACKING                      │
└─────────────────────────────────────────────────────────────────┘

Tracked Metrics (per ICP template):
├── Emails sent
├── Replies received
├── Reply rate (%)
├── Days since last used
└── Total leads sourced

Analytics Query:
┌─────────────────────────────────────────────────────────────────┐
│ ICP Template              │ Sent │ Replied │ Rate │ Last Run   │
├───────────────────────────┼──────┼─────────┼──────┼────────────┤
│ startup_founders_funded   │  45  │    3    │ 6.7% │ 2 days ago │
│ ctos_at_capacity          │  38  │    2    │ 5.3% │ 3 days ago │
│ ai_prototype_hell         │  22  │    1    │ 4.5% │ 5 days ago │
│ legacy_modernization      │   0  │    0    │  -   │ never      │
└─────────────────────────────────────────────────────────────────┘

Learning Loop:
High performers → More usage
Low performers → Less usage (but still explored)
Untested → High exploration priority
```

---

## MongoDB Collections

```
Database: primeoutreachcron
│
├── scheduler_config        # Autonomous scheduler settings
│   ├── config_type: "main"
│   │   ├── mode: "autonomous"
│   │   ├── scheduled_campaigns: [...]
│   │   └── schedules: {...}
│   └── config_type: "settings"
│       ├── timezone: "America/New_York"
│       ├── exploration_rate: 0.3
│       └── min_days_between_same_icp: 2
│
├── icp_run_history         # ICP usage tracking
│   ├── icp_template: "startup_founders_funded"
│   ├── run_date: datetime
│   ├── campaign_id: ObjectId
│   ├── leads_sent: 15
│   └── results: {...}
│
├── campaigns               # Campaign records
│   ├── name: "Campaign: Startup Founders Funded"
│   ├── target_criteria: {
│   │   ├── current_title: [...]
│   │   ├── location: [...]
│   │   ├── keywords: [...]
│   │   └── campaign_context: {
│   │       ├── icp_template: "startup_founders_funded"
│   │       ├── single_pain_point: "..."
│   │       └── case_study: {...}
│   │   }
│   └── stats: {sent, replied, bounced}
│
├── leads                   # Lead records
│   ├── email, name, company, title
│   ├── is_icp: true/false
│   ├── icp_template: "startup_founders_funded"
│   ├── icp_score: 0.75
│   └── enrichment: {...}
│
├── emails                  # Email records
│   ├── lead_id, campaign_id
│   ├── subject, body
│   ├── status: "sent" | "replied" | "bounced"
│   ├── is_icp: true/false
│   ├── icp_template: "..."
│   ├── message_id: "..." (for threading)
│   └── followup_number: 0 | 1 | 2
│
├── email_reviews           # Quality review records
├── search_offsets          # RocketReach pagination
├── llm_usage               # Groq API usage tracking
└── sending_stats           # Per-account send stats
```

---

## ICP Templates

Pre-defined ICP templates in `primestrides_context.py`:

| Template | Target | Pain Point |
|----------|--------|------------|
| `startup_founders_funded` | CEO/Founder at funded startups | Need to ship fast, can't find talent |
| `ctos_at_capacity` | CTO/VP Eng with stretched teams | Team can't hire fast enough |
| `ai_prototype_hell` | Leaders with AI demos that don't work | Prototypes fail in production |
| `legacy_modernization` | CTOs with legacy systems | Old systems holding them back |
| `product_leaders_roadmap_slip` | VP Product with slipping roadmap | Can't hit deadlines |

Each template includes:
- Target titles for RocketReach
- Industries/keywords
- Pain point for email copy
- Relevant case study
- Front-end offer
- Trigger signals

---

## 🔥 Domain Warmup System

New domains lack sender reputation and emails may land in spam. The system includes an automated **bidirectional warmup** to build domain reputation before scaling outreach.

### How It Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BIDIRECTIONAL WARMUP FLOW                                 │
│                                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │ 1. SEND     │───►│ 2. MONITOR  │───►│ 3. REPLY    │───►│ 4. RESCUE   │  │
│  │ Zoho → Test │    │ IMAP inbox  │    │ via Groq AI │    │ Spam→Inbox  │  │
│  │             │    │             │    │             │    │             │  │
│  │ Real-looking│    │ Gmail/IMAP  │    │ Contextual  │    │ Auto-move   │  │
│  │ business    │    │ check for   │    │ replies to  │    │ from spam   │  │
│  │ emails      │    │ warmup msgs │    │ warm emails │    │ to inbox    │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│                                                                              │
│  Test Accounts: Gmail addresses with app passwords (receive warmup emails)   │
│  Sender Accounts: Zoho production accounts (always send FROM Zoho)           │
│  Schedule: Runs every 4 hours as background task in v2 scheduler             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Sender Mode Switching

The system supports two modes via the `PRIMARY_SENDER_MODE` environment variable:

| Mode | `PRIMARY_SENDER_MODE` | Accounts Used | SMTP/IMAP Host |
|------|----------------------|---------------|----------------|
| **Zoho** (default) | `zoho` | `ZOHO_ACCOUNTS` (8 accounts) | smtppro.zoho.com / imappro.zoho.com |
| **Warmup** | `warmup` | `WARMUP_ACCOUNTS` (Gmail) | smtp.gmail.com / imap.gmail.com |

In **warmup mode**, the campaign pipeline continues running normally — it just routes through Gmail warmup accounts instead of Zoho. The warmup bidirectional system always sends FROM Zoho accounts TO test accounts regardless of mode.

> **CRITICAL**: The campaign pipeline (IMAP worker, send worker, pre-generator, campaign scheduler) is NEVER disabled regardless of sender mode. All workers always launch.

### Warmup Environment Variables

```env
# Test accounts that receive warmup emails (Gmail with app passwords)
WARMUP_EMAILS=account1@gmail.com,account2@gmail.com
WARMUP_EMAILS_APP_PASSWORDS=app_pw_1,app_pw_2

# Switch production sending to warmup accounts
PRIMARY_SENDER_MODE=warmup   # "zoho" (default) or "warmup"
```

### Warmup MongoDB Collections

| Collection | Purpose |
|-----------|---------|
| `warmup_email_drafts` | Pre-generated warmup email templates (separate from campaign drafts) |
| `warmup_threads` | Tracks warmup conversation threads for threading/replies |
| `emails` | Warmup sends are recorded here with `email_type: "warmup"` (no `lead_id`) |

---

## Configuration

### Environment Variables (.env)

```env
# MongoDB
DATABASE_URL=mongodb://localhost:27017/primeoutreachcron

# LLM Provider
LLM_PROVIDER=ollama                        # "ollama" or "groq"
OLLAMA_API_BASE=http://192.168.1.9:11434   # Ollama server (for campaigns)
GROQ_API_KEY=your_key                       # Groq API key (for warmup + fallback)

# RocketReach
ROCKETREACH_API_KEY=your_key

# Zoho (multiple accounts - production senders)
ZOHO_ACCOUNTS=[{"email":"a@co.com","password":"xxx"},{"email":"b@co.com","password":"xxx"}]

# Warmup (Gmail test accounts)
WARMUP_EMAILS=test1@gmail.com,test2@gmail.com
WARMUP_EMAILS_APP_PASSWORDS=app_pw1,app_pw2

# Sender Mode
PRIMARY_SENDER_MODE=zoho                    # "zoho" or "warmup"

# Verification
VERIFY_EMAILS=true
VERIFY_SMTP=true

# Sending
TARGET_TIMEZONE=America/New_York
SENDING_START_HOUR=9
SENDING_END_HOUR=17
```

### Scheduler Config (MongoDB)

The system stores config in MongoDB (`scheduler_config` collection), initialized with:

```json
{
  "mode": "autonomous",
  "scheduled_campaigns": [
    {
      "name": "morning_campaign",
      "autonomous": true,
      "schedule_time": "09:30",
      "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
      "max_leads": 15,
      "enabled": true
    },
    {
      "name": "afternoon_campaign",
      "autonomous": true,
      "schedule_time": "14:30",
      "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
      "max_leads": 15,
      "enabled": true
    }
  ],
  "settings": {
    "timezone": "America/New_York",
    "exploration_rate": 0.3,
    "min_days_between_same_icp": 2
  }
}
```

---

## Running the System

### Fully Autonomous (Recommended)

```bash
python auto_scheduler.py
```

Output:
```
📦 Loading scheduler config from MongoDB...
   Mode: autonomous
   Timezone: America/New_York
   Campaigns: 2
   🤖 Campaign #1: AUTONOMOUS (AI selects ICP)
   🤖 Campaign #2: AUTONOMOUS (AI selects ICP)

============================================================
🤖 AUTONOMOUS CAMPAIGN - NO HUMAN INPUT REQUIRED
============================================================

🎯 AI Selected ICP: startup_founders_funded
   Reason: High performer (6.7% reply rate)
   Mode: exploitation

Created campaign: Campaign: Startup Founders Funded
Fetching leads... Excluding 147 already-contacted
📍 Starting RocketReach search from offset 16
✅ Fetched 15 leads

[For each lead]
✅ ICP Match (score: 0.75)
📧 Generating email...
✅ Email passed review (score: 82)
📤 Sent to john@startup.com

============================================================
✅ ICP CAMPAIGN COMPLETE: 15 emails sent
============================================================
```

### Legacy Mode (JSON Config)

```bash
python auto_scheduler.py --legacy
```

---

## Testing

```bash
# Test full autonomous pipeline (dry run)
python -c "
from campaign_manager import CampaignManager
m = CampaignManager()
results = m.run_autonomous_campaign(max_leads=2, dry_run=True)
print(f'ICP: {results[\"icp_template\"]}')
print(f'Sent: {results[\"sent\"]}')
"

# Check ICP analytics
python -c "
from icp_manager import ICPManager
m = ICPManager()
m.print_analytics_report()
"

# Check scheduler config
python tests/test_scheduler_config.py

# Test email generation
python tests/test_email_generation.py

# Full pipeline test
python tests/test_full_pipeline.py
```

---

## LLM Configuration (Groq with Fallback Chain)

The system uses Groq as the primary LLM provider with automatic fallback:

```
┌─────────────────────────────────────────────────────────────────┐
│                    MODEL FALLBACK CHAIN                          │
│                                                                  │
│  1️⃣ llama-3.3-70b-versatile    →  1,000 req/day                 │
│         ↓ (if exhausted)                                        │
│  2️⃣ llama-3.1-70b-versatile    →  6,000 req/day                 │
│         ↓ (if exhausted)                                        │
│  3️⃣ llama-3.1-8b-instant       → 14,400 req/day                 │
│         ↓ (if exhausted)                                        │
│  4️⃣ llama3-70b-8192            →  6,000 req/day                 │
│         ↓ (if exhausted)                                        │
│  5️⃣ llama3-8b-8192             → 14,400 req/day                 │
│         ↓ (ALL exhausted)                                       │
│  6️⃣ OpenAI gpt-4o-mini         → Last resort fallback          │
│                                                                  │
│  Combined Groq capacity: 28,900 requests/day!                   │
└─────────────────────────────────────────────────────────────────┘
```

### Usage Tracking
- Usage is stored in MongoDB (`llm_usage` collection)
- Persists across process restarts
- Resets daily at midnight UTC
- Check usage with: `python check_groq_usage.py`

---

## ICP Tracking (TK Kader Framework)

The system implements TK Kader's Ideal Customer Profile framework for data-driven targeting:

### Core Principles

1. **10x Better** - Target prospects where we solve urgent problems better than alternatives
2. **Data-Backed** - ICP decisions informed by actual performance data, not wishlists
3. **Mobilize & Track** - Track ICP vs non-ICP throughout go-to-market, refine quarterly

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                    ICP TRACKING FLOW                             │
└─────────────────────────────────────────────────────────────────┘

1. Lead Classification (before sending)
   └── classify_lead_icp() scores each lead:
       ├── Title match (40%): Decision-maker titles (CTO, Founder, VP Eng)
       ├── Company signals (30%): Funded, growing, tech industry
       ├── Enrichment (20%): Hiring engineers, matching tech stack
       └── Template match (10%): Aligns with known ICP templates

2. Tracking (when sending)
   └── Email records include:
       ├── is_icp: True/False
       ├── icp_template: Which template matched
       └── icp_score: Confidence 0.0-1.0

3. Analytics (ongoing)
   └── get_icp_analytics() returns:
       ├── ICP vs Non-ICP reply rates
       ├── Performance by template
       └── Recommendations for refinement

4. Refinement (quarterly)
   └── AI generates new ICPs based on:
       ├── What's working (high reply rate templates)
       ├── What's not (underperforming templates)
       └── New opportunities from case studies
```

### CLI Commands

```bash
# View ICP performance analytics
python icp_manager.py analytics

# Generate a new ICP template from campaign goal
python icp_manager.py generate --goal "Series B fintech startups building payment infrastructure"

# Generate campaign config from existing ICP template
python icp_manager.py campaign --icp startup_founders_funded
```

### Example Analytics Output

```
📊 ICP PERFORMANCE ANALYTICS (TK Kader Framework)
============================================================

📧 Total Emails: 500 sent, 25 replied

🎯 ICP vs Non-ICP Performance:
----------------------------------------
  ICP Leads:
    Sent: 300, Replied: 20
    Reply Rate: 6.67%
  Non-ICP Leads:
    Sent: 200, Replied: 5
    Reply Rate: 2.5%

💡 Key Insights:
  • ICP leads convert 167% better than non-ICP leads

🎬 Recommendations:
  ✅ Double down on 'startup_founders_funded' - 8.5% reply rate
  🔄 Review these templates: legacy_modernization - zero replies
```

### Existing ICP Templates

| Template | Target | Pain Point |
|----------|--------|------------|
| `startup_founders_funded` | Funded startup founders | Ship faster with limited team |
| `ctos_at_capacity` | CTOs at growing companies | Team at capacity, roadmap slipping |
| `ai_prototype_hell` | Founders with AI ideas | Stuck between prototype and production |
| `legacy_modernization` | Enterprise VPs | Legacy system migration paralysis |
| `product_leaders_roadmap_slip` | Product leaders | Roadmap slip, can't hire fast enough |

---

## Deduplication

The system guarantees you **never email the same person twice**:

| Stage | Protection |
|-------|------------|
| RocketReach fetch | Checks DB for already-contacted emails before expensive lookups |
| Email verification | Multi-layer verification (syntax, MX, SMTP) |
| Campaign level | Double-checks before each send |
| Database | Unique index on email field |

---

## Performance Optimizations

| Metric | Before | After |
|--------|--------|-------|
| **Leads per search** | 0-5 results | 17K-305K results |
| **Bounce rate** | ~40% | ~0% (verified) |
| **LLM capacity** | 1K req/day | 28,900 req/day |
| **LLM persistence** | Lost on restart | Stored in MongoDB |
| **Email pass rate** | Variable | 100% first attempt |
| **API calls per email** | 4-6 | 2 (optimized prompts) |
| **Human input required** | Every campaign | **ZERO** |

### Key Improvements Made:
1. **Autonomous ICP selection**: AI picks best ICP based on historical performance
2. **MongoDB config storage**: No more JSON files, dynamic updates
3. **Multi-armed bandit**: Balances exploration (testing new ICPs) vs exploitation (using best performers)
4. **Search criteria**: Use keywords instead of narrow industry filters
5. **Pagination**: SearchOffsetTracker for iterating through large result sets
6. **Email verification**: Multi-layer (syntax → MX → SMTP) catches 100% of bounces
7. **LLM fallback**: Automatic model rotation when limits hit
8. **Usage persistence**: MongoDB-backed usage tracking survives restarts
9. **Self-improving prompts**: Learns from failures, injects fixes into generation
10. **Human-sounding output**: Strips AI patterns (em dashes, corporate words)
11. **Quality gate**: AI reviewer ensures emails meet guidelines before sending

---

## Project Structure

```
coldemails/
├── auto_scheduler.py            # Legacy entry - fully autonomous scheduler (MongoDB config)
├── main_v2.py                   # V2 entry - async pipeline with all workers
├── campaign_manager.py          # Campaign orchestration + autonomous pipeline
├── icp_manager.py               # ICP selection, analytics, TK Kader framework
├── email_generator.py           # AI email generation (Ollama/Groq + fallback chain)
├── email_reviewer.py            # Self-improving AI review system
├── email_verifier.py            # Multi-layer email verification
├── warmup_bidirectional.py      # 🔥 Bidirectional warmup (Zoho → Gmail test accounts)
├── primestrides_context.py      # Case studies, ICP templates, company context
├── rocketreach_client.py        # Lead discovery + deduplication
├── zoho_sender.py               # Legacy multi-account email sending (mode-aware)
├── reply_detector.py            # IMAP reply checking
├── database.py                  # MongoDB models + SchedulerConfig + SearchOffsetTracker
├── config.py                    # Environment config + PRODUCTION_ACCOUNTS routing
├── main.py                      # CLI interface
├── v2/                          # Async v2 pipeline
│   ├── scheduler.py             # Async orchestrator (all workers + warmup loop)
│   ├── pre_generator.py         # Draft pre-generation pipeline
│   ├── send_worker.py           # Async SMTP sender (uses PRODUCTION_ACCOUNTS)
│   ├── imap_worker.py           # Async IMAP reply/bounce detection
│   └── account_pool.py          # Account rotation + reputation tracking
├── utils/                       # Utility modules
│   ├── __init__.py
│   └── logging_utils.py         # Logging + retry decorators
├── data/                        # Author knowledge base
│   ├── author_knowledge.json
│   └── author_knowledge.md
├── docs/                        # Cold email strategy documentation
│   ├── cold-email-strategies-lead-gen-jay.txt
│   ├── secret-90-page-cold-email-strategy.txt
│   └── ...
├── tests/                       # Test files
│   ├── test_full_pipeline.py
│   ├── test_email_generation.py
│   ├── test_reviewer.py
│   └── ...
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
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

### UnboundLocalError: emails_collection
This was fixed. The system now uses `ec_bounce_check` for local imports to avoid Python scoping conflicts.

### Legacy Mode
If you prefer JSON config over MongoDB:
```bash
python auto_scheduler.py --legacy
```

---

## Manual CLI Commands

```bash
# Test email sending
python main.py test-email your@email.com

# Test RocketReach
python main.py test-rocketreach

# Create campaign manually
python main.py create "Target SaaS founders needing AI integration"

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

# Check Groq usage
python check_groq_usage.py

# Check ICP analytics
python -c "from icp_manager import ICPManager; ICPManager().print_analytics_report()"
```

---

## License

Private - PrimeStrides Internal Use Only
