import requests
from typing import List, Dict, Any, Optional
import config
import time
import re
import socket
import smtplib
import random


def is_valid_email(email: str) -> bool:
    """Check if email is a valid format (has @ and domain)"""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def check_mx_records(domain: str, timeout: int = 5) -> bool:
    """Check if domain has valid MX records"""
    try:
        import dns.resolver
        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout
        resolver.lifetime = timeout
        records = resolver.resolve(domain, 'MX')
        return len(list(records)) > 0
    except ImportError:
        # dnspython not installed, skip MX check
        return True
    except:
        return False


def get_bounced_domains() -> set:
    """Get domains that have bounced from our database"""
    try:
        from database import db
        bounced_emails = db.emails.distinct("recipient_email", {"status": "bounced"})
        domains = {email.split('@')[1].lower() for email in bounced_emails if '@' in email}
        return domains
    except Exception:
        return set()


# Cache bounced domains (refreshed every time module loads)
_BOUNCED_DOMAINS_CACHE = None


def get_cached_bounced_domains() -> set:
    """Get cached bounced domains (loads once per session)"""
    global _BOUNCED_DOMAINS_CACHE
    if _BOUNCED_DOMAINS_CACHE is None:
        _BOUNCED_DOMAINS_CACHE = get_bounced_domains()
    return _BOUNCED_DOMAINS_CACHE


def refresh_bounced_domains_cache():
    """Refresh the bounced domains cache"""
    global _BOUNCED_DOMAINS_CACHE
    _BOUNCED_DOMAINS_CACHE = get_bounced_domains()


def quick_email_check(email: str, check_mx: bool = True, check_bounced_domains: bool = True) -> tuple:
    """
    Quick email validation with comprehensive checks.
    Returns (is_valid, reason)
    
    Checks performed:
    1. Syntax validation
    2. Disposable domain detection
    3. Role-based email detection  
    4. Problematic TLD detection
    5. Known bounced domain detection
    6. Large company domain detection (high bounce risk for cold outreach)
    7. MX record verification
    """
    if not email:
        return False, "Empty email"
    
    email = email.lower().strip()
    
    # Basic syntax check
    if not is_valid_email(email):
        return False, "Invalid syntax"
    
    local_part, domain = email.rsplit('@', 1)
    
    # Check for disposable domains
    disposable_domains = {
        'tempmail.com', 'throwaway.email', 'guerrillamail.com', 'mailinator.com',
        '10minutemail.com', 'temp-mail.org', 'fakeinbox.com', 'trashmail.com',
        'yopmail.com', 'getnada.com', 'maildrop.cc', 'dispostable.com',
        'sharklasers.com', 'getairmail.com', 'emailondeck.com', 'tempr.email'
    }
    if domain in disposable_domains:
        return False, "Disposable domain"
    
    # Check for role-based emails (often bounce or go to team inboxes)
    role_prefixes = {
        'info', 'support', 'admin', 'contact', 'hello', 'sales', 'team', 
        'office', 'hr', 'jobs', 'careers', 'marketing', 'press', 'media',
        'help', 'service', 'billing', 'webmaster', 'postmaster', 'abuse',
        'noreply', 'no-reply', 'donotreply', 'newsletter', 'enquiries',
        'inquiries', 'orders', 'feedback', 'privacy', 'legal'
    }
    if any(local_part == prefix or local_part.startswith(f"{prefix}.") for prefix in role_prefixes):
        return False, "Role-based email"
    
    # Check for suspicious patterns
    # Too many numbers = likely auto-generated
    digit_ratio = sum(c.isdigit() for c in local_part) / len(local_part) if local_part else 0
    if digit_ratio > 0.6:
        return False, "Too many digits (likely auto-generated)"
    
    # Very short local parts are risky (high bounce rate from our data)
    if len(local_part) < 4:
        return False, f"Local part too short ({len(local_part)} chars)"
    
    # Check for known problematic TLDs (expanded list based on bounce data)
    problematic_tlds = {'.ir', '.ru', '.cn', '.in', '.br', '.bt', '.pk', '.bd', '.ng'}
    if any(domain.endswith(tld) for tld in problematic_tlds):
        return False, f"Problematic TLD (high bounce rate)"
    
    # Check against domains that have bounced before in our system
    if check_bounced_domains:
        bounced_domains = get_cached_bounced_domains()
        if domain in bounced_domains:
            return False, f"Domain has bounced before ({domain})"
    
    # Check for large company domains (high bounce rate for cold outreach - employees change frequently)
    # These domains often accept email (catch-all) but then bounce later
    large_company_domains = {
        'google.com', 'microsoft.com', 'apple.com', 'amazon.com', 'meta.com',
        'facebook.com', 'netflix.com', 'uber.com', 'airbnb.com', 'twitter.com',
        'salesforce.com', 'oracle.com', 'ibm.com', 'intel.com', 'adobe.com',
        'vmware.com', 'cisco.com', 'dell.com', 'hp.com', 'sap.com',
        'linkedin.com', 'coinbase.com', 'stripe.com', 'square.com', 'paypal.com',
        'upwork.com', 'fiverr.com'
    }
    if domain in large_company_domains:
        return False, f"Large company domain (high bounce risk): {domain}"
    
    # Check MX records (most important check!)
    if check_mx:
        if not check_mx_records(domain):
            return False, "No MX records (domain cannot receive email)"
    
    return True, "OK"


