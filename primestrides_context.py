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
            "launched HIPAA-compliant in just 8 weeks (others quoted 6 months)",
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
            "40+ sites now syncing in real-time, 60% faster inspections in 10 weeks",
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

# =============================================================================
# ICP TEMPLATES — Chris Do Framework + LeadGenJay Cold Email Targeting
# =============================================================================
#
# Chris Do's ICP Framework:
# 1. THE TRIFECTA: Joy (we love the work) + Money (they can pay) + Mission (aligned values)
# 2. PSYCHOGRAPHICS > DEMOGRAPHICS: Values, fears, spending logic, not just title/industry
# 3. "THE CRAP THEY DEAL WITH": Build empathy — understand their frustrations from vendors
# 4. "THE HUNGER": What are they STARVING for that we uniquely solve?
# 5. MATH DOESN'T LIE: If their company does <$5M revenue, your fee is "Peanuts" budget
# 6. HAPPY TO PAY: Target people who see your fee as a rounding error, not a stretch
#
# Each template includes:
# - persona: Named character (Chris Do: "when we gave him a name, he stuck to it")
# - psychographics: Values, fears, spending logic (what the LLM needs for empathetic emails)
# - the_crap_they_deal_with: Vendor frustrations — so we DON'T sound like those vendors
# - the_hunger: The urgent need — this drives the email's "poke the bear" line
# - rocketreach_filters: ACTUAL API params including company_size for qualified leads
# =============================================================================

