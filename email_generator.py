"""
Cold Email Generator - Aligned with Expert Strategies
Based on: Eric Nowoslawski's 90-page doc, LeadGenJay's masterclass

Key principles:
1. Subject lines should look like they're from a colleague/friend
2. First line = preview text, must create curiosity NOT pitch
3. Keep emails ULTRA short (under 100 words, 75 better)
4. 2 email sequence max (3rd only if NEW thread with different angle)
5. Use spintax for variation
6. Specific case studies with real numbers (3.72x not 4x)
7. What can you say that NO ONE else can say?
8. Problem sniffing - AI finds specific issues before emailing
"""

from openai import OpenAI
from typing import Dict, Any, List, Optional
import config
import json
import random
import re
from primestrides_context import COMPANY_CONTEXT, ICP_TEMPLATES, EMAIL_CONTEXT, CASE_STUDIES, SPINTAX_TEMPLATES


class EmailGenerator:
    """Generate personalized cold emails using expert strategies"""
    
    def __init__(self):
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.model = "gpt-4o"
        self.company_context = COMPANY_CONTEXT
        self.email_context = EMAIL_CONTEXT
        self.case_studies = CASE_STUDIES
    
    def determine_icp_and_criteria(self, campaign_description: str) -> Dict[str, Any]:
        """
        Use AI to determine the best ICP and RocketReach search criteria
        based on a simple campaign description
        """
        
        icp_options = json.dumps(ICP_TEMPLATES, indent=2)
        case_study_options = json.dumps(CASE_STUDIES, indent=2)
        
        system_prompt = f"""You are an expert at B2B sales targeting and cold email strategy.
You work for PrimeStrides, a boutique software agency.

{self.company_context}

Given a campaign description, determine:
1. The best target audience (be SPECIFIC - "tech founder" is bad, "SaaS founder who just raised seed funding" is good)
2. RocketReach search criteria
3. The ONE specific pain point to focus on (not a list - ONE)
4. The unique angle that ONLY PrimeStrides can claim
5. Which case study is most relevant

Available ICP templates:
{icp_options}

Available case studies (USE REAL NAMES AND NUMBERS):
{case_study_options}

Return JSON:
{{
    "campaign_name": "descriptive name",
    "target_description": "hyper-specific who and why",
    "search_criteria": {{
        "current_title": ["title1", "title2"],
        "industry": ["industry1", "industry2"],
        "location": ["United States"]
    }},
    "campaign_context": {{
        "product_service": "specific offer for this audience",
        "single_pain_point": "THE ONE pain point we address",
        "unique_angle": "what can WE say that no one else can?",
        "case_study": {{
            "company_name": "real company name",
            "result": "specific result with decimals",
            "timeline": "specific timeline",
            "quote": "optional real quote from client"
        }},
        "front_end_offer": "low-friction offer like free audit, checklist, etc.",
        "trigger_signal": "what triggered this outreach (hiring, funding, etc.)"
    }}
}}"""

        user_prompt = f"""Campaign description: {campaign_description}

Create hyper-targeted campaign for PrimeStrides. Remember:
- ONE pain point, not a list
- Specific case study with REAL numbers
- What can we say that NO ONE else can say?"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
        except Exception as e:
            print(f"Error determining ICP: {e}")
            return self._fallback_icp(campaign_description)
    
    def _fallback_icp(self, description: str) -> Dict:
        """Fallback ICP if AI fails"""
        return {
            "campaign_name": description,
            "target_description": "Startup founders needing dev help",
            "search_criteria": {
                "current_title": ["CEO", "Founder", "CTO"],
                "industry": ["Technology", "Software", "SaaS"],
                "location": ["United States"]
            },
            "campaign_context": {
                "product_service": "senior engineering team for 8-week sprints",
                "single_pain_point": "can't ship fast enough with current team",
                "unique_angle": "we shipped RoboApply's entire AI system in 8 weeks - their CTO said he'd never use another agency",
                "case_study": CASE_STUDIES["roboapply"],
                "front_end_offer": "free 30-min architecture review",
                "trigger_signal": "actively building/scaling product"
            }
        }
    
    def generate_initial_email(self, 
                               lead: Dict[str, Any],
                               campaign_context: Dict[str, Any],
                               tone: str = "casual") -> Dict[str, str]:
        """
        Generate a personalized initial cold email following expert strategies
        
        Key rules from Eric/Jay:
        - Subject: 2-3 words, looks like it's from a colleague
        - First line: Preview text, creates CURIOSITY, not a pitch
        - Under 75-100 words total
        - ONE pain point
        - Specific case study
        - Soft CTA (not "schedule a call")
        """
        
        case_study = campaign_context.get("case_study", CASE_STUDIES["roboapply"])
        
        system_prompt = f"""You are a cold email expert. Write emails that get opened and replied to.

