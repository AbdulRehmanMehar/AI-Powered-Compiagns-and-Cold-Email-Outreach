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
CASE_STUDIES = {
    "roboapply": {
        "company_name": "an HR tech startup",
        "industry": "HR Tech / AI",
        "what_we_built": "AI-powered job application automation system",
        "timeline": "8 weeks",
        "result": "43% reduction in manual processing time",
        "result_short": "43% faster processing",
        "quote": "I'd never go back to a traditional agency - PrimeStrides shipped faster than our internal team could have.",
        "person": "CTO",
        "relevance": ["AI", "automation", "startups", "fast shipping", "HR tech"]
    },
    "stratmap": {
        "company_name": "a B2B SaaS startup",
        "industry": "SaaS / Strategy",
        "what_we_built": "Full MVP - strategy mapping platform",
        "timeline": "6 weeks",
        "result": "Raised Series A 3 months after launch",
        "result_short": "Series A in 3 months post-launch",
        "quote": "They treated our MVP like a real product, not a throwaway prototype.",
        "person": "Founder",
        "relevance": ["MVP", "startups", "fundraising", "SaaS", "B2B"]
    },
    "timpl": {
        "company_name": "an enterprise staffing company",
        "industry": "Enterprise / Staffing",
        "what_we_built": "Legacy system modernization",
        "timeline": "12 weeks",
        "result": "3.2x faster deployment cycles, 41% operational cost reduction",
        "result_short": "3.2x faster deploys, 41% cost cut",
        "quote": "Finally - engineers who understood our legacy constraints but didn't use them as excuses.",
        "person": "VP Engineering",
        "relevance": ["legacy", "modernization", "enterprise", "cost reduction", "staffing"]
    },
    "fintech_client": {
        "company_name": "a Series B fintech",
        "industry": "FinTech",
        "what_we_built": "Payment processing overhaul",
        "timeline": "10 weeks",
        "result": "Transaction throughput up 2.7x, zero downtime migration",
        "result_short": "2.7x throughput, zero downtime",
        "quote": "We expected a 6-month project. They did it in 10 weeks.",
        "person": "CTO",
        "relevance": ["fintech", "payments", "scale", "enterprise", "B2B"]
    },
    "healthtech_client": {
        "company_name": "a HIPAA-compliant health startup",
        "industry": "HealthTech",
        "what_we_built": "Patient data platform with HIPAA compliance",
        "timeline": "8 weeks",
        "result": "Full HIPAA compliance + launch in under 2 months",
        "result_short": "HIPAA-compliant launch in 8 weeks",
        "quote": "Other agencies said 6 months minimum for HIPAA. They did it in 8 weeks.",
        "person": "CEO",
        "relevance": ["healthtech", "HIPAA", "compliance", "healthcare", "startups"]
    }
}

# ICP templates with expert-aligned targeting
ICP_TEMPLATES = {
    "startup_founders_funded": {
        "description": "Startup founders who recently raised funding and need to ship",
        "titles": ["CEO", "Founder", "Co-Founder", "CTO"],
        "industries": ["Technology", "Software", "Internet", "SaaS", "FinTech", "HealthTech"],
        "company_size": "1-50",
        "trigger_signals": ["recently raised", "hiring engineers", "launching new product"],
        "single_pain_point": "need to ship fast but can't find reliable senior talent",
        "unique_angle": "we shipped RoboApply's AI in 8 weeks - their CTO said he'd never use another agency",
        "relevant_case_study": "roboapply",
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
        "relevant_case_study": "timpl",
        "front_end_offer": "free technical roadmap session"
    },
    "ai_prototype_hell": {
        "description": "Companies with AI demos that don't work in production",
        "titles": ["CEO", "CTO", "VP of Engineering", "Head of AI", "Head of Product"],
        "industries": ["Technology", "Software", "Financial Services", "Healthcare", "Legal"],
        "company_size": "10-500",
        "trigger_signals": ["hiring AI engineers", "AI initiative mentioned", "automation focus"],
        "single_pain_point": "AI prototypes that look good in demos but fail in production",
        "unique_angle": "we ship production AI, not demo-ware - RoboApply's AI handles 10k+ applications daily",
        "relevant_case_study": "roboapply",
        "front_end_offer": "free AI architecture review - we'll tell you why it's not working"
    },
    "legacy_modernization": {
        "description": "Companies with legacy systems holding them back",
        "titles": ["CTO", "VP of Engineering", "IT Director", "Head of Engineering"],
        "industries": ["Financial Services", "Healthcare", "Insurance", "Manufacturing", "Retail"],
        "company_size": "100-1000",
        "trigger_signals": ["digital transformation", "system upgrade mentioned", "hiring for modernization"],
        "single_pain_point": "legacy systems are the bottleneck but multi-year rewrites aren't an option",
        "unique_angle": "we modernized Timpl's legacy stack in 12 weeks - 3.2x faster deployments, 41% cost cut",
        "relevant_case_study": "timpl",
        "front_end_offer": "free legacy assessment - we'll identify the 20% causing 80% of your pain"
    },
    "product_leaders_roadmap_slip": {
        "description": "Product leaders whose roadmap keeps slipping",
        "titles": ["VP of Product", "Head of Product", "Product Director", "CPO"],
        "industries": ["Technology", "Software", "SaaS", "E-commerce", "FinTech"],
        "company_size": "20-200",
        "trigger_signals": ["hiring product engineers", "new product launch", "roadmap planning"],
        "single_pain_point": "engineering is the bottleneck - features take 3x longer than planned",
        "unique_angle": "we ship features in weeks not quarters - StratMap went idea to launch in 6 weeks",
        "relevant_case_study": "stratmap",
        "front_end_offer": "free roadmap acceleration session"
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
