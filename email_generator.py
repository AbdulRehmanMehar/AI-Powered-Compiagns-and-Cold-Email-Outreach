"""
Cold Email Generator - PROPERLY Aligned with LeadGenJay/Eric Nowoslawski Guidelines

Key principles implemented:
1. ACTUAL research on company before writing (problem sniffing)
2. First line must be SPECIFIC to the company - no generic "saw something interesting"
3. ONE pain point per email, matched to the lead's industry/role
4. Case studies matched by relevance, not copy-pasted everywhere
5. Under 75 words (ideally 50-60)
6. Subject looks like colleague sent it (2-4 words)
7. Soft CTA only - never "schedule a call"
8. NO corporate jargon, NO lies, NO fluff
9. SOUND HUMAN - no em dashes, no AI words, use contractions

"If you can't say what you saw that was interesting, don't say you saw something." - LeadGenJay
"""

from typing import Dict, Any, List, Optional
import config
import json
import random
import re
import time
import datetime
import logging
from primestrides_context import COMPANY_CONTEXT, ICP_TEMPLATES, EMAIL_CONTEXT, CASE_STUDIES

# Module logger
logger = logging.getLogger(__name__)


# =============================================================================
# HUMANIZE EMAIL - STRIP AI TELLS
# =============================================================================

def humanize_email(text: str) -> str:
    """
    Post-process email to remove AI writing tells.
    This is a safety net to catch anything the LLM slips through.
    """
    if not text:
        return text
    
    # Replace em dashes with comma or period (context-aware)
    text = re.sub(r'\s*—\s*', ', ', text)  # Em dash → comma
    text = re.sub(r'\s*–\s*', ', ', text)  # En dash → comma
    text = re.sub(r'…', '...', text)  # Fancy ellipsis → simple
    
    # Fix double commas that might result
    text = re.sub(r',\s*,', ',', text)
    text = re.sub(r',\s*\.', '.', text)
    
    # Replace AI words with simpler alternatives
    ai_word_replacements = {
        r'\bdelve into\b': 'look at',
        r'\bdelving into\b': 'looking at',
        r'\bdelve\b': 'dig',
        r'\bdelving\b': 'digging',
        r'\butilize\b': 'use',
        r'\butilizing\b': 'using',
        r'\bleverage\b': 'use',
        r'\bleveraging\b': 'using',
        r'\bfacilitate\b': 'help',
        r'\bfacilitating\b': 'helping',
        r'\brobust\b': 'solid',
        r'\bseamless\b': 'smooth',
        r'\bseamlessly\b': 'smoothly',
        r'\bpivotal\b': 'key',
        r'\belevate\b': 'improve',
        r'\belevating\b': 'improving',
        r'\bharness\b': 'use',
        r'\bharnessing\b': 'using',
        r'\bfoster\b': 'build',
        r'\bfostering\b': 'building',
        r'\bbolster\b': 'strengthen',
        r'\bunderscores?\b': 'shows',
        r'\bmyriad\b': 'many',
        r'\bplethora\b': 'lots of',
        r'\bmultifaceted\b': 'complex',
        r'\bnuanced\b': 'detailed',
        r'\bembark on\b': 'start',
        r'\bembarking on\b': 'starting',
        r'\bembark\b': 'start',
        r'\bembarking\b': 'starting',
        r'\bspearhead\b': 'lead',
        r'\bspearheading\b': 'leading',
        r'\blandscape\b': 'space',
        r'\brealm\b': 'area',
    }
    
    for pattern, replacement in ai_word_replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    # Remove AI transition phrases
    ai_transitions = [
        r'\bfurthermore,?\s*',
        r'\bmoreover,?\s*',
        r'\badditionally,?\s*',
        r'\bimportantly,?\s*',
        r'\bnotably,?\s*',
        r'\bessentially,?\s*',
        r'\bfundamentally,?\s*',
        r'\bultimately,?\s*',
        r'\binterestingly,?\s*',
        r'\bcrucially,?\s*',
        r"\bit's worth noting that\s*",
        r'\bworth noting that\s*',
        r'\bin essence,?\s*',
        r'\bat its core,?\s*',
        r"\bin today's\s+\w+\s*",  # "in today's landscape/market/world"
    ]
    
    for pattern in ai_transitions:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Clean up extra spaces
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r'\n +', '\n', text)
    
    return text.strip()


# =============================================================================
# GROQ RATE LIMITING WITH MONGODB STORAGE & MODEL FALLBACK
# =============================================================================

# Rate limits by model (requests per day, requests per minute)
GROQ_MODEL_LIMITS = {
    'llama-3.3-70b-versatile': {'daily': 900, 'per_minute': 25},
    'llama-3.1-8b-instant': {'daily': 14000, 'per_minute': 25},
    'llama-3.1-70b-versatile': {'daily': 14000, 'per_minute': 25},
    'mixtral-8x7b-32768': {'daily': 14000, 'per_minute': 25},
}

# Fallback chain: try models in order until one works
GROQ_FALLBACK_CHAIN = [
    'llama-3.3-70b-versatile',   # Best quality (1K/day)
    'llama-3.1-70b-versatile',   # Great quality (14K/day)
    'llama-3.1-8b-instant',       # Good quality, highest limit (14.4K/day)
]

# In-memory cache (synced with DB periodically)
_rate_limit_cache = {}
_last_db_sync = None
DB_SYNC_INTERVAL = 30  # Sync with DB every 30 seconds


