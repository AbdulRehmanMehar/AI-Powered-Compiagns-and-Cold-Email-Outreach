"""
PrimeStrides Company Context - Expert Cold Email Strategies
Updated to align with Eric Nowoslawski's 90-page doc + LeadGenJay's masterclass

Key changes:
- Added REAL case studies with SPECIFIC numbers (3.72x not "4x")
- Added unique angles that ONLY PrimeStrides can claim
- Added spintax templates for copy variation
- Added front-end offers for lower friction CTAs
"""

COMPANY_CONTEXT = """
# About PrimeStrides

PrimeStrides is a boutique software development agency that ships production-ready software and AI systems.

## What Makes Us UNIQUELY Different (what no one else can claim)
- **Direct access to senior engineers** - No account managers, no layers. You talk to the people writing code.
- **8-week shipping guarantee** - We've shipped 50+ projects on this timeline. Not a promise - a track record.
- **Zero offshore/outsourcing** - Your project never touches an overseas team. Ever.
- **Small by design** - Max 4 active projects at a time. We're selective because quality matters.

## Real Case Studies (USE THESE - they're our competitive advantage)
1. **HR Tech Startup** - AI job application system shipped in 8 weeks. Cut their manual processing by 43%. Their CTO: "I'd never go back to a traditional agency."
2. **B2B SaaS Startup** - MVP to launch in 6 weeks. Raised Series A 3 months after launch.
3. **Enterprise Staffing Company** - Legacy system modernization. 3.2x faster deployment cycles. Cut operational costs 41%.

## Our Ideal Clients (by persona)
1. **Startup founders** - Building technical products, burned by agencies before, need to ship fast
2. **CTOs hitting capacity** - Team stretched thin, need senior talent without 3-month hiring cycle
3. **Product leaders** - Features taking too long, roadmap slipping, engineering is the bottleneck
4. **Companies stuck in AI prototype hell** - Built demos that don't work in production

## What We Say That NO ONE ELSE CAN
- "We shipped an AI system in 8 weeks - their CTO said he'd never use another agency"
- "Zero offshore. Your project never touches an overseas team."
- "Max 4 active projects. We turn down work to maintain quality."
- "50+ projects shipped on 8-week timelines - not a promise, a track record"

## Front-End Offers (low friction, high value)
1. Free 30-min architecture review (we actually look at their stack)
2. "12 things startups mess up before Series A" checklist
3. Free technical roadmap session
4. Code review of one critical component
"""

