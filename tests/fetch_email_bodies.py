"""
Fetch actual email bodies from database for human review
"""

from pymongo import MongoClient
from datetime import datetime
import config
import json

# Connect to database
client = MongoClient(config.DATABASE_URL)
db = client.get_database()
emails_collection = db["emails"]
leads_collection = db["leads"]

def fetch_emails_with_bodies():
    """Fetch emails with their actual bodies for review"""
    
    pipeline = [
        {
            "$lookup": {
                "from": "leads",
                "localField": "lead_id",
                "foreignField": "_id",
                "as": "lead"
            }
        },
        {
            "$unwind": {"path": "$lead", "preserveNullAndEmptyArrays": True}
        },
        {
            "$project": {
                "subject": 1,
                "body": 1,
                "email_type": 1,
                "status": 1,
                "sent_at": 1,
                "created_at": 1,
                "lead_email": "$lead.email",
                "lead_name": "$lead.full_name",
                "lead_company": "$lead.company",
                "lead_title": "$lead.title"
            }
        },
        {"$sort": {"created_at": -1}},
        {"$limit": 20}  # Get last 20 emails
    ]
    
    return list(emails_collection.aggregate(pipeline))


def print_emails():
    """Print emails in a readable format"""
    
    emails = fetch_emails_with_bodies()
    
    print("\n" + "="*80)
    print("📧 ACTUAL EMAIL BODIES FROM DATABASE")
    print("="*80)
    print(f"Total emails in DB: {emails_collection.count_documents({})}")
    print(f"Showing last 20 emails\n")
    
    for i, email in enumerate(emails, 1):
        print(f"\n{'─'*80}")
        print(f"EMAIL #{i}")
        print(f"{'─'*80}")
        print(f"TO: {email.get('lead_name', 'N/A')} <{email.get('lead_email', 'N/A')}>")
        print(f"COMPANY: {email.get('lead_company', 'N/A')}")
        print(f"TITLE: {email.get('lead_title', 'N/A')}")
        print(f"STATUS: {email.get('status', 'N/A')}")
        print(f"TYPE: {email.get('email_type', 'N/A')}")
        print(f"\nSUBJECT: {email.get('subject', 'N/A')}")
        print(f"\nBODY:\n{'-'*40}")
        print(email.get('body', 'NO BODY'))
        print(f"{'-'*40}")
        print(f"Word count: {len(email.get('body', '').split())}")
    
    # Also export to JSON for easier reading
    export_data = []
    for email in emails:
        export_data.append({
            "to": f"{email.get('lead_name', 'N/A')} at {email.get('lead_company', 'N/A')}",
            "email": email.get('lead_email', 'N/A'),
            "status": email.get('status', 'N/A'),
            "subject": email.get('subject', 'N/A'),
            "body": email.get('body', 'NO BODY'),
            "word_count": len(email.get('body', '').split())
        })
    
    with open('actual_email_bodies.json', 'w') as f:
        json.dump(export_data, f, indent=2, default=str)
    
    print(f"\n\n📄 Full data exported to: actual_email_bodies.json")


if __name__ == "__main__":
    print_emails()
