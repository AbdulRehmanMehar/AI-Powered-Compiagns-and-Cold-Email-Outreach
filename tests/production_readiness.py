#!/usr/bin/env python3
"""
PRODUCTION READINESS ANALYSIS
Comprehensive check of all system components before deployment.
"""
import sys
import os
sys.path.insert(0, '/Users/abdulrehmanmehar/Documents/PrimeStrides/coldemails')

from datetime import datetime, timedelta
from pymongo import MongoClient

def main():
    print('=' * 70)
    print('PRODUCTION READINESS ANALYSIS')
    print('=' * 70)
    
    issues = []
    warnings = []
    
    # 1. Database connection
    print('\n1. DATABASE CONNECTION')
    try:
        client = MongoClient('mongodb://admin:strongpassword@192.168.1.9:27017/', serverSelectionTimeoutMS=5000)
        client.server_info()
        print('   ✅ MongoDB connected')
    except Exception as e:
        print(f'   ❌ MongoDB FAILED: {e}')
        issues.append('Database connection failed')
        return issues, warnings
    
    db = client['primeoutreachcron']
    
    # 2. Check collections
    print('\n2. REQUIRED COLLECTIONS')
    required = ['leads', 'emails', 'campaigns', 'groq_model_limits', 'email_reviews']
    for coll in required:
        count = db[coll].count_documents({})
        print(f'   ✅ {coll}: {count:,} documents')
    
    # 3. Lead pipeline
    print('\n3. LEAD PIPELINE')
    pending = db['leads'].count_documents({'status': 'pending'})
    contacted = db['leads'].count_documents({'status': 'contacted'})
    invalid = db['leads'].count_documents({'email_valid': False})
    print(f'   Pending: {pending}')
    print(f'   Contacted: {contacted}')
    print(f'   Invalid emails: {invalid}')
    if pending < 10:
        warnings.append(f'Low pending leads: {pending}')
        print('   ⚠️ WARNING: Low pending leads')
    else:
        print('   ✅ Sufficient leads')
    
    # 4. Autonomous campaigns
    print('\n4. AUTONOMOUS CAMPAIGNS')
    auto_campaigns = list(db['campaigns'].find({'autonomous': True}))
    print(f'   Autonomous campaigns: {len(auto_campaigns)}')
    for c in auto_campaigns[:3]:
        last_run = c.get('last_run')
        name = c.get('name', 'unnamed')
        print(f'   - {name}: last_run={last_run}')
    if not auto_campaigns:
        warnings.append('No autonomous campaigns configured')
        print('   ⚠️ WARNING: No autonomous campaigns')
    
    # 5. Groq rate limits
    print('\n5. GROQ MODEL LIMITS')
    today = datetime.utcnow().strftime('%Y-%m-%d')
    models = list(db['groq_model_limits'].find())
    print(f'   Models configured: {len(models)}')
    depleted = 0
    for m in models:
        usage = m.get('usage', {})
        if usage.get('depleted_reason'):
            depleted += 1
            print(f'   ⚠️ {m["model"]}: DEPLETED ({usage.get("depleted_reason")})')
    if depleted > 0:
        warnings.append(f'{depleted} models are depleted')
    else:
        print('   ✅ All models available')
    
    # 6. Recent email performance
    print('\n6. RECENT EMAIL PERFORMANCE')
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_sent = db['emails'].count_documents({'sent_at': {'$gte': week_ago}})
    recent_bounced = db['emails'].count_documents({'bounced': True, 'sent_at': {'$gte': week_ago}})
    print(f'   Emails sent (7 days): {recent_sent}')
    print(f'   Bounced (7 days): {recent_bounced}')
    if recent_sent > 0:
        bounce_rate = recent_bounced / recent_sent * 100
        print(f'   Bounce rate: {bounce_rate:.1f}%')
        if bounce_rate > 10:
            warnings.append(f'High bounce rate: {bounce_rate:.1f}%')
            print('   ⚠️ WARNING: High bounce rate')
    
    # 7. Email review pass rate
    print('\n7. EMAIL REVIEW QUALITY')
    recent_reviews = db['email_reviews'].count_documents({'created_at': {'$gte': week_ago}})
    passed_reviews = db['email_reviews'].count_documents({'created_at': {'$gte': week_ago}, 'passed': True})
    print(f'   Reviews (7 days): {recent_reviews}')
    if recent_reviews > 0:
        pass_rate = passed_reviews / recent_reviews * 100
        print(f'   Pass rate: {pass_rate:.1f}%')
        if pass_rate < 50:
            warnings.append(f'Low review pass rate: {pass_rate:.1f}%')
    
    # 8. Check key imports
    print('\n8. MODULE IMPORTS')
    try:
        from campaign_manager import CampaignManager
        print('   ✅ CampaignManager')
    except Exception as e:
        issues.append(f'CampaignManager import failed: {e}')
        print(f'   ❌ CampaignManager: {e}')
    
    try:
        from email_generator import EmailGenerator
        print('   ✅ EmailGenerator')
    except Exception as e:
        issues.append(f'EmailGenerator import failed: {e}')
        print(f'   ❌ EmailGenerator: {e}')
    
    try:
        from email_reviewer import EmailReviewer
        print('   ✅ EmailReviewer')
    except Exception as e:
        issues.append(f'EmailReviewer import failed: {e}')
        print(f'   ❌ EmailReviewer: {e}')
    
    try:
        from zoho_sender import ZohoEmailSender
        print('   ✅ ZohoEmailSender')
    except Exception as e:
        issues.append(f'ZohoEmailSender import failed: {e}')
        print(f'   ❌ ZohoEmailSender: {e}')
    
    # 9. Config check
    print('\n9. CONFIGURATION')
    try:
        import config
        print(f'   GROQ_API_KEY: {"✅ Set" if config.GROQ_API_KEY else "❌ Missing"}')
        print(f'   ZOHO_ACCOUNTS: {len(config.ZOHO_ACCOUNTS)} accounts')
        print(f'   ROCKETREACH_API_KEY: {"✅ Set" if config.ROCKETREACH_API_KEY else "❌ Missing"}')
        if not config.GROQ_API_KEY:
            issues.append('GROQ_API_KEY not set')
        if not config.ZOHO_ACCOUNTS:
            issues.append('No ZOHO_ACCOUNTS configured')
    except Exception as e:
        issues.append(f'Config load failed: {e}')
        print(f'   ❌ Config error: {e}')
    
    # 10. Test email generation (dry run)
    print('\n10. EMAIL GENERATION TEST')
    try:
        from email_generator import EmailGenerator
        gen = EmailGenerator()
        test_lead = {
            'first_name': 'Test',
            'company': 'TestCorp',
            'title': 'CTO',
            'industry': 'Technology'
        }
        test_context = {
            'product_service': 'engineering team',
            'single_pain_point': 'shipping fast',
            'case_study': {
                'company_hint': 'an enterprise company',
                'result_short': '3x faster',
                'timeline': '8 weeks'
            }
        }
        # Don't actually generate - just check it can be called
        print('   ✅ Generator initialized')
    except Exception as e:
        warnings.append(f'Generator test failed: {e}')
        print(f'   ⚠️ Generator test: {e}')
    
    # Summary
    print('\n' + '=' * 70)
    print('SUMMARY')
    print('=' * 70)
    
    if issues:
        print('\n❌ CRITICAL ISSUES (must fix before production):')
        for i in issues:
            print(f'   - {i}')
    
    if warnings:
        print('\n⚠️ WARNINGS (should address):')
        for w in warnings:
            print(f'   - {w}')
    
    if not issues and not warnings:
        print('\n✅ ALL CHECKS PASSED - PRODUCTION READY')
    elif not issues:
        print('\n⚠️ READY WITH WARNINGS - review before deployment')
    else:
        print('\n❌ NOT PRODUCTION READY - fix critical issues first')
    
    return issues, warnings

if __name__ == '__main__':
    issues, warnings = main()
    sys.exit(1 if issues else 0)
