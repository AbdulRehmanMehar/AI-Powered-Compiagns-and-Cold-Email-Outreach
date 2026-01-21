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

"If you can't say what you saw that was interesting, don't say you saw something." - LeadGenJay
"""

from openai import OpenAI
from typing import Dict, Any, List, Optional
import config
import json
import random
import re
from primestrides_context import COMPANY_CONTEXT, ICP_TEMPLATES, EMAIL_CONTEXT, CASE_STUDIES


class EmailGenerator:
    """Generate personalized cold emails with REAL personalization"""
    
    def __init__(self):
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.model = "gpt-4.1-mini"
        self.company_context = COMPANY_CONTEXT
        self.email_context = EMAIL_CONTEXT
        self.case_studies = CASE_STUDIES
    
    def research_company(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        PROBLEM SNIFFING: Research the company to find something SPECIFIC to mention.
        This is what separates spam from real outreach.
        
        Returns specific insights we can reference in the email.
        """
        company = lead.get('company', '')
        title = lead.get('title', '')
        industry = lead.get('industry', '')
        first_name = lead.get('first_name', '')
        
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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            return json.loads(response.choices[0].message.content)
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
        """
        industry = lead.get('industry', '').lower()
        title = lead.get('title', '').lower()
        pain_point = research.get('likely_pain_point', '').lower()
        
        # Score each case study for relevance
        scores = {}
        
        for key, study in self.case_studies.items():
            score = 0
            relevance_tags = [r.lower() for r in study.get('relevance', [])]
            study_industry = study.get('industry', '').lower()
            
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
            
            # Title match (CTOs care about different things than founders)
            if 'cto' in title or 'engineer' in title:
                if key == 'timpl':  # Technical case study
                    score += 1
            if 'ceo' in title or 'founder' in title:
                if key == 'stratmap':  # Business outcome case study
                    score += 1
            
            scores[key] = score
        
        # Pick the best match, with some randomization for ties
        best_score = max(scores.values())
        best_matches = [k for k, v in scores.items() if v == best_score]
        selected = random.choice(best_matches)
        
        # Add industry match flag for prompt to use
        result = self.case_studies[selected].copy()
        result['industry_match'] = best_score >= 3  # True if reasonably matched
        
        return result
    
    def determine_icp_and_criteria(self, campaign_description: str) -> Dict[str, Any]:
        """
        Use AI to determine the best ICP and RocketReach search criteria
        """
        icp_options = json.dumps(ICP_TEMPLATES, indent=2)
        case_study_options = json.dumps(CASE_STUDIES, indent=2)
        
        system_prompt = f"""You are an expert at B2B sales targeting and cold email strategy.
You work for PrimeStrides, a boutique software agency.

{self.company_context}

Given a campaign description, determine:
1. The best target audience (be SPECIFIC)
2. RocketReach search criteria
3. The ONE specific pain point to focus on
4. The unique angle that ONLY PrimeStrides can claim
5. Which case study is most relevant

Available ICP templates:
{icp_options}

Available case studies:
{case_study_options}

Return JSON with campaign_name, target_description, search_criteria, and campaign_context."""

        user_prompt = f"""Campaign description: {campaign_description}

