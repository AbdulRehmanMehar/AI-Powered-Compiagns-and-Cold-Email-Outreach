from pymongo import MongoClient
from datetime import datetime
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
        lead = {
            "email": data.get("email"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "full_name": data.get("name") or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip(),
            "title": data.get("current_title") or data.get("title"),
            "company": data.get("current_employer") or data.get("company"),
            "linkedin_url": data.get("linkedin_url"),
            "location": data.get("location"),
            "industry": data.get("industry"),
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
        return leads_collection.find_one({"email": email})
    
    @staticmethod
    def get_by_id(lead_id: str) -> Optional[Dict]:
        from bson import ObjectId
        return leads_collection.find_one({"_id": ObjectId(lead_id)})
    
    @staticmethod
    def get_all() -> List[Dict]:
        return list(leads_collection.find())


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
