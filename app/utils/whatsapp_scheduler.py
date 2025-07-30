# app/utils/whatsapp_scheduler.py
# 🆕 NEW FILE - Scheduler for bulk WhatsApp jobs

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.executors.asyncio import AsyncIOExecutor
import logging
from bson import ObjectId

from app.config.database import get_database
from app.services.bulk_whatsapp_processor import get_bulk_whatsapp_processor
from app.utils.timezone_helper import TimezoneHandler
from app.models.bulk_whatsapp import BulkJobStatus

logger = logging.getLogger(__name__)

class WhatsAppJobScheduler:
    """
    Scheduler for bulk WhatsApp jobs - SAME PATTERN as your emailSchedulerService.js
    Handles scheduling and execution of WhatsApp bulk messaging jobs
    """
    
    def __init__(self):
        self.db = get_database()
        self.processor = get_bulk_whatsapp_processor()
        
        # Configure scheduler (Python equivalent of node-schedule)
        executors = {
            'default': AsyncIOExecutor()
        }
        
        self.scheduler = AsyncIOScheduler(
            executors=executors,
            timezone='UTC'  # Always work in UTC like your email system
        )
        
        # Track scheduled jobs (same as your activeJobs in email)
        self.scheduled_jobs = {}  # job_id -> scheduler_job mapping
        
        self.is_running = False
        
        logger.info("WhatsApp Job Scheduler initialized")
    
    async def start(self) -> None:
        """
        Start the scheduler - SAME pattern as your email scheduler startup
        """
        try:
            if not self.is_running:
                self.scheduler.start()
                self.is_running = True
                
                # Load existing scheduled jobs from database (same as email recovery)
                await self._load_pending_scheduled_jobs()
                
                logger.info("✅ WhatsApp Job Scheduler started successfully")
            else:
                logger.warning("Scheduler already running")
                
        except Exception as e:
            logger.error(f"❌ Error starting WhatsApp scheduler: {str(e)}")
            raise
    
    async def stop(self) -> None:
        """
        Stop the scheduler - SAME pattern as email scheduler shutdown
        """
        try:
            if self.is_running:
                self.scheduler.shutdown(wait=True)
                self.scheduled_jobs.clear()
                self.is_running = False
                
                logger.info("✅ WhatsApp Job Scheduler stopped successfully")
            else:
                logger.warning("Scheduler not running")
                
        except Exception as e:
            logger.error(f"❌ Error stopping WhatsApp scheduler: {str(e)}")
    
    async def schedule_whatsapp_job(self, job_id: str, scheduled_time_utc: datetime) -> bool:
        """
        Schedule a WhatsApp bulk job - SAME LOGIC as your email scheduleEmailJob()
        
        Args:
            job_id: Job identifier
            scheduled_time_utc: When to execute (already in UTC from timezone helper)
            
        Returns:
            True if scheduled successfully
        """
        try:
            logger.info(f"🕒 Scheduling WhatsApp job {job_id} for {scheduled_time_utc} UTC")
            
            # Cancel existing job if it exists (same as your email cancellation)
            if job_id in self.scheduled_jobs:
                self.scheduler.remove_job(self.scheduled_jobs[job_id].id)
                logger.info(f"Cancelled existing scheduled job: {job_id}")
            
            # Create new scheduled job (same pattern as email)
            scheduler_job = self.scheduler.add_job(
                func=self._execute_scheduled_job,
                trigger=DateTrigger(run_date=scheduled_time_utc),
                args=[job_id],
                id=f"whatsapp_bulk_{job_id}",
                name=f"WhatsApp Bulk Job {job_id}",
                replace_existing=True
            )
            
            # Track the job (same as your activeJobs)
            self.scheduled_jobs[job_id] = scheduler_job
            
            logger.info(f"✅ WhatsApp job {job_id} scheduled successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error scheduling WhatsApp job {job_id}: {str(e)}")
            return False
    
    async def cancel_scheduled_job(self, job_id: str) -> bool:
        """
        Cancel a scheduled job - SAME as your email job cancellation
        
        Args:
            job_id: Job to cancel
            
        Returns:
            True if cancelled successfully
        """
        try:
            if job_id in self.scheduled_jobs:
                # Remove from scheduler
                self.scheduler.remove_job(self.scheduled_jobs[job_id].id)
                
                # Remove from tracking
                del self.scheduled_jobs[job_id]
                
                logger.info(f"✅ Cancelled scheduled WhatsApp job: {job_id}")
                return True
            else:
                logger.warning(f"Scheduled job not found: {job_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error cancelling scheduled job {job_id}: {str(e)}")
            return False
    
    async def _execute_scheduled_job(self, job_id: str) -> None:
        """
        Execute scheduled job - SAME PATTERN as your email job execution
        
        Args:
            job_id: Job to execute
        """
        try:
            logger.info(f"🕒 Executing scheduled WhatsApp job {job_id} at {datetime.utcnow()}")
            
            # Get job details from database (same as email)
            job = await self.db.bulk_whatsapp_jobs.find_one({"job_id": job_id})
            
            if not job:
                logger.error(f"Scheduled job not found in database: {job_id}")
                return
            
            # Check if job is still pending (same validation as email)
            if job.get("status") != BulkJobStatus.PENDING:
                logger.warning(f"Job {job_id} is not in pending status: {job.get('status')}")
                return
            
            # Update job status to indicate execution started
            await self.db.bulk_whatsapp_jobs.update_one(
                {"job_id": job_id},
                {"$set": {
                    "status": BulkJobStatus.PROCESSING,
                    "started_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }}
            )
            
            # Process the job (same as email processing)
            await self.processor.process_bulk_job(job_id)
            
            logger.info(f"✅ Scheduled WhatsApp job {job_id} execution completed")
            
        except Exception as e:
            logger.error(f"❌ Error executing scheduled job {job_id}: {str(e)}")
            
            # Mark job as failed (same as email error handling)
            try:
                await self.db.bulk_whatsapp_jobs.update_one(
                    {"job_id": job_id},
                    {"$set": {
                        "status": BulkJobStatus.FAILED,
                        "error_message": f"Scheduled execution failed: {str(e)}",
                        "completed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }}
                )
            except Exception as update_error:
                logger.error(f"Failed to update job status after error: {update_error}")
        
        finally:
            # Remove from scheduled jobs tracking (same as email cleanup)
            self.scheduled_jobs.pop(job_id, None)
    
    async def _load_pending_scheduled_jobs(self) -> None:
        """
        Load and reschedule pending jobs on startup - SAME as email recovery logic
        This handles the case where the server was restarted with pending scheduled jobs
        """
        try:
            logger.info("🔄 Loading pending scheduled WhatsApp jobs from database")
            
            # Find pending scheduled jobs (same query as email)
            query = {
                "status": BulkJobStatus.PENDING,
                "is_scheduled": True,
                "scheduled_time": {"$exists": True, "$ne": None}
            }
            
            pending_jobs = await self.db.bulk_whatsapp_jobs.find(query).to_list(length=None)
            
            current_utc = datetime.utcnow()
            rescheduled_count = 0
            overdue_count = 0
            
            for job in pending_jobs:
                job_id = job["job_id"]
                scheduled_time_utc = job["scheduled_time"]
                
                if scheduled_time_utc <= current_utc:
                    # Job is overdue - execute immediately (same as email overdue handling)
                    logger.warning(f"Overdue job found: {job_id}, executing immediately")
                    
                    # Execute in background
                    asyncio.create_task(self.processor.process_bulk_job(job_id))
                    overdue_count += 1
                    
                else:
                    # Job is still in future - reschedule it (same as email rescheduling)
                    success = await self.schedule_whatsapp_job(job_id, scheduled_time_utc)
                    if success:
                        rescheduled_count += 1
                        logger.info(f"Rescheduled job: {job_id} for {scheduled_time_utc}")
            
            logger.info(f"✅ Loaded {len(pending_jobs)} pending jobs: {rescheduled_count} rescheduled, {overdue_count} executed immediately")
            
        except Exception as e:
            logger.error(f"❌ Error loading pending scheduled jobs: {str(e)}")
    
    async def get_scheduled_jobs_status(self) -> Dict[str, Any]:
        """
        Get status of scheduled jobs - SAME as your email scheduler status
        
        Returns:
            Status information about scheduled jobs
        """
        try:
            current_utc = datetime.utcnow()
            
            # Count scheduled jobs in database
            pending_scheduled = await self.db.bulk_whatsapp_jobs.count_documents({
                "status": BulkJobStatus.PENDING,
                "is_scheduled": True,
                "scheduled_time": {"$gt": current_utc}
            })
            
            # Count overdue jobs
            overdue_scheduled = await self.db.bulk_whatsapp_jobs.count_documents({
                "status": BulkJobStatus.PENDING,
                "is_scheduled": True,
                "scheduled_time": {"$lte": current_utc}
            })
            
            # Get next job to execute
            next_job_cursor = self.db.bulk_whatsapp_jobs.find({
                "status": BulkJobStatus.PENDING,
                "is_scheduled": True,
                "scheduled_time": {"$gt": current_utc}
            }).sort("scheduled_time", 1).limit(1)
            
            next_jobs = await next_job_cursor.to_list(1)
            next_job_time = None
            next_job_info = None
            
            if next_jobs:
                next_job = next_jobs[0]
                next_job_time = next_job["scheduled_time"]
                
                # Convert to IST for display (same as email timezone conversion)
                next_job_time_ist = TimezoneHandler.utc_to_ist(next_job_time)
                
                next_job_info = {
                    "job_id": next_job["job_id"],
                    "job_name": next_job["job_name"],
                    "scheduled_time_utc": next_job_time,
                    "scheduled_time_ist": next_job_time_ist,
                    "scheduled_time_ist_display": next_job_time_ist.strftime('%Y-%m-%d %H:%M:%S IST'),
                    "total_recipients": next_job["total_recipients"]
                }
            
            return {
                "scheduler_running": self.is_running,
                "active_scheduled_jobs": len(self.scheduled_jobs),
                "pending_scheduled_jobs": pending_scheduled,
                "overdue_scheduled_jobs": overdue_scheduled,
                "next_job": next_job_info,
                "current_time_utc": current_utc,
                "current_time_ist": TimezoneHandler.utc_to_ist(current_utc)
            }
            
        except Exception as e:
            logger.error(f"Error getting scheduled jobs status: {str(e)}")
            return {
                "scheduler_running": self.is_running,
                "error": str(e)
            }
    
    async def reschedule_job(self, job_id: str, new_scheduled_time_utc: datetime) -> bool:
        """
        Reschedule an existing job - SAME as email rescheduling
        
        Args:
            job_id: Job to reschedule
            new_scheduled_time_utc: New execution time in UTC
            
        Returns:
            True if rescheduled successfully
        """
        try:
            # Update database first
            result = await self.db.bulk_whatsapp_jobs.update_one(
                {"job_id": job_id, "status": BulkJobStatus.PENDING},
                {"$set": {
                    "scheduled_time": new_scheduled_time_utc,
                    "updated_at": datetime.utcnow()
                }}
            )
            
            if result.matched_count == 0:
                logger.error(f"Job not found or not in pending status: {job_id}")
                return False
            
            # Reschedule in scheduler
            success = await self.schedule_whatsapp_job(job_id, new_scheduled_time_utc)
            
            if success:
                logger.info(f"✅ Job {job_id} rescheduled for {new_scheduled_time_utc}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error rescheduling job {job_id}: {str(e)}")
            return False
    
    async def cleanup_old_jobs(self, days_old: int = 30) -> int:
        """
        Cleanup old completed/failed jobs - SAME as email cleanup
        
        Args:
            days_old: Remove jobs older than this many days
            
        Returns:
            Number of jobs cleaned up
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            # Delete old completed/failed jobs
            result = await self.db.bulk_whatsapp_jobs.delete_many({
                "status": {"$in": [BulkJobStatus.COMPLETED, BulkJobStatus.FAILED]},
                "completed_at": {"$lt": cutoff_date}
            })
            
            cleaned_count = result.deleted_count
            logger.info(f"✅ Cleaned up {cleaned_count} old WhatsApp jobs (older than {days_old} days)")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"❌ Error cleaning up old jobs: {str(e)}")
            return 0

# ================================
# GLOBAL SCHEDULER INSTANCE
# ================================

# Global scheduler instance (same pattern as your email scheduler)
_whatsapp_scheduler = None

def get_whatsapp_scheduler() -> WhatsAppJobScheduler:
    """Get WhatsApp job scheduler instance with lazy initialization"""
    global _whatsapp_scheduler
    if _whatsapp_scheduler is None:
        _whatsapp_scheduler = WhatsAppJobScheduler()
    return _whatsapp_scheduler

# Helper function for easy import
whatsapp_scheduler = get_whatsapp_scheduler

# ================================
# STARTUP AND SHUTDOWN HANDLERS
# ================================

async def start_whatsapp_scheduler():
    """
    Start the WhatsApp scheduler - Call this on app startup
    SAME pattern as your email scheduler startup
    """
    try:
        scheduler = get_whatsapp_scheduler()
        await scheduler.start()
        logger.info("🚀 WhatsApp Job Scheduler service started")
    except Exception as e:
        logger.error(f"❌ Failed to start WhatsApp scheduler: {str(e)}")
        raise

async def stop_whatsapp_scheduler():
    """
    Stop the WhatsApp scheduler - Call this on app shutdown
    SAME pattern as your email scheduler shutdown
    """
    try:
        scheduler = get_whatsapp_scheduler()
        await scheduler.stop()
        logger.info("🛑 WhatsApp Job Scheduler service stopped")
    except Exception as e:
        logger.error(f"❌ Failed to stop WhatsApp scheduler: {str(e)}")

# ================================
# USAGE EXAMPLES (for documentation)
# ================================

"""
Usage Examples:

1. Schedule a job (from bulk service):
   scheduler = get_whatsapp_scheduler()
   await scheduler.schedule_whatsapp_job(job_id, scheduled_time_utc)

2. Cancel a scheduled job:
   await scheduler.cancel_scheduled_job(job_id)

3. Get scheduler status:
   status = await scheduler.get_scheduled_jobs_status()

4. App startup (in main.py):
   await start_whatsapp_scheduler()

5. App shutdown (in main.py):
   await stop_whatsapp_scheduler()
"""