CRITICAL RULES (from top cold email experts):

**SUBJECT LINE:**
- 2-4 words MAX
- Must look like it's from a colleague or friend
- NO: "Quick question", "Partnership", "Intro", "[Company] + [Company]"
- YES: "{{first_name}}?", "thought about this", "re: {{company}}", "saw something"

**FIRST LINE (this is the preview text - most important!):**
- Must create CURIOSITY
- Must NOT sound like a pitch
- NO: "I noticed your company...", "I'm reaching out because...", "My name is..."
- YES: "saw something interesting on {{company}}'s site", "random question", "this might be off base but"

**BODY:**
- Under 75 words total (entire email)
- ONE pain point only
- Include specific case study: {case_study.get('company_name')} - {case_study.get('result')} in {case_study.get('timeline')}
- Sound like a human, not a template
- 6th grade reading level, no jargon

**CTA:**
- Super soft, low friction
- NO: "Let's schedule a call", "Are you free Tuesday?"
- YES: "worth a quick chat?", "make sense to connect?", "open to hearing more?"

**DO NOT:**
- Use "I hope this finds you well"
- Say "reaching out" or "touching base"
- List multiple services
- Use corporate buzzwords (leverage, synergy, streamline)
- Write more than 4-5 sentences
- Sound salesy or desperate

Return JSON with "subject" and "body" keys only."""

        # Build lead context
        first_name = lead.get('first_name', 'there')
        company = lead.get('company', 'your company')
        title = lead.get('title', '')
        industry = lead.get('industry', '')

        user_prompt = f"""RECIPIENT:
- First Name: {first_name}
- Title: {title}
- Company: {company}
- Industry: {industry}

CAMPAIGN:
- Pain point to address: {campaign_context.get('single_pain_point', 'shipping product faster')}
- Our unique angle: {campaign_context.get('unique_angle', 'senior engineers who write code, no offshore teams')}
- Case study to reference: {case_study.get('company_name')} achieved {case_study.get('result')} in {case_study.get('timeline')}
- Front-end offer if relevant: {campaign_context.get('front_end_offer', 'free architecture review')}

