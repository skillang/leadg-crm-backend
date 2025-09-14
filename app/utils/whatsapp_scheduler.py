# app/utils/whatsapp_scheduler.py
# Scheduler for bulk WhatsApp jobs with Facebook Token Auto-Refresh - TIMEZONE FIXED

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.executors.asyncio import AsyncIOExecutor
import logging
from bson import ObjectId
import pytz

from app.config.database import get_database
from app.services.bulk_whatsapp_processor import get_bulk_whatsapp_processor
from app.utils.timezone_helper import TimezoneHandler
from app.models.bulk_whatsapp import BulkJobStatus
from app.services.facebook_leads_service import facebook_leads_service  # ADD: Facebook service import

logger = logging.getLogger(__name__)

class WhatsAppJobScheduler:
    """
    Scheduler for bulk WhatsApp jobs with Facebook Token Auto-Refresh
    Handles scheduling and execution of WhatsApp bulk messaging jobs
    FIXED: Proper timezone handling
    """
    
    def __init__(self):
        self.db = get_database()
        self.processor = get_bulk_whatsapp_processor()
        
        # Configure scheduler (Python equivalent of node-schedule)
        executors = {
            'default': AsyncIOExecutor()
        }
        
        # FIX: Use pytz.UTC explicitly instead of string
        self.scheduler = AsyncIOScheduler(
            executors=executors,
            timezone=pytz.UTC  # FIXED: Explicit UTC timezone
        )
        
        # Track scheduled jobs (same as your activeJobs in email)
        self.scheduled_jobs = {}  # job_id -> scheduler_job mapping
        
        self.is_running = False
        
        logger.info("WhatsApp Job Scheduler initialized with UTC timezone")
    
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
    
    # NEW: Facebook Token Auto-Refresh Methods
    async def check_facebook_token(self):
        """Check and refresh Facebook token - runs every 7 days"""
        try:
            logger.info("🔄 Checking Facebook access token...")
            result = await facebook_leads_service.auto_refresh_token_if_needed()
            
            if result.get("success"):
                if result.get("refreshed"):
                    logger.info("✅ Facebook token refreshed successfully!")
                elif result.get("valid"):
                    logger.info(f"✅ Facebook token valid for {result.get('days_left', 'unknown')} more days")
                else:
                    logger.info("✅ Facebook token check completed")
            else:
                logger.error(f"❌ Facebook token issue: {result.get('error')}")
                
            return result
            
        except Exception as e:
            logger.error(f"❌ Facebook token check failed: {str(e)}")
            return {"success": False, "error": str(e)}

    async def start_facebook_token_scheduler(self):
        """Start Facebook token check - every 7 days"""
        try:
            self.scheduler.add_job(
                func=self.check_facebook_token,
                trigger='interval',
                days=7,
                id='facebook_token_check',
                name='Facebook Token Check',
                replace_existing=True
            )
            
            logger.info("✅ Facebook token scheduler started (runs every 7 days)")
            
            # Run immediate check
            await self.check_facebook_token()
            
        except Exception as e:
            logger.error(f"❌ Facebook scheduler setup failed: {str(e)}")
    
    async def schedule_whatsapp_job(self, job_id: str, scheduled_time_utc: datetime) -> bool:
        """
        Schedule a WhatsApp bulk job - SAME LOGIC as your email scheduleEmailJob()
        FIXED: Proper timezone handling
        
        Args:
            job_id: Job identifier
            scheduled_time_utc: When to execute (already in UTC from timezone helper)
            
        Returns:
            True if scheduled successfully
        """
        try:
            # FIX: Ensure the datetime is timezone-aware UTC
            if scheduled_time_utc.tzinfo is None:
                # If naive datetime, assume it's UTC
                scheduled_time_utc = pytz.UTC.localize(scheduled_time_utc)
            elif scheduled_time_utc.tzinfo != pytz.UTC:
                # If different timezone, convert to UTC
                scheduled_time_utc = scheduled_time_utc.astimezone(pytz.UTC)
            
            # DEBUG: Log current time and scheduled time for debugging
            current_utc = datetime.now(pytz.UTC)
            logger.info(f"🕒 Scheduling WhatsApp job {job_id}")
            logger.info(f"🕐 Current UTC time: {current_utc}")
            logger.info(f"🕑 Scheduled UTC time: {scheduled_time_utc}")
            logger.info(f"⏱️ Time difference: {(scheduled_time_utc - current_utc).total_seconds()} seconds")
            
            # VALIDATION: Check if time is in the future
            if scheduled_time_utc <= current_utc:
                logger.error(f"❌ Cannot schedule job for past time: {scheduled_time_utc} <= {current_utc}")
                return False
            
            # Cancel existing job if it exists (same as your email cancellation)
            if job_id in self.scheduled_jobs:
                self.scheduler.remove_job(self.scheduled_jobs[job_id].id)
                logger.info(f"Cancelled existing scheduled job: {job_id}")
            
            # Create new scheduled job (same pattern as email)
            scheduler_job = self.scheduler.add_job(
                func=self._execute_scheduled_job,
                trigger=DateTrigger(run_date=scheduled_time_utc),  # Now timezone-aware
                args=[job_id],
                id=f"whatsapp_bulk_{job_id}",
                name=f"WhatsApp Bulk Job {job_id}",
                replace_existing=True
            )
            
            # Track the job (same as your activeJobs)
            self.scheduled_jobs[job_id] = scheduler_job
            
            logger.info(f"✅ WhatsApp job {job_id} scheduled successfully for {scheduled_time_utc}")
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
            current_utc = datetime.now(pytz.UTC)
            logger.info(f"🕒 Executing scheduled WhatsApp job {job_id} at {current_utc}")
            
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
                    "started_at": current_utc.replace(tzinfo=None),  # Store as naive UTC in DB
                    "updated_at": current_utc.replace(tzinfo=None)
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
            
            # FIX: Use timezone-aware current time
            current_utc = datetime.now(pytz.UTC)
            rescheduled_count = 0
            overdue_count = 0
            
            for job in pending_jobs:
                job_id = job["job_id"]
                scheduled_time_naive = job["scheduled_time"]  # This is naive UTC from DB
                
                # FIX: Convert naive datetime to timezone-aware UTC
                if scheduled_time_naive.tzinfo is None:
                    scheduled_time_utc = pytz.UTC.localize(scheduled_time_naive)
                else:
                    scheduled_time_utc = scheduled_time_naive.astimezone(pytz.UTC)
                
                logger.info(f"🔍 Job {job_id}: scheduled for {scheduled_time_utc}, current time {current_utc}")
                
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
        FIXED: Proper timezone handling
        
        Returns:
            Status information about scheduled jobs
        """
        try:
            # FIX: Use timezone-aware current time
            current_utc = datetime.now(pytz.UTC).replace(tzinfo=None)  # Convert to naive for DB comparison
            
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
        FIXED: Proper timezone handling
        
        Args:
            job_id: Job to reschedule
            new_scheduled_time_utc: New execution time in UTC
            
        Returns:
            True if rescheduled successfully
        """
        try:
            # FIX: Ensure datetime is naive for database storage
            if new_scheduled_time_utc.tzinfo is not None:
                new_scheduled_time_utc = new_scheduled_time_utc.replace(tzinfo=None)
            
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
            
            # Reschedule in scheduler (convert back to timezone-aware)
            scheduled_time_aware = pytz.UTC.localize(new_scheduled_time_utc)
            success = await self.schedule_whatsapp_job(job_id, scheduled_time_aware)
            
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
# STARTUP AND SHUTDOWN HANDLERS - ENHANCED WITH FACEBOOK TOKEN
# ================================

