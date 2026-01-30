"""Test ICP to RocketReach search criteria flow"""
import sys
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

from icp_manager import ICPManager
from primestrides_context import ICP_TEMPLATES
import json

def test_icp_to_rocketreach():
    manager = ICPManager()
    
    print("=== ICP → ROCKETREACH SEARCH CRITERIA FLOW ===\n")
    
    for icp_name in list(ICP_TEMPLATES.keys()):
        print(f"🎯 ICP: {icp_name}")
        print("-" * 50)
        
        # Get the campaign config (which includes search criteria)
        campaign = manager.generate_campaign_from_icp(icp_name)
        
        criteria = campaign.get("target_criteria", {})
        print(f"Search criteria for RocketReach:")
        print(f"  current_title: {criteria.get('current_title', [])}")
        print(f"  location: {criteria.get('location', [])}")
        print(f"  keywords: {criteria.get('keywords', [])}")
        print()


def test_full_autonomous_flow():
    """Test the complete autonomous selection → search criteria flow"""
    from database import SchedulerConfig
    
    print("\n" + "="*60)
    print("FULL AUTONOMOUS FLOW TEST")
    print("="*60)
    
    # Step 1: Autonomous ICP selection
    selection = SchedulerConfig.select_icp_for_autonomous_run()
    selected_icp = selection["selected_icp"]
    
    print(f"\n1️⃣ AI Selected ICP: {selected_icp}")
    print(f"   Reason: {selection['selection_reason']}")
    
    # Step 2: Get RocketReach criteria for that ICP
    manager = ICPManager()
    campaign = manager.generate_campaign_from_icp(selected_icp)
    criteria = campaign.get("target_criteria", {})
    
    print(f"\n2️⃣ RocketReach Search Criteria:")
    print(json.dumps(criteria, indent=4))
    
    # Step 3: Campaign context for email generation
    context = campaign.get("campaign_context", {})
    print(f"\n3️⃣ Email Context:")
    print(f"   Pain point: {context.get('single_pain_point', '')[:60]}...")
    print(f"   Case study: {context.get('case_study', {}).get('client', 'N/A')}")
    print(f"   ICP template: {context.get('icp_template')}")
    
    print("\n✅ Full flow verified - ICP selection → Search → Email context")


if __name__ == "__main__":
    test_icp_to_rocketreach()
    test_full_autonomous_flow()
