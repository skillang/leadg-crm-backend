# app/services/lead_service.py - Updated to handle AGE, EXPERIENCE, and Nationality

from typing import Dict, Any, Optional, List
from datetime import datetime
from bson import ObjectId
import logging

from ..config.database import get_database
from ..models.lead import (
    LeadCreateComprehensive, LeadStatus, LeadStage, 
    ExperienceLevel, LeadSource, CourseLevel
)
from .lead_assignment_service import lead_assignment_service
from .user_lead_array_service import user_lead_array_service

logger = logging.getLogger(__name__)

class LeadService:
    """Service for lead-related operations with support for new fields"""
    
    def __init__(self):
        pass
    
    def get_db(self):
        """Get database connection"""
        return get_database()
    
    async def create_lead_comprehensive(
        self,
        lead_data: LeadCreateComprehensive,
        created_by: str,
        force_create: bool = False
    ) -> Dict[str, Any]:
        """
        Create a comprehensive lead with support for AGE, EXPERIENCE, and Nationality
        """
        try:
            db = self.get_db()
            
            # Step 1: Extract basic info including new fields
            basic_info = lead_data.basic_info
            status_and_tags = lead_data.status_and_tags or {}
            assignment = lead_data.assignment or {}
            additional_info = lead_data.additional_info or {}
            
            logger.info(f"Creating lead with new fields: age={basic_info.age}, experience={basic_info.experience}, nationality={basic_info.nationality}")
            
            # Step 2: Check for duplicates
            if not force_create:
                duplicate_check = await self.check_duplicate_lead(basic_info.email)
                if duplicate_check["is_duplicate"]:
                    return {
                        "success": False,
                        "message": "Lead with this email already exists",
                        "duplicate_check": duplicate_check
                    }
            
            # Step 3: Generate category-based lead ID
            lead_id = await self.generate_lead_id_by_category(basic_info.category)
            
            # Step 4: Handle assignment
            assigned_to = assignment.assigned_to if assignment else None
            assigned_to_name = None
            assignment_method = "manual" if assigned_to else "round_robin"
            
            if not assigned_to:
                # Auto-assign using round-robin
                assigned_to = await lead_assignment_service.get_next_round_robin_user()
                assignment_method = "round_robin"
                logger.info(f"Auto-assigned to: {assigned_to}")
            
            # Get assignee name
            if assigned_to:
                assignee = await db.users.find_one({"email": assigned_to})
                if assignee:
                    assigned_to_name = f"{assignee.get('first_name', '')} {assignee.get('last_name', '')}".strip()
                    if not assigned_to_name:
                        assigned_to_name = assignee.get('email', 'Unknown')
            
            # Step 5: Create lead document with new fields
            lead_doc = {
                "lead_id": lead_id,
                "status": LeadStatus.INITIAL,
                "name": basic_info.name,
                "email": basic_info.email.lower(),
                "contact_number": basic_info.contact_number,
                "phone_number": basic_info.contact_number,  # Legacy field
                "source": basic_info.source,
                "category": basic_info.category,
                
                # 🆕 NEW: Add the new optional fields
                "age": basic_info.age,
                "experience": basic_info.experience,
                "nationality": basic_info.nationality,
                
                # Status and tags
                "stage": status_and_tags.stage if hasattr(status_and_tags, 'stage') else LeadStage.INITIAL,
                "lead_score": status_and_tags.lead_score if hasattr(status_and_tags, 'lead_score') else 0,
                "priority": "medium",
                "tags": status_and_tags.tags if hasattr(status_and_tags, 'tags') else [],
                
                # Assignment
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
                
                # Additional info
                "notes": additional_info.notes if hasattr(additional_info, 'notes') else None,
                
                # System fields
                "created_by": created_by,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "last_contacted": None,
                
                # Legacy fields for compatibility
                "country_of_interest": "",
                "course_level": None
            }
            
            # Step 6: Insert lead
            result = await db.leads.insert_one(lead_doc)
            lead_doc["_id"] = str(result.inserted_id)
            lead_doc["id"] = str(result.inserted_id)
            
            # Step 7: Update user array and log activity
            if assigned_to:
                await user_lead_array_service.add_lead_to_user_array(assigned_to, lead_id)
                
                # Log lead creation activity
                await self.log_lead_activity(
                    lead_id=lead_id,
                    lead_object_id=result.inserted_id,
                    activity_type="lead_created",
                    description=f"Lead '{basic_info.name}' created with ID {lead_id}",
                    created_by=created_by,
                    metadata={
                        "lead_id": lead_id,
                        "lead_name": basic_info.name,
                        "lead_email": basic_info.email,
                        "category": basic_info.category,
                        "assigned_to": assigned_to,
                        "assignment_method": assignment_method,
                        # Include new fields in metadata
                        "age": basic_info.age,
                        "experience": basic_info.experience,
                        "nationality": basic_info.nationality
                    }
                )
            
            logger.info(f"✅ Lead created successfully: {lead_id} with new fields")
            
            return {
                "success": True,
                "message": f"Lead created successfully with ID: {lead_id}",
                "lead": self.format_lead_response(lead_doc),
                "assignment_info": {
                    "assigned_to": assigned_to,
                    "assigned_to_name": assigned_to_name,
                    "assignment_method": assignment_method
                },
                "duplicate_check": {
                    "is_duplicate": False,
                    "checked": True
                }
            }
            
        except Exception as e:
            logger.error(f"Error creating lead: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to create lead: {str(e)}"
            }
    
    async def check_duplicate_lead(self, email: str) -> Dict[str, Any]:
        """Check if lead with email already exists"""
        try:
            db = self.get_db()
            existing_lead = await db.leads.find_one({"email": email.lower()})
            
            if existing_lead:
                return {
                    "is_duplicate": True,
                    "checked": True,
                    "existing_lead_id": existing_lead.get("lead_id"),
                    "duplicate_field": "email",
                    "message": f"Lead with email {email} already exists"
                }
            
            return {
                "is_duplicate": False,
                "checked": True
            }
            
        except Exception as e:
            logger.error(f"Error checking duplicate: {str(e)}")
            return {
                "is_duplicate": False,
                "checked": False,
                "message": f"Error checking duplicate: {str(e)}"
            }
    
    async def generate_lead_id_by_category(self, category: str) -> str:
        """Generate category-based lead ID"""
        try:
            db = self.get_db()
            
            # Get category short form
            category_short = await self.get_category_short_form(category)
            
            # Get next sequence number for this category
            sequence_doc = await db.lead_sequences.find_one_and_update(
                {"category": category},
                {"$inc": {"sequence": 1}},
                upsert=True,
                return_document=True
            )
            
            sequence_number = sequence_doc["sequence"]
            lead_id = f"{category_short}-{sequence_number}"
            
            logger.info(f"Generated lead ID: {lead_id} for category: {category}")
            return lead_id
            
        except Exception as e:
            logger.error(f"Error generating lead ID: {str(e)}")
            # Fallback to simple numeric ID
            return f"LD-{int(datetime.utcnow().timestamp())}"
    
    async def get_category_short_form(self, category: str) -> str:
        """Get short form for category"""
        try:
            db = self.get_db()
            category_doc = await db.lead_categories.find_one({"name": category})
            
            if category_doc and category_doc.get("short_form"):
                return category_doc["short_form"]
            
            # Generate short form if not found
            words = category.split()
            if len(words) >= 2:
                return "".join([word[0].upper() for word in words[:2]])
            else:
                return category[:2].upper()
                
        except Exception as e:
            logger.error(f"Error getting category short form: {str(e)}")
            return "LD"
    
    async def log_lead_activity(
        self,
        lead_id: str,
        lead_object_id: ObjectId,
        activity_type: str,
        description: str,
        created_by: str,
        metadata: Dict[str, Any] = None
    ):
        """Log lead activity"""
        try:
            db = self.get_db()
            
            activity_doc = {
                "lead_id": lead_id,
                "lead_object_id": lead_object_id,
                "activity_type": activity_type,
                "description": description,
                "created_by": ObjectId(created_by) if ObjectId.is_valid(created_by) else created_by,
                "created_at": datetime.utcnow(),
                "is_system_generated": True,
                "metadata": metadata or {}
            }
            
            await db.lead_activities.insert_one(activity_doc)
            logger.info(f"✅ Activity logged: {activity_type} for lead {lead_id}")
            
        except Exception as e:
            logger.error(f"Error logging activity: {str(e)}")
    
    def format_lead_response(self, lead_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Format lead document for response with new fields"""
        return {
            "id": str(lead_doc.get("_id", "")),
            "lead_id": lead_doc.get("lead_id", ""),
            "name": lead_doc.get("name", ""),
            "email": lead_doc.get("email", ""),
            "contact_number": lead_doc.get("contact_number", ""),
            "phone_number": lead_doc.get("phone_number", ""),
            "source": lead_doc.get("source", "website"),
            "category": lead_doc.get("category", ""),
            
            # 🆕 NEW: Include new fields in response
            "age": lead_doc.get("age"),
            "experience": lead_doc.get("experience"),
            "nationality": lead_doc.get("nationality"),
            
            "status": lead_doc.get("status", "Initial"),
            "stage": lead_doc.get("stage", "Initial"),
            "lead_score": lead_doc.get("lead_score", 0),
            "priority": lead_doc.get("priority", "medium"),
            "tags": lead_doc.get("tags", []),
            "assigned_to": lead_doc.get("assigned_to"),
            "assigned_to_name": lead_doc.get("assigned_to_name"),
            "assignment_method": lead_doc.get("assignment_method"),
            "assignment_history": lead_doc.get("assignment_history", []),
            "notes": lead_doc.get("notes"),
            "created_by": lead_doc.get("created_by", ""),
            "created_at": lead_doc.get("created_at"),
            "updated_at": lead_doc.get("updated_at"),
            "last_contacted": lead_doc.get("last_contacted"),
            
            # Legacy fields
            "country_of_interest": lead_doc.get("country_of_interest", ""),
            "course_level": lead_doc.get("course_level")
        }

# Global service instance
lead_service = LeadService()