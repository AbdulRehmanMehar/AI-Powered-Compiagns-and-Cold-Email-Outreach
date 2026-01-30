"""
Lead Enrichment Agent

Crawls company websites and extracts REAL data for email personalization.
This replaces fake "I saw you're doing X" with actual observations.

Data extracted:
- Recent news/blog posts
- Tech stack hints (job postings, GitHub)
- Product offerings
- Company size/stage signals
- Leadership quotes
- Recent funding/growth signals
"""

import os
import re
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin
import hashlib

import httpx
from bs4 import BeautifulSoup
from groq import Groq

from database import leads_collection
from config import GROQ_API_KEY
from email_generator import get_rate_limiter, GROQ_FALLBACK_CHAIN, GROQ_MODEL_LIMITS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting for web requests
REQUEST_DELAY = 1.0  # seconds between requests to same domain
MAX_PAGES_PER_DOMAIN = 5  # Don't crawl too deep
REQUEST_TIMEOUT = 10  # seconds

# Groq models for analysis (use smaller models for cost efficiency)
ENRICHMENT_MODEL = "llama-3.1-8b-instant"  # Fast and cheap for extraction


class LeadEnricher:
    """
    Enriches lead data by crawling company websites and extracting
    real, specific information for email personalization.
    """
    
    def __init__(self):
        # Disable SDK auto-retry - we handle retries ourselves with model rotation
        self.groq_client = Groq(api_key=GROQ_API_KEY, max_retries=0)
        self.rate_limiter = get_rate_limiter()
        self.http_client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
        )
        self._domain_last_request: Dict[str, float] = {}
    
    def _call_llm(self, prompt: str, temperature: float = 0.3, max_tokens: int = 1000) -> str:
        """
        Call LLM with automatic model rotation on rate limits.
        """
        tried_models = set()
        last_error = None
        
        while True:
            # Find an available model
            available_model = self.rate_limiter.get_best_available_model(ENRICHMENT_MODEL)
            
            if available_model in tried_models:
                for model in GROQ_FALLBACK_CHAIN:
                    if model not in tried_models:
                        available_model = model
                        break
                else:
                    available_model = None
            
            if available_model is None:
                raise last_error or Exception("All Groq models rate limited")
            
            tried_models.add(available_model)
            
            try:
                response = self.groq_client.chat.completions.create(
                    model=available_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                # Check for empty response
                content = response.choices[0].message.content
                if not content or content.strip() == '':
                    logger.warning(f"Enricher: {available_model} returned empty response, trying next...")
                    continue
                
                # Record usage
                tokens_used = 1000
                if hasattr(response, 'usage') and response.usage:
                    tokens_used = getattr(response.usage, 'total_tokens', 1000)
                self.rate_limiter.record_request(available_model, tokens_used)
                
                return content
                
            except Exception as e:
                error_str = str(e).lower()
                last_error = e
                
                if 'rate' in error_str and 'limit' in error_str:
                    self.rate_limiter.mark_model_depleted(available_model, "429_rate_limit")
                    logger.warning(f"Enricher: {available_model} hit rate limit, marked as depleted, trying next...")
                    continue
                else:
                    raise
    
    async def close(self):
        """Clean up resources."""
        await self.http_client.aclose()
    
    def _get_company_domain(self, lead: Dict[str, Any]) -> Optional[str]:
        """Extract company domain from lead data."""
        # Try website field first
        website = lead.get('website') or lead.get('company_website')
        if website:
            parsed = urlparse(website if website.startswith('http') else f"https://{website}")
            return parsed.netloc or parsed.path.split('/')[0]
        
        # Try to extract from email
        email = lead.get('email', '')
        if email and '@' in email:
            domain = email.split('@')[1]
            # Skip generic email providers
            generic_providers = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com']
            if domain not in generic_providers:
                return domain
        
        # Try raw_data
        raw_data = lead.get('raw_data', {})
        if raw_data:
            website = raw_data.get('current_employer_website')
            if website:
                parsed = urlparse(website if website.startswith('http') else f"https://{website}")
                return parsed.netloc or parsed.path.split('/')[0]
        
        return None
    
    async def _rate_limited_get(self, url: str) -> Optional[str]:
        """Fetch URL with rate limiting per domain."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            
            # Rate limit per domain
            now = asyncio.get_event_loop().time()
            last_request = self._domain_last_request.get(domain, 0)
            if now - last_request < REQUEST_DELAY:
                await asyncio.sleep(REQUEST_DELAY - (now - last_request))
            
            response = await self.http_client.get(url)
            self._domain_last_request[domain] = asyncio.get_event_loop().time()
            
            if response.status_code == 200:
                return response.text
            else:
                logger.warning(f"Failed to fetch {url}: {response.status_code}")
                return None
                
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
            return None
    
    def _extract_text_from_html(self, html: str, max_chars: int = 15000) -> str:
        """Extract readable text from HTML, focusing on main content."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove script, style, nav, footer, header elements
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript']):
            tag.decompose()
        
        # Try to find main content
        main_content = soup.find('main') or soup.find('article') or soup.find('div', {'class': re.compile(r'content|main|body', re.I)})
        if main_content:
            text = main_content.get_text(separator=' ', strip=True)
        else:
            text = soup.get_text(separator=' ', strip=True)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text[:max_chars]
    
    def _find_interesting_pages(self, html: str, base_url: str) -> List[str]:
        """Find links to interesting pages (about, blog, news, careers)."""
        soup = BeautifulSoup(html, 'html.parser')
        interesting_patterns = [
            r'/about', r'/team', r'/blog', r'/news', r'/press', 
            r'/careers', r'/jobs', r'/product', r'/solutions',
            r'/company', r'/story', r'/mission'
        ]
        
        interesting_urls = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            # Make absolute URL
            full_url = urljoin(base_url, href)
            
            # Check if it matches interesting patterns
            for pattern in interesting_patterns:
                if re.search(pattern, href, re.I):
                    if full_url not in interesting_urls:
                        interesting_urls.append(full_url)
                    break
        
        return interesting_urls[:MAX_PAGES_PER_DOMAIN]
    
    def _analyze_with_llm(self, text: str, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to extract structured insights from crawled text."""
        company = lead.get('company', 'Unknown')
        title = lead.get('title', '')
        name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
        
        prompt = f"""Analyze this company website and extract information for a cold email.
We're selling senior engineering services. Extract ONLY what's explicitly stated.

Company: {company}
Contact: {name} ({title})

Website Content:
{text[:8000]}

**YOUR JOB:** Extract info that helps us write a human cold email.

1. WHAT_THEY_DO: One clear sentence about their core product/service (not marketing fluff)
2. THEIR_SPACE: What industry/vertical are they in? (e.g., "construction tech", "HR automation", "fintech")
3. LIKELY_CHALLENGES: Based on what they do, what engineering challenges probably keep them up at night?
   - Think: scaling, shipping speed, technical debt, hiring, legacy systems, etc.
   - Be SPECIFIC to their space, not generic
4. RECENT_NEWS: Any recent funding, launches, partnerships (only if explicitly mentioned)
5. HIRING_SIGNALS: Are they hiring engineers? What types?
6. COMPANY_STAGE: Startup stage if mentioned (seed, Series A/B/C, growth, enterprise)

**CRITICAL - CONVERSATION STARTERS:**
Write 2-3 ways we could START a cold email that:
- Sound curious, not creepy ("curious about X" not "been checking your site")
- Reference what they do WITHOUT being stalker-ish
- Could lead naturally into engineering challenges

BAD: "been checking {company}'s AI-powered infrastructure work" (sounds like stalking)
GOOD: "{company} is doing interesting stuff in construction tech" (genuine curiosity)
GOOD: "saw {company} is tackling [problem space]" (natural observation)

Respond in JSON:
{{
    "what_they_do": "One sentence - what does {company} actually do?",
    "their_space": "industry/vertical in 2-3 words",
    "likely_challenges": "Engineering challenges specific to their space",
    "recent_news": "Recent announcements or 'none found'",
    "hiring_signals": "Hiring info or 'unknown'",
    "company_stage": "Stage or 'unknown'",
    "conversation_starters": [
        "Natural way to open email mentioning {company}",
        "Another natural opener"
    ],
    "pain_point_guess": "Most likely engineering pain point based on their space"
}}
"""
        
        try:
            # Use _call_llm for automatic model rotation
            content = self._call_llm(prompt, temperature=0.3, max_tokens=1000)
            
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json.loads(json_match.group())
            else:
                logger.warning("Could not parse LLM response as JSON")
                return {}
                
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return {}
    
    async def enrich_lead(self, lead: Dict[str, Any], force_refresh: bool = False) -> Dict[str, Any]:
        """
        Enrich a single lead with website data.
        
        Args:
            lead: Lead document from MongoDB
            force_refresh: If True, re-crawl even if recently enriched
            
        Returns:
            Enrichment data dict
        """
        lead_id = lead.get('_id')
        
        # Check if already enriched recently (within 7 days)
        enrichment = lead.get('enrichment', {})
        last_enriched = enrichment.get('enriched_at')
        if last_enriched and not force_refresh:
            if isinstance(last_enriched, str):
                last_enriched = datetime.fromisoformat(last_enriched)
            if datetime.utcnow() - last_enriched < timedelta(days=7):
                logger.info(f"Lead {lead_id} already enriched recently, skipping")
                return enrichment
        
        # Get company domain
        domain = self._get_company_domain(lead)
        if not domain:
            logger.warning(f"Could not determine domain for lead {lead_id}")
            return {"error": "no_domain", "enriched_at": datetime.utcnow().isoformat()}
        
        base_url = f"https://{domain}"
        logger.info(f"Enriching lead {lead_id} from {base_url}")
        
        # Crawl homepage
        homepage_html = await self._rate_limited_get(base_url)
        if not homepage_html:
            return {"error": "fetch_failed", "enriched_at": datetime.utcnow().isoformat()}
        
        # Extract text from homepage
        all_text = self._extract_text_from_html(homepage_html)
        
        # Find and crawl interesting pages
        interesting_pages = self._find_interesting_pages(homepage_html, base_url)
        for page_url in interesting_pages[:3]:  # Limit to 3 additional pages
            page_html = await self._rate_limited_get(page_url)
            if page_html:
                page_text = self._extract_text_from_html(page_html, max_chars=5000)
                all_text += f"\n\n--- {page_url} ---\n{page_text}"
        
        # Analyze with LLM
        insights = self._analyze_with_llm(all_text, lead)
        
        # Build enrichment data
        enrichment_data = {
            "domain": domain,
            "enriched_at": datetime.utcnow().isoformat(),
            "pages_crawled": 1 + len([p for p in interesting_pages[:3]]),
            "insights": insights,
            "personalization_hooks": insights.get("personalization_hooks", []),
            "tech_stack": insights.get("tech_stack", []),
            "company_stage": insights.get("company_stage", "unknown"),
            "hiring_signals": insights.get("hiring_signals", "unknown"),
            "recent_news": insights.get("recent_news", "unknown"),
            "raw_text_hash": hashlib.md5(all_text.encode()).hexdigest()[:8]
        }
        
        # Update lead in database
        if lead_id:
            leads_collection.update_one(
                {"_id": lead_id},
                {"$set": {"enrichment": enrichment_data}}
            )
            logger.info(f"Updated lead {lead_id} with enrichment data")
        
        return enrichment_data
    
    async def enrich_batch(self, limit: int = 50, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Enrich a batch of leads that haven't been enriched recently.
        
        Args:
            limit: Maximum number of leads to enrich
            force_refresh: If True, re-enrich all leads
            
        Returns:
            Summary of enrichment results
        """
        # Find leads to enrich
        query = {}
        if not force_refresh:
            # Find leads without enrichment or with old enrichment
            cutoff = datetime.utcnow() - timedelta(days=7)
            query = {
                "$or": [
                    {"enrichment": {"$exists": False}},
                    {"enrichment.enriched_at": {"$lt": cutoff.isoformat()}},
                    {"enrichment.error": {"$exists": True}}
                ]
            }
        
        leads = list(leads_collection.find(query).limit(limit))
        logger.info(f"Found {len(leads)} leads to enrich")
        
        results = {
            "total": len(leads),
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "errors": []
        }
        
        for lead in leads:
            try:
                enrichment = await self.enrich_lead(lead, force_refresh)
                if enrichment.get("error"):
                    results["failed"] += 1
                    results["errors"].append({
                        "lead_id": str(lead.get("_id")),
                        "error": enrichment.get("error")
                    })
                else:
                    results["success"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({
                    "lead_id": str(lead.get("_id")),
                    "error": str(e)
                })
                logger.error(f"Error enriching lead {lead.get('_id')}: {e}")
        
        return results


def enrich_lead_sync(lead: Dict[str, Any], force_refresh: bool = False) -> Dict[str, Any]:
    """
    Synchronous wrapper to enrich a single lead.
    Use this from non-async code (like campaign_manager).
    
    Args:
        lead: Lead document from MongoDB
        force_refresh: If True, re-crawl even if recently enriched
        
    Returns:
        Enrichment data dict
    """
    async def _enrich():
        enricher = LeadEnricher()
        try:
            return await enricher.enrich_lead(lead, force_refresh)
        finally:
            await enricher.close()
    
    return asyncio.run(_enrich())


def get_enrichment_for_email(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get enrichment data formatted for email generation.
    
    Returns a dict with:
    - conversation_starters: Natural ways to open the email
    - what_they_do: One-liner about the company
    - their_space: Industry/vertical
    - pain_point_guess: Likely engineering pain based on their space
    - company_context: Stage, hiring signals
    """
    enrichment = lead.get('enrichment', {})
    
    if not enrichment or enrichment.get('error'):
        return {
            "has_enrichment": False,
            "conversation_starters": [],
            "what_they_do": None,
            "their_space": None,
            "pain_point_guess": None,
            "company_context": {}
        }
    
    insights = enrichment.get('insights', {})
    
    # Get conversation starters (the new field)
    conversation_starters = insights.get('conversation_starters', [])
    
    # Fallback to old format if new fields not present
    if not conversation_starters:
        hooks = insights.get('personalization_hooks', [])
        if hooks:
            conversation_starters = hooks
    
    return {
        "has_enrichment": True,
        "conversation_starters": conversation_starters,
        "what_they_do": insights.get('what_they_do'),
        "their_space": insights.get('their_space'),
        "pain_point_guess": insights.get('pain_point_guess') or insights.get('likely_challenges'),
        "company_context": {
            "stage": insights.get('company_stage') or enrichment.get('company_stage'),
            "hiring": insights.get('hiring_signals') or enrichment.get('hiring_signals'),
            "recent_news": insights.get('recent_news')
        }
    }


async def enrich_leads_cli(limit: int = 50, force: bool = False):
    """CLI entry point for batch enrichment."""
    enricher = LeadEnricher()
    try:
        results = await enricher.enrich_batch(limit=limit, force_refresh=force)
        print(f"\n=== Enrichment Results ===")
        print(f"Total: {results['total']}")
        print(f"Success: {results['success']}")
        print(f"Failed: {results['failed']}")
        if results['errors']:
            print(f"\nErrors:")
            for err in results['errors'][:5]:
                print(f"  - {err['lead_id']}: {err['error']}")
    finally:
        await enricher.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Enrich leads with website data")
    parser.add_argument("--limit", type=int, default=50, help="Max leads to enrich")
    parser.add_argument("--force", action="store_true", help="Force re-enrichment")
    
    args = parser.parse_args()
    
    asyncio.run(enrich_leads_cli(limit=args.limit, force=args.force))
