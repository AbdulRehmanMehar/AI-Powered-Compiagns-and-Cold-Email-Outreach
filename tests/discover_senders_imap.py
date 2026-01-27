#!/usr/bin/env python3
"""
Discover actual senders by checking IMAP Sent folders.
More accurate than round-robin guessing.
"""

import sys
sys.path.insert(0, '..')

import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
from database import emails_collection, leads_collection
import config
import re

def decode_subject(subject):
    """Decode email subject"""
    if not subject:
        return ""
    decoded_parts = decode_header(subject)
    result = ""
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            result += part.decode(encoding or 'utf-8', errors='ignore')
        else:
            result += part
    return result

def extract_email_address(header):
    """Extract email address from header like 'Name <email@domain.com>'"""
    if not header:
        return None
    match = re.search(r'<([^>]+)>', header)
    if match:
        return match.group(1).lower()
    # Maybe it's just an email address
    if '@' in header:
        return header.strip().lower()
    return None

def get_sent_emails_from_imap(account, since_days=30):
    """Get sent emails from an account's Sent folder"""
    sent_emails = []
    
    try:
        mail = imaplib.IMAP4_SSL("imap.zoho.com", 993)
        mail.login(account["email"], account["password"])
        
        # Try different sent folder names
        sent_folders = ["Sent", "SENT", "Sent Items", "Sent Mail", "[Gmail]/Sent Mail"]
        sent_folder = None
        
        for folder in sent_folders:
            try:
                status, _ = mail.select(folder)
                if status == "OK":
                    sent_folder = folder
                    break
            except:
                continue
        
        if not sent_folder:
            print(f"  ⚠️  Could not find Sent folder for {account['email']}")
            mail.logout()
            return []
        
        # Search for emails since N days ago
        since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'SINCE {since_date}')
        
        if status != "OK":
            mail.logout()
            return []
        
        message_ids = messages[0].split()
        print(f"  📧 Found {len(message_ids)} sent emails in last {since_days} days")
        
        for msg_id in message_ids:
            try:
                status, msg_data = mail.fetch(msg_id, "(RFC822.HEADER)")
                if status != "OK":
                    continue
                
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                to_header = msg.get("To", "")
                subject = decode_subject(msg.get("Subject", ""))
                date_str = msg.get("Date", "")
                
                to_email = extract_email_address(to_header)
                
                if to_email:
                    sent_emails.append({
                        "to": to_email,
                        "subject": subject,
                        "date": date_str,
                        "from_account": account["email"]
                    })
            except Exception as e:
                continue
        
        mail.logout()
        
    except imaplib.IMAP4.error as e:
        if "IMAP" in str(e).upper():
            print(f"  ⚠️  {account['email']}: IMAP not enabled")
        else:
            print(f"  ❌ {account['email']}: {e}")
    except Exception as e:
        print(f"  ❌ {account['email']}: {e}")
    
    return sent_emails

def match_and_update():
    """Match sent emails to database records and update from_email"""
    
    print("=" * 60)
    print("DISCOVERING ACTUAL SENDERS VIA IMAP")
    print("=" * 60)
    
    # Get all leads for email matching
    leads = {lead["email"].lower(): lead for lead in leads_collection.find()}
    print(f"\nLoaded {len(leads)} leads from database")
    
    # Get all sent emails from database that need from_email
    db_emails = list(emails_collection.find({"status": "sent"}))
    print(f"Found {len(db_emails)} sent emails in database")
    
    # Build lookup by recipient + subject
    db_lookup = {}
    for e in db_emails:
        lead = leads_collection.find_one({"_id": e["lead_id"]})
        if lead:
            key = (lead["email"].lower(), e["subject"][:50])  # First 50 chars of subject
            db_lookup[key] = e
    
    print(f"\nScanning Sent folders for each account...")
    print()
    
    all_sent = []
    for account in config.ZOHO_ACCOUNTS:
        print(f"Checking {account['email']}...")
        sent = get_sent_emails_from_imap(account, since_days=30)
        all_sent.extend(sent)
    
    print(f"\nTotal sent emails found via IMAP: {len(all_sent)}")
    
    # Match and update
    matched = 0
    updated = 0
    
    for sent in all_sent:
        to_email = sent["to"]
        subject = sent["subject"][:50]
        from_account = sent["from_account"]
        
        key = (to_email, subject)
        
        if key in db_lookup:
            db_email = db_lookup[key]
            matched += 1
            
            # Check if we need to update
            current_from = db_email.get("from_email")
            if current_from != from_account:
                emails_collection.update_one(
                    {"_id": db_email["_id"]},
                    {"$set": {"from_email": from_account}}
                )
                updated += 1
                if current_from:
                    print(f"  Updated: {to_email} - was {current_from}, now {from_account}")
    
    print()
    print("=" * 60)
    print(f"RESULTS:")
    print(f"  Matched: {matched} emails")
    print(f"  Updated: {updated} emails (corrected sender)")
    print("=" * 60)
    
    # Show final distribution
    print("\nFinal sender distribution:")
    for acc in config.ZOHO_ACCOUNTS:
        count = emails_collection.count_documents({"from_email": acc["email"], "status": "sent"})
        if count > 0:
            print(f"  {acc['email']}: {count} emails")

if __name__ == "__main__":
    match_and_update()