# Real case studies with SPECIFIC numbers (not rounded)
# LeadGenJay: "Use REAL numbers like 3.72x, not 4x - specifics build trust"
# ADDED: company_hint and result_variations for varied email presentation
# Case studies with ANONYMOUS company references (no client names disclosed)
# Use descriptive industry terms instead of actual company names
CASE_STUDIES = {
    # HR Tech AI case study (aliases: roboapply, hr_tech_ai)
    "hr_tech_ai": {
        "company_name": "an HR tech startup",
        "company_hint": "an HR startup",  # Short version for emails
        "industry": "HR Tech / AI",
        "what_we_built": "AI-powered job application automation system",
        "timeline": "8 weeks",
        "result": "43% reduction in manual processing time",
        "result_short": "43% faster processing",
        "result_variations": [
            "cut manual processing 43%",
            "reduced hiring workflow time by 43%",
            "went from weeks of manual review to 43% faster automation",
        ],
        "quote": "I'd never go back to a traditional agency - PrimeStrides shipped faster than our internal team could have.",
        "person": "CTO",
        "relevance": ["AI", "automation", "startups", "fast shipping", "HR tech"]
    },
    # SaaS MVP case study (aliases: stratmap, saas_mvp)
    "saas_mvp": {
        "company_name": "a B2B SaaS startup",
        "company_hint": "a SaaS founder",
        "industry": "SaaS / Strategy",
        "what_we_built": "Full MVP - strategy mapping platform",
        "timeline": "6 weeks",
        "result": "Raised Series A 3 months after launch",
        "result_short": "Series A in 3 months post-launch",
        "result_variations": [
            "went from idea to Series A in under 4 months",
            "launched in 6 weeks, closed Series A 3 months later",
            "hit Series A velocity - 6 weeks to launch, funding 3 months after",
        ],
        "quote": "They treated our MVP like a real product, not a throwaway prototype.",
        "person": "Founder",
        "relevance": ["MVP", "startups", "fundraising", "SaaS", "B2B"]
    },
    # Enterprise modernization case study (aliases: timpl, enterprise_modernization)
    "enterprise_modernization": {
        "company_name": "an enterprise staffing company",
        "company_hint": "an enterprise company",
        "industry": "Enterprise / Staffing",
        "what_we_built": "Legacy system modernization",
        "timeline": "12 weeks",
        "result": "3.2x faster deployment cycles, 41% operational cost reduction",
        "result_short": "3.2x faster deploys, 41% cost cut",
        "result_variations": [
            "3.2x faster deploy cycles and 41% cost savings",
            "went from monthly deploys to 3.2x faster releases",
            "slashed deploy time to 1/3rd and cut ops costs 41%",
        ],
        "quote": "Finally - engineers who understood our legacy constraints but didn't use them as excuses.",
        "person": "VP Engineering",
        "relevance": ["legacy", "modernization", "enterprise", "cost reduction", "staffing"]
    },
    "fintech_client": {
        "company_name": "a Series B fintech",
        "company_hint": "a fintech team",
        "industry": "FinTech",
        "what_we_built": "Payment processing overhaul",
        "timeline": "10 weeks",
        "result": "Transaction throughput up 2.7x, zero downtime migration",
        "result_short": "2.7x throughput, zero downtime",
        "result_variations": [
            "2.7x transaction throughput with zero downtime",
            "scaled to 2.7x volume without dropping a single transaction",
            "went from bottlenecked to 2.7x capacity in 10 weeks",
        ],
        "quote": "We expected a 6-month project. They did it in 10 weeks.",
        "person": "CTO",
        "relevance": ["fintech", "payments", "scale", "enterprise", "B2B"]
    },
    "healthtech_client": {
        "company_name": "a HIPAA-compliant health startup",
        "company_hint": "a healthtech startup",
        "industry": "HealthTech",
        "what_we_built": "Patient data platform with HIPAA compliance",
        "timeline": "8 weeks",
        "result": "Full HIPAA compliance + launch in under 2 months",
        "result_short": "HIPAA-compliant launch in 8 weeks",
        "result_variations": [
            "full HIPAA compliance in 8 weeks (others quoted 6 months)",
            "launched HIPAA-compliant in 2 months flat",
            "went from zero to HIPAA-certified production in 8 weeks",
        ],
        "quote": "Other agencies said 6 months minimum for HIPAA. They did it in 8 weeks.",
        "person": "CEO",
        "relevance": ["healthtech", "HIPAA", "compliance", "healthcare", "startups", "medical"]
    },
    "construction_tech": {
        "company_name": "a construction tech company",
        "company_hint": "a construction tech team",
        "industry": "Construction Tech",
        "what_we_built": "Field data sync platform with offline-first architecture",
        "timeline": "10 weeks",
        "result": "Site inspection time cut 60%, real-time sync across 40+ job sites",
        "result_short": "60% faster inspections, 40+ sites synced",
        "result_variations": [
            "cut site inspection time 60% across 40+ job sites",
            "went from day-old data to real-time sync in 10 weeks",
            "40+ sites now syncing in real-time, 60% faster inspections",
        ],
        "quote": "Finally software that works when there's no cell signal.",
        "person": "VP Operations",
        "relevance": ["construction", "field service", "infrastructure", "logistics", "operations", "offline"]
    }
}

# Backward-compatible aliases for case studies (for any code using old keys)
CASE_STUDIES["roboapply"] = CASE_STUDIES["hr_tech_ai"]
CASE_STUDIES["stratmap"] = CASE_STUDIES["saas_mvp"]
CASE_STUDIES["timpl"] = CASE_STUDIES["enterprise_modernization"]

