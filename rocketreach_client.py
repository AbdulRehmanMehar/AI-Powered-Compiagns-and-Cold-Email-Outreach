import requests
from typing import List, Dict, Any, Optional
import config
import time
import re


def is_valid_email(email: str) -> bool:
    """Check if email is a valid format (has @ and domain)"""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


class RocketReachClient:
    """Client for RocketReach API to fetch leads"""
    
    BASE_URL = "https://api.rocketreach.co/v2/api"
    
    def __init__(self):
        self.api_key = config.ROCKETREACH_API_KEY
        self.headers = {
            "Api-Key": self.api_key,
            "Content-Type": "application/json"
        }
    
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
        Fetch leads based on criteria and get their emails
        
        Args:
            criteria: Search criteria dict with keys like:
                - current_title: List of job titles
                - current_employer: List of companies
                - location: List of locations
                - industry: List of industries
            max_leads: Maximum number of leads to fetch
            exclude_emails: Set of email addresses to skip (already contacted)
        
        Returns:
            List of leads with email addresses
        """
        leads = []
        start = 1
        page_size = min(25, max_leads)
        exclude_emails = {e.lower() for e in (exclude_emails or set())}
        skipped_existing = 0
        
        while len(leads) < max_leads:
            # Search for people - map campaign criteria keys to RocketReach API keys
            search_results = self.search_people(
                current_title=criteria.get("current_title") or criteria.get("titles"),  # Support both keys
                current_employer=criteria.get("current_employer"),
                location=criteria.get("location"),
                industry=criteria.get("industry") or criteria.get("industries"),  # Support both keys
                keywords=criteria.get("keywords"),
                page_size=page_size,
                start=start
            )
            
            profiles = search_results.get("profiles", [])
            
            if not profiles:
                break
            
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
                        email = emails[0] if isinstance(emails[0], str) else emails[0].get("email")
                        
                        # Skip if already contacted (check BEFORE adding)
                        if email and email.lower() in exclude_emails:
                            skipped_existing += 1
                            continue
                        
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
            pagination = search_results.get("pagination", {})
            total = pagination.get("total", 0)
            if start > total:
                break
        
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
