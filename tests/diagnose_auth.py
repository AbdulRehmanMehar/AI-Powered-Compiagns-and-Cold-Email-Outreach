#!/usr/bin/env python3
"""Diagnose email authentication issues."""
import subprocess
import sys

print("=== EMAIL AUTHENTICATION DIAGNOSTIC ===\n")

domains = ['primestrides.com', 'theabdulrehman.com']

for domain in domains:
    print(f"\n{'='*60}")
    print(f"Domain: {domain}")
    print('='*60)
    
    # Check SPF
    print(f"\n1. SPF Record:")
    try:
        result = subprocess.run(
            ['dig', f'{domain}', 'TXT', '+short'],
            capture_output=True,
            text=True,
            timeout=5
        )
        txt_records = result.stdout.strip().split('\n')
        spf_records = [r for r in txt_records if 'v=spf1' in r]
        
        if spf_records:
            for spf in spf_records:
                print(f"   ✅ Found: {spf[:80]}...")
        else:
            print(f"   ❌ NO SPF RECORD FOUND")
            print(f"   All TXT records:")
            for r in txt_records[:3]:
                print(f"      {r[:80]}")
                
    except Exception as e:
        print(f"   ❌ Error checking SPF: {e}")
    
    # Check DKIM (Zoho specific)
    print(f"\n2. DKIM (Zoho expects zmail._domainkey):")
    try:
        result = subprocess.run(
            ['dig', f'zmail._domainkey.{domain}', 'CNAME', '+short'],
            capture_output=True,
            text=True,
            timeout=5
        )
        cname = result.stdout.strip()
        if cname:
            print(f"   ✅ Found CNAME: {cname}")
        else:
            print(f"   ⚠️  No CNAME found (Zoho may auto-sign, check mail config)")
            
    except Exception as e:
        print(f"   ⚠️  Error checking DKIM: {e}")
    
    # Check DMARC
    print(f"\n3. DMARC Policy:")
    try:
        result = subprocess.run(
            ['dig', f'_dmarc.{domain}', 'TXT', '+short'],
            capture_output=True,
            text=True,
            timeout=5
        )
        dmarc = result.stdout.strip()
        if dmarc and 'v=DMARC1' in dmarc:
            print(f"   ✅ Found: {dmarc[:80]}...")
        elif dmarc:
            print(f"   Found: {dmarc[:80]}...")
        else:
            print(f"   ⚠️  No DMARC record (optional, but good practice)")
            
    except Exception as e:
        print(f"   ⚠️  Error checking DMARC: {e}")

print("\n" + "="*60)
print("WHAT THIS MEANS:")
print("="*60)
print("""
✅ If you see SPF record:
   - Your domain allows Zoho to send emails
   - SPF should include: include:zoho.com or IP ranges

❌ If NO SPF record:
   - **THIS IS YOUR PROBLEM** — Gmail will reject/spam folder
   - You MUST add SPF record to domain DNS
   - Typical Zoho SPF: v=spf1 include:zoho.com ~all

Next Steps:
1. Check your domain DNS control panel (GoDaddy, Namecheap, etc.)
2. Add TXT record: v=spf1 include:zoho.com ~all
3. Wait 24 hours for DNS propagation
4. Re-test sending to your Gmail account
5. If still in spam, check Gmail Security Settings for "Less secure apps"

Gmail specific issues:
- New domains/IPs get filtered even with good auth
- You may need to send 50-100 legitimate emails first
- Watch https://gmail.com/postmaster in your account
""")
