# app/services/campaign_executor.py
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from bson import ObjectId
import logging
from app.decorators.timezone_decorator import ist_time_to_utc_datetime

from app.config.database import get_database
from app.models.campaign_tracking import (
    CampaignEnrollment,
    CampaignJob,
    TrackingStatus,
    JobType
)
from app.services.campaign_service import campaign_service

logger = logging.getLogger(__name__)


class CampaignExecutor:
    """Service for executing campaigns - enrollment and job creation"""
    
    def __init__(self):
        self.enrollment_collection = "campaign_tracking"
        self.jobs_collection = "campaign_tracking"  # Same collection, different job_type
    
    @property
    def db(self):
        """Get database connection"""
        return get_database()
    
    async def enroll_leads_in_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """
        Find matching leads and enroll them in campaign
        
        Args:
            campaign_id: Campaign ID
            
        Returns:
            Dictionary with enrollment results
        """
        try:
            logger.info(f"Starting enrollment for campaign: {campaign_id}")
            
            # Get campaign details
            campaign = await campaign_service.get_campaign(campaign_id)
            if not campaign:
                return {
                    "success": False,
                    "message": "Campaign not found"
                }
            
            if campaign["status"] != "active":
                return {
                    "success": False,
                    "message": f"Campaign is {campaign['status']}, not active"
                }
            
            # Find matching leads
            matching_leads = await self._find_matching_leads(campaign)
            
            if not matching_leads:
                logger.info(f"No matching leads found for campaign {campaign_id}")
                return {
                    "success": True,
                    "message": "No matching leads found",
                    "enrolled_count": 0
                }
            
            logger.info(f"Found {len(matching_leads)} matching leads for campaign {campaign_id}")
            
            # Enroll each lead
            enrolled_count = 0
            for lead in matching_leads:
                success = await self._enroll_single_lead(campaign, lead)
                if success:
                    enrolled_count += 1
            
            logger.info(f"Enrolled {enrolled_count} leads in campaign {campaign_id}")
            
            return {
                "success": True,
                "message": f"Enrolled {enrolled_count} leads",
                "enrolled_count": enrolled_count,
                "total_matching": len(matching_leads)
            }
            
        except Exception as e:
            logger.error(f"Error enrolling leads in campaign {campaign_id}: {str(e)}")
            return {
                "success": False,
                "message": f"Enrollment failed: {str(e)}",
                "enrolled_count": 0
            }
    
    async def _find_matching_leads(self, campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Find leads that match campaign criteria
        
        Args:
            campaign: Campaign document
            
        Returns:
            List of matching lead documents
        """
        try:
            query = {}
            
            if campaign["send_to_all"]:
                # Send to all leads
                logger.info("Campaign set to send_to_all")
            else:
                # Build filter query
                filters = []
                
                if campaign.get("stage_ids"):
                    # Convert stage ObjectIds to stage names
                    stage_names = await self._convert_stage_ids_to_names(campaign["stage_ids"])
                    filters.append({"stage": {"$in": stage_names}})

                if campaign.get("source_ids"):
                    # Convert source ObjectIds to source names
                    source_names = await self._convert_source_ids_to_names(campaign["source_ids"])
                    filters.append({"source": {"$in": source_names}})
                
                if filters:
                    query["$and"] = filters
            
            # Ensure lead has contact info based on campaign type
            if campaign["campaign_type"] == "whatsapp":
                query["$or"] = [
                    {"contact_number": {"$exists": True, "$ne": "", "$ne": None}},
                    {"phone_number": {"$exists": True, "$ne": "", "$ne": None}}
                ]
            elif campaign["campaign_type"] == "email":
                query["email"] = {"$exists": True, "$ne": "", "$ne": None}
            
            # Exclude already enrolled leads
            already_enrolled = await self.db[self.enrollment_collection].find(
                {
                    "campaign_id": campaign["campaign_id"],
                    "job_type": "enrollment"
                },
                {"lead_id": 1}
            ).to_list(None)
            
            enrolled_lead_ids = [doc["lead_id"] for doc in already_enrolled]
            if enrolled_lead_ids:
                query["lead_id"] = {"$nin": enrolled_lead_ids}
            
            logger.info(f"Lead query: {query}")
            
            # Find matching leads
            leads = await self.db.leads.find(query).to_list(None)
            
            return leads
            
        except Exception as e:
            logger.error(f"Error finding matching leads: {str(e)}")
            return []
        
    async def _convert_stage_ids_to_names(self, stage_ids: List[str]) -> List[str]:
        """Convert stage ObjectIds to stage names"""
        try:
            stage_object_ids = [ObjectId(sid) for sid in stage_ids]
            stages = await self.db.lead_stages.find(
                {"_id": {"$in": stage_object_ids}}
            ).to_list(None)
            return [stage["name"] for stage in stages]
        except Exception as e:
            logger.error(f"Error converting stage IDs to names: {str(e)}")
            return []

    async def _convert_source_ids_to_names(self, source_ids: List[str]) -> List[str]:
        """Convert source ObjectIds to source names"""
        try:
            logger.info(f"Converting source IDs: {source_ids}")  # ADD THIS
            source_object_ids = [ObjectId(sid) for sid in source_ids]
            logger.info(f"ObjectIds created: {source_object_ids}")  # ADD THIS
            
            sources = await self.db.sources.find(
                {"_id": {"$in": source_object_ids}}
            ).to_list(None)
            
            logger.info(f"Found sources: {sources}")  # ADD THIS
            result = [source["name"] for source in sources]
            logger.info(f"Converted to names: {result}")  # ADD THIS
            return result
        except Exception as e:
            logger.error(f"Error converting source IDs to names: {str(e)}")
            return []
    
    async def _enroll_single_lead(
        self,
        campaign: Dict[str, Any],
        lead: Dict[str, Any]
    ) -> bool:
        """
        Enroll a single lead and create all message jobs
        
        Args:
            campaign: Campaign document
            lead: Lead document
            
        Returns:
            True if successful
        """
        try:
            campaign_id = campaign["campaign_id"]
            lead_id = lead["lead_id"]
            
            # Create enrollment record
            enrollment_doc = {
                "campaign_id": campaign_id,
                "lead_id": lead_id,
                "job_type": "enrollment",
                
                "enrolled_at": datetime.utcnow(),
                "enrolled_with_stage": lead.get("stage"),
                "enrolled_with_source": lead.get("source"),
                
                "messages_sent": 0,
                "current_sequence": 0,
                "status": TrackingStatus.ACTIVE.value,
                
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            await self.db[self.enrollment_collection].insert_one(enrollment_doc)
            
            # Create message jobs
            await self._create_message_jobs(campaign, lead, enrollment_doc)
            
            logger.debug(f"Lead {lead_id} enrolled in campaign {campaign_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error enrolling lead {lead.get('lead_id')}: {str(e)}")
            return False
    
    async def _create_message_jobs(
        self,
        campaign: Dict[str, Any],
        lead: Dict[str, Any],
        enrollment: Dict[str, Any]
    ) -> None:
        """
        Create all message jobs for a lead
        
        Args:
            campaign: Campaign document
            lead: Lead document
            enrollment: Enrollment document
        """
        try:
            campaign_id = campaign["campaign_id"]
            lead_id = lead["lead_id"]
            enrollment_time = enrollment["enrolled_at"]
            
            jobs = []
            
            for template in campaign["templates"]:
                # Calculate execute_at time
                if campaign["use_custom_dates"]:
                    # Use specific date
                    send_date = datetime.strptime(template["custom_date"], "%Y-%m-%d")
                    # Convert IST time to UTC
                    execute_at = ist_time_to_utc_datetime(send_date, campaign["send_time"])
                else:
                    # Calculate based on scheduled_day
                    days_to_add = template["scheduled_day"]
                    target_date = enrollment_time + timedelta(days=days_to_add)
                    # Convert IST time to UTC
                    execute_at = ist_time_to_utc_datetime(target_date, campaign["send_time"])
                            
                # Create job document
                job_doc = {
                    "campaign_id": campaign_id,
                    "lead_id": lead_id,
                    "job_type": "message_job",
                    
                    "channel": campaign["campaign_type"],
                    "template_id": template["template_id"],
                    "template_name": template["template_name"],
                    "sequence_order": template["sequence_order"],
                    
                    "execute_at": execute_at,
                    "status": TrackingStatus.PENDING.value,
                    
                    "attempts": 0,
                    "max_attempts": 3,
                    "error_message": None,
                    
                    "created_at": datetime.utcnow()
                }
                
                jobs.append(job_doc)
            
            # Insert all jobs
            if jobs:
                await self.db[self.jobs_collection].insert_many(jobs)
                logger.debug(f"Created {len(jobs)} jobs for lead {lead_id}")
            
        except Exception as e:
            logger.error(f"Error creating message jobs: {str(e)}")
    
    async def check_lead_criteria_change(
        self,
        lead_id: str,
        new_stage: Optional[str] = None,
        new_source: Optional[str] = None
    ) -> None:
        """
        Check if lead still matches campaign criteria after stage/source change
        
        Args:
            lead_id: Lead ID
            new_stage: New stage (if changed)
            new_source: New source (if changed)
        """
        try:
            logger.info(f"Checking campaign criteria for lead {lead_id}")
            
            # Get all active enrollments for this lead
            enrollments = await self.db[self.enrollment_collection].find({
                "lead_id": lead_id,
                "job_type": "enrollment",
                "status": TrackingStatus.ACTIVE.value
            }).to_list(None)
            
            if not enrollments:
                logger.debug(f"No active campaign enrollments for lead {lead_id}")
                return
            
            # Check each enrollment
            for enrollment in enrollments:
                campaign = await campaign_service.get_campaign(enrollment["campaign_id"])
                
                if not campaign:
                    continue
                
                # Check if lead still matches criteria
                still_matches = await self._check_criteria_match(
                    campaign,
                    enrollment,
                    new_stage,
                    new_source
                )
                
                if not still_matches:
                    # Pause this enrollment
                    await self._pause_enrollment(enrollment["campaign_id"], lead_id)
                    logger.info(f"Paused campaign {enrollment['campaign_id']} for lead {lead_id} - criteria no longer match")
            
        except Exception as e:
            logger.error(f"Error checking lead criteria: {str(e)}")
    
    async def _check_criteria_match(
        self,
        campaign: Dict[str, Any],
        enrollment: Dict[str, Any],
        new_stage: Optional[str],
        new_source: Optional[str]
    ) -> bool:
        """
        Check if lead still matches campaign criteria
        
        Returns:
            True if still matches
        """
        if campaign["send_to_all"]:
            return True
        
        # Check stage
        if campaign.get("stage_ids") and new_stage:
            stage_names = await self._convert_stage_ids_to_names(campaign["stage_ids"])
            if new_stage not in stage_names:
                return False

        # Check source
        if campaign.get("source_ids") and new_source:
            source_names = await self._convert_source_ids_to_names(campaign["source_ids"])
            if new_source not in source_names:
                return False
        
        return True
    
    async def _pause_enrollment(self, campaign_id: str, lead_id: str) -> None:
        """Pause enrollment and cancel pending jobs"""
        try:
            # Update enrollment status
            await self.db[self.enrollment_collection].update_one(
                {
                    "campaign_id": campaign_id,
                    "lead_id": lead_id,
                    "job_type": "enrollment"
                },
                {
                    "$set": {
                        "status": TrackingStatus.CRITERIA_NOT_MATCHED.value,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            # Cancel pending jobs
            await self.db[self.jobs_collection].update_many(
                {
                    "campaign_id": campaign_id,
                    "lead_id": lead_id,
                    "job_type": "message_job",
                    "status": TrackingStatus.PENDING.value
                },
                {
                    "$set": {
                        "status": TrackingStatus.CANCELLED.value,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Error pausing enrollment: {str(e)}")


# Global service instance
campaign_executor = CampaignExecutor()