#!/usr/bin/env python3
"""
Comprehensive log analyzer for cold email system
Analyzes _coldemails_logs.txt for bugs, performance issues, and patterns
"""

import re
from collections import Counter, defaultdict
from datetime import datetime

def analyze_logs(filename="_coldemails_logs.txt"):
    """Analyze the log file thoroughly"""
    
    with open(filename, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    
    print("=" * 80)
    print("COMPREHENSIVE LOG ANALYSIS")
    print("=" * 80)
    print(f"\nTotal lines: {len(lines)}")
    
    # 1. Count critical events
    print("\n" + "=" * 80)
    print("1. CRITICAL EVENTS")
    print("=" * 80)
    
    emails_sent = len(re.findall(r'✉️  Sent to', content))
    failed_campaigns = len(re.findall(r'❌ Scheduled campaign failed', content))
    errors = len(re.findall(r'ERROR|Exception|Traceback', content, re.IGNORECASE))
    warnings = len(re.findall(r'WARNING:', content))
    
    print(f"✉️  Emails successfully sent: {emails_sent}")
    print(f"❌ Campaign failures: {failed_campaigns}")
    print(f"🔴 Errors/Exceptions: {errors}")
    print(f"⚠️  Warnings: {warnings}")
    
    # 2. Analyze skipped leads
    print("\n" + "=" * 80)
    print("2. SKIPPED LEADS BREAKDOWN")
    print("=" * 80)
    
    skipped_patterns = {
        'RocketReach invalid': r'⛔ Skipping .* - RocketReach marked INVALID',
        'MX/SMTP failed': r'⛔ Skipping .* - failed MX/SMTP verification',
        'Already contacted': r'⏭️  Skipping .* - already contacted',
        'Previously bounced': r'⛔ Skipping .* - previously bounced',
        'Marked invalid': r'⛔ Skipping .* - marked invalid',
    }
    
    for pattern_name, pattern in skipped_patterns.items():
        count = len(re.findall(pattern, content))
        print(f"  {pattern_name}: {count}")
    
    # 3. API Rate Limit Analysis
    print("\n" + "=" * 80)
    print("3. API RATE LIMIT ISSUES")
    print("=" * 80)
    
    rate_limit_429 = len(re.findall(r'429 Too Many Requests', content))
    rate_limit_exceeded = len(re.findall(r'rate_limit_exceeded', content))
    model_depleted = len(re.findall(r'marked as depleted', content))
    
    print(f"  429 errors: {rate_limit_429}")
    print(f"  Rate limit exceeded messages: {rate_limit_exceeded}")
    print(f"  Models marked depleted: {model_depleted}")
    
    # Extract which models hit limits
    models_hit = re.findall(r'Model ([\w/-]+) marked as depleted', content)
    if models_hit:
        model_counts = Counter(models_hit)
        print(f"\n  Models hitting limits:")
        for model, count in model_counts.most_common():
            print(f"    - {model}: {count} times")
    
    # 4. Email Review Analysis
    print("\n" + "=" * 80)
    print("4. EMAIL REVIEW QUALITY")
    print("=" * 80)
    
    passed_reviews = len(re.findall(r'✅ Email passed review', content))
    passed_warnings = len(re.findall(r'⚠️ Email passed with warnings', content))
    failed_reviews = len(re.findall(r'❌ Review failed', content))
    
    print(f"  ✅ Passed: {passed_reviews}")
    print(f"  ⚠️  Passed with warnings: {passed_warnings}")
    print(f"  ❌ Failed: {failed_reviews}")
    
    # Extract failed review scores
    failed_scores = re.findall(r'❌ Review failed.*?score: (\d+)', content))
    if failed_scores:
        scores = [int(s) for s in failed_scores]
        print(f"  Average failed score: {sum(scores)/len(scores):.1f}")
        print(f"  Failed score range: {min(scores)}-{max(scores)}")
    
    # 5. Enrichment Issues
    print("\n" + "=" * 80)
    print("5. LEAD ENRICHMENT ISSUES")
    print("=" * 80)
    
    enrichment_failed = len(re.findall(r'⚠️ Enrichment failed', content))
    no_domain = len(re.findall(r'no_domain - will use fallback', content))
    fetch_failed = len(re.findall(r'fetch_failed - will use fallback', content))
    
    print(f"  Total enrichment failures: {enrichment_failed}")
    print(f"    - No domain found: {no_domain}")
    print(f"    - Fetch failed: {fetch_failed}")
    
    # 6. The Fatal Bug
    print("\n" + "=" * 80)
    print("6. THE FATAL BUG (FIXED)")
    print("=" * 80)
    
    nonetype_errors = re.findall(r"'NoneType' object has no attribute 'lower'", content)
    print(f"  NoneType.lower() crashes: {len(nonetype_errors)}")
    
    if nonetype_errors:
        # Find context around the error
        error_lines = [i for i, line in enumerate(lines) if "'NoneType' object has no attribute 'lower'" in line]
        for line_num in error_lines[:3]:  # Show first 3
            context_start = max(0, line_num - 2)
            context_end = min(len(lines), line_num + 3)
            print(f"\n  Error at line {line_num}:")
            for i in range(context_start, context_end):
                prefix = "  >>> " if i == line_num else "      "
                print(f"{prefix}{lines[i][:100]}")
    
    # 7. Timeline Analysis
    print("\n" + "=" * 80)
    print("7. TIMELINE ANALYSIS")
    print("=" * 80)
    
    timestamps = re.findall(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) EST\]', content)
    if timestamps:
        first_activity = timestamps[0]
        last_activity = timestamps[-1]
        print(f"  First activity: {first_activity} EST")
        print(f"  Last activity: {last_activity} EST")
        print(f"  Total timestamps: {len(timestamps)}")
    
    # 8. Specific Error Patterns
    print("\n" + "=" * 80)
    print("8. SPECIFIC ERROR PATTERNS")
    print("=" * 80)
    
    error_patterns = {
        '503 Service Unavailable': r'Error code: 503',
        'Connection failures': r'Server disconnected',
        'AI generation failed': r'AI pain point generation failed',
        'Email generation errors': r'Error generating email',
    }
    
    for error_type, pattern in error_patterns.items():
        count = len(re.findall(pattern, content))
        if count > 0:
            print(f"  {error_type}: {count}")
    
    # 9. Success Rate
    print("\n" + "=" * 80)
    print("9. OVERALL SUCCESS METRICS")
    print("=" * 80)
    
    total_processing_attempts = len(re.findall(r'📧 Generating email for', content))
    success_rate = (emails_sent / total_processing_attempts * 100) if total_processing_attempts > 0 else 0
    
    print(f"  Email generation attempts: {total_processing_attempts}")
    print(f"  Successfully sent: {emails_sent}")
    print(f"  Success rate: {success_rate:.1f}%")
    
    # 10. Critical Bugs Found
    print("\n" + "=" * 80)
    print("10. BUGS IDENTIFIED")
    print("=" * 80)
    
    bugs = []
    
    if len(nonetype_errors) > 0:
        bugs.append("❌ CRITICAL: NoneType.lower() crash (FIXED)")
    
    if rate_limit_429 > 100:
        bugs.append("⚠️  HIGH: Excessive API rate limiting (needs better handling)")
    
    if failed_reviews > 10:
        bugs.append(f"⚠️  MEDIUM: {failed_reviews} emails failed review (avg score too low)")
    
    if enrichment_failed > 20:
        bugs.append(f"⚠️  MEDIUM: {enrichment_failed} enrichment failures (fallback working)")
    
    if len(re.findall(r'SMTP verification failed', content)) > 10:
        bugs.append("⚠️  MEDIUM: Multiple SMTP verification failures (may need retry logic)")
    
    if bugs:
        for i, bug in enumerate(bugs, 1):
            print(f"  {i}. {bug}")
    else:
        print("  ✅ No critical bugs found (besides the fixed NoneType issue)")
    
    # 11. Recommendations
    print("\n" + "=" * 80)
    print("11. RECOMMENDATIONS")
    print("=" * 80)
    
    recommendations = []
    
    if rate_limit_429 > 50:
        recommendations.append("⚡ Implement exponential backoff for API retries")
        recommendations.append("⚡ Add API quota pre-check before campaign starts")
        recommendations.append("⚡ Consider upgrading Groq tier or adding backup API")
    
    if failed_reviews > 10:
        recommendations.append("📝 Review email templates - too many failing quality checks")
        recommendations.append("📝 Lower review threshold or improve prompts")
    
    if enrichment_failed > 15:
        recommendations.append("🌐 Improve domain extraction logic")
        recommendations.append("🌐 Add fallback enrichment sources")
    
    if len(re.findall(r'Server disconnected', content)) > 5:
        recommendations.append("🔌 Add retry logic for SMTP verification")
        recommendations.append("🔌 Implement greylisting detection")
    
    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}")
    else:
        print("  ✅ System is operating well")
    
    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    try:
        analyze_logs()
    except FileNotFoundError:
        print("❌ Error: _coldemails_logs.txt not found")
        print("   Make sure you're in the project root directory")
    except Exception as e:
        print(f"❌ Error analyzing logs: {e}")
        import traceback
        traceback.print_exc()
