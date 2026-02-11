"""
Email Reviewer Service - Self-Improving AI Quality Gate

Critically reviews generated emails against LeadGenJay / Eric Nowoslawski guidelines
from the 90-page cold email masterclass and 4-hour $15M masterclass.

SELF-IMPROVEMENT FEATURES:
- Stores ALL reviews in MongoDB (passed and failed)
- Learns from past failures to improve generation prompts
- Tracks common issues over time for targeted improvements

Key guidelines enforced:
1. First line = PREVIEW TEXT (must sound like friend/colleague, NOT "why you're reaching out")
2. Under 75 words total (50-60 ideal)
3. 6th grade reading level - no corporate jargon
4. ONE pain point, ONE CTA
5. Specific numbers (3.72x not "4x")
6. Subject line: 2-4 words, looks like colleague sent it
7. Case study must be RELEVANT to recipient's industry
8. NO banned phrases that scream "cold email"
"""

from email_generator import humanize_email, get_llm_client, get_rate_limiter, GROQ_FALLBACK_CHAIN, GROQ_MODEL_LIMITS  # Import humanize function, LLM client, and rotation
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
import json
import re
import logging
import config
from database import db, email_reviews_collection

# Module logger
logger = logging.getLogger(__name__)


class ReviewStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"


@dataclass
class ReviewResult:
    """Result of email review"""
    status: ReviewStatus
    score: int  # 0-100
    issues: List[Dict[str, Any]]
    suggestions: List[str]
    rewrite_required: bool
    ai_feedback: str
    rule_violations: List[str]


# =============================================================================
# GUIDELINES EXTRACTED FROM DOCS (LeadGenJay + Eric Nowoslawski)
# =============================================================================

COLD_EMAIL_GUIDELINES = """
# COLD EMAIL REVIEW GUIDELINES
Based on Eric Nowoslawski's 90-page doc + LeadGenJay's $15M Masterclass

## CRITICAL RULES (Instant Fail if Violated)

### 1. FIRST LINE (Preview Text)
- Must sound like it could be from a friend or colleague
- NEVER start with "I noticed", "I saw that", "I came across", "I'm reaching out"
- Goal: Get them to OPEN the email before they know it's a pitch
- Good: "[Company]'s new [specific thing] looks sick."
- Bad: "I noticed your company is hiring..."

### 2. WORD COUNT
- Maximum: 75 words (hard cap)
- Ideal: 50-60 words
- Shorter = better
- If over 75, email FAILS

### 3. READING LEVEL
- 6th grade reading level
- No corporate jargon: leverage, synergy, streamline, optimize, innovative, comprehensive, incentivize
- Simple words only
- If it sounds "professional" or "corporate", it's wrong

### 4. STRUCTURE (4 lines max)
- Line 1: Preview bait (specific observation about company)
- Line 2: Poke the bear (one sentence about their pain)
- Line 3: Case study with SPECIFIC numbers (3.2x not "3x", 43% not "~40%")
- Line 4: Soft CTA only ("interested?", "make sense?", "thoughts?")

### 5. SUBJECT LINE
- 2-4 words maximum
- Must look like colleague sent it
- Good: "mike?", "thought", "quick q", "hey", "idea"
- Bad: "Partnership Opportunity", "Quick Question for You", "Intro"

### 6. CALL TO ACTION
- ONE soft CTA only
- Never: "schedule a call", "book a meeting", "let's set up time"
- Always: "interested?", "make sense?", "thoughts?", "worth exploring?"
- Multiple CTAs = desperate = FAIL

### 7. CASE STUDY
- Must include SPECIFIC numbers (3.72x, 43%, 8 weeks)
- Should be RELEVANT to recipient's industry
- "a similar company" is fine, but industry match is better
- Never round numbers - specifics build trust

### 8. BANNED PHRASES (Instant Fail)
- "I hope this finds you well"
- "I'm reaching out because..."
- "I noticed that..."
- "I saw that..."
- "I came across..."
- "Just wanted to touch base"
- "Circling back"
- "Following up"
- "Quick question—" as opener
- "How are you handling/managing/navigating X?"
- "I'd love to..."
- "I wanted to..."
- "My name is..."
- "Partnership opportunity"
- Any corporate jargon

### 9. TONE
- Casual, like texting a friend
- Direct, not salesy
- Confident, not desperate
- Helpful, not pushy
- If it sounds like a sales email, it's wrong

### 10. SPECIFICITY (LeadGenJay: "specify WHAT you saw")
- Never say "saw something interesting" - say WHAT you saw
- Never say "your company is doing great things" - say WHAT things
- Generic observations = spam folder

### 11. SOUND HUMAN, NOT AI (CRITICAL)
- NO em dashes (—) - this is the #1 AI tell. Use commas or periods instead.
- NO fancy transitions: "furthermore", "moreover", "additionally", "importantly"
- NO AI words: "delve", "leverage", "utilize", "foster", "robust", "seamless"
- Use contractions: "don't" not "do not", "can't" not "cannot"
- Be choppy, not smooth. Real humans don't write perfectly.
- Start some sentences with "And" or "But" - AI rarely does this
- Use simple punctuation: periods, commas, question marks. That's it.
- Vary sentence length randomly. AI writes uniform sentences.
- Make small imperfections. Perfect = robotic.
- Write like you're texting, not writing an essay.
"""