# ICP templates with expert-aligned targeting
ICP_TEMPLATES = {
    "startup_founders_funded": {
        "description": "Startup founders who recently raised funding and need to ship",
        "titles": ["CEO", "Founder", "Co-Founder", "CTO"],
        "industries": ["Technology", "Software", "Internet", "SaaS", "FinTech", "HealthTech"],
        "company_size": "1-50",
        "trigger_signals": ["recently raised", "hiring engineers", "launching new product"],
        "single_pain_point": "need to ship fast but can't find reliable senior talent",
        "unique_angle": "we shipped an HR tech startup's AI system in 8 weeks - their CTO won't use another agency",
        "relevant_case_study": "hr_tech_ai",
        "front_end_offer": "free 30-min architecture review"
    },
    "ctos_at_capacity": {
        "description": "CTOs and engineering leaders whose teams are stretched thin",
        "titles": ["CTO", "VP of Engineering", "Head of Engineering", "Engineering Director"],
        "industries": ["Technology", "Software", "SaaS", "E-commerce", "FinTech"],
        "company_size": "20-200",
        "trigger_signals": ["hiring multiple engineers", "launching new initiatives", "recent funding"],
        "single_pain_point": "team is stretched thin and can't hire fast enough",
        "unique_angle": "senior engineers who hit the ground running - no 3-month ramp up",
        "relevant_case_study": "enterprise_modernization",
        "front_end_offer": "free technical roadmap session"
    },
    "ai_prototype_hell": {
        "description": "Companies with AI demos that don't work in production",
        "titles": ["CEO", "CTO", "VP of Engineering", "Head of AI", "Head of Product"],
        "industries": ["Technology", "Software", "Financial Services", "Healthcare", "Legal"],
        "company_size": "10-500",
        "trigger_signals": ["hiring AI engineers", "AI initiative mentioned", "automation focus"],
        "single_pain_point": "AI prototypes that look good in demos but fail in production",
        "unique_angle": "we ship production AI, not demo-ware - one client's AI handles 10k+ applications daily",
        "relevant_case_study": "hr_tech_ai",
        "front_end_offer": "free AI architecture review - we'll tell you why it's not working"
    },
    "legacy_modernization": {
        "description": "Companies with legacy systems holding them back",
        "titles": ["CTO", "VP of Engineering", "IT Director", "Head of Engineering"],
        "industries": ["Financial Services", "Healthcare", "Insurance", "Manufacturing", "Retail"],
        "company_size": "100-1000",
        "trigger_signals": ["digital transformation", "system upgrade mentioned", "hiring for modernization"],
        "single_pain_point": "legacy systems are the bottleneck but multi-year rewrites aren't an option",
        "unique_angle": "we modernized an enterprise company's legacy stack in 12 weeks - 3.2x faster deployments, 41% cost cut",
        "relevant_case_study": "enterprise_modernization",
        "front_end_offer": "free legacy assessment - we'll identify the 20% causing 80% of your pain"
    },
    "product_leaders_roadmap_slip": {
        "description": "Product leaders whose roadmap keeps slipping",
        "titles": ["VP of Product", "Head of Product", "Product Director", "CPO"],
        "industries": ["Technology", "Software", "SaaS", "E-commerce", "FinTech"],
        "company_size": "20-200",
        "trigger_signals": ["hiring product engineers", "new product launch", "roadmap planning"],
        "single_pain_point": "engineering is the bottleneck - features take 3x longer than planned",
        "unique_angle": "we ship features in weeks not quarters - one SaaS client went idea to launch in 6 weeks",
        "relevant_case_study": "saas_mvp",
        "front_end_offer": "free roadmap acceleration session"
    }
}

