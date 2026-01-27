"""Test the updated ICP generation to ensure broad search criteria"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_generator import EmailGenerator
from rocketreach_client import RocketReachClient
import json

gen = EmailGenerator()
client = RocketReachClient()

print("="*60)
print("Testing Updated Search Criteria Generation")
print("="*60)

# Test with a campaign description
test_descriptions = [
    "Target CTOs leading cloud migration projects",
    "Target startup founders building MVPs for SaaS products",
    "Target fintech founders building compliance-heavy platforms"
]

for desc in test_descriptions:
    print(f"\n{'─'*60}")
    print(f"Campaign: {desc}")
    print(f"{'─'*60}")
    
    result = gen.determine_icp_and_criteria(desc)
    
    print(f"\nGenerated Name: {result.get('campaign_name')}")
    print(f"\nSearch Criteria:")
    criteria = result.get('search_criteria', {})
    print(json.dumps(criteria, indent=2))
    
    # Check for issues
    issues = []
    if 'industry' in criteria:
        issues.append("❌ HAS INDUSTRY FILTER (will return very few results)")
    if 'industries' in criteria:
        issues.append("❌ HAS INDUSTRIES FILTER (will return very few results)")
    if not criteria.get('location'):
        issues.append("⚠️  No location specified")
    if not criteria.get('keywords'):
        issues.append("⚠️  No keywords (industry targeting missing)")
    
    titles = criteria.get('current_title', [])
    if len(titles) < 3:
        issues.append(f"⚠️  Only {len(titles)} titles - might be too narrow")
    
    if issues:
        print("\n🚨 Issues Found:")
        for issue in issues:
            print(f"   {issue}")
    else:
        print("\n✅ Search criteria looks good!")
    
    # Test actual RocketReach search count
    print(f"\n📊 Testing RocketReach results count...")
    search_results = client.search_people(
        current_title=criteria.get("current_title"),
        location=criteria.get("location"),
        industry=criteria.get("industry"),  # Will be None if properly removed
        keywords=criteria.get("keywords"),
        page_size=1
    )
    
    total = search_results.get("pagination", {}).get("total", 0)
    if total < 100:
        print(f"   ❌ Only {total} results - TOO FEW!")
    elif total < 1000:
        print(f"   ⚠️  {total} results - could be better")
    else:
        print(f"   ✅ {total:,} results available - GREAT!")

print(f"\n{'='*60}")
print("Test Complete")
print(f"{'='*60}")