def get_mx_host(domain: str, timeout: int = 5) -> Optional[str]:
    """Get the primary MX host for a domain"""
    try:
        import dns.resolver
        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout
        resolver.lifetime = timeout
        records = resolver.resolve(domain, 'MX')
        # Return highest priority (lowest preference number) MX host
        mx_host = str(sorted(records, key=lambda x: x.preference)[0].exchange).rstrip('.')
        return mx_host
    except:
        return None


def verify_email_smtp(email: str, timeout: int = 10) -> tuple:
    """
    Verify email via SMTP - checks if the mailbox actually exists.
    This is FREE but slower (~1-5 seconds per email).
    
    Returns (is_valid, reason)
    
    Possible outcomes:
    - (True, "OK") - Mailbox exists
    - (True, "Catch-all domain") - Domain accepts all emails (risky but valid)
    - (False, "Mailbox does not exist") - SMTP rejected the address
    - (None, "Could not verify") - Server blocked verification
    """
    email = email.lower().strip()
    
    try:
        domain = email.split('@')[1]
    except:
        return False, "Invalid email format"
    
    # Get MX host
    mx_host = get_mx_host(domain, timeout=5)
    if not mx_host:
        return False, "No MX records"
    
    try:
        # Connect to SMTP server
        smtp = smtplib.SMTP(timeout=timeout)
        smtp.connect(mx_host, 25)
        smtp.helo('verify.primestrides.com')
        
        # Set sender
        smtp.mail('verify@primestrides.com')
        
        # Check if recipient mailbox exists
        code, message = smtp.rcpt(email)
        
        if code == 250:
            # Accepted! But check if it's a catch-all domain
            # by testing a random invalid email
            random_email = f"definitely_invalid_{random.randint(100000, 999999)}@{domain}"
            catch_code, _ = smtp.rcpt(random_email)
            
            smtp.quit()
            
            if catch_code == 250:
                return True, "Catch-all domain (accepts all emails)"
            return True, "OK"
        
        elif code in [550, 551, 552, 553, 554]:
            # Mailbox doesn't exist
            smtp.quit()
            return False, f"Mailbox does not exist (SMTP {code})"
        
        else:
            # Uncertain response
            smtp.quit()
            return None, f"Uncertain SMTP response: {code}"
            
    except smtplib.SMTPServerDisconnected:
        return None, "Server disconnected"
    except smtplib.SMTPConnectError:
        return None, "Could not connect to mail server"
    except socket.timeout:
        return None, "Connection timeout"
    except Exception as e:
        return None, f"SMTP error: {str(e)[:50]}"


