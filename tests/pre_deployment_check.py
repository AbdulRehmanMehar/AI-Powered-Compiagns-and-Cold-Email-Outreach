#!/usr/bin/env python3
"""
Pre-Deployment Analysis for Ollama Setup
Comprehensive system readiness check before deployment
"""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def print_header(title):
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)

def print_status(check, status, details=""):
    icons = {"pass": "✅", "fail": "❌", "warn": "⚠️", "info": "ℹ️"}
    icon = icons.get(status, "•")
    print(f"{icon} {check}")
    if details:
        for line in details.split("\n"):
            if line.strip():
                print(f"   {line}")

# Track results
issues = []
warnings = []
passes = []

print_header("PRE-DEPLOYMENT SYSTEM ANALYSIS")
print("\nDate: February 10, 2026")
print("Target: Ollama Migration\n")

# =============================================================================
# 1. OLLAMA CONNECTIVITY
# =============================================================================
print_header("1. OLLAMA CONNECTIVITY")

ollama_working = False
ollama_url = None

import requests

for url in ['http://localhost:11434', 'http://127.0.0.1:11434', 'http://192.168.1.9:11434']:
    try:
        response = requests.get(f'{url}/api/version', timeout=2)
        if response.status_code == 200:
            ollama_url = url
            ollama_working = True
            try:
                version_data = response.json()
                print_status(f"Ollama running at {url}", "pass", f"Version: {version_data}")
            except:
                print_status(f"Ollama running at {url}", "pass", "Server responding")
            passes.append(f"Ollama accessible at {url}")
            break
    except requests.exceptions.ConnectionError:
        print_status(f"Checking {url}", "fail", "Connection refused")
    except Exception as e:
        print_status(f"Checking {url}", "fail", str(e))

if not ollama_working:
    issues.append("CRITICAL: Ollama is not running or not accessible")
    print_status("\nOllama Status", "fail", 
                "Ollama is not running!\n"
                "Start it with: ollama serve\n"
                "Or check if it's running on a different port")

# =============================================================================
# 2. OLLAMA MODELS
# =============================================================================
print_header("2. OLLAMA MODELS")

required_model = "qwen2.5:7b"
model_installed = False

if ollama_working:
    try:
        response = requests.get(f'{ollama_url}/api/tags', timeout=2)
        if response.status_code == 200:
            data = response.json()
            models = data.get('models', [])
            
            print_status(f"Installed models: {len(models)}", "info")
            
            if models:
                model_names = []
                for model in models:
                    name = model.get('name', 'unknown')
                    size = model.get('size', 0) / (1024**3)
                    model_names.append(name)
                    print(f"   - {name} ({size:.2f} GB)")
                
                if required_model in model_names:
                    model_installed = True
                    print_status(f"\nRequired model '{required_model}' found", "pass")
                    passes.append(f"Model {required_model} installed")
                else:
                    issues.append(f"CRITICAL: Required model '{required_model}' not installed")
                    print_status(f"\nRequired model '{required_model}' NOT found", "fail",
                               f"Install with: ollama pull {required_model}")
            else:
                issues.append("CRITICAL: No models installed in Ollama")
                print_status("No models installed", "fail",
                           f"Install with: ollama pull {required_model}")
    except Exception as e:
        warnings.append(f"Could not check Ollama models: {e}")
        print_status("Model check failed", "warn", str(e))
else:
    print_status("Skipped", "warn", "Ollama not running")

# =============================================================================
# 3. OLLAMA API TEST
# =============================================================================
print_header("3. OLLAMA API TEST")

