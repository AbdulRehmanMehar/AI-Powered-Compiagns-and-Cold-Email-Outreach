"""
ICP Manager - AI-Powered Ideal Customer Profile Management

Based on TK Kader's ICP Framework:
1. 10x Better: Where are we solving urgent problems better than alternatives?
2. Data-Backed: Decisions informed by internal/external data, not wishlists
3. Mobilize & Track: Track ICP leads through go-to-market, refine quarterly

This module:
- Generates new ICP templates based on performance data
- Analyzes which ICPs perform best (reply rates, meetings)
- Suggests campaign criteria for new ICPs
- Feeds back data to improve targeting over time
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

from database import Email, Lead, Campaign, emails_collection, leads_collection
from primestrides_context import ICP_TEMPLATES, CASE_STUDIES, COMPANY_CONTEXT
from email_generator import get_rate_limiter, GROQ_FALLBACK_CHAIN, GROQ_MODEL_LIMITS
import config

logger = logging.getLogger(__name__)


class ICPManager:
    """
    AI-powered ICP generation and management.
    
    Implements TK Kader's data-driven ICP refinement cycle:
    1. Track ICP vs non-ICP leads
    2. Analyze performance (reply rates, conversions)
    3. Generate new ICPs or refine existing ones
    4. Iterate quarterly
    """
    
    def __init__(self):
        self.groq_api_key = config.GROQ_API_KEY
        self.llm_model = config.GROQ_MODEL
        self.rate_limiter = get_rate_limiter()
        self._groq_client = None
    
    @property
    def groq_client(self):
        """Lazy load Groq client."""
        if self._groq_client is None:
            import groq
            # Disable SDK auto-retry - we handle retries ourselves with model rotation
            self._groq_client = groq.Groq(api_key=self.groq_api_key, max_retries=0)
        return self._groq_client
    
    def _call_llm(self, system_prompt: str, user_prompt: str, temperature: float = 0.7, json_mode: bool = True) -> str:
        """
        Call LLM with automatic model rotation on rate limits.
        """
        tried_models = set()
        last_error = None
        
        while True:
            available_model = self.rate_limiter.get_best_available_model(self.llm_model)
            
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
                
                response = self.groq_client.chat.completions.create(**kwargs)
                
                # Check for empty response
                content = response.choices[0].message.content
                if not content or content.strip() == '':
                    logger.warning(f"ICPManager: {available_model} returned empty response, trying next...")
                    continue
                
                tokens_used = 2000
                if hasattr(response, 'usage') and response.usage:
                    tokens_used = getattr(response.usage, 'total_tokens', 2000)
                self.rate_limiter.record_request(available_model, tokens_used)
                
                return content
                
            except Exception as e:
                error_str = str(e).lower()
                last_error = e
                
                if 'rate' in error_str and 'limit' in error_str:
                    self.rate_limiter.mark_model_depleted(available_model, "429_rate_limit")
                    logger.warning(f"ICPManager: {available_model} hit rate limit, marked as depleted, trying next...")
                    continue
                else:
                    raise
    
    def get_icp_analytics(self, campaign_id: str = None, days: int = 30) -> Dict[str, Any]:
        """
        Get comprehensive ICP performance analytics.
        
        This is the core data that feeds into ICP refinement.
        """
        analytics = Email.get_icp_analytics(campaign_id)
        
        # Add trend analysis
        analytics["analysis"] = self._analyze_performance(analytics)
        analytics["recommendations"] = self._generate_recommendations(analytics)
        analytics["generated_at"] = datetime.utcnow().isoformat()
        
        return analytics
    
    def _analyze_performance(self, analytics: Dict) -> Dict[str, Any]:
        """Analyze ICP performance and generate insights."""
        analysis = {
            "icp_effectiveness": None,
            "top_performing_templates": [],
            "underperforming_templates": [],
            "key_insights": []
        }
        
        # Compare ICP vs non-ICP performance
        icp = analytics.get("icp_leads", {})
        non_icp = analytics.get("non_icp_leads", {})
        
        icp_rate = icp.get("reply_rate", 0)
        non_icp_rate = non_icp.get("reply_rate", 0)
        
        if icp.get("sent", 0) > 10 and non_icp.get("sent", 0) > 10:
            if icp_rate > non_icp_rate:
                improvement = ((icp_rate - non_icp_rate) / max(non_icp_rate, 0.01)) * 100
                analysis["icp_effectiveness"] = {
                    "verdict": "ICP targeting is working",
                    "icp_reply_rate": icp_rate,
                    "non_icp_reply_rate": non_icp_rate,
                    "improvement_percent": round(improvement, 1)
                }
                analysis["key_insights"].append(
                    f"ICP leads convert {round(improvement)}% better than non-ICP leads"
                )
            else:
                analysis["icp_effectiveness"] = {
                    "verdict": "ICP needs refinement",
                    "icp_reply_rate": icp_rate,
                    "non_icp_reply_rate": non_icp_rate,
                    "improvement_percent": 0
                }
                analysis["key_insights"].append(
                    "⚠️ ICP leads are NOT outperforming non-ICP - review targeting criteria"
                )
        else:
            analysis["key_insights"].append(
                "Need more data: Send to at least 10+ ICP and 10+ non-ICP leads"
            )
        
        # Analyze by template
        templates = analytics.get("by_template", {})
        sorted_templates = sorted(
            [(k, v) for k, v in templates.items() if v.get("sent", 0) >= 5],
            key=lambda x: x[1].get("reply_rate", 0),
            reverse=True
        )
        
        if sorted_templates:
            # Top performers
            for name, data in sorted_templates[:3]:
                if data.get("reply_rate", 0) > 0:
                    analysis["top_performing_templates"].append({
                        "template": name,
                        "reply_rate": data.get("reply_rate"),
                        "sent": data.get("sent"),
                        "replied": data.get("replied")
                    })
            
            # Underperformers
            for name, data in sorted_templates[-3:]:
                if data.get("sent", 0) >= 10 and data.get("reply_rate", 0) == 0:
                    analysis["underperforming_templates"].append({
                        "template": name,
                        "reply_rate": 0,
                        "sent": data.get("sent"),
                        "recommendation": "Consider deprecating or revising"
                    })
        
        return analysis
    
    def _generate_recommendations(self, analytics: Dict) -> List[str]:
        """Generate actionable recommendations based on analytics."""
        recommendations = []
        
        analysis = analytics.get("analysis", {})
        total = analytics.get("total", {})
        
        # Data volume recommendations
        if total.get("sent", 0) < 50:
            recommendations.append(
                "📊 Need more data: Send at least 50 emails before making ICP decisions"
            )
        
        # ICP targeting recommendations
        effectiveness = analysis.get("icp_effectiveness")
        if effectiveness and effectiveness.get("verdict") == "ICP needs refinement":
            recommendations.append(
                "🎯 Refine ICP criteria: Current targeting isn't improving conversion rates"
            )
        
        # Template recommendations
        if analysis.get("underperforming_templates"):
            templates = [t["template"] for t in analysis["underperforming_templates"]]
            recommendations.append(
                f"🔄 Review these templates: {', '.join(templates)} - zero replies"
            )
        
        if analysis.get("top_performing_templates"):
            top = analysis["top_performing_templates"][0]
            if top.get("reply_rate", 0) > 5:
                recommendations.append(
                    f"✅ Double down on '{top['template']}' - {top['reply_rate']}% reply rate"
                )
        
        # Unknown/untracked leads
        unknown = analytics.get("unknown_leads", {})
        if unknown.get("sent", 0) > analytics.get("icp_leads", {}).get("sent", 0):
            recommendations.append(
                "⚠️ Most emails lack ICP tracking - classify leads before sending"
            )
        
        return recommendations
    
    def generate_new_icp(self, 
                         campaign_goal: str,
                         existing_performance: Dict = None) -> Dict[str, Any]:
        """
        Use AI to generate a new ICP template based on:
        1. Campaign goal/description
        2. Existing performance data (if available)
        3. Our case studies and capabilities
        
        Returns a new ICP template ready to use.
        """
        # Get performance context if we have data
        performance_context = ""
        if existing_performance:
            analytics = self.get_icp_analytics()
            if analytics.get("analysis", {}).get("top_performing_templates"):
                top = analytics["analysis"]["top_performing_templates"]
                performance_context = f"""