def full_email_verification(email: str, use_smtp: bool = True) -> tuple:
    """
    Complete email verification with all checks including SMTP.
    
    Returns (is_valid, reason, details)
    - is_valid: True/False/None (None = couldn't verify)
    - reason: Human-readable explanation
    - details: Dict with check results
    """
    details = {
        'email': email,
        'checks_passed': [],
        'checks_failed': [],
    }
    
    # First do quick checks (fast)
    is_valid, reason = quick_email_check(email, check_mx=True)
    
    if not is_valid:
        details['checks_failed'].append(('quick_check', reason))
        return False, reason, details
    
    details['checks_passed'].append('quick_check')
    
    # Then do SMTP verification (slow but most accurate)
    if use_smtp:
        smtp_valid, smtp_reason = verify_email_smtp(email)
        
        if smtp_valid is False:
            details['checks_failed'].append(('smtp', smtp_reason))
            return False, smtp_reason, details
        elif smtp_valid is True:
            details['checks_passed'].append('smtp')
            if "Catch-all" in smtp_reason:
                details['warning'] = smtp_reason
        else:
            # Couldn't verify via SMTP - still allow but flag it
            details['warning'] = f"SMTP verification inconclusive: {smtp_reason}"
    
    return True, "Email verified", details


class RocketReachClient:
    """Client for RocketReach API to fetch leads"""
    
    BASE_URL = "https://api.rocketreach.co/v2/api"
    
    def __init__(self, verify_emails: bool = None):
        """
        Args:
            verify_emails: If True, verify emails before accepting (reduces bounces)
                          If None, uses config.VERIFY_EMAILS
        """
        self.api_key = config.ROCKETREACH_API_KEY
        self.headers = {
            "Api-Key": self.api_key,
            "Content-Type": "application/json"
        }
        self.verify_emails = verify_emails if verify_emails is not None else getattr(config, 'VERIFY_EMAILS', True)
    
    def search_people(self, 
                      query: str = None,
                      name: str = None,
                      current_title: List[str] = None,
                      current_employer: List[str] = None,
                      location: List[str] = None,
                      industry: List[str] = None,
                      keywords: List[str] = None,
                      page_size: int = 10,
                      start: int = 1) -> Dict[str, Any]:
        """
        Search for people on RocketReach
        
        Args:
            query: General search query
            name: Person's name
            current_title: List of job titles to filter by
            current_employer: List of company names
            location: List of locations
            industry: List of industries
            keywords: List of keywords
            page_size: Number of results per page (max 100)
            start: Starting position for pagination
        
        Returns:
            Dict with profiles and pagination info
        """
        endpoint = f"{self.BASE_URL}/search"
        
        payload = {
            "start": start,
            "page_size": min(page_size, 100)
        }
        
        # Build query parameters
        query_params = {}
        
        if query:
            query_params["query"] = query
        if name:
            query_params["name"] = [name]
        if current_title:
            query_params["current_title"] = current_title if isinstance(current_title, list) else [current_title]
        if current_employer:
            query_params["current_employer"] = current_employer if isinstance(current_employer, list) else [current_employer]
        if location:
            query_params["location"] = location if isinstance(location, list) else [location]
        if industry:
            query_params["industry"] = industry if isinstance(industry, list) else [industry]
        if keywords:
            query_params["keyword"] = keywords if isinstance(keywords, list) else [keywords]
        
        if query_params:
            payload["query"] = query_params
        
        try:
            response = requests.post(endpoint, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error searching RocketReach: {e}")
            return {"profiles": [], "error": str(e)}
    
    def lookup_person(self, 
                      profile_id: int = None,
                      name: str = None,
                      current_employer: str = None,
                      linkedin_url: str = None,
                      email: str = None) -> Optional[Dict[str, Any]]:
        """
        Look up a specific person to get their contact info
        
        Args:
            profile_id: RocketReach profile ID
            name: Person's name
            current_employer: Company name
            linkedin_url: LinkedIn profile URL
            email: Email address
        
        Returns:
            Person's profile with contact information
        """
        endpoint = f"{self.BASE_URL}/lookupProfile"
        
        payload = {}
        
        if profile_id:
            payload["id"] = profile_id
        if name:
            payload["name"] = name
        if current_employer:
            payload["current_employer"] = current_employer
        if linkedin_url:
            payload["linkedin_url"] = linkedin_url
        if email:
            payload["email"] = email
        
        try:
            response = requests.get(endpoint, params=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error looking up person: {e}")
            return None
    
    def get_person_with_email(self, profile_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a person's profile including their email
        Uses the lookup endpoint to retrieve full contact info
        """
        result = self.lookup_person(profile_id=profile_id)
        
        if result and result.get("status") == "complete":
            return result
        elif result and result.get("status") == "searching":
            # Wait and retry if still searching
            time.sleep(2)
            return self.lookup_person(profile_id=profile_id)
        
        return result
    
    def fetch_leads(self,
                    criteria: Dict[str, Any],
                    max_leads: int = 50,
                    exclude_emails: set = None) -> List[Dict[str, Any]]:
        """
        Fetch leads based on criteria and get their emails.
        
        Uses SearchOffsetTracker to remember where we left off, so we don't
        keep getting the same people every search.
        
        Args:
            criteria: Search criteria dict with keys like:
                - current_title: List of job titles
                - current_employer: List of companies
                - location: List of locations
                - keywords: List of keywords (used instead of industry for broader results)
            max_leads: Maximum number of leads to fetch
            exclude_emails: Set of email addresses to skip (already contacted)
        
        Returns:
            List of leads with email addresses
        """
        from database import SearchOffsetTracker
        
        leads = []
        page_size = min(25, max_leads)
        exclude_emails = {e.lower() for e in (exclude_emails or set())}
        skipped_existing = 0
        
        # Get the starting offset from tracker (continues from where we left off)
        start = SearchOffsetTracker.get_next_offset(criteria)
        initial_start = start
        print(f"   📍 Starting RocketReach search from offset {start}")
        
        while len(leads) < max_leads:
            # Search for people - map campaign criteria keys to RocketReach API keys
            search_results = self.search_people(
                current_title=criteria.get("current_title") or criteria.get("titles"),  # Support both keys
                current_employer=criteria.get("current_employer"),
                location=criteria.get("location"),
                industry=criteria.get("industry") or criteria.get("industries"),  # Support both keys (but prefer keywords)
                keywords=criteria.get("keywords"),
                page_size=page_size,
                start=start
            )
            
            profiles = search_results.get("profiles", [])
            pagination = search_results.get("pagination", {})
            total_available = pagination.get("total", 0)
            
            if not profiles:
                print(f"   ⚠️  No more profiles found at offset {start}")
                break
            
            print(f"   🔍 Searching offset {start}-{start+len(profiles)} (total available: {total_available})")
            
            # Get detailed info for each profile
            for profile in profiles:
                if len(leads) >= max_leads:
                    break
                
                profile_id = profile.get("id")
                
                # Check teaser email first to avoid wasting lookup credits
                teaser_emails = profile.get("teaser", {}).get("emails", [])
                if teaser_emails:
                    teaser_domain = teaser_emails[0] if isinstance(teaser_emails[0], str) else teaser_emails[0].get("email", "")
                    # If we can check domain against exclude list, skip early
                    # (teaser only has domain, but we can check if any excluded email has this domain)
                
                # Always do a full lookup to get actual email address
                # Search results only contain teaser data (domains, not full emails)
                detailed = self.get_person_with_email(profile_id)
                
                if detailed:
                    # Check various email fields
                    emails = detailed.get("emails", []) or detailed.get("current_personal_email", []) or detailed.get("professional_emails", [])
                    
                    if emails:
                        # CRITICAL: Use RocketReach's pre-validated email data!
                        # Pick the BEST email based on RocketReach's smtp_valid and grade
                        email = None
                        email_data = None
                        
                        for e in emails:
                            if isinstance(e, str):
                                email = e
                                break
                            else:
                                e_addr = e.get("email")
                                e_valid = e.get("smtp_valid", "").lower()
                                e_grade = e.get("grade", "F")
                                
                                # Skip explicitly invalid emails from RocketReach
                                if e_valid == "invalid":
                                    print(f"   ⚠️ Skipping {e_addr} - RocketReach marked invalid (grade: {e_grade})")
                                    continue
                                
                                # Skip F-grade emails
                                if e_grade == "F":
                                    print(f"   ⚠️ Skipping {e_addr} - RocketReach grade F")
                                    continue
                                
                                # Prefer valid emails, then inconclusive, skip invalid
                                if e_valid == "valid":
                                    email = e_addr
                                    email_data = e
                                    break
                                elif e_valid in ("inconclusive", "unknown", "") and email is None:
                                    # Use inconclusive only if no valid found yet
                                    email = e_addr
                                    email_data = e
                        
                        if not email:
                            print(f"   ⚠️ No valid emails found for {profile.get('name')} - all marked invalid by RocketReach")
                            continue
                        
                        # Skip if already contacted (check BEFORE adding)
                        if email and email.lower() in exclude_emails:
                            skipped_existing += 1
                            continue
                        
                        # VERIFY EMAIL before accepting (reduces bounces)
                        # Only do our own SMTP check if RocketReach didn't already validate it
                        if self.verify_emails:
                            # Quick checks first (instant)
                            is_valid, reason = quick_email_check(email)
                            if not is_valid:
                                print(f"   ⚠️ Skipping {email} - {reason}")
                                continue
                            
                            # SMTP verification (slower but catches remaining bounces)
                            if getattr(config, 'VERIFY_SMTP', True):
                                smtp_valid, smtp_reason = verify_email_smtp(email, timeout=10)
                                if smtp_valid is False:
                                    print(f"   ⚠️ Skipping {email} - SMTP: {smtp_reason}")
                                    continue
                                elif smtp_valid is True and "Catch-all" in smtp_reason:
                                    print(f"   ⚡ Warning: {email} - {smtp_reason}")
                        
                        if is_valid_email(email):
                            profile["email"] = email
                            profile.update(detailed)
                            leads.append(profile)
                            print(f"   ✓ Found: {profile.get('name')} - {email}")
                        else:
                            print(f"   ⚠️ Invalid email format: {email} - skipping")
                    else:
                        print(f"   ⚠️ No email found for {profile.get('name')} - skipping")
                
                # Rate limiting
                time.sleep(0.5)
            
            start += page_size
            
            # Check if we've exhausted results
            if start > total_available:
                print(f"   📊 Reached end of results (total: {total_available})")
                # Reset to beginning for next time (circular search)
                SearchOffsetTracker.update_offset(criteria, 1, total_available)
                break
        
        # Save where we left off for next search
        if start != initial_start:
            SearchOffsetTracker.update_offset(criteria, start, total_available if 'total_available' in dir() else None)
            print(f"   💾 Saved search offset: {start} for next time")
        
        if skipped_existing > 0:
            print(f"   ⏭️  Skipped {skipped_existing} already-contacted leads during search")
        
        return leads
    
    def check_credits(self) -> Dict[str, Any]:
        """Check remaining API credits"""
        endpoint = f"{self.BASE_URL}/account"
        
        try:
            response = requests.get(endpoint, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error checking credits: {e}")
            return {"error": str(e)}


# Example usage
if __name__ == "__main__":
    client = RocketReachClient()
    
    # Check credits
    print("Checking credits...")
    credits = client.check_credits()
    print(f"Credits: {credits}")
    
    # Example search
    criteria = {
        "current_title": ["CEO", "Founder", "CTO"],
        "location": ["United States"],
        "industry": ["Technology"]
    }
    
    print("\nSearching for leads...")
    leads = client.fetch_leads(criteria, max_leads=5)
    
    for lead in leads:
        print(f"- {lead.get('name')} | {lead.get('current_title')} @ {lead.get('current_employer')} | {lead.get('email')}")
