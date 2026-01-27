"""
Email Verification Service

Verifies email addresses before sending to reduce bounces.
Uses multiple verification methods:
1. Syntax validation
2. Domain MX record check
3. SMTP verification (checks if mailbox exists)
4. Disposable/temporary email detection
5. Role-based email detection

This can reduce bounce rates from 40%+ to under 5%.
"""

import re
import dns.resolver
import smtplib
import socket
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import time


class VerificationStatus(Enum):
    VALID = "valid"
    INVALID = "invalid"
    RISKY = "risky"  # Catch-all domains, etc.
    UNKNOWN = "unknown"  # Couldn't verify


@dataclass
class VerificationResult:
    email: str
    status: VerificationStatus
    score: int  # 0-100, higher = more likely valid
    checks: Dict[str, bool]
    reason: str
    
    def is_safe_to_send(self) -> bool:
        """Returns True if email is safe to send to"""
        return self.status == VerificationStatus.VALID and self.score >= 70


# Disposable email domains (incomplete list - should use API for comprehensive check)
DISPOSABLE_DOMAINS = {
    'tempmail.com', 'throwaway.email', 'guerrillamail.com', 'mailinator.com',
    '10minutemail.com', 'temp-mail.org', 'fakeinbox.com', 'trashmail.com',
    'yopmail.com', 'getnada.com', 'maildrop.cc', 'dispostable.com'
}

# Role-based prefixes that often bounce or go to team inboxes
ROLE_BASED_PREFIXES = {
    'info', 'support', 'admin', 'contact', 'hello', 'sales', 'team', 
    'office', 'hr', 'jobs', 'careers', 'marketing', 'press', 'media',
    'help', 'service', 'billing', 'webmaster', 'postmaster', 'abuse',
    'noreply', 'no-reply', 'donotreply', 'newsletter'
}

# Known problematic domains (high bounce rates)
PROBLEMATIC_DOMAINS = {
    # Add domains that have historically bounced
}