BANNED_PHRASES = [
    # Robotic openers
    "i hope this finds you well",
    "i hope this email finds you",
    "i'm reaching out",
    "i am reaching out",
    "reaching out to you",
    "i noticed that",
    "i noticed your",
    "i noticed you",
    "i saw that",
    "i saw your",
    "i came across",
    "came across your",
    "just wanted to",
    "i wanted to",
    "i'd love to",
    "i would love to",
    
    # LAZY GENERIC PHRASES (sound templated, not human)
    "scaling is hard",
    "scaling is tough",
    "growth is hard",
    "growth is tough",
    "scaling fast is hard",
    "scaling fast is tough",
    "growth must be tough",
    "must be tough",
    "must hurt",
    "must be a pain",
    "must be crazy",
    "must be a headache",
    "must be a challenge",
    "must be brutal",
    "growing fast is tough",
    "growing fast is hard",
    "funding is a challenge",
    # NEW: Overused AI patterns per LeadGenJay
    "sound familiar?",         # Every AI uses this
    "you're probably",         # Generic assumption
    "most teams struggle",     # Templated garbage
    "you're likely",           # Another assumption
    
    # Follow-up phrases in initial emails
    "touching base",
    "circling back",
    "following up",
    "just following up",
    "bumping this",
    
    # Corporate jargon
    "leverage",
    "synergy",
    "streamline",
    "optimize",
    "innovative",
    "cutting-edge",
    "game-changing",
    "game changer",
    "revolutionary",
    "state of the art",
    "best in class",
    "world class",
    "comprehensive",
    "incentivize",
    "holistic",
    "paradigm",
    "scalable solution",
    "value proposition",
    "thought leadership",
    "circle back",
    "low-hanging fruit",
    "move the needle",
    "bandwidth",  # unless specifically about tech
    "deep dive",
    
    # Salesy phrases
    "partnership opportunity",
    "business opportunity",
    "schedule a call",
    "book a meeting",
    "set up time",
    "let's set up",
    "i'd like to schedule",
    "free consultation",
    "no obligation",
    "limited time",
    "act now",
    "don't miss",
    "exclusive offer",
    
    # Too formal questions
    "how are you handling",
    "how are you managing",
    "how are you navigating",
    "how are you ensuring",
    "how's that affecting",
    "are you struggling with",
    
    # Self-introductions
    "my name is",
    "i am the",
    "i'm the founder",
    "let me introduce",
    "allow me to introduce",
    
    # Desperation signals
    "please let me know",
    "please respond",
    "looking forward to hearing",
    "hoping to hear",
    "i really think",
    "i truly believe",
    
    # AI WRITING TELLS - These scream "written by ChatGPT"
    "delve",
    "delving",
    "dive into",
    "diving into",
    "deep dive",
    "it's worth noting",
    "worth noting that",
    "interestingly",
    "importantly",
    "crucially",
    "notably",
    "essentially",
    "fundamentally",
    "ultimately",
    "additionally",
    "furthermore",
    "moreover",
    "in today's",
    "in this day and age",
    "navigating the",
    "landscape",
    "realm",
    "foster",
    "facilitate",
    "utilize",
    "spearhead",
    "embark",
    "embarking",
    "pave the way",
    "at the forefront",
    "cutting edge",
    "game-changer",
    "robust",
    "seamless",
    "seamlessly",
    "elevate",
    "elevating",
    "harness",
    "harnessing",
    "pivotal",
    "myriad",
    "plethora",
    "multifaceted",
    "nuanced",
    "bolster",
    "underscore",
    "underscores",
    "in essence",
    "at its core",
    "serves as",
    "aimed at",
    "geared towards",
    "in the realm of",
    "when it comes to",
    "not only... but also",
    "whether it's... or",
    "from... to...",
    "revolutionize",
    "revolutionizing",
    "transform",
    "transforming",
    "reimagine",
    "reimagining",
    "unlock",
    "unlocking",
    "empower",
    "empowering",
    "supercharge",
]

# AI PUNCTUATION PATTERNS - Instant AI detection
AI_PUNCTUATION_TELLS = [
    "—",  # Em dash - AI LOVES this
    "–",  # En dash
    "…",  # Ellipsis character (real humans type ...)
]

SPAM_TRIGGER_WORDS = [
    "free", "guarantee", "guaranteed", "promise", "amazing", "incredible",
    "unbelievable", "act now", "limited time", "urgent", "winner",
    "congratulations", "100%", "risk free", "no risk", "click here",
    "buy now", "order now", "special offer", "best price"
]