Based on our data:
- Top performing ICPs: {json.dumps(top, indent=2)}
- ICP leads reply at {analytics.get('icp_leads', {}).get('reply_rate', 0)}%
- Non-ICP leads reply at {analytics.get('non_icp_leads', {}).get('reply_rate', 0)}%

Build on what's working!
"""
        
        system_prompt = f"""You are an expert at defining Ideal Customer Profiles for B2B SaaS.

You work for PrimeStrides, a boutique software agency that helps companies build and scale products.

{COMPANY_CONTEXT}

Your job is to create a NEW ICP template that:
1. Targets prospects where we are 10x BETTER than alternatives (TK Kader principle)
2. Focuses on URGENT, IMPORTANT problems with budget
3. Is SPECIFIC enough to identify high-value leads
4. Is TRACKABLE through our go-to-market

Available case studies to reference:
{json.dumps(CASE_STUDIES, indent=2)}

Existing ICP templates (for reference):
{json.dumps(ICP_TEMPLATES, indent=2)}

{performance_context}

Return a JSON object with:
{{
    "template_name": "snake_case_name",
    "description": "Who this targets and why",
    "titles": ["Title 1", "Title 2", ...],  // Decision-maker titles
    "industries": ["Industry 1", ...],  // Target verticals
    "company_size": "Description of ideal company size",
    "trigger_signals": ["Signal 1", ...],  // What indicates they need us NOW
    "single_pain_point": "The ONE pain this ICP has",
    "unique_angle": "Why PrimeStrides specifically (not generic)",
    "relevant_case_study": "case_study_key",  // From available case studies
    "front_end_offer": "Low-commitment first step",
    "search_criteria": {{  // RocketReach search
        "current_title": [...],
        "location": [...],
        "keywords": [...]  // No industry filter - use keywords
    }},
    "icp_signals": {{  // How to score leads
        "must_have": ["Signal 1", ...],  // Required for ICP=true
        "good_to_have": ["Signal 1", ...],  // Bonus points
        "disqualifiers": ["Signal 1", ...]  // Automatic non-ICP
    }}
}}"""

        user_prompt = f"""Create a new ICP template for this campaign goal:

