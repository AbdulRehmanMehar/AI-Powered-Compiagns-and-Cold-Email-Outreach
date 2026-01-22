from pymongo import MongoClient
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import config

client = MongoClient(config.DATABASE_URL)
db = client.get_database()

# Collections
leads_collection = db["leads"]
emails_collection = db["emails"]
campaigns_collection = db["campaigns"]

# Create indexes
leads_collection.create_index("email", unique=True)
emails_collection.create_index([("lead_id", 1), ("campaign_id", 1)])
emails_collection.create_index("status")


class Lead:
    """Lead/Contact model"""
    
    @staticmethod
    def create(data: Dict[str, Any]) -> str:
        """Create or update a lead"""
        # Extract first_name - try from data, or parse from full name
        first_name = data.get("first_name")
        full_name = data.get("name") or data.get("full_name") or ""
        
        # If first_name is None/empty but we have full_name, extract it
        if not first_name and full_name:
            first_name = full_name.split()[0] if full_name.split() else None
        
        lead = {
            "email": data.get("email"),
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
        
        # Extract first_name from full_name if missing
        full_name = lead.get('full_name') or ''
        first_name = lead.get('first_name')
        if not first_name and full_name:
            first_name = full_name.split()[0] if full_name.split() else 'there'
        
        # Get industry from raw_data if missing
        industry = lead.get('industry')
        if not industry and lead.get('raw_data'):
            industry = lead['raw_data'].get('current_employer_industry')
        
        # Apply safe defaults for commonly-used fields
        lead['first_name'] = first_name or 'there'
        lead['full_name'] = full_name or lead.get('email', '').split('@')[0]
        lead['industry'] = industry or ''
        lead['title'] = lead.get('title') or ''
        lead['company'] = lead.get('company') or ''
        
        return lead


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
               email_type: str = "initial", followup_number: int = 0) -> str:
        """Create a new email record"""
        from bson import ObjectId
        
        email = {
            "lead_id": ObjectId(lead_id),
            "campaign_id": ObjectId(campaign_id),
            "subject": subject,
            "body": body,
            "email_type": email_type,  # "initial" or "followup"
            "followup_number": followup_number,
            "status": Email.STATUS_PENDING,
            "created_at": datetime.utcnow(),
            "scheduled_at": None,
            "sent_at": None,
            "opened_at": None,
            "replied_at": None,
            "error_message": None,
        }
        
        result = emails_collection.insert_one(email)
        return str(result.inserted_id)
    
    @staticmethod
    def mark_sent(email_id: str):
        from bson import ObjectId
        emails_collection.update_one(
            {"_id": ObjectId(email_id)},
            {"$set": {"status": Email.STATUS_SENT, "sent_at": datetime.utcnow()}}
        )
    
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
        """Get leads that need follow-up emails"""
        from bson import ObjectId
        from datetime import timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_since_last)
        
        pipeline = [
            {"$match": {"campaign_id": ObjectId(campaign_id), "status": Email.STATUS_SENT}},
            {"$sort": {"sent_at": -1}},
            {"$group": {
                "_id": "$lead_id",
                "last_email": {"$first": "$$ROOT"},
                "email_count": {"$sum": 1}
            }},
            {"$match": {
                "last_email.sent_at": {"$lt": cutoff_date},
                "email_count": {"$lt": config.MAX_FOLLOWUPS + 1},
                "last_email.status": {"$nin": [Email.STATUS_REPLIED, Email.STATUS_BOUNCED]}
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
        """Get how many days this account has been sending"""
        # Find the earliest send date for this account
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