ICP_TEMPLATES = {
    "funded_saas_founders": {
        "description": "Series A+ SaaS founders who raised $5M+ and need to ship product fast to hit milestones",

        # === CHRIS DO PERSONA (feeds into email generator for empathetic writing) ===
        "persona": {
            "name": "SaaS Founder Sarah",
            "archetype": "Funded founder racing against the clock",
            "age_range": "32-45",
            "income": "$200k-$400k salary + equity",
            "values": "Velocity and quality. She wants code that's 'acquisition-ready.'",
            "belief_system": "You are only as good as your domain boundaries. Ship fast but ship clean.",
            "fears": "Due diligence failing because of spaghetti code. Missing the Series B window because product is behind.",
            "spending_logic": "Spends $100-300k to 'buy back' her timeline. The money is VC capital — price is secondary to speed and quality.",
            "the_crap_they_deal_with": "Junior-heavy dev shops that hack features without considering architecture. Agencies that over-promise and under-deliver. Engineers who say '2 weeks' and mean '2 months'.",
            "the_hunger": "A senior engineering partner who ships production-ready features in weeks, not quarters. Needs to hit milestones before the next board meeting."
        },

        # === TRIFECTA ALIGNMENT (why WE want this client) ===
        "trifecta": {
            "joy": "Building real products from scratch with clean architecture",
            "money": "$100-300k projects funded by VC — price isn't the issue, speed is",
            "mission": "Helping founders turn ideas into real products that change their industry"
        },

        # === EMAIL GENERATION CONTEXT ===
        "single_pain_point": "raised money but can't ship fast enough to hit milestones before the next board meeting",
        "unique_angle": "we shipped an HR tech startup's AI system in 8 weeks — their CTO said he'd never use another agency",
        "relevant_case_study": "hr_tech_ai",
        "front_end_offer": "free 30-min architecture review — we'll look at your actual stack",

        # === ROCKETREACH SEARCH FILTERS (what actually goes to the API) ===
        "titles": ["CEO", "Founder", "Co-Founder", "CTO"],
        "industries": ["Software - General", "Information Services", "Internet & Digital Media", "Financial Services"],
        "company_size": ["11-50", "51-200"],  # Funded startups, not solo founders
        "location": ["United States", "Canada", "United Kingdom"],
        "keywords": ["SaaS", "Series A", "Series B", "venture-backed", "B2B software", "cloud platform"],
        "trigger_signals": ["recently raised funding", "hiring engineers", "launching new product"]
    },

    "scaling_ctos": {
        "description": "CTOs/VP Engs at mid-market companies (50-500 employees) whose teams are drowning",

        "persona": {
            "name": "Modernizing Michael",
            "archetype": "Engineering leader stretched past breaking point",
            "age_range": "38-52",
            "income": "$300k-$550k total comp",
            "values": "Integrity and 'measuring 100 times before cutting.' Hates vendor BS.",
            "belief_system": "Technical debt is a silent killer. Good architecture is the foundation of everything.",
            "fears": "Public failure of a migration or release that takes down production. Losing top engineers because they're stuck on maintenance.",
            "spending_logic": "Spends $150-400k on a proven partner to avoid a $2M internal mistake. Your fee is less than 2% of their infrastructure budget.",
            "the_crap_they_deal_with": "Burned by 'AI wrapper' agencies that didn't understand their stack. Offshore teams writing unmaintainable code. Recruiters who take 6 months to find anyone decent. Internal 'innovation theater' from leadership that adds scope without headcount.",
            "the_hunger": "Senior engineers who hit the ground running — no 3-month onboarding. Someone who understands their existing codebase constraints but doesn't use them as excuses."
        },

        "trifecta": {
            "joy": "Modernizing complex systems — turning legacy into something clean",
            "money": "$150-400k projects, recurring retainers, long-term relationships",
            "mission": "Helping engineering leaders actually deliver on their vision"
        },

        "single_pain_point": "team is stretched past capacity — backlog growing faster than they can hire, and the good engineers keep getting poached",
        "unique_angle": "senior engineers who hit the ground running — one client went from monthly deploys to 3.2x faster release cycles in 12 weeks",
        "relevant_case_study": "enterprise_modernization",
        "front_end_offer": "free technical roadmap session — we'll identify your top 3 engineering bottlenecks",

        "titles": ["CTO", "VP of Engineering", "Head of Engineering", "Engineering Director", "Director of Engineering"],
        "industries": ["Software - General", "Information Services", "Financial Services", "Internet & Digital Media", "Insurance - General"],
        "company_size": ["51-200", "201-500"],  # Mid-market — has budget, has pain
        "location": ["United States", "Canada", "United Kingdom"],
        "keywords": ["engineering", "software development", "platform", "SaaS", "fintech", "technology"],
        "trigger_signals": ["hiring multiple engineers", "recent funding", "digital transformation"]
    },

    "ai_stuck_enterprise": {
        "description": "Mid-to-large companies with AI demos stuck in prototype hell — need production-grade AI",

        "persona": {
            "name": "Innovating Isabella",
            "archetype": "Innovation leader who needs AI that actually works in production",
            "age_range": "40-55",
            "income": "$400k-$650k total comp",
            "values": "Innovation that solves real problems, not buzzword bingo. AI should augment humans, not replace them.",
            "belief_system": "A demo that works on a laptop and a system that works at scale are completely different things.",
            "fears": "Missing a breakthrough because the data was siloed in an old system. Getting burned by another 'AI agency' that delivers a chatbot wrapper and calls it enterprise AI.",
            "spending_logic": "Will pay $200-500k for a partner who understands RAG, fine-tuning, and production deployment — not just API wrappers.",
            "the_crap_they_deal_with": "AI hype-men who sell 'cloud-only' LLM solutions without understanding their data or compliance requirements. Internal teams that build cool demos but can't deploy to production. Vendors who don't understand their domain (healthcare, legal, finance).",
            "the_hunger": "A production AI system that handles real-world data at scale — not another demo. Someone who can go from prototype to deployed product in months, not years."
        },

        "trifecta": {
            "joy": "High-complexity AI work — RAG, production pipelines, data science",
            "money": "$200-500k projects with massive enterprise budgets behind them",
            "mission": "Shipping AI that actually makes a difference (healthcare, finance, ops)"
        },

        "single_pain_point": "AI prototypes that look great in demos but fall apart in production — the gap between POC and deployed system is killing their AI roadmap",
        "unique_angle": "we ship production AI, not demo-ware — one client's system handles 10k+ applications daily with 43% efficiency gains",
        "relevant_case_study": "hr_tech_ai",
        "front_end_offer": "free AI architecture review — we'll tell you exactly why your prototype isn't scaling",

        "titles": ["CTO", "VP of Engineering", "Head of AI", "Head of Engineering", "Chief Innovation Officer", "VP of Product"],
        "industries": ["Software - General", "Financial Services", "Hospitals & Healthcare", "Insurance - General", "Information Services"],
        "company_size": ["51-200", "201-500", "501-1000"],  # Companies with real AI budgets
        "location": ["United States", "Canada", "United Kingdom"],
        "keywords": ["artificial intelligence", "machine learning", "AI", "automation", "data science", "deep learning"],
        "trigger_signals": ["AI initiative", "hiring AI engineers", "data platform"]
    },

    "legacy_enterprise": {
        "description": "Enterprise companies (200-5000 employees) stuck on legacy systems that won't die",

        "persona": {
            "name": "Architectural Arthur",
            "archetype": "Senior technical leader at a large company who needs to modernize without breaking things",
            "age_range": "45-58",
            "income": "$350k-$550k total comp",
            "values": "Legacy and longevity. He builds things to last 20 years. Documentation and boundaries matter.",
            "belief_system": "A system is only as good as its documentation. You can't move fast if the foundation is crumbling. Multi-year rewrites are career suicide.",
            "fears": "Retiring and leaving behind a mess no one can maintain. A migration that takes down production systems affecting millions of users.",
            "spending_logic": "Spends $200-500k on a partner who will 'do it right' — not 'do it fast.' The ROI on modernization is immediate in deployment speed and ops cost reduction.",
            "the_crap_they_deal_with": "Offshore teams that write unreadable code. Internal managers pushing 'features over foundation.' Every vendor promises 'digital transformation' but nobody understands their 15-year-old COBOL/.NET monolith. Past modernization attempts that burned $1M+ and got scrapped.",
            "the_hunger": "A strangler-fig migration plan — modernize piece by piece without a risky big-bang rewrite. Engineers who understand legacy constraints but deliver modern solutions."
        },

        "trifecta": {
            "joy": "Strategic architectural work — designing the roadmap for complex transformations",
            "money": "$200-500k projects with long-term consulting retainers",
            "mission": "Turning 'legacy dinosaurs' into modern platforms that last another 20 years"
        },

        "single_pain_point": "legacy systems are the bottleneck holding back the entire business, but a multi-year rewrite isn't an option — they need incremental modernization that delivers results in weeks",
        "unique_angle": "we modernized an enterprise company's legacy stack in 12 weeks — 3.2x faster deployments and 41% cost reduction without a single day of downtime",
        "relevant_case_study": "enterprise_modernization",
        "front_end_offer": "free legacy assessment — we'll identify the 20% of your stack causing 80% of your pain",

        "titles": ["CTO", "VP of Engineering", "IT Director", "Head of Engineering", "Principal Architect", "Director of Engineering"],
        "industries": ["Financial Services", "Insurance - General", "Hospitals & Healthcare", "Retail - General", "Manufacturing"],
        "company_size": ["201-500", "501-1000", "1001-5000"],  # True enterprise — has budget AND legacy pain
        "location": ["United States", "Canada", "United Kingdom"],
        "keywords": ["legacy", "modernization", "migration", "enterprise", "digital transformation", "infrastructure"],
        "trigger_signals": ["digital transformation", "system upgrade", "hiring for modernization"]
    },

    "product_leaders_bottlenecked": {
        "description": "VP/Head of Product at growing companies where engineering is the bottleneck and roadmap keeps slipping",

        "persona": {
            "name": "Roadmap Rachel",
            "archetype": "Product leader who can't ship because engineering is underwater",
            "age_range": "35-50",
            "income": "$250k-$450k total comp",
            "values": "Execution and accountability. She measures everything and hates 'we'll ship it next sprint' lies.",
            "belief_system": "Product is only as good as its ability to ship. Strategy without execution is just a PowerPoint deck.",
            "fears": "Losing to competitors who ship faster. Board asking why the roadmap keeps slipping when they just raised funding.",
            "spending_logic": "Spends $100-250k to unblock the product roadmap. If one feature ships 3 months sooner, it's worth 10x the cost in retained customers.",
            "the_crap_they_deal_with": "Engineering giving vague estimates that always triple. Developers who gold-plate code instead of shipping. Being caught between customer demands and engineering reality. Every planning session ends with cutting scope.",
            "the_hunger": "An external team that ships features in weeks, not quarters — proves it with real results — and doesn't need 6 weeks of onboarding before they're productive."
        },

        "trifecta": {
            "joy": "Shipping real features that customers love — fast",
            "money": "$100-250k per engagement, often recurring quarterly",
            "mission": "Unblocking product teams so they can actually execute their vision"
        },

        "single_pain_point": "engineering is the bottleneck — features take 3x longer than planned and the roadmap keeps slipping while competitors ship faster",
        "unique_angle": "we ship features in weeks not quarters — one SaaS client went from idea to launch in 6 weeks and raised Series A three months later",
        "relevant_case_study": "saas_mvp",
        "front_end_offer": "free roadmap acceleration session — we'll identify the top 3 things slowing down your engineering output",

        "titles": ["VP of Product", "Head of Product", "Product Director", "CPO", "Director of Product"],
        "industries": ["Software - General", "Information Services", "Internet & Digital Media", "Financial Services"],
        "company_size": ["51-200", "201-500"],  # Big enough to have product teams, small enough to feel the pain
        "location": ["United States", "Canada", "United Kingdom"],
        "keywords": ["product", "SaaS", "platform", "software", "B2B", "product management"],
        "trigger_signals": ["hiring product engineers", "new product launch", "roadmap"]
    },

    "compliance_tech_leaders": {
        "description": "CTOs/CISOs at regulated companies (finance, healthcare, insurance) who need compliant software built fast",

        "persona": {
            "name": "Compliance-Driven Clara",
            "archetype": "Tech leader in regulated industry where security comes first and 'move fast and break things' is not an option",
            "age_range": "42-58",
            "income": "$400k-$600k total comp",
            "values": "Precision and security. She hates 'move fast and break things.' Every line of code must be auditable.",
            "belief_system": "AI is a tool for efficiency, not a replacement for human judgment. Compliance isn't overhead — it's the product.",
            "fears": "Data leaks through unvetted LLM integrations. A security incident that makes the news. Failing a regulatory audit because of sloppy vendor code.",
            "spending_logic": "Happily pays a premium ($200-500k) for 'engineering-first' partners who prioritize security over buzzwords. The ROI on compliance automation is immediate.",
            "the_crap_they_deal_with": "Internal IT teams resistant to change. 'Security consultants' who only offer generic checklists. Vendors who say 'we're HIPAA compliant' but can't explain how. Agencies that don't understand regulatory requirements (SOC2, HIPAA, PCI-DSS).",
            "the_hunger": "A technical partner who builds compliant, production-grade software without needing 6 months of 'compliance review.' Someone who gets it right the first time because they've done it before."
        },

        "trifecta": {
            "joy": "Building high-security, high-performance systems in regulated domains",
            "money": "$200-500k+ projects — compliance budgets are among the highest in any org",
            "mission": "Proving that regulated industries can innovate fast without cutting security corners"
        },

        "single_pain_point": "compliance requirements turn every 2-week feature into a 3-month project — they need engineers who ship compliant code from day one, not as an afterthought",
        "unique_angle": "we shipped a HIPAA-compliant health platform in 8 weeks — other agencies quoted 6 months minimum",
        "relevant_case_study": "healthtech_client",
        "front_end_offer": "free compliance architecture review — we'll audit your current stack for regulatory gaps",

        "titles": ["CTO", "CISO", "VP of Engineering", "Head of Engineering", "IT Director", "Chief Technology Officer"],
        "industries": ["Financial Services", "Insurance - General", "Hospitals & Healthcare", "Legal"],
        "company_size": ["51-200", "201-500", "501-1000"],  # Regulated companies with compliance budgets
        "location": ["United States", "Canada", "United Kingdom"],
        "keywords": ["compliance", "HIPAA", "SOC2", "security", "fintech", "healthcare", "regulated", "financial services"],
        "trigger_signals": ["compliance hiring", "security initiative", "regulatory"]
    },

    # =============================================================================
    # TIER 1 — Highest ROI Personas (start immediately)
    # =============================================================================

    "pe_portfolio_tech_leaders": {
        "description": "CTOs at PE-acquired companies facing forced tech consolidation under aggressive timelines",

        "persona": {
            "name": "Portfolio Pete",
            "archetype": "Tech leader at a PE-acquired company who inherited 3 redundant systems and a 12-month deadline",
            "age_range": "40-55",
            "income": "$350k-$550k total comp",
            "values": "Visible progress and pragmatism. PE partners want biweekly updates — not theory, not roadmaps, but working software.",
            "belief_system": "Consolidation done right pays for itself in 6 months. But 'rip and replace' is a fantasy — you modernize incrementally or you fail.",
            "fears": "Migration taking down production during peak season. Best engineers quitting during the chaos. PE partners losing confidence and bringing in their own 'technology advisor' who overrides every decision.",
            "spending_logic": "PE firm allocated $5-20M for operational improvements. A $200-400k engagement is a rounding error. If they DON'T consolidate, the PE firm's value creation thesis fails and his job is on the line.",
            "the_crap_they_deal_with": "Consulting firms that charge $3M for a PowerPoint roadmap and then leave. Big integrators that take 18 months with 40-person teams. Offshore teams writing unmaintainable code. PE operating partners who have zero technical understanding but demand weekly progress reports. The previous CTO left — institutional knowledge walked out the door.",
            "the_hunger": "A small senior engineering team that can assess their multi-system mess, build a consolidation plan, and start executing in weeks. Someone who shows visible progress to PE partners every 2 weeks — not another 6-month 'assessment phase.'"
        },

        "trifecta": {
            "joy": "Complex technical puzzles — consolidating messy multi-system landscapes",
            "money": "$200-400k projects backed by PE transformation budgets, often recurring for bolt-on acquisitions",
            "mission": "Proving that tech consolidation doesn't have to be a multi-year death march"
        },

        "single_pain_point": "PE firm expects tech consolidation done in 12 months — internal team is already stretched maintaining 3 redundant systems and the best engineers are leaving",
        "unique_angle": "we modernized an enterprise company's legacy stack in 12 weeks — 3.2x faster deployments and 41% cost reduction without a single day of downtime",
        "relevant_case_study": "enterprise_modernization",
        "front_end_offer": "free consolidation assessment — we'll map your 3 biggest integration bottlenecks in 30 minutes",

        "titles": ["CTO", "VP of Engineering", "VP of Technology", "Director of Engineering", "Head of Technology", "Chief Technology Officer", "VP of IT"],
        "industries": ["Business Services", "Financial Services", "Manufacturing", "Hospitals & Healthcare", "Insurance - General", "Software - General"],
        "company_size": ["201-500", "501-1000", "1001-5000"],
        "location": ["United States", "Canada", "United Kingdom"],
        "keywords": ["private equity", "portfolio company", "acquisition", "integration", "consolidation", "PE-backed", "mergers"],
        "trigger_signals": ["recent acquisition", "hiring integration roles", "new CTO appointment"]
    },

    "agency_whitelabel_partners": {
        "description": "Digital agency CEOs who sell app/web development but need a reliable white-label engineering partner",

        "persona": {
            "name": "Agency Alex",
            "archetype": "Agency owner who sells the work but needs someone to actually build it — reliably",
            "age_range": "35-50",
            "income": "$200k-$500k (agency revenue dependent)",
            "values": "Reliability and discretion. His reputation is built on client relationships, not code. He needs a partner who makes him look brilliant.",
            "belief_system": "The best agencies don't build everything in-house. They orchestrate the best talent. But the talent has to be invisible to the client.",
            "fears": "White-label partner embarrassing him in front of a $500k/year client. Partner communicating directly with the client and cutting him out. Being dependent on a single dev partner who holds him hostage on pricing.",
            "spending_logic": "Sells a $300k app build to client, pays PrimeStrides $150-200k, pockets $100-150k margin without hiring a single developer. One good partner = the entire engineering department he can't afford to build.",
            "the_crap_they_deal_with": "Offshore teams that miss deadlines and embarrass them in front of clients. Freelancers who disappear mid-project. Client-facing demos that crash because the dev team didn't QA. Constantly managing code quality instead of selling and growing the business.",
            "the_hunger": "A development partner who delivers production-quality work on time, communicates proactively, and NEVER embarrasses them in front of a client. Send a brief, get back working software in 6-8 weeks."
        },

        "trifecta": {
            "joy": "Consistent, high-trust partnerships — becoming someone's go-to engineering arm",
            "money": "$150-200k per project, 3-5 projects/year per agency = $500k-$1M recurring per partner",
            "mission": "Enabling agencies to punch above their weight and deliver real engineering"
        },

        "single_pain_point": "sells digital transformation to clients but relies on freelancers and offshore teams that miss deadlines and deliver buggy code — one bad delivery away from losing their biggest client",
        "unique_angle": "we white-label for agencies — you sell it, we build it, your clients never know. 8-week delivery, production-quality code, zero drama",
        "relevant_case_study": "saas_mvp",
        "front_end_offer": "let's do a pilot project together — one small build so you can test our work before committing",

        "titles": ["CEO", "Managing Director", "Founder", "Partner", "Head of Technology", "VP of Delivery", "Creative Director", "Chief Strategy Officer"],
        "industries": ["Advertising & Marketing", "Business Services", "Internet & Digital Media", "Management Consulting"],
        "company_size": ["11-50", "51-200"],
        "location": ["United States", "Canada", "United Kingdom"],
        "keywords": ["digital agency", "creative agency", "consulting", "digital transformation", "marketing agency", "web development", "advertising"],
        "trigger_signals": ["growing team", "new enterprise clients", "hiring freelance developers"]
    },

    "ops_leaders_manual_processes": {
        "description": "COOs/VP Ops at mid-market companies drowning in spreadsheets and manual processes in physical industries",

        "persona": {
            "name": "Operations Owen",
            "archetype": "Operations leader running a $50M+ business on spreadsheets, email chains, and 15-year-old software",
            "age_range": "42-58",
            "income": "$250k-$450k total comp",
            "values": "Simplicity and adoption. The best software is the one his field workers actually use. He measures success in hours saved, not features shipped.",
            "belief_system": "Technology should adapt to the operation, not the other way around. If it takes 4 hours to train someone, it's already failed.",
            "fears": "Building custom software nobody uses because it wasn't designed for the actual workflow. Workers in the field refusing to adopt new technology. The CEO asking why he 'wasted $200k on custom software' when there's a $50/month SaaS tool.",
            "spending_logic": "If a superintendent saves 2 hours/day across 40 job sites, that's $800k+/year in reclaimed labor. A $150-250k build pays for itself in under 4 months. Thinks in ROI and efficiency — show the math and the purchase order writes itself.",
            "the_crap_they_deal_with": "SaaS tools that promise 'customizable workflows' but can't handle their actual process. IT department that manages email and printers but doesn't build software. Freelancers from Upwork who missed deadlines and shipped buggy code. Vendors who don't understand that workers are on job sites with spotty internet. 'Digital transformation' consultants who propose $2M, 18-month projects.",
            "the_hunger": "Simple, purpose-built software that field workers actually use. Not a bloated enterprise platform — a lean tool that works offline, syncs when connected, and saves real hours every day."
        },

        "trifecta": {
            "joy": "Building software that changes how real-world operations run — tangible impact",
            "money": "$150-250k projects, often followed by Phase 2 and Phase 3 expansions",
            "mission": "Bringing modern software to industries that technology forgot"
        },

        "single_pain_point": "running critical operations on spreadsheets and email while losing $500k+ per year in manual labor, errors, and missed opportunities",
        "unique_angle": "we built an offline-first field platform for a construction company — inspection time dropped 60% across 40+ job sites in 10 weeks",
        "relevant_case_study": "construction_tech",
        "front_end_offer": "free workflow audit — we'll map your top 3 manual processes and estimate the ROI of automating them",

        "titles": ["COO", "VP of Operations", "Director of Operations", "Head of Operations", "VP of Supply Chain", "Operations Manager", "VP of Logistics"],
        "industries": ["Construction", "Manufacturing", "Logistics & Supply Chain", "Real Estate", "Utilities", "Agriculture"],
        "company_size": ["51-200", "201-500", "501-1000"],
        "location": ["United States", "Canada", "United Kingdom"],
        "keywords": ["operations", "field service", "logistics", "supply chain", "construction", "manufacturing", "warehouse"],
        "trigger_signals": ["operational efficiency", "digital transformation", "field service hiring"]
    },

    # =============================================================================
    # TIER 2 — Strong Fit Personas
    # =============================================================================

    "revenue_ops_leaders": {
        "description": "Revenue and growth leaders at B2B companies whose customer-facing tools are blocked by engineering priorities",

        "persona": {
            "name": "Revenue Ryan",
            "archetype": "Revenue leader whose growth is bottlenecked by crappy internal tools that engineering refuses to prioritize",
            "age_range": "35-48",
            "income": "$300k-$500k total comp (OTE)",
            "values": "Speed to revenue and customer experience. He measures everything in pipeline impact and churn reduction.",
            "belief_system": "Every month without proper customer tooling is lost revenue you never recover. Engineering doesn't own the customer relationship — he does.",
            "fears": "Churn climbing while waiting for engineering to 'get to it.' Board losing confidence because revenue growth is decelerating. Competitors shipping better customer experiences while he's stuck on spreadsheets.",
            "spending_logic": "If customer self-service reduces churn by 5%, that's $500k-$2M in saved annual revenue. A $150k build with 8-week delivery is the cheapest path to that outcome. Budget comes from 'revenue tools' or 'customer experience' — doesn't compete with engineering's budget.",
            "the_crap_they_deal_with": "Engineering always deprioritizes sales/CS tooling for 'core product.' Cobbled together Zapier/Airtable/spreadsheet workflows that break constantly. 'We'll get to it next quarter' — heard it for 3 quarters straight. Freelancers who build dashboards that look nice but fall apart at 1000 users.",
            "the_hunger": "An engineering partner who understands business metrics and customer experience. Someone who can build a customer portal, analytics dashboard, or integration layer that directly impacts revenue — shipped in weeks, not quarters."
        },

        "trifecta": {
            "joy": "Building customer-facing tools that directly drive revenue metrics",
            "money": "$150-300k per engagement, often recurring as the revenue team expands",
            "mission": "Empowering revenue teams to stop waiting on engineering and start shipping"
        },

        "single_pain_point": "customer-facing tools keep getting deprioritized by engineering — churn is climbing and the board wants answers, but the customer portal is still 'next quarter'",
        "unique_angle": "we built a full SaaS platform in 6 weeks — the founder raised Series A 3 months later. when revenue needs tooling, waiting isn't an option",
        "relevant_case_study": "saas_mvp",
        "front_end_offer": "free revenue tooling audit — we'll identify the #1 tool your customer team is missing and scope it in 30 minutes",

        "titles": ["Chief Revenue Officer", "VP of Sales", "VP of Revenue Operations", "VP of Customer Success", "Head of Growth", "VP of Business Development", "Head of Revenue Operations"],
        "industries": ["Software - General", "Information Services", "Financial Services", "Business Services", "Internet & Digital Media"],
        "company_size": ["51-200", "201-500"],
        "location": ["United States", "Canada", "United Kingdom"],
        "keywords": ["revenue operations", "customer success", "SaaS", "B2B", "growth", "sales operations", "software"],
        "trigger_signals": ["hiring revenue operations", "customer success expansion", "growth roles"]
    },

    "ecommerce_platform_leaders": {
        "description": "E-commerce leaders at DTC/B2B brands who've outgrown Shopify and need custom platform engineering",

        "persona": {
            "name": "E-Commerce Emma",
            "archetype": "E-commerce leader whose platform is the bottleneck to growth — outgrew Shopify, needs real engineering",
            "age_range": "35-50",
            "income": "$250k-$450k total comp",
            "values": "Conversion rate and customer experience. Every 100ms of page load time is money. She lives in analytics dashboards and A/B tests.",
            "belief_system": "The platform IS the product for DTC brands. If the checkout is slow, all the marketing spend in the world won't save you.",
            "fears": "New platform crashing on Black Friday. Migration losing 5 years of SEO rankings. Custom build that's harder to maintain than Shopify was. Getting locked into a vendor who holds the platform hostage.",
            "spending_logic": "A 1% improvement in conversion rate at $50M revenue = $500k/year. A 2-second reduction in page load = 15% more conversions. Custom checkout optimization = 20% reduction in cart abandonment. The math makes a $200-400k investment trivial.",
            "the_crap_they_deal_with": "Shopify apps conflicting and slowing the site to a crawl. Agencies that build 'beautiful' sites with 6-second load times. Platform agencies charging $200k for a skin on top of Shopify Plus. 3 different agencies touching different parts of the stack — nobody owns the whole picture. Theme customizations that break every Shopify update.",
            "the_hunger": "A technical partner who can architect a custom e-commerce platform that handles their catalog complexity, integrates with ERP/WMS, and performs at scale during Black Friday. Not another 'Shopify partner' — an actual engineering team."
        },

        "trifecta": {
            "joy": "High-performance platform engineering where milliseconds matter",
            "money": "$200-400k projects with ongoing optimization retainers",
            "mission": "Helping DTC brands break free from platform limitations and own their tech"
        },

        "single_pain_point": "outgrew Shopify but every 'platform migration' agency quotes 6 months and $500k+ — meanwhile conversion rates are dropping because the site can't handle their catalog complexity",
        "unique_angle": "we migrated a fintech's core platform in 10 weeks — 2.7x throughput, zero downtime. your Black Friday traffic deserves the same treatment",
        "relevant_case_study": "fintech_client",
        "front_end_offer": "free platform performance audit — we'll identify exactly what's killing your conversion rate in 30 minutes",

        "titles": ["VP of E-Commerce", "Head of Digital", "CTO", "VP of Digital Product", "Director of E-Commerce", "Head of E-Commerce", "Chief Digital Officer"],
        "industries": ["Retail - General", "Consumer Goods", "Wholesale", "Internet & Digital Media", "Food & Beverage"],
        "company_size": ["51-200", "201-500"],
        "location": ["United States", "Canada", "United Kingdom"],
        "keywords": ["e-commerce", "ecommerce", "DTC", "direct to consumer", "Shopify", "headless commerce", "retail", "online store"],
        "trigger_signals": ["platform migration", "hiring e-commerce developers", "replatforming"]
    },

    "marketplace_scale_founders": {
        "description": "Marketplace/platform founders whose MVP architecture is breaking under growth",

        "persona": {
            "name": "Marketplace Marcus",
            "archetype": "Marketplace founder whose platform was built for 500 users and now has 50,000 — everything is on fire",
            "age_range": "30-45",
            "income": "$200k-$400k salary + equity",
            "values": "Network effects and reliability. Every outage costs supply-side churn that takes months to rebuild. Uptime is everything.",
            "belief_system": "The platform is the moat. If it's unreliable, no amount of marketing fixes the supply-side exodus.",
            "fears": "Platform going down during a surge and losing the supply side permanently. Re-architecture breaking existing workflows and pissing off power users. Spending 6 months on infrastructure with nothing visible to show investors.",
            "spending_logic": "At $10M ARR growing 100% YoY, every month of platform instability costs $200k+ in churned providers. A $200-400k engagement to stabilize and scale is the cheapest insurance against growth stalling. Funded by VC capital with a mandate to 'invest in infrastructure.'",
            "the_crap_they_deal_with": "Internal team in permanent firefighting mode. Freelancers who built V1 and left behind zero documentation. Agencies that don't understand two-sided marketplace dynamics. The matching algorithm was hard-coded by a contractor and nobody understands it. Mobile app is a webview wrapper that crashes on Android.",
            "the_hunger": "Senior engineers who understand marketplace architecture — matching algorithms, real-time systems, trust/safety, payment flows. Someone who can re-architect the core while the internal team keeps the lights on."
        },

        "trifecta": {
            "joy": "Complex distributed systems — matching engines, real-time, multi-tenant scaling",
            "money": "$200-400k projects, often leading to ongoing retainers as marketplace grows",
            "mission": "Helping marketplace founders scale past the inflection point without burning out"
        },

        "single_pain_point": "marketplace MVP that proved product-market fit is now breaking under scale — every outage costs supply-side churn and the 5-person engineering team is drowning in support tickets",
        "unique_angle": "we scaled a fintech's transaction processing 2.7x in 10 weeks with zero downtime — your marketplace traffic needs the same treatment",
        "relevant_case_study": "fintech_client",
        "front_end_offer": "free architecture review — we'll pinpoint the top 3 bottlenecks in your marketplace platform in 30 minutes",

        "titles": ["CEO", "CTO", "Co-Founder", "Founder", "VP of Engineering", "Head of Engineering"],
        "industries": ["Internet & Digital Media", "Software - General", "Information Services", "Real Estate", "Business Services"],
        "company_size": ["11-50", "51-200"],
        "location": ["United States", "Canada", "United Kingdom"],
        "keywords": ["marketplace", "platform", "two-sided", "gig economy", "matching", "on-demand", "SaaS", "startup"],
        "trigger_signals": ["Series A funding", "Series B funding", "hiring platform engineers", "geographic expansion"]
    },

    # =============================================================================
    # TIER 3 — Good Personas (requires positioning nuance)
    # =============================================================================

    "data_analytics_modernizers": {
        "description": "Data/analytics leaders at enterprises stuck on legacy BI tools while the board demands AI-powered insights",

        "persona": {
            "name": "Data-Driven Diana",
            "archetype": "Data leader maintaining 200 legacy reports nobody trusts while the CEO demands AI-powered dashboards by next quarter",
            "age_range": "40-55",
            "income": "$350k-$550k total comp",
            "values": "Data integrity and governance. She'd rather ship nothing than ship insights built on dirty data. Accuracy is non-negotiable.",
            "belief_system": "A beautiful dashboard on dirty data is worse than no dashboard at all. Fix the foundation first, then build the intelligence layer.",
            "fears": "AI hallucinating insights that lead to wrong business decisions. Migrating data and breaking the CFO's downstream reports. The project expanding from 'build a dashboard' into 'rebuild the entire data warehouse.'",
            "spending_logic": "If real-time inventory analytics prevents $2M in overstocking/year, a $300k build is trivially justified. If self-service analytics eliminates 3 analyst positions ($450k/year), the ROI is immediate. Data modernization budgets are typically $1-5M.",
            "the_crap_they_deal_with": "Data engineers spending 80% of time on ETL maintenance. Business users who export everything to Excel because they don't trust the warehouse. 'AI' vendors who plug an LLM into their data without understanding schema or governance. Every department has their own 'single source of truth' (there are 7 of them). BI consultants who build beautiful Tableau dashboards on top of dirty data.",
            "the_hunger": "A modern data platform that business users actually use — real-time dashboards, self-service analytics, and properly governed AI insights. Engineers who understand data modeling AND can build the frontend."
        },

        "trifecta": {
            "joy": "Complex data engineering challenges — making messy data clean and useful",
            "money": "$200-400k projects, often a wedge into $1-5M data modernization programs",
            "mission": "Making enterprise data actually useful instead of just expensive to store"
        },

        "single_pain_point": "data team spends 80% of time maintaining legacy reports and 20% building what the business actually needs — the CEO wants AI dashboards by next quarter and the foundation isn't ready",
        "unique_angle": "we modernized an enterprise company's legacy stack in 12 weeks — 3.2x faster deployment, 41% cost cut. their team went from maintaining to building",
        "relevant_case_study": "enterprise_modernization",
        "front_end_offer": "free data architecture review — we'll identify the top 3 bottlenecks between your current data and the AI-powered insights your CEO wants",

        "titles": ["Chief Data Officer", "VP of Data", "VP of Analytics", "Head of Data Engineering", "Director of Business Intelligence", "VP of Business Intelligence", "Head of Analytics"],
        "industries": ["Financial Services", "Insurance - General", "Retail - General", "Manufacturing", "Hospitals & Healthcare", "Logistics & Supply Chain"],
        "company_size": ["201-500", "501-1000", "1001-5000"],
        "location": ["United States", "Canada", "United Kingdom"],
        "keywords": ["data analytics", "business intelligence", "data engineering", "data platform", "analytics", "data warehouse", "enterprise"],
        "trigger_signals": ["hiring data engineers", "analytics modernization", "data platform migration"]
    },

    "mobile_gap_leaders": {
        "description": "CTOs/VP Product at companies whose customers or field workers desperately need mobile access they don't have",

        "persona": {
            "name": "Mobile-First Mike",
            "archetype": "Tech leader whose users are 70% mobile but the company's mobile experience is an embarrassment",
            "age_range": "38-52",
            "income": "$300k-$500k total comp",
            "values": "User experience and reliability. An app that crashes is worse than no app. He'd rather delay launch than ship something with 2-star reviews.",
            "belief_system": "Mobile is the primary channel now — not a nice-to-have. If your field workers can't use it without WiFi, it's not a real mobile app.",
            "fears": "Launching an app that gets 1-star reviews and damages the brand. Building for iOS and having Android be an afterthought. The app needing a 'complete rebuild' in 18 months because it was built on the wrong framework.",
            "spending_logic": "If 70% of users are on mobile and the experience is driving 1-star reviews, they're losing customers daily. A $150-300k mobile build that moves ratings from 2.3 to 4.5 stars directly impacts acquisition. For field workers, a proper mobile tool saves 1-2 hours/day per worker — at 100 workers, that's $500k+/year.",
            "the_crap_they_deal_with": "Web agencies that say 'we'll make it responsive' and deliver a terrible experience. Cross-platform frameworks producing sluggish, non-native apps. Freelancers who build iOS and 'forget' Android. The agency that built the current app is gone and nobody has the source code. Push notifications that don't work, offline that doesn't sync.",
            "the_hunger": "A production-ready mobile app that users actually love — fast, reliable, works offline, and integrates with existing backend systems. Built by engineers who understand mobile-specific challenges, not web devs pretending."
        },

        "trifecta": {
            "joy": "Building polished mobile experiences with real-world constraints (offline, field use)",
            "money": "$150-300k per engagement, often followed by V2 and platform expansion",
            "mission": "Proving that mobile-first doesn't have to mean mobile-worst"
        },

        "single_pain_point": "customers or field workers need mobile access but the current 'app' is a broken webview wrapper — competitors at 4.7 stars while they're at 2.3",
        "unique_angle": "we built an offline-first mobile platform for a construction company — 60% faster inspections, real-time sync across 40+ job sites, works without cell signal",
        "relevant_case_study": "construction_tech",
        "front_end_offer": "free mobile audit — we'll review your current mobile experience and identify the top 3 things hurting adoption",

        "titles": ["CTO", "VP of Product", "Head of Digital", "VP of Engineering", "Chief Digital Officer", "CEO", "Director of Product"],
        "industries": ["Hospitals & Healthcare", "Real Estate", "Logistics & Supply Chain", "Construction", "Professional Services", "Education"],
        "company_size": ["51-200", "201-500"],
        "location": ["United States", "Canada", "United Kingdom"],
        "keywords": ["mobile app", "mobile", "digital transformation", "app development", "mobile platform", "iOS", "Android"],
        "trigger_signals": ["mobile app launch", "hiring mobile developers", "digital channel expansion"]
    },
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
    "Construction": {
        "founder": "field teams are still on paper forms and email while competitors go digital",
        "cto": "building software that works offline on job sites with spotty internet is a different beast",
        "ops": "every hour a superintendent spends on paperwork instead of managing the site costs real money",
    },
    "Manufacturing": {
        "founder": "your factory runs on 15-year-old software that nobody wants to touch but everyone depends on",
        "cto": "connecting shop floor systems to modern dashboards feels like duct-taping the past to the future",
        "ops": "manual data entry across disconnected systems means you're always working with yesterday's numbers",
    },
    "Logistics & Supply Chain": {
        "founder": "visibility across the supply chain is still a spreadsheet exercise in most companies your size",
        "cto": "integrating legacy warehouse systems with modern tracking tools is a full-time job nobody signed up for",
        "ops": "routing and dispatch still rely on tribal knowledge instead of real-time data",
    },
    "Retail - General": {
        "founder": "your e-commerce platform was built for 10x less traffic than you're getting now",
        "cto": "every shopify app you add slows the site down and Black Friday is always a prayer",
        "product": "the checkout experience is losing you conversions but the platform limits what you can customize",
    },
    "Advertising & Marketing": {
        "founder": "you sell digital transformation but your dev team is freelancers and offshore contractors held together with hope",
        "cto": "every client project is a scramble to find developers who won't embarrass you",
        "ops": "managing offshore teams takes more time than just building it yourself — but you can't scale that way",
    },
    "Business Services": {
        "founder": "your biggest client wants a custom portal but your team can barely maintain what's already built",
        "cto": "the PE firm wants tech consolidation done yesterday and your best engineers are already interviewing elsewhere",
        "ops": "three acquired companies means three different systems doing the same thing — and nobody knows which data to trust",
    },
    "Insurance - General": {
        "founder": "legacy policy systems are the bottleneck for every new product you try to launch",
        "cto": "modernizing claims processing without breaking the regulatory audit trail is a tightrope walk",
        "product": "customers expect a self-service portal but your tech stack was designed for agents, not end users",
    },
    "Real Estate": {
        "founder": "property management still runs on phone calls and spreadsheets while tenants expect an app",
        "cto": "connecting listing data, payments, and maintenance requests into one system sounds simple but never is",
        "ops": "field inspections generate paper that sits in a truck for a week before anyone enters the data",
    },
    "default": {
        "founder": "growing the business and building the product at the same time usually means neither gets full attention",
        "cto": "your best engineers are drowning in maintenance while the roadmap stalls",
        "product": "the features customers want keep getting pushed because engineering is underwater",
    }
}