Write a cold email that will get opened (subject + first line create curiosity) and replied to (specific, human, helpful).
Remember: UNDER 75 WORDS, looks like it's from a colleague."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.85,  # Higher temp for more human variation
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Apply spintax variation
            subject = self._apply_spintax(result.get("subject", f"{first_name}?"))
            body = self._apply_spintax(result.get("body", ""))
            
            return {
                "subject": subject,
                "body": body
            }
        except Exception as e:
            print(f"Error generating email: {e}")
            return self._fallback_email(lead, campaign_context)
    
    def generate_followup_email(self,
                                lead: Dict[str, Any],
                                campaign_context: Dict[str, Any],
                                previous_emails: List[Dict[str, str]],
                                followup_number: int) -> Dict[str, str]:
        """
        Generate follow-up emails following expert strategy:
        
        Email 1: Initial (new thread)
        Email 2: Same thread, add value (not "just following up")
        Email 3: NEW thread, different subject, different angle (optional)
        
        Max 2-3 emails total. Short sequences = less spam complaints.
        """
        
        if followup_number == 1:
            # Email 2: Same thread, add genuine value
            return self._generate_followup_same_thread(lead, campaign_context, previous_emails)
        elif followup_number == 2:
            # Email 3: NEW thread, completely different angle
            return self._generate_followup_new_thread(lead, campaign_context, previous_emails)
        else:
            # We shouldn't send more than 3 emails (expert advice)
            return self._generate_breakup_email(lead, campaign_context, previous_emails)
    
    def _generate_followup_same_thread(self, lead: Dict, context: Dict, previous: List) -> Dict:
        """Follow-up in same thread - add value, don't just bump"""
        
        system_prompt = """You are a cold email expert writing follow-up #2.

CRITICAL RULES:
- This is a SAME THREAD reply (will show as Re: original subject)
- UNDER 50 words
- Add GENUINE VALUE - share an insight, relevant resource, or quick tip
- DO NOT say "just following up", "circling back", "bumping this"
- DO NOT guilt trip them
- Sound helpful, not desperate

GOOD examples:
- "quick thought - [relevant insight about their business]"
- "fwiw - we just published something on [topic relevant to their pain]. happy to share."
- "one more thing - [specific value add]"

BAD examples:
- "just wanted to follow up on my last email"
- "did you get a chance to see my message?"
- "I know you're busy but..."

Return JSON with "subject" and "body" keys. Subject should be "Re: [original subject]"."""

        first_name = lead.get('first_name', 'there')
        original_subject = previous[0]['subject'] if previous else "previous email"

        user_prompt = f"""RECIPIENT: {first_name} at {lead.get('company', 'their company')} ({lead.get('title', '')})

ORIGINAL EMAIL:
Subject: {original_subject}
Body: {previous[0].get('body', '')[:200] if previous else ''}

PAIN POINT: {context.get('single_pain_point', '')}

Write a short follow-up that adds genuine value. Under 50 words."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.85,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return {
                "subject": f"Re: {original_subject}",
                "body": result.get("body", "")
            }
        except Exception as e:
            print(f"Error generating follow-up: {e}")
            return {
                "subject": f"Re: {original_subject}",
                "body": self._fallback_followup_same_thread(lead)
            }
    
    def _generate_followup_new_thread(self, lead: Dict, context: Dict, previous: List) -> Dict:
        """Follow-up #3: NEW thread with completely different angle"""
        
        system_prompt = """You are a cold email expert writing follow-up #3.

CRITICAL: This is a NEW THREAD (different subject line, fresh start)

Strategy:
- Different angle/pain point than original emails
- They already ignored you twice - try something new
- Lower friction CTA (offer something valuable for free)
- Under 60 words
- Subject should be different and intriguing

This is like a fresh email but referencing you've tried to connect.

GOOD subject lines for fresh thread:
- "different thought"
- "[first_name] - one more idea"  
- "re: [something they care about]"

IMPORTANT:
- Do NOT include a signature or sign-off like "Best," or "[Your Name]"
- End with the question/CTA directly
- Keep it conversational, no formal closings

Return JSON with "subject" and "body" keys."""

        first_name = lead.get('first_name', 'there')
        company = lead.get('company', 'your company')

        user_prompt = f"""RECIPIENT: {first_name}, {lead.get('title', '')} at {company}

PREVIOUS ANGLES TRIED (don't repeat these):
{[email.get('subject', '') for email in previous]}

New angle to try: offer the free front-end offer
Front-end offer: {context.get('front_end_offer', 'free architecture review')}

Write a fresh email with different approach. New subject line, under 60 words."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.85,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return {
                "subject": result.get("subject", f"{first_name} - one more idea"),
                "body": result.get("body", ""),
                "new_thread": True  # Flag for campaign manager
            }
        except Exception as e:
            print(f"Error generating new thread follow-up: {e}")
            return {
                "subject": f"{first_name} - different thought",
                "body": self._fallback_followup_new_thread(lead, context),
                "new_thread": True
            }
    
    def _generate_breakup_email(self, lead: Dict, context: Dict, previous: List) -> Dict:
        """Final email - helpful, not guilt-tripping. Leave door open."""
        
        first_name = lead.get('first_name', 'there')
        company = lead.get('company', 'your company')
        
        # Expert advice: "Should I reach out to [other person] instead?" works well
        body = f"""{first_name} - 

