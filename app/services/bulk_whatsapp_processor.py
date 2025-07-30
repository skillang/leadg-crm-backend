# app/services/bulk_whatsapp_processor.py
# 🆕 NEW FILE - Background processor for bulk WhatsApp jobs

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
from bson import ObjectId
import logging
from fastapi import HTTPException

from app.config.database import get_database
from app.models.bulk_whatsapp import BulkJobStatus, MessageType, RecipientStatus
from app.services.whatsapp_message_service import WhatsAppMessageService
from app.utils.timezone_helper import TimezoneHandler

logger = logging.getLogger(__name__)

class BulkWhatsAppProcessor:
    def __init__(self):
        self.collection_name = "bulk_whatsapp_jobs"
        self.active_jobs = {}
        # Remove self.whatsapp_service = WhatsAppMessageService() - use lazy loading

    @property
    def db(self):
        """Get database connection when needed (lazy initialization like email service)"""
        return get_database()
    
    @property
    def whatsapp_service(self):
        """Get WhatsApp service when needed (lazy initialization)"""
        return WhatsAppMessageService() 
    
    async def process_bulk_job(self, job_id: str) -> None:
        """
        Main processing method for bulk job - SAME PATTERN as your email scheduler
        
        Args:
            job_id: Job identifier to process
        """
        try:
            logger.info(f"🚀 Starting bulk WhatsApp job processing: {job_id}")
            
            # 1. Get job details (same as email)
            job = await self.db[self.collection_name].find_one({"job_id": job_id})
            if not job:
                logger.error(f"Job not found: {job_id}")
                return
            
            # 2. Check if job is already processing or completed
            current_status = job.get("status")
            if current_status != BulkJobStatus.PENDING:
                logger.warning(f"Job {job_id} already processed or processing. Status: {current_status}")
                return
            
            # 3. Mark job as processing (same as email)
            await self._update_job_status(job_id, BulkJobStatus.PROCESSING, started_at=datetime.utcnow())
            
            # 4. Track active job (same as your email activeJobs)
            self.active_jobs[job_id] = {
                "started_at": datetime.utcnow(),
                "status": "processing"
            }
            
            # 5. Process recipients in batches (SAME LOOP as your email)
            await self._process_recipients_in_batches(job)
            
            # 6. Mark job as completed
            await self._finalize_job(job_id)
            
            logger.info(f"✅ Bulk WhatsApp job completed: {job_id}")
            
        except Exception as e:
            logger.error(f"❌ Error processing bulk job {job_id}: {str(e)}")
            await self._mark_job_failed(job_id, str(e))
        finally:
            # 7. Remove from active jobs (same as email)
            self.active_jobs.pop(job_id, None)
    
    async def _process_recipients_in_batches(self, job: Dict[str, Any]) -> None:
        """
        Process recipients in batches with delays - SAME LOGIC as your email processor
        
        Args:
            job: Job document from database
        """
        job_id = job["job_id"]
        recipients = job.get("recipients", [])
        batch_size = job.get("batch_size", 10)
        delay_between_messages = job.get("delay_between_messages", 2)
        
        logger.info(f"Processing {len(recipients)} recipients in batches of {batch_size}")
        
        success_count = 0
        failed_count = 0
        skipped_count = 0
        results = []
        
        # Process recipients one by one (SAME PATTERN as email)
        for i, recipient in enumerate(recipients):
            try:
                # Check if job was cancelled
                current_job = await self.db[self.collection_name].find_one({"job_id": job_id})
                if current_job.get("status") == BulkJobStatus.CANCELLED:
                    logger.info(f"Job {job_id} was cancelled, stopping processing")
                    break
                
                # Skip if already processed
                if recipient.get("status") != RecipientStatus.PENDING:
                    skipped_count += 1
                    continue
                
                # Send message (SAME TRY-CATCH pattern as email)
                result = await self._send_single_message(job, recipient)
                
                if result["success"]:
                    success_count += 1
                    recipient_result = {
                        "lead_id": recipient["lead_id"],
                        "phone_number": recipient["phone_number"],
                        "status": RecipientStatus.SENT,
                        "sent_at": datetime.utcnow(),
                        "message_id": result.get("message_id")
                    }
                else:
                    failed_count += 1
                    recipient_result = {
                        "lead_id": recipient["lead_id"],
                        "phone_number": recipient["phone_number"],
                        "status": RecipientStatus.FAILED,
                        "failed_at": datetime.utcnow(),
                        "error_message": result.get("error", "Unknown error")
                    }
                
                results.append(recipient_result)
                
                # Update progress in database (SAME as email progress updates)
                await self._update_job_progress(
                    job_id, 
                    processed_count=i + 1,
                    success_count=success_count,
                    failed_count=failed_count,
                    skipped_count=skipped_count
                )
                
                # Log individual message activity (SAME as email logging)
                await self._log_message_activity(job, recipient, result["success"])
                
                # Delay between messages (SAME as email delay)
                if i < len(recipients) - 1:  # Don't delay after last message
                    logger.debug(f"Waiting {delay_between_messages} seconds before next message")
                    await asyncio.sleep(delay_between_messages)
                
            except Exception as e:
                logger.error(f"Error processing recipient {recipient.get('phone_number')}: {str(e)}")
                failed_count += 1
                
                results.append({
                    "lead_id": recipient["lead_id"],
                    "phone_number": recipient["phone_number"],
                    "status": RecipientStatus.FAILED,
                    "failed_at": datetime.utcnow(),
                    "error_message": str(e)
                })
        
        # Update final results
        await self.db[self.collection_name].update_one(
            {"job_id": job_id},
            {"$set": {"results": results, "updated_at": datetime.utcnow()}}
        )
        
        logger.info(f"Batch processing completed. Success: {success_count}, Failed: {failed_count}, Skipped: {skipped_count}")
    
    async def _send_single_message(self, job: Dict[str, Any], recipient: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send single WhatsApp message - SAME PATTERN as your email individual sending
        
        Args:
            job: Job configuration
            recipient: Recipient details
            
        Returns:
            Result dictionary with success status
        """
        try:
            phone_number = recipient["phone_number"]
            lead_name = recipient.get("lead_name", "")
            
            logger.debug(f"Sending WhatsApp to {phone_number} for lead {recipient.get('lead_id')}")
            
            # Send based on message type (same structure as individual WhatsApp endpoints)
            if job["message_type"] == MessageType.TEMPLATE:
                # Send template message (using existing WhatsApp service)
                result = await self.whatsapp_service.send_template_message(
                    contact=phone_number,
                    template_name=job["template_name"],
                    lead_name=lead_name
                )
            
            elif job["message_type"] == MessageType.TEXT:
                # Send text message (using existing WhatsApp service)
                message_content = job["message_content"]
                # Personalize message with lead name
                personalized_message = message_content.replace("{lead_name}", lead_name)
                
                result = await self.whatsapp_service.send_text_message(
                    contact=phone_number,
                    message=personalized_message
                )
            
            else:
                raise ValueError(f"Unknown message type: {job['message_type']}")
            
            # Format result (SAME as email result format)
            if result and result.get("success"):
                return {
                    "success": True,
                    "message_id": result.get("message_id", f"bulk_{int(datetime.utcnow().timestamp())}"),
                    "data": result
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Failed to send message"),
                    "data": result
                }
            
        except Exception as e:
            logger.error(f"Error sending message to {recipient.get('phone_number')}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _update_job_status(
        self, 
        job_id: str, 
        status: str, 
        error_message: str = None,
        started_at: datetime = None,
        completed_at: datetime = None
    ) -> None:
        """
        Update job status - SAME as your email status updates
        
        Args:
            job_id: Job identifier
            status: New status
            error_message: Error message if failed
            started_at: Start time
            completed_at: Completion time
        """
        update_data = {
            "status": status,
            "updated_at": datetime.utcnow()
        }
        
        if error_message:
            update_data["error_message"] = error_message
        
        if started_at:
            update_data["started_at"] = started_at
        
        if completed_at:
            update_data["completed_at"] = completed_at
        
        await self.db[self.collection_name].update_one(
            {"job_id": job_id},
            {"$set": update_data}
        )
        
        logger.info(f"Updated job {job_id} status to: {status}")
    
    async def _update_job_progress(
        self, 
        job_id: str, 
        processed_count: int,
        success_count: int,
        failed_count: int,
        skipped_count: int
    ) -> None:
        """
        Update job progress counters - SAME as email progress tracking
        
        Args:
            job_id: Job identifier
            processed_count: Total processed
            success_count: Successful sends
            failed_count: Failed sends
            skipped_count: Skipped sends
        """
        await self.db[self.collection_name].update_one(
            {"job_id": job_id},
            {"$set": {
                "processed_count": processed_count,
                "success_count": success_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count,
                "updated_at": datetime.utcnow()
            }}
        )
    
    async def _finalize_job(self, job_id: str) -> None:
        """
        Finalize completed job - SAME as email finalization
        
        Args:
            job_id: Job identifier
        """
        # Get final job state
        job = await self.db[self.collection_name].find_one({"job_id": job_id})
        
        if not job:
            return
        
        # Determine final status based on results
        success_count = job.get("success_count", 0)
        failed_count = job.get("failed_count", 0)
        
        if success_count > 0:
            final_status = BulkJobStatus.COMPLETED
        else:
            final_status = BulkJobStatus.FAILED
        
        # Update final status
        await self._update_job_status(
            job_id, 
            final_status, 
            completed_at=datetime.utcnow()
        )
        
        # Log completion activity (SAME as email completion logging)
        await self._log_job_completion_activity(job, success_count > 0)
        
        logger.info(f"Job {job_id} finalized with status: {final_status}")
    
    async def _mark_job_failed(self, job_id: str, error_message: str) -> None:
        """
        Mark job as failed - SAME as email failure handling
        
        Args:
            job_id: Job identifier
            error_message: Error description
        """
        await self._update_job_status(
            job_id,
            BulkJobStatus.FAILED,
            error_message=error_message,
            completed_at=datetime.utcnow()
        )
        
        logger.error(f"Job {job_id} marked as failed: {error_message}")
    
    async def _log_message_activity(
        self, 
        job: Dict[str, Any], 
        recipient: Dict[str, Any], 
        success: bool
    ) -> None:
        """
        Log individual message activity - SAME as your email activity logging
        
        Args:
            job: Job configuration
            recipient: Recipient details
            success: Whether message was sent successfully
        """
        try:
            lead_id = recipient.get("lead_id")
            
            # Skip custom phone numbers (not in leads database)
            if not lead_id or lead_id.startswith("custom_"):
                return
            
            activity_type = "bulk_whatsapp_sent" if success else "bulk_whatsapp_failed"
            description = f"WhatsApp message {'sent' if success else 'failed'} via bulk job: {job['job_name']}"
            
            activity = {
                "_id": ObjectId(),
                "lead_id": lead_id,
                "activity_type": activity_type,
                "description": description,
                "metadata": {
                    "job_id": job["job_id"],
                    "job_name": job["job_name"],
                    "message_type": job["message_type"],
                    "template_name": job.get("template_name"),
                    "phone_number": recipient["phone_number"],
                    "bulk_campaign": True,
                    "success": success
                },
                "created_by": ObjectId(job["created_by"]) if job.get("created_by") else None,
                "created_by_name": job.get("created_by_name"),
                "created_at": datetime.utcnow()
            }
            
            await self.db.lead_activities.insert_one(activity)
            
        except Exception as e:
            logger.error(f"Error logging message activity: {e}")
    
    async def _log_job_completion_activity(self, job: Dict[str, Any], success: bool) -> None:
        """
        Log job completion activities - SAME as email completion logging
        
        Args:
            job: Job document
            success: Whether job completed successfully
        """
        try:
            activities = []
            recipients = job.get("recipients", [])
            
            # Create completion activity for each lead (SAME as email)
            for recipient in recipients:
                lead_id = recipient.get("lead_id")
                
                # Skip custom phone numbers
                if not lead_id or lead_id.startswith("custom_"):
                    continue
                
                activity_type = "bulk_whatsapp_completed" if success else "bulk_whatsapp_job_failed"
                description = f"Bulk WhatsApp job {'completed' if success else 'failed'}: {job['job_name']}"
                
                activity = {
                    "_id": ObjectId(),
                    "lead_id": lead_id,
                    "activity_type": activity_type,
                    "description": description,
                    "metadata": {
                        "job_id": job["job_id"],
                        "job_name": job["job_name"],
                        "total_recipients": job.get("total_recipients", 0),
                        "success_count": job.get("success_count", 0),
                        "failed_count": job.get("failed_count", 0),
                        "completion_success": success
                    },
                    "created_by": ObjectId(job["created_by"]) if job.get("created_by") else None,
                    "created_by_name": job.get("created_by_name"),
                    "created_at": datetime.utcnow()
                }
                activities.append(activity)
            
            # Insert all activities (SAME as email)
            if activities:
                await self.db.lead_activities.insert_many(activities)
                logger.info(f"Logged {len(activities)} job completion activities")
                
        except Exception as e:
            logger.error(f"Error logging job completion activities: {e}")
    
    async def get_active_jobs(self) -> Dict[str, Any]:
        """
        Get currently active jobs - SAME as your email active jobs tracking
        
        Returns:
            Dictionary of active jobs
        """
        return self.active_jobs.copy()
    
    async def stop_job(self, job_id: str) -> bool:
        """
        Stop/cancel active job - SAME as email job stopping
        
        Args:
            job_id: Job to stop
            
        Returns:
            True if stopped successfully
        """
        try:
            if job_id in self.active_jobs:
                # Mark as cancelled in database
                await self._update_job_status(
                    job_id, 
                    BulkJobStatus.CANCELLED,
                    completed_at=datetime.utcnow()
                )
                
                # Remove from active jobs
                self.active_jobs.pop(job_id, None)
                
                logger.info(f"Stopped active job: {job_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error stopping job {job_id}: {str(e)}")
            return False

# ================================
# PROCESSOR INSTANCE
# ================================

# Global processor instance (same pattern as your email scheduler)
_bulk_whatsapp_processor = None

def get_bulk_whatsapp_processor() -> BulkWhatsAppProcessor:
    """Get bulk WhatsApp processor instance with lazy initialization"""
    global _bulk_whatsapp_processor
    if _bulk_whatsapp_processor is None:
        _bulk_whatsapp_processor = BulkWhatsAppProcessor()
    return _bulk_whatsapp_processor

# Helper function for easy import
bulk_whatsapp_processor = get_bulk_whatsapp_processor