class GroqRateLimiter:
    """
    Rate limiter for Groq API with MongoDB persistence and model fallback.
    
    Features:
    - Stores usage in MongoDB for persistence across restarts
    - Automatically falls back to other Groq models when rate limited
    - In-memory cache to reduce DB reads
    - Per-model tracking
    """
    
    def __init__(self):
        self._db = None
        self._collection = None
        self._cache = {}  # {model: {'daily_count': int, 'minute_requests': [timestamps], 'date': str}}
    
    @property
    def db(self):
        """Lazy load database connection"""
        if self._db is None:
            from database import db
            self._db = db
            self._collection = db.llm_usage
            # Create index for efficient queries
            self._collection.create_index([("model", 1), ("date", 1)], unique=True)
        return self._collection
    
    def _get_today(self) -> str:
        """Get today's date as string"""
        return datetime.date.today().isoformat()
    
    def _load_from_db(self, model: str) -> dict:
        """Load usage data from MongoDB"""
        today = self._get_today()
        try:
            doc = self.db.find_one({"model": model, "date": today})
            if doc:
                return {
                    'daily_count': doc.get('daily_count', 0),
                    'minute_requests': doc.get('minute_requests', []),
                    'date': today
                }
        except Exception as e:
            print(f"   ⚠️ Error loading rate limit from DB: {e}")
        
        return {'daily_count': 0, 'minute_requests': [], 'date': today}
    
    def _save_to_db(self, model: str, data: dict):
        """Save usage data to MongoDB"""
        today = self._get_today()
        try:
            self.db.update_one(
                {"model": model, "date": today},
                {"$set": {
                    "daily_count": data['daily_count'],
                    "minute_requests": data['minute_requests'][-100:],  # Keep last 100 timestamps
                    "updated_at": datetime.datetime.utcnow()
                }},
                upsert=True
            )
        except Exception as e:
            print(f"   ⚠️ Error saving rate limit to DB: {e}")
    
    def _get_cache(self, model: str) -> dict:
        """Get cached data for a model, loading from DB if needed"""
        today = self._get_today()
        
        # Check if cache is valid
        if model in self._cache and self._cache[model].get('date') == today:
            return self._cache[model]
        
        # Load from DB
        data = self._load_from_db(model)
        self._cache[model] = data
        return data
    
    def check_limit(self, model: str) -> tuple:
        """
        Check if model is within rate limits.
        Returns (can_proceed, wait_seconds, reason)
        """
        limits = GROQ_MODEL_LIMITS.get(model, {'daily': 900, 'per_minute': 25})
        data = self._get_cache(model)
        now = time.time()
        
        # Check daily limit
        if data['daily_count'] >= limits['daily']:
            return False, 0, "daily_limit"
        
        # Clean old minute requests
        data['minute_requests'] = [t for t in data['minute_requests'] if now - t < 60]
        
        # Check per-minute limit
        if len(data['minute_requests']) >= limits['per_minute']:
            wait_time = 60 - (now - data['minute_requests'][0])
            return False, max(0, wait_time), "minute_limit"
        
        return True, 0, "ok"
    
    def record_request(self, model: str):
        """Record a successful API request"""
        data = self._get_cache(model)
        data['daily_count'] += 1
        data['minute_requests'].append(time.time())
        
        # Save to DB periodically (every 5 requests to reduce writes)
        if data['daily_count'] % 5 == 0:
            self._save_to_db(model, data)
    
    def get_best_available_model(self, preferred_model: str = None) -> Optional[str]:
        """
        Get the best available model from the fallback chain.
        Returns None if all models are rate limited.
        """
        chain = GROQ_FALLBACK_CHAIN.copy()
        
        # Put preferred model first if specified
        if preferred_model and preferred_model in chain:
            chain.remove(preferred_model)
            chain.insert(0, preferred_model)
        
        for model in chain:
            can_proceed, wait_time, reason = self.check_limit(model)
            if can_proceed:
                return model
            elif reason == "minute_limit" and wait_time < 5:
                # Short wait is acceptable
                time.sleep(wait_time + 0.5)
                return model
        
        return None
    
    def get_usage_stats(self) -> dict:
        """Get current usage statistics for all models"""
        stats = {}
        today = self._get_today()
        
        for model, limits in GROQ_MODEL_LIMITS.items():
            data = self._get_cache(model)
            stats[model] = {
                'daily_used': data['daily_count'],
                'daily_limit': limits['daily'],
                'daily_remaining': limits['daily'] - data['daily_count'],
                'percent_used': round(data['daily_count'] / limits['daily'] * 100, 1)
            }
        
        return stats
    
    def flush_to_db(self):
        """Force save all cached data to DB"""
        for model, data in self._cache.items():
            self._save_to_db(model, data)


# Global rate limiter instance
_rate_limiter = None

def get_rate_limiter() -> GroqRateLimiter:
    """Get or create the global rate limiter"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = GroqRateLimiter()
    return _rate_limiter


def get_llm_client(provider: str = None, model: str = None):
    """Get the appropriate LLM client based on config or explicit provider"""
    if provider is None:
        provider = getattr(config, 'LLM_PROVIDER', 'openai').lower()
    
    if provider == 'groq':
        from groq import Groq
        if model is None:
            model = getattr(config, 'GROQ_MODEL', 'llama-3.3-70b-versatile')
        return Groq(api_key=config.GROQ_API_KEY), model, 'groq'
    else:
        from openai import OpenAI
        if model is None:
            model = getattr(config, 'OPENAI_MODEL', 'gpt-4.1-mini')
        return OpenAI(api_key=config.OPENAI_API_KEY), model, 'openai'


# Legacy functions for backward compatibility
def check_groq_rate_limit(model: str = None) -> tuple:
    """Check if we're within Groq rate limits."""
    if model is None:
        model = getattr(config, 'GROQ_MODEL', 'llama-3.3-70b-versatile')
    return get_rate_limiter().check_limit(model)


def record_groq_request(model: str = None):
    """Record a Groq API request for rate limiting"""
    if model is None:
        model = getattr(config, 'GROQ_MODEL', 'llama-3.3-70b-versatile')
    get_rate_limiter().record_request(model)


