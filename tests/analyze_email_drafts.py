#!/usr/bin/env python3
"""
Analyze all email drafts from MongoDB.
Shows breakdown of failed vs successful generations, formatting issues, and actionable stats.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from datetime import datetime, timedelta
from collections import Counter, defaultdict

def analyze_drafts():
    print("=" * 70)
    print("EMAIL DRAFTS ANALYSIS")
    print(f"Run at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 70)

    all_drafts = list(db.email_drafts.find({}))
    total = len(all_drafts)
    print(f"\nTotal drafts in DB: {total}")

    # ── 1. STATUS BREAKDOWN ──
    status_counts = Counter(d.get('status', 'unknown') for d in all_drafts)
    print("\n" + "-" * 50)
    print("1. STATUS BREAKDOWN")
    print("-" * 50)
    for status, count in status_counts.most_common():
        pct = count / total * 100 if total else 0
        print(f"  {status:20s}: {count:5d}  ({pct:.1f}%)")

    # ── 2. SUCCESSFUL DRAFTS (ready_to_send) ──
    successful = [d for d in all_drafts if d.get('status') == 'ready_to_send']
    sent = [d for d in all_drafts if d.get('status') == 'sent']
    failed = [d for d in all_drafts if d.get('status') == 'failed']
    review_failed = [d for d in all_drafts if d.get('status') == 'review_failed']
    generating = [d for d in all_drafts if d.get('status') == 'generating']

    print("\n" + "-" * 50)
    print("2. SUCCESSFUL DRAFTS (ready_to_send)")
    print("-" * 50)
    print(f"  Count: {len(successful)}")

    if successful:
        # Formatting analysis
        no_paragraph_breaks = 0
        has_em_dash = 0
        has_en_dash = 0
        word_counts = []
        quality_scores = []
        line_counts = []

        for d in successful:
            body = d.get('body', '') or ''
            subject = d.get('subject', '') or ''
            qs = d.get('quality_score', 0) or 0

            word_counts.append(len(body.split()))
            quality_scores.append(qs)
            line_counts.append(len(body.split('\n')))

            if '\n\n' not in body:
                no_paragraph_breaks += 1
            if '—' in body or '—' in subject:
                has_em_dash += 1
            if '–' in body or '–' in subject:
                has_en_dash += 1

        avg_words = sum(word_counts) / len(word_counts) if word_counts else 0
        avg_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        avg_lines = sum(line_counts) / len(line_counts) if line_counts else 0

        print(f"  Avg word count:        {avg_words:.1f}")
        print(f"  Avg quality score:     {avg_score:.1f}")
        print(f"  Avg lines per email:   {avg_lines:.1f}")
        print(f"  Missing para breaks:   {no_paragraph_breaks}  ({no_paragraph_breaks/len(successful)*100:.1f}%)")
        print(f"  Contains em dash (—):  {has_em_dash}  ({has_em_dash/len(successful)*100:.1f}%)")
        print(f"  Contains en dash (–):  {has_en_dash}  ({has_en_dash/len(successful)*100:.1f}%)")

        # Email type breakdown
        type_counts = Counter(d.get('email_type', 'unknown') for d in successful)
        print(f"\n  By email type:")
        for etype, count in type_counts.most_common():
            print(f"    {etype:25s}: {count}")

        # Quality score distribution
        score_buckets = Counter()
        for qs in quality_scores:
            if qs >= 90:
                score_buckets['90-100'] += 1
            elif qs >= 80:
                score_buckets['80-89'] += 1
            elif qs >= 70:
                score_buckets['70-79'] += 1
            elif qs >= 60:
                score_buckets['60-69'] += 1
            else:
                score_buckets['<60'] += 1

        print(f"\n  Quality score distribution:")
        for bucket in ['90-100', '80-89', '70-79', '60-69', '<60']:
            count = score_buckets.get(bucket, 0)
            bar = '#' * (count // 5)
            print(f"    {bucket:8s}: {count:4d}  {bar}")

        # Sample 3 ready_to_send emails
        print(f"\n  Sample ready_to_send emails:")
        for i, d in enumerate(successful[:3], 1):
            body = d.get('body', '')
            subject = d.get('subject', '')
            print(f"\n  --- Sample {i} (score: {d.get('quality_score', 0)}) ---")
            print(f"  Subject: \"{subject}\"")
            print(f"  Body:")
            for line in body.split('\n'):
                print(f"    | {line}")

    # ── 3. ALREADY SENT DRAFTS ──
    print("\n" + "-" * 50)
    print("3. ALREADY SENT DRAFTS")
    print("-" * 50)
    print(f"  Count: {len(sent)}")
    if sent:
        sent_dates = [d.get('sent_at') for d in sent if d.get('sent_at')]
        if sent_dates:
            print(f"  First sent: {min(sent_dates)}")
            print(f"  Last sent:  {max(sent_dates)}")

    # ── 4. FAILED DRAFTS ──
    print("\n" + "-" * 50)
    print("4. FAILED DRAFTS")
    print("-" * 50)
    print(f"  Count: {len(failed)}")

    if failed:
        # Error breakdown
        error_counts = Counter(d.get('error', 'unknown') for d in failed)
        print(f"\n  Error reasons:")
        for error, count in error_counts.most_common():
            print(f"    [{count:3d}] {error[:80]}")

        # Timeline
        fail_dates = [d.get('created_at') for d in failed if d.get('created_at')]
        if fail_dates:
            print(f"\n  First failure: {min(fail_dates)}")
            print(f"  Last failure:  {max(fail_dates)}")

        # Have any content?
        with_content = sum(1 for d in failed if (d.get('body') or '').strip())
        print(f"  With body content: {with_content}")
        print(f"  Empty bodies:      {len(failed) - with_content}")

    # ── 5. REVIEW FAILED DRAFTS ──
    print("\n" + "-" * 50)
    print("5. REVIEW FAILED DRAFTS")
    print("-" * 50)
    print(f"  Count: {len(review_failed)}")

    if review_failed:
        rf_scores = [d.get('quality_score', 0) or 0 for d in review_failed]
        with_content = sum(1 for d in review_failed if (d.get('body') or '').strip())
        print(f"  Avg quality score: {sum(rf_scores)/len(rf_scores):.1f}")
        print(f"  With body content: {with_content}")
        print(f"  Empty bodies:      {len(review_failed) - with_content}")

        for i, d in enumerate(review_failed[:2], 1):
            body = d.get('body', '')
            subject = d.get('subject', '')
            print(f"\n  --- Review Failed Sample {i} (score: {d.get('quality_score', 0)}) ---")
            print(f"  Subject: \"{subject}\"")
            if body:
                print(f"  Body:")
                for line in body.split('\n'):
                    print(f"    | {line}")
            else:
                print(f"  Body: (empty)")

    # ── 6. STUCK IN GENERATING ──
    print("\n" + "-" * 50)
    print("6. STUCK IN 'generating' STATUS")
    print("-" * 50)
    print(f"  Count: {len(generating)}")
    if generating:
        for d in generating:
            created = d.get('created_at', 'Unknown')
            print(f"  ID: {d['_id']}, Created: {created}, To: {d.get('to_email', 'N/A')}")

    # ── 7. TIMELINE ANALYSIS ──
    print("\n" + "-" * 50)
    print("7. DAILY TIMELINE")
    print("-" * 50)

    daily = defaultdict(lambda: Counter())
    for d in all_drafts:
        created = d.get('created_at')
        if created:
            day = created.strftime('%Y-%m-%d')
            daily[day][d.get('status', 'unknown')] += 1

    for day in sorted(daily.keys()):
        counts = daily[day]
        total_day = sum(counts.values())
        parts = ', '.join(f"{s}:{c}" for s, c in counts.most_common())
        print(f"  {day}: {total_day:4d} total  [{parts}]")

    # ── 8. ACTIONABLE SUMMARY ──
    print("\n" + "=" * 70)
    print("ACTIONABLE SUMMARY")
    print("=" * 70)
    print(f"  Ready to send NOW:       {len(successful):5d}  (these can be sent immediately)")
    print(f"  Already sent:            {len(sent):5d}")
    print(f"  Failed (need regenerate): {len(failed):5d}")
    print(f"  Review failed:           {len(review_failed):5d}")
    print(f"  Stuck generating:        {len(generating):5d}")
    print()

    if successful:
        formatting_issues = sum(1 for d in successful if '\n\n' not in (d.get('body', '') or ''))
        em_dash_issues = sum(1 for d in successful 
                           if '—' in (d.get('body', '') or '') or '—' in (d.get('subject', '') or ''))
        print(f"  FORMATTING ISSUES in ready_to_send:")
        print(f"    Missing paragraph breaks: {formatting_issues} / {len(successful)}")
        print(f"    Contains em dashes:       {em_dash_issues} / {len(successful)}")

    print()


if __name__ == "__main__":
    analyze_drafts()
