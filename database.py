from pymongo import MongoClient
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import config
import json
import re

client = MongoClient(config.DATABASE_URL)
db = client.get_database()

# Collections
leads_collection = db["leads"]
emails_collection = db["emails"]
campaigns_collection = db["campaigns"]
email_reviews_collection = db["email_reviews"]
groq_limits_collection = db["groq_model_limits"]  # Model limits and usage tracking

# Create indexes
leads_collection.create_index("email", unique=True)
emails_collection.create_index([("lead_id", 1), ("campaign_id", 1)])
emails_collection.create_index("status")
email_reviews_collection.create_index([("created_at", -1)])
email_reviews_collection.create_index([("passed", 1)])
email_reviews_collection.create_index([("email_id", 1)])
groq_limits_collection.create_index("model", unique=True)


def is_valid_first_name(name: str) -> bool:
    """
    Check if a string is a valid first name for use in cold emails.
    
    Rejects:
    - Single letters or very short strings
    - Company names (multiple words, Inc, Ltd, etc.)
    - Names with numbers or special characters
    - Common non-name patterns
    """
    if not name or not isinstance(name, str):
        return False
    
    name = name.strip()
    
    # Too short (single letter or 2 chars)
    if len(name) < 3:
        return False
    
    # Too long for a first name (likely company name)
    if len(name) > 20:
        return False
    
    # Contains numbers
    if any(c.isdigit() for c in name):
        return False
    
    # Contains special characters (except hyphen for names like Jean-Pierre)
    if re.search(r'[^\w\s\-\']', name):
        return False
    
    # Multiple words (likely company name) - first names are usually one word
    if len(name.split()) > 1:
        return False
    
    # Company name indicators
    company_indicators = ['inc', 'ltd', 'llc', 'corp', 'company', 'co', 'group', 'technologies', 
                          'services', 'solutions', 'consulting', 'capital', 'ventures', 'labs',
                          'studio', 'agency', 'media', 'digital', 'global', 'international']
    if name.lower() in company_indicators:
        return False
    
    # Names that look like company names (end with common company suffixes)
    if name.lower().endswith(('tech', 'soft', 'ware', 'corp', 'labs', 'hub', 'io')):
        return False
    
    # Common invalid patterns (from actual bad data)
    invalid_names = {'in', 'ysis', 'api', 'ceo', 'cto', 'vp', 'the', 'mr', 'ms', 'mrs', 'dr',
                     'n/a', 'na', 'none', 'null', 'test', 'admin', 'info', 'hello', 'support',
                     'sales', 'contact', 'team', 'general', 'office', 'main', 'primary',
                     'fazmercado', 'bitpin', 'coinbase', 'workflow'}  # Known bad patterns from data
    if name.lower() in invalid_names:
        return False
    
    # Must start with a letter
    if not name[0].isalpha():
        return False
    
    return True


def clean_first_name(full_name: str, email: str = None) -> str:
    """
    Extract and validate a first name from full name or email.
    Returns 'there' if no valid name found.
    """
    # Try extracting from full name
    if full_name:
        parts = full_name.strip().split()
        if parts:
            candidate = parts[0]
            if is_valid_first_name(candidate):
                return candidate.capitalize()
    
    # Try extracting from email (before @ and before any dots/numbers)
    if email and '@' in email:
        local_part = email.split('@')[0]
        # Remove numbers and get first part before dots/underscores
        name_part = re.split(r'[._\d]', local_part)[0]
        if is_valid_first_name(name_part):
            return name_part.capitalize()
    
    # Fallback
    return 'there'