# Industry-specific pain points for better targeting
# LeadGenJay: "The pain point must be SPECIFIC to their world, not generic"
INDUSTRY_PAIN_POINTS = {
    "Technology": {
        "founder": "shipping features while also fundraising and hiring is a juggling act that usually drops something",
        "cto": "your backlog is growing faster than your team, and the good engineers are getting poached",
        "product": "every sprint ends with less done than planned because the technical debt keeps compounding",
    },
    "Financial Services": {
        "founder": "compliance keeps blocking releases while competitors ship weekly",
        "cto": "maintaining uptime on legacy systems while building new features is impossible with current headcount",
        "product": "every new feature needs 3 months of security review before it can ship",
    },
    "Software": {
        "founder": "you're competing with companies that have 10x your engineering team",
        "cto": "your senior engineers are stuck maintaining instead of building the next thing",
        "product": "the gap between what you promised customers and what engineering can deliver keeps growing",
    },
    "Internet & Digital Media": {
        "founder": "scaling infrastructure while adding features means something always breaks",
        "cto": "every traffic spike becomes an all-hands emergency because there's no bandwidth for proper architecture",
        "product": "user feedback comes in faster than your team can ship fixes",
    },
    "Healthcare": {
        "founder": "HIPAA compliance turns every 2-week feature into a 3-month project",
        "cto": "finding engineers who understand both healthcare compliance AND modern architecture is nearly impossible",
        "product": "clinical workflows need to be perfect the first time - there's no 'move fast and break things' in healthcare",
    },
    "Human Resources & Staffing": {
        "founder": "candidates expect a modern experience but your tech stack was built in 2015",
        "cto": "integrating with 50 different ATS systems while keeping your core product moving forward",
        "product": "recruiters need features yesterday but engineering is stuck on integrations",
    },
    "default": {
        "founder": "growing the business and building the product at the same time usually means neither gets full attention",
        "cto": "your best engineers are drowning in maintenance while the roadmap stalls",
        "product": "the features customers want keep getting pushed because engineering is underwater",
    }
}

# Spintax templates for copy variation (prevents copy burning)
SPINTAX_TEMPLATES = {
    "greetings": [
        "{hey|hi|yo}",
    ],
    "saw_something": [
        "{saw|noticed|came across} something {interesting|cool|worth mentioning}",
        "{random|quick} question",
        "this might be {off base|totally wrong} but"
    ],
    "cta_soft": [
        "{worth a quick chat?|make sense to connect?|open to hearing more?}",
        "{interested?|worth exploring?|want to hear more?}",
        "if {that resonates|you're facing something similar|this sounds familiar}, {happy to chat|let's connect}"
    ],
    "sign_off": [
        "{best|cheers|talk soon}",
        "{- the primestrides team|best, primestrides team}",
    ],
    "value_add": [
        "{fwiw|one thing I forgot|quick thought}",
        "{might be relevant|could be useful|thought you'd want to know}"
    ]
}

# Email configuration
EMAIL_CONTEXT = {
    "sender_name": "PrimeStrides Team",
    "company_name": "PrimeStrides",
    "website": "primestrides.com",
    
    # Soft CTAs only - never "schedule a call"
    "approved_ctas": [
        "worth a quick chat?",
        "make sense to connect?",
        "open to hearing more?",
        "interested?",
        "want me to share how?",
    ],
    
    # BANNED phrases (from experts)
    "banned_phrases": [
        "I hope this email finds you well",
        "reaching out",
        "touching base",
        "circling back",
        "just following up",
        "leverage",
        "synergy",
        "streamline",
        "quick question",  # burned subject line
        "partnership opportunity",
        "I'd love to",
        "I wanted to",
        "My name is",
    ],
    
    # Subject line rules
    "subject_rules": {
        "max_words": 4,
        "style": "looks like from a colleague",
        "banned": ["Quick question", "Partnership", "Intro", "Opportunity"],
        "good_examples": ["{first_name}?", "thought about this", "re: {company}", "saw something", "one idea"]
    },
    
    # Sequence rules (from experts)
    "sequence_rules": {
        "max_emails": 3,
        "email_1": {"type": "initial", "thread": "new", "max_words": 75},
        "email_2": {"type": "followup", "thread": "same", "max_words": 50, "days_after": 3},
        "email_3": {"type": "different_angle", "thread": "new", "max_words": 60, "days_after": 5}
    }
}

# Realistic benchmarks (from Eric's data)
BENCHMARKS = {
    "expected_reply_rate": "0.3% - 1%",  # 1 positive per 100-350 contacts
    "good_reply_rate": "1%+",
    "excellent_reply_rate": "2%+",  # rare, usually niche/event campaigns
    "note": "If you're getting 1% positive reply rate, you're doing well. Scale from there."
}
