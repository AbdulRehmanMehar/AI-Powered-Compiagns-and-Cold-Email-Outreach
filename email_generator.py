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
# CIRCUIT BREAKER - PREVENT INFINITE RETRY LOOPS
# =============================================================================

class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open (too many failures)"""
    pass


class APICircuitBreaker:
    """
    Circuit breaker to prevent infinite retry loops when API is down.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, block all requests for timeout period
    - HALF_OPEN: Testing if service recovered
    
    This prevents burning through API quota when service is degraded.
    """
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 300):
        """
        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            timeout: Seconds to wait before attempting recovery (default 5 min)
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.success_count = 0  # For half-open state
    
    def call(self, func, *args, **kwargs):
        """
        Execute function with circuit breaker protection.
        
        Raises:
            CircuitBreakerOpen: If circuit is open (too many failures)
        """
        # Check if circuit should transition from OPEN to HALF_OPEN
        if self.state == "OPEN":
            time_since_failure = time.time() - (self.last_failure_time or 0)
            if time_since_failure > self.timeout:
                logger.info(f"🔄 Circuit breaker transitioning to HALF_OPEN (testing recovery)")
                self.state = "HALF_OPEN"
                self.success_count = 0
            else:
                wait_time = int(self.timeout - time_since_failure)
                raise CircuitBreakerOpen(
                    f"Circuit breaker OPEN - too many API failures. "
                    f"Retry in {wait_time}s"
                )
        
        # Execute the function
        try:
            result = func(*args, **kwargs)
            
            # Success! Handle state transitions
            if self.state == "HALF_OPEN":
                self.success_count += 1
                if self.success_count >= 2:  # Need 2 successes to close
                    logger.info(f"✅ Circuit breaker CLOSED (service recovered)")
                    self.state = "CLOSED"
                    self.failures = 0
            elif self.state == "CLOSED":
                # Reset failure count on success
                self.failures = 0
            
            return result
            
        except Exception as e:
            # Failure! Increment counter and potentially open circuit
            self.failures += 1
            self.last_failure_time = time.time()
            
            if self.state == "HALF_OPEN":
                # Failed during test - back to OPEN
                logger.warning(f"🔴 Circuit breaker back to OPEN (recovery test failed)")
                self.state = "OPEN"
            elif self.failures >= self.failure_threshold:
                # Too many failures - open the circuit
                logger.error(
                    f"🔴 Circuit breaker OPEN after {self.failures} consecutive failures. "
                    f"Blocking API calls for {self.timeout}s to prevent quota waste."
                )
                self.state = "OPEN"
            
            raise
    
    def reset(self):
        """Manually reset the circuit breaker"""
        self.failures = 0
        self.state = "CLOSED"
        self.success_count = 0
        logger.info("♻️  Circuit breaker manually reset")


# Global circuit breaker instance
_circuit_breaker = APICircuitBreaker(failure_threshold=5, timeout=300)


def get_circuit_breaker() -> APICircuitBreaker:
    """Get the global circuit breaker instance"""
    return _circuit_breaker


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
# Default Groq limits - these are seeded to DB on first run
# Users should update limits in MongoDB groq_model_limits collection
DEFAULT_GROQ_LIMITS = {
    # High capacity models - USE THESE FIRST
    'groq/compound': {'requests_per_minute': 30, 'requests_per_day': 250, 'tokens_per_minute': 70000, 'tokens_per_day': 10000000, 'priority': 1},
    'groq/compound-mini': {'requests_per_minute': 30, 'requests_per_day': 250, 'tokens_per_minute': 70000, 'tokens_per_day': 10000000, 'priority': 2},
    'llama-3.1-8b-instant': {'requests_per_minute': 30, 'requests_per_day': 14400, 'tokens_per_minute': 6000, 'tokens_per_day': 500000, 'priority': 3},
    
    # Medium capacity models
    'llama-3.3-70b-versatile': {'requests_per_minute': 30, 'requests_per_day': 1000, 'tokens_per_minute': 12000, 'tokens_per_day': 100000, 'priority': 4},
    'qwen/qwen3-32b': {'requests_per_minute': 60, 'requests_per_day': 1000, 'tokens_per_minute': 6000, 'tokens_per_day': 500000, 'priority': 5},
    'meta-llama/llama-4-maverick-17b-128e-instruct': {'requests_per_minute': 30, 'requests_per_day': 1000, 'tokens_per_minute': 6000, 'tokens_per_day': 500000, 'priority': 6},
    'meta-llama/llama-4-scout-17b-16e-instruct': {'requests_per_minute': 30, 'requests_per_day': 1000, 'tokens_per_minute': 30000, 'tokens_per_day': 500000, 'priority': 7},
    
    # Additional models for more capacity
    'openai/gpt-oss-120b': {'requests_per_minute': 30, 'requests_per_day': 1000, 'tokens_per_minute': 8000, 'tokens_per_day': 200000, 'priority': 8},
    'moonshotai/kimi-k2-instruct': {'requests_per_minute': 60, 'requests_per_day': 1000, 'tokens_per_minute': 10000, 'tokens_per_day': 300000, 'priority': 9},
    'allam-2-7b': {'requests_per_minute': 30, 'requests_per_day': 7000, 'tokens_per_minute': 6000, 'tokens_per_day': 500000, 'priority': 10},
}

# Fallback chain for chat completions (ordered by quality, then capacity)
# Strategy: Prioritize quality for cold emails, use smaller models only as last resort
GROQ_FALLBACK_CHAIN = [
    'groq/compound',                                    # Best quality - unlimited tokens!
    'groq/compound-mini',                               # Good quality - unlimited tokens!
    'llama-3.3-70b-versatile',                         # High quality 70B (1K/day, 100K tokens)
    'openai/gpt-oss-120b',                             # OpenAI 120B via Groq (1K/day, 200K tokens)
    'qwen/qwen3-32b',                                  # Good 32B model (1K/day, 500K tokens)
    'moonshotai/kimi-k2-instruct',                     # Moonshot Kimi K2 (1K/day, 300K tokens)
    'meta-llama/llama-4-maverick-17b-128e-instruct',  # Llama 4 17B (1K/day, 500K tokens)
    'meta-llama/llama-4-scout-17b-16e-instruct',      # Llama 4 Scout (1K/day, 500K tokens)
    'allam-2-7b',                                      # Allam 7B (7K/day, 500K tokens) - high request limit!
    'llama-3.1-8b-instant',                            # LAST RESORT - fast but lower quality (14.4K/day)
]

# Legacy compatibility
GROQ_MODEL_LIMITS = {k: {'daily': v['requests_per_day'], 'per_minute': v['requests_per_minute'], 'tokens_per_day': v['tokens_per_day']} for k, v in DEFAULT_GROQ_LIMITS.items()}

# In-memory cache (synced with DB periodically)
_rate_limit_cache = {}
_last_db_sync = None
DB_SYNC_INTERVAL = 30  # Sync with DB every 30 seconds


