from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
import logging
import re

from ..config.database import get_database
from ..models.lead import (
    LeadCreateComprehensive, LeadUpdateComprehensive, LeadStatus, LeadStage,
    DuplicateCheckResult, LeadCreate, LeadUpdate
)
from ..schemas.lead import LeadFilterParams
from .lead_assignment_service import lead_assignment_service
from .user_lead_array_service import user_lead_array_service

logger = logging.getLogger(__name__)

class LeadService:
    """Core lead service - CRUD operations and business logic"""
    
    def __init__(self):
        pass
    
    def get_db(self):
        """Get database connection"""
        return get_database()
    
    # ... (keep all your existing methods: check_for_duplicates, generate_lead_id, etc.)
    
    async def create_lead_comprehensive(
        self, 
        lead_data: LeadCreateComprehensive, 
        created_by: str,
        force_create: bool = False
    ) -> Dict[str, Any]:
        """Create a comprehensive lead with round-robin assignment"""
        db = self.get_db()
        
        try:
            # Step 1: Check for duplicates
            duplicate_check = await self.check_for_duplicates(lead_data)
            
            if duplicate_check.is_duplicate and not force_create:
                logger.warning(f"Duplicate lead creation attempted: {lead_data.basic_info.email}")
                return {
                    "success": False,
                    "message": f"Duplicate lead found. Matches existing lead(s) by: {', '.join(duplicate_check.match_criteria)}",
                    "duplicate_check": duplicate_check,
                    "lead": None
                }
            
            # Step 2: Generate lead ID
            lead_id = await self.generate_lead_id()
            
            # Step 3: Get round-robin assignment
            assigned_to = await lead_assignment_service.get_next_assignee_round_robin()
            assignment_method = "round_robin" if assigned_to else "none"
            
            # Get assigned user's name
            assigned_to_name = "Unassigned"
            if assigned_to:
                assigned_user = await db.users.find_one({"email": assigned_to})
                if assigned_user:
                    first_name = assigned_user.get('first_name', '')
                    last_name = assigned_user.get('last_name', '')
                    assigned_to_name = f"{first_name} {last_name}".strip() or assigned_user.get('email', 'Unknown')
            
            # Step 4: Create lead document
            lead_doc = {
                "lead_id": lead_id,
                "status": LeadStatus.OPEN,
                "name": lead_data.basic_info.name,
                "email": lead_data.basic_info.email.lower(),
                "contact_number": lead_data.basic_info.contact_number,
                "phone_number": lead_data.basic_info.contact_number,
                "source": lead_data.basic_info.source,
                "stage": lead_data.status_and_tags.stage if lead_data.status_and_tags else LeadStage.INITIAL,
                "lead_score": lead_data.status_and_tags.lead_score if lead_data.status_and_tags else 0,
                "tags": lead_data.status_and_tags.tags if lead_data.status_and_tags else [],
                "assigned_to": assigned_to,
                "assigned_to_name": assigned_to_name,
                "assignment_method": assignment_method,
                "notes": lead_data.additional_info.notes if lead_data.additional_info else None,
                "created_by": created_by,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "last_contacted": None,
                "assignment_history": [
                    {
                        "assigned_to": assigned_to,
                        "assigned_to_name": assigned_to_name,
                        "assigned_by": created_by,
                        "assignment_method": assignment_method,
                        "assigned_at": datetime.utcnow(),
                        "reason": "Initial auto-assignment via round-robin"
                    }
                ] if assigned_to else []
            }
            
            # Step 5: Insert lead and update user array
            result = await db.leads.insert_one(lead_doc)
            lead_doc["_id"] = str(result.inserted_id)
            lead_doc["id"] = str(result.inserted_id)
            
            # Add to user's assigned_leads array
            if assigned_to:
                await user_lead_array_service.add_lead_to_user_array(assigned_to, lead_id)
            
            # Get creator name and log activity
            # ... (keep existing code)
            
            return {
                "success": True,
                "message": f"Lead {lead_id} created successfully",
                "lead": self._format_lead_response(lead_doc),
                "assignment_info": {
                    "assigned_to": assigned_to,
                    "assigned_to_name": assigned_to_name,
                    "assignment_method": assignment_method
                }
            }
            
        except Exception as e:
            logger.error(f"Error creating comprehensive lead: {str(e)}")
            raise Exception(f"Failed to create lead: {str(e)}")
    
    # Delegate assignment operations to assignment service
    async def reassign_lead_manual(self, lead_id: str, new_assignee: str, reassigned_by: str, reason: Optional[str] = None) -> bool:
        """Delegate to assignment service"""
        return await lead_assignment_service.reassign_lead(lead_id, new_assignee, reassigned_by, reason)
    
    async def get_round_robin_stats(self) -> Dict[str, Any]:
        """Delegate to assignment service"""
        return await lead_assignment_service.get_round_robin_stats()
    
    async def get_user_leads_fast(self, user_email: str) -> Dict[str, Any]:
        """Delegate to user array service"""
        return await user_lead_array_service.get_user_leads_fast(user_email)
    
    # ... (keep all other existing methods)

# Global service instance
lead_service = LeadService()