if ollama_working and model_installed:
    try:
        payload = {
            'model': required_model,
            'prompt': 'Say just "WORKING" if you can read this.',
            'stream': False,
            'options': {'temperature': 0.1, 'num_predict': 5}
        }
        
        print_status("Testing Ollama text generation...", "info")
        response = requests.post(f'{ollama_url}/api/generate', json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            text = result.get('response', '').strip()
            duration = result.get('total_duration', 0) / 1e9
            
            print_status("Ollama API test", "pass",
                        f"Response: {text[:50]}\n"
                        f"Duration: {duration:.2f}s\n"
                        f"Tokens: {result.get('eval_count', 0)}")
            passes.append("Ollama API working correctly")
        else:
            issues.append(f"Ollama API returned status {response.status_code}")
            print_status("Ollama API test", "fail", f"Status: {response.status_code}")
            
    except requests.exceptions.Timeout:
        warnings.append("Ollama API timeout (model may be loading)")
        print_status("Ollama API test", "warn", "Timeout - model might still be loading")
    except Exception as e:
        issues.append(f"Ollama API error: {e}")
        print_status("Ollama API test", "fail", str(e))
else:
    print_status("Skipped", "warn", "Ollama or model not available")

# =============================================================================
# 4. DATABASE CONNECTION
# =============================================================================
print_header("4. DATABASE CONNECTION")

from dotenv import load_dotenv
load_dotenv()

db_url = os.getenv('DATABASE_URL')

if db_url:
    from pymongo import MongoClient
    
    # Check for Docker hostnames
    if 'host.docker.internal' in db_url:
        warnings.append("DATABASE_URL uses Docker hostname (host.docker.internal)")
        print_status("Database URL contains 'host.docker.internal'", "warn",
                    "This only works inside Docker containers!\n"
                    "For native Python, use: 192.168.1.9 or localhost")
    
    print_status(f"Connecting to: {db_url[:60]}...", "info")
    
    try:
        client = MongoClient(db_url, serverSelectionTimeoutMS=3000)
        client.server_info()
        
        db = client.get_database()
        collections = db.list_collection_names()
        
        # Get stats
        stats = []
        if 'leads' in collections:
            total = db.leads.count_documents({})
            pending = db.leads.count_documents({'status': 'pending'})
            stats.append(f"Leads: {total} total, {pending} pending")
        
        if 'campaigns' in collections:
            total = db.campaigns.count_documents({})
            stats.append(f"Campaigns: {total}")
        
        if 'emails' in collections:
            total = db.emails.count_documents({})
            sent = db.emails.count_documents({'status': 'sent'})
            stats.append(f"Emails: {total} total, {sent} sent")
        
        print_status("MongoDB connection", "pass", "\n".join(stats))
        passes.append("MongoDB accessible")
        client.close()
        
    except Exception as e:
        issues.append(f"CRITICAL: MongoDB connection failed: {e}")
        print_status("MongoDB connection", "fail", str(e))
else:
    issues.append("CRITICAL: DATABASE_URL not set")
    print_status("DATABASE_URL", "fail", "Not found in .env")

# =============================================================================
# 5. CONFIGURATION FILES
# =============================================================================
print_header("5. CONFIGURATION FILES")

# Check .env
if os.path.exists('.env'):
    with open('.env', 'r') as f:
        env_content = f.read()
    
    env_vars = {}
    for line in env_content.split('\n'):
        if '=' in line and not line.strip().startswith('#'):
            key = line.split('=')[0].strip()
            env_vars[key] = True
    
    print_status(".env file exists", "pass", f"{len(env_vars)} variables configured")
    
    # Check key variables
    critical_vars = ['DATABASE_URL', 'ZOHO_EMAILS', 'ZOHO_PASSWORDS', 'ROCKETREACH_API_KEY']
    missing_vars = [v for v in critical_vars if v not in env_vars]
    
    if missing_vars:
        warnings.append(f"Missing variables in .env: {', '.join(missing_vars)}")
        print_status("Critical variables", "warn", f"Missing: {', '.join(missing_vars)}")
    else:
        print_status("Critical variables", "pass", "All present")
    
    # Check LLM provider
    llm_provider = os.getenv('LLM_PROVIDER', '').lower()
    print_status(f"Current LLM_PROVIDER", "info", f"{llm_provider or 'not set (defaults to groq)'}")
    
else:
    issues.append("CRITICAL: .env file not found")
    print_status(".env file", "fail", "File not found")

# Check stack.env
if os.path.exists('stack.env'):
    with open('stack.env', 'r') as f:
        stack_content = f.read()
    
    stack_vars = {}
    for line in stack_content.split('\n'):
        if '=' in line and not line.strip().startswith('#'):
            key, value = line.split('=', 1)
            stack_vars[key.strip()] = value.strip()
    
    print_status("\nstack.env file exists", "info", f"{len(stack_vars)} variables")
    
    # Check if it has Docker hostnames
    if 'DATABASE_URL' in stack_vars and 'host.docker.internal' in stack_vars['DATABASE_URL']:
        warnings.append("stack.env is configured for Docker (host.docker.internal)")
        print_status("stack.env configuration", "warn",
                    "Uses Docker hostnames (host.docker.internal)\n"
                    "Won't work for native Python execution")
    
    # Check LLM provider
    if stack_vars.get('LLM_PROVIDER') == 'ollama':
        print_status("stack.env LLM_PROVIDER", "info", "Set to 'ollama' ✓")
    
else:
    print_status("stack.env file", "info", "Not found (optional)")

# =============================================================================
# 6. PYTHON DEPENDENCIES
# =============================================================================
print_header("6. PYTHON DEPENDENCIES")

import sys
print_status("Python version", "info", sys.version.split()[0])

required_packages = ['pymongo', 'requests', 'schedule', 'pytz', 'dotenv', 'groq']
missing = []

for package in required_packages:
    try:
        if package == 'dotenv':
            __import__('dotenv')
        else:
            __import__(package)
        print(f"   ✅ {package}")
    except ImportError:
        missing.append(package)
        print(f"   ❌ {package}")

if missing:
    issues.append(f"Missing Python packages: {', '.join(missing)}")
    print_status("\nDependencies", "fail", f"Run: pip install {' '.join(missing)}")
else:
    print_status("\nAll dependencies", "pass", "Installed")
    passes.append("All dependencies installed")

# =============================================================================
# 7. PRIORITY 1 FIXES
# =============================================================================
print_header("7. PRIORITY 1 FIXES STATUS")

try:
    from email_generator import get_circuit_breaker
    breaker = get_circuit_breaker()
    print_status("Circuit Breaker", "pass",
                f"State: {breaker.state}\n"
                f"Threshold: {breaker.failure_threshold} failures\n"
                f"Timeout: {breaker.timeout}s")
    passes.append("Circuit breaker implemented")
except Exception as e:
    warnings.append(f"Circuit breaker check failed: {e}")
    print_status("Circuit Breaker", "warn", str(e))

try:
    from auto_scheduler import AutoScheduler
    scheduler = AutoScheduler()
    if hasattr(scheduler, 'check_system_health'):
        print_status("Health Monitoring", "pass", "check_system_health() method exists")
        passes.append("Health monitoring implemented")
    else:
        warnings.append("Health monitoring method not found")
        print_status("Health Monitoring", "warn", "Method not found")
except Exception as e:
    warnings.append(f"Health monitoring check failed: {e}")
    print_status("Health Monitoring", "warn", str(e))

# =============================================================================
# 8. RUNNING PROCESSES
# =============================================================================
print_header("8. RUNNING PROCESSES")

import subprocess
try:
    result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    processes = result.stdout
    
    # Check for Ollama
    if 'ollama' in processes.lower():
        print_status("Ollama process", "pass", "Running")
    else:
        warnings.append("Ollama process not found in ps aux")
        print_status("Ollama process", "warn", "Not found - may be running as service")
    
    # Check for auto_scheduler
    if 'auto_scheduler' in processes:
        issues.append("auto_scheduler already running - will cause conflicts")
        print_status("auto_scheduler", "warn", "Already running - kill before deploying")
    else:
        print_status("auto_scheduler", "pass", "Not running (ready for fresh start)")
        
except Exception as e:
    print_status("Process check", "warn", f"Could not check: {e}")

# =============================================================================
# FINAL REPORT
# =============================================================================
print_header("DEPLOYMENT READINESS REPORT")

print(f"\n📊 Summary:")
print(f"   ✅ Passed:   {len(passes)}")
print(f"   ⚠️  Warnings: {len(warnings)}")
print(f"   ❌ Failed:   {len(issues)}")

if issues:
    print(f"\n🚨 CRITICAL ISSUES ({len(issues)}):")
    for i, issue in enumerate(issues, 1):
        print(f"   {i}. {issue}")

if warnings:
    print(f"\n⚠️  WARNINGS ({len(warnings)}):")
    for i, warning in enumerate(warnings, 1):
        print(f"   {i}. {warning}")

if passes:
    print(f"\n✅ PASSED CHECKS ({len(passes)}):")
    for i, check in enumerate(passes, 1):
        print(f"   {i}. {check}")

# =============================================================================
# DEPLOYMENT DECISION
# =============================================================================
print("\n" + "="*70)

if len(issues) == 0:
    if len(warnings) == 0:
        print("🟢 DEPLOYMENT: GO AHEAD")
        print("="*70)
        print("\nAll systems are ready for Ollama deployment!")
        print("\nNext steps:")
        print("1. Backup current .env: cp .env .env.backup")
        print("2. Fix stack.env hostnames if using natively")
        print("3. Copy stack.env to .env: cp stack.env .env")
        print("4. Start scheduler: python auto_scheduler.py")
        sys.exit(0)
    else:
        print("🟡 DEPLOYMENT: PROCEED WITH CAUTION")
        print("="*70)
        print("\nSystem is mostly ready, but has warnings.")
        print("Review warnings above and proceed if acceptable.")
        print("\nRecommendation: Fix warnings first for best results.")
        sys.exit(0)
else:
    print("🔴 DEPLOYMENT: DO NOT PROCEED")
    print("="*70)
    print("\nCritical issues must be fixed before deployment!")
    print("See issues list above for required actions.")
    sys.exit(1)