{campaign_goal}

Remember:
- Be SPECIFIC (not "tech companies" but "Series A fintech startups with <10 engineers")
- Focus on urgency (why do they need us NOW?)
- Include trackable signals
- Use case studies we actually have"""

        try:
            # Use _call_llm for automatic model rotation
            response_content = self._call_llm(system_prompt, user_prompt, temperature=0.7, json_mode=True)
            
            result = json.loads(response_content)
            result["generated_at"] = datetime.utcnow().isoformat()
            result["generated_from"] = campaign_goal
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating ICP: {e}")
            return {"error": str(e)}
    
    def generate_campaign_from_icp(self, 
                                    icp_template: str,
                                    custom_context: Dict = None) -> Dict[str, Any]:
        """
        Generate a complete campaign configuration from an ICP template.
        
        This creates everything needed to run a campaign:
        - Search criteria
        - Email context
        - Pain points
        - Case study selection
        """
        # Get the ICP template
        template = ICP_TEMPLATES.get(icp_template)
        if not template:
            return {"error": f"ICP template '{icp_template}' not found"}
        
        # Get the relevant case study
        case_study_key = template.get("relevant_case_study", "roboapply")
        case_study = CASE_STUDIES.get(case_study_key, CASE_STUDIES.get("roboapply", {}))
        
        campaign = {
            "name": f"Campaign: {icp_template.replace('_', ' ').title()}",
            "description": template.get("description", ""),
            "target_criteria": {
                "current_title": template.get("titles", []),
                "location": ["United States", "Canada", "United Kingdom"],
                "keywords": template.get("industries", []) + template.get("trigger_signals", [])[:2]
            },
            "campaign_context": {
                "product_service": "senior engineering team for 8-week sprints",
                "single_pain_point": template.get("single_pain_point", ""),
                "unique_angle": template.get("unique_angle", ""),
                "case_study": case_study,
                "front_end_offer": template.get("front_end_offer", "free 30-min architecture review"),
                "trigger_signal": template.get("trigger_signals", ["actively building"])[0],
                "icp_template": icp_template  # For tracking
            }
        }
        
        # Merge custom context if provided
        if custom_context:
            campaign["campaign_context"].update(custom_context)
        
        return campaign
    
    def select_best_icp_autonomous(self) -> str:
        """
        AUTONOMOUS ICP SELECTION
        
        Automatically selects the best ICP template to use based on:
        1. Historical performance data (reply rates by template)
        2. Exploration vs exploitation (try undertested templates)
        3. Rotation to avoid burning any single audience
        
        This is the core of autonomous campaign management - NO HUMAN INPUT NEEDED.
        
        Returns:
            Name of the ICP template to use
        """
        analytics = self.get_icp_analytics()
        by_template = analytics.get("by_template", {})
        
        # Get all available templates
        all_templates = list(ICP_TEMPLATES.keys())
        
        # Calculate scores for each template
        template_scores = {}
        
        for template in all_templates:
            data = by_template.get(template, {"sent": 0, "replied": 0, "reply_rate": 0})
            sent = data.get("sent", 0)
            reply_rate = data.get("reply_rate", 0)
            
            # Score calculation (multi-armed bandit inspired)
            if sent == 0:
                # Never tried - high exploration bonus
                score = 100  # Try untested templates first
            elif sent < 20:
                # Low sample size - exploration bonus + performance
                exploration_bonus = 50 * (1 - sent/20)  # Decreases as we get more data
                score = reply_rate * 10 + exploration_bonus
            else:
                # Enough data - weight by performance
                score = reply_rate * 10
                
                # Penalty for over-used templates (avoid audience burnout)
                if sent > 100:
                    score *= 0.8
                if sent > 200:
                    score *= 0.7
            
            template_scores[template] = {
                "score": round(score, 2),
                "sent": sent,
                "reply_rate": reply_rate,
                "reason": self._explain_score(sent, reply_rate, score)
            }
        
        # Sort by score and pick the best
        sorted_templates = sorted(
            template_scores.items(),
            key=lambda x: x[1]["score"],
            reverse=True
        )
        
        selected = sorted_templates[0][0]
        
        logger.info(f"🤖 Autonomous ICP Selection: {selected}")
        logger.info(f"   Reason: {template_scores[selected]['reason']}")
        
        return selected
    
    def _explain_score(self, sent: int, reply_rate: float, score: float) -> str:
        """Generate human-readable explanation for ICP selection."""
        if sent == 0:
            return "Never tested - exploring this ICP"
        elif sent < 20:
            return f"Low data ({sent} sent) - still exploring"
        elif reply_rate > 5:
            return f"High performer ({reply_rate}% reply rate)"
        elif reply_rate > 2:
            return f"Moderate performer ({reply_rate}% reply rate)"
        else:
            return f"Needs improvement ({reply_rate}% reply rate)"
    
    def get_autonomous_campaign_plan(self, num_campaigns: int = 3) -> List[Dict[str, Any]]:
        """
        Generate an autonomous campaign plan for the day.
        
        This creates a balanced plan that:
        1. Prioritizes high-performing ICPs
        2. Explores untested ICPs
        3. Rotates to avoid burnout
        
        Args:
            num_campaigns: How many campaigns to plan
        
        Returns:
            List of campaign configs ready to execute
        """
        analytics = self.get_icp_analytics()
        by_template = analytics.get("by_template", {})
        all_templates = list(ICP_TEMPLATES.keys())
        
        plan = []
        used_templates = set()
        
        for i in range(num_campaigns):
            # Get scores excluding already-planned templates
            remaining = [t for t in all_templates if t not in used_templates]
            if not remaining:
                remaining = all_templates  # Reset if we've used all
            
            # Score remaining templates
            best_template = None
            best_score = -1
            
            for template in remaining:
                data = by_template.get(template, {"sent": 0, "reply_rate": 0})
                sent = data.get("sent", 0)
                reply_rate = data.get("reply_rate", 0)
                
                if sent == 0:
                    score = 100 - (i * 10)  # Slight preference for exploration early
                elif sent < 20:
                    score = 50 + reply_rate * 5
                else:
                    score = reply_rate * 10
                
                if score > best_score:
                    best_score = score
                    best_template = template
            
            if best_template:
                used_templates.add(best_template)
                campaign_config = self.generate_campaign_from_icp(best_template)
                campaign_config["selection_reason"] = self._explain_score(
                    by_template.get(best_template, {}).get("sent", 0),
                    by_template.get(best_template, {}).get("reply_rate", 0),
                    best_score
                )
                campaign_config["priority"] = i + 1
                plan.append(campaign_config)
        
        return plan
    
    def print_analytics_report(self, campaign_id: str = None):
        """Print a formatted ICP analytics report."""
        analytics = self.get_icp_analytics(campaign_id)
        
        print("\n" + "="*60)
        print("📊 ICP PERFORMANCE ANALYTICS (TK Kader Framework)")
        print("="*60)
        
        # Overall stats
        total = analytics.get("total", {})
        print(f"\n📧 Total Emails: {total.get('sent', 0)} sent, {total.get('replied', 0)} replied")
        
        # ICP vs Non-ICP comparison
        print("\n🎯 ICP vs Non-ICP Performance:")
        print("-" * 40)
        
        for category, label in [("icp_leads", "ICP Leads"), 
                                ("non_icp_leads", "Non-ICP Leads"),
                                ("unknown_leads", "Unclassified")]:
            data = analytics.get(category, {})
            if data.get("sent", 0) > 0:
                print(f"  {label}:")
                print(f"    Sent: {data.get('sent', 0)}, Replied: {data.get('replied', 0)}")
                print(f"    Reply Rate: {data.get('reply_rate', 0)}%")
        
        # By template
        by_template = analytics.get("by_template", {})
        if by_template:
            print("\n📋 Performance by ICP Template:")
            print("-" * 40)
            sorted_templates = sorted(
                by_template.items(),
                key=lambda x: x[1].get("reply_rate", 0),
                reverse=True
            )
            for name, data in sorted_templates:
                if data.get("sent", 0) > 0:
                    print(f"  {name}:")
                    print(f"    Sent: {data.get('sent')}, Replied: {data.get('replied')}, Rate: {data.get('reply_rate')}%")
        
        # Analysis insights
        analysis = analytics.get("analysis", {})
        if analysis.get("key_insights"):
            print("\n💡 Key Insights:")
            print("-" * 40)
            for insight in analysis["key_insights"]:
                print(f"  • {insight}")
        
        # Recommendations
        recommendations = analytics.get("recommendations", [])
        if recommendations:
            print("\n🎬 Recommendations:")
            print("-" * 40)
            for rec in recommendations:
                print(f"  {rec}")
        
        print("\n" + "="*60)
        return analytics
    
    def get_rocketreach_criteria_for_icp(self, icp_template: str) -> Dict[str, Any]:
        """
        Get RocketReach-optimized search criteria for an ICP template.
        
        This is the key function that connects ICP definitions to lead sourcing.
        It generates search criteria that will find leads matching the ICP.
        
        IMPORTANT: Uses keywords instead of industry filters because
        RocketReach industry filters are too restrictive.
        """
        template = ICP_TEMPLATES.get(icp_template)
        if not template:
            return {"error": f"ICP template '{icp_template}' not found"}
        
        # Build title variations for broader search
        base_titles = template.get("titles", [])
        expanded_titles = set(base_titles)
        
        # Add common variations
        for title in base_titles:
            title_lower = title.lower()
            if "founder" in title_lower:
                expanded_titles.update(["Founder", "Co-Founder", "CEO", "CEO & Founder", "Co-founder and CEO"])
            if "cto" in title_lower:
                expanded_titles.update(["CTO", "Chief Technology Officer", "VP Engineering", "VP of Engineering"])
            if "vp" in title_lower and "engineering" in title_lower:
                expanded_titles.update(["VP Engineering", "VP of Engineering", "Head of Engineering", "Engineering Director"])
            if "product" in title_lower:
                expanded_titles.update(["VP Product", "VP of Product", "Head of Product", "CPO", "Chief Product Officer"])
        
        # Build keywords from industries + trigger signals (NOT as filters)
        keywords = []
        keywords.extend(template.get("industries", []))
        keywords.extend(template.get("trigger_signals", [])[:2])  # Top 2 signals
        
        # Remove duplicates and generic terms
        keywords = list(set(kw for kw in keywords if kw.lower() not in ["technology", "software"]))
        
        criteria = {
            "current_title": list(expanded_titles),
            "location": ["United States", "Canada", "United Kingdom"],
            "keywords": keywords if keywords else ["startup", "SaaS", "tech"]
            # NOTE: No 'industry' field - too restrictive in RocketReach
        }
        
        # Add company size hints via keywords if specified
        company_size = template.get("company_size", "")
        if "1-50" in company_size or "startup" in company_size.lower():
            criteria["keywords"].append("startup")
        elif "100-" in company_size or "enterprise" in company_size.lower():
            criteria["keywords"].append("enterprise")
        
        return {
            "icp_template": icp_template,
            "description": template.get("description", ""),
            "search_criteria": criteria,
            "expected_icp_match_rate": "70-90%",  # Since we're searching based on ICP criteria
            "pain_point": template.get("single_pain_point", ""),
            "case_study": template.get("relevant_case_study", "")
        }
    
    def list_icps(self) -> List[Dict[str, Any]]:
        """List all available ICP templates with their search criteria."""
        icps = []
        for name, template in ICP_TEMPLATES.items():
            icps.append({
                "name": name,
                "description": template.get("description", ""),
                "titles": template.get("titles", []),
                "pain_point": template.get("single_pain_point", ""),
                "case_study": template.get("relevant_case_study", "")
            })
        return icps
    
    def print_icp_list(self):
        """Print all available ICP templates."""
        print("\n" + "="*60)
        print("🎯 AVAILABLE ICP TEMPLATES")
        print("="*60)
        
        for name, template in ICP_TEMPLATES.items():
            print(f"\n📋 {name}")
            print(f"   {template.get('description', '')}")
            print(f"   Titles: {', '.join(template.get('titles', []))}")
            print(f"   Pain: {template.get('single_pain_point', '')[:60]}...")
        
        print("\n" + "="*60)


def main():
    """CLI for ICP management."""
    import argparse
    
    parser = argparse.ArgumentParser(description="ICP Manager - AI-Powered ICP Management")
    parser.add_argument("command", choices=["analytics", "generate", "campaign", "list", "search"],
                       help="Command to run")
    parser.add_argument("--campaign-id", help="Campaign ID for analytics")
    parser.add_argument("--goal", help="Campaign goal for ICP generation")
    parser.add_argument("--icp", help="ICP template name")
    
    args = parser.parse_args()
    
    manager = ICPManager()
    
    if args.command == "analytics":
        manager.print_analytics_report(args.campaign_id)
    
    elif args.command == "list":
        manager.print_icp_list()
    
    elif args.command == "search":
        if not args.icp:
            print("Error: --icp required for search criteria")
            manager.print_icp_list()
            return
        result = manager.get_rocketreach_criteria_for_icp(args.icp)
        print(json.dumps(result, indent=2))
    
    elif args.command == "generate":
        if not args.goal:
            print("Error: --goal required for ICP generation")
            return
        result = manager.generate_new_icp(args.goal)
        print(json.dumps(result, indent=2))
    
    elif args.command == "campaign":
        if not args.icp:
            print("Error: --icp required for campaign generation")
            manager.print_icp_list()
            return
        result = manager.generate_campaign_from_icp(args.icp)
        print(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