class Lead:
    """Lead/Contact model"""
    
    @staticmethod
    def create(data: Dict[str, Any], campaign_id: str = None) -> str:
        """Create or update a lead
        
        Args:
            data: Lead data from RocketReach or other source
            campaign_id: Optional campaign ID to associate with this lead
        """
        # Extract and validate first_name
        full_name = data.get("name") or data.get("full_name") or ""
        email = data.get("email") or ""
        
        # Use the new validation function
        first_name = clean_first_name(full_name, email)
        
        # If data has explicit first_name, validate it
        if data.get("first_name") and is_valid_first_name(data.get("first_name")):
            first_name = data.get("first_name").capitalize()
        
        lead = {
            "email": email,
            "first_name": first_name,
            "last_name": data.get("last_name"),
            "full_name": full_name or f"{data.get('first_name') or ''} {data.get('last_name') or ''}".strip(),
            "title": data.get("current_title") or data.get("title"),
            "company": data.get("current_employer") or data.get("company"),
            "linkedin_url": data.get("linkedin_url"),
            "location": data.get("location"),
            "industry": data.get("industry") or data.get("current_employer_industry"),  # Fallback to employer industry
            "rocketreach_id": data.get("id"),
            "raw_data": data,
            "updated_at": datetime.utcnow(),
            # Campaign association - which campaign fetched this lead
            "campaign_id": campaign_id or data.get("campaign_id"),
            # ICP Tracking (TK Kader Framework)
            "is_icp": data.get("is_icp"),  # True/False - core classification
            "icp_template": data.get("icp_template"),  # Which template matched
            "icp_score": data.get("icp_score"),  # Confidence 0.0-1.0
            "icp_reasons": data.get("icp_reasons", []),  # Why they matched
        }
        
        result = leads_collection.update_one(
            {"email": lead["email"]},
            {
                "$set": lead,
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )
        
        if result.upserted_id:
            return str(result.upserted_id)
        
        existing = leads_collection.find_one({"email": lead["email"]})
        return str(existing["_id"])
    
    @staticmethod
    def get_by_email(email: str) -> Optional[Dict]:
        lead = leads_collection.find_one({"email": email})
        return Lead._normalize(lead) if lead else None
    
    @staticmethod
    def get_by_id(lead_id: str) -> Optional[Dict]:
        from bson import ObjectId
        lead = leads_collection.find_one({"_id": ObjectId(lead_id)})
        return Lead._normalize(lead) if lead else None
    
    @staticmethod
    def get_all() -> List[Dict]:
        return [Lead._normalize(l) for l in leads_collection.find()]
    
    @staticmethod
    def _normalize(lead: Dict) -> Dict:
        """Ensure lead has all required fields with safe defaults (never None)"""
        if not lead:
            return lead
        
        # Use validation function to get clean first name
        full_name = lead.get('full_name') or ''
        email = lead.get('email') or ''
        first_name = lead.get('first_name')
        
        # Validate existing first_name or extract from full_name/email
        if not first_name or not is_valid_first_name(first_name):
            first_name = clean_first_name(full_name, email)
        
        # Get industry from raw_data if missing
        industry = lead.get('industry')
        if not industry and lead.get('raw_data'):
            industry = lead['raw_data'].get('current_employer_industry')
        
        # Apply safe defaults for commonly-used fields
        lead['first_name'] = first_name
        lead['full_name'] = full_name or lead.get('email', '').split('@')[0]
        lead['industry'] = industry or ''
        lead['title'] = lead.get('title') or ''
        lead['company'] = lead.get('company') or ''
        
        # ICP fields (default to None for backwards compatibility)
        lead['is_icp'] = lead.get('is_icp')
        lead['icp_template'] = lead.get('icp_template')
        lead['icp_score'] = lead.get('icp_score')
        lead['icp_reasons'] = lead.get('icp_reasons', [])
        
        return lead
    
    @staticmethod
    def update_icp_classification(lead_id: str, is_icp: bool, icp_template: str = None,
                                   icp_score: float = None, icp_reasons: List[str] = None):
        """Update ICP classification for a lead"""
        from bson import ObjectId
        update = {
            "is_icp": is_icp,
            "icp_template": icp_template,
            "icp_score": icp_score,
            "icp_reasons": icp_reasons or []
        }
        leads_collection.update_one(
            {"_id": ObjectId(lead_id)},
            {"$set": update}
        )


class Email:
    """Email tracking model"""
    
    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_OPENED = "opened"
    STATUS_REPLIED = "replied"
    STATUS_BOUNCED = "bounced"
    
    @staticmethod
    def create(lead_id: str, campaign_id: str, subject: str, body: str, 
               email_type: str = "initial", followup_number: int = 0,
               to_email: str = None, is_icp: bool = None, icp_template: str = None) -> str:
        """Create a new email record"""
        from bson import ObjectId
        
        email = {
            "lead_id": ObjectId(lead_id),
            "campaign_id": ObjectId(campaign_id),
            "to_email": to_email,  # Store recipient email for bounce lookups
            "subject": subject,
            "body": body,
            "email_type": email_type,  # "initial", "followup", or "followup_new_thread"
            "followup_number": followup_number,
            "status": Email.STATUS_PENDING,
            "message_id": None,  # SMTP Message-ID for threading
            "in_reply_to": None,  # Parent email's Message-ID
            "references": [],  # Thread chain of Message-IDs
            "created_at": datetime.utcnow(),
            "scheduled_at": None,
            "sent_at": None,
            "opened_at": None,
            "replied_at": None,
            "error_message": None,
            # ICP Tracking (denormalized for reporting)
            "is_icp": is_icp,
            "icp_template": icp_template,
        }
        
        result = emails_collection.insert_one(email)
        return str(result.inserted_id)
    
    @staticmethod
    def mark_sent(email_id: str, from_email: str = None, message_id: str = None):
        """Mark email as sent and store which account sent it + Message-ID for threading"""
        from bson import ObjectId
        update = {"status": Email.STATUS_SENT, "sent_at": datetime.utcnow()}
        if from_email:
            update["from_email"] = from_email
        if message_id:
            update["message_id"] = message_id
        emails_collection.update_one(
            {"_id": ObjectId(email_id)},
            {"$set": update}
        )
    
    @staticmethod
    def get_sender_for_lead(lead_id: str, campaign_id: str) -> Optional[str]:
        """Get the email account that originally emailed this lead in this campaign"""
        from bson import ObjectId
        email = emails_collection.find_one(
            {
                "lead_id": ObjectId(lead_id),
                "campaign_id": ObjectId(campaign_id),
                "status": Email.STATUS_SENT,
                "from_email": {"$exists": True}
            },
            sort=[("sent_at", 1)]  # Get the first email sent
        )
        return email.get("from_email") if email else None
    
    @staticmethod
    def get_thread_info(lead_id: str, campaign_id: str) -> dict:
        """
        Get threading information for a follow-up email.
        
        Returns:
            dict with:
            - in_reply_to: Message-ID of the most recent email (to reply to)
            - references: List of all Message-IDs in the thread chain
            - first_message_id: Message-ID of the first email (thread root)
        """
        from bson import ObjectId
        
        # Get all sent emails for this lead/campaign, ordered by sent_at
        emails = list(emails_collection.find(
            {
                "lead_id": ObjectId(lead_id),
                "campaign_id": ObjectId(campaign_id),
                "status": Email.STATUS_SENT,
                "message_id": {"$exists": True, "$ne": None}
            },
            sort=[("sent_at", 1)]
        ))
        
        if not emails:
            return {"in_reply_to": None, "references": [], "first_message_id": None}
        
        # Collect all message IDs in order
        message_ids = [e.get("message_id") for e in emails if e.get("message_id")]
        
        if not message_ids:
            return {"in_reply_to": None, "references": [], "first_message_id": None}
        
        return {
            "in_reply_to": message_ids[-1],  # Reply to the most recent email
            "references": message_ids,  # Full thread chain
            "first_message_id": message_ids[0]  # Thread root
        }
    
    @staticmethod
    def has_been_contacted(lead_id: str) -> bool:
        """Check if lead has received ANY email (across all campaigns)"""
        from bson import ObjectId
        count = emails_collection.count_documents({
            "lead_id": ObjectId(lead_id),
            "status": {"$in": [Email.STATUS_SENT, Email.STATUS_REPLIED, Email.STATUS_OPENED]}
        })
        return count > 0
    
    @staticmethod
    def has_been_contacted_by_email(email_address: str) -> bool:
        """Check if this email address has been contacted (regardless of lead_id)"""
        # First find all leads with this email
        lead = leads_collection.find_one({"email": email_address})
        if not lead:
            return False
        
        from bson import ObjectId
        count = emails_collection.count_documents({
            "lead_id": lead["_id"],
            "status": {"$in": [Email.STATUS_SENT, Email.STATUS_REPLIED, Email.STATUS_OPENED]}
        })
        return count > 0
    
    @staticmethod
    def get_contacted_emails() -> set:
        """Get set of all email addresses that have been contacted"""
        pipeline = [
            {"$match": {"status": {"$in": [Email.STATUS_SENT, Email.STATUS_REPLIED, Email.STATUS_OPENED]}}},
            {"$lookup": {
                "from": "leads",
                "localField": "lead_id",
                "foreignField": "_id",
                "as": "lead"
            }},
            {"$unwind": "$lead"},
            {"$group": {"_id": "$lead.email"}}
        ]
        results = emails_collection.aggregate(pipeline)
        return {r["_id"] for r in results if r["_id"]}
    
    @staticmethod
    def get_email_count_for_lead(lead_id: str, days: int = None) -> int:
        """Get count of emails sent to a lead, optionally within last N days"""
        from bson import ObjectId
        from datetime import timedelta
        
        query = {"lead_id": ObjectId(lead_id)}
        
        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            query["created_at"] = {"$gte": cutoff}
        
        return emails_collection.count_documents(query)
    
    @staticmethod
    def can_email_lead(lead_id: str, max_emails_per_week: int = 3) -> bool:
        """Check if we can send another email to this lead (spam prevention)"""
        # Don't send more than max_emails_per_week in a 7-day window
        recent_count = Email.get_email_count_for_lead(lead_id, days=7)
        return recent_count < max_emails_per_week
    
    @staticmethod
    def mark_failed(email_id: str, error: str):
        from bson import ObjectId
        emails_collection.update_one(
            {"_id": ObjectId(email_id)},
            {"$set": {"status": Email.STATUS_FAILED, "error_message": error}}
        )
    
    @staticmethod
    def get_pending_followups(campaign_id: str, days_since_last: int) -> List[Dict]:
        """
        Get leads that need follow-up emails.
        
        Only returns leads whose initial email has a message_id stored.
        This ensures we can properly thread follow-ups (In-Reply-To header).
        
        Emails sent before threading support was added (2026-01-29 17:27 EST)
        won't have message_id and will be automatically skipped.
        """
        from bson import ObjectId
        from datetime import timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_since_last)
        
        pipeline = [
            # Only consider sent emails that have message_id (for threading)
            {"$match": {
                "campaign_id": ObjectId(campaign_id), 
                "status": Email.STATUS_SENT,
                "message_id": {"$exists": True, "$ne": None}  # Must have message_id for threading
            }},
            {"$sort": {"sent_at": -1}},
            {"$group": {
                "_id": "$lead_id",
                "last_email": {"$first": "$$ROOT"},
                "email_count": {"$sum": 1},
                "first_message_id": {"$last": "$message_id"}  # Get the first email's message_id
            }},
            {"$match": {
                "last_email.sent_at": {"$lt": cutoff_date},
                "email_count": {"$lt": config.MAX_FOLLOWUPS + 1},
                "last_email.status": {"$nin": [Email.STATUS_REPLIED, Email.STATUS_BOUNCED]},
                "first_message_id": {"$ne": None}  # Double-check thread root exists
            }}
        ]
        
        return list(emails_collection.aggregate(pipeline))
    
    @staticmethod
    def get_by_lead_and_campaign(lead_id: str, campaign_id: str) -> List[Dict]:
        from bson import ObjectId
        return list(emails_collection.find({
            "lead_id": ObjectId(lead_id),
            "campaign_id": ObjectId(campaign_id)
        }).sort("created_at", 1))
    
    @staticmethod
    def get_icp_analytics(campaign_id: str = None) -> Dict[str, Any]:
        """
        Get ICP performance analytics (TK Kader Framework).
        
        Returns reply rates, conversion rates broken down by:
        - ICP vs Non-ICP leads
        - By ICP template
        
        This data should feed back into ICP refinement.
        """
        from bson import ObjectId
        
        match_stage = {"status": {"$in": [Email.STATUS_SENT, Email.STATUS_REPLIED, Email.STATUS_OPENED]}}
        if campaign_id:
            match_stage["campaign_id"] = ObjectId(campaign_id)
        
        pipeline = [
            {"$match": match_stage},
            {"$group": {
                "_id": {
                    "is_icp": "$is_icp",
                    "icp_template": "$icp_template"
                },
                "total_sent": {"$sum": 1},
                "total_replied": {"$sum": {"$cond": [{"$eq": ["$status", Email.STATUS_REPLIED]}, 1, 0]}},
                "total_opened": {"$sum": {"$cond": [{"$eq": ["$status", Email.STATUS_OPENED]}, 1, 0]}},
            }},
            {"$sort": {"_id.is_icp": -1, "total_sent": -1}}
        ]
        
        results = list(emails_collection.aggregate(pipeline))
        
        # Process into readable format
        analytics = {
            "icp_leads": {"sent": 0, "replied": 0, "opened": 0, "reply_rate": 0},
            "non_icp_leads": {"sent": 0, "replied": 0, "opened": 0, "reply_rate": 0},
            "unknown_leads": {"sent": 0, "replied": 0, "opened": 0, "reply_rate": 0},  # Pre-ICP tracking
            "by_template": {},
            "total": {"sent": 0, "replied": 0, "opened": 0}
        }
        
        for r in results:
            is_icp = r["_id"].get("is_icp")
            template = r["_id"].get("icp_template") or "unknown"
            
            sent = r["total_sent"]
            replied = r["total_replied"]
            opened = r["total_opened"]
            
            # Aggregate totals
            analytics["total"]["sent"] += sent
            analytics["total"]["replied"] += replied
            analytics["total"]["opened"] += opened
            
            # By ICP status
            if is_icp is True:
                analytics["icp_leads"]["sent"] += sent
                analytics["icp_leads"]["replied"] += replied
                analytics["icp_leads"]["opened"] += opened
            elif is_icp is False:
                analytics["non_icp_leads"]["sent"] += sent
                analytics["non_icp_leads"]["replied"] += replied
                analytics["non_icp_leads"]["opened"] += opened
            else:
                analytics["unknown_leads"]["sent"] += sent
                analytics["unknown_leads"]["replied"] += replied
                analytics["unknown_leads"]["opened"] += opened
            
            # By template
            if template not in analytics["by_template"]:
                analytics["by_template"][template] = {"sent": 0, "replied": 0, "opened": 0, "reply_rate": 0}
            analytics["by_template"][template]["sent"] += sent
            analytics["by_template"][template]["replied"] += replied
            analytics["by_template"][template]["opened"] += opened
        
        # Calculate reply rates
        for key in ["icp_leads", "non_icp_leads", "unknown_leads"]:
            if analytics[key]["sent"] > 0:
                analytics[key]["reply_rate"] = round(analytics[key]["replied"] / analytics[key]["sent"] * 100, 2)
        
        for template in analytics["by_template"]:
            if analytics["by_template"][template]["sent"] > 0:
                rate = analytics["by_template"][template]["replied"] / analytics["by_template"][template]["sent"] * 100
                analytics["by_template"][template]["reply_rate"] = round(rate, 2)
        
        return analytics