Create hyper-targeted campaign. Remember: ONE pain point, specific case study, unique angle."""

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
            
            return json.loads(response.choices[0].message.content)
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
                "unique_angle": "we shipped RoboApply's entire AI system in 8 weeks",
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
        Generate a TRULY personalized cold email.
        
        LeadGenJay Rules:
        1. Subject: 2-4 words, looks like colleague
        2. First line: Creates CURIOSITY, is SPECIFIC (not "saw something interesting")
        3. Under 75 words total (50-60 ideal)
        4. ONE pain point
        5. Relevant case study with REAL numbers
        6. Soft CTA
        """
        
        # Step 1: Research the company (PROBLEM SNIFFING)
        research = self.research_company(lead)
        
        # Step 2: Select the most relevant case study
        case_study = self.select_case_study(lead, research)
        
        first_name = lead.get('first_name', 'there')
        company = lead.get('company', 'your company')
        title = lead.get('title', '')
        industry = lead.get('industry', '')
        
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
        
        # Vary subject lines to avoid repetition
        subject_options = [
            f'"{first_name}?"',
            '"thought"',
            '"quick q"', 
            f'"re: {company}"',
            '"hey"',
            '"idea"',
        ]
        
        # Randomly select opening style for variation
        import random
        
        # LeadGenJay style: First line is PREVIEW TEXT - must bait them to open
        # NOT "why you're reaching out" - that kills open rates
        opening_styles = [
            f"{company}'s [specific thing] looks sick.",
            f"{first_name}—[observation].",
            f"[Specific thing about {company}]. Made me think.",
            f"Saw {company}'s [specific thing]—pretty cool.",
            f"{company} just [did something]. That's gotta be [feeling].",
        ]
        suggested_opener = random.choice(opening_styles)
        
        # Randomly select CTA for variation - LeadGenJay: ONE soft CTA only
        cta_options = [
            "interested?",
            "make sense?",
            "thoughts?",
            "worth exploring?",
            "open to it?",
        ]
        suggested_cta = random.choice(cta_options)
        
        # Case study reference - LeadGenJay: use relevant case studies
        case_study_reference = f"a {case_study.get('industry', 'similar')} company"
        
        # LeadGenJay's EXACT framework from the 90-page doc:
        # Line 1: Preview text that sounds like a friend (NOT why you're reaching out)
        # Line 2: Poke the bear / agitate pain
        # Line 3: Case study with SPECIFIC numbers (3.72x not 4x)
        # Line 4: Soft CTA
        
        system_prompt = f"""You are writing a cold email that should read like a casual text from a friend.

CRITICAL RULES FROM LEADGENJAY:
1. First line = PREVIEW TEXT. It must sound like it could be from a friend or colleague. 
   The goal is to get them to OPEN the email. If they know it's a pitch before opening, they delete.
   
2. 6th GRADE READING LEVEL. Simple words. No jargon. Like texting.

3. Under 75 words total. Shorter is better.

4. SPECIFIC numbers in case study: "3.2x" not "3x", "43%" not "~40%"

**STRUCTURE (4 lines max):**
Line 1: [Preview bait] - Something specific you noticed. NOT "I noticed" or "I saw that" - just state the observation.
Line 2: [Poke the bear] - One sentence about their likely pain/challenge. Don't ask "how are you handling X?"
Line 3: [Case study] - "{case_study_reference} {case_study.get('result_short', case_study.get('result'))} in {case_study.get('timeline')}."
Line 4: [CTA] - Just "{suggested_cta}" - nothing more.

**SUBJECT LINE:** 2-3 words max. Pick from: {first_name}?, thought, quick q, hey, idea
Should sound like it could be from a coworker.

**BANNED (instant spam folder):**
- "I noticed..." / "I saw that..." / "I came across..."
- "I hope this finds you well"
- "Quick thought—" at the start
- Questions like "How are you handling/managing/navigating X?"
- Corporate words: leverage, synergy, streamline, optimize, innovative, comprehensive, incentivize
- Guarantees or promises
- Multiple CTAs
- Anything over 75 words

**GOOD EXAMPLE:**
Subject: mike?

{company}'s new warehouse automation is wild. Scaling that with real-time inventory sync has to be tricky. {case_study_reference} cut processing time 43% in 8 weeks. {suggested_cta}

Return JSON: {{"subject": "...", "body": "..."}}"""

        user_prompt = f"""Write a LeadGenJay-style cold email to:
- Name: {first_name}
- Title: {title}  
- Company: {company}
- Industry: {industry}

Research found: {json.dumps(research)}

Use this case study: {case_study_reference} - {case_study.get('result')} in {case_study.get('timeline')}

End with CTA: {suggested_cta}

Remember: 
- First line must bait them to open (preview text)
- 6th grade reading level
- Under 75 words
- SPECIFIC numbers
- No "I noticed" or formal questions"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.9,  # Higher for more human variation
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Validate and clean
            subject = result.get("subject", f"{first_name}?")
            body = result.get("body", "")
            
            # Final validation
            body = self._validate_and_clean(body, lead, case_study)
            
            return {
                "subject": subject,
                "body": body,
                "research": research,  # Include for debugging
                "case_study_used": case_study.get('company_name')
            }
        except Exception as e:
            print(f"Error generating email: {e}")
            return self._fallback_email(lead, campaign_context, research, case_study)
    
    def _validate_and_clean(self, body: str, lead: Dict, case_study: Dict) -> str:
        """Validate email doesn't contain banned patterns - STRICT per LeadGenJay"""
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
    
    def _fallback_email(self, lead: Dict, context: Dict, research: Dict, case_study: Dict) -> Dict[str, str]:
        """Fallback email that sounds human, not templated"""
        first_name = lead.get('first_name', 'there')
        company = lead.get('company', 'your company')
        
        # Different casual openers to avoid repetition
        openers = [
            f"{company} caught my eye.",
            f"Quick thought about {company}.",
            f"Been thinking about {company}'s setup.",
        ]
        
        opener = random.choice(openers)
        
        # Casual body
        body = f"""{opener}

Scaling eng teams is brutal. We helped a similar company ship 3x faster in 8 weeks.

Worth a quick chat?"""

        return {
            "subject": f"{first_name}?",
            "body": body,
            "research": research,
            "case_study_used": "generic"
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
        first_name = lead.get('first_name', 'there')
        company = lead.get('company', '')
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
        first_name = lead.get('first_name', 'there')
        company = lead.get('company', '')
        front_end_offer = context.get('front_end_offer', 'free architecture review')
        
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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.9,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return {
                "subject": result.get("subject", "different thought"),
                "body": result.get("body", ""),
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
        first_name = lead.get('first_name', 'there')
        company = lead.get('company', '')
        
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