class EmailVerifier:
    """Verify email addresses before sending"""
    
    def __init__(self, smtp_timeout: int = 10, skip_smtp_verify: bool = False):
        """
        Args:
            smtp_timeout: Timeout for SMTP connections
            skip_smtp_verify: If True, skip SMTP mailbox verification (faster but less accurate)
        """
        self.smtp_timeout = smtp_timeout
        self.skip_smtp_verify = skip_smtp_verify
        self._dns_cache = {}
    
    def verify(self, email: str) -> VerificationResult:
        """
        Verify an email address with multiple checks.
        
        Returns VerificationResult with status and score.
        """
        email = email.lower().strip()
        checks = {}
        score = 100
        reasons = []
        
        # 1. Syntax check
        checks['syntax'] = self._check_syntax(email)
        if not checks['syntax']:
            return VerificationResult(
                email=email,
                status=VerificationStatus.INVALID,
                score=0,
                checks=checks,
                reason="Invalid email syntax"
            )
        
        local_part, domain = email.rsplit('@', 1)
        
        # 2. Check for disposable domains
        checks['not_disposable'] = domain not in DISPOSABLE_DOMAINS
        if not checks['not_disposable']:
            return VerificationResult(
                email=email,
                status=VerificationStatus.INVALID,
                score=0,
                checks=checks,
                reason="Disposable email domain"
            )
        
        # 3. Check for role-based emails
        checks['not_role_based'] = not any(
            local_part == prefix or local_part.startswith(f"{prefix}.") or local_part.startswith(f"{prefix}_")
            for prefix in ROLE_BASED_PREFIXES
        )
        if not checks['not_role_based']:
            score -= 30
            reasons.append("Role-based email")
        
        # 4. Check MX records
        mx_records = self._get_mx_records(domain)
        checks['has_mx'] = len(mx_records) > 0
        if not checks['has_mx']:
            return VerificationResult(
                email=email,
                status=VerificationStatus.INVALID,
                score=0,
                checks=checks,
                reason="Domain has no MX records"
            )
        
        # 5. Check for problematic domains
        checks['not_problematic'] = domain not in PROBLEMATIC_DOMAINS
        if not checks['not_problematic']:
            score -= 50
            reasons.append("Known problematic domain")
        
        # 6. SMTP verification (most accurate but slower)
        if not self.skip_smtp_verify:
            smtp_result = self._verify_smtp(email, mx_records[0])
            checks['smtp_valid'] = smtp_result['valid']
            checks['is_catch_all'] = smtp_result.get('catch_all', False)
            
            if not smtp_result['valid']:
                return VerificationResult(
                    email=email,
                    status=VerificationStatus.INVALID,
                    score=0,
                    checks=checks,
                    reason=f"SMTP verification failed: {smtp_result.get('error', 'Unknown')}"
                )
            
            if smtp_result.get('catch_all'):
                score -= 20
                reasons.append("Catch-all domain (can't verify individual mailbox)")
        else:
            checks['smtp_valid'] = None
            checks['is_catch_all'] = None
        
        # 7. Additional heuristics
        # Short local parts are more likely to be valid
        if len(local_part) < 3:
            score -= 10
            reasons.append("Very short local part")
        
        # Too many numbers might indicate auto-generated
        digit_ratio = sum(c.isdigit() for c in local_part) / len(local_part) if local_part else 0
        if digit_ratio > 0.5:
            score -= 15
            reasons.append("High digit ratio in local part")
        
        # Determine final status
        if score >= 70:
            status = VerificationStatus.VALID
        elif score >= 40:
            status = VerificationStatus.RISKY
        else:
            status = VerificationStatus.INVALID
        
        return VerificationResult(
            email=email,
            status=status,
            score=max(0, score),
            checks=checks,
            reason="; ".join(reasons) if reasons else "All checks passed"
        )
    
    def _check_syntax(self, email: str) -> bool:
        """Validate email syntax"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _get_mx_records(self, domain: str) -> list:
        """Get MX records for domain with caching"""
        if domain in self._dns_cache:
            return self._dns_cache[domain]
        
        try:
            records = dns.resolver.resolve(domain, 'MX')
            mx_hosts = [str(r.exchange).rstrip('.') for r in sorted(records, key=lambda x: x.preference)]
            self._dns_cache[domain] = mx_hosts
            return mx_hosts
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout):
            self._dns_cache[domain] = []
            return []
        except Exception:
            return []
    
    def _verify_smtp(self, email: str, mx_host: str) -> Dict:
        """
        Verify email via SMTP.
        
        This connects to the mail server and checks if the mailbox exists.
        Note: Some servers don't give accurate responses (catch-all, greylisting).
        """
        result = {'valid': False, 'catch_all': False, 'error': None}
        
        try:
            # Connect to MX server
            smtp = smtplib.SMTP(timeout=self.smtp_timeout)
            smtp.connect(mx_host, 25)
            smtp.helo('verify.primestrides.com')
            
            # Check sender
            smtp.mail('verify@primestrides.com')
            
            # Check if recipient exists
            code, message = smtp.rcpt(email)
            
            if code == 250:
                result['valid'] = True
                
                # Check for catch-all by testing a random address
                random_email = f"definitely_not_real_xyz123@{email.split('@')[1]}"
                catch_code, _ = smtp.rcpt(random_email)
                if catch_code == 250:
                    result['catch_all'] = True
            elif code == 550:
                result['valid'] = False
                result['error'] = "Mailbox does not exist"
            else:
                # Unknown response - mark as risky
                result['valid'] = True  # Assume valid but risky
                result['error'] = f"Uncertain response: {code}"
            
            smtp.quit()
            
        except smtplib.SMTPServerDisconnected:
            result['valid'] = True  # Server disconnected - assume valid (greylisting)
            result['error'] = "Server disconnected (possible greylisting)"
        except socket.timeout:
            result['valid'] = True  # Timeout - assume valid
            result['error'] = "Connection timeout"
        except Exception as e:
            result['valid'] = True  # Error - assume valid to avoid false negatives
            result['error'] = str(e)
        
        return result
    
    def verify_batch(self, emails: list, delay: float = 0.5) -> Dict[str, VerificationResult]:
        """
        Verify multiple emails with rate limiting.
        
        Args:
            emails: List of email addresses
            delay: Delay between verifications (seconds)
        
        Returns:
            Dict mapping email to VerificationResult
        """
        results = {}
        for email in emails:
            results[email] = self.verify(email)
            time.sleep(delay)
        return results


def quick_verify(email: str) -> Tuple[bool, str]:
    """
    Quick email verification without SMTP check.
    Faster but less accurate - good for initial filtering.
    
    Returns (is_valid, reason)
    """
    verifier = EmailVerifier(skip_smtp_verify=True)
    result = verifier.verify(email)
    return result.is_safe_to_send(), result.reason


def full_verify(email: str) -> VerificationResult:
    """
    Full email verification including SMTP check.
    Slower but more accurate - use before sending.
    """
    verifier = EmailVerifier(skip_smtp_verify=False)
    return verifier.verify(email)


# Test
if __name__ == "__main__":
    test_emails = [
        "test@gmail.com",
        "info@company.com",  # Role-based
        "test@tempmail.com",  # Disposable
        "invalid-email",  # Bad syntax
        "user@nonexistentdomain12345.com",  # No MX
    ]
    
    print("Email Verification Test")
    print("=" * 60)
    
    verifier = EmailVerifier(skip_smtp_verify=True)  # Skip SMTP for quick test
    
    for email in test_emails:
        result = verifier.verify(email)
        print(f"\n{email}")
        print(f"  Status: {result.status.value}")
        print(f"  Score: {result.score}")
        print(f"  Safe to send: {result.is_safe_to_send()}")
        print(f"  Reason: {result.reason}")
