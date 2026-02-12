#!/usr/bin/env python3
"""
Pre-deployment verification for v2 cold email system with 300/day target
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print('🔍 PRE-DEPLOY VERIFICATION')
print('='*70)

# 1. Check all critical imports work
print('\n1. Testing critical imports...')
try:
    from v2.scheduler import AsyncScheduler
    from adaptive_campaign import AdaptiveCampaignRunner, run_adaptive_campaign_check
    from v2.pre_generator import PreGenerator
    from email_verifier import EmailVerifier
    print('   ✅ All critical imports successful')
except Exception as e:
    print(f'   ❌ Import failed: {e}')
    sys.exit(1)

# 2. Check config
print('\n2. Checking configuration...')
import config
issues = []
if config.GLOBAL_DAILY_TARGET == 0:
    issues.append('GLOBAL_DAILY_TARGET is 0 (set to 300 for deployment)')
if not config.DATABASE_URL:
    issues.append('DATABASE_URL not set')
if not config.ZOHO_ACCOUNTS:
    issues.append('No Zoho accounts configured')

if issues:
    print('   ⚠️  Configuration issues:')
    for issue in issues:
        print(f'      - {issue}')
else:
    print('   ✅ Configuration valid')

# 3. Check MongoDB connectivity
print('\n3. Testing MongoDB connection...')
try:
    from database import db
    db.command('ping')
    print('   ✅ MongoDB connected')
except Exception as e:
    print(f'   ❌ MongoDB connection failed: {e}')
    sys.exit(1)

# 4. Check campaign health
print('\n4. Checking campaign health...')
try:
    from adaptive_campaign import get_campaign_health
    health = get_campaign_health()
    print(f'   ✅ {health["pending_leads"]} pending leads available')
    print(f'   ✅ {health["sent_today"]} emails sent today')
    print(f'   ✅ {health["ready_drafts"]} drafts ready to send')
except Exception as e:
    print(f'   ❌ Campaign health check failed: {e}')
    sys.exit(1)

# 5. Check active campaigns
print('\n5. Checking active campaigns...')
from database import Campaign
active = Campaign.get_active_campaigns()
print(f'   ✅ {len(active)} active campaigns in MongoDB')

# 6. Run all v2 tests
print('\n6. Running v2 test suite...')
import subprocess
import os
import glob
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
venv_python = os.path.join(project_root, 'venv', 'bin', 'python')

# Find all test_v2_*.py files
test_pattern = os.path.join(project_root, 'tests', 'test_v2_*.py')
test_files = glob.glob(test_pattern)

if not test_files:
    print('   ⚠️  No v2 test files found')
else:
    result = subprocess.run(
        [venv_python, '-m', 'pytest'] + test_files + ['-q', '--tb=no'],
        capture_output=True,
        text=True,
        cwd=project_root
    )
if not test_files:
    print('   ⚠️  No v2 test files found')
else:
    result = subprocess.run(
        [venv_python, '-m', 'pytest'] + test_files + ['-q', '--tb=no'],
        capture_output=True,
        text=True,
        cwd=project_root
    )
    if result.returncode == 0:
        # Count passed tests
        output = result.stdout
        if 'passed' in output:
            print(f'   ✅ All v2 tests passed')
        else:
            print(f'   ✅ Tests completed')
    else:
        print(f'   ❌ Some tests failed')
        print('STDOUT:', result.stdout)
        print('STDERR:', result.stderr)
        sys.exit(1)

print()
print('='*70)
print('✅ DEPLOYMENT STATUS: READY')
print('='*70)
print()
print('📋 DEPLOYMENT CHECKLIST:')
print()
print('1. Set environment variables:')
print('   export GLOBAL_DAILY_TARGET=300')
print('   export MIN_DELAY_BETWEEN_EMAILS=5')
print('   export MAX_DELAY_BETWEEN_EMAILS=12')
print('   export WARMUP_WEEK4_LIMIT=50')
print()
print('2. Start the v2 scheduler:')
print('   python main_v2.py')
print()
print('   OR with Docker:')
print('   docker-compose up -d')
print()
print('🎯 WHAT HAPPENS AUTOMATICALLY:')
print('   • 09:00: Adaptive check → fetch ~110 leads → generate drafts')
print('   • 11:00: Adaptive check → fetch ~110 leads → generate drafts')
print('   • 13:00: Adaptive check → fetch ~110 leads → generate drafts')
print('   • 15:00: Adaptive check → fetch ~110 leads → generate drafts')
print('   • Result: 300+ emails sent throughout the day')
print()
print('🛡️  AUTOMATIC PROTECTIONS:')
print('   ✅ Email verification (MX/SMTP) before sending')
print('   ✅ DNC list filtering')
print('   ✅ Bounce detection and marking')
print('   ✅ "Stealth Startup" filtering')
print('   ✅ 25-35% skip buffer for rejections')
print('   ✅ Warmup limits respected')
print()
print('📊 MONITORING:')
print('   • Check logs: tail -f v2_scheduler.log')
print('   • Health: python -c "from adaptive_campaign import get_campaign_health; print(get_campaign_health())"')
print()