class EmailReviewer:
    """
    Production-ready email reviewer that uses the configured LLM provider
    (Groq or OpenAI) to critically evaluate cold emails against expert guidelines.
    
    SELF-IMPROVEMENT: 
    - Stores all reviews in MongoDB
    - Learns from failures to generate improvement prompts
    - Tracks patterns over time
    """
    
    def __init__(self):
        # Use the same LLM client as email_generator (respects LLM_PROVIDER config)
        self.client, self.model, self.provider = get_llm_client()
        self.rate_limiter = get_rate_limiter() if self.provider == 'groq' else None
        print(f"📋 Email reviewer using: {self.provider.upper()} ({self.model})")
        if self.rate_limiter:
            print(f"   ✅ Model rotation enabled (fallback chain active)")
        
        # Thresholds
        self.min_passing_score = 70
        self.warning_threshold = 80
        self.max_word_count = 75
        self.min_word_count = 18  # Minimum word count - lowered from 25 (was too strict)
        self.ideal_word_count_min = 35
        self.ideal_word_count_max = 65
        self.max_subject_words = 4
    
    def _call_llm(self, system_prompt: str, user_prompt: str, temperature: float = 0.3, json_mode: bool = True) -> str:
        """
        Call the LLM with automatic Groq model fallback (same as EmailGenerator).
        Returns the response content as string.
        """
        # For OpenAI or Ollama, just make the call directly
        if self.provider in ['openai', 'ollama']:
            kwargs = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": temperature,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        
        # For Groq, use aggressive fallback - try each model in chain until one works
        tried_models = set()
        last_error = None
        
        while True:
            # Find an available model from the fallback chain
            available_model = self.rate_limiter.get_best_available_model(self.model)
            
            # Skip models we've already tried this call
            if available_model in tried_models:
                for model in GROQ_FALLBACK_CHAIN:
                    if model not in tried_models:
                        available_model = model
                        break
                else:
                    available_model = None
            
            if available_model is None:
                # All Groq models exhausted - fall back to OpenAI if available
                if getattr(config, 'OPENAI_API_KEY', None):
                    print(f"   ⚠️ All Groq models exhausted, reviewer falling back to OpenAI")
                    from openai import OpenAI
                    openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
                    openai_model = getattr(config, 'OPENAI_MODEL', 'gpt-4.1-mini')
                    kwargs = {
                        "model": openai_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": temperature,
                    }
                    if json_mode:
                        kwargs["response_format"] = {"type": "json_object"}
                    response = openai_client.chat.completions.create(**kwargs)
                    return response.choices[0].message.content
                else:
                    raise last_error or Exception("All Groq models rate limited and no OpenAI fallback configured")
            
            tried_models.add(available_model)
            
            try:
                kwargs = {
                    "model": available_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": temperature,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                
                response = self.client.chat.completions.create(**kwargs)
                
                # Check for empty response
                content = response.choices[0].message.content
                if not content or content.strip() == '':
                    print(f"   ⚠️ {available_model} returned empty response, trying next model...")
                    continue
                
                # Validate JSON if json_mode was requested
                if json_mode:
                    try:
                        json.loads(content)
                    except json.JSONDecodeError as e:
                        print(f"   ⚠️ {available_model} returned invalid JSON, trying next model...")
                        continue
                
                # Record successful request with token usage
                tokens_used = 2000  # Default estimate
                if hasattr(response, 'usage') and response.usage:
                    tokens_used = getattr(response.usage, 'total_tokens', 2000)
                self.rate_limiter.record_request(available_model, tokens_used)
                
                return content
                
            except Exception as e:
                error_str = str(e).lower()
                last_error = e
                
                # If it's a rate limit error, mark this model as depleted and try next
                if 'rate' in error_str and 'limit' in error_str:
                    self.rate_limiter.mark_model_depleted(available_model, "429_rate_limit")
                    print(f"   ⚠️ Reviewer: {available_model} hit rate limit, marked as depleted, trying next model...")
                    continue
                # If it's a 413 "Request Entity Too Large" error, skip this model (prompt too big for it)
                elif '413' in error_str or 'too large' in error_str or 'payload' in error_str:
                    print(f"   ⚠️ Reviewer: {available_model} returned 413 (prompt too large), trying next model...")
                    continue
                elif '503' in error_str or 'service unavailable' in error_str or '502' in error_str or 'bad gateway' in error_str or 'over capacity' in error_str:
                    print(f"   ⚠️ Reviewer: {available_model} returned 503/502 (service unavailable), trying next model...")
                    continue
                elif 'timeout' in error_str or 'timed out' in error_str or 'connection' in error_str:
                    print(f"   ⚠️ Reviewer: {available_model} connection error, trying next model...")
                    continue
                else:
                    raise
    
    def review_email(self, 
                     email: Dict[str, str],
                     lead: Dict[str, Any],
                     email_type: str = "initial",
                     email_id: str = None,
                     save_review: bool = True) -> ReviewResult:
        """
        Comprehensive review of an email against all guidelines.
        
        Args:
            email: Dict with 'subject' and 'body'
            lead: Lead information for context (company, industry, etc.)
            email_type: "initial" or "followup"
            email_id: Database email ID (for linking review)
            save_review: Whether to save review to database (for learning)
        
        Returns:
            ReviewResult with pass/fail status, score, issues, and suggestions
        """
        subject = email.get('subject', '')
        body = email.get('body', '')
        
        # Run all checks
        rule_violations = []
        issues = []
        suggestions = []
        score = 100
        
        # 1. Rule-based checks (fast, deterministic)
        rule_results = self._run_rule_checks(subject, body, lead)
        rule_violations.extend(rule_results['violations'])
        issues.extend(rule_results['issues'])
        suggestions.extend(rule_results['suggestions'])
        score -= rule_results['penalty']
        
        # 2. AI-powered deep analysis
        ai_result = self._run_ai_review(subject, body, lead, email_type)
        issues.extend(ai_result['issues'])
        suggestions.extend(ai_result['suggestions'])
        score -= ai_result['penalty']
        
        # CRITICAL: If AI review failed, treat it as a rule violation
        # Emails should NOT pass without proper AI review
        if ai_result.get('ai_review_failed', False):
            rule_violations.append("AI review failed - email must be re-reviewed")
        
        # Clamp score
        score = max(0, min(100, score))
        
        # Determine status
        if rule_violations or score < self.min_passing_score:
            status = ReviewStatus.FAIL
            rewrite_required = True
        elif score < self.warning_threshold:
            status = ReviewStatus.WARNING
            rewrite_required = False
        else:
            status = ReviewStatus.PASS
            rewrite_required = False
        
        result = ReviewResult(
            status=status,
            score=score,
            issues=issues,
            suggestions=suggestions,
            rewrite_required=rewrite_required,
            ai_feedback=ai_result.get('feedback', ''),
            rule_violations=rule_violations
        )
        
        # Save review to database for self-improvement
        if save_review:
            self._save_review(
                email=email,
                lead=lead,
                email_id=email_id,
                result=result
            )
        
        return result
    
    def _save_review(self, email: Dict, lead: Dict, email_id: str, result: ReviewResult):
        """Save review to MongoDB for self-improvement learning."""
        try:
            doc = {
                "email_id": email_id,
                "subject": email.get('subject', ''),
                "body": email.get('body', ''),
                "lead_id": str(lead.get('_id')) if lead.get('_id') else None,
                "lead_company": lead.get('company'),
                "lead_industry": lead.get('industry'),
                "passed": result.status == ReviewStatus.PASS,
                "score": result.score,
                "status": result.status.value,
                "issues": [
                    {"type": i.get('type'), "severity": i.get('severity'), "message": i.get('message')}
                    for i in result.issues
                ],
                "suggestions": result.suggestions,
                "rule_violations": result.rule_violations,
                "ai_feedback": result.ai_feedback,
                "created_at": datetime.utcnow()
            }
            email_reviews_collection.insert_one(doc)
        except Exception as e:
            print(f"   ⚠️ Failed to save review: {e}")
    
    def get_recent_reviews(self, 
                          days: int = 7, 
                          only_failures: bool = False,
                          limit: int = 50) -> List[Dict]:
        """Get recent reviews for learning/analysis."""
        query = {
            "created_at": {"$gte": datetime.utcnow() - timedelta(days=days)}
        }
        if only_failures:
            query["passed"] = False
        
        return list(email_reviews_collection.find(
            query,
            {"_id": 0, "body": 0}  # Exclude full body for efficiency
        ).sort("created_at", -1).limit(limit))
    
    def get_improvement_prompt(self, days: int = 14) -> str:
        """
        Generate a prompt section based on recent failures.
        
        This is the SELF-IMPROVEMENT mechanism - we learn from past mistakes
        and inject that knowledge into the generation prompt.
        """
        recent_failures = self.get_recent_reviews(days=days, only_failures=True, limit=200)
        
        if not recent_failures:
            return ""
        
        # Aggregate violations - but SKIP API failures (not quality issues)
        violation_counts = {}
        
        for review in recent_failures:
            # Skip API failures - these aren't quality issues
            violations = review.get('rule_violations', [])
            if violations and any('AI review failed' in str(v) for v in violations if v):
                continue
            
            # Count rule violations
            for violation in violations:
                if not violation:
                    continue
                v_str = str(violation)
                # Extract the key part (banned phrase or pattern)
                if 'banned phrase' in v_str.lower():
                    # Extract just the phrase: "Contains banned phrase: 'bandwidth'" -> "bandwidth"
                    match = re.search(r"'([^']+)'", v_str)
                    if match:
                        v_key = f"NEVER use: '{match.group(1)}'"
                        violation_counts[v_key] = violation_counts.get(v_key, 0) + 1
                elif 'em dash' in v_str.lower():
                    v_key = "NEVER use em dashes (—)"
                    violation_counts[v_key] = violation_counts.get(v_key, 0) + 1
                elif 'spammy pattern' in v_str.lower():
                    match = re.search(r"'([^']+)'", v_str)
                    if match:
                        v_key = f"NEVER use in subject: '{match.group(1)}'"
                        violation_counts[v_key] = violation_counts.get(v_key, 0) + 1
        
        if not violation_counts:
            return ""
        
        # Build a CONCISE improvement prompt
        prompt_lines = ["\n**CRITICAL - AVOID THESE (learned from past failures):**"]
        
        # Top violations - only significant ones
        top_violations = sorted(violation_counts.items(), key=lambda x: -x[1])[:5]
        for violation, count in top_violations:
            if count >= 2:  # Only include if happened multiple times
                prompt_lines.append(f"- {violation} (failed {count}x)")
        
        if len(prompt_lines) == 1:
            return ""  # No meaningful learnings
        
        return "\n".join(prompt_lines)
    
    def get_review_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get aggregate statistics on reviews."""
        since = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {"$group": {
                "_id": None,
                "total": {"$sum": 1},
                "passed": {"$sum": {"$cond": ["$passed", 1, 0]}},
                "failed": {"$sum": {"$cond": [{"$not": "$passed"}, 1, 0]}},
                "avg_score": {"$avg": "$score"},
                "min_score": {"$min": "$score"},
                "max_score": {"$max": "$score"}
            }}
        ]
        
        result = list(email_reviews_collection.aggregate(pipeline))
        
        if result:
            stats = result[0]
            del stats['_id']
            stats['pass_rate'] = round(stats['passed'] / stats['total'] * 100, 1) if stats['total'] > 0 else 0
            stats['avg_score'] = round(stats['avg_score'], 1) if stats['avg_score'] else 0
            stats['days'] = days
            return stats
        
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "pass_rate": 0,
            "avg_score": 0,
            "min_score": 0,
            "max_score": 0,
            "days": days
        }
    
    def _run_rule_checks(self, subject: str, body: str, lead: Dict) -> Dict:
        """
        Fast rule-based checks that don't need AI.
        These are hard rules that cause instant failure.
        """
        violations = []
        issues = []
        suggestions = []
        penalty = 0
        
        body_lower = body.lower()
        subject_lower = subject.lower()
        company = (lead.get('company') or '').lower()
        
        # =================================================================
        # CHECK 1: Word count (CRITICAL)
        # =================================================================
        word_count = len(body.split())
        if word_count > self.max_word_count:
            violations.append(f"Word count {word_count} exceeds maximum of {self.max_word_count}")
            penalty += 30
            issues.append({
                "type": "word_count",
                "severity": "critical",
                "message": f"Email is {word_count} words. Maximum is {self.max_word_count}.",
                "current": word_count,
                "required": self.max_word_count
            })
            suggestions.append(f"Cut {word_count - self.max_word_count} words. Remove filler and keep only essential points.")
        elif word_count < self.min_word_count:
            # NEW: Too short is now a VIOLATION (not warning)
            violations.append(f"Word count {word_count} below minimum of {self.min_word_count} - too robotic")
            penalty += 25
            issues.append({
                "type": "word_count_too_low",
                "severity": "critical",
                "message": f"Email is only {word_count} words. Minimum is {self.min_word_count}. This feels robotic.",
                "current": word_count,
                "required": self.min_word_count
            })
            suggestions.append(f"Add {self.min_word_count - word_count} more words. Include specific company observation or expand the pain point.")
        elif word_count > self.ideal_word_count_max:
            penalty += 5
            issues.append({
                "type": "word_count",
                "severity": "warning",
                "message": f"Email is {word_count} words. Ideal is {self.ideal_word_count_min}-{self.ideal_word_count_max}.",
                "current": word_count,
                "ideal": f"{self.ideal_word_count_min}-{self.ideal_word_count_max}"
            })
        elif word_count < self.ideal_word_count_min:
            penalty += 5
            issues.append({
                "type": "word_count",
                "severity": "warning",
                "message": f"Email might be too short ({word_count} words). May lack substance.",
            })
        
        # =================================================================
        # CHECK 1.5: TEMPLATED OPENER DETECTION (NEW)
        # =================================================================
        first_line = body.split('\n')[0].strip().lower() if body else ""
        
        # These patterns indicate a lazy, templated email
        templated_opener_patterns = [
            (r"^(random|odd|quick)\s+(thought|q)\.\s+\w+('s|s)?\s+(scaling|growth|growing)\s+(is\s+)?(fast|hard|tough)", "Templated opener: '[type]. [Company] scaling [adjective]' - too robotic"),
            (r"^(random|odd|quick)\s+(thought|q)\.\s+\w+\s+scaling\s+fast\b", "Templated opener: starts with generic '[type]. [Company] scaling fast'"),
            (r"^(random|odd|quick)\s+(thought|q)\.\s+\w+('s)?\s+growth\s+(is\s+)?(fast|tough|hard)", "Templated opener: '[type]. [Company] growth is [adjective]'"),
            (r"^(random|odd|quick)\s+(thought|q)\.\s+scaling\s+(at\s+)?\w+\s+must", "Templated opener: 'scaling at [Company] must...' pattern"),
        ]
        
        for pattern, message in templated_opener_patterns:
            if re.search(pattern, first_line):
                violations.append(message)
                penalty += 20
                issues.append({
                    "type": "templated_opener",
                    "severity": "critical",
                    "message": message,
                    "line": first_line[:60]
                })
                suggestions.append("Write a unique opener. Don't just say '[Company] scaling fast' - reference something SPECIFIC about them.")
                break  # Only flag one pattern
        
        # Check for repetitive "scaling fast" / "growth is tough" anywhere
        lazy_patterns = [
            (r"\bscaling fast\b.*\bscaling is (hard|tough)\b", "Redundant: says 'scaling fast' then 'scaling is hard/tough'"),
            (r"\bgrowth is (fast|tough|hard)\.\s*(scaling|growth) is (tough|hard)", "Redundant: repeats growth/scaling difficulty"),
        ]
        for pattern, message in lazy_patterns:
            if re.search(pattern, body_lower):
                penalty += 15
                issues.append({
                    "type": "redundant_phrases",
                    "severity": "warning",
                    "message": message,
                })
        
        # =================================================================
        # CHECK 2: Banned phrases (CRITICAL)
        # =================================================================
        found_banned = []
        for phrase in BANNED_PHRASES:
            if phrase in body_lower:
                found_banned.append(phrase)
        
        if found_banned:
            penalty += 20 * len(found_banned)
            for phrase in found_banned:
                violations.append(f"Contains banned phrase: '{phrase}'")
                issues.append({
                    "type": "banned_phrase",
                    "severity": "critical",
                    "message": f"Contains banned phrase: '{phrase}'",
                    "phrase": phrase
                })
            suggestions.append("Remove or rephrase banned phrases. These scream 'cold email' to recipients.")
        
        # =================================================================
        # CHECK 2.5: AI Punctuation Tells (CRITICAL - instant AI detection)
        # =================================================================
        found_ai_punctuation = []
        for char in AI_PUNCTUATION_TELLS:
            if char in body or char in subject:
                found_ai_punctuation.append(char)
        
        if found_ai_punctuation:
            penalty += 25  # Heavy penalty - this is a dead giveaway
            for char in found_ai_punctuation:
                char_name = {
                    "—": "em dash (—)",
                    "–": "en dash (–)", 
                    "…": "ellipsis character (…)"
                }.get(char, char)
                violations.append(f"Contains AI punctuation tell: {char_name}")
                issues.append({
                    "type": "ai_punctuation",
                    "severity": "critical",
                    "message": f"Contains {char_name} - this screams AI-written. Use comma, period, or '...' instead.",
                })
            suggestions.append("Replace em dashes (—) with commas or periods. Use '...' not '…'. These are AI tells.")
        
        # =================================================================
        # CHECK 3: Subject line
        # =================================================================
        subject_words = len(subject.split())
        if subject_words > self.max_subject_words:
            penalty += 10
            issues.append({
                "type": "subject_length",
                "severity": "warning",
                "message": f"Subject is {subject_words} words. Should be 2-{self.max_subject_words}.",
            })
            suggestions.append("Shorten subject line. Good examples: 'mike?', 'thought', 'quick q'")
        
        bad_subject_patterns = [
            "partnership", "opportunity", "meeting request", "introduction",
            "quick question", "following up", "checking in", "touching base"
        ]
        for pattern in bad_subject_patterns:
            if pattern in subject_lower:
                penalty += 15
                violations.append(f"Subject contains spammy pattern: '{pattern}'")
                issues.append({
                    "type": "subject_pattern",
                    "severity": "critical",
                    "message": f"Subject contains pattern that screams cold email: '{pattern}'",
                })
        
        # =================================================================
        # CHECK 4: First line check (Preview text)
        # =================================================================
        first_line = body.split('\n')[0].strip().lower() if body else ""
        
        bad_openers = [
            "i noticed", "i saw", "i came across", "i'm reaching out",
            "i am reaching out", "i wanted to", "i'd like to", "my name is",
            "hi,", "hello,", "dear ", "hope this"
        ]
        for opener in bad_openers:
            if first_line.startswith(opener):
                penalty += 20
                violations.append(f"First line starts with robotic opener: '{opener}'")
                issues.append({
                    "type": "first_line",
                    "severity": "critical",
                    "message": f"First line starts with '{opener}' - this kills open rates. Preview text must sound like a friend.",
                })
                suggestions.append("Start with specific observation about their company, not about yourself or what you noticed.")
                break
        
        # =================================================================
        # CHECK 5: Multiple CTAs
        # =================================================================
        cta_phrases = [
            "worth a chat", "worth a quick chat", "interested?", 
            "make sense?", "open to it?", "curious if", "thoughts?",
            "worth exploring?", "want to hear", "happy to chat",
            "let me know", "schedule a call", "book a meeting"
        ]
        cta_count = sum(1 for cta in cta_phrases if cta in body_lower)
        
        if cta_count > 1:
            penalty += 15
            issues.append({
                "type": "multiple_ctas",
                "severity": "critical",
                "message": f"Found {cta_count} CTAs. Multiple CTAs = desperate. Use exactly ONE.",
            })
            violations.append(f"Multiple CTAs detected ({cta_count}) - looks desperate")
            suggestions.append("Keep only ONE soft CTA at the end. Remove all others.")
        elif cta_count == 0:
            penalty += 10
            issues.append({
                "type": "missing_cta",
                "severity": "warning",
                "message": "No clear CTA found. End with a soft ask like 'interested?' or 'make sense?'",
            })
        
        # =================================================================
        # CHECK 6: Spam trigger words
        # =================================================================
        found_spam_words = [w for w in SPAM_TRIGGER_WORDS if w in body_lower]
        if found_spam_words:
            penalty += 10 * len(found_spam_words)
            for word in found_spam_words:
                issues.append({
                    "type": "spam_word",
                    "severity": "warning",
                    "message": f"Contains spam trigger word: '{word}'",
                })
            suggestions.append(f"Remove spam trigger words: {', '.join(found_spam_words)}")
        
        # =================================================================
        # CHECK 7: Specificity check
        # =================================================================
        vague_patterns = [
            "something interesting", "great things", "awesome work",
            "impressive", "amazing company", "doing well", "great job",
            "new feature", "new product", "your platform"
        ]
        company = (lead.get('company') or '').lower()
        
        for pattern in vague_patterns:
            if pattern in body_lower and company not in body_lower:
                penalty += 5
                issues.append({
                    "type": "vague_reference",
                    "severity": "warning",
                    "message": f"Vague reference: '{pattern}'. Be SPECIFIC about what you saw.",
                })
                suggestions.append("Replace vague observations with specific details about their company or product.")
                break
        
        # =================================================================
        # CHECK 8: Case study specificity
        # =================================================================
        # Check for rounded numbers (bad) vs specific numbers (good)
        if re.search(r'\b[234]x\b', body_lower):  # 2x, 3x, 4x (rounded)
            if not re.search(r'\b\d+\.\d+x\b', body_lower):  # Not 2.7x, 3.2x (specific)
                penalty += 5
                issues.append({
                    "type": "rounded_numbers",
                    "severity": "warning",
                    "message": "Use specific numbers like '3.2x' instead of rounded '3x'. Specifics build trust.",
                })
        
        if re.search(r'~\d+%', body):  # ~40% is bad
            penalty += 5
            issues.append({
                "type": "approximate_numbers",
                "severity": "warning",
                "message": "Don't use approximate numbers (~40%). Use exact: '43%'.",
            })
        
        # =================================================================
        # CHECK 9: Company name personalization
        # =================================================================
        if company and company.lower() not in body_lower:
            penalty += 10
            issues.append({
                "type": "missing_personalization",
                "severity": "warning",
                "message": f"Company name '{lead.get('company')}' not mentioned in email body.",
            })
            suggestions.append("Include the company name in the first line for personalization.")
        
        return {
            "violations": violations,
            "issues": issues,
            "suggestions": list(set(suggestions)),  # Dedupe
            "penalty": penalty
        }
    
    def _run_ai_review(self, subject: str, body: str, lead: Dict, email_type: str) -> Dict:
        """
        AI-powered deep analysis for nuanced issues that rules can't catch.
        """
        system_prompt = f"""You are an expert cold email reviewer trained on Eric Nowoslawski's 90-page 
cold email masterclass and LeadGenJay's $15M cold email strategies.

Your job is to CRITICALLY review this email and find issues that would cause low reply rates.

GUIDELINES YOU ENFORCE:
{COLD_EMAIL_GUIDELINES}

CRITICAL - CHECK FOR AI WRITING TELLS:
- Em dashes (—) are a MAJOR red flag - instant AI detection
- Words like: delve, leverage, utilize, robust, seamless, pivotal, foster, harness
- Transitions like: furthermore, moreover, additionally, importantly, notably
- Phrases like: "it's worth noting", "in today's [X]", "at its core"
- Too smooth/polished writing - real humans are choppy
- Lack of contractions (don't, can't, won't)
- Uniform sentence lengths - humans vary

LEAD CONTEXT:
- Name: {lead.get('first_name', 'Unknown')}
- Company: {lead.get('company', 'Unknown')}
- Title: {lead.get('title', 'Unknown')}
- Industry: {lead.get('industry', 'Unknown')}

EMAIL TYPE: {email_type}

Analyze the email and return JSON:
{{
    "overall_score": 0-100,
    "tone_score": 0-100,  // Does it sound like a friend texting? Or a salesperson?
    "specificity_score": 0-100,  // Is the observation specific to THIS company?
    "structure_score": 0-100,  // Does it follow the 4-line framework?
    "readability_score": 0-100,  // Is it 6th grade reading level?
    "human_score": 0-100,  // Does it sound human-written or AI-generated?
    "issues": [
        {{
            "type": "tone|specificity|structure|relevance|other",
            "severity": "critical|warning|minor",
            "message": "What's wrong",
            "line": "The problematic text"
        }}
    ],
    "suggestions": ["Specific actionable suggestions"],
    "feedback": "2-3 sentence overall assessment",
    "would_you_reply": true/false,
    "why_or_why_not": "Brief explanation",
    "sounds_ai_written": true/false,
    "ai_tells_found": ["list any AI writing tells you spotted"]
}}

Be CRITICAL. A 70 score means "barely acceptable". 
90+ means "this could be from Eric Nowoslawski himself".
If the email sounds AI-written (em dashes, corporate words, too polished), score it LOW."""

        user_prompt = f"""Review this cold email:

SUBJECT: {subject}

BODY:
{body}

Be harsh but fair. Find everything that could hurt reply rates.
Pay special attention to whether this sounds human or AI-written."""

        try:
            # Use _call_llm for automatic model rotation on rate limits
            response_content = self._call_llm(system_prompt, user_prompt, temperature=0.3, json_mode=True)
            
            result = json.loads(response_content)
            
            # Calculate penalty from AI scores
            ai_score = result.get('overall_score', 70)
            penalty = max(0, 100 - ai_score) // 2  # Half weight compared to rules
            
            issues = result.get('issues', [])
            suggestions = result.get('suggestions', [])
            feedback = result.get('feedback', '')
            
            # Add would-you-reply insight
            if not result.get('would_you_reply', True):
                issues.append({
                    "type": "ai_judgment",
                    "severity": "warning",
                    "message": f"AI reviewer says they would NOT reply: {result.get('why_or_why_not', 'No reason given')}"
                })
            
            return {
                "issues": issues,
                "suggestions": suggestions,
                "feedback": feedback,
                "penalty": penalty,
                "raw_scores": {
                    "tone": result.get('tone_score', 0),
                    "specificity": result.get('specificity_score', 0),
                    "structure": result.get('structure_score', 0),
                    "readability": result.get('readability_score', 0)
                }
            }
            
        except Exception as e:
            print(f"AI review failed: {e}")
            # IMPORTANT: When AI review fails, flag it so review_email can fail the email
            # Emails should NOT pass without proper AI review
            return {
                "issues": [{
                    "type": "ai_review_failed",
                    "severity": "critical",  # Changed from warning to critical
                    "message": f"AI review failed: {str(e)} - email needs manual review or retry"
                }],
                "suggestions": ["Retry email generation or manually review before sending"],
                "feedback": f"AI review failed: {str(e)}",
                "penalty": 15,
                "ai_review_failed": True  # Flag to trigger rule violation
            }
    
    def review_and_rewrite_if_needed(self,
                                      email: Dict[str, str],
                                      lead: Dict[str, Any],
                                      generator,  # EmailGenerator instance
                                      campaign_context: Dict[str, Any],
                                      max_attempts: int = 3) -> Tuple[Dict[str, str], ReviewResult]:
        """
        Review email and rewrite if it fails. Returns (final_email, final_review).
        
        Args:
            email: The email to review
            lead: Lead info
            generator: EmailGenerator instance for rewrites
            campaign_context: Campaign context for rewrites
            max_attempts: Maximum rewrite attempts
        
        Returns:
            Tuple of (final_email, final_review)
        """
        attempt = 0
        current_email = email
        
        while attempt < max_attempts:
            attempt += 1
            review = self.review_email(current_email, lead)
            
            print(f"\n📝 Review attempt {attempt}:")
            print(f"   Score: {review.score}/100")
            print(f"   Status: {review.status.value}")
            
            if not review.rewrite_required:
                print(f"   ✅ Email passed review!")
                return current_email, review
            
            print(f"   ❌ Email failed review. Issues:")
            for issue in review.issues[:3]:  # Show top 3 issues
                print(f"      - {issue.get('message', str(issue))}")
            
            if attempt < max_attempts:
                print(f"   🔄 Generating rewrite...")
                current_email = self._rewrite_email(current_email, lead, review, campaign_context)
        
        # After max attempts, return best effort
        final_review = self.review_email(current_email, lead)
        if final_review.status == ReviewStatus.FAIL:
            print(f"   ⚠️ Email still failing after {max_attempts} attempts. Using best effort.")
        
        return current_email, final_review
    
    def _rewrite_email(self, 
                       email: Dict[str, str],
                       lead: Dict[str, Any],
                       review: ReviewResult,
                       campaign_context: Dict[str, Any]) -> Dict[str, str]:
        """
        Rewrite email based on review feedback using full LeadGenJay guidelines.
        """
        # Safe access to review fields (handle potential None values)
        issues = review.issues if review and hasattr(review, 'issues') and review.issues else []
        suggestions = review.suggestions if review and hasattr(review, 'suggestions') and review.suggestions else []
        rule_violations = review.rule_violations if review and hasattr(review, 'rule_violations') and review.rule_violations else []
        
        # Build text safely
        issues_text = "\n".join([
            f"- {i.get('message', str(i)) if isinstance(i, dict) else str(i)}" 
            for i in issues
        ])
        suggestions_text = "\n".join([f"- {s}" for s in suggestions])
        violations_text = "\n".join([f"- {v}" for v in rule_violations])
        
        # Get improvement context from past failures
        improvement_context = self.get_improvement_prompt(days=14)
        
        system_prompt = f"""You are rewriting a cold email that failed quality review.

{COLD_EMAIL_GUIDELINES}

**ISSUES THAT CAUSED THIS EMAIL TO FAIL:**
{violations_text if violations_text else 'No hard rule violations'}

{issues_text}

**REVIEWER SUGGESTIONS:**
{suggestions_text}
{improvement_context if improvement_context else ''}

**YOUR TASK:**
Rewrite the email fixing ALL issues above while following the LeadGenJay guidelines exactly.

**CRITICAL: SOUND HUMAN, NOT AI**
- NEVER use em dashes (—) or en dashes (–). Use commas or periods instead.
- NEVER use words like: delve, leverage, utilize, robust, seamless, pivotal, foster, harness
- Use choppy sentences. Short and punchy. Not smooth AI transitions.
- Use contractions naturally (don't, can't, isn't, that's)
- Write like you text a friend, not like a press release

**STRUCTURE TO USE (4 lines):**
Line 1: Curiosity hook - "random question." or "odd thought." or "quick q for you." (with PERIOD, not em dash)
Line 2: Poke the bear - State their pain in ONE sentence (don't ask about it)
Line 3: Case study - "a [industry] company hit [specific number] in [timeline]"
Line 4: Soft CTA - "worth a chat?", "make sense?", "thoughts?"

Return JSON: {{"subject": "...", "body": "..."}}"""

        user_prompt = f"""Rewrite this FAILED email:

LEAD:
- Name: {lead.get('first_name', '')}
- Company: {lead.get('company', '')}
- Title: {lead.get('title', '')}
- Industry: {lead.get('industry', '')}

FAILED EMAIL:
Subject: {email.get('subject', '')}

{email.get('body', '')}

Fix ALL the issues. Follow LeadGenJay's guidelines EXACTLY:
- Subject: 2-4 words like a colleague ("random thought", "quick q", NOT "Name?")
- First line: Curiosity hook, NOT company observation
- Under 75 words (aim for 50-60)
- ONE soft CTA
- 6th grade reading level
- NO em dashes (—) anywhere"""

        try:
            # Use _call_llm for automatic model rotation on rate limits
            response_content = self._call_llm(system_prompt, user_prompt, temperature=0.8, json_mode=True)
            
            # Handle None or empty response
            if not response_content:
                print(f"Rewrite failed: LLM returned empty response")
                return email
            
            result = json.loads(response_content)
            
            # Post-process to remove any AI tells the LLM sneaks in
            # Use 'or' to handle both None and empty string from result.get()
            subject = result.get("subject") or email.get("subject", "")
            body = result.get("body") or email.get("body", "")
            
            subject = humanize_email(subject) if subject else email.get("subject", "")
            body = humanize_email(body) if body else email.get("body", "")
            
            return {
                "subject": subject,
                "body": body
            }
            
        except Exception as e:
            print(f"Rewrite failed: {e}")
            return email  # Return original if rewrite fails
    
    def batch_review(self, emails: List[Dict]) -> Dict[str, Any]:
        """
        Review multiple emails and return aggregate statistics.
        
        Args:
            emails: List of dicts with 'email' (subject/body) and 'lead' info
        
        Returns:
            Aggregate review statistics
        """
        results = {
            "total": len(emails),
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "average_score": 0,
            "common_issues": {},
            "reviews": []
        }
        
        total_score = 0
        
        for item in emails:
            email = item.get('email', {})
            lead = item.get('lead', {})
            
            review = self.review_email(email, lead)
            results["reviews"].append({
                "lead": lead.get('email', lead.get('full_name', 'Unknown')),
                "status": review.status.value,
                "score": review.score,
                "issue_count": len(review.issues)
            })
            
            total_score += review.score
            
            if review.status == ReviewStatus.PASS:
                results["passed"] += 1
            elif review.status == ReviewStatus.FAIL:
                results["failed"] += 1
            else:
                results["warnings"] += 1
            
            # Track common issues
            for issue in review.issues:
                issue_type = issue.get('type', 'unknown')
                results["common_issues"][issue_type] = results["common_issues"].get(issue_type, 0) + 1
        
        results["average_score"] = total_score / len(emails) if emails else 0
        results["pass_rate"] = (results["passed"] / len(emails) * 100) if emails else 0
        
        return results


def format_review_report(review: ReviewResult) -> str:
    """Format a review result as a readable report."""
    status_emoji = {
        ReviewStatus.PASS: "✅",
        ReviewStatus.FAIL: "❌",
        ReviewStatus.WARNING: "⚠️"
    }
    
    report = []
    report.append(f"\n{'='*60}")
    report.append(f"{status_emoji[review.status]} REVIEW RESULT: {review.status.value.upper()}")
    report.append(f"{'='*60}")
    report.append(f"Score: {review.score}/100")
    report.append(f"Rewrite Required: {'Yes' if review.rewrite_required else 'No'}")
    
    if review.rule_violations:
        report.append(f"\n🚫 RULE VIOLATIONS ({len(review.rule_violations)}):")
        for v in review.rule_violations:
            report.append(f"   • {v}")
    
    if review.issues:
        report.append(f"\n⚠️ ISSUES ({len(review.issues)}):")
        for issue in review.issues:
            severity = issue.get('severity', 'unknown')
            emoji = "🔴" if severity == "critical" else "🟡" if severity == "warning" else "🔵"
            report.append(f"   {emoji} [{severity}] {issue.get('message', str(issue))}")
    
    if review.suggestions:
        report.append(f"\n💡 SUGGESTIONS:")
        for s in review.suggestions:
            report.append(f"   • {s}")
    
    if review.ai_feedback:
        report.append(f"\n🤖 AI FEEDBACK:")
        report.append(f"   {review.ai_feedback}")
    
    report.append(f"{'='*60}\n")
    
    return "\n".join(report)


# =============================================================================
# TEST
# =============================================================================
if __name__ == "__main__":
    reviewer = EmailReviewer()
    
    # Test with a problematic email
    test_email = {
        "subject": "Partnership Opportunity - Let's Connect!",
        "body": """I hope this email finds you well! I noticed your company is doing great things 
in the tech space. I'm reaching out because I'd love to tell you about our innovative solution 
that can help you leverage AI to streamline your operations and optimize your workflow.

We've helped similar companies achieve approximately 3x improvement in efficiency.

Would you be interested in scheduling a quick call to discuss? I'd love to set up a meeting 
at your convenience. Let me know what works best for you!

Looking forward to hearing from you."""
    }
    
    test_lead = {
        "first_name": "Sarah",
        "company": "TechFlow Inc",
        "title": "CTO",
        "industry": "SaaS"
    }
    
    print("Testing EmailReviewer with a problematic email...")
    review = reviewer.review_email(test_email, test_lead)
    print(format_review_report(review))
    
    # Test with a good email
    good_email = {
        "subject": "sarah?",
        "body": """TechFlow's new API gateway looks solid. Scaling that with microservices must be tricky.

We helped a SaaS company ship 3.2x faster in 8 weeks by handling their backend.

thoughts?"""
    }
    
    print("\n\nTesting with a well-written email...")
    review2 = reviewer.review_email(good_email, test_lead)
    print(format_review_report(review2))
    
    # Show stats and improvement prompt
    print("\n\n📊 REVIEW STATISTICS (Last 7 Days):")
    stats = reviewer.get_review_stats(days=7)
    print(f"   Total Reviews: {stats['total']}")
    print(f"   Passed: {stats['passed']} ({stats['pass_rate']}%)")
    print(f"   Failed: {stats['failed']}")
    print(f"   Avg Score: {stats['avg_score']}")
    
    print("\n\n📚 SELF-IMPROVEMENT PROMPT (from past failures):")
    improvement = reviewer.get_improvement_prompt(days=14)
    if improvement:
        print(improvement)
    else:
        print("   No failures recorded yet - nothing to learn from!")