class Campaign:
    """Campaign model"""
    
    STATUS_DRAFT = "draft"
    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_COMPLETED = "completed"
    
    @staticmethod
    def create(name: str, description: str = "", target_criteria: Dict = None,
               email_template: str = "", followup_templates: List[str] = None) -> str:
        """Create a new campaign"""
        campaign = {
            "name": name,
            "description": description,
            "target_criteria": target_criteria or {},
            "email_template": email_template,
            "followup_templates": followup_templates or [],
            "status": Campaign.STATUS_DRAFT,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "stats": {
                "total_leads": 0,
                "emails_sent": 0,
                "emails_opened": 0,
                "emails_replied": 0,
                "emails_bounced": 0,
            }
        }
        
        result = campaigns_collection.insert_one(campaign)
        return str(result.inserted_id)
    
    @staticmethod
    def get_by_id(campaign_id: str) -> Optional[Dict]:
        from bson import ObjectId
        return campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
    
    @staticmethod
    def update_status(campaign_id: str, status: str):
        from bson import ObjectId
        campaigns_collection.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$set": {"status": status, "updated_at": datetime.utcnow()}}
        )
    
    @staticmethod
    def increment_stat(campaign_id: str, stat_name: str, value: int = 1):
        from bson import ObjectId
        campaigns_collection.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$inc": {f"stats.{stat_name}": value}}
        )
    
    @staticmethod
    def get_active_campaigns() -> List[Dict]:
        return list(campaigns_collection.find({"status": Campaign.STATUS_ACTIVE}))


