from datetime import datetime
from typing import Optional, Dict, Any
from bson import ObjectId
import logging

from app.config.database import get_database

logger = logging.getLogger(__name__)

class CommunicationService:
    """
    Central service for tracking all communication activities with leads.
    Updates last_contacted field without affecting lead's updated_at timestamp.
    """
    
    @staticmethod
    async def update_last_contacted(
        lead_id: str, 
        method: Optional[str] = None,
        log_activity: bool = True
    ) -> bool:
        """
        Update last_contacted timestamp for a lead without touching updated_at.
        
        Args:
            lead_id (str): Lead ID (e.g., "DC-DM-22")
            method (str, optional): Communication method (email, phone, whatsapp, meeting)
            log_activity (bool): Whether to log activity record
            
        Returns:
            bool: True if update successful, False if lead not found
        """
        try:
            db = get_database()
            
            # Update only last_contacted field
            update_data = {
                "last_contacted": datetime.utcnow()
                # Intentionally NOT updating "updated_at" to preserve data semantics
            }
            
            result = await db.leads.update_one(
                {"lead_id": lead_id},
                {"$set": update_data}
            )
            
            if result.matched_count == 0:
                logger.warning(f"Lead {lead_id} not found for last_contacted update")
                return False
            
            logger.info(f"Updated last_contacted for lead {lead_id} via {method or 'unknown'}")
            
            # Optionally log activity record
            if log_activity and method:
                await CommunicationService._log_communication_activity(lead_id, method)
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating last_contacted for lead {lead_id}: {str(e)}")
            return False
    
    @staticmethod
    async def log_email_communication(
        lead_id: str, 
        email_subject: Optional[str] = None,
        template_key: Optional[str] = None
    ) -> bool:
        """
        Log email communication for a lead.
        
        Args:
            lead_id (str): Lead ID
            email_subject (str, optional): Email subject line
            template_key (str, optional): Email template used
            
        Returns:
            bool: Success status
        """
        success = await CommunicationService.update_last_contacted(
            lead_id, 
            method="email",
            log_activity=True
        )
        
        if success:
            logger.info(f"Email communication logged for lead {lead_id}")
        
        return success
    
    @staticmethod
    async def log_phone_communication(
        lead_id: str,
        call_duration: Optional[int] = None,
        call_status: Optional[str] = None
    ) -> bool:
        """
        Log phone call communication for a lead.
        
        Args:
            lead_id (str): Lead ID
            call_duration (int, optional): Call duration in seconds
            call_status (str, optional): Call completion status
            
        Returns:
            bool: Success status
        """
        success = await CommunicationService.update_last_contacted(
            lead_id,
            method="phone", 
            log_activity=True
        )
        
        if success:
            logger.info(f"Phone communication logged for lead {lead_id}")
        
        return success
    
    @staticmethod
    async def log_whatsapp_communication(lead_id: str) -> bool:
        """
        Log WhatsApp communication for a lead.
        
        Args:
            lead_id (str): Lead ID
            
        Returns:
            bool: Success status
        """
        success = await CommunicationService.update_last_contacted(
            lead_id,
            method="whatsapp",
            log_activity=True
        )
        
        if success:
            logger.info(f"WhatsApp communication logged for lead {lead_id}")
        
        return success
    
    @staticmethod
    async def log_meeting_communication(
        lead_id: str,
        meeting_type: Optional[str] = None
    ) -> bool:
        """
        Log meeting/call communication for a lead.
        
        Args:
            lead_id (str): Lead ID
            meeting_type (str, optional): Type of meeting (video, in-person, etc.)
            
        Returns:
            bool: Success status
        """
        success = await CommunicationService.update_last_contacted(
            lead_id,
            method="meeting",
            log_activity=True
        )
        
        if success:
            logger.info(f"Meeting communication logged for lead {lead_id}")
        
        return success
    
    @staticmethod
    async def _log_communication_activity(lead_id: str, method: str) -> None:
        """
        Internal method to log communication activity to lead_activities collection.
        
        Args:
            lead_id (str): Lead ID
            method (str): Communication method
        """
        try:
            db = get_database()
            
            activity_doc = {
                "lead_id": lead_id,
                "activity_type": "communication_logged",
                "description": f"Contact made via {method}",
                "created_at": datetime.utcnow(),
                "is_system_generated": True,
                "metadata": {
                    "contact_method": method,
                    "logged_at": datetime.utcnow().isoformat()
                }
            }
            
            await db.lead_activities.insert_one(activity_doc)
            logger.debug(f"Activity logged for lead {lead_id}: {method} communication")
            
        except Exception as e:
            logger.error(f"Error logging communication activity for lead {lead_id}: {str(e)}")
            # Don't raise exception - communication tracking shouldn't fail the main operation
    
    @staticmethod
    async def get_lead_last_contacted(lead_id: str) -> Optional[datetime]:
        """
        Get the last_contacted timestamp for a lead.
        
        Args:
            lead_id (str): Lead ID
            
        Returns:
            datetime or None: Last contacted timestamp
        """
        try:
            db = get_database()
            
            lead = await db.leads.find_one(
                {"lead_id": lead_id},
                {"last_contacted": 1}
            )
            
            if lead:
                return lead.get("last_contacted")
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting last_contacted for lead {lead_id}: {str(e)}")
            return None