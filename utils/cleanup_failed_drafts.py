#!/usr/bin/env python3
"""
Safely clean up failed draft generation attempts.
These are empty records from when generate_cold_email method was missing.
"""

from database import db
from datetime import datetime

def cleanup_failed_drafts():
    """Remove failed draft records with empty content"""
    
    print("=== FAILED DRAFTS CLEANUP ===")
    
    # Find failed drafts with empty content
    failed_drafts = {
        'status': 'failed',
        'error': 'generate_cold_email method did not exist — fixed in deploy',
        '$or': [
            {'body': ''},
            {'body': {'$exists': False}}, 
            {'body': None}
        ]
    }
    
    # Count before deletion
    count_to_delete = db.email_drafts.count_documents(failed_drafts)
    print(f"Found {count_to_delete} failed draft records to clean up")
    
    if count_to_delete == 0:
        print("No failed drafts to clean up")
        return
        
    # Show samples before deletion for verification
    samples = list(db.email_drafts.find(failed_drafts, {'_id': 1, 'status': 1, 'error': 1, 'body': 1}).limit(3))
    print("\nSample records to be deleted:")
    for sample in samples:
        print(f"  ID: {sample['_id']}, Status: {sample.get('status')}, Body: '{sample.get('body', '')}'")
    
    # Safety confirmation
    response = input(f"\nDelete {count_to_delete} failed draft records? (yes/no): ")
    if response.lower() != 'yes':
        print("Cleanup cancelled")
        return
    
    # Delete failed drafts
    result = db.email_drafts.delete_many(failed_drafts)
    print(f"✅ Deleted {result.deleted_count} failed draft records")
    
    # Verify cleanup
    remaining = db.email_drafts.count_documents({})
    print(f"Remaining drafts: {remaining}")

if __name__ == "__main__":
    cleanup_failed_drafts()