class EmailGenerator:
    """Generate personalized cold emails with REAL personalization"""
    
    def __init__(self):
        self.client, self.model, self.provider = get_llm_client()
        self.company_context = COMPANY_CONTEXT
        self.email_context = EMAIL_CONTEXT
        self.case_studies = CASE_STUDIES
        self.rate_limiter = get_rate_limiter() if self.provider == 'groq' else None
        
        # Show initialization message with available Groq capacity
        if self.provider == 'groq':
            stats = self.rate_limiter.get_usage_stats()
            primary_stats = stats.get(self.model, {})
            print(f"📝 Email generator using: GROQ ({self.model})")
            print(f"   Daily capacity: {primary_stats.get('daily_remaining', '?')}/{primary_stats.get('daily_limit', '?')} remaining")
            print(f"   Fallback chain: {' → '.join(GROQ_FALLBACK_CHAIN)}")
        else:
            print(f"📝 Email generator using: {self.provider.upper()} ({self.model})")
    
    def _call_llm(self, system_prompt: str, user_prompt: str, temperature: float = 0.7, json_mode: bool = False) -> str:
        """
        Call the LLM (Groq or OpenAI) with rate limiting and automatic Groq model fallback.
        Returns the response content as string.
        """
        # For OpenAI, just make the call directly
        if self.provider != 'groq':
            return self._make_llm_call(self.client, self.model, system_prompt, user_prompt, temperature, json_mode)
        
        # For Groq, use the fallback chain
        preferred_model = self.model
        
        # Find an available model from the fallback chain
        available_model = self.rate_limiter.get_best_available_model(preferred_model)
        
        if available_model is None:
            # All Groq models exhausted - fall back to OpenAI if available
            if getattr(config, 'OPENAI_API_KEY', None):
                print(f"   ⚠️ All Groq models exhausted, falling back to OpenAI")
                from openai import OpenAI
                openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
                openai_model = getattr(config, 'OPENAI_MODEL', 'gpt-4.1-mini')
                return self._make_llm_call(openai_client, openai_model, system_prompt, user_prompt, temperature, json_mode)
            else:
                raise Exception("All Groq models rate limited and no OpenAI fallback configured")
        
        # Log if we're using a different model than preferred
        if available_model != preferred_model:
            logger.info(f"Using fallback model: {available_model} (primary {preferred_model} rate limited)")
        
        # Get client for the available model (all Groq models use same client)
        return self._make_llm_call(self.client, available_model, system_prompt, user_prompt, temperature, json_mode, record_usage=True)
    
    def _make_llm_call(self, client, model: str, system_prompt: str, user_prompt: str, 
                       temperature: float, json_mode: bool, record_usage: bool = False) -> str:
        """Make the actual LLM API call with retry logic"""
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature,
        }
        
        # JSON mode - Groq supports this for Llama 3.3+
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        
        # Try the API call with retry logic for rate limits
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(**kwargs)
                
                # Record successful Groq request
                if record_usage and self.rate_limiter:
                    self.rate_limiter.record_request(model)
                
                return response.choices[0].message.content
                
            except Exception as e:
                error_str = str(e).lower()
                
                # Check if it's a rate limit error
                if 'rate' in error_str and 'limit' in error_str:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 5
                        logger.warning(f"Rate limit error, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                
                # Not a rate limit error or final retry - raise it
                logger.error(f"LLM call failed: {e}")
                raise
        
        raise Exception("Max retries exceeded for LLM call")
    
    def research_company(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        PROBLEM SNIFFING: Research the company to find something SPECIFIC to mention.
        This is what separates spam from real outreach.
        
        Returns specific insights we can reference in the email.
        """
        company = lead.get('company') or ''
        title = lead.get('title') or ''
        industry = lead.get('industry') or ''
        first_name = lead.get('first_name') or ''
        
        system_prompt = """You are researching a company to write a personalized cold email.
Your job is to find ONE specific, interesting thing about this company that we can reference.

DO NOT make things up. If you don't know something specific, say so.
DO NOT be generic. "Great company" or "interesting product" is useless.

Find something SPECIFIC like:
- A recent product launch or feature
- Their business model or unique approach
- A specific problem they likely face based on their stage/industry
- Something about their tech stack or hiring patterns
- A recent news item or milestone

Return JSON:
{
    "specific_observation": "One specific thing we noticed (or 'none' if nothing specific)",
    "likely_pain_point": "Based on their stage/industry, what probably keeps them up at night",
    "why_relevant_to_us": "Why PrimeStrides specifically could help with this",
    "conversation_hook": "A natural way to open the conversation based on this",
    "confidence": "high/medium/low - how confident are we this is accurate"
}

If confidence is low, we'll use a different approach (honest curiosity instead of fake observation)."""

        user_prompt = f"""Research this lead:
- Name: {first_name}
- Title: {title}
- Company: {company}
- Industry: {industry}

Find something SPECIFIC we can reference. Don't make things up."""

        try:
            content = self._call_llm(system_prompt, user_prompt, temperature=0.7, json_mode=True)
            return json.loads(content)
        except Exception as e:
            print(f"Error researching company: {e}")
            return {
                "specific_observation": "none",
                "likely_pain_point": "shipping product fast with limited engineering bandwidth",
                "why_relevant_to_us": "we help startups ship in weeks not months",
                "conversation_hook": "curious about your engineering setup",
                "confidence": "low"
            }
    
    def select_case_study(self, lead: Dict[str, Any], research: Dict[str, Any]) -> Dict[str, Any]:
        """
        Select the MOST RELEVANT case study for this specific lead.
        LeadGenJay: "If the prospect is nothing like your case study, it doesn't really help"
        
        IMPROVED: Better industry keyword matching with comprehensive mappings
        """
        industry = (lead.get('industry') or '').lower()
        company = (lead.get('company') or '').lower()
        title = (lead.get('title') or '').lower()
        pain_point = (research.get('likely_pain_point') or '').lower()
        
        # Industry keyword mappings for better matching
        industry_keywords = {
            'fintech_client': ['fintech', 'finance', 'financial', 'banking', 'payment', 'crypto', 'defi', 'trading', 'investment', 'wallet', 'money', 'capital'],
            'healthtech_client': ['health', 'medical', 'healthcare', 'hipaa', 'patient', 'clinical', 'pharma', 'drug', 'biotech', 'hospital', 'doctor', 'med'],
            'roboapply': ['hr', 'human resource', 'recruiting', 'hiring', 'talent', 'staffing', 'job', 'career', 'ai', 'automation', 'application'],
            'stratmap': ['saas', 'b2b', 'startup', 'mvp', 'software', 'platform', 'seed', 'series', 'venture', 'founder'],
            'timpl': ['enterprise', 'legacy', 'staffing', 'corporate', 'modernization', 'migration', 'deployment']
        }
        
        # Score each case study for relevance
        scores = {}
        
        for key, study in self.case_studies.items():
            score = 0
            relevance_tags = [r.lower() for r in (study.get('relevance') or [])]
            study_industry = (study.get('industry') or '').lower()
            keywords = industry_keywords.get(key, [])
            
            # Check industry field for keyword matches
            for kw in keywords:
                if kw in industry:
                    score += 4  # Strong match
                if kw in company:
                    score += 2  # Company name hint
            
            # STRONG industry match (most important per LeadGenJay)
            if study_industry and study_industry in industry:
                score += 5
            elif any(tag in industry for tag in relevance_tags):
                score += 3
            
            # Pain point match
            if 'ai' in pain_point and 'ai' in relevance_tags:
                score += 2
            if 'legacy' in pain_point and 'legacy' in relevance_tags:
                score += 2
            if 'mvp' in pain_point or 'ship' in pain_point:
                if 'mvp' in relevance_tags or 'fast shipping' in relevance_tags:
                    score += 2
            if 'scale' in pain_point or 'scaling' in pain_point:
                score += 1  # Generic, slight boost for any case study
            
            # Title match (CTOs care about different things than founders)
            if 'cto' in title or 'engineer' in title or 'technical' in title:
                if key == 'timpl' or key == 'fintech_client':  # Technical case studies
                    score += 1
            if 'ceo' in title or 'founder' in title:
                if key == 'stratmap':  # Business outcome case study
                    score += 2
            
            scores[key] = score
        
        # Pick the best match, with some randomization for ties
        best_score = max(scores.values())
        best_matches = [k for k, v in scores.items() if v == best_score]
        selected = random.choice(best_matches)
        
        # Log selection for debugging
        if best_score < 2:
            print(f"   ⚠️ Low case study match (score={best_score}) for industry: {industry}")
        
        # Add industry match flag for prompt to use
        result = self.case_studies[selected].copy()
        result['industry_match'] = best_score >= 3  # True if reasonably matched
        result['match_score'] = best_score
        
        return result
    
    def determine_icp_and_criteria(self, campaign_description: str) -> Dict[str, Any]:
        """
        Use AI to determine the best ICP and RocketReach search criteria.
        
        CRITICAL: RocketReach has millions of people but industry filters are VERY restrictive.
        - A broad search for "Founder/CEO/CTO" in US returns 1.7M+ results
        - Adding industry filters like "Technology, SaaS" reduces it to just 5-10 results!
        
        Strategy: Use BROAD searches with keyword targeting, not restrictive industry filters.
        """
        icp_options = json.dumps(ICP_TEMPLATES, indent=2)
        case_study_options = json.dumps(CASE_STUDIES, indent=2)
        
        system_prompt = f"""You are an expert at B2B sales targeting and cold email strategy.
You work for PrimeStrides, a boutique software agency.

{self.company_context}

Given a campaign description, determine:
1. The best target audience (be SPECIFIC in description)
2. RocketReach search criteria (MUST FOLLOW RULES BELOW)
3. The ONE specific pain point to focus on
4. The unique angle that ONLY PrimeStrides can claim
5. Which case study is most relevant

**CRITICAL RULES FOR search_criteria (RocketReach API limits):**

1. **DO NOT use industry filters** - they are too restrictive and return almost zero results.
   RocketReach industry matching is broken - "Technology" + "SaaS" returns only 5 people!

2. **Use BROAD title searches** - Include variations:
   - For founders: ["Founder", "Co-Founder", "CEO", "CEO & Founder", "Co-founder and CEO"]
   - For technical: ["CTO", "VP Engineering", "Head of Engineering", "VP of Engineering", "Engineering Director", "VP Technology"]
   - For product: ["Head of Product", "VP Product", "CPO", "Chief Product Officer"]

3. **Use keywords INSTEAD of industry** - Put industry/vertical targeting in keywords:
   - For fintech: keywords: ["fintech", "payments", "banking", "financial services"]
   - For healthtech: keywords: ["healthtech", "healthcare", "medical", "HIPAA"]
   - For SaaS: keywords: ["SaaS", "B2B software", "cloud software"]

4. **Always include location** - Use ["United States", "Canada", "United Kingdom"] for English-speaking markets

5. **NEVER combine multiple restrictive filters** - Each filter MULTIPLIES restrictions

Example GOOD search_criteria:
{{
    "current_title": ["Founder", "Co-Founder", "CEO", "CTO", "CEO & Founder"],
    "location": ["United States"],
    "keywords": ["SaaS", "B2B", "startup"]
}}

Example BAD search_criteria (will return 0 results):
{{
    "current_title": ["CTO", "VP of Engineering"],
    "industry": ["Technology", "Software", "SaaS"],
    "location": ["United States"]
}}

Available ICP templates:
{icp_options}

Available case studies:
{case_study_options}

Return JSON with campaign_name, target_description, search_criteria, and campaign_context.
REMEMBER: No industry field in search_criteria - use keywords instead!"""

        user_prompt = f"""Campaign description: {campaign_description}

Create hyper-targeted campaign.
Remember: 
- ONE pain point
- Specific case study
- Unique angle
- BROAD search criteria (no industry filter, use keywords instead)"""

        try:
            content = self._call_llm(system_prompt, user_prompt, temperature=0.7, json_mode=True)
            result = json.loads(content)
            
            # POST-PROCESS: Remove industry filter if AI still included it (it's too restrictive)
            if 'search_criteria' in result:
                if 'industry' in result['search_criteria']:
                    # Convert industry to keywords instead
                    industries = result['search_criteria'].pop('industry')
                    existing_keywords = result['search_criteria'].get('keywords', [])
                    if isinstance(industries, list):
                        result['search_criteria']['keywords'] = existing_keywords + industries
                    print(f"   ⚠️  Converted industry filter to keywords for broader search")
                
                # Also remove 'industries' if present
                if 'industries' in result['search_criteria']:
                    industries = result['search_criteria'].pop('industries')
                    existing_keywords = result['search_criteria'].get('keywords', [])
                    if isinstance(industries, list):
                        result['search_criteria']['keywords'] = existing_keywords + industries
                
                # Ensure we have broad enough titles
                titles = result['search_criteria'].get('current_title', [])
                if len(titles) < 3:
                    # Add more title variations for better coverage
                    base_titles = set(titles)
                    if any('founder' in t.lower() for t in titles):
                        base_titles.update(['Founder', 'Co-Founder', 'CEO', 'CEO & Founder'])
                    if any('cto' in t.lower() or 'engineer' in t.lower() for t in titles):
                        base_titles.update(['CTO', 'VP Engineering', 'Head of Engineering', 'VP of Engineering'])
                    result['search_criteria']['current_title'] = list(base_titles)
                    print(f"   📈 Expanded title search to {len(base_titles)} variations")
                
                # Ensure we have location
                if 'location' not in result['search_criteria']:
                    result['search_criteria']['location'] = ['United States', 'Canada', 'United Kingdom']
            
            return result
        except Exception as e:
            print(f"Error determining ICP: {e}")
            return self._fallback_icp(campaign_description)
    
    def _fallback_icp(self, description: str) -> Dict:
        """Fallback ICP if AI fails - uses BROAD search criteria"""
        return {
            "campaign_name": description,
            "target_description": "Startup founders needing dev help",
            "search_criteria": {
                "current_title": ["Founder", "Co-Founder", "CEO", "CTO", "CEO & Founder", "Co-founder and CEO"],
                "location": ["United States", "Canada", "United Kingdom"],
                "keywords": ["startup", "SaaS", "tech", "software"]
                # NOTE: No industry field - it's too restrictive in RocketReach
            },
            "campaign_context": {
                "product_service": "senior engineering team for 8-week sprints",
                "single_pain_point": "can't ship fast enough with current team",
                "unique_angle": "we shipped RoboApply's entire AI system in 8 weeks",
                "case_study": CASE_STUDIES["roboapply"],
                "front_end_offer": "free 30-min architecture review",
                "trigger_signal": "actively building/scaling product"
            }
        }
    
    def generate_initial_email(self, 
                               lead: Dict[str, Any],
                               campaign_context: Dict[str, Any],
                               tone: str = "casual",
                               include_review_learnings: bool = True) -> Dict[str, str]:
        """
        Generate a TRULY personalized cold email.
        
        LeadGenJay Rules:
        1. Subject: 2-4 words, looks like colleague
        2. First line: Creates CURIOSITY, is SPECIFIC (not "saw something interesting")
        3. Under 75 words total (50-60 ideal)
        4. ONE pain point
        5. Relevant case study with REAL numbers
        6. Soft CTA
        
        Self-Improvement:
        - Includes learnings from past failed reviews
        """
        
        # Get improvement context from past reviews (SELF-IMPROVEMENT)
        improvement_prompt = ""
        if include_review_learnings:
            try:
                from email_reviewer import EmailReviewer
                reviewer = EmailReviewer()
                improvement_prompt = reviewer.get_improvement_prompt(days=14)
                if improvement_prompt:
                    print("   📚 Including learnings from past reviews")
            except Exception as e:
                pass  # Silently fail - improvement is optional
        
        # Step 1: Research the company (PROBLEM SNIFFING)
        research = self.research_company(lead)
        
        # Step 2: Select the most relevant case study
        case_study = self.select_case_study(lead, research)
        
        first_name = lead.get('first_name') or 'there'
        company = lead.get('company') or 'your company'
        title = lead.get('title') or ''
        industry = lead.get('industry') or ''
        
        # Determine opening strategy based on research confidence
        if research.get('confidence') == 'high':
            opening_instruction = f"""Use this SPECIFIC observation: "{research.get('specific_observation')}"
Reference it naturally like you're texting a friend - NOT "I noticed" or "I saw"."""
        elif research.get('confidence') == 'medium':
            opening_instruction = f"""Use this hook: "{research.get('conversation_hook')}"
Be casual and direct - like texting a colleague, not writing a formal email."""
        else:
            opening_instruction = f"""Be direct and honest - don't pretend you researched if you didn't:
- "{company}'s in an interesting space" or ask a genuine question
- Just get to the point quickly"""
        
        # VARIED SUBJECT LINES - LeadGenJay: 2-3 words that a colleague could send
        # NEVER just "{name}?" - it's overused and boring
        subject_templates = [
            "random thought",
            "quick idea", 
            "saw something",
            "wild idea",
            "quick q",
            f"{first_name.lower()} - idea",
            "thought about this",
            f"re {company.lower().split()[0] if company else 'you'}",
            "random q",
            "hey quick q",
        ]
        suggested_subject = random.choice(subject_templates)
        
        # CURIOSITY-FIRST OPENERS - LeadGenJay: First line = preview text
        # Must sound like it could be from a friend, NOT reveal it's a pitch
        # NEVER start with company observation - that's instant delete
        # NO EM DASHES (—) - this is the #1 AI tell!
        curiosity_openers = [
            f"random question, how's your team handling [specific challenge] these days?",
            f"been thinking about this. {company} is in an interesting spot right now.",
            f"quick q for you {first_name}.",
            f"this might be out of left field.",
            f"curious about something with {company}.",
            f"weird timing but had a thought.",
            f"so I was looking at {company}'s site...",
            f"hey {first_name}, random one for you.",
        ]
        suggested_opener = random.choice(curiosity_openers)
        
        # VARIED CTAs - LeadGenJay: ONE soft CTA, but vary them
        cta_options = [
            "worth a quick chat?",
            "ring any bells?",
            "sound familiar?",
            "crazy or worth exploring?",
            "am I off base here?",
            "make any sense?",
            "worth 15 mins?",
            "curious if this resonates.",
        ]
        suggested_cta = random.choice(cta_options)
        
        # Case study reference - LeadGenJay: use relevant case studies with REAL company hints
        # "a HR Tech company" is weak - add specificity when possible
        industry_hint = case_study.get('industry', 'similar')
        if case_study.get('industry_match'):
            case_study_reference = f"a {industry_hint} company like yours"
        else:
            case_study_reference = f"a {industry_hint} company we worked with"
        
        # LeadGenJay's EXACT framework from the 90-page doc:
        # Line 1: Preview text that sounds like a friend (NOT why you're reaching out)
        # Line 2: Poke the bear / agitate pain with observation, NOT question
        # Line 3: Case study with SPECIFIC numbers (3.72x not 4x)
        # Line 4: Soft CTA
        
        system_prompt = f"""You are writing a cold email following LeadGenJay's $15M framework.

**YOUR EMAIL MUST PASS THESE CHECKS OR IT FAILS:**
✅ Company name "{company}" appears in the body
✅ Exactly 4 lines (hook, pain, case study, CTA)
✅ Ends with soft CTA: "thoughts?", "make sense?", "worth a chat?"
✅ Under 75 words
✅ NO em dashes (—), NO AI words

**EXACT 4-LINE STRUCTURE (copy this format):**
```
Line 1: [curiosity hook]. {company} [observation about their pain].
Line 2: [State the pain in one sentence - don't ask about it].
Line 3: a [industry] company [result] in [timeline].
Line 4: [soft CTA]?
```

**PASSING EXAMPLE (copy this style):**
Subject: quick q

random thought. {company}'s compliance rules must be a headache lately.
scaling while keeping quality tight feels impossible.
a FinTech firm boosted throughput 2.7x with zero downtime in 10 weeks.
thoughts?

**ANOTHER PASSING EXAMPLE:**
Subject: odd thought

quick q for you. {company} scaling fast right now?
shipping speed usually tanks when teams grow.
a SaaS company cut bug rates by 43% in 8 weeks.
make sense?

**SUBJECT LINE (2-4 words):**
Good: "random thought", "quick q", "odd thought", "{suggested_subject}"
Bad: "{first_name}?", "Quick Question", "Partnership"

**FIRST LINE STARTERS (pick one):**
- "random thought. {company}..."
- "quick q for you. {company}..."
- "odd thought. {company}..."
- "this might be weird but {company}..."

**BANNED (instant fail):**
❌ Em dash (—) anywhere
❌ "I noticed", "I saw", "I came across"
❌ "how is {company} handling..."
❌ AI words: delve, leverage, utilize, robust, seamless, foster, harness

**USE:**
✅ Contractions (don't, can't, isn't)
✅ Choppy sentences. Short. Punchy.
✅ Simple words (6th grade level)
{improvement_prompt if improvement_prompt else ""}

Return JSON: {{"subject": "...", "body": "..."}}"""

        user_prompt = f"""Write cold email to:
- Name: {first_name}
- Company: {company} (MUST appear in body)
- Title: {title}
- Industry: {industry}

Case study: {case_study_reference} - {case_study.get('result')} in {case_study.get('timeline')}

MANDATORY CHECKLIST (verify before responding):
☐ "{company}" appears in line 1
☐ Exactly 4 lines
☐ Ends with "thoughts?" or "make sense?" or "worth a chat?"
☐ NO em dash (—)
☐ Under 75 words"""

        try:
            content = self._call_llm(system_prompt, user_prompt, temperature=0.9, json_mode=True)
            result = json.loads(content)
            
            # Validate and clean - handle None values explicitly
            subject = result.get("subject") or suggested_subject
            body = result.get("body") or ""
            
            # If body is empty or None, use fallback
            if not body or not body.strip():
                print(f"   ⚠️ LLM returned empty body, using fallback")
                return self._fallback_email(lead, campaign_context, research, case_study, suggested_cta)
            
            # CRITICAL: Check if email starts with company observation (instant delete pattern)
            first_line = body.split('\n')[0].lower().strip() if body else ""
            company_lower = company.lower() if company else ""
            
            bad_start_patterns = [
                f"{company_lower}'s",
                f"{company_lower} just",
                f"{company_lower} is",
                f"{company_lower} has",
                "i noticed",
                "i saw",
                "i came across",
            ]
            
            # Check for bad patterns
            starts_bad = any(first_line.startswith(p) for p in bad_start_patterns if p)
            
            # Also check for subject being just "Name?"
            subject_is_weak = subject.strip().lower() in [
                f"{first_name.lower()}?", 
                f"{first_name.lower()} ?",
                first_name.lower(),
            ]
            
            if starts_bad or subject_is_weak:
                if starts_bad:
                    print(f"   ⚠️ Email starts with company observation, regenerating...")
                if subject_is_weak:
                    print(f"   ⚠️ Subject is weak '{subject}', using suggested: {suggested_subject}")
                    subject = suggested_subject
                
                # Try to regenerate with stricter prompt (one retry)
                if starts_bad:
                    return self._fallback_email(lead, campaign_context, research, case_study, suggested_cta)
            
            # Final validation for other issues
            body = self._validate_and_clean(body, lead, case_study)
            
            # HUMANIZE - Strip any remaining AI tells
            subject = humanize_email(subject)
            body = humanize_email(body)
            
            return {
                "subject": subject,
                "body": body,
                "research": research,  # Include for debugging
                "case_study_used": case_study.get('company_name')
            }
        except Exception as e:
            print(f"Error generating email: {e}")
            return self._fallback_email(lead, campaign_context, research, case_study, suggested_cta)
    
    def _validate_and_clean(self, body: str, lead: Dict, case_study: Dict) -> str:
        """Validate email doesn't contain banned patterns - STRICT per LeadGenJay"""
        # Safety check for None
        if body is None:
            return ""
        
        banned_phrases = [
            "i hope this finds you well",
            "i'm reaching out",
            "i noticed your company",
            "i noticed that",
            "i noticed ",  # Catch all "I noticed" variants
            "i saw that",
            "i came across",
            "just wanted to reach out",
            "touching base",
            "circling back",
            "leverage",
            "synergy",
            "streamline",
            "optimize",
            "innovative",
            "cutting-edge",
            "game-changing",
            "how are you navigating",  # Too formal
            "how are you ensuring",    # Too formal
            "how are you managing",    # Too formal
            "how are you handling",    # Too formal
            "how's that affecting",    # Too formal
        ]
        
        # Check for double CTAs (desperate look)
        cta_phrases = ["worth a chat", "worth a quick chat", "interested", "make sense", "open to", "curious if"]
        
        body_lower = body.lower()
        issues = []
        
        for phrase in banned_phrases:
            if phrase in body_lower:
                issues.append(f"Contains banned phrase: '{phrase}'")
        
        # Count CTAs
        cta_count = sum(1 for cta in cta_phrases if cta in body_lower)
        if cta_count > 1:
            issues.append(f"Multiple CTAs detected ({cta_count}) - looks desperate")
        
        # Check first line for robotic patterns
        first_line = body.split('\n')[0].lower() if body else ""
        if first_line.startswith("i noticed") or first_line.startswith("i saw"):
            issues.append("Opens with robotic 'I noticed/saw' pattern")
        
        # Check sentence lengths
        sentences = [s.strip() for s in body.replace('\n', '. ').split('.') if s.strip()]
        for s in sentences:
            word_count = len(s.split())
            if word_count > 15:
                issues.append(f"Long sentence ({word_count} words): '{s[:40]}...'")
        
        # Log warnings
        for issue in issues:
            print(f"⚠️  VALIDATION WARNING: {issue}")
        
        return body
    
    def _fallback_email(self, lead: Dict, context: Dict, research: Dict, case_study: Dict, cta: str = None) -> Dict[str, str]:
        """
        Fallback email that sounds human, not templated.
        Uses LeadGenJay structure: curiosity hook → pain → case study → soft CTA
        NO EM DASHES - use commas/periods instead
        """
        first_name = lead.get('first_name') or 'there'
        company = lead.get('company') or 'your company'
        
        # Varied subject lines (NEVER just "name?")
        subjects = [
            "random thought",
            "quick idea",
            "hey quick q",
            f"{first_name.lower()} - quick q",
            "saw something",
        ]
        
        # Curiosity-first openers (NOT company observations, NO EM DASHES)
        openers = [
            f"random question. how's your team handling eng bandwidth these days?",
            f"quick thought for you {first_name}.",
            f"been thinking about this lately.",
            f"quick q, how are things going with scaling the technical side?",
            f"curious about something.",
            f"hey {first_name}, random one.",
        ]
        
        # Pain statements (observations, not questions)
        pains = [
            "scaling eng teams while shipping fast is brutal.",
            "most teams we talk to are stretched thin right now.",
            "shipping fast without breaking things is tough.",
            "finding senior devs who can hit the ground running is hard.",
        ]
        
        # Use provided CTA or pick one
        ctas = cta or random.choice([
            "worth a quick chat?",
            "ring any bells?",
            "sound familiar?",
            "crazy or worth exploring?",
        ])
        
        # Get case study info
        cs_industry = case_study.get('industry', 'similar') if case_study else 'similar'
        cs_result = case_study.get('result_short', '3x faster shipping') if case_study else '3x faster shipping'
        cs_timeline = case_study.get('timeline', '8 weeks') if case_study else '8 weeks'
        
        subject = random.choice(subjects)
        opener = random.choice(openers)
        pain = random.choice(pains)
        
        # Build email following LeadGenJay structure
        body = f"""{opener}

{pain} a {cs_industry} company we worked with hit {cs_result} in {cs_timeline}.

{ctas}"""

        return {
            "subject": subject,
            "body": body,
            "research": research,
            "case_study_used": case_study.get('company_name', 'generic') if case_study else 'generic'
        }
    
    def generate_followup_email(self,
                                lead: Dict[str, Any],
                                campaign_context: Dict[str, Any],
                                previous_emails: List[Dict[str, str]],
                                followup_number: int) -> Dict[str, str]:
        """
        Generate follow-up emails following LeadGenJay strategy:
        
        Email 2: Same thread, ADD VALUE (not "just following up")
        Email 3: NEW thread, different angle
        Max 3 emails total.
        """
        
        if followup_number == 1:
            return self._generate_followup_same_thread(lead, campaign_context, previous_emails)
        elif followup_number == 2:
            return self._generate_followup_new_thread(lead, campaign_context, previous_emails)
        else:
            return self._generate_breakup_email(lead, campaign_context, previous_emails)
    
    def _generate_followup_same_thread(self, lead: Dict, context: Dict, previous: List) -> Dict:
        """
        Follow-up #2: Same thread, ADD GENUINE VALUE
        
        LeadGenJay: "Don't say 'just following up'. Add something useful."
        """
        first_name = lead.get('first_name') or 'there'
        company = lead.get('company') or ''
        original_subject = previous[0]['subject'] if previous else "previous"
        
        system_prompt = """Write follow-up #2 for a cold email that got no reply.

RULES:
- Same thread (Re: original subject)
- UNDER 40 WORDS
- Add GENUINE value - share an insight, resource, or quick tip
- NEVER say "just following up", "circling back", "bumping this"
- NEVER guilt trip
- Sound helpful, not desperate

GOOD approaches:
- "one thing I forgot - [specific insight]"
- "fwiw - just published something on [relevant topic]. happy to share."
- Share a specific tip related to their pain point

Return JSON: {"subject": "Re: [original]", "body": "..."}"""

        user_prompt = f"""Follow up with {first_name} at {company}.
Original subject: {original_subject}
Original body: {previous[0].get('body', '')[:150] if previous else ''}

Write a SHORT follow-up that adds value. Under 40 words."""

        try:
            content = self._call_llm(system_prompt, user_prompt, temperature=0.85, json_mode=True)
            result = json.loads(content)
            body = result.get("body") or ""
            if not body.strip():
                # Use fallback if empty
                return {
                    "subject": f"Re: {original_subject}",
                    "body": f"""one thing I forgot to mention - 

we just wrote up how we cut deployment time by 3x for a company similar to {company}.

might be relevant. happy to share if useful."""
                }
            return {
                "subject": f"Re: {original_subject}",
                "body": body
            }
        except Exception as e:
            print(f"Error generating follow-up: {e}")
            # Fallback
            return {
                "subject": f"Re: {original_subject}",
                "body": f"""one thing I forgot to mention - 

we just wrote up how we cut deployment time by 3x for a company similar to {company}.

might be relevant. happy to share if useful."""
            }
    
    def _generate_followup_new_thread(self, lead: Dict, context: Dict, previous: List) -> Dict:
        """
        Follow-up #3: NEW thread, completely different angle
        
        LeadGenJay: "Email 3 should be a fresh start with different subject and angle"
        """
        first_name = lead.get('first_name') or 'there'
        company = lead.get('company') or ''
        front_end_offer = context.get('front_end_offer') or 'free architecture review'
        
        system_prompt = """Write follow-up #3 - a FRESH email with NEW thread.

RULES:
- NEW subject line (different from previous emails)
- Different angle than before
- Offer something valuable for free (the front-end offer)
- Under 50 words
- Don't reference previous emails
- Sound like a fresh, helpful message

IMPORTANT: Do NOT include signature or sign-off. End with the question.

Return JSON: {"subject": "...", "body": "..."}"""

        previous_subjects = [e.get('subject', '') for e in previous]
        
        user_prompt = f"""Fresh email to {first_name} at {company}.
Previous subjects used (DON'T repeat): {previous_subjects}
Front-end offer to make: {front_end_offer}

Write a fresh email with different approach. Under 50 words."""

        try:
            content = self._call_llm(system_prompt, user_prompt, temperature=0.9, json_mode=True)
            result = json.loads(content)
            subject = result.get("subject") or "different thought"
            body = result.get("body") or ""
            if not body.strip():
                # Use fallback if empty
                return {
                    "subject": "different thought",
                    "body": f"""{first_name} - 

totally different idea. we're doing free {front_end_offer}s for companies in your space.

30 mins, specific feedback, no pitch.

interested?""",
                    "new_thread": True
                }
            return {
                "subject": subject,
                "body": body,
                "new_thread": True
            }
        except Exception as e:
            return {
                "subject": "different thought",
                "body": f"""{first_name} - 

totally different idea. we're doing free {front_end_offer}s for companies in your space.

30 mins, specific feedback, no pitch.

interested?""",
                "new_thread": True
            }
    
    def _generate_breakup_email(self, lead: Dict, context: Dict, previous: List) -> Dict:
        """Final email - helpful redirect, not guilt trip"""
        first_name = lead.get('first_name') or 'there'
        company = lead.get('company') or ''
        
        # LeadGenJay tip: "Should I reach out to someone else?" works well
        body = f"""{first_name} -

last note from me. if dev bandwidth becomes a priority at {company}, happy to help.

or if there's someone else I should talk to, just point me their way.

either way, rooting for you."""

        return {
            "subject": "closing the loop",
            "body": body,
            "new_thread": True
        }


# Test
if __name__ == "__main__":
    generator = EmailGenerator()
    
    # Test with real lead data
    test_lead = {
        "first_name": "Sarah",
        "full_name": "Sarah Chen",
        "title": "CTO",
        "company": "FinFlow",
        "industry": "FinTech",
        "location": "San Francisco"
    }
    
    print("="*60)
    print("Testing improved email generator")
    print("="*60)
    
    # Test research
    print("\n1. Researching company...")
    research = generator.research_company(test_lead)
    print(f"Research: {json.dumps(research, indent=2)}")
    
    # Test case study selection
    print("\n2. Selecting case study...")
    case_study = generator.select_case_study(test_lead, research)
    print(f"Selected: {case_study.get('company_name')}")
    
    # Test email generation
    print("\n3. Generating email...")
    context = {"single_pain_point": "shipping AI features fast"}
    email = generator.generate_initial_email(test_lead, context)
    
    print(f"\nSubject: {email['subject']}")
    print(f"\nBody:\n{email['body']}")
    print(f"\nWord count: {len(email['body'].split())}")
    print(f"Case study used: {email.get('case_study_used', 'N/A')}")