last one from me. if dev capacity ever becomes a priority at {company}, happy to help.

or if I should be talking to someone else on the team, just point me in the right direction.

either way, rooting for you."""

        return {
            "subject": "closing the loop",
            "body": body,
            "new_thread": True
        }
    
    def _apply_spintax(self, text: str) -> str:
        """Apply spintax variations: {word1|word2|word3} -> random choice"""
        pattern = r'\{([^{}]+)\}'
        
        def replace_spintax(match):
            options = match.group(1).split('|')
            return random.choice(options)
        
        return re.sub(pattern, replace_spintax, text)
    
    def _fallback_email(self, lead: Dict, context: Dict) -> Dict[str, str]:
        """Fallback email if AI fails - still follows expert rules"""
        first_name = lead.get('first_name', 'there')
        company = lead.get('company', 'your company')
        case_study = context.get('case_study', CASE_STUDIES.get('roboapply', {}))
        
        body = f"""saw {company} is building some interesting stuff.

random question - struggling to ship as fast as you'd like?

we just helped {case_study.get('company_name', 'a similar company')} go from idea to production in {case_study.get('timeline', '8 weeks')} - {case_study.get('result', 'cut their timeline in half')}.

if you're facing something similar, might be worth a quick chat.

{random.choice(['cool what you are building.', 'interesting product.', 'like what I see.'])}"""
        
        return {
            "subject": f"{first_name}?",
            "body": body
        }
    
    def _fallback_followup_same_thread(self, lead: Dict) -> str:
        """Fallback follow-up in same thread"""
        first_name = lead.get('first_name', 'there')
        return f"""{first_name} - 

one thing I forgot - we just wrote up how we cut {random.choice(['RoboApply', 'StratMap', 'Timpl'])}'s deployment time by 3.2x.

might be relevant given what you're building. happy to share if useful."""
    
    def _fallback_followup_new_thread(self, lead: Dict, context: Dict) -> str:
        """Fallback new thread follow-up"""
        first_name = lead.get('first_name', 'there')
        offer = context.get('front_end_offer', 'quick architecture review')
        return f"""{first_name} - 

totally different thought. we've been offering a free {offer} for companies in your space.

takes 30 mins, you get specific feedback on your stack. no pitch, just useful.

interested?"""


# Utility function for problem sniffing (future enhancement)
def analyze_company_problems(company_url: str, client: OpenAI) -> Dict:
    """
    Future: Use AI to analyze company website and identify specific problems
    This is "problem sniffing" - finding issues before emailing
    """
    # TODO: Implement web scraping + AI analysis
    # - Check their tech stack
    # - Look for hiring signals
    # - Analyze their product for issues
    # - Check reviews/feedback
    pass


# Example usage
if __name__ == "__main__":
    generator = EmailGenerator()
    
    # Test ICP determination
    print("Testing ICP determination...")
    result = generator.determine_icp_and_criteria("target fintech startups who just raised seed funding")
    print(json.dumps(result, indent=2))
    
    # Test email generation
    print("\n" + "="*50)
    print("Testing email generation...")
    
    lead = {
        "first_name": "Sarah",
        "full_name": "Sarah Chen",
        "title": "CEO",
        "company": "PayFlow",
        "industry": "FinTech",
        "location": "San Francisco"
    }
    
    email = generator.generate_initial_email(lead, result.get("campaign_context", {}))
    print(f"\nSubject: {email['subject']}")
    print(f"\nBody:\n{email['body']}")
    print(f"\nWord count: {len(email['body'].split())}")