# RocketReach uses specific industry names — alias them to our pain points
INDUSTRY_PAIN_POINTS["Hospitals & Healthcare"] = INDUSTRY_PAIN_POINTS["Healthcare"]
INDUSTRY_PAIN_POINTS["Software - General"] = INDUSTRY_PAIN_POINTS["Software"]
INDUSTRY_PAIN_POINTS["Information Services"] = INDUSTRY_PAIN_POINTS["Technology"]
INDUSTRY_PAIN_POINTS["Management Consulting"] = INDUSTRY_PAIN_POINTS["Advertising & Marketing"]
INDUSTRY_PAIN_POINTS["Professional Services"] = INDUSTRY_PAIN_POINTS["Business Services"]
INDUSTRY_PAIN_POINTS["Consumer Goods"] = INDUSTRY_PAIN_POINTS["Retail - General"]
INDUSTRY_PAIN_POINTS["Wholesale"] = INDUSTRY_PAIN_POINTS["Retail - General"]
INDUSTRY_PAIN_POINTS["Food & Beverage"] = INDUSTRY_PAIN_POINTS["Retail - General"]
INDUSTRY_PAIN_POINTS["Legal"] = INDUSTRY_PAIN_POINTS["Insurance - General"]
INDUSTRY_PAIN_POINTS["Utilities"] = INDUSTRY_PAIN_POINTS["Manufacturing"]
INDUSTRY_PAIN_POINTS["Education"] = INDUSTRY_PAIN_POINTS["Healthcare"]
INDUSTRY_PAIN_POINTS["Agriculture"] = INDUSTRY_PAIN_POINTS["Construction"]

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
