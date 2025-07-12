# app/services/lead_service.py - Complete fixed version with category support and assignment fix

from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId  # type: ignore
import logging
import re
from fastapi import HTTPException  # 🆕 ADD THIS IMPORT

from ..config.database import get_database
from ..models.lead import (
    LeadCreateComprehensive, LeadUpdateComprehensive, LeadStatus, LeadStage,
    DuplicateCheckResult, LeadCreate, LeadUpdate
)
from ..schemas.lead import LeadFilterParams
from .lead_assignment_service import lead_assignment_service
from .user_lead_array_service import user_lead_array_service
from .lead_category_service import lead_category_service  # 🆕 CATEGORY SERVICE

logger = logging.getLogger(__name__)

class LeadService:
    """Core lead service - CRUD operations and business logic"""
    
    def __init__(self):
        pass
    
    def get_db(self):
        """Get database connection"""
        return get_database()
    
    async def check_for_duplicates(self, lead_data: LeadCreateComprehensive) -> DuplicateCheckResult:
        """Check for duplicate leads based on email and phone number"""
        db = self.get_db()
        
        try:
            # Search for existing leads with same email or phone
            query = {
                "$or": [
                    {"email": lead_data.basic_info.email.lower()},
                    {"contact_number": lead_data.basic_info.contact_number},
                    {"phone_number": lead_data.basic_info.contact_number}
                ]
            }
            
            existing_leads = await db.leads.find(query).to_list(length=10)
            
            if existing_leads:
                duplicate_info = []
                match_criteria = []
                
                for lead in existing_leads:
                    if lead["email"].lower() == lead_data.basic_info.email.lower():
                        match_criteria.append("email")
                    if (lead.get("contact_number") == lead_data.basic_info.contact_number or 
                        lead.get("phone_number") == lead_data.basic_info.contact_number):
                        match_criteria.append("phone")
                    
                    duplicate_info.append({
                        "lead_id": lead["lead_id"],
                        "name": lead["name"],
                        "email": lead["email"],
                        "phone": lead.get("contact_number", lead.get("phone_number", "")),
                        "status": lead["status"],
                        "created_at": lead["created_at"].isoformat() if isinstance(lead["created_at"], datetime) else str(lead["created_at"])
                    })
                
                return DuplicateCheckResult(
                    is_duplicate=True,
                    duplicate_leads=duplicate_info,
                    match_criteria=list(set(match_criteria))
                )
            
            return DuplicateCheckResult(is_duplicate=False)
            
        except Exception as e:
            logger.error(f"Error checking duplicates: {str(e)}")
            return DuplicateCheckResult(is_duplicate=False)
    
    async def generate_lead_id(self) -> str:
        """Generate legacy lead ID (fallback method)"""
        db = self.get_db()
        
        try:
            # Get the highest lead ID number
            pipeline = [
                {"$match": {"lead_id": {"$regex": "^LD-"}}},
                {"$addFields": {
                    "lead_number": {
                        "$toInt": {"$substr": ["$lead_id", 3, -1]}
                    }
                }},
                {"$sort": {"lead_number": -1}},
                {"$limit": 1}
            ]
            
            result = await db.leads.aggregate(pipeline).to_list(length=1)
            
            if result:
                next_number = result[0]["lead_number"] + 1
            else:
                next_number = 1000  # Start from LD-1000
            
            return f"LD-{next_number}"
            
        except Exception as e:
            logger.error(f"Error generating lead ID: {str(e)}")
            # Fallback to timestamp-based ID
            timestamp = int(datetime.utcnow().timestamp())
            return f"LD-{timestamp}"
    
    async def create_lead_comprehensive(
        self, 
        lead_data: LeadCreateComprehensive, 
        created_by: str,
        force_create: bool = False
    ) -> Dict[str, Any]:
        """Create a comprehensive lead with category-based lead ID generation"""
        db = self.get_db()
        
        try:
            # Step 1: Validate category exists and is active
            if hasattr(lead_data.basic_info, 'category') and lead_data.basic_info.category:
                category_exists = await db.lead_categories.find_one({
                    "name": lead_data.basic_info.category,
                    "is_active": True
                })
                
                if not category_exists:
                    logger.error(f"Category '{lead_data.basic_info.category}' not found or inactive")
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Category '{lead_data.basic_info.category}' not found or inactive"
                    )
            else:
                # If no category provided, use fallback
                logger.warning("No category provided in lead creation")
                raise HTTPException(
                    status_code=400,
                    detail="Category is required for lead creation"
                )
            
            # Step 2: Check for duplicates
            duplicate_check = await self.check_for_duplicates(lead_data)
            
            if duplicate_check.is_duplicate and not force_create:
                logger.warning(f"Duplicate lead creation attempted: {lead_data.basic_info.email}")
                return {
                    "success": False,
                    "message": f"Duplicate lead found. Matches existing lead(s) by: {', '.join(duplicate_check.match_criteria)}",
                    "duplicate_check": duplicate_check,
                    "lead": None
                }
            
            # Step 3: Generate category-based lead ID
            try:
                lead_id = await lead_category_service.generate_lead_id(lead_data.basic_info.category)
                logger.info(f"Generated category-based lead ID: {lead_id} for category: {lead_data.basic_info.category}")
            except Exception as e:
                logger.error(f"Failed to generate category-based lead ID: {str(e)}")
                # Fallback to old method if category service fails
                lead_id = await self.generate_lead_id()
                logger.info(f"Using fallback lead ID: {lead_id}")
            
            # Step 4: Get round-robin assignment - 🔧 FIXED METHOD NAME
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
            
            # Step 5: Create lead document with category
            lead_doc = {
                "lead_id": lead_id,  # Now category-based (NS-1, SA-1, etc.)
               "status": LeadStatus.initial,  # Default status
                "name": lead_data.basic_info.name,
                "email": lead_data.basic_info.email.lower(),
                "contact_number": lead_data.basic_info.contact_number,
                "phone_number": lead_data.basic_info.contact_number,  # Legacy field
                "source": lead_data.basic_info.source,
                "category": lead_data.basic_info.category,  # 🆕 NEW: Store category
                "stage": lead_data.status_and_tags.stage if lead_data.status_and_tags else LeadStage.INITIAL,
                "lead_score": lead_data.status_and_tags.lead_score if lead_data.status_and_tags else 0,
                "priority": "medium",  # Default priority
                "tags": lead_data.status_and_tags.tags if lead_data.status_and_tags else [],
                "assigned_to": assigned_to,
                "assigned_to_name": assigned_to_name,
                "assignment_method": assignment_method,
                "assignment_history": [
                    {
                        "assigned_to": assigned_to,
                        "assigned_to_name": assigned_to_name,
                        "assigned_by": created_by,
                        "assignment_method": assignment_method,
                        "assigned_at": datetime.utcnow(),
                        "reason": "Initial auto-assignment via round-robin"
                    }
                ] if assigned_to else [],
                "notes": lead_data.additional_info.notes if lead_data.additional_info else None,
                "created_by": created_by,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "last_contacted": None,
                # Legacy fields for compatibility
                "country_of_interest": "",
                "course_level": ""
            }
            
            # Step 6: Insert lead
            result = await db.leads.insert_one(lead_doc)
            lead_doc["_id"] = str(result.inserted_id)
            lead_doc["id"] = str(result.inserted_id)
            
            # Step 7: Update user array and log activity
            if assigned_to:
                await user_lead_array_service.add_lead_to_user_array(assigned_to, lead_id)
                
            # Log activity
            await self.log_activity(
                lead_id=lead_id,
                activity_type="lead_created",
                description=f"Lead created in category '{lead_data.basic_info.category}' with ID {lead_id}",
                performed_by=created_by,
                additional_data={
                    "category": lead_data.basic_info.category,
                    "source": lead_data.basic_info.source,
                    "assignment_method": assignment_method
                }
            )
            
            logger.info(f"Lead {lead_id} created successfully in category {lead_data.basic_info.category}")
            
            return {
                "success": True,
                "message": f"Lead {lead_id} created successfully with status 'Initial' and auto-assigned to {assigned_to_name} via {assignment_method}",
                "lead": self._format_lead_response(lead_doc),
                "assignment_info": {
                    "assigned_to": assigned_to,
                    "assigned_to_name": assigned_to_name,
                    "assignment_method": assignment_method,
                    "assignment_history": lead_doc.get("assignment_history", [])
                },
                "duplicate_check": {
                    "is_duplicate": False,
                    "checked": True
                }
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating comprehensive lead: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to create lead: {str(e)}")
    
    def _format_lead_response(self, lead_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Format lead document for response"""
        return {
            "id": str(lead_doc["_id"]) if "_id" in lead_doc else lead_doc.get("id"),
            "lead_id": lead_doc["lead_id"],
            "name": lead_doc["name"],
            "email": lead_doc["email"],
            "contact_number": lead_doc["contact_number"],
            "phone_number": lead_doc.get("phone_number", lead_doc["contact_number"]),
            "country_of_interest": lead_doc.get("country_of_interest", ""),
            "course_level": lead_doc.get("course_level", ""),
            "source": lead_doc["source"],
            "category": lead_doc.get("category", ""),  # 🆕 Include category
            "stage": lead_doc.get("stage", "initial"),
            "lead_score": lead_doc.get("lead_score", 0),
            "priority": lead_doc.get("priority", "medium"),
            "tags": lead_doc.get("tags", []),
            "status": lead_doc["status"],
            "assigned_to": lead_doc.get("assigned_to"),
            "assigned_to_name": lead_doc.get("assigned_to_name"),
            "assignment_method": lead_doc.get("assignment_method"),
            "assignment_history": lead_doc.get("assignment_history", []),
            "notes": lead_doc.get("notes"),
            "created_by": lead_doc["created_by"],
            "created_by_name": lead_doc.get("created_by_name", "Unknown"),
            "created_at": lead_doc["created_at"],
            "updated_at": lead_doc["updated_at"]
        }
    
    async def log_activity(
        self,
        lead_id: str,
        activity_type: str,
        description: str,
        performed_by: str,
        additional_data: Optional[Dict[str, Any]] = None
    ):
        """Log activity to lead_activities collection"""
        db = self.get_db()
        
        try:
            # Get lead object ID
            lead = await db.leads.find_one({"lead_id": lead_id})
            if not lead:
                logger.error(f"Lead {lead_id} not found for activity logging")
                return
            
            activity_doc = {
                "lead_object_id": lead["_id"],
                "lead_id": lead_id,
                "activity_type": activity_type,
                "description": description,
                "created_by": ObjectId(performed_by) if ObjectId.is_valid(performed_by) else performed_by,
                "created_at": datetime.utcnow(),
                "metadata": additional_data or {}
            }
            
            await db.lead_activities.insert_one(activity_doc)
            logger.info(f"Activity logged for lead {lead_id}: {activity_type}")
            
        except Exception as e:
            logger.error(f"Failed to log activity for lead {lead_id}: {str(e)}")
    
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
    
    async def get_lead_by_id(self, lead_id: str, current_user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get lead by ID with permission checking"""
        db = self.get_db()
        
        try:
            # Build query based on user role
            query = {"lead_id": lead_id}
            if current_user["role"] != "admin":
                query["assigned_to"] = current_user["email"]
            
            lead = await db.leads.find_one(query)
            
            if not lead:
                return None
            
            return self._format_lead_response(lead)
            
        except Exception as e:
            logger.error(f"Error getting lead {lead_id}: {str(e)}")
            return None
    
    async def update_lead(self, lead_id: str, update_data: Dict[str, Any], updated_by: str) -> Dict[str, Any]:
        """Update lead with activity logging"""
        db = self.get_db()
        
        try:
            # Update the lead
            update_data["updated_at"] = datetime.utcnow()
            
            result = await db.leads.update_one(
                {"lead_id": lead_id},
                {"$set": update_data}
            )
            
            if result.matched_count == 0:
                raise HTTPException(status_code=404, detail="Lead not found")
            
            # Log activity
            await self.log_activity(
                lead_id=lead_id,
                activity_type="lead_updated",
                description=f"Lead updated: {', '.join(update_data.keys())}",
                performed_by=updated_by,
                additional_data={"updated_fields": list(update_data.keys())}
            )
            
            # Get updated lead
            updated_lead = await db.leads.find_one({"lead_id": lead_id})
            return self._format_lead_response(updated_lead)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating lead {lead_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to update lead: {str(e)}")
    
    async def delete_lead(self, lead_id: str, deleted_by: str) -> bool:
        """Delete lead with activity logging"""
        db = self.get_db()
        
        try:
            # Get lead info before deletion
            lead = await db.leads.find_one({"lead_id": lead_id})
            if not lead:
                raise HTTPException(status_code=404, detail="Lead not found")
            
            # Remove from user arrays
            if lead.get("assigned_to"):
                await user_lead_array_service.remove_lead_from_user_array(lead["assigned_to"], lead_id)
            
            # Delete lead
            result = await db.leads.delete_one({"lead_id": lead_id})
            
            if result.deleted_count == 0:
                raise HTTPException(status_code=404, detail="Lead not found")
            
            # Log activity (to activities collection, not tied to lead anymore)
            await self.log_activity(
                lead_id=lead_id,
                activity_type="lead_deleted",
                description=f"Lead {lead_id} deleted",
                performed_by=deleted_by,
                additional_data={"lead_name": lead["name"], "lead_email": lead["email"]}
            )
            
            logger.info(f"Lead {lead_id} deleted successfully")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting lead {lead_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to delete lead: {str(e)}")

# Global service instance
lead_service = LeadService()