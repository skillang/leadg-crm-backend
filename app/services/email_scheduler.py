# app/services/email_scheduler.py
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any
import logging
from bson import ObjectId

from app.services.communication_service import CommunicationService

from ..config.database import get_database
from ..services.zepto_client import zepto_client

logger = logging.getLogger(__name__)

class EmailSchedulerService:
    """Background service to process scheduled emails"""
    
    def __init__(self):
        self.db = get_database()
        self.zepto_client = zepto_client
        self.is_running = False
        self.collection_name = "crm_lead_emails"
    
    async def start_scheduler(self):
        """Start the background scheduler"""
        if self.is_running:
            logger.warning("Email scheduler is already running")
            return
        
        self.is_running = True
        logger.info("🕒 Email scheduler started")
        
        # Run scheduler loop
        asyncio.create_task(self._scheduler_loop())
    
    async def stop_scheduler(self):
        """Stop the background scheduler"""
        self.is_running = False
        logger.info("🛑 Email scheduler stopped")
    
    async def _scheduler_loop(self):
        """Main scheduler loop - checks every minute for due emails"""
        while self.is_running:
            try:
                await self._process_due_emails()
                # Wait 1 minute before next check
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(60)  # Continue even if error occurs
    
    async def _process_due_emails(self):
        """Find and process emails that are due for sending"""
        try:
            now_utc = datetime.utcnow()
            
            # Find pending scheduled emails that are due
            query = {
                "status": "pending",
                "is_scheduled": True,
                "scheduled_time": {"$lte": now_utc}
            }
            
            due_emails_cursor = self.db[self.collection_name].find(query)
            due_emails = await due_emails_cursor.to_list(None)
            
            if due_emails:
                logger.info(f"📧 Processing {len(due_emails)} due emails")
                
                for email_doc in due_emails:
                    await self._send_scheduled_email(email_doc)
            
        except Exception as e:
            logger.error(f"Error processing due emails: {e}")
    
    async def _send_scheduled_email(self, email_doc: Dict[str, Any]):
        """Send a single scheduled email"""
        try:
            email_id = email_doc["email_id"]
            logger.info(f"📤 Sending scheduled email {email_id}")
            
            # Mark as processing to avoid double-sending
            await self.db[self.collection_name].update_one(
                {"_id": email_doc["_id"]},
                {"$set": {"status": "processing", "updated_at": datetime.utcnow()}}
            )
            
            recipients = email_doc.get("recipients", [])
            if not recipients:
                await self._mark_email_failed(email_id, "No recipients found")
                return
            
            # Send emails to all recipients
            results = []
            successful_count = 0
            failed_count = 0
            
            for recipient in recipients:
                try:
                    # Send individual email using ZeptoMail
                    result = await self.zepto_client.send_template_email(
                        template_key=email_doc["template_key"],
                        sender_email=email_doc["sender_email"],
                        recipient_email=recipient["email"],
                        recipient_name=recipient["name"],
                        merge_data={"username": recipient["name"]}
                    )
                    
                    if result["success"]:
                        successful_count += 1
                        results.append({
                            "recipient": recipient["email"],
                            "status": "sent",
                            "sent_at": datetime.utcnow()
                        })
                    else:
                        failed_count += 1
                        results.append({
                            "recipient": recipient["email"], 
                            "status": "failed",
                            "error": result.get("error", "Unknown error"),
                            "failed_at": datetime.utcnow()
                        })
                    
                    # Small delay between emails
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error sending to {recipient['email']}: {e}")
                    results.append({
                        "recipient": recipient["email"],
                        "status": "failed", 
                        "error": str(e),
                        "failed_at": datetime.utcnow()
                    })
            
            # Update email status based on results
            if successful_count > 0:
                final_status = "sent" if failed_count == 0 else "partial"
                await self._mark_email_sent(email_id, final_status, successful_count, failed_count, results)
                logger.info(f"✅ Email {email_id} sent: {successful_count} success, {failed_count} failed")
            else:
                await self._mark_email_failed(email_id, "All recipients failed", results)
                logger.error(f"❌ Email {email_id} failed: all recipients failed")
            
            # Log activities
            await self._log_scheduled_email_activities(email_doc, results, successful_count > 0)
            
        except Exception as e:
            logger.error(f"Error sending scheduled email {email_doc.get('email_id')}: {e}")
            await self._mark_email_failed(email_doc["email_id"], f"Scheduler error: {str(e)}")
    
    async def _mark_email_sent(self, email_id: str, status: str, sent_count: int, failed_count: int, results: list):
        """Mark email as sent with results"""
        update_data = {
            "status": status,
            "sent_at": datetime.utcnow(),
            "sent_count": sent_count,
            "failed_count": failed_count,
            "updated_at": datetime.utcnow(),
            "results": results
        }
        
        await self.db[self.collection_name].update_one(
            {"email_id": email_id},
            {"$set": update_data}
        )
    
    async def _mark_email_failed(self, email_id: str, error_message: str, results: list = None):
        """Mark email as failed"""
        update_data = {
            "status": "failed",
            "error_message": error_message,
            "failed_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        if results:
            update_data["results"] = results
        
        await self.db[self.collection_name].update_one(
            {"email_id": email_id},
            {"$set": update_data}
        )
    
    async def _log_scheduled_email_activities(self, email_doc: Dict[str, Any], results: list, success: bool):
        """Log email activities to lead_activities collection"""
        try:
            activities = []
            
            if email_doc.get("email_type") == "single":
                # Single lead activity
                lead_id = email_doc.get("lead_id")
                if lead_id:
                    if success:
                        await CommunicationService.log_email_communication(
                            lead_id=lead_id,
                            template_key=email_doc.get("template_key")
                        )
                    activity = {
                        "_id": ObjectId(),
                        "lead_id": lead_id,
                        "activity_type": "scheduled_email_sent" if success else "scheduled_email_failed",
                        "description": f"Scheduled email {'sent' if success else 'failed'} using template '{email_doc.get('template_key')}'",
                        "metadata": {
                            "email_id": email_doc["email_id"],
                            "template_key": email_doc.get("template_key"),
                            "sender_email": email_doc.get("sender_email"),
                            "scheduled": True,
                            "success": success,
                            "recipients_count": len(results)
                        },
                        "created_by": email_doc.get("created_by"),
                        "created_by_name": email_doc.get("created_by_name"),
                        "created_at": datetime.utcnow()
                    }
                    activities.append(activity)
            else:
                # Bulk email activities
                lead_ids = email_doc.get("lead_ids", [])
                for lead_id in lead_ids:
                    if success:
                        await CommunicationService.log_email_communication(
                            lead_id=lead_id,
                            template_key=email_doc.get("template_key")
                        )
                    activity = {
                        "_id": ObjectId(),
                        "lead_id": lead_id,
                        "activity_type": "scheduled_bulk_email_sent" if success else "scheduled_bulk_email_failed",
                        "description": f"Scheduled bulk email {'sent' if success else 'failed'} using template '{email_doc.get('template_key')}'",
                        "metadata": {
                            "email_id": email_doc["email_id"],
                            "template_key": email_doc.get("template_key"),
                            "sender_email": email_doc.get("sender_email"),
                            "total_recipients": email_doc.get("total_recipients"),
                            "scheduled": True,
                            "success": success
                        },
                        "created_by": email_doc.get("created_by"),
                        "created_by_name": email_doc.get("created_by_name"),
                        "created_at": datetime.utcnow()
                    }
                    activities.append(activity)
            
            # Insert activities
            if activities:
                await self.db.lead_activities.insert_many(activities)
                logger.info(f"Logged {len(activities)} scheduled email activities")
                
        except Exception as e:
            logger.error(f"Error logging scheduled email activities: {e}")
    
    async def get_scheduler_status(self) -> Dict[str, Any]:
        """Get scheduler status and statistics"""
        try:
            now_utc = datetime.utcnow()
            
            # Count pending scheduled emails
            pending_count = await self.db[self.collection_name].count_documents({
                "status": "pending",
                "is_scheduled": True
            })
            
            # Count overdue emails (should have been sent but are still pending)
            overdue_count = await self.db[self.collection_name].count_documents({
                "status": "pending",
                "is_scheduled": True,
                "scheduled_time": {"$lt": now_utc}
            })
            
            # Next email to be sent
            next_email_cursor = self.db[self.collection_name].find({
                "status": "pending",
                "is_scheduled": True,
                "scheduled_time": {"$gt": now_utc}
            }).sort("scheduled_time", 1).limit(1)
            
            next_emails = await next_email_cursor.to_list(1)
            next_email_time = next_emails[0]["scheduled_time"] if next_emails else None
            
            return {
                "is_running": self.is_running,
                "pending_emails": pending_count,
                "overdue_emails": overdue_count,
                "next_email_time": next_email_time,
                "current_time_utc": now_utc
            }
            
        except Exception as e:
            logger.error(f"Error getting scheduler status: {e}")
            return {
                "is_running": self.is_running,
                "error": str(e)
            }

# Global scheduler instance
email_scheduler = EmailSchedulerService()