class SendingStats:
    """Track sending statistics per account for warm-up and daily limits"""
    
    # Collection for tracking sends
    _collection = db["sending_stats"]
    _collection.create_index([("account_email", 1), ("date", 1)], unique=True)
    
    @staticmethod
    def get_sends_today(account_email: str) -> int:
        """Get number of emails sent today from this account"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        record = SendingStats._collection.find_one({
            "account_email": account_email,
            "date": today
        })
        return record["count"] if record else 0
    
    @staticmethod
    def increment_send(account_email: str):
        """Increment send count for today"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        SendingStats._collection.update_one(
            {"account_email": account_email, "date": today},
            {
                "$inc": {"count": 1},
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )
    
    @staticmethod
    def get_account_age_days(account_email: str) -> int:
        """Get how many days this account has been active (for warm-up)"""
        # First check AccountMetadata for explicit added_date
        added_date = AccountMetadata.get_added_date(account_email)
        if added_date:
            days = (datetime.utcnow() - added_date).days
            return max(0, days)
        
        # Fallback: Find the earliest send date for this account
        oldest = SendingStats._collection.find_one(
            {"account_email": account_email},
            sort=[("date", 1)]
        )
        if not oldest:
            return 0
        
        from datetime import datetime as dt
        first_send = dt.strptime(oldest["date"], "%Y-%m-%d")
        days = (dt.utcnow() - first_send).days
        return max(0, days)
    
    @staticmethod
    def get_all_sends_today() -> Dict[str, int]:
        """Get sends today for all accounts"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        records = SendingStats._collection.find({"date": today})
        return {r["account_email"]: r["count"] for r in records}
    
    @staticmethod
    def get_total_sends_today() -> int:
        """Get total sends today across all accounts"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        pipeline = [
            {"$match": {"date": today}},
            {"$group": {"_id": None, "total": {"$sum": "$count"}}}
        ]
        result = list(SendingStats._collection.aggregate(pipeline))
        return result[0]["total"] if result else 0