async def start_whatsapp_scheduler():
    """
    Start the WhatsApp and Facebook token schedulers - Call this on app startup
    ENHANCED with better error handling and Facebook token auto-refresh
    """
    try:
        logger.info("🚀 Initializing WhatsApp Job Scheduler...")
        
        scheduler = get_whatsapp_scheduler()
        
        # Force start the scheduler if not already running
        if not scheduler.is_running:
            logger.info("📱 Starting APScheduler for WhatsApp jobs...")
            await scheduler.start()
            
            # Start Facebook token scheduler
            await scheduler.start_facebook_token_scheduler()
            
            logger.info("✅ WhatsApp and Facebook schedulers started successfully")
        else:
            logger.warning("⚠️ WhatsApp scheduler already running")
            
        # Verify scheduler is actually running
        if scheduler.scheduler.running:
            logger.info(f"✅ APScheduler confirmed running with timezone: {scheduler.scheduler.timezone}")
        else:
            logger.error("❌ APScheduler failed to start")
            raise Exception("APScheduler is not running")
            
    except Exception as e:
        logger.error(f"❌ Failed to start WhatsApp scheduler: {str(e)}")
        logger.error(f"❌ Error type: {type(e).__name__}")
        # Don't re-raise - let app continue without scheduler
        logger.warning("⚠️ WhatsApp scheduler disabled - scheduled jobs will not work")

async def stop_whatsapp_scheduler():
    """
    Stop the WhatsApp scheduler - Call this on app shutdown
    ENHANCED with better error handling
    """
    try:
        logger.info("🛑 Stopping WhatsApp Job Scheduler...")
        
        scheduler = get_whatsapp_scheduler()
        
        if scheduler.is_running:
            await scheduler.stop()
            logger.info("✅ WhatsApp Job Scheduler service stopped")
        else:
            logger.warning("⚠️ WhatsApp scheduler was not running")
            
    except Exception as e:
        logger.error(f"❌ Failed to stop WhatsApp scheduler: {str(e)}")

# ENHANCED: Test function to verify scheduler works
async def test_whatsapp_scheduler():
    """
    Test function to verify scheduler is working with proper timezone handling
    """
    try:
        scheduler = get_whatsapp_scheduler()
        
        # Test scheduling a job 10 seconds in the future
        current_utc = datetime.now(pytz.UTC)
        test_time = current_utc + timedelta(seconds=10)
        
        logger.info(f"🧪 Testing scheduler with job at {test_time}")
        logger.info(f"🕐 Current time: {current_utc}")
        logger.info(f"🕑 Test time: {test_time}")
        
        # Create a test job
        success = await scheduler.schedule_whatsapp_job("test_job_123", test_time)
        
        if success:
            logger.info("✅ Test job scheduled successfully")
            
            # Cancel the test job immediately
            cancelled = await scheduler.cancel_scheduled_job("test_job_123")
            if cancelled:
                logger.info("✅ Test job cancelled successfully")
            else:
                logger.warning("⚠️ Test job cancellation failed")
                
            return True
        else:
            logger.error("❌ Test job scheduling failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Scheduler test failed: {str(e)}")
        return False

# ================================
# USAGE EXAMPLES (for documentation)
# ================================

"""
Usage Examples:

1. Schedule a WhatsApp job (from bulk service):
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

6. Facebook Token Auto-Refresh:
   - Automatically checks Facebook token every 7 days
   - Refreshes token when it has 10 days or less remaining
   - Extends token for another 60 days each refresh

TIMEZONE FIXES:
- Uses pytz.UTC explicitly instead of string
- Ensures all datetime objects are timezone-aware during scheduling
- Proper timezone validation and debugging logs
- Prevents scheduling jobs in the past
"""