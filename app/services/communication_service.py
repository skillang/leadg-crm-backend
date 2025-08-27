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
        log_activity: bool = True,
        current_user: Optional[Dict[str, Any]] = None,
        message_content: Optional[str] = None
    ) -> bool:
        """
        Update last_contacted timestamp for a lead without touching updated_at.
        
        Args:
            lead_id (str): Lead ID (e.g., "DC-DM-22")
            method (str, optional): Communication method (email, phone, whatsapp, meeting)
            log_activity (bool): Whether to log activity record
            current_user (dict, optional): Current user context
            message_content (str, optional): Message content for preview
            
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
            
            # Optionally log activity record with user context
            if log_activity and method:
                await CommunicationService._log_communication_activity(
                    lead_id, 
                    method, 
                    current_user=current_user,
                    message_content=message_content
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating last_contacted for lead {lead_id}: {str(e)}")
            return False

    @staticmethod
    async def log_email_communication(
        lead_id: str, 
        email_subject: Optional[str] = None,
        template_key: Optional[str] = None,
        current_user: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log email communication for a lead.
        
        Args:
            lead_id (str): Lead ID
            email_subject (str, optional): Email subject line
            template_key (str, optional): Email template used
            current_user (dict, optional): Current user context
            
        Returns:
            bool: Success status
        """
        success = await CommunicationService.update_last_contacted(
            lead_id, 
            method="email",
            log_activity=True,
            current_user=current_user,
            message_content=email_subject
        )
        
        if success:
            user_info = current_user.get('email', 'System') if current_user else 'System'
            logger.info(f"Email communication logged for lead {lead_id} by {user_info}")
        
        return success
    
    @staticmethod
    async def log_phone_communication(
        lead_id: str,
        call_duration: Optional[int] = None,
        call_status: Optional[str] = None,
        current_user: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log phone call communication for a lead.
        
        Args:
            lead_id (str): Lead ID
            call_duration (int, optional): Call duration in seconds
            call_status (str, optional): Call completion status
            current_user (dict, optional): Current user context
            
        Returns:
            bool: Success status
        """
        # Create call details for logging
        call_details = None
        if call_duration:
            minutes = call_duration // 60
            seconds = call_duration % 60
            call_details = f"Duration: {minutes}m {seconds}s"
        
        success = await CommunicationService.update_last_contacted(
            lead_id,
            method="phone", 
            log_activity=True,
            current_user=current_user,
            message_content=call_details
        )
        
        if success:
            user_info = current_user.get('email', 'System') if current_user else 'System'
            logger.info(f"Phone communication logged for lead {lead_id} by {user_info}")
        
        return success
    
    @staticmethod
    async def log_whatsapp_communication(
        lead_id: str, 
        current_user: Optional[Dict[str, Any]] = None,
        message_content: Optional[str] = None
    ) -> bool:
        """
        Log WhatsApp communication for a lead.
        
        Args:
            lead_id (str): Lead ID
            current_user (dict, optional): Current user context
            message_content (str, optional): Message content for preview
            
        Returns:
            bool: Success status
        """
        success = await CommunicationService.update_last_contacted(
            lead_id,
            method="whatsapp",
            log_activity=True,
            current_user=current_user,
            message_content=message_content
        )
        
        if success:
            user_info = current_user.get('email', 'System') if current_user else 'System Generated'
            logger.info(f"WhatsApp communication logged for lead {lead_id} by {user_info}")
        
        return success

    @staticmethod
    async def log_meeting_communication(
        lead_id: str,
        meeting_type: Optional[str] = None,
        current_user: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log meeting/call communication for a lead.
        
        Args:
            lead_id (str): Lead ID
            meeting_type (str, optional): Type of meeting (video, in-person, etc.)
            current_user (dict, optional): Current user context
            
        Returns:
            bool: Success status
        """
        success = await CommunicationService.update_last_contacted(
            lead_id,
            method="meeting",
            log_activity=True,
            current_user=current_user,
            message_content=meeting_type
        )
        
        if success:
            user_info = current_user.get('email', 'System') if current_user else 'System'
            logger.info(f"Meeting communication logged for lead {lead_id} by {user_info}")
        
        return success
    
    @staticmethod
    async def _log_communication_activity(
        lead_id: str, 
        method: str, 
        current_user: Optional[Dict[str, Any]] = None,
        message_content: Optional[str] = None
    ) -> None:
        """
        Internal method to log communication activity to lead_activities collection.
        
        Args:
            lead_id (str): Lead ID
            method (str): Communication method (email, phone, whatsapp, meeting)
            current_user (dict, optional): Current user context for "done by" field
            message_content (str, optional): Message preview for WhatsApp
        """
        try:
            db = get_database()
            
            # Determine who performed this action
            created_by = None
            created_by_name = "System Generated"  # Default fallback for webhooks
            
            if current_user:
                # Extract user ID
                user_id = current_user.get("user_id") or current_user.get("_id") or current_user.get("id")
                if user_id:
                    created_by = ObjectId(user_id) if ObjectId.is_valid(str(user_id)) else user_id
                    
                    # Build user name
                    first_name = current_user.get('first_name', '')
                    last_name = current_user.get('last_name', '')
                    if first_name and last_name:
                        created_by_name = f"{first_name} {last_name}".strip()
                    else:
                        created_by_name = current_user.get('email', 'Unknown User')
            
            # Create activity description based on method and context
            if method == "whatsapp":
                if current_user:
                    # Outgoing message (user sent it)
                    if message_content:
                        preview = message_content[:50] + "..." if len(message_content) > 50 else message_content
                        description = f"Sent WhatsApp message: {preview}"
                    else:
                        description = "Sent WhatsApp message"
                else:
                    # Incoming message (webhook/system)
                    if message_content:
                        preview = message_content[:50] + "..." if len(message_content) > 50 else message_content
                        description = f"Received WhatsApp message: {preview}"
                    else:
                        description = "Received WhatsApp message"
            elif method == "email":
                if message_content:
                    description = f"Email sent - Subject: {message_content}"
                else:
                    description = "Contact made via email"
            elif method == "phone":
                if message_content:
                    description = f"Phone call made - {message_content}"
                else:
                    description = "Contact made via phone call"
            elif method == "meeting":
                if message_content:
                    description = f"Meeting conducted - {message_content}"
                else:
                    description = "Contact made via meeting"
            else:
                # Generic fallback
                description = f"Contact made via {method}"
            
            # Create activity document
            activity_doc = {
                "lead_id": lead_id,
                "activity_type": "communication_logged",
                "description": description,
                "created_by": created_by,
                "created_by_name": created_by_name,
                "created_at": datetime.utcnow(),
                "is_system_generated": True if not current_user else False,
                "metadata": {
                    "communication_method": method,
                    "message_preview": message_content[:100] if message_content else None,
                    "logged_via": "whatsapp_webhook" if method == "whatsapp" and not current_user else "manual",
                    "direction": "outgoing" if current_user else "incoming" if method == "whatsapp" else "unknown"
                }
            }
            
            # Insert activity
            await db.lead_activities.insert_one(activity_doc)
            logger.info(f"Communication activity logged for lead {lead_id} via {method} by {created_by_name}")
            
        except Exception as e:
            logger.error(f"Error logging communication activity: {str(e)}")
    
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

    @staticmethod
    async def get_lead_communication_stats(lead_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get communication statistics for a lead over the specified period.
        
        Args:
            lead_id (str): Lead ID
            days (int): Number of days to look back (default: 30)
            
        Returns:
            dict: Communication statistics
        """
        try:
            db = get_database()
            
            # Date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Query activities
            activities = await db.lead_activities.find({
                "lead_id": lead_id,
                "activity_type": "communication_logged",
                "created_at": {"$gte": start_date, "$lte": end_date}
            }).to_list(None)
            
            # Analyze activities
            stats = {
                "total_communications": len(activities),
                "by_method": {},
                "by_direction": {"incoming": 0, "outgoing": 0},
                "last_communication": None,
                "most_active_day": None
            }
            
            # Count by method and direction
            daily_counts = {}
            
            for activity in activities:
                method = activity.get("metadata", {}).get("communication_method", "unknown")
                direction = activity.get("metadata", {}).get("direction", "unknown")
                created_at = activity.get("created_at")
                
                # Count by method
                stats["by_method"][method] = stats["by_method"].get(method, 0) + 1
                
                # Count by direction
                if direction in ["incoming", "outgoing"]:
                    stats["by_direction"][direction] += 1
                
                # Track daily activity
                if created_at:
                    day_key = created_at.strftime("%Y-%m-%d")
                    daily_counts[day_key] = daily_counts.get(day_key, 0) + 1
                    
                    # Track last communication
                    if not stats["last_communication"] or created_at > stats["last_communication"]:
                        stats["last_communication"] = created_at
            
            # Find most active day
            if daily_counts:
                most_active = max(daily_counts.items(), key=lambda x: x[1])
                stats["most_active_day"] = {
                    "date": most_active[0],
                    "count": most_active[1]
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting communication stats for lead {lead_id}: {str(e)}")
            return {
                "total_communications": 0,
                "by_method": {},
                "by_direction": {"incoming": 0, "outgoing": 0},
                "last_communication": None,
                "most_active_day": None
            }