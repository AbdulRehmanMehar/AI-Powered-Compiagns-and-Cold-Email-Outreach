"""
Check how many emails were sent and drafted on Feb 18, 2026 (US Time).
Covers all US timezones: EST (UTC-5) through PST (UTC-8).

Checks TWO collections:
  - emails          : legacy / old pipeline (auto_scheduler.py)
  - email_drafts    : v2 pipeline (pre_generator.py + send_worker.py)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from datetime import datetime, timezone

# Feb 18, 2026 in US Time coverage:
#   Start: Feb 18 00:00 EST = Feb 18 05:00 UTC
#   End:   Feb 18 23:59 PST = Feb 19 07:59 UTC

START_UTC = datetime(2026, 2, 18, 5, 0, 0, tzinfo=timezone.utc)   # Feb 18 00:00 EST
END_UTC   = datetime(2026, 2, 19, 8, 0, 0, tzinfo=timezone.utc)   # Feb 18 23:59 PST

email_drafts = db["email_drafts"]


def section(title):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def print_breakdown(label, pipeline, collection):
    rows = list(collection.aggregate(pipeline))
    if rows:
        for doc in rows:
            print(f"  {str(doc['_id'] or 'unknown'):40s}: {doc['count']}")
    else:
        print(f"  (none)")


def main():
    print("=" * 60)
    print("  Email Stats for Feb 18, 2026 (US Time)")
    print("=" * 60)
    print(f"UTC window: {START_UTC.strftime('%Y-%m-%d %H:%M')} → {END_UTC.strftime('%Y-%m-%d %H:%M')}")

    # ══════════════════════════════════════════════════════════
    # 1. LEGACY  `emails` collection (old pipeline)
    # ══════════════════════════════════════════════════════════
    section("[emails collection — legacy pipeline]")

    legacy_sent = db.emails.count_documents({
        'status': 'sent',
        'sent_at': {'$gte': START_UTC, '$lt': END_UTC}
    })
    legacy_draft = db.emails.count_documents({
        'status': 'draft',
        'created_at': {'$gte': START_UTC, '$lt': END_UTC}
    })
    legacy_status = list(db.emails.aggregate([
        {'$match': {'created_at': {'$gte': START_UTC, '$lt': END_UTC}}},
        {'$group': {'_id': '$status', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ]))
    legacy_total = sum(d['count'] for d in legacy_status)

    print(f"  Sent:   {legacy_sent}")
    print(f"  Draft:  {legacy_draft}")
    print(f"  Total:  {legacy_total}")

    print("\n  Status breakdown:")
    for doc in legacy_status:
        print(f"    {doc['_id'] or 'unknown':20s}: {doc['count']}")

    print("\n  Sent by campaign:")
    print_breakdown("legacy campaign", [
        {'$match': {'status': 'sent', 'sent_at': {'$gte': START_UTC, '$lt': END_UTC}}},
        {'$group': {'_id': '$campaign_id', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ], db.emails)

    print("\n  Sent by account:")
    print_breakdown("legacy account", [
        {'$match': {'status': 'sent', 'sent_at': {'$gte': START_UTC, '$lt': END_UTC}}},
        {'$group': {'_id': '$from_email', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ], db.emails)

    # ══════════════════════════════════════════════════════════
    # 2. V2  `email_drafts` collection (pre_generator + send_worker)
    # ══════════════════════════════════════════════════════════
    section("[email_drafts collection — v2 pipeline]")

    v2_sent = email_drafts.count_documents({
        'status': 'sent',
        'sent_at': {'$gte': START_UTC, '$lt': END_UTC}
    })
    v2_generated = email_drafts.count_documents({
        'created_at': {'$gte': START_UTC, '$lt': END_UTC}
    })
    v2_status = list(email_drafts.aggregate([
        {'$match': {'created_at': {'$gte': START_UTC, '$lt': END_UTC}}},
        {'$group': {'_id': '$status', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ]))

    print(f"  Sent (via send_worker): {v2_sent}")
    print(f"  Drafts generated:       {v2_generated}")

    print("\n  Draft status breakdown:")
    if v2_status:
        for doc in v2_status:
            print(f"    {doc['_id'] or 'unknown':20s}: {doc['count']}")
    else:
        print("    (none — v2 pipeline may not have been running)")

    print("\n  Sent by campaign:")
    print_breakdown("v2 campaign", [
        {'$match': {'status': 'sent', 'sent_at': {'$gte': START_UTC, '$lt': END_UTC}}},
        {'$group': {'_id': '$campaign_id', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ], email_drafts)

    print("\n  Sent by account:")
    print_breakdown("v2 account", [
        {'$match': {'status': 'sent', 'sent_at': {'$gte': START_UTC, '$lt': END_UTC}}},
        {'$group': {'_id': '$from_account', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ], email_drafts)

    # ══════════════════════════════════════════════════════════
    # 3. COMBINED TOTALS
    # ══════════════════════════════════════════════════════════
    section("COMBINED TOTALS")
    print(f"  Total SENT (legacy + v2): {legacy_sent + v2_sent}")
    print(f"  Total DRAFTS generated:   {v2_generated} (v2 only; legacy doesn't use drafts)")
    print()
    print("=" * 60)


if __name__ == '__main__':
    main()
