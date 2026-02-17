#!/usr/bin/env python3
"""
Fix formatting issues in ready_to_send email drafts.
Adds paragraph breaks to single-line emails that are missing them.

Pattern detected in broken emails:
  "Hey Name, opener. Question/pain. We helped X do Y. CTA?"
  
Target format (matching good emails):
  "hey name, opener.
   
   question/pain point sentence.
   
   we helped X do Y.
   CTA?
   abdul"

Safety: 
  - Only touches ready_to_send drafts missing paragraph breaks
  - Does NOT touch sent emails
  - Backs up original body before modifying
  - Dry-run mode by default
"""

import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db


def add_paragraph_breaks(body: str) -> str:
    """
    Intelligently add paragraph breaks to a single-line email body.
    
    Strategy: Split at sentence boundaries, then group into:
      1. Opening line (greeting + hook)
      2. Pain point / question
      3. Case study / proof
      4. CTA
      5. Signature
    """
    if not body or '\n\n' in body:
        return body  # Already has breaks or empty
    
    # If already multi-line with single \n breaks, upgrade them to \n\n
    if '\n' in body and '\n\n' not in body:
        lines = [l for l in body.split('\n') if l.strip()]
        if len(lines) >= 2:
            return '\n\n'.join(lines)
    
    # Split into sentences (preserving the delimiters)
    # Match sentence endings: period, question mark, exclamation
    sentences = re.split(r'(?<=[.?!])\s+', body.strip())
    
    if len(sentences) <= 1:
        return body  # Can't split a single sentence
    
    # Identify sentence roles
    opener = []      # First 1-2 sentences (greeting + hook)
    middle = []      # Pain point / question
    case_study = []  # "We helped..." proof
    cta = []         # Final question/CTA
    signature = []   # "abdul" etc.
    
    sender_names = ["abdul", "abdulrehman", "ali", "usama", "bilal"]
    
    for i, sentence in enumerate(sentences):
        s_lower = sentence.strip().lower()
        
        # Check if it's just a signature
        if s_lower.rstrip('.') in sender_names:
            signature.append(sentence)
            continue
        
        # Check if it's a case study line
        if any(phrase in s_lower for phrase in [
            'we helped', 'helped a ', 'helped an ', 'we sped', 'we built',
            'we shipped', 'we cut', 'we reduced', 'we took', 'we scaled'
        ]):
            case_study.append(sentence)
            continue
        
        # Check if it's a CTA (short question at end)
        if i == len(sentences) - 1 or (i == len(sentences) - 2 and sentences[-1].strip().lower().rstrip('.') in sender_names):
            if any(cta_phrase in s_lower for cta_phrase in [
                'worth a chat', 'worth a look', 'worth exploring', 'worth checking',
                'make sense', 'sound familiar', 'crazy or', 'am i off',
                'does this resonate', 'ring any', 'curious if', 'thoughts?',
                'interested?', 'want me to', 'open to', 'sound interesting',
                'want the doc', 'send it over'
            ]):
                cta.append(sentence)
                continue
        
        # First 1-2 sentences are the opener
        if not opener or (len(opener) == 1 and len(opener[0].split()) <= 6):
            opener.append(sentence)
        else:
            middle.append(sentence)
    
    # Build the formatted email
    parts = []
    
    if opener:
        parts.append(' '.join(opener))
    
    if middle:
        parts.append(' '.join(middle))
    
    if case_study:
        parts.append(' '.join(case_study))
    
    if cta:
        parts.append(' '.join(cta))
    
    if signature:
        parts.append(' '.join(signature))
    
    # Join with paragraph breaks
    # If we only got 2 parts (e.g. opener+cta), still add break
    if len(parts) >= 2:
        return '\n\n'.join(parts)
    
    # Fallback: if classification failed, just split at midpoint
    mid = len(sentences) // 2
    part1 = ' '.join(sentences[:mid])
    part2 = ' '.join(sentences[mid:])
    return f"{part1}\n\n{part2}"


def fix_drafts(dry_run=True):
    """Fix formatting issues in ready_to_send drafts."""
    
    print("=" * 70)
    print(f"EMAIL DRAFT FORMATTING FIX {'(DRY RUN)' if dry_run else '(LIVE)'}")
    print("=" * 70)
    
    # Fetch all ready_to_send drafts
    all_ready = list(db.email_drafts.find({'status': 'ready_to_send'}))
    
    # Filter to ones missing paragraph breaks
    broken = [d for d in all_ready if '\n\n' not in (d.get('body', '') or '')]
    
    print(f"\nTotal ready_to_send: {len(all_ready)}")
    print(f"Missing paragraph breaks: {len(broken)}")
    print(f"Already formatted: {len(all_ready) - len(broken)}")
    
    if not broken:
        print("\nNo drafts need fixing!")
        return
    
    fixed_count = 0
    failed_count = 0
    
    for i, draft in enumerate(broken):
        draft_id = draft['_id']
        original_body = draft.get('body', '')
        subject = draft.get('subject', '')
        
        # Apply formatting fix
        fixed_body = add_paragraph_breaks(original_body)
        
        # Verify the fix actually added breaks
        if '\n\n' not in fixed_body:
            failed_count += 1
            if i < 3:  # Show first few failures
                print(f"\n  SKIP #{i+1}: Could not add breaks to: \"{original_body[:60]}...\"")
            continue
        
        fixed_count += 1
        
        # Show before/after for first few
        if i < 5:
            print(f"\n{'─' * 50}")
            print(f"Draft #{i+1} (ID: {draft_id})")
            print(f"Subject: \"{subject}\"")
            print(f"\nBEFORE (single line):")
            print(f"  \"{original_body[:120]}...\"")
            print(f"\nAFTER (formatted):")
            for line in fixed_body.split('\n'):
                print(f"  | {line}")
        
        if not dry_run:
            # Save original body as backup and update
            db.email_drafts.update_one(
                {'_id': draft_id},
                {
                    '$set': {
                        'body': fixed_body,
                        'original_body_backup': original_body,
                        'formatting_fixed': True
                    }
                }
            )
    
    print(f"\n{'=' * 70}")
    print(f"RESULTS")
    print(f"{'=' * 70}")
    print(f"  Fixed:   {fixed_count}")
    print(f"  Skipped: {failed_count} (couldn't determine break points)")
    
    if dry_run:
        print(f"\n  >>> DRY RUN - no changes made <<<")
        print(f"  >>> Run with --live to apply fixes <<<")
    else:
        print(f"\n  >>> {fixed_count} drafts updated in DB <<<")
        print(f"  >>> Original bodies backed up in 'original_body_backup' field <<<")


if __name__ == "__main__":
    live = '--live' in sys.argv
    fix_drafts(dry_run=not live)
