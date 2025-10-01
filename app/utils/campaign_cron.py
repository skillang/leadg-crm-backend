# app/utils/campaign_cron.py
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging
from bson import ObjectId

from app.config.database import get_database
from app.services.campaign_service import campaign_service

logger = logging.getLogger(__name__)


class CampaignCron:
    """
    Cron service for processing campaign jobs
    Runs every 1 minute to check and execute pending jobs
    """
    
    def __init__(self):
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the campaign cron job"""
        if self.is_running:
            logger.warning("Campaign cron is already running")
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._run_loop())
        logger.info("Campaign cron started - checking jobs every 1 minute")
    
    async def stop(self):
        """Stop the campaign cron job"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("Campaign cron stopped")
    
    async def _run_loop(self):
        """Main cron loop - runs every minute"""
        while self.is_running:
            try:
                await self._process_pending_jobs()
                
                # Wait 1 minute before next check
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in campaign cron loop: {str(e)}")
                await asyncio.sleep(60)  # Continue even if error occurs
    
    async def _process_pending_jobs(self):
        """Process all pending jobs that are due"""
        try:
            db = get_database()
            current_time = datetime.utcnow()
            
            # Find pending jobs that are due
            pending_jobs = await db.campaign_tracking.find({
                "job_type": "message_job",
                "status": "pending",
                "execute_at": {"$lte": current_time}
            }).to_list(length=100)  # Process max 100 jobs per minute
            
            if not pending_jobs:
                logger.debug("No pending campaign jobs to process")
                return
            
            logger.info(f"Processing {len(pending_jobs)} pending campaign jobs")
            
            # Process each job
            for job in pending_jobs:
                try:
                    await self._execute_job(job)
                except Exception as job_error:
                    logger.error(f"Error executing job {job.get('_id')}: {str(job_error)}")
                    continue
            
        except Exception as e:
            logger.error(f"Error processing pending jobs: {str(e)}")
    
    async def _execute_job(self, job: Dict[str, Any]):
        """
        Execute a single campaign job
        
        Args:
            job: Job document from database
        """
        try:
            db = get_database()
            job_id = job["_id"]
            campaign_id = job["campaign_id"]
            lead_id = job["lead_id"]
            
            logger.info(f"Executing job {job_id} for lead {lead_id} in campaign {campaign_id}")
            
            # Check if campaign is still active
            campaign = await campaign_service.get_campaign(campaign_id)
            if not campaign or campaign["status"] != "active":
                logger.info(f"Campaign {campaign_id} not active, skipping job")
                await self._cancel_job(job_id)
                return
            
            # Check if enrollment is still active
            enrollment = await db.campaign_tracking.find_one({
                "campaign_id": campaign_id,
                "lead_id": lead_id,
                "job_type": "enrollment"
            })
            
            if not enrollment or enrollment["status"] != "active":
                logger.info(f"Enrollment not active for lead {lead_id}, skipping job")
                await self._cancel_job(job_id)
                return
            
            # Check if lead still matches criteria
            lead = await db.leads.find_one({"lead_id": lead_id})
            if not lead:
                logger.warning(f"Lead {lead_id} not found, skipping job")
                await self._fail_job(job_id, "Lead not found")
                return
            
            still_matches = await self._check_lead_matches_criteria(campaign, lead)
            if not still_matches:
                logger.info(f"Lead {lead_id} no longer matches criteria, pausing enrollment")
                await self._pause_enrollment(campaign_id, lead_id)
                return
            
            # Send the message
            success = await self._send_message(job, lead, campaign)
            
            if success:
                # Mark job as completed
                await db.campaign_tracking.update_one(
                    {"_id": job_id},
                    {
                        "$set": {
                            "status": "completed",
                            "executed_at": datetime.utcnow(),
                            "completed_at": datetime.utcnow()
                        }
                    }
                )
                
                # Update enrollment progress
                await db.campaign_tracking.update_one(
                    {
                        "campaign_id": campaign_id,
                        "lead_id": lead_id,
                        "job_type": "enrollment"
                    },
                    {
                        "$inc": {"messages_sent": 1},
                        "$set": {
                            "current_sequence": job["sequence_order"],
                            "last_message_sent_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                logger.info(f"Job {job_id} completed successfully")
            else:
                # Increment attempts
                new_attempts = job["attempts"] + 1
                
                if new_attempts >= job["max_attempts"]:
                    # Max attempts reached, mark as failed
                    await self._fail_job(job_id, "Max retry attempts reached")
                else:
                    # Retry later
                    await db.campaign_tracking.update_one(
                        {"_id": job_id},
                        {
                            "$set": {
                                "attempts": new_attempts,
                                "execute_at": datetime.utcnow() + timedelta(minutes=5),
                                "updated_at": datetime.utcnow()
                            }
                        }
                    )
                    logger.info(f"Job {job_id} will retry (attempt {new_attempts}/{job['max_attempts']})")
            
        except Exception as e:
            logger.error(f"Error executing job: {str(e)}")
            await self._fail_job(job["_id"], str(e))
    
    async def _send_message(
        self,
        job: Dict[str, Any],
        lead: Dict[str, Any],
        campaign: Dict[str, Any]
    ) -> bool:
        """
        Send message via WhatsApp or Email
        
        Returns:
            True if successful
        """
        try:
            channel = job["channel"]
            template_name = job["template_name"]
            lead_name = lead.get("name", "")
            
            if channel == "whatsapp":
                # Use existing WhatsApp service
                from app.services.whatsapp_message_service import whatsapp_message_service
                
                contact_number = lead.get("contact_number") or lead.get("phone_number")
                if not contact_number:
                    logger.error(f"No phone number for lead {lead['lead_id']}")
                    return False
                
                result = await whatsapp_message_service.send_template_message(
                    contact=contact_number,
                    template_name=template_name,
                    lead_name=lead_name
                )
                
                return result.get("success", False)
                
            elif channel == "email":
                # Use existing email service
                from app.services.zepto_client import send_single_email
                
                email = lead.get("email")
                if not email:
                    logger.error(f"No email for lead {lead['lead_id']}")
                    return False
                
                # Get template key from job
                template_key = job.get("template_id")
                
                result = await send_single_email(
                    template_key=template_key,
                    sender_prefix="noreply",
                    recipient_email=email,
                    recipient_name=lead_name,
                    merge_data={"username": lead_name}
                )
                
                return result.get("success", False)
            
            return False
            
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return False
    
    async def _check_lead_matches_criteria(
    self,
    campaign: Dict[str, Any],
    lead: Dict[str, Any]
) -> bool:
        """Check if lead still matches campaign criteria"""
        try:
            if campaign["send_to_all"]:
                return True
            
            # Import the converter functions
            from app.services.campaign_executor import campaign_executor
            
            # Get required stage and source names from campaign
            required_stages = []
            required_sources = []
            
            if campaign.get("stage_ids"):
                required_stages = await campaign_executor._convert_stage_ids_to_names(campaign["stage_ids"])
                logger.debug(f"Required stages: {required_stages}, Lead stage: {lead.get('stage')}")
            
            if campaign.get("source_ids"):
                required_sources = await campaign_executor._convert_source_ids_to_names(campaign["source_ids"])
                logger.debug(f"Required sources: {required_sources}, Lead source: {lead.get('source')}")
            
            # Get current lead stage and source
            current_stage = lead.get("stage")
            current_source = lead.get("source")
            
            # Check based on what's configured in campaign
            if required_stages and required_sources:
                # Both stage AND source must match
                stage_match = current_stage in required_stages
                source_match = current_source in required_sources
                logger.debug(f"Both criteria check - Stage match: {stage_match}, Source match: {source_match}")
                return stage_match and source_match
            
            elif required_stages:
                # Only stage needs to match
                stage_match = current_stage in required_stages
                logger.debug(f"Stage only check - Match: {stage_match}")
                return stage_match
            
            elif required_sources:
                # Only source needs to match
                source_match = current_source in required_sources
                logger.debug(f"Source only check - Match: {source_match}")
                return source_match
            
            # No criteria specified
            return True
            
        except Exception as e:
            logger.error(f"Error checking lead criteria match: {str(e)}")
            return False
    
    async def _pause_enrollment(self, campaign_id: str, lead_id: str):
        """Pause enrollment when criteria no longer match"""
        try:
            db = get_database()
            
            await db.campaign_tracking.update_one(
                {
                    "campaign_id": campaign_id,
                    "lead_id": lead_id,
                    "job_type": "enrollment"
                },
                {
                    "$set": {
                        "status": "criteria_not_matched",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            # Cancel pending jobs
            await db.campaign_tracking.update_many(
                {
                    "campaign_id": campaign_id,
                    "lead_id": lead_id,
                    "job_type": "message_job",
                    "status": "pending"
                },
                {
                    "$set": {
                        "status": "cancelled",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Error pausing enrollment: {str(e)}")
    
    async def _cancel_job(self, job_id: ObjectId):
        """Cancel a job"""
        try:
            db = get_database()
            await db.campaign_tracking.update_one(
                {"_id": job_id},
                {
                    "$set": {
                        "status": "cancelled",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
        except Exception as e:
            logger.error(f"Error cancelling job: {str(e)}")
    
    async def _fail_job(self, job_id: ObjectId, error_message: str):
        """Mark job as failed"""
        try:
            db = get_database()
            await db.campaign_tracking.update_one(
                {"_id": job_id},
                {
                    "$set": {
                        "status": "failed",
                        "error_message": error_message,
                        "last_error_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
        except Exception as e:
            logger.error(f"Error marking job as failed: {str(e)}")


# Global cron instance
_campaign_cron: Optional[CampaignCron] = None


async def start_campaign_cron():
    """Start the campaign cron service"""
    global _campaign_cron
    
    if _campaign_cron is None:
        _campaign_cron = CampaignCron()
    
    await _campaign_cron.start()


async def stop_campaign_cron():
    """Stop the campaign cron service"""
    global _campaign_cron
    
    if _campaign_cron:
        await _campaign_cron.stop()