class AccountMetadata:
    """Store email account metadata like added_date for warm-up tracking"""
    
    _collection = db["account_metadata"]
    _collection.create_index("account_email", unique=True)
    
    @staticmethod
    def set_added_date(account_email: str, added_date: datetime) -> None:
        """Set the added_date for an account"""
        AccountMetadata._collection.update_one(
            {"account_email": account_email},
            {
                "$set": {
                    "added_date": added_date,
                    "updated_at": datetime.utcnow()
                },
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )
    
    @staticmethod
    def get_added_date(account_email: str) -> Optional[datetime]:
        """Get the added_date for an account"""
        record = AccountMetadata._collection.find_one({"account_email": account_email})
        return record.get("added_date") if record else None
    
    @staticmethod
    def get_all() -> List[Dict[str, Any]]:
        """Get all account metadata"""
        return list(AccountMetadata._collection.find())
    
    @staticmethod
    def initialize_accounts(account_emails: List[str], added_date: datetime) -> int:
        """Initialize multiple accounts with the same added_date (if not already set)"""
        count = 0
        for email in account_emails:
            existing = AccountMetadata._collection.find_one({"account_email": email})
            if not existing:
                AccountMetadata.set_added_date(email, added_date)
                count += 1
        return count


class BlockedAccounts:
    """Track accounts blocked by Zoho (554 errors) with cooldown periods"""
    
    _collection = db["blocked_accounts"]
    _collection.create_index("account_email", unique=True)
    
    # Default cooldown period in hours (48 hours = 2 days)
    DEFAULT_COOLDOWN_HOURS = 48
    
    @staticmethod
    def mark_blocked(account_email: str, error_message: str = None, cooldown_hours: int = None):
        """Mark an account as blocked with a cooldown period"""
        cooldown = cooldown_hours or BlockedAccounts.DEFAULT_COOLDOWN_HOURS
        blocked_until = datetime.utcnow() + timedelta(hours=cooldown)
        
        BlockedAccounts._collection.update_one(
            {"account_email": account_email},
            {
                "$set": {
                    "blocked_at": datetime.utcnow(),
                    "blocked_until": blocked_until,
                    "error_message": error_message,
                    "cooldown_hours": cooldown
                },
                "$inc": {"block_count": 1}
            },
            upsert=True
        )
        print(f"   ⛔ Account {account_email} blocked until {blocked_until.strftime('%Y-%m-%d %H:%M')} UTC")
    
    @staticmethod
    def is_blocked(account_email: str) -> bool:
        """Check if an account is currently blocked"""
        record = BlockedAccounts._collection.find_one({"account_email": account_email})
        if not record:
            return False
        
        # Check if cooldown has expired
        if record.get("blocked_until") and record["blocked_until"] > datetime.utcnow():
            return True
        
        return False
    
    @staticmethod
    def get_blocked_until(account_email: str) -> Optional[datetime]:
        """Get when the block expires for an account"""
        record = BlockedAccounts._collection.find_one({"account_email": account_email})
        if record and record.get("blocked_until"):
            return record["blocked_until"]
        return None
    
    @staticmethod
    def unblock(account_email: str):
        """Manually unblock an account"""
        BlockedAccounts._collection.delete_one({"account_email": account_email})
    
    @staticmethod
    def get_all_blocked() -> List[Dict]:
        """Get all currently blocked accounts"""
        now = datetime.utcnow()
        return list(BlockedAccounts._collection.find({"blocked_until": {"$gt": now}}))
    
    @staticmethod
    def cleanup_expired():
        """Remove expired blocks"""
        now = datetime.utcnow()
        result = BlockedAccounts._collection.delete_many({"blocked_until": {"$lte": now}})
        if result.deleted_count > 0:
            print(f"   🔓 Unblocked {result.deleted_count} account(s) after cooldown expired")


class AccountCooldown:
    """Track per-account send cooldowns for rate limiting without blocking all accounts"""
    
    _collection = db["account_cooldowns"]
    _collection.create_index("account_email", unique=True)
    
    @staticmethod
    def record_send(account_email: str, cooldown_minutes: int):
        """Record a send and set the cooldown for this account"""
        available_at = datetime.utcnow() + timedelta(minutes=cooldown_minutes)
        
        AccountCooldown._collection.update_one(
            {"account_email": account_email},
            {
                "$set": {
                    "last_send_at": datetime.utcnow(),
                    "available_at": available_at,
                    "cooldown_minutes": cooldown_minutes
                },
                "$inc": {"total_sends": 1}
            },
            upsert=True
        )
    
    @staticmethod
    def is_available(account_email: str) -> bool:
        """Check if an account is available (cooldown expired)"""
        record = AccountCooldown._collection.find_one({"account_email": account_email})
        if not record:
            return True  # Never sent = available
        
        available_at = record.get("available_at")
        if not available_at:
            return True
        
        return datetime.utcnow() >= available_at
    
    @staticmethod
    def get_available_at(account_email: str) -> Optional[datetime]:
        """Get when the account will be available"""
        record = AccountCooldown._collection.find_one({"account_email": account_email})
        if record and record.get("available_at"):
            return record["available_at"]
        return None
    
    @staticmethod
    def get_seconds_until_available(account_email: str) -> int:
        """Get seconds until account is available (0 if available now)"""
        available_at = AccountCooldown.get_available_at(account_email)
        if not available_at:
            return 0
        
        delta = (available_at - datetime.utcnow()).total_seconds()
        return max(0, int(delta))
    
    @staticmethod
    def get_next_available_account(account_emails: List[str]) -> Optional[str]:
        """Get the first available account, or None if all on cooldown"""
        for email in account_emails:
            if AccountCooldown.is_available(email):
                return email
        return None
    
    @staticmethod
    def get_soonest_available(account_emails: List[str]) -> tuple[Optional[str], int]:
        """Get the account that will be available soonest and seconds until then"""
        soonest_email = None
        soonest_seconds = float('inf')
        
        for email in account_emails:
            seconds = AccountCooldown.get_seconds_until_available(email)
            if seconds == 0:
                return email, 0  # Available now
            if seconds < soonest_seconds:
                soonest_seconds = seconds
                soonest_email = email
        
        return soonest_email, int(soonest_seconds) if soonest_seconds != float('inf') else 0
    
    @staticmethod
    def get_all_cooldown_status() -> Dict[str, Dict]:
        """Get cooldown status for all accounts"""
        records = AccountCooldown._collection.find()
        now = datetime.utcnow()
        
        status = {}
        for r in records:
            email = r["account_email"]
            available_at = r.get("available_at", now)
            is_available = now >= available_at
            
            status[email] = {
                "available": is_available,
                "available_at": available_at,
                "seconds_remaining": max(0, int((available_at - now).total_seconds())) if not is_available else 0,
                "last_send_at": r.get("last_send_at"),
                "total_sends": r.get("total_sends", 0)
            }
        return status


class FailedEmails:
    """Track failed emails for retry logic"""
    
    MAX_RETRIES = 3
    RETRY_DELAY_HOURS = [1, 6, 24]  # Wait 1h, then 6h, then 24h between retries
    
    @staticmethod
    def get_emails_to_retry() -> List[Dict]:
        """Get failed emails that are eligible for retry"""
        from bson import ObjectId
        
        # Find failed emails with retry_count < MAX_RETRIES
        pipeline = [
            {"$match": {
                "status": Email.STATUS_FAILED,
                "$or": [
                    {"retry_count": {"$exists": False}},
                    {"retry_count": {"$lt": FailedEmails.MAX_RETRIES}}
                ]
            }},
            # Check if enough time has passed since last attempt
            {"$addFields": {
                "retry_count": {"$ifNull": ["$retry_count", 0]},
                "last_attempt": {"$ifNull": ["$last_retry_at", "$created_at"]}
            }},
            {"$lookup": {
                "from": "leads",
                "localField": "lead_id",
                "foreignField": "_id",
                "as": "lead"
            }},
            {"$unwind": "$lead"}
        ]
        
        candidates = list(emails_collection.aggregate(pipeline))
        
        # Filter by retry delay
        now = datetime.utcnow()
        eligible = []
        
        for email in candidates:
            retry_count = email.get("retry_count", 0)
            last_attempt = email.get("last_attempt", email.get("created_at"))
            
            if retry_count >= len(FailedEmails.RETRY_DELAY_HOURS):
                delay_hours = FailedEmails.RETRY_DELAY_HOURS[-1]
            else:
                delay_hours = FailedEmails.RETRY_DELAY_HOURS[retry_count]
            
            next_retry_at = last_attempt + timedelta(hours=delay_hours)
            
            if now >= next_retry_at:
                eligible.append(email)
        
        return eligible
    
    @staticmethod
    def mark_retry_attempt(email_id: str, success: bool, error: str = None):
        """Record a retry attempt"""
        from bson import ObjectId
        
        update = {
            "$inc": {"retry_count": 1},
            "$set": {"last_retry_at": datetime.utcnow()}
        }
        
        if success:
            update["$set"]["status"] = Email.STATUS_SENT
            update["$set"]["sent_at"] = datetime.utcnow()
        else:
            update["$set"]["last_error"] = error
        
        emails_collection.update_one(
            {"_id": ObjectId(email_id)},
            update
        )
    
    @staticmethod
    def get_retry_stats() -> Dict:
        """Get statistics about failed/retryable emails"""
        pipeline = [
            {"$match": {"status": Email.STATUS_FAILED}},
            {"$group": {
                "_id": None,
                "total_failed": {"$sum": 1},
                "with_retries": {"$sum": {"$cond": [{"$gt": [{"$ifNull": ["$retry_count", 0]}, 0]}, 1, 0]}},
                "max_retries_reached": {"$sum": {"$cond": [{"$gte": [{"$ifNull": ["$retry_count", 0]}, FailedEmails.MAX_RETRIES]}, 1, 0]}}
            }}
        ]
        result = list(emails_collection.aggregate(pipeline))
        if result:
            return result[0]
        return {"total_failed": 0, "with_retries": 0, "max_retries_reached": 0}


class DoNotContact:
    """
    Persistent blocklist for emails that should never be contacted.
    
    Reasons for blocking:
    - unsubscribe: Recipient requested to be removed
    - complaint: Spam complaint received
    - manual: Manually added by user
    - hard_bounce: Permanent delivery failure
    """
    
    _collection = db["do_not_contact"]
    _collection.create_index("email", unique=True)
    _collection.create_index("added_at")
    
    REASON_UNSUBSCRIBE = "unsubscribe"
    REASON_COMPLAINT = "complaint"
    REASON_MANUAL = "manual"
    REASON_HARD_BOUNCE = "hard_bounce"
    REASON_AUTO_REPLY = "auto_reply_permanent"  # e.g., "no longer with company"
    
    @staticmethod
    def add(email: str, reason: str, notes: str = None, source_email_id: str = None) -> bool:
        """
        Add an email to the do-not-contact list.
        
        Args:
            email: Email address to block
            reason: Why they're blocked (use REASON_* constants)
            notes: Optional notes/context
            source_email_id: ID of the email that triggered this (for audit trail)
        
        Returns:
            True if added, False if already exists
        """
        email = email.lower().strip()
        
        try:
            DoNotContact._collection.insert_one({
                "email": email,
                "reason": reason,
                "notes": notes,
                "source_email_id": source_email_id,
                "added_at": datetime.utcnow()
            })
            print(f"   🚫 Added {email} to do-not-contact list (reason: {reason})")
            return True
        except Exception:
            # Already exists (duplicate key error)
            return False
    
    @staticmethod
    def is_blocked(email: str) -> bool:
        """Check if an email is on the do-not-contact list"""
        email = email.lower().strip()
        return DoNotContact._collection.find_one({"email": email}) is not None
    
    @staticmethod
    def get_reason(email: str) -> Optional[str]:
        """Get the reason an email is blocked (or None if not blocked)"""
        email = email.lower().strip()
        record = DoNotContact._collection.find_one({"email": email})
        return record.get("reason") if record else None
    
    @staticmethod
    def remove(email: str) -> bool:
        """Remove an email from the do-not-contact list"""
        email = email.lower().strip()
        result = DoNotContact._collection.delete_one({"email": email})
        return result.deleted_count > 0
    
    @staticmethod
    def get_all(reason: str = None, limit: int = 100) -> List[Dict]:
        """Get all blocked emails, optionally filtered by reason"""
        query = {"reason": reason} if reason else {}
        return list(DoNotContact._collection.find(query).limit(limit))
    
    @staticmethod
    def count(reason: str = None) -> int:
        """Count blocked emails, optionally filtered by reason"""
        query = {"reason": reason} if reason else {}
        return DoNotContact._collection.count_documents(query)
    
    @staticmethod
    def get_stats() -> Dict[str, int]:
        """Get count by reason"""
        pipeline = [
            {"$group": {"_id": "$reason", "count": {"$sum": 1}}}
        ]
        results = list(DoNotContact._collection.aggregate(pipeline))
        return {r["_id"]: r["count"] for r in results}


class SearchOffsetTracker:
    """
    Track search pagination offsets to avoid re-searching the same people.
    
    Problem: RocketReach always returns results starting from position 1.
    If we search for "Founders in US" multiple times, we get the SAME people.
    
    Solution: Track the last offset we searched to, and start from there next time.
    """
    
    _collection = db["search_offsets"]
    _collection.create_index("search_hash", unique=True)
    
    @staticmethod
    def _hash_criteria(criteria: Dict) -> str:
        """Create a unique hash for search criteria"""
        import hashlib
        # Sort keys for consistent hashing
        criteria_str = json.dumps(criteria, sort_keys=True)
        return hashlib.md5(criteria_str.encode()).hexdigest()
    
    @staticmethod
    def get_next_offset(criteria: Dict) -> int:
        """Get the starting offset for this search criteria"""
        search_hash = SearchOffsetTracker._hash_criteria(criteria)
        record = SearchOffsetTracker._collection.find_one({"search_hash": search_hash})
        
        if record:
            return record.get("next_offset", 1)
        return 1
    
    @staticmethod
    def update_offset(criteria: Dict, new_offset: int, total_available: int = None):
        """Update the offset after a search"""
        search_hash = SearchOffsetTracker._hash_criteria(criteria)
        
        update_data = {
            "search_hash": search_hash,
            "criteria_summary": str(criteria)[:200],  # For debugging
            "next_offset": new_offset,
            "updated_at": datetime.utcnow()
        }
        
        if total_available:
            update_data["total_available"] = total_available
        
        SearchOffsetTracker._collection.update_one(
            {"search_hash": search_hash},
            {"$set": update_data, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True
        )
    
    @staticmethod
    def reset_offset(criteria: Dict):
        """Reset offset for a search (start from beginning)"""
        search_hash = SearchOffsetTracker._hash_criteria(criteria)
        SearchOffsetTracker._collection.delete_one({"search_hash": search_hash})
    
    @staticmethod
    def get_all_offsets() -> List[Dict]:
        """Get all tracked offsets for debugging"""
        return list(SearchOffsetTracker._collection.find({}, {"_id": 0}))


class SchedulerConfig:
    """
    MongoDB-based scheduler configuration for fully autonomous operation.
    
    Stores:
    - Scheduled campaigns (times, days, settings)
    - ICP run history (when each ICP was last used)
    - Performance-based adjustments
    - System settings
    
    This replaces the static scheduler_config.json file.
    """
    
    _collection = db["scheduler_config"]
    _run_history = db["icp_run_history"]
    
    # Create indexes
    _collection.create_index("config_type", unique=True)
    _run_history.create_index([("icp_template", 1), ("run_date", -1)])
    _run_history.create_index("run_date")
    
    # Config types
    CONFIG_MAIN = "main"
    CONFIG_SETTINGS = "settings"
    
    @staticmethod
    def initialize_default_config():
        """
        Initialize with default autonomous configuration.
        Only runs if no config exists yet.
        """
        existing = SchedulerConfig._collection.find_one({"config_type": SchedulerConfig.CONFIG_MAIN})
        if existing:
            return existing
        
        default_config = {
            "config_type": SchedulerConfig.CONFIG_MAIN,
            "mode": "autonomous",  # "autonomous" or "manual"
            "scheduled_campaigns": [
                {
                    "name": "morning_campaign",
                    "description": "Morning Autonomous Campaign",
                    "autonomous": True,
                    "schedule_time": "09:30",
                    "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                    "max_leads": 15,
                    "enabled": True
                },
                {
                    "name": "afternoon_campaign",
                    "description": "Afternoon Autonomous Campaign",
                    "autonomous": True,
                    "schedule_time": "14:30",
                    "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                    "max_leads": 15,
                    "enabled": True
                }
            ],
            "schedules": {
                "followup_check": "11:00",
                "initial_emails": "09:30"
            },
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        SchedulerConfig._collection.insert_one(default_config)
        
        # Also initialize settings
        default_settings = {
            "config_type": SchedulerConfig.CONFIG_SETTINGS,
            "timezone": "America/New_York",  # US Eastern - target audience timezone
            "pause_weekends": True,
            "max_emails_per_day_per_mailbox": 25,
            "min_delay_minutes": 7,
            "max_delay_minutes": 12,
            "exploration_rate": 0.3,  # 30% chance to try underperforming ICPs
            "min_days_between_same_icp": 2,  # Don't run same ICP 2 days in a row
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        SchedulerConfig._collection.update_one(
            {"config_type": SchedulerConfig.CONFIG_SETTINGS},
            {"$set": default_settings},
            upsert=True
        )
        
        return default_config
    
    @staticmethod
    def get_config() -> Dict[str, Any]:
        """Get the main scheduler configuration."""
        config = SchedulerConfig._collection.find_one({"config_type": SchedulerConfig.CONFIG_MAIN})
        if not config:
            config = SchedulerConfig.initialize_default_config()
        return config
    
    @staticmethod
    def get_settings() -> Dict[str, Any]:
        """Get scheduler settings."""
        settings = SchedulerConfig._collection.find_one({"config_type": SchedulerConfig.CONFIG_SETTINGS})
        if not settings:
            SchedulerConfig.initialize_default_config()
            settings = SchedulerConfig._collection.find_one({"config_type": SchedulerConfig.CONFIG_SETTINGS})
        return settings
    
    @staticmethod
    def update_setting(key: str, value: Any):
        """Update a specific setting."""
        SchedulerConfig._collection.update_one(
            {"config_type": SchedulerConfig.CONFIG_SETTINGS},
            {"$set": {key: value, "updated_at": datetime.utcnow()}}
        )
    
    @staticmethod
    def add_scheduled_campaign(campaign: Dict) -> bool:
        """Add a new scheduled campaign."""
        SchedulerConfig._collection.update_one(
            {"config_type": SchedulerConfig.CONFIG_MAIN},
            {
                "$push": {"scheduled_campaigns": campaign},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        return True
    
    @staticmethod
    def update_scheduled_campaign(campaign_name: str, updates: Dict):
        """Update a scheduled campaign by name."""
        SchedulerConfig._collection.update_one(
            {
                "config_type": SchedulerConfig.CONFIG_MAIN,
                "scheduled_campaigns.name": campaign_name
            },
            {
                "$set": {
                    "scheduled_campaigns.$": {**updates, "name": campaign_name},
                    "updated_at": datetime.utcnow()
                }
            }
        )
    
    @staticmethod
    def enable_campaign(campaign_name: str, enabled: bool = True):
        """Enable or disable a scheduled campaign."""
        SchedulerConfig._collection.update_one(
            {
                "config_type": SchedulerConfig.CONFIG_MAIN,
                "scheduled_campaigns.name": campaign_name
            },
            {
                "$set": {
                    "scheduled_campaigns.$.enabled": enabled,
                    "updated_at": datetime.utcnow()
                }
            }
        )
    
    # ==================== ICP Run History ====================
    
    @staticmethod
    def record_icp_run(icp_template: str, campaign_id: str = None, 
                       leads_sent: int = 0, results: Dict = None):
        """
        Record that an ICP was used for a campaign run.
        This is critical for autonomous rotation and learning.
        """
        run_record = {
            "icp_template": icp_template,
            "run_date": datetime.utcnow(),
            "campaign_id": campaign_id,
            "leads_sent": leads_sent,
            "results": results or {},
            "day_of_week": datetime.utcnow().strftime("%A").lower()
        }
        SchedulerConfig._run_history.insert_one(run_record)
    
    @staticmethod
    def get_last_run(icp_template: str) -> Optional[Dict]:
        """Get the last time this ICP was used."""
        return SchedulerConfig._run_history.find_one(
            {"icp_template": icp_template},
            sort=[("run_date", -1)]
        )
    
    @staticmethod
    def get_runs_today() -> List[Dict]:
        """Get all ICP runs from today."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return list(SchedulerConfig._run_history.find(
            {"run_date": {"$gte": today_start}}
        ))
    
    @staticmethod
    def get_icps_used_recently(days: int = 2) -> List[str]:
        """Get ICPs used in the last N days (for rotation)."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        runs = SchedulerConfig._run_history.find(
            {"run_date": {"$gte": cutoff}},
            {"icp_template": 1}
        )
        return list(set(r["icp_template"] for r in runs))
    
    @staticmethod
    def get_icp_run_stats(days: int = 30) -> Dict[str, Any]:
        """
        Get statistics on ICP runs for the last N days.
        Used for autonomous ICP selection.
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {"$match": {"run_date": {"$gte": cutoff}}},
            {"$group": {
                "_id": "$icp_template",
                "total_runs": {"$sum": 1},
                "total_leads": {"$sum": "$leads_sent"},
                "last_run": {"$max": "$run_date"},
                "days_since_last_run": {"$max": "$run_date"}
            }},
            {"$sort": {"total_runs": -1}}
        ]
        
        results = list(SchedulerConfig._run_history.aggregate(pipeline))
        
        # Calculate days since last run
        now = datetime.utcnow()
        for r in results:
            if r.get("last_run"):
                r["days_since_last_run"] = (now - r["last_run"]).days
            else:
                r["days_since_last_run"] = 999
        
        return {
            "by_icp": {r["_id"]: r for r in results},
            "total_runs": sum(r["total_runs"] for r in results),
            "period_days": days
        }
    
    @staticmethod
    def select_icp_for_autonomous_run() -> Dict[str, Any]:
        """
        CORE AUTONOMOUS SELECTION ALGORITHM
        
        Selects the best ICP to run next based on:
        1. Performance data (reply rates from Email.get_icp_analytics)
        2. Recency (avoid using same ICP too frequently)
        3. Exploration (occasionally try underperformers)
        
        Returns:
            Dict with selected_icp, reason, and scoring details
        """
        import random
        from primestrides_context import ICP_TEMPLATES
        
        settings = SchedulerConfig.get_settings()
        exploration_rate = settings.get("exploration_rate", 0.3)
        min_days_gap = settings.get("min_days_between_same_icp", 2)
        
        # Get performance analytics
        analytics = Email.get_icp_analytics()
        by_template = analytics.get("by_template", {})
        
        # Get run history
        run_stats = SchedulerConfig.get_icp_run_stats(days=30)
        icps_used_recently = SchedulerConfig.get_icps_used_recently(days=min_days_gap)
        icps_used_today = [r["icp_template"] for r in SchedulerConfig.get_runs_today()]
        
        all_templates = list(ICP_TEMPLATES.keys())
        
        # Score each ICP
        scored_icps = []
        
        for template in all_templates:
            perf = by_template.get(template, {"sent": 0, "replied": 0, "reply_rate": 0})
            run_info = run_stats.get("by_icp", {}).get(template, {})
            
            sent = perf.get("sent", 0)
            reply_rate = perf.get("reply_rate", 0)
            days_since_run = run_info.get("days_since_last_run", 999)
            
            # Skip if used today already
            if template in icps_used_today:
                continue
            
            # Base score from performance
            if sent == 0:
                # Never tested - high exploration value
                performance_score = 50
                reason = "Never tested - exploring"
            elif sent < 20:
                # Low data - moderate exploration
                performance_score = 30 + reply_rate * 2
                reason = f"Low data ({sent} sent) - exploring"
            else:
                # Enough data - use performance
                performance_score = reply_rate * 10
                reason = f"Performance: {reply_rate}% reply rate"
            
            # Recency bonus (prefer ICPs not used recently)
            if template in icps_used_recently:
                recency_penalty = -30
                reason += " (used recently, -30)"
            elif days_since_run > 7:
                recency_bonus = min(20, days_since_run)
                performance_score += recency_bonus
                reason += f" (+{recency_bonus} recency)"
            else:
                recency_penalty = 0
                performance_score += recency_penalty
            
            final_score = max(0, performance_score)
            
            scored_icps.append({
                "template": template,
                "score": final_score,
                "reason": reason,
                "sent": sent,
                "reply_rate": reply_rate,
                "days_since_run": days_since_run
            })
        
        if not scored_icps:
            # All ICPs used today - pick least recently used
            scored_icps = [{"template": t, "score": 0, "reason": "fallback"} for t in all_templates]
        
        # Sort by score
        scored_icps.sort(key=lambda x: x["score"], reverse=True)
        
        # Exploration vs Exploitation
        if random.random() < exploration_rate and len(scored_icps) > 1:
            # Explore: Pick from top 3 randomly (weighted by score)
            top_candidates = scored_icps[:min(3, len(scored_icps))]
            weights = [max(1, c["score"]) for c in top_candidates]
            selected = random.choices(top_candidates, weights=weights, k=1)[0]
            selection_mode = "exploration"
        else:
            # Exploit: Pick the best
            selected = scored_icps[0]
            selection_mode = "exploitation"
        
        return {
            "selected_icp": selected["template"],
            "selection_reason": selected["reason"],
            "selection_mode": selection_mode,
            "score": selected["score"],
            "all_scores": {s["template"]: {"score": s["score"], "reason": s["reason"]} 
                          for s in scored_icps[:5]},
            "icps_excluded_today": icps_used_today
        }

