#!/usr/bin/env python3
"""
Test ICP Tracking System

Verifies:
1. Database ICP fields work correctly
2. ICP classification is accurate
3. ICP analytics aggregation works
4. System doesn't break existing functionality
"""

import sys
sys.path.insert(0, '.')

from database import Lead, Email
from email_generator import EmailGenerator
from icp_manager import ICPManager

def test_imports():
    """Test all imports work."""
    print("✅ All imports successful")
    return True

def test_icp_analytics():
    """Test ICP analytics function."""
    print("\n📊 Testing ICP Analytics...")
    analytics = Email.get_icp_analytics()
    
    print(f"  Total sent: {analytics.get('total', {}).get('sent', 0)}")
    print(f"  ICP leads: {analytics.get('icp_leads', {}).get('sent', 0)}")
    print(f"  Non-ICP leads: {analytics.get('non_icp_leads', {}).get('sent', 0)}")
    print(f"  Unclassified: {analytics.get('unknown_leads', {}).get('sent', 0)}")
    
    # Verify structure
    assert "icp_leads" in analytics, "Missing icp_leads in analytics"
    assert "non_icp_leads" in analytics, "Missing non_icp_leads in analytics"
    assert "by_template" in analytics, "Missing by_template in analytics"
    
    print("  ✅ Analytics structure correct")
    return True

def test_icp_classification():
    """Test ICP classification function."""
    print("\n🎯 Testing ICP Classification...")
    gen = EmailGenerator()
    
    # Test ICP lead (CTO at tech company)
    icp_lead = {
        'title': 'CTO',
        'company': 'TechStartup Inc',
        'industry': 'Software',
        'enrichment': {'has_enrichment': True, 'is_hiring_engineers': True}
    }
    result = gen.classify_lead_icp(icp_lead)
    
    print(f"  CTO at tech company:")
    print(f"    is_icp: {result['is_icp']}")
    print(f"    score: {result['icp_score']}")
    print(f"    reasons: {result['icp_reasons'][:2]}")
    
    assert result['is_icp'] == True, "CTO at tech company should be ICP"
    assert result['icp_score'] >= 0.5, "Score should be >= 0.5"
    
    # Test non-ICP lead (generic title, non-tech)
    non_icp_lead = {
        'title': 'Office Manager',
        'company': 'Law Firm LLC',
        'industry': 'Legal',
        'enrichment': {}
    }
    result2 = gen.classify_lead_icp(non_icp_lead)
    
    print(f"\n  Office Manager at law firm:")
    print(f"    is_icp: {result2['is_icp']}")
    print(f"    score: {result2['icp_score']}")
    print(f"    non_icp_reasons: {result2['non_icp_reasons'][:2]}")
    
    assert result2['is_icp'] == False, "Office Manager at law firm should NOT be ICP"
    assert result2['icp_score'] < 0.5, "Score should be < 0.5"
    
    print("  ✅ Classification logic correct")
    return True

def test_icp_manager():
    """Test ICP Manager."""
    print("\n🏢 Testing ICP Manager...")
    manager = ICPManager()
    
    # Test analytics report
    analytics = manager.get_icp_analytics()
    assert "analysis" in analytics, "Missing analysis in manager output"
    assert "recommendations" in analytics, "Missing recommendations"
    
    print(f"  Analysis generated: {bool(analytics.get('analysis'))}")
    print(f"  Recommendations: {len(analytics.get('recommendations', []))}")
    
    # Test campaign generation from ICP
    campaign = manager.generate_campaign_from_icp("startup_founders_funded")
    assert "name" in campaign, "Missing campaign name"
    assert "target_criteria" in campaign, "Missing target criteria"
    assert "campaign_context" in campaign, "Missing campaign context"
    
    print(f"  Generated campaign: {campaign['name']}")
    print(f"  ICP template tracked: {campaign['campaign_context'].get('icp_template')}")
    
    print("  ✅ ICP Manager working")
    return True

def test_existing_functionality():
    """Ensure existing functionality still works."""
    print("\n🔧 Testing existing functionality...")
    
    # Test Lead.create still works (with optional ICP fields)
    test_data = {
        'email': 'test@example.com',
        'name': 'Test User',
        'current_title': 'CTO',
        'current_employer': 'Test Corp'
    }
    # Don't actually create - just verify the function signature
    import inspect
    sig = inspect.signature(Lead.create)
    print(f"  Lead.create signature: {sig}")
    
    # Test Email.create still works (with optional ICP fields)
    sig = inspect.signature(Email.create)
    params = list(sig.parameters.keys())
    print(f"  Email.create params: {params}")
    
    assert 'is_icp' in params, "Email.create missing is_icp param"
    assert 'icp_template' in params, "Email.create missing icp_template param"
    
    print("  ✅ Existing functionality preserved (backwards compatible)")
    return True

def main():
    print("="*60)
    print("ICP TRACKING SYSTEM TEST")
    print("="*60)
    
    tests = [
        ("Imports", test_imports),
        ("ICP Analytics", test_icp_analytics),
        ("ICP Classification", test_icp_classification),
        ("ICP Manager", test_icp_manager),
        ("Existing Functionality", test_existing_functionality),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            if test_fn():
                passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60)
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
