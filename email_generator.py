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

# Rate limits by model (requests per day, requests per minute, tokens per day)
# Groq's actual limit is ~100k tokens/day per model for free tier
# Updated 2026-01-30 with currently available models from Groq
GROQ_MODEL_LIMITS = {
    'llama-3.3-70b-versatile': {'daily': 900, 'per_minute': 25, 'tokens_per_day': 100000},
    'llama-3.1-8b-instant': {'daily': 14000, 'per_minute': 25, 'tokens_per_day': 500000},
    'qwen/qwen3-32b': {'daily': 14000, 'per_minute': 25, 'tokens_per_day': 500000},
    'meta-llama/llama-4-maverick-17b-128e-instruct': {'daily': 14000, 'per_minute': 25, 'tokens_per_day': 500000},
}

# Aggressive fallback chain - distribute load across models
# Strategy: Use high-quality models first, with aggressive fallback to others
# Updated 2026-01-30 - removed decommissioned models
GROQ_FALLBACK_CHAIN = [
    'llama-3.3-70b-versatile',                         # Best quality (100k tokens/day)
    'qwen/qwen3-32b',                                   # Good 32B model (500k tokens/day)
    'meta-llama/llama-4-maverick-17b-128e-instruct',   # Llama 4 17B (500k tokens/day)
    'llama-3.1-8b-instant',                            # Fast 8B model (500k tokens/day) - last resort
    'llama-3.1-8b-instant',       # POOR quality - last resort only (14.4K/day)
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
                    'tokens_used': doc.get('tokens_used', 0),
                    'minute_requests': doc.get('minute_requests', []),
                    'date': today
                }
        except Exception as e:
            print(f"   ⚠️ Error loading rate limit from DB: {e}")
        
        return {'daily_count': 0, 'tokens_used': 0, 'minute_requests': [], 'date': today}
    
    def _save_to_db(self, model: str, data: dict):
        """Save usage data to MongoDB"""
        today = self._get_today()
        try:
            self.db.update_one(
                {"model": model, "date": today},
                {"$set": {
                    "daily_count": data['daily_count'],
                    "tokens_used": data.get('tokens_used', 0),
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
        limits = GROQ_MODEL_LIMITS.get(model, {'daily': 900, 'per_minute': 25, 'tokens_per_day': 100000})
        data = self._get_cache(model)
        now = time.time()
        
        # Check daily request limit
        if data['daily_count'] >= limits['daily']:
            return False, 0, "daily_limit"
        
        # Check estimated token limit (estimate ~2000 tokens per request for safety)
        tokens_used = data.get('tokens_used', 0)
        token_limit = limits.get('tokens_per_day', 100000)
        if tokens_used >= token_limit * 0.95:  # Leave 5% buffer
            return False, 0, "token_limit"
        
        # Clean old minute requests
        data['minute_requests'] = [t for t in data['minute_requests'] if now - t < 60]
        
        # Check per-minute limit
        if len(data['minute_requests']) >= limits['per_minute']:
            wait_time = 60 - (now - data['minute_requests'][0])
            return False, max(0, wait_time), "minute_limit"
        
        return True, 0, "ok"
    
    def record_request(self, model: str, tokens_used: int = 2000):
        """Record a successful API request with estimated token usage"""
        data = self._get_cache(model)
        data['daily_count'] += 1
        data['tokens_used'] = data.get('tokens_used', 0) + tokens_used
        data['minute_requests'].append(time.time())
        
        # Save to DB periodically (every 5 requests to reduce writes)
        if data['daily_count'] % 5 == 0:
            self._save_to_db(model, data)
    
    def get_best_available_model(self, preferred_model: str = None) -> Optional[str]:
        """
        Get the best available model from the fallback chain.
        AGGRESSIVE: Distributes load across models to avoid hitting any single model's limit.
        Returns None if all models are rate limited.
        """
        chain = GROQ_FALLBACK_CHAIN.copy()
        
        # Get usage stats for smart selection
        model_stats = {}
        for model in chain:
            data = self._get_cache(model)
            limits = GROQ_MODEL_LIMITS.get(model, {'tokens_per_day': 100000})
            tokens_used = data.get('tokens_used', 0)
            token_limit = limits.get('tokens_per_day', 100000)
            usage_percent = (tokens_used / token_limit) * 100 if token_limit > 0 else 100
            model_stats[model] = usage_percent
        
        # AGGRESSIVE STRATEGY: Prefer the model with the most capacity remaining
        # Sort by usage percentage (lowest first)
        sorted_models = sorted(chain, key=lambda m: model_stats.get(m, 100))
        
        # If preferred model has < 80% usage, still use it for quality
        if preferred_model and model_stats.get(preferred_model, 100) < 80:
            sorted_models.remove(preferred_model)
            sorted_models.insert(0, preferred_model)
        
        for model in sorted_models:
            can_proceed, wait_time, reason = self.check_limit(model)
            if can_proceed:
                # Log when using fallback
                if model != (preferred_model or GROQ_FALLBACK_CHAIN[0]):
                    usage = model_stats.get(model, 0)
                    print(f"   🔄 Using {model} ({usage:.0f}% capacity used)")
                return model
            elif reason == "minute_limit" and wait_time < 5:
                # Short wait is acceptable
                time.sleep(wait_time + 0.5)
                return model
        
        return None
    
    def get_usage_stats(self) -> dict:
        """Get current usage statistics for all models including token usage"""
        stats = {}
        today = self._get_today()
        
        for model, limits in GROQ_MODEL_LIMITS.items():
            data = self._get_cache(model)
            token_limit = limits.get('tokens_per_day', 100000)
            tokens_used = data.get('tokens_used', 0)
            
            stats[model] = {
                'daily_used': data['daily_count'],
                'daily_limit': limits['daily'],
                'daily_remaining': limits['daily'] - data['daily_count'],
                'tokens_used': tokens_used,
                'tokens_limit': token_limit,
                'tokens_remaining': token_limit - tokens_used,
                'percent_used': round(tokens_used / token_limit * 100, 1) if token_limit > 0 else 0
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


def get_industry_pain_point(industry: str, title: str, enrichment: dict = None) -> str:
    """
    Use AI to generate a SPECIFIC pain point based on context.
    LeadGenJay: "Generic pain points like 'scaling is hard' get deleted instantly"
    
    The AI considers:
    - What the company actually does (from enrichment)
    - The person's role/title
    - Industry context
    """
    # Build context for AI
    context_parts = []
    if enrichment:
        if enrichment.get('what_they_do'):
            context_parts.append(f"Company does: {enrichment['what_they_do']}")
        if enrichment.get('their_space'):
            context_parts.append(f"Industry/space: {enrichment['their_space']}")
        if enrichment.get('pain_point_guess'):
            context_parts.append(f"Suspected challenge: {enrichment['pain_point_guess']}")
    
    if industry and industry not in ['Unknown', 'N/A', '']:
        context_parts.append(f"Industry: {industry}")
    
    context = "\n".join(context_parts) if context_parts else f"Industry: {industry or 'tech startup'}"
    
    prompt = f"""Based on this company context, write ONE specific pain point statement that someone with the title "{title}" would relate to.

CONTEXT:
{context}

RULES:
1. Be SPECIFIC to what this company does - no generic "scaling is hard" statements
2. Write from THEIR perspective - what keeps them up at night?
3. Make it feel like you understand their daily struggle
4. Keep it under 20 words
5. Don't start with "you" - start with the situation

EXAMPLES of good pain points:
- "shipping features while also fundraising means something always gets dropped"
- "every traffic spike becomes an all-hands emergency because there's no time for proper architecture"
- "compliance keeps blocking releases while competitors ship weekly"

EXAMPLES of BAD pain points (too generic):
- "scaling is hard"
- "you need more engineers"
- "technical debt is growing"

Return ONLY the pain point statement, nothing else."""

    try:
        rate_limiter = get_rate_limiter()
        available_model = rate_limiter.get_best_available_model()
        
        if not available_model:
            # Fallback to a sensible default
            return "your best engineers are stuck maintaining instead of building the next thing"
        
        client, _, provider = get_llm_client('groq', available_model)
        
        response = client.chat.completions.create(
            model=available_model,
            messages=[
                {"role": "system", "content": "You write specific, relatable pain points for cold emails. Be concise and insightful."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=100
        )
        
        rate_limiter.record_request(available_model, response.usage.total_tokens if response.usage else 100)
        
        pain_point = response.choices[0].message.content.strip()
        # Clean up any quotes or extra formatting
        pain_point = pain_point.strip('"\'')
        
        return pain_point
        
    except Exception as e:
        logger.warning(f"AI pain point generation failed: {e}, using fallback")
        return "your best engineers are stuck maintaining instead of building the next thing"


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
            print(f"📝 Email generator using: GROQ (aggressive fallback enabled)")
            print(f"   Model capacity (tokens used / limit):")
            for model in GROQ_FALLBACK_CHAIN:
                s = stats.get(model, {})
                used = s.get('tokens_used', 0)
                limit = s.get('tokens_limit', 100000)
                pct = s.get('percent_used', 0)
                status = "✅" if pct < 80 else "⚠️" if pct < 95 else "❌"
                print(f"      {status} {model}: {used:,}/{limit:,} ({pct}%)")
        else:
            print(f"📝 Email generator using: {self.provider.upper()} ({self.model})")
    
    def _call_llm(self, system_prompt: str, user_prompt: str, temperature: float = 0.7, json_mode: bool = False) -> str:
        """
        Call the LLM (Groq or OpenAI) with rate limiting and automatic Groq model fallback.
        AGGRESSIVE: Automatically tries next model in chain when one hits rate limits.
        Returns the response content as string.
        """
        # For OpenAI, just make the call directly
        if self.provider != 'groq':
            return self._make_llm_call(self.client, self.model, system_prompt, user_prompt, temperature, json_mode)
        
        # For Groq, use aggressive fallback - try each model in chain until one works
        tried_models = set()
        last_error = None
        
        while True:
            # Find an available model from the fallback chain (excluding already tried)
            available_model = self.rate_limiter.get_best_available_model(self.model)
            
            # Skip models we've already tried this call
            if available_model in tried_models:
                # Find any model we haven't tried yet
                for model in GROQ_FALLBACK_CHAIN:
                    if model not in tried_models:
                        available_model = model
                        break
                else:
                    available_model = None
            
            if available_model is None:
                # All Groq models exhausted - fall back to OpenAI if available
                if getattr(config, 'OPENAI_API_KEY', None):
                    print(f"   ⚠️ All Groq models exhausted, falling back to OpenAI")
                    from openai import OpenAI
                    openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
                    openai_model = getattr(config, 'OPENAI_MODEL', 'gpt-4.1-mini')
                    return self._make_llm_call(openai_client, openai_model, system_prompt, user_prompt, temperature, json_mode)
                else:
                    raise last_error or Exception("All Groq models rate limited and no OpenAI fallback configured")
            
            tried_models.add(available_model)
            
            try:
                # Try this model
                return self._make_llm_call(self.client, available_model, system_prompt, user_prompt, temperature, json_mode, record_usage=True)
            except Exception as e:
                error_str = str(e).lower()
                last_error = e
                
                # If it's a rate limit error, mark this model as exhausted and try next
                if 'rate' in error_str and 'limit' in error_str:
                    # Mark this model as at capacity for today
                    data = self.rate_limiter._get_cache(available_model)
                    limits = GROQ_MODEL_LIMITS.get(available_model, {})
                    data['tokens_used'] = limits.get('tokens_per_day', 100000)  # Max out the token count
                    self.rate_limiter._save_to_db(available_model, data)
                    print(f"   ⚠️ {available_model} hit rate limit, trying next model...")
                    continue
                else:
                    # Non-rate-limit error, raise it
                    raise
    
    def _make_llm_call(self, client, model: str, system_prompt: str, user_prompt: str, 
                       temperature: float, json_mode: bool, record_usage: bool = False) -> str:
        """Make the actual LLM API call - raises exception on failure for fallback handling"""
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
        
        # Single attempt - let _call_llm handle fallback
        response = client.chat.completions.create(**kwargs)
        
        # Record successful Groq request with actual token usage
        if record_usage and self.rate_limiter:
            # Extract actual token usage from response
            tokens_used = 2000  # Default estimate
            if hasattr(response, 'usage') and response.usage:
                tokens_used = getattr(response.usage, 'total_tokens', 2000)
            self.rate_limiter.record_request(model, tokens_used)
        
        return response.choices[0].message.content
    
    def research_company(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        PROBLEM SNIFFING: Research the company to find something SPECIFIC to mention.
        This is what separates spam from real outreach.
        
        PRIORITY ORDER:
        1. Use REAL enrichment data if available (from website crawl)
        2. Fall back to LLM research (but be honest about confidence)
        
        Returns specific insights we can reference in the email.
        """
        company = lead.get('company') or ''
        title = lead.get('title') or ''
        industry = lead.get('industry') or ''
        first_name = lead.get('first_name') or ''
        
        # FIRST: Check for real enrichment data from website crawl
        try:
            from lead_enricher import get_enrichment_for_email
            enrichment = get_enrichment_for_email(lead)
            
            if enrichment.get('has_enrichment'):
                conversation_starters = enrichment.get('conversation_starters', [])
                what_they_do = enrichment.get('what_they_do')
                their_space = enrichment.get('their_space')
                pain_guess = enrichment.get('pain_point_guess')
                
                # Only use if we have meaningful data
                if conversation_starters or what_they_do:
                    print(f"   🎯 Using REAL enrichment data for {company}")
                    return {
                        "conversation_starters": conversation_starters,
                        "what_they_do": what_they_do,
                        "their_space": their_space or industry,
                        "likely_pain_point": pain_guess or "shipping fast while maintaining quality",
                        "company_context": enrichment.get('company_context', {}),
                        "confidence": "high",
                        "source": "website_enrichment"
                    }
        except Exception as e:
            print(f"   ⚠️ Could not load enrichment: {e}")
        
        # FALLBACK: Use LLM research (but be honest about confidence)
        system_prompt = """You are researching a company to write a personalized cold email.
Your job is to find ONE specific, interesting thing about this company that we can reference.

CRITICAL: DO NOT make things up. If you don't know something specific, say so.
DO NOT pretend you "saw their latest moves" or "noticed they're hiring" without proof.
DO NOT be generic. "Great company" or "interesting product" is useless.

If you can't find something REAL and SPECIFIC, return confidence: "low"
and we'll use an honest approach instead of faking observation.

Find something SPECIFIC like:
- A recent product launch or feature (only if you know for sure)
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

BE HONEST. If confidence is low, we'll use a direct approach instead of fake observation."""

        user_prompt = f"""Research this lead:
- Name: {first_name}
- Title: {title}
- Company: {company}
- Industry: {industry}

Find something SPECIFIC we can reference. If you don't have REAL information, say confidence: low."""

        try:
            content = self._call_llm(system_prompt, user_prompt, temperature=0.7, json_mode=True)
            result = json.loads(content)
            result['source'] = 'llm_research'
            return result
        except Exception as e:
            print(f"Error researching company: {e}")
            return {
                "specific_observation": "none",
                "likely_pain_point": "shipping product fast with limited engineering bandwidth",
                "why_relevant_to_us": "we help startups ship in weeks not months",
                "conversation_hook": "curious about your engineering setup",
                "confidence": "low",
                "source": "fallback"
            }
    
    def select_case_study(self, lead: Dict[str, Any], research: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use AI to select the most relevant case study for this lead.
        
        Instead of brittle keyword matching, let the LLM understand context
        and pick the case study that will resonate most.
        """
        company = lead.get('company') or 'Unknown'
        title = lead.get('title') or ''
        their_space = research.get('their_space') or lead.get('industry') or ''
        what_they_do = research.get('what_they_do') or ''
        pain_guess = research.get('likely_pain_point') or ''
        
        # Build case study summaries for the AI
        case_study_summaries = []
        for key, cs in self.case_studies.items():
            # Skip aliases (roboapply, stratmap, timpl)
            if key in ['roboapply', 'stratmap', 'timpl']:
                continue
            case_study_summaries.append(f"""
- {key}:
  Company type: {cs.get('company_hint', cs.get('company_name', 'unknown'))}
  What we built: {cs.get('what_we_built', 'unknown')}
  Result: {cs.get('result', 'unknown')}
  Timeline: {cs.get('timeline', 'unknown')}
  Best for: {', '.join(cs.get('relevance', []))}""")
        
        system_prompt = """You pick the best case study for a cold email.

RULES:
1. The case study must RELATE to their business or pain point
2. A construction tech company → enterprise/cost reduction case study (NOT SaaS MVP)
3. An AI startup → AI/automation case study (NOT legacy modernization)
4. A fintech → fintech or fast shipping case study
5. If nothing matches well, pick the most UNIVERSAL one (enterprise_modernization or hr_tech_ai)

Return ONLY the case study key (e.g., "enterprise_modernization"), nothing else."""

        user_prompt = f"""Pick the best case study for:

Company: {company}
Their space: {their_space}
What they do: {what_they_do}
Their likely pain: {pain_guess}
Contact's title: {title}

CASE STUDIES:
{chr(10).join(case_study_summaries)}

Which case study key is most relevant? Return ONLY the key."""

        try:
            content = self._call_llm(system_prompt, user_prompt, temperature=0.3)
            selected_key = content.strip().lower().replace('"', '').replace("'", "")
            
            # Validate the key exists
            if selected_key in self.case_studies:
                result = self.case_studies[selected_key].copy()
                result['selected_by'] = 'ai'
                return result
        except Exception as e:
            print(f"   ⚠️ AI case study selection failed: {e}")
        
        # Fallback to enterprise_modernization (most universal)
        result = self.case_studies.get('enterprise_modernization', list(self.case_studies.values())[0]).copy()
        result['selected_by'] = 'fallback'
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
                "unique_angle": "we shipped an HR tech startup's AI system in 8 weeks",
                "case_study": CASE_STUDIES.get("hr_tech_ai", CASE_STUDIES.get("roboapply", {})),
                "front_end_offer": "free 30-min architecture review",
                "trigger_signal": "actively building/scaling product"
            }
        }
    
    def classify_lead_icp(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify whether a lead is an Ideal Customer Profile (ICP) match.
        
        Based on TK Kader's ICP Framework:
        - 10x better: We solve an urgent problem better than alternatives
        - Data-backed: Classification is based on criteria, not wishlist
        - Trackable: Returns structured data for analytics
        
        Returns:
            {
                "is_icp": True/False,
                "icp_template": "template_name" or None,
                "icp_score": 0.0-1.0,
                "icp_reasons": ["reason1", "reason2", ...],
                "non_icp_reasons": ["reason1", ...]  # If not ICP
            }
        """
        title = (lead.get("title") or "").lower()
        company = (lead.get("company") or "").lower()
        industry = (lead.get("industry") or "").lower()
        enrichment = lead.get("enrichment", {})
        
        # Initialize scoring
        score = 0.0
        reasons = []
        non_icp_reasons = []
        matched_template = None
        
        # === TITLE MATCH (40% weight) ===
        # Ideal: Decision-makers who can buy and need dev help
        decision_maker_titles = [
            "founder", "co-founder", "ceo", "cto", "chief technology",
            "vp engineering", "head of engineering", "vp product",
            "head of product", "cpo", "chief product"
        ]
        
        technical_titles = [
            "cto", "chief technology", "vp engineering", "head of engineering",
            "engineering director", "software director"
        ]
        
        is_decision_maker = any(t in title for t in decision_maker_titles)
        is_technical = any(t in title for t in technical_titles)
        
        if is_decision_maker:
            score += 0.40
            reasons.append(f"Decision-maker title: {lead.get('title')}")
            if is_technical:
                reasons.append("Technical decision-maker (can evaluate our work)")
        else:
            non_icp_reasons.append(f"Not a decision-maker title: {lead.get('title')}")
        
        # === COMPANY SIGNALS (30% weight) ===
        # Look for signals that suggest they need dev help
        
        # Funded startup signal
        funding_keywords = ["series a", "series b", "seed", "funded", "raised", "venture"]
        company_lower = (company + " " + enrichment.get("company_description", "")).lower()
        if any(kw in company_lower for kw in funding_keywords):
            score += 0.15
            reasons.append("Funded company (has budget for dev work)")
        
        # Scaling/growth signals
        growth_keywords = ["growing", "scaling", "hiring", "expanding", "fast-growing"]
        if any(kw in company_lower for kw in growth_keywords):
            score += 0.15
            reasons.append("Growth signals (likely need to ship faster)")
        
        # Tech company signals (our wheelhouse)
        tech_keywords = ["software", "saas", "platform", "app", "tech", "ai", "fintech", 
                        "healthtech", "edtech", "proptech", "automation"]
        if any(kw in company_lower or kw in industry for kw in tech_keywords):
            score += 0.15
            reasons.append("Tech/software company (perfect fit for our services)")
        else:
            non_icp_reasons.append("Not clearly a tech/software company")
        
        # === ENRICHMENT SIGNALS (20% weight) ===
        if enrichment.get("has_enrichment"):
            # Job posting signals (they're hiring = maybe stretched thin)
            if enrichment.get("is_hiring_engineers"):
                score += 0.10
                reasons.append("Currently hiring engineers (team at capacity)")
            
            # Tech stack signals (we work with these)
            tech_stack = enrichment.get("tech_stack", [])
            our_stack = ["python", "react", "node", "aws", "typescript", "javascript", 
                        "django", "fastapi", "nextjs", "postgresql", "mongodb"]
            matching_tech = [t for t in tech_stack if any(our in t.lower() for our in our_stack)]
            if matching_tech:
                score += 0.10
                reasons.append(f"Tech stack we excel at: {', '.join(matching_tech[:3])}")
        
        # === PAIN POINT ALIGNMENT (10% weight) ===
        # Match to specific ICP template
        for template_name, template in ICP_TEMPLATES.items():
            template_titles = [t.lower() for t in template.get("titles", [])]
            template_industries = [i.lower() for i in template.get("industries", [])]
            
            title_match = any(t in title for t in template_titles)
            industry_match = any(i in industry for i in template_industries) if industry else False
            
            if title_match:
                if industry_match or not industry:  # Industry match OR industry unknown
                    matched_template = template_name
                    score += 0.10
                    reasons.append(f"Matches ICP template: {template_name}")
                    break
        
        # === FINAL CLASSIFICATION ===
        # ICP if score >= 0.50 (need at least decision-maker + one other signal)
        is_icp = score >= 0.50
        
        if not is_icp and not non_icp_reasons:
            non_icp_reasons.append("Insufficient signals to classify as ICP")
        
        return {
            "is_icp": is_icp,
            "icp_template": matched_template,
            "icp_score": round(score, 2),
            "icp_reasons": reasons,
            "non_icp_reasons": non_icp_reasons
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
        
        # Build personalization context from enrichment
        has_real_data = research.get('source') == 'website_enrichment'
        conversation_starters = research.get('conversation_starters', [])
        what_they_do = research.get('what_they_do', '')
        their_space = research.get('their_space', industry)
        pain_guess = research.get('likely_pain_point', '')
        
        # Determine opening strategy based on research confidence
        if research.get('confidence') == 'high' and has_real_data:
            # We have REAL data from their website
            starters_text = "\\n".join([f"  - \"{s}\"" for s in conversation_starters[:2]]) if conversation_starters else "none"
            opening_instruction = f"""**USE THIS REAL DATA FROM THEIR WEBSITE:**
What they do: {what_they_do or 'unknown'}
Their space: {their_space or 'unknown'}
Likely pain point: {pain_guess or 'shipping fast'}

**SUGGESTED CONVERSATION STARTERS (use one or adapt):**
{starters_text}

Pick a starter that sounds curious, not creepy. Then connect it to their likely pain point."""
        elif research.get('confidence') == 'medium':
            opening_instruction = f"""Use this hook: "{research.get('conversation_hook', '')}"
Be casual and direct - like texting a colleague, not writing a formal email."""
        else:
            opening_instruction = f"""Be direct and honest - no fake observations:
- "{company} caught my eye" or "{company} is doing interesting stuff in [their space]"
- Ask a genuine question about challenges in their industry
- Just get to the point quickly
DO NOT fake observations like "saw you're hiring" or "noticed your growth"."""
        
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
        
        # Case study reference - use company_hint for natural phrasing
        # e.g., "an enterprise company" instead of "Enterprise / Staffing"
        company_hint = case_study.get('company_hint') or case_study.get('company_name') or 'a similar company'
        case_study_reference = company_hint
        
        # =================================================================
        # LEADGENJAY'S FRAMEWORK (from 90-page doc + his actual emails)
        # =================================================================
        # His CORE insight: "I consider that first sentence the preview text.
        # You don't want them to think you're being pitched before they open."
        #
        # Line 1 = PREVIEW TEXT - sounds like friend texting
        # Line 2 = POKE THE BEAR - ask a QUESTION about how they do things
        # Line 3 = CASE STUDY - must match the pain, specific numbers
        # Line 4 = SOFT CTA - "thoughts?" "worth a chat?"
        # =================================================================
        
        system_prompt = f"""You are LeadGenJay writing a cold email.

You've sent thousands of these. You know what works.

**YOUR PHILOSOPHY:**
- The first line is PREVIEW TEXT. They see it before opening. If it looks like a pitch, they delete without opening.
- You write like you're texting a friend, not writing a business email.
- You NEVER say "most teams struggle with X" - that's lazy templated garbage.
- You poke the bear by asking a QUESTION about how they handle something specific.
- The whole email flows like ONE conversation, not 4 disconnected lines.

**YOUR 4-LINE STRUCTURE:**

LINE 1 - THE PREVIEW TEXT:
This shows in inbox before they open. Sound like a friend texting.
GOOD: "hey {first_name.lower()}, random q" / "quick one for you" / "this might be off base"
BAD: "{company}'s growth caught my eye" / "saw you're doing X" (reveals pitch = instant delete)

LINE 2 - POKE THE BEAR:
Ask a QUESTION about a UNIVERSAL pain (speed, cost, manual work, hiring) that ANY business faces.
Make it feel relevant to their world without being too niche.
GOOD: "are you guys still doing [process] manually or did you automate that?"
GOOD: "is your team stuck maintaining stuff instead of building new features?"
GOOD: "how are you handling dev capacity while also [growing/fundraising/scaling]?"
BAD: "Managing compliance is getting harder" (statement, not question)
BAD: "most teams struggle with..." (lazy, everyone says this)

LINE 3 - CASE STUDY:
**CRITICAL: USE THE EXACT CASE STUDY I GIVE YOU. DO NOT CHANGE THE COMPANY TYPE.**
If I say "helped a healthtech startup" - say EXACTLY that, even if the prospect is in pet tech.
The case study is REAL. Changing it is LYING. Never fabricate.
Frame it around a UNIVERSAL outcome (speed, cost savings, faster shipping) that resonates with anyone.

LINE 4 - SOFT CTA:
"thoughts?" / "worth a quick chat?" / "am I way off here?"

**RULES:**
- Subject: 2-3 lowercase words ("quick q" / "random thought")
- Body: 35-50 words TOTAL
- 4 short paragraphs, blank lines between
- NO em dashes (—), NO corporate jargon (no "streamline", "leverage", "optimize")
- Contractions always (don't, can't, won't)
- 6th grade reading level
- NEVER change or fabricate the case study company type
{improvement_prompt if improvement_prompt else ""}

Return JSON: {{"subject": "...", "body": "line1\\n\\nline2\\n\\nline3\\n\\nline4"}}"""

        # Build enrichment context for AI pain point generation
        enrichment_context = {
            'what_they_do': what_they_do,
            'their_space': their_space,
            'pain_point_guess': pain_guess
        } if has_real_data else None
        
        # Get AI-generated pain point based on context
        industry_pain_point = get_industry_pain_point(industry, title, enrichment_context)
        
        # Use enrichment pain point if available, otherwise use AI-generated one
        actual_pain_point = pain_guess if (has_real_data and pain_guess) else industry_pain_point
        
        user_prompt = f"""Write a LeadGenJay-style cold email.

TO: {first_name} at {company} ({title})
INDUSTRY: {their_space or industry or "tech"}

ASK A QUESTION ABOUT ONE OF THESE UNIVERSAL PAINS:
- Manual processes that should be automated
- Dev team stretched thin / can't hire fast enough  
- Shipping too slow / roadmap slipping
- Tech debt vs new features tradeoff

Pick whichever feels natural for a {title}.

**CASE STUDY - USE WORD FOR WORD:**
"{case_study_reference}" achieved "{case_study.get('result_short', case_study.get('result'))}" in "{case_study.get('timeline')}"

⚠️ HONESTY CHECK: The prospect is in {their_space or industry or 'tech'}. Your case study is about "{case_study_reference}".
These may not match - THAT'S OK. Use "{case_study_reference}" exactly as written. Do NOT change it to "{their_space or industry or 'tech'}". Lying destroys trust.

**WRITE 4 LINES:**

1. Preview text (friend): "hey {first_name.lower()}, quick one." or "random q for you."

2. Question (universal pain): "are you guys still [doing X manually]?" or "is your team stuck [maintaining vs building]?"

3. Case study (VERBATIM): "helped {case_study_reference} {case_study.get('result_short', 'ship faster')} in {case_study.get('timeline', '8 weeks')}."

4. Soft CTA: "thoughts?"

Return JSON only."""

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
            
            # CRITICAL: Check for HALLUCINATED case studies
            # If AI changed the case study company type, use fallback
            body_lower = body.lower()
            expected_cs = case_study_reference.lower()
            
            # List of hallucination patterns - AI changing case study to match prospect industry
            hallucination_indicators = [
                f"{industry.lower()} company" if industry else None,
                f"{industry.lower()} startup" if industry else None,
                f"{industry.lower()} team" if industry else None,
                "pet tech", "legal tech", "legaltech", "edtech", "foodtech", "food tech",
                "logistics company", "sustainability", "beverage tech",
            ]
            hallucination_indicators = [h for h in hallucination_indicators if h]
            
            # Check if AI hallucinated a case study
            has_hallucination = any(h in body_lower for h in hallucination_indicators if h not in expected_cs)
            has_real_case_study = expected_cs in body_lower or any(
                variant.lower() in body_lower 
                for variant in [
                    case_study.get('company_name', ''),
                    case_study.get('company_hint', ''),
                ]
            )
            
            if has_hallucination and not has_real_case_study:
                print(f"   ⚠️ AI hallucinated case study (expected '{case_study_reference}'), using fallback...")
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
                "i've been following",
                "i've been watching",
                "been following",
                "been watching",
            ]
            
            # Check for bad patterns
            starts_bad = any(first_line.startswith(p) for p in bad_start_patterns if p)
            
            # Check for formal/long subjects (should be 2-3 words)
            subject_words = len(subject.split())
            subject_is_formal = subject_words > 4 or any(w in subject.lower() for w in ['thoughts on', 'regarding', 'about your', 'question about'])
            
            # Also check for subject being just "Name?"
            subject_is_weak = subject.strip().lower() in [
                f"{first_name.lower()}?", 
                f"{first_name.lower()} ?",
                first_name.lower(),
            ]
            
            if subject_is_formal or subject_is_weak:
                print(f"   ⚠️ Subject '{subject}' is too formal/weak, using: {suggested_subject}")
                subject = suggested_subject
            
            if starts_bad:
                print(f"   ⚠️ Email starts with stalker pattern, using fallback...")
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
            # NEW: Lazy generic phrases
            "scaling is hard",
            "scaling is tough",
            "growth is hard",
            "growth is tough",
            "must be tough",
            "must hurt",
            "must be a pain",
            "must be a headache",
            "must be challenging",
            "funding is a challenge",
        ]
        
        # NEW: Lazy templated patterns to check
        lazy_patterns = [
            r"^(random|odd|quick)\s+(thought|q)\.\s+\w+\s+scaling\s+fast",
            r"^(random|odd|quick)\s+(thought|q)\.\s+\w+('s)?\s+growth\s+(is\s+)?(fast|tough|hard)",
            r"\bscaling fast\.\s*(scaling|growth)\s+is\s+(hard|tough)",
        ]
        
        # Check for double CTAs (desperate look)
        cta_phrases = ["worth a chat", "worth a quick chat", "interested", "make sense", "open to", "curious if"]
        
        body_lower = body.lower()
        first_line = body.split('\n')[0].lower() if body else ""
        issues = []
        
        for phrase in banned_phrases:
            if phrase in body_lower:
                issues.append(f"Contains banned phrase: '{phrase}'")
        
        # NEW: Check for lazy templated patterns
        for pattern in lazy_patterns:
            if re.search(pattern, first_line):
                issues.append(f"Lazy templated opener detected: '{first_line[:50]}...'")
                break
        
        # NEW: Check minimum word count
        word_count = len(body.split())
        if word_count < 25:
            issues.append(f"Email too short ({word_count} words) - feels robotic")
        
        # Count CTAs
        cta_count = sum(1 for cta in cta_phrases if cta in body_lower)
        if cta_count > 1:
            issues.append(f"Multiple CTAs detected ({cta_count}) - looks desperate")
        
        # Check first line for robotic patterns
        if first_line.startswith("i noticed") or first_line.startswith("i saw"):
            issues.append("Opens with robotic 'I noticed/saw' pattern")
        
        # Check sentence lengths
        sentences = [s.strip() for s in body.replace('\n', '. ').split('.') if s.strip()]
        for s in sentences:
            s_word_count = len(s.split())
            if s_word_count > 15:
                issues.append(f"Long sentence ({s_word_count} words): '{s[:40]}...'")
        
        # Log warnings
        for issue in issues:
            print(f"⚠️  VALIDATION WARNING: {issue}")
        
        return body
    
    def _fallback_email(self, lead: Dict, context: Dict, research: Dict, case_study: Dict, cta: str = None) -> Dict[str, str]:
        """
        Fallback email that sounds human, not templated.
        Uses LeadGenJay structure: curiosity hook → pain → case study → soft CTA
        
        CRITICAL: Must include company name and feel personalized even in fallback.
        Uses research data when available for better personalization.
        NO EM DASHES - use commas/periods instead
        NO lazy phrases like "scaling is hard" or "[Company] scaling fast"
        """
        first_name = lead.get('first_name') or 'there'
        company = lead.get('company') or 'your company'
        industry = lead.get('industry') or ''
        title = lead.get('title') or ''
        
        # Get research-based data if available
        likely_pain = research.get('likely_pain_point', '') if research else ''
        their_space = research.get('their_space', industry) if research else industry
        what_they_do = research.get('what_they_do', '') if research else ''
        
        # Varied subject lines (NEVER just "name?")
        subjects = [
            "random thought",
            "quick idea",
            "hey quick q",
            f"{company.split()[0].lower()} question" if company else "quick thought",
            "saw something",
            "quick q",
        ]
        
        # PERSONALIZED openers - LeadGenJay: Line 1 = preview text, should NOT reveal pitch
        # These should sound like they could be from a friend/colleague
        company_openers = [
            f"quick one for you.",
            f"had a thought about {company}.",
            f"random q about the eng setup.",
            f"this might be off base but...",
            f"quick thought on something.",
        ]
        
        # Use AI-generated pain point if available, otherwise use contextual fallbacks
        # LeadGenJay: Poke the bear with OBSERVATION, not "most teams struggle with X"
        if likely_pain and len(likely_pain) > 10:
            # Clean up the AI pain point to sound conversational
            pain = likely_pain.lower().strip()
            
            # Remove any personal references like "for mike" "for tom"
            import re
            pain = re.sub(r'\bfor\s+\w+\b', '', pain)
            pain = re.sub(r'\b(his|her|their)\s+team\b', 'teams', pain)
            
            # If pain point is too long (>15 words), use industry-specific fallback
            if len(pain.split()) > 15:
                if 'health' in industry.lower() or 'medical' in industry.lower():
                    pains = ["HIPAA compliance turns every 2-week feature into a 3-month project."]
                elif 'fintech' in industry.lower() or 'finance' in industry.lower():
                    pains = ["compliance keeps blocking releases while competitors ship weekly."]
                elif 'construction' in industry.lower():
                    pains = ["coordinating sites while building product means something always drops."]
                else:
                    pains = ["shipping features while fundraising usually means something drops."]
            else:
                if not pain.endswith('.'):
                    pain = pain + '.'
                pains = [pain]
        # LEADGENJAY STYLE: Poke the bear with a QUESTION, not a statement
        # The question should make them think, then the case study answers it
        elif 'health' in industry.lower() or 'medical' in industry.lower():
            pains = [
                "are you guys still doing manual HIPAA audits or did you automate that?",
                "how's the team handling compliance while also shipping fast?",
                "curious - do compliance reviews still take weeks on your end?",
            ]
        elif 'fintech' in industry.lower() or 'finance' in industry.lower():
            pains = [
                "how are you handling SOC2 stuff while also building product?",
                "are compliance audits still eating into your feature time?",
                "curious if PCI compliance is slowing down releases there too.",
            ]
        elif 'construction' in industry.lower() or 'infrastructure' in industry.lower():
            pains = [
                "how's the team syncing data across job sites right now?",
                "are site inspections still bottlenecking your project timelines?",
                "curious how you're handling field data while also building product.",
            ]
        elif 'cto' in title.lower() or 'engineer' in title.lower() or 'technical' in title.lower():
            pains = [
                "is your best talent stuck maintaining legacy stuff or actually building?",
                "how are you balancing tech debt vs new features these days?",
                "curious if you're still fighting fires or finally ahead of them.",
            ]
        else:
            pains = [
                "how are you handling dev capacity while also fundraising?",
                "is hiring senior devs taking forever there too?",
                "curious how you're keeping velocity up with a lean team.",
            ]
        
        # VARIED case study presentations
        cs_result = case_study.get('result_short', '3x faster shipping') if case_study else '3x faster shipping'
        cs_timeline = case_study.get('timeline', '8 weeks') if case_study else '8 weeks'
        cs_company_hint = case_study.get('company_hint', 'a startup') if case_study else 'a startup'
        
        # Check if timeline is already in the result to avoid duplication like "8 weeks in 8 weeks"
        timeline_in_result = cs_timeline.lower() in cs_result.lower() or 'weeks' in cs_result.lower() or 'months' in cs_result.lower()
        
        # Use company_hint for natural phrasing, avoid raw industry strings
        if timeline_in_result:
            case_study_lines = [
                f"we helped {cs_company_hint} hit {cs_result}.",
                f"worked with {cs_company_hint} recently, hit {cs_result}.",
                f"{cs_company_hint} we know was in the same spot, now at {cs_result}.",
            ]
        else:
            case_study_lines = [
                f"we helped {cs_company_hint} hit {cs_result} in {cs_timeline}.",
                f"worked with {cs_company_hint} recently, they went from stuck to {cs_result} in {cs_timeline}.",
                f"{cs_company_hint} we know was in the same spot, now they're at {cs_result} ({cs_timeline} later).",
            ]
        
        # Use provided CTA or pick one
        ctas = cta or random.choice([
            "worth a quick chat?",
            "ring any bells?",
            "sound familiar?",
            "crazy or worth exploring?",
            "any of this hit home?",
            "make sense for you?",
        ])
        
        subject = random.choice(subjects)
        opener = random.choice(company_openers)
        pain = random.choice(pains)
        case_study_line = random.choice(case_study_lines)
        
        # Build email following LeadGenJay structure with proper newlines
        body = f"""{opener}

{pain}

{case_study_line}

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
        "Email 2 is in the same thread as Email 1"
        """
        first_name = lead.get('first_name') or 'there'
        company = lead.get('company') or ''
        original_subject = previous[0]['subject'] if previous else "previous"
        
        system_prompt = """You are LeadGenJay writing follow-up #2.

They didn't reply to your first email. That's fine - they're busy.

**LEADGENJAY'S FOLLOW-UP RULES:**
- Same thread (Re: original subject)
- UNDER 30 WORDS - even shorter than email 1
- Add GENUINE value - share an insight, a specific tip, or offer something
- NEVER say "just following up", "circling back", "bumping this", "checking in"
- NEVER guilt trip or sound desperate
- Sound like a friend who thought of something helpful

**GOOD FOLLOW-UP PATTERNS:**
- "one thing I forgot - [specific insight related to their pain]"
- "fwiw - [quick tip or resource]. happy to share more."
- "forgot to mention - [something valuable]"

**BAD PATTERNS (NEVER USE):**
- "just following up on my last email"
- "wanted to circle back"
- "bumping this to the top of your inbox"
- "did you get a chance to read my email?"
- "I hope this email finds you well"
- "per my last email"

Write like you're texting a friend who you thought of something useful for.
ALL LOWERCASE. No capital letters except proper nouns.

Return JSON: {"subject": "Re: [original]", "body": "..."}"""

        user_prompt = f"""Follow up with {first_name} at {company}.
Original subject: {original_subject}

Write a SHORT follow-up (under 30 words) that adds value.
Don't repeat what you said before - add something NEW and helpful.

Example format:
one thing I forgot -

we actually documented how we did the 3.2x deploy speedup. might be useful for your team.

want me to send it over?"""

        try:
            content = self._call_llm(system_prompt, user_prompt, temperature=0.85, json_mode=True)
            result = json.loads(content)
            body = result.get("body") or ""
            if not body.strip():
                # LeadGenJay-style fallback
                return {
                    "subject": f"Re: {original_subject}",
                    "body": f"""one thing I forgot -

we documented how we hit those deploy numbers. might be useful for {company}.

want me to send it over?"""
                }
            
            # Humanize
            body = humanize_email(body)
            
            return {
                "subject": f"Re: {original_subject}",
                "body": body
            }
        except Exception as e:
            print(f"Error generating follow-up: {e}")
            return {
                "subject": f"Re: {original_subject}",
                "body": f"""one thing I forgot -

we documented how we hit those deploy numbers. might be useful for {company}.

want me to send it over?"""
            }
    
    def _generate_followup_new_thread(self, lead: Dict, context: Dict, previous: List) -> Dict:
        """
        Follow-up #3: NEW thread, completely different angle
        
        LeadGenJay: "Email 3 should be a fresh start with different subject and angle"
        "Give away something valuable for free - the front-end offer"
        """
        first_name = lead.get('first_name') or 'there'
        company = lead.get('company') or ''
        front_end_offer = context.get('front_end_offer') or 'free architecture review'
        
        system_prompt = """You are LeadGenJay writing follow-up #3 - a FRESH email.

They didn't reply to emails 1 or 2. No worries. This is a completely fresh start.

**LEADGENJAY'S EMAIL 3 RULES:**
- NEW subject line - something like "different thought" or "quick idea"
- Different angle than before - offer your FRONT-END OFFER (free value)
- Don't reference previous emails AT ALL
- Under 40 words
- End with a soft question

**FRONT-END OFFER CONCEPT (LeadGenJay):**
"Give away something valuable for free. If someone raises their hand for the free thing,
you have a warm lead. The free thing should take 15-30 mins of your time and showcase
your expertise."

Examples of front-end offers:
- Free architecture review
- Free technical audit
- Free 30-min strategy session
- Free code review
- Free deployment assessment

**FORMAT:**
Line 1: their name + dash
Line 2-3: the offer (specific, valuable, no pitch)
Line 4: soft CTA question

ALL LOWERCASE. No capital letters except proper nouns.
DO NOT include signature or sign-off. End with the question.

Return JSON: {"subject": "...", "body": "..."}"""

        previous_subjects = [e.get('subject', '') for e in previous]
        
        user_prompt = f"""Fresh email to {first_name} at {company}.
Previous subjects used (DON'T repeat): {previous_subjects}
Front-end offer to make: {front_end_offer}

Write a fresh email offering the front-end offer. Under 40 words.

Example:
{first_name.lower()} -

totally different idea. we're doing free {front_end_offer}s this month for teams scaling fast.

30 mins, specific feedback, no pitch.

want one?"""

        try:
            content = self._call_llm(system_prompt, user_prompt, temperature=0.9, json_mode=True)
            result = json.loads(content)
            subject = result.get("subject") or "different thought"
            body = result.get("body") or ""
            if not body.strip():
                # LeadGenJay-style fallback
                return {
                    "subject": "different thought",
                    "body": f"""{first_name.lower()} -

totally different idea. we're doing free {front_end_offer}s this month.

30 mins, specific feedback, no pitch.

interested?""",
                    "new_thread": True
                }
            
            # Humanize
            body = humanize_email(body)
            
            return {
                "subject": subject,
                "body": body,
                "new_thread": True
            }
        except Exception as e:
            return {
                "subject": "different thought",
                "body": f"""{first_name.lower()} -

totally different idea. we're doing free {front_end_offer}s this month.

30 mins, specific feedback, no pitch.

interested?""",
                "new_thread": True
            }
    
    def _generate_breakup_email(self, lead: Dict, context: Dict, previous: List) -> Dict:
        """
        Final email - helpful redirect, not guilt trip
        
        LeadGenJay: "Should I reach out to someone else?" is incredibly effective
        because it triggers reciprocity. They feel bad ignoring you, and often
        either respond or refer you to someone else.
        """
        first_name = lead.get('first_name') or 'there'
        company = lead.get('company') or ''
        
        # LeadGenJay tip: "Should I reach out to someone else?" works well
        # Keep it SHORT and non-desperate
        body = f"""{first_name.lower()} -

last note from me. if dev bandwidth becomes a priority at {company}, happy to help.

should I reach out to someone else on your team, or close the loop here?

either way, rooting for you guys."""

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