class GroqRateLimiter:
    """
    Rate limiter for Groq API with MongoDB persistence and model fallback.
    
    Features:
    - Stores limits AND usage in MongoDB (groq_model_limits collection)
    - Automatically seeds default limits on first run
    - Automatically falls back to other Groq models when rate limited
    - In-memory cache to reduce DB reads
    - Per-model tracking with daily reset
    
    Collection schema (groq_model_limits):
    {
        "model": "groq/compound",
        "requests_per_minute": 30,
        "requests_per_day": 250,
        "tokens_per_minute": 70000,
        "tokens_per_day": 10000000,
        "priority": 1,
        "enabled": true,
        "usage": {
            "date": "2026-01-30",
            "requests_today": 150,
            "tokens_today": 45000,
            "minute_requests": [timestamps...]
        }
    }
    """
    
    def __init__(self):
        self._db = None
        self._limits_collection = None
        self._cache = {}  # {model: {limits + usage}}
        self._cache_time = {}  # {model: timestamp}
        self._initialized = False
    
    @property
    def db(self):
        """Lazy load database connection"""
        if self._db is None:
            from database import db, groq_limits_collection
            self._db = db
            self._limits_collection = groq_limits_collection
            if not self._initialized:
                self._seed_defaults()
                self._initialized = True
        return self._limits_collection
    
    def _seed_defaults(self):
        """Seed default limits to database if not exists"""
        for model, limits in DEFAULT_GROQ_LIMITS.items():
            try:
                existing = self._limits_collection.find_one({"model": model})
                if not existing:
                    doc = {
                        "model": model,
                        **limits,
                        "enabled": True,
                        "usage": {
                            "date": self._get_today(),
                            "requests_today": 0,
                            "tokens_today": 0,
                            "minute_requests": []
                        },
                        "created_at": datetime.datetime.utcnow(),
                        "updated_at": datetime.datetime.utcnow()
                    }
                    self._limits_collection.insert_one(doc)
            except Exception as e:
                pass  # Ignore errors (e.g., duplicate key)
    
    def _get_today(self) -> str:
        """Get today's date as string"""
        return datetime.date.today().isoformat()
    
    def _load_model(self, model: str) -> dict:
        """Load model limits and usage from MongoDB"""
        today = self._get_today()
        try:
            doc = self.db.find_one({"model": model})
            if doc:
                usage = doc.get('usage', {})
                # Reset daily usage if:
                # 1. It's a new day, OR
                # 2. Model was depleted (give it a fresh start each load)
                is_new_day = usage.get('date') != today
                was_depleted = usage.get('depleted_reason') is not None
                
                if is_new_day or was_depleted:
                    usage = {
                        "date": today,
                        "requests_today": 0,
                        "tokens_today": 0,
                        "minute_requests": []
                        # Note: depleted_reason is NOT copied - fresh start
                    }
                    self._save_usage(model, usage)
                    if was_depleted:
                        logger.info(f"Reset depleted model {model} - fresh start")
                
                return {
                    'model': model,
                    'requests_per_minute': doc.get('requests_per_minute', 30),
                    'requests_per_day': doc.get('requests_per_day', 1000),
                    'tokens_per_minute': doc.get('tokens_per_minute', 6000),
                    'tokens_per_day': doc.get('tokens_per_day', 100000),
                    'priority': doc.get('priority', 99),
                    'enabled': doc.get('enabled', True),
                    'usage': usage
                }
        except Exception as e:
            print(f"   ⚠️ Error loading model {model} from DB: {e}")
        
        # Fallback to defaults if not in DB
        defaults = DEFAULT_GROQ_LIMITS.get(model, {})
        return {
            'model': model,
            'requests_per_minute': defaults.get('requests_per_minute', 30),
            'requests_per_day': defaults.get('requests_per_day', 1000),
            'tokens_per_minute': defaults.get('tokens_per_minute', 6000),
            'tokens_per_day': defaults.get('tokens_per_day', 100000),
            'priority': defaults.get('priority', 99),
            'enabled': True,
            'usage': {"date": today, "requests_today": 0, "tokens_today": 0, "minute_requests": []}
        }
    
    def _save_usage(self, model: str, usage: dict):
        """Save usage data to MongoDB"""
        try:
            self.db.update_one(
                {"model": model},
                {"$set": {"usage": usage, "updated_at": datetime.datetime.utcnow()}},
                upsert=True
            )
        except Exception as e:
            print(f"   ⚠️ Error saving usage for {model}: {e}")
    
    # Legacy compatibility methods
    def _get_cache(self, model: str) -> dict:
        """Legacy method - maps to new structure"""
        data = self._get_cached(model)
        usage = data.get('usage', {})
        return {
            'daily_count': usage.get('requests_today', 0),
            'tokens_used': usage.get('tokens_today', 0),
            'minute_requests': usage.get('minute_requests', []),
            'date': usage.get('date', self._get_today())
        }
    
    def _save_to_db(self, model: str, data: dict):
        """Legacy method - maps to new structure"""
        usage = {
            "date": data.get('date', self._get_today()),
            "requests_today": data.get('daily_count', 0),
            "tokens_today": data.get('tokens_used', 0),
            "minute_requests": data.get('minute_requests', [])[-100:]
        }
        self._save_usage(model, usage)
    
    def _get_cached(self, model: str) -> dict:
        """Get cached data for a model, loading from DB if needed"""
        now = time.time()
        today = self._get_today()
        
        # Check if cache is valid (30 second TTL)
        if model in self._cache:
            cache_age = now - self._cache_time.get(model, 0)
            cache_date = self._cache[model].get('usage', {}).get('date')
            if cache_age < DB_SYNC_INTERVAL and cache_date == today:
                return self._cache[model]
        
        # Load from DB
        data = self._load_model(model)
        self._cache[model] = data
        self._cache_time[model] = now
        return data
    
    def check_limit(self, model: str) -> tuple:
        """
        Check if model is within rate limits.
        Returns (can_proceed, wait_seconds, reason)
        """
        data = self._get_cached(model)
        
        if not data.get('enabled', True):
            return False, 0, "disabled"
        
        usage = data.get('usage', {})
        now = time.time()
        
        # Check if model was marked depleted (should have been reset by _load_model, but double-check)
        if usage.get('depleted_reason'):
            # Force reload to trigger reset
            self._cache.pop(model, None)
            data = self._get_cached(model)
            usage = data.get('usage', {})
        
        # Check daily request limit
        requests_today = usage.get('requests_today', 0)
        if requests_today >= data['requests_per_day']:
            return False, 0, "daily_limit"
        
        # Check daily token limit (leave 5% buffer, skip for "unlimited" 10M+)
        tokens_today = usage.get('tokens_today', 0)
        token_limit = data['tokens_per_day']
        if token_limit < 10000000 and tokens_today >= token_limit * 0.95:
            return False, 0, "token_limit"
        
        # Clean old minute requests
        minute_requests = [t for t in usage.get('minute_requests', []) if now - t < 60]
        usage['minute_requests'] = minute_requests
        
        # Check per-minute limit
        if len(minute_requests) >= data['requests_per_minute']:
            wait_time = 60 - (now - minute_requests[0])
            return False, max(0, wait_time), "minute_limit"
        
        return True, 0, "ok"
    
    def record_request(self, model: str, tokens_used: int = 2000):
        """Record a successful API request with token usage"""
        data = self._get_cached(model)
        usage = data.get('usage', {})
        
        usage['requests_today'] = usage.get('requests_today', 0) + 1
        usage['tokens_today'] = usage.get('tokens_today', 0) + tokens_used
        usage['minute_requests'] = usage.get('minute_requests', []) + [time.time()]
        usage['date'] = self._get_today()
        
        data['usage'] = usage
        self._cache[model] = data
        
        # Save to DB periodically (every 5 requests)
        if usage['requests_today'] % 5 == 0:
            self._save_usage(model, usage)
    
    def mark_model_depleted(self, model: str, reason: str = "rate_limit"):
        """
        Mark a model as depleted (hit rate limit from API).
        The model will be reset on next load/initialization.
        """
        data = self._get_cached(model)
        usage = data.get('usage', {})
        
        # Just mark as depleted - don't max out counters
        # The depleted_reason flag will trigger a reset on next load
        usage['depleted_reason'] = reason
        usage['depleted_at'] = time.time()
        # Don't change the date - let the reset logic handle it
        
        data['usage'] = usage
        self._cache[model] = data
        self._save_usage(model, usage)
        
        logger.warning(f"Model {model} marked as depleted: {reason}")
    
    def get_all_models(self) -> list:
        """Get all models with their limits and usage from DB"""
        try:
            return list(self.db.find({}, {"_id": 0}).sort("priority", 1))
        except Exception as e:
            return []
    
    def update_model_limits(self, model: str, limits: dict):
        """Update limits for a model in the database"""
        try:
            self.db.update_one(
                {"model": model},
                {"$set": {**limits, "updated_at": datetime.datetime.utcnow()}},
                upsert=True
            )
            if model in self._cache:
                del self._cache[model]
            print(f"   ✅ Updated limits for {model}")
        except Exception as e:
            print(f"   ❌ Error updating limits: {e}")
    
    def get_best_available_model(self, preferred_model: str = None) -> Optional[str]:
        """
        Get the best available model using smart load balancing.
        
        STRATEGY: Weighted Load Balancing with Quality Preference
        - Distributes load proportionally based on remaining capacity
        - Prefers higher-quality models when capacity is similar
        - Automatically shifts load away from models approaching limits
        
        Returns None if all models are rate limited.
        """
        # Get all enabled models sorted by priority
        try:
            all_models = self.get_all_models()
            enabled_models = [m for m in all_models if m.get('enabled', True)]
        except:
            enabled_models = []
        
        # Build chain: use DB models if available, else fallback to hardcoded
        if enabled_models:
            chain_models = enabled_models
        else:
            chain_models = [
                {'model': m, **DEFAULT_GROQ_LIMITS.get(m, {})} 
                for m in GROQ_FALLBACK_CHAIN
            ]
        
        # Calculate availability score for each model
        # Score = (remaining_capacity_pct * 100) - (priority * 5)
        # Higher score = better choice
        model_scores = []
        
        for m in chain_models:
            model = m['model']
            data = self._get_cached(model)
            
            # Check basic availability
            can_proceed, wait_time, reason = self.check_limit(model)
            if not can_proceed and reason != "minute_limit":
                continue
            if reason == "minute_limit" and wait_time > 5:
                continue
            
            usage = data.get('usage', {})
            
            # Calculate remaining capacity as percentage
            requests_today = usage.get('requests_today', 0)
            requests_limit = data.get('requests_per_day', 1000)
            tokens_today = usage.get('tokens_today', 0)
            tokens_limit = data.get('tokens_per_day', 100000)
            
            # For "unlimited" token models (10M+), only consider request limits
            if tokens_limit >= 10000000:
                remaining_pct = max(0, (requests_limit - requests_today) / requests_limit * 100)
            else:
                # Use the more restrictive limit
                request_remaining = max(0, (requests_limit - requests_today) / requests_limit * 100)
                token_remaining = max(0, (tokens_limit - tokens_today) / tokens_limit * 100)
                remaining_pct = min(request_remaining, token_remaining)
            
            # Priority bonus (lower priority number = better quality = higher bonus)
            priority = data.get('priority', 99)
            quality_bonus = max(0, 20 - priority * 2)  # Priority 1 = +18, Priority 10 = 0
            
            # Calculate final score
            score = remaining_pct + quality_bonus
            
            # Penalty for models below 20% capacity (avoid exhausting completely)
            if remaining_pct < 20:
                score -= 30
            
            model_scores.append({
                'model': model,
                'score': score,
                'remaining_pct': remaining_pct,
                'priority': priority,
                'wait_time': wait_time if reason == "minute_limit" else 0
            })
        
        if not model_scores:
            return None
        
        # Sort by score (highest first)
        model_scores.sort(key=lambda x: (-x['score'], x['priority']))
        
        # Select best model
        best = model_scores[0]
        
        # If needs a short wait, do it
        if best['wait_time'] > 0:
            time.sleep(best['wait_time'] + 0.5)
        
        # Log if switching from preferred model
        if preferred_model and best['model'] != preferred_model:
            pref_remaining = next(
                (m['remaining_pct'] for m in model_scores if m['model'] == preferred_model), 
                0
            )
            logger.info(
                f"Load balance: {preferred_model} ({pref_remaining:.0f}% left) → "
                f"{best['model']} ({best['remaining_pct']:.0f}% left, score: {best['score']:.0f})"
            )
        
        return best['model']
    
    def get_usage_stats(self) -> dict:
        """Get current usage statistics for all models including token usage"""
        stats = {}
        
        # Get all models from DB, fallback to hardcoded
        try:
            all_models = self.get_all_models()
            if not all_models:
                all_models = [{'model': m, **DEFAULT_GROQ_LIMITS.get(m, {})} for m in GROQ_FALLBACK_CHAIN]
        except:
            all_models = [{'model': m, **DEFAULT_GROQ_LIMITS.get(m, {})} for m in GROQ_FALLBACK_CHAIN]
        
        for m in all_models:
            model = m['model']
            data = self._get_cached(model)
            usage = data.get('usage', {})
            
            token_limit = data.get('tokens_per_day', 100000)
            tokens_used = usage.get('tokens_today', 0)
            requests_limit = data.get('requests_per_day', 1000)
            requests_used = usage.get('requests_today', 0)
            
            stats[model] = {
                'requests_today': requests_used,
                'requests_limit': requests_limit,
                'requests_remaining': requests_limit - requests_used,
                'tokens_used': tokens_used,
                'tokens_limit': token_limit,
                'tokens_remaining': max(0, token_limit - tokens_used),
                'percent_used': round(tokens_used / token_limit * 100, 1) if token_limit > 0 else 0,
                'enabled': data.get('enabled', True),
                'priority': data.get('priority', 99)
            }
        
        return stats
    
    def flush_to_db(self):
        """Force save all cached data to DB"""
        for model, data in self._cache.items():
            usage = data.get('usage', {})
            self._save_usage(model, usage)
    
    def show_load_distribution(self) -> str:
        """
        Show current load distribution across all models.
        Useful for monitoring load balancing effectiveness.
        """
        stats = self.get_usage_stats()
        lines = ["=== Model Load Distribution ==="]
        
        # Sort by percent used (descending)
        sorted_models = sorted(
            stats.items(), 
            key=lambda x: (not x[1].get('enabled', True), -x[1].get('percent_used', 0))
        )
        
        total_requests = sum(s['requests_today'] for s in stats.values())
        total_tokens = sum(s['tokens_used'] for s in stats.values())
        
        for model, s in sorted_models:
            if model not in GROQ_FALLBACK_CHAIN:
                continue
            enabled = "✅" if s.get('enabled', True) else "❌"
            pct = s.get('percent_used', 0)
            bar_len = int(pct / 5)  # 20 char bar max
            bar = "█" * bar_len + "░" * (20 - bar_len)
            
            req_info = f"{s['requests_today']:,}/{s['requests_limit']:,} req"
            tok_info = f"{s['tokens_used']:,}/{s['tokens_limit']:,} tok"
            
            lines.append(f"{enabled} {model[:35]:<35} [{bar}] {pct:5.1f}% | {req_info}")
        
        lines.append(f"\nTotal today: {total_requests:,} requests, {total_tokens:,} tokens")
        return "\n".join(lines)


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
        # Use current LLM provider (respects config.LLM_PROVIDER)
        client, model, provider = get_llm_client()
        
        # For Groq, use rate limiter and model rotation
        if provider == 'groq':
            rate_limiter = get_rate_limiter()
            available_model = rate_limiter.get_best_available_model()
            
            if not available_model:
                # Fallback to a sensible default
                return "your best engineers are stuck maintaining instead of building the next thing"
            
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
        else:
            # For Ollama/OpenAI, use directly without rate limiting
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You write specific, relatable pain points for cold emails. Be concise and insightful."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=100
            )
        
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
        # Disable SDK auto-retry - we handle retries ourselves with model rotation
        return Groq(api_key=config.GROQ_API_KEY, max_retries=0), model, 'groq'
    elif provider == 'ollama':
        from openai import OpenAI
        if model is None:
            model = getattr(config, 'OLLAMA_MODEL', 'qwen2.5:7b')
        base_url = getattr(config, 'OLLAMA_BASE_URL', 'http://localhost:11434')
        # Ollama is OpenAI-compatible - use /v1 endpoint
        return OpenAI(base_url=f"{base_url}/v1", api_key="ollama"), model, 'ollama'
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
        
        # Separate Ollama client for follow-ups (free, no rate limits)
        self._followup_client = None
        self._followup_model = getattr(config, 'OLLAMA_MODEL', 'qwen2.5:7b')
        self._followup_base_url = getattr(config, 'OLLAMA_BASE_URL', 'http://192.168.1.9:11434')
        
        # Show initialization message with available capacity
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
        elif self.provider == 'ollama':
            base_url = getattr(config, 'OLLAMA_BASE_URL', 'http://localhost:11434')
            print(f"📝 Email generator using: OLLAMA ({self.model})")
            print(f"   Server: {base_url}")
            print(f"   ✅ No rate limits - unlimited generation!")
        else:
            print(f"📝 Email generator using: {self.provider.upper()} ({self.model})")
    
    def _call_llm(self, system_prompt: str, user_prompt: str, temperature: float = 0.7, json_mode: bool = False) -> str:
        """
        Call the LLM (Groq, OpenAI, or Ollama) with rate limiting and automatic Groq model fallback.
        AGGRESSIVE: Automatically tries next model in chain when one hits rate limits.
        Returns the response content as string.
        """
        # For OpenAI or Ollama, just make the call directly
        if self.provider in ['openai', 'ollama']:
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
                
                # If it's a rate limit error or empty/invalid response, try next model
                if 'rate' in error_str and 'limit' in error_str:
                    # Mark this model as depleted for today (maxes out both requests AND tokens)
                    self.rate_limiter.mark_model_depleted(available_model, "429_rate_limit")
                    print(f"   ⚠️ {available_model} hit rate limit, marked as depleted, trying next model...")
                    continue
                elif 'empty response' in error_str or 'invalid json' in error_str:
                    # Model returned empty or invalid content, try next
                    print(f"   ⚠️ {available_model} returned bad response, trying next model...")
                    continue
                elif '413' in error_str or 'too large' in error_str or 'payload' in error_str:
                    # Prompt too large for this model, try next
                    print(f"   ⚠️ {available_model} returned 413 (prompt too large), trying next model...")
                    continue
                elif '503' in error_str or 'service unavailable' in error_str or '502' in error_str or 'bad gateway' in error_str or 'over capacity' in error_str:
                    # Service temporarily unavailable, try next model
                    print(f"   ⚠️ {available_model} returned 503/502 (service unavailable), trying next model...")
                    continue
                elif 'timeout' in error_str or 'timed out' in error_str or 'connection' in error_str:
                    # Connection issues, try next model
                    print(f"   ⚠️ {available_model} connection error, trying next model...")
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
        
        # Qwen-specific parameters for better output quality (works with Ollama)
        # These parameters help prevent ultra-short responses and improve instruction following
        if 'qwen' in model.lower() or (client.__class__.__name__ == 'OpenAI' and hasattr(client, 'base_url') and client.base_url and 'ollama' in str(client.base_url)):
            kwargs["top_p"] = 0.9      # Qwen works best with 0.8-0.95
            kwargs["max_tokens"] = 500  # Ensure space for 75-word emails
        
        # JSON mode - Groq supports this for Llama 3.3+
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        
        # Single attempt - let _call_llm handle fallback
        response = client.chat.completions.create(**kwargs)
        
        # Check for empty response - some models return empty content
        content = response.choices[0].message.content
        if not content or content.strip() == '':
            raise ValueError(f"Model {model} returned empty response")
        
        # If json_mode requested, validate it's actually valid JSON
        # This catches cases where model returns garbage or partial response
        if json_mode:
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                raise ValueError(f"Model {model} returned invalid JSON: {str(e)[:50]}")
        
        # Record successful Groq request with actual token usage
        if record_usage and self.rate_limiter:
            # Extract actual token usage from response
            tokens_used = 2000  # Default estimate
            if hasattr(response, 'usage') and response.usage:
                tokens_used = getattr(response.usage, 'total_tokens', 2000)
            self.rate_limiter.record_request(model, tokens_used)
        
        return content
    
    def _call_ollama_for_followup(self, system_prompt: str, user_prompt: str, temperature: float = 0.85) -> str:
        """
        Call Ollama/Qwen specifically for follow-up generation.
        Separate from _call_llm to keep initial email system untouched.
        Free, no rate limits, runs locally.
        """
        if self._followup_client is None:
            from openai import OpenAI
            self._followup_client = OpenAI(
                base_url=f"{self._followup_base_url}/v1",
                api_key="ollama"
            )
        
        try:
            response = self._followup_client.chat.completions.create(
                model=self._followup_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                top_p=0.9,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            
            content = response.choices[0].message.content
            if not content or content.strip() == '':
                raise ValueError("Ollama returned empty response")
            
            # Validate JSON
            json.loads(content)
            return content
            
        except Exception as e:
            print(f"   ⚠️ Ollama follow-up call failed: {e}")
            raise
    
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
        Select the most relevant case study for this lead.
        
        STRATEGY: Try keyword matching FIRST (fast & reliable), then AI fallback.
        This prevents the AI from always defaulting to enterprise_modernization.
        """
        company = lead.get('company') or 'Unknown'
        title = lead.get('title') or ''
        their_space = research.get('their_space') or lead.get('industry') or ''
        what_they_do = research.get('what_they_do') or ''
        pain_guess = research.get('likely_pain_point') or ''
        
        # FIRST: Try direct keyword matching (fast, reliable, no AI needed)
        context_text = f"{their_space} {what_they_do} {company} {pain_guess}".lower()
        
        keyword_map = {
            'healthtech_client': ['health', 'medical', 'hipaa', 'patient', 'clinical', 'hospital', 'pharma', 'medisync', 'healthcare'],
            'construction_tech': ['construction', 'building', 'field', 'site', 'infrastructure', 'buildtrack', 'architect'],
            'fintech_client': ['fintech', 'payment', 'banking', 'financial', 'transaction', 'lending', 'insurance'],
            'hr_tech_ai': ['hr', 'hiring', 'recruit', 'talent', 'applicant', 'job', 'workforce', 'ai', 'ml', 'machine learning', 'artificial intelligence', 'data', 'automation'],
            'saas_mvp': ['saas', 'mvp', 'startup', 'early-stage', 'seed', 'pre-seed', 'fundrais', 'series a', 'b2b'],
            'enterprise_modernization': ['enterprise', 'legacy', 'moderniz', 'staffing', 'large company'],
        }
        
        best_match = None
        best_score = 0
        for cs_key, keywords in keyword_map.items():
            score = sum(1 for kw in keywords if kw in context_text)
            if score > best_score:
                best_score = score
                best_match = cs_key
        
        if best_match and best_score >= 1:
            result = self.case_studies[best_match].copy()
            result['selected_by'] = f'keyword_match ({best_match}, score={best_score})'
            print(f"   📎 Case study: {best_match} (keyword match, score={best_score})")
            return result
        
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
            "vp engineering", "vp of engineering", "head of engineering", "vp product",
            "vp of product", "head of product", "cpo", "chief product",
            "engineering director", "director of engineering", "director engineering"
        ]
        
        technical_titles = [
            "cto", "chief technology", "vp engineering", "vp of engineering",
            "head of engineering", "engineering director", "director of engineering",
            "software director", "technical director"
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
        # NO dashes, NO single words, NO formal language
        # Must look like it came from a coworker or friend
        subject_templates = [
            "random thought",
            "quick question",
            "quick idea",
            "wild idea",
            "quick q",
            "thought of this",
            "random q",
            "hey quick q",
            "had a thought",
            "one more thing",
        ]
        suggested_subject = random.choice(subject_templates)
        
        # CURIOSITY-FIRST OPENERS - LeadGenJay: First line = PREVIEW TEXT
        # RULE: Must sound like a FRIEND texting. NO company name. NO pitch hint.
        # They see this BEFORE opening. If it smells like a pitch, they delete.
        # NO EM DASHES, NO placeholders, NO company observations.
        curiosity_openers = [
            "had a random thought.",
            "quick one.",
            "this might be out of left field.",
            "weird timing but had a thought.",
            f"hey {first_name.lower()}, random one for you.",
            "been meaning to ask you something.",
            "random one.",
            "quick q.",
        ]
        suggested_opener = random.choice(curiosity_openers)
        
        # VARIED CTAs - LeadGenJay: ONE soft CTA, but vary them
        # NO "sound familiar?" - overused AI pattern
        cta_options = [
            "worth a quick chat?",
            "ring any bells?",
            "crazy or worth exploring?",
            "am I off base here?",
            "make any sense?",
            "worth 15 mins?",
            "curious if this resonates.",
            "thoughts?",
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
        
        system_prompt = f"""You write cold emails using LeadGenJay's exact 4-line framework.

THE 4 LINES (each separated by a blank line):

Line 1 = PREVIEW TEXT (1 short sentence, 5-10 words):
This is what they see BEFORE opening. Must sound like a friend texting.
NO company names. NO pitch hints. NO "I noticed" or "I saw".
Just casual curiosity like: "had a random thought." or "quick one."

Line 2 = POKE THE BEAR (2-3 sentences, 25-35 words):
Now mention "{company}" by name. Ask a QUESTION about a specific pain they face.
Follow up with one more sentence expanding on the pain.
This is where you show you understand their world.

Line 3 = CASE STUDY (1-2 sentences, 15-20 words):
Share a relevant result with REAL numbers. Use the exact case study provided.
Don't change the company type or industry. Keep it factual.

Line 4 = SOFT CTA + SIGN-OFF (2 lines):
One casual question as CTA. Then "abdul" on the next line.

RULES:
- Subject: 2-3 lowercase words, no dashes, no punctuation
- Body: 45-70 words total. If under 45, add more detail to Line 2.
- CRITICAL: Separate each section with a BLANK LINE (empty line between sections)
- Line 1 must NOT mention "{company}" or any company. Pure curiosity only.
- Line 2 MUST mention "{company}" by name, spelled exactly.
- NO em dashes. Use commas or periods.
- NO jargon: streamline, leverage, optimize, solutions, empower, innovative
- NO stalker phrases: "I noticed", "I saw", "I was looking at", "came across"
- Contractions always: don't, can't, won't, we've
- 6th grade reading level, all lowercase
- Case study: use EXACTLY as provided, don't fabricate or change industry
{improvement_prompt if improvement_prompt else ""}

Return JSON: {{"subject": "2-3 word subject", "body": "line1\\n\\nline2\\n\\nline3\\n\\nCTA\\nabdul"}}"""

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
        
        # Pick a varied pain point question based on title
        # Each includes a follow-up sentence to hit 50+ word target
        pain_questions = {
            'CTO': [
                f"is {company}'s dev team spending more time on maintenance than new features right now? seems to be the pattern with a lot of {their_space or industry or 'tech'} companies scaling up.",
                f"curious if {company} is tackling the build-vs-buy decision on infrastructure. it's a tough call when you're moving fast.",
                f"is {company}'s engineering team stuck putting out fires instead of shipping new stuff? been seeing that a lot lately.",
            ],
            'VP Engineering': [
                f"is {company}'s team hitting a wall trying to ship faster without adding headcount? seems to be the story everywhere right now.",
                f"curious how {company} is handling tech debt vs feature deadlines. it's usually a pick-one situation that nobody likes.",
                f"is {company}'s roadmap getting squeezed because the team's stretched? i keep hearing that from engineering leads in {their_space or industry or 'tech'}.",
            ],
            'CEO': [
                f"is {company} at that stage where the tech side can't keep pace with the business? i see that a lot with {their_space or industry or 'tech'} companies growing fast.",
                f"curious if {company} is feeling the drag from manual processes. it's one of those things that sneaks up when you're focused on growth.",
                f"is {company} at that ceiling where you need to ship faster but can't hire fast enough? seems to be the number one thing for {their_space or industry or 'tech'} companies right now.",
            ],
            'Founder': [
                f"is {company} at the crossroads of fixing old stuff vs building new things? that's usually where founders in {their_space or industry or 'tech'} land.",
                f"curious if {company} is dealing with the founder dilemma of speed vs quality. it never gets easier, especially at your stage.",
                f"is {company}'s team buried in tech debt while trying to ship the next big thing? seems to be the pattern with fast-growing companies in your space.",
            ],
        }
        # Get role-specific questions or default
        title_key = title.split('&')[0].strip() if '&' in title else title
        role_questions = pain_questions.get(title_key, pain_questions.get('CEO', []))
        selected_pain_question = random.choice(role_questions)
        
        # Build the case study sentence with varied result phrasing
        cs_result = case_study.get('result_short', case_study.get('result', ''))
        cs_timeline = case_study.get('timeline', '')
        cs_variations = case_study.get('result_variations', [])
        cs_result_text = random.choice(cs_variations) if cs_variations else f"achieve {cs_result}"
        
        # Avoid duplicating timeline if the variation already includes a time reference
        # Check for both exact timeline match AND general time phrases (weeks, months, days)
        import re
        has_time_ref = bool(re.search(r'\b\d+\s*(weeks?|months?|days?)\b', cs_result_text, re.IGNORECASE))
        has_exact_timeline = cs_timeline.lower() in cs_result_text.lower()
        
        if has_time_ref or has_exact_timeline:
            case_study_sentence = f"we helped {case_study_reference} {cs_result_text}."
        else:
            case_study_sentence = f"we helped {case_study_reference} {cs_result_text} in {cs_timeline}."
        
        # Pre-build a draft email following LeadGenJay's exact 4-line framework
        # Line 1 = preview text (NO company name)
        # Line 2 = poke the bear (company + pain question)
        # Line 3 = case study
        # Line 4 = CTA + sign-off
        draft_email = f"""hey {first_name.lower()}, {suggested_opener}

{selected_pain_question}

{case_study_sentence}

{suggested_cta}
abdul"""
        
        user_prompt = f"""Rewrite this draft cold email to flow naturally. Keep ALL content, just make it conversational.

DRAFT:
{draft_email}

KEEP THESE 4 SECTIONS (each on its own line, separated by BLANK LINES):
1. PREVIEW TEXT: "hey {first_name.lower()}, {suggested_opener}" - keep this SHORT. Do NOT add company name here.
2. PAIN QUESTION: Must mention "{company}" and ask about their pain. Keep the follow-up sentence.
3. CASE STUDY: "{case_study_sentence}" - use this word for word.
4. CTA + sign-off: "{suggested_cta}" then "abdul" on next line.

RULES:
- Do NOT mention "{company}" in the first line. First line is preview text only.
- Spell "{company}" EXACTLY as shown. Do not change its spelling.
- SEPARATE each section with a blank line (\\n\\n between them)
- Do NOT merge sections onto the same line
- Total 45-70 words
- All lowercase, casual
- No em dashes
- Do NOT repeat any line. Each line must be unique.

Return JSON: {{"subject": "{suggested_subject}", "body": "line1\\n\\nline2\\n\\nline3\\n\\ncta\\nabdul"}}."""

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
            
            # FIX: Correct company name misspellings by Qwen
            # Qwen sometimes drops letters or misspells the company name
            if company:
                body_lower_check = body.lower()
                company_lower_check = company.lower()
                if company_lower_check not in body_lower_check:
                    # Try to find a close misspelling and replace it
                    import difflib
                    words_in_body = body.split()
                    for idx, word in enumerate(words_in_body):
                        # Strip punctuation for comparison
                        clean_word = word.strip(".,!?'\"():;")
                        # Check if this word is a close match to company name (or part of it)
                        similarity = difflib.SequenceMatcher(None, clean_word.lower(), company_lower_check).ratio()
                        if similarity >= 0.65 and len(clean_word) >= 3:
                            # Preserve original casing/punctuation
                            prefix = word[:len(word) - len(word.lstrip(".,!?'\"():;"))] if word != word.lstrip(".,!?'\"():;") else ""
                            suffix = word[len(word.rstrip(".,!?'\"():;"))] if word != word.rstrip(".,!?'\"():;") else ""
                            # Check if it had possessive 's
                            if clean_word.lower().endswith("'s") or clean_word.lower().endswith("'s"):
                                replacement = company.lower() + "'s"
                            else:
                                replacement = company.lower()
                            trailing = word[len(clean_word):]
                            words_in_body[idx] = replacement + trailing
                            body = ' '.join(words_in_body)
                            print(f"   🔧 Fixed company misspelling: '{clean_word}' → '{replacement}'")
                            break
            
            # FIX: Deduplicate repeated lines in body
            # Qwen sometimes repeats the CTA or other lines
            lines = body.split('\n')
            seen_lines = set()
            deduped_lines = []
            for line in lines:
                stripped = line.strip().lower()
                if stripped == '' or stripped not in seen_lines:
                    deduped_lines.append(line)
                    if stripped:
                        seen_lines.add(stripped)
                else:
                    print(f"   🔧 Removed duplicate line: '{line.strip()}'")
            body = '\n'.join(deduped_lines)
            
            # FIX: Ensure paragraph breaks between sections
            # LeadGenJay emails have 4 distinct sections separated by blank lines
            # If Qwen merged them into one paragraph, re-split
            non_empty_lines = [l for l in body.split('\n') if l.strip()]
            blank_line_count = body.count('\n\n')
            if blank_line_count < 2 and len(non_empty_lines) >= 3:
                # Try to split at sentence boundaries that look like section breaks
                # Detect case study line (contains 'we helped' or 'helped a')
                # Detect CTA line (short line at end like 'worth a chat?' 'thoughts?')
                reconstructed = []
                for j, line in enumerate(non_empty_lines):
                    line_lower = line.strip().lower()
                    if j > 0 and ('we helped' in line_lower or 'helped a' in line_lower):
                        reconstructed.append('')  # blank line before case study
                    elif j > 0 and j == len(non_empty_lines) - 1 and len(line.split()) <= 8:
                        reconstructed.append('')  # blank line before CTA
                    elif j > 0 and any(cta in line_lower for cta in ['worth', 'thoughts?', 'ring any', 'crazy or', 'am i off', 'make any sense', 'curious if this', 'abdul']):
                        if not reconstructed or reconstructed[-1] != '':
                            reconstructed.append('')  # blank line before CTA/signoff
                    reconstructed.append(line)
                body = '\n'.join(reconstructed)
                print(f"   🔧 Added paragraph breaks between sections")
            
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
            
            # Check for single-word subjects (need 2-4 words)
            subject_is_short = subject_words < 2
            
            # Check for dashes in subject (looks like em dash)
            subject_has_dash = '-' in subject or '—' in subject
            
            # Also check for subject being just "Name?"
            subject_is_weak = subject.strip().lower() in [
                f"{first_name.lower()}?", 
                f"{first_name.lower()} ?",
                first_name.lower(),
            ] or subject_is_short or subject_has_dash
            
            if subject_is_formal or subject_is_weak:
                print(f"   ⚠️ Subject '{subject}' is too formal/weak, using: {suggested_subject}")
                subject = suggested_subject
            
            if starts_bad:
                print(f"   ⚠️ Email starts with stalker pattern, using fallback...")
                return self._fallback_email(lead, campaign_context, research, case_study, suggested_cta)
            
            # STRIP em dashes before validation (replace with comma instead of rejecting)
            if '—' in body:
                body = body.replace('—', ',')
                print(f"   🔧 Replaced em dashes with commas")
            if '—' in subject:
                subject = subject.replace('—', ',')
            
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
        
        # CRITICAL: Check for em dash - the #1 AI writing tell
        if '—' in body:
            print(f"   ❌ EMAIL REJECTED: Contains em dash (—) - AI tell!")
            raise ValueError("Email contains em dash (—) - banned per LeadGenJay rules")
        
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
            # NEW: Lazy generic phrases from LeadGenJay
            "sound familiar?",         # Overused AI pattern
            "you're probably",         # Generic assumption
            "most teams struggle",     # Templated garbage
            "you're likely",           # Another assumption
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
        # NO company name in opener. Must sound like a friend.
        company_openers = [
            f"quick one for you.",
            f"random q.",
            f"had a random thought.",
            f"this might be off base but...",
            f"quick thought on something.",
        ]
        
        # Use AI-generated pain point if available, otherwise use contextual fallbacks
        # LeadGenJay: Poke the bear — MUST mention company name in this section
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
                    pains = [f"is {company}'s team spending too long on HIPAA stuff while features pile up?"]
                elif 'fintech' in industry.lower() or 'finance' in industry.lower():
                    pains = [f"is compliance at {company} blocking releases while competitors ship weekly?"]
                elif 'construction' in industry.lower():
                    pains = [f"is {company}'s team juggling site coordination and product at the same time?"]
                else:
                    pains = [f"is {company} shipping features while fundraising? usually something drops."]
            else:
                if not pain.endswith('.'):
                    pain = pain + '.'
                pains = [f"curious if {company} is dealing with this: {pain}"]
        # LEADGENJAY STYLE: Poke the bear with a QUESTION mentioning the company
        elif 'health' in industry.lower() or 'medical' in industry.lower():
            pains = [
                f"is {company} still doing manual HIPAA audits or did you automate that?",
                f"how's {company}'s team handling compliance while also shipping fast?",
                f"curious if compliance reviews at {company} still take weeks.",
            ]
        elif 'fintech' in industry.lower() or 'finance' in industry.lower():
            pains = [
                f"how's {company} handling SOC2 stuff while also building product?",
                f"are compliance audits at {company} still eating into feature time?",
                f"curious if PCI compliance is slowing down {company}'s releases too.",
            ]
        elif 'construction' in industry.lower() or 'infrastructure' in industry.lower():
            pains = [
                f"how's {company}'s team syncing data across job sites right now?",
                f"are site inspections still bottlenecking {company}'s project timelines?",
                f"curious how {company} is handling field data while also building product.",
            ]
        elif 'cto' in title.lower() or 'engineer' in title.lower() or 'technical' in title.lower():
            pains = [
                f"is {company}'s best talent stuck maintaining legacy stuff or actually building?",
                f"how's {company} balancing tech debt vs new features these days?",
                f"curious if {company} is still fighting fires or finally ahead of them.",
            ]
        else:
            pains = [
                f"how's {company} handling dev capacity while also fundraising?",
                f"is hiring senior devs at {company} taking forever too?",
                f"curious how {company} is keeping velocity up with a lean team.",
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
        
        # Use provided CTA or pick one - NO "sound familiar?" (banned as AI pattern)
        ctas = cta or random.choice([
            "worth a quick chat?",
            "ring any bells?",
            "crazy or worth exploring?",
            "any of this hit home?",
            "make sense for you?",
            "thoughts?",
        ])
        
        subject = random.choice(subjects)
        opener = random.choice(company_openers)
        pain = random.choice(pains)
        case_study_line = random.choice(case_study_lines)
        
        # Build email following LeadGenJay structure with proper newlines
        body = f"""hey {first_name.lower()}, {opener}

{pain}

{case_study_line}

{ctas}
abdul"""

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
        Follow-up #1 (Email 2 of 3): Same thread, ADD GENUINE VALUE
        
        LeadGenJay: "Don't say 'just following up'. Add something useful."
        "Email 2 is in the same thread as Email 1"
        
        Uses Ollama/Qwen (free, local) — completely separate from initial email system.
        Falls back to template if Ollama is unavailable.
        """
        first_name = lead.get('first_name') or 'there'
        company = lead.get('company') or ''
        title = lead.get('title') or ''
        industry = lead.get('industry') or ''
        original_subject = previous[0]['subject'] if previous else "previous"
        original_body = previous[0].get('body', '') if previous else ""
        
        # Select a DIFFERENT case study than initial email
        from primestrides_context import CASE_STUDIES
        cs_key = self._pick_followup_case_study(lead, original_body)
        case_study = CASE_STUDIES.get(cs_key, CASE_STUDIES['enterprise_modernization'])
        
        cs_result_text = random.choice(case_study.get('result_variations', [f"achieve {case_study.get('result_short', '')}"])) 
        cs_reference = case_study.get('company_hint', case_study.get('company_name', 'a tech company'))
        cs_timeline = case_study.get('timeline', '')
        
        import re
        has_time_ref = bool(re.search(r'\b\d+\s*(weeks?|months?|days?)\b', cs_result_text, re.IGNORECASE))
        if has_time_ref:
            cs_result_sentence = f"{cs_result_text}"
        else:
            cs_result_sentence = f"{cs_result_text} in {cs_timeline}"
        
        company_possessive = f"{company}'" if company.endswith('s') else f"{company}'s"
        
        # Build a draft for Qwen to rewrite
        openers = [
            "forgot to mention this",
            "one more thing",
            "actually, thought of something",
            "this might be more relevant",
            "fwiw",
            "quick aside",
            "meant to add this",
        ]
        selected_opener = random.choice(openers)
        
        followup_ctas = [
            "want me to send it over?",
            "happy to share if it's useful.",
            "want the doc?",
            "worth a look?",
            "want me to forward it?",
        ]
        selected_cta = random.choice(followup_ctas)
        
        draft_body = f"""{selected_opener} - we helped {cs_reference} {cs_result_sentence}. documented the whole process, might be relevant for {company}.

{selected_cta}"""
        
        system_prompt = f"""You rewrite follow-up emails in LeadGenJay's style.

CONTEXT:
- You are emailing {first_name} who works at "{company}" (THE LEAD'S COMPANY)
- The case study company is "{cs_reference}" (A DIFFERENT COMPANY we helped before)
- NEVER confuse these two. "{company}" is who you're emailing. "{cs_reference}" is the past client.

RULES:
- This is email #2 in the same thread. Subject stays "Re: [original]".
- UNDER 40 words. Shorter than the first email.
- PURPOSE: explain in more depth HOW we made the case study result possible. Don't just name-drop the result, explain the approach or what we did.
- NEVER say "just following up", "circling back", "bumping this", "checking in", "wanted to follow up", "remember"
- Sound like a casual friend who remembered something useful
- ALL lowercase except proper nouns like "{company}" and "{cs_reference}"
- No exclamation marks (!). Keep it chill.
- End with a soft CTA question
- Spell "{company}" exactly as shown (case-sensitive)
- No em dashes. Use commas or periods.
- No signatures, no sign-offs, no greetings like "hi" or "hey"

Return JSON: {{"body": "the rewritten follow-up body"}}"""

        user_prompt = f"""Rewrite this follow-up draft. The goal is to explain HOW we achieved the result for our past client, not just what the result was.

DRAFT:
{draft_body}

Lead's company: {company} (you're emailing them)
Case study client: {cs_reference} (our past client, different company)
Case study result: {cs_result_sentence}
Lead: {first_name} ({title} at {company}, {industry})

Explain the approach briefly (e.g. "we did X which led to Y"). Under 40 words. Keep the CTA.

Return JSON: {{"body": "..."}}"""
        
        try:
            content = self._call_ollama_for_followup(system_prompt, user_prompt, temperature=0.85)
            result = json.loads(content)
            body = result.get("body") or ""
            
            if not body.strip() or len(body.split()) < 8:
                raise ValueError("Body too short or empty")
            
            # Post-processing (same quality checks as initial emails)
            body = humanize_email(body)
            
            # Fix company misspelling
            if company and company.lower() not in body.lower():
                import difflib
                words = body.split()
                for idx, word in enumerate(words):
                    clean = word.strip(".,!?'\"():;")
                    sim = difflib.SequenceMatcher(None, clean.lower(), company.lower()).ratio()
                    if sim >= 0.7 and len(clean) >= 3:
                        body = body.replace(clean, company)
                        break
            
            # Remove em dashes
            body = body.replace('—', ',')
            body = body.replace('–', ',')
            
            return {
                "subject": f"Re: {original_subject}",
                "body": body
            }
            
        except Exception as e:
            print(f"   ⚠️ Ollama follow-up failed ({e}), using template fallback")
            body = f"""{selected_opener} - we helped {cs_reference} {cs_result_sentence}. documented the whole process, might be relevant for {company}.

{selected_cta}"""
            body = humanize_email(body)
            return {
                "subject": f"Re: {original_subject}",
                "body": body
            }
    
    def _pick_followup_case_study(self, lead: Dict, original_body: str) -> str:
        """Pick a case study for follow-up, trying to avoid repeating the one from initial email."""
        from primestrides_context import CASE_STUDIES
        
        industry = (lead.get('industry') or '').lower()
        title = (lead.get('title') or '').lower()
        original_lower = original_body.lower()
        
        # All main case study keys (not aliases)
        all_keys = ['hr_tech_ai', 'saas_mvp', 'enterprise_modernization', 'fintech_client', 'healthtech_client', 'construction_tech']
        
        # Figure out which case study was used in the initial email by checking body text
        used_key = None
        for key in all_keys:
            cs = CASE_STUDIES[key]
            # Check if the case study's company_name or hint appears in the original body
            if cs.get('company_name', '').lower() in original_lower or cs.get('company_hint', '').lower() in original_lower:
                used_key = key
                break
            # Also check result text
            if cs.get('result_short', '').lower() in original_lower:
                used_key = key
                break
        
        # Available keys (excluding the one already used)
        available = [k for k in all_keys if k != used_key]
        
        # Try to match by industry keywords
        industry_keywords = {
            'hr_tech_ai': ['hr', 'human resources', 'recruiting', 'hiring', 'talent', 'ai', 'automation', 'machine learning'],
            'saas_mvp': ['saas', 'startup', 'mvp', 'b2b', 'software', 'platform'],
            'enterprise_modernization': ['enterprise', 'legacy', 'staffing', 'modernization', 'large'],
            'fintech_client': ['fintech', 'finance', 'banking', 'payments', 'financial', 'insurance'],
            'healthtech_client': ['health', 'medical', 'hipaa', 'healthcare', 'pharma', 'biotech'],
            'construction_tech': ['construction', 'field', 'logistics', 'operations', 'infrastructure', 'manufacturing'],
        }
        
        # Score each available case study
        best_key = None
        best_score = -1
        for key in available:
            score = 0
            keywords = industry_keywords.get(key, [])
            for kw in keywords:
                if kw in industry or kw in title:
                    score += 1
            if score > best_score:
                best_score = score
                best_key = key
        
        # If no good match, pick randomly from available
        if best_score == 0:
            return random.choice(available) if available else 'enterprise_modernization'
        
        return best_key
    
    def _generate_followup_new_thread(self, lead: Dict, context: Dict, previous: List) -> Dict:
        """
        Follow-up #2 (Email 3 of 3): NEW thread, completely different angle
        
        LeadGenJay: "Email 3 should be a fresh start with different subject and angle"
        "Give away something valuable for free - the front-end offer"
        
        Uses Ollama/Qwen (free, local) — completely separate from initial email system.
        Falls back to template if Ollama is unavailable.
        """
        first_name = lead.get('first_name') or 'there'
        company = lead.get('company') or ''
        title = lead.get('title') or ''
        industry = lead.get('industry') or ''
        
        # Get front-end offer from campaign context, or build one from role
        front_end_offer = context.get('front_end_offer') or ''
        if not front_end_offer:
            title_upper = (title or '').upper()
            if 'CTO' in title_upper or 'ENG' in title_upper:
                front_end_offer = 'free technical roadmap session'
            elif 'PRODUCT' in title_upper or 'CPO' in title_upper:
                front_end_offer = 'free roadmap acceleration session'
            elif 'AI' in title_upper or 'ML' in title_upper:
                front_end_offer = 'free AI architecture review'
            else:
                front_end_offer = 'free 30-min architecture review'
        
        previous_subjects = [e.get('subject', '') for e in previous]
        
        # Pick a new subject (varied, never reusing previous)
        new_subjects = [
            "different thought",
            "random idea", 
            "separate thought",
            "quick idea",
            "different angle",
            "unrelated thought",
        ]
        available_subjects = [s for s in new_subjects if s not in previous_subjects]
        new_subject = random.choice(available_subjects) if available_subjects else random.choice(new_subjects)
        
        company_possessive = f"{company}'" if company.endswith('s') else f"{company}'s"
        
        # Build draft for Qwen to rewrite — role-specific pain reframe
        title_upper = (title or '').upper()
        if 'CTO' in title_upper or 'CHIEF TECH' in title_upper:
            pain_angle = f"we built a doc on how {industry or 'tech'} teams at {company_possessive} stage avoid the hire-vs-outsource trap"
        elif 'VP' in title_upper and 'ENG' in title_upper:
            pain_angle = f"we put together a breakdown of how teams like {company_possessive} unblock their roadmap without adding headcount"
        elif 'FOUNDER' in title_upper or 'CO-FOUNDER' in title_upper:
            pain_angle = f"we documented how founders in {industry or 'tech'} ship their product backlog 3x faster"
        elif 'PRODUCT' in title_upper or 'CPO' in title_upper:
            pain_angle = f"we wrote up how product teams at {company_possessive} stage unblock engineering without the politics"
        else:
            pain_angle = f"we put together a doc on how {industry or 'tech'} companies at {company_possessive} stage fix the engineering bottleneck"
        
        draft_body = f"""hey {first_name.lower()}, {pain_angle}. based on real numbers from companies we've worked with.

want me to send it over?"""
        
        system_prompt = f"""You rewrite cold emails in LeadGenJay's style.

CONTEXT:
- This is email #3 in the sequence. COMPLETELY NEW thread. They ignored emails 1 and 2.
- The angle: offer a FREE resource/lead magnet (not a meeting). Lower the friction.
- LeadGenJay says: "they've already ignored you. your CTA was too much of an ask. offer more value and give them something in return."

RULES:
- Start naturally, like texting a colleague. Use "hey {first_name.lower()}," or just jump in.
- Do NOT use the "name -" or "name —" format. No dashes after the name.
- UNDER 40 words total
- OFFER A RESOURCE, DOC, OR BREAKDOWN. Not a meeting or call.
- Frame it as something we already built for companies LIKE theirs (not specifically for them). Use "teams like yours" or "companies at your stage", NOT "{company}'s roadmap".
- Explain WHY it's relevant to their specific role as {title}
- ALL lowercase except proper nouns like "{company}"
- No exclamation marks. Keep it chill.
- End with a low-friction CTA like "want me to send it over?" or "want the doc?"
- Spell "{company}" exactly as shown (case-sensitive)
- No em dashes. Use commas or periods.
- No signatures, no sign-offs
- Don't mention previous emails

Return JSON: {{"body": "the rewritten email body"}}"""

        user_prompt = f"""Rewrite this email offering a free resource. Frame it as something we already have, not something we'd create.

DRAFT:
{draft_body}

Lead: {first_name} ({title} at {company}, {industry})
Their role: {title}
Front-end offer: {front_end_offer}

Make it role-specific to a {title}. Lower the CTA friction, just offer to send the doc. Under 40 words.

Return JSON: {{"body": "..."}}"""
        
        try:
            content = self._call_ollama_for_followup(system_prompt, user_prompt, temperature=0.85)
            result = json.loads(content)
            body = result.get("body") or ""
            
            if not body.strip() or len(body.split()) < 10:
                raise ValueError("Body too short or empty")
            
            # Strip any name-dash format Qwen might still produce
            body_lower_first = first_name.lower()
            if body.strip().startswith(f"{body_lower_first} -") or body.strip().startswith(f"{body_lower_first} –"):
                body = body.strip()
                body = body[len(body_lower_first):].lstrip(' -–').strip()
                body = f"hey {body_lower_first}, {body}"
            
            # Post-processing
            body = humanize_email(body)
            
            # Fix company misspelling
            if company and company.lower() not in body.lower():
                import difflib
                words = body.split()
                for idx, word in enumerate(words):
                    clean = word.strip(".,!?'\"():;")
                    sim = difflib.SequenceMatcher(None, clean.lower(), company.lower()).ratio()
                    if sim >= 0.7 and len(clean) >= 3:
                        body = body.replace(clean, company)
                        break
            
            # Remove em dashes
            body = body.replace('—', ',')
            body = body.replace('–', ',')
            
            return {
                "subject": new_subject,
                "body": body,
                "new_thread": True
            }
            
        except Exception as e:
            print(f"   ⚠️ Ollama new-thread follow-up failed ({e}), using template fallback")
            body = f"""hey {first_name.lower()}, {pain_angle}. based on real numbers from companies we've worked with.

want me to send it over?"""
            body = humanize_email(body)
            return {
                "subject": new_subject,
                "body": body,
                "new_thread": True
            }
    
    def _generate_breakup_email(self, lead: Dict, context: Dict, previous: List) -> Dict:
        """
        Final email (if needed beyond 3) - helpful redirect, not guilt trip
        
        LeadGenJay: "Should I reach out to someone else?" is incredibly effective
        because it triggers reciprocity.
        
        Uses Ollama/Qwen (free, local) for variety.
        Falls back to template if Ollama is unavailable.
        """
        first_name = lead.get('first_name') or 'there'
        company = lead.get('company') or ''
        title = lead.get('title') or ''
        
        subjects = ["closing the loop", "last note", "quick check"]
        subject = random.choice(subjects)
        
        # Figure out a plausible alternate role to redirect to (Eric's technique)
        title_upper = (title or '').upper()
        if 'CEO' in title_upper or 'FOUNDER' in title_upper:
            alt_role = "your CTO or VP of Engineering"
        elif 'CTO' in title_upper:
            alt_role = "your VP of Engineering or a team lead"
        elif 'VP' in title_upper:
            alt_role = "your CTO or another engineering lead"
        elif 'PRODUCT' in title_upper or 'CPO' in title_upper:
            alt_role = "your CTO or engineering lead"
        else:
            alt_role = "someone else on the engineering side"
        
        # Draft template for Qwen to rewrite — Eric's technique: suggest a specific alternate role
        draft_body = f"""hey {first_name.lower()}, maybe engineering bandwidth isn't your call at {company}. should i reach out to {alt_role} instead, or should i close this out?"""
        
        system_prompt = f"""You rewrite breakup emails in LeadGenJay's style.

CONTEXT:
- Eric Nowoslawski's breakup template: "Fred, I know there's about 20 employees at Otter PR and perhaps SDR is not your responsibility. Should I reach out to Scott instead given their role?"
- The key insight: suggest reaching out to a SPECIFIC ROLE, not just "someone else"

RULES:
- This is the FINAL email. Be graceful, not desperate.
- Start naturally, like texting a colleague. Use "hey {first_name.lower()}," or just jump in.
- Do NOT use the "name -" or "name —" format. No dashes after the name.
- UNDER 30 words
- MUST end with a question suggesting you reach out to a specific role: "{alt_role}"
- The redirect-to-someone-else angle triggers reciprocity
- ALL lowercase except proper nouns like "{company}"
- Spell "{company}" exactly as shown (case-sensitive). Every letter must match.
- NOT guilt-trippy, NOT passive-aggressive, NOT whiny
- No exclamation marks. No em dashes. Use commas or periods.
- No signatures, no sign-offs

Return JSON: {{"body": "the breakup email body"}}"""

        user_prompt = f"""Rewrite this breakup email. Keep the redirect-to-alternate-role angle.

DRAFT:
{draft_body}

Lead: {first_name} ({title} at {company})
Alternate role to suggest: {alt_role}

Spell "{company}" exactly like that (case-sensitive). Under 30 words.

Return JSON: {{"body": "..."}}"""
        
        try:
            content = self._call_ollama_for_followup(system_prompt, user_prompt, temperature=0.9)
            result = json.loads(content)
            body = result.get("body") or ""
            
            if not body.strip() or len(body.split()) < 8:
                raise ValueError("Body too short or empty")
            
            # Strip any name-dash format Qwen might still produce
            body_lower_first = first_name.lower()
            if body.strip().startswith(f"{body_lower_first} -") or body.strip().startswith(f"{body_lower_first} –"):
                body = body.strip()
                body = body[len(body_lower_first):].lstrip(' -–').strip()
                body = f"hey {body_lower_first}, {body}"
            
            body = body.replace('—', ',')
            body = body.replace('–', ',')
            
            return {
                "subject": subject,
                "body": body,
                "new_thread": True
            }
            
        except Exception as e:
            print(f"   ⚠️ Ollama breakup email failed ({e}), using template fallback")
            templates = [
                f"""hey {first_name.lower()}, maybe engineering bandwidth isn't your call at {company}. should i reach out to {alt_role} instead, or close this out?""",
                
                f"""hey {first_name.lower()}, not trying to be a pest. if the timing's off, totally get it. should i check back in a few months, or talk to {alt_role} at {company}?""",
                
                f"""hey {first_name.lower()}, totally understand if this isn't a priority at {company} right now. would it make more sense to connect with {alt_role}?""",
            ]
            return {
                "subject": subject,
                "body": random.choice(templates),
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
