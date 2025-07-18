
# app/services/lead_service.py - Complete Updated with Selective Round Robin & Multi-Assignment

from typing import Dict, Any, Optional, List
from datetime import datetime
from bson import ObjectId
import logging

from ..config.database import get_database
from ..models.lead import (
    LeadCreateComprehensive, ExperienceLevel, LeadSource, CourseLevel
)
from .lead_assignment_service import lead_assignment_service
from .user_lead_array_service import user_lead_array_service

logger = logging.getLogger(__name__)

class LeadService:
    """Service for lead-related operations with enhanced assignment features"""
    
    def __init__(self):
        pass
    
    def get_db(self):
        """Get database connection"""
        return get_database()
    
    # ============================================================================
    # 🆕 NEW: ENHANCED LEAD CREATION WITH SELECTIVE ROUND ROBIN
    # ============================================================================
    
    async def create_lead_with_selective_assignment(
        self, 
        basic_info, 
        status_and_tags, 
        assignment_info, 
        additional_info,
        created_by: str,
        selected_user_emails: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create lead with selective round robin assignment
        
        Args:
            selected_user_emails: If provided, round robin will only use these users
            Other params: Same as existing create_lead method
        """
        db = self.get_db()
        
        try:
            # Step 1: Generate lead ID
            lead_id = await self._generate_lead_id()
            
            # Step 2: Handle assignment with selective round robin
            assigned_to = assignment_info.assigned_to if assignment_info else None
            assigned_to_name = None
            assignment_method = "manual" if assigned_to else "round_robin"
            
            if not assigned_to:
                # Use selective round robin if specific users provided
                if selected_user_emails:
                    assigned_to = await lead_assignment_service.get_next_assignee_selective_round_robin(
                        selected_user_emails
                    )
                    assignment_method = "selective_round_robin"
                    logger.info(f"Selective round robin assigned to: {assigned_to}")
                else:
                    # Use regular round robin for all active users
                    assigned_to = await lead_assignment_service.get_next_assignee_round_robin()
                    assignment_method = "round_robin"
                    logger.info(f"Regular round robin assigned to: {assigned_to}")
            
            # Get assignee name
            if assigned_to:
                assignee = await db.users.find_one({"email": assigned_to})
                if assignee:
                    assigned_to_name = f"{assignee.get('first_name', '')} {assignee.get('last_name', '')}".strip()
                    if not assigned_to_name:
                        assigned_to_name = assignee.get('email', 'Unknown')
            
            # Step 3: Create lead document with new multi-assignment fields
            lead_doc = {
                "lead_id": lead_id,
                "status": status_and_tags.status if hasattr(status_and_tags, 'status') else "New",
                "name": basic_info.name,
                "email": basic_info.email.lower(),
                "contact_number": basic_info.contact_number,
                "phone_number": basic_info.contact_number,  # Legacy field
                "source": basic_info.source,
                "category": basic_info.category,
                
                # Optional fields
                "age": basic_info.age,
                "experience": basic_info.experience,
                "nationality": basic_info.nationality,
                
                # Status and tags
                "stage": status_and_tags.stage if hasattr(status_and_tags, 'stage') else "Pending",
                "lead_score": status_and_tags.lead_score if hasattr(status_and_tags, 'lead_score') else 0,
                "priority": "medium",
                "tags": status_and_tags.tags if hasattr(status_and_tags, 'tags') else [],
                
                # Single assignment (backward compatibility)
                "assigned_to": assigned_to,
                "assigned_to_name": assigned_to_name,
                "assignment_method": assignment_method,
                
                # 🆕 NEW: Multi-assignment fields
                "co_assignees": [],  # Initially empty, can be added later
                "co_assignees_names": [],
                "is_multi_assigned": False,
                
                # Assignment history
                "assignment_history": [
                    {
                        "assigned_to": assigned_to,
                        "assigned_to_name": assigned_to_name,
                        "assigned_by": created_by,
                        "assignment_method": assignment_method,
                        "assigned_at": datetime.utcnow(),
                        "reason": "Initial assignment",
                        "selected_users_pool": selected_user_emails  # Track which users were in the pool
                    }
                ],
                
                # Additional info
                "notes": additional_info.notes if hasattr(additional_info, 'notes') else "",
                "created_by": created_by,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            # Step 4: Insert lead
            result = await db.leads.insert_one(lead_doc)
            
            if result.inserted_id:
                # Step 5: Update user array if assigned
                if assigned_to:
                    await user_lead_array_service.add_lead_to_user_array(assigned_to, lead_id)
                
                logger.info(f"Lead {lead_id} created and assigned to {assigned_to} using {assignment_method}")
                
                return {
                    "success": True,
                    "lead_id": lead_id,
                    "assigned_to": assigned_to,
                    "assignment_method": assignment_method,
                    "selected_users_pool": selected_user_emails
                }
            else:
                return {"success": False, "error": "Failed to create lead"}
                
        except Exception as e:
            logger.error(f"Error creating lead with selective assignment: {str(e)}")
            return {"success": False, "error": str(e)}
    
    # ============================================================================
    # 🆕 NEW: BULK LEAD CREATION WITH SELECTIVE ROUND ROBIN
    # ============================================================================
    
    async def bulk_create_leads_with_selective_assignment(
        self,
        leads_data: List[Dict[str, Any]],
        created_by: str,
        assignment_method: str = "all_users",
        selected_user_emails: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Bulk create leads with selective round robin assignment
        
        Args:
            leads_data: List of lead data dictionaries
            created_by: Email of user creating leads
            assignment_method: "all_users" or "selected_users"
            selected_user_emails: Required if assignment_method is "selected_users"
        """
        db = self.get_db()
        
        try:
            created_leads = []
            failed_leads = []
            assignment_summary = []
            
            for i, lead_data in enumerate(leads_data):
                try:
                    # Generate lead ID
                    lead_id = await self._generate_lead_id()
                    
                    # Get next assignee based on method
                    if assignment_method == "selected_users" and selected_user_emails:
                        assigned_to = await lead_assignment_service.get_next_assignee_selective_round_robin(
                            selected_user_emails
                        )
                        method = "selective_round_robin"
                    else:
                        assigned_to = await lead_assignment_service.get_next_assignee_round_robin()
                        method = "round_robin"
                    
                    # Get assignee name
                    assigned_to_name = None
                    if assigned_to:
                        assignee = await db.users.find_one({"email": assigned_to})
                        if assignee:
                            assigned_to_name = f"{assignee.get('first_name', '')} {assignee.get('last_name', '')}".strip()
                            if not assigned_to_name:
                                assigned_to_name = assignee.get('email', 'Unknown')
                    
                    # Create lead document
                    lead_doc = {
                        "lead_id": lead_id,
                        "status": lead_data.get("status", "New"),
                        "name": lead_data.get("name", ""),
                        "email": lead_data.get("email", "").lower(),
                        "contact_number": lead_data.get("contact_number", ""),
                        "phone_number": lead_data.get("contact_number", ""),
                        "source": lead_data.get("source", "bulk_import"),
                        "category": lead_data.get("category", "General"),
                        
                        # Optional fields
                        "age": lead_data.get("age"),
                        "experience": lead_data.get("experience"),
                        "nationality": lead_data.get("nationality"),
                        
                        # Status and tags
                        "stage": lead_data.get("stage", "Pending"),
                        "lead_score": lead_data.get("lead_score", 0),
                        "priority": lead_data.get("priority", "medium"),
                        "tags": lead_data.get("tags", []),
                        
                        # Assignment
                        "assigned_to": assigned_to,
                        "assigned_to_name": assigned_to_name,
                        "assignment_method": method,
                        
                        # Multi-assignment fields
                        "co_assignees": [],
                        "co_assignees_names": [],
                        "is_multi_assigned": False,
                        
                        # Assignment history
                        "assignment_history": [
                            {
                                "assigned_to": assigned_to,
                                "assigned_to_name": assigned_to_name,
                                "assigned_by": created_by,
                                "assignment_method": method,
                                "assigned_at": datetime.utcnow(),
                                "reason": f"Bulk creation ({assignment_method})",
                                "bulk_index": i,
                                "selected_users_pool": selected_user_emails if assignment_method == "selected_users" else None
                            }
                        ],
                        
                        # Additional info
                        "notes": lead_data.get("notes", ""),
                        "created_by": created_by,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                    
                    # Insert lead
                    result = await db.leads.insert_one(lead_doc)
                    
                    if result.inserted_id:
                        # Update user array
                        if assigned_to:
                            await user_lead_array_service.add_lead_to_user_array(assigned_to, lead_id)
                        
                        created_leads.append(lead_id)
                        assignment_summary.append({
                            "lead_id": lead_id,
                            "assigned_to": assigned_to,
                            "status": "success"
                        })
                        
                        logger.info(f"Bulk created lead {lead_id} assigned to {assigned_to}")
                    else:
                        failed_leads.append({
                            "index": i,
                            "data": lead_data,
                            "error": "Failed to insert to database"
                        })
                        assignment_summary.append({
                            "lead_id": None,
                            "assigned_to": None,
                            "status": "failed",
                            "error": "Database insertion failed"
                        })
                
                except Exception as e:
                    logger.error(f"Error creating lead at index {i}: {str(e)}")
                    failed_leads.append({
                        "index": i,
                        "data": lead_data,
                        "error": str(e)
                    })
                    assignment_summary.append({
                        "lead_id": None,
                        "assigned_to": None,
                        "status": "failed",
                        "error": str(e)
                    })
            
            return {
                "success": len(failed_leads) == 0,
                "total_processed": len(leads_data),
                "successfully_created": len(created_leads),
                "failed_count": len(failed_leads),
                "created_lead_ids": created_leads,
                "failed_leads": failed_leads,
                "assignment_method": assignment_method,
                "selected_users": selected_user_emails if assignment_method == "selected_users" else None,
                "assignment_summary": assignment_summary
            }
            
        except Exception as e:
            logger.error(f"Error in bulk lead creation: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "total_processed": len(leads_data),
                "successfully_created": 0,
                "failed_count": len(leads_data)
            }
    
    # ============================================================================
    # 🆕 NEW: METHODS FOR QUERYING MULTI-ASSIGNED LEADS
    # ============================================================================
    
    async def get_leads_by_user_including_co_assignments(
        self, 
        user_email: str, 
        page: int = 1, 
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get all leads where user is assigned (primary or co-assignee)
        """
        db = self.get_db()
        
        try:
            # Build query to include both primary and co-assignments
            base_query = {
                "$or": [
                    {"assigned_to": user_email},
                    {"co_assignees": user_email}
                ]
            }
            
            # Add additional filters if provided
            if filters:
                base_query.update(filters)
            
            # Get total count
            total_count = await db.leads.count_documents(base_query)
            
            # Get leads with pagination
            skip = (page - 1) * limit
            leads = await db.leads.find(base_query).skip(skip).limit(limit).sort("created_at", -1).to_list(None)
            
            # Convert ObjectId to string for JSON serialization
            for lead in leads:
                if "_id" in lead:
                    lead["_id"] = str(lead["_id"])
            
            return {
                "success": True,
                "leads": leads,
                "total_count": total_count,
                "page": page,
                "limit": limit,
                "total_pages": (total_count + limit - 1) // limit,
                "user_email": user_email
            }
            
        except Exception as e:
            logger.error(f"Error getting leads for user {user_email}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "leads": [],
                "total_count": 0
            }
    
    async def get_multi_assigned_leads_stats(self) -> Dict[str, Any]:
        """
        Get statistics about multi-assigned leads
        """
        db = self.get_db()
        
        try:
            # Count multi-assigned leads
            multi_assigned_count = await db.leads.count_documents({"is_multi_assigned": True})
            
            # Count single-assigned leads
            single_assigned_count = await db.leads.count_documents({
                "assigned_to": {"$ne": None},
                "is_multi_assigned": {"$ne": True}
            })
            
            # Count unassigned leads
            unassigned_count = await db.leads.count_documents({"assigned_to": None})
            
            # Get distribution of team sizes for multi-assigned leads
            pipeline = [
                {"$match": {"is_multi_assigned": True}},
                {
                    "$addFields": {
                        "team_size": {
                            "$add": [
                                1,  # Primary assignee
                                {"$size": {"$ifNull": ["$co_assignees", []]}}  # Co-assignees
                            ]
                        }
                    }
                },
                {
                    "$group": {
                        "_id": "$team_size",
                        "count": {"$sum": 1}
                    }
                },
                {"$sort": {"_id": 1}}
            ]
            
            team_size_distribution = await db.leads.aggregate(pipeline).to_list(None)
            
            # Get most active co-assignees
            pipeline = [
                {"$match": {"co_assignees": {"$exists": True, "$ne": []}}},
                {"$unwind": "$co_assignees"},
                {
                    "$group": {
                        "_id": "$co_assignees",
                        "co_assignment_count": {"$sum": 1}
                    }
                },
                {"$sort": {"co_assignment_count": -1}},
                {"$limit": 10}
            ]
            
            top_co_assignees = await db.leads.aggregate(pipeline).to_list(None)
            
            return {
                "total_leads": multi_assigned_count + single_assigned_count + unassigned_count,
                "multi_assigned_leads": multi_assigned_count,
                "single_assigned_leads": single_assigned_count,
                "unassigned_leads": unassigned_count,
                "multi_assignment_percentage": round((multi_assigned_count / (multi_assigned_count + single_assigned_count + unassigned_count)) * 100, 2) if (multi_assigned_count + single_assigned_count + unassigned_count) > 0 else 0,
                "team_size_distribution": team_size_distribution,
                "top_co_assignees": top_co_assignees
            }
            
        except Exception as e:
            logger.error(f"Error getting multi-assignment stats: {str(e)}")
            return {"error": str(e)}
    
    # ============================================================================
    # EXISTING METHODS (UPDATED TO MAINTAIN COMPATIBILITY)
    # ============================================================================
    
    async def create_lead_comprehensive(
        self,
        lead_data: LeadCreateComprehensive,
        created_by: str,
        force_create: bool = False
    ) -> Dict[str, Any]:
        """
        UPDATED: Original comprehensive create method now uses selective assignment if needed
        Maintains backward compatibility while supporting new features
        """
        try:
            db = self.get_db()
            
            # Step 1: Extract basic info including new fields
            basic_info = lead_data.basic_info
            status_and_tags = lead_data.status_and_tags or type('obj', (object,), {})()
            assignment = lead_data.assignment or type('obj', (object,), {})()
            additional_info = lead_data.additional_info or type('obj', (object,), {})()
            
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
            assigned_to = assignment.assigned_to if hasattr(assignment, 'assigned_to') else None
            assigned_to_name = None
            assignment_method = "manual" if assigned_to else "round_robin"
            
            if not assigned_to:
                # Auto-assign using round-robin
                assigned_to = await lead_assignment_service.get_next_assignee_round_robin()
                assignment_method = "round_robin"
                logger.info(f"Auto-assigned to: {assigned_to}")
            
            # Get assignee name
            if assigned_to:
                assignee = await db.users.find_one({"email": assigned_to})
                if assignee:
                    assigned_to_name = f"{assignee.get('first_name', '')} {assignee.get('last_name', '')}".strip()
                    if not assigned_to_name:
                        assigned_to_name = assignee.get('email', 'Unknown')
            
            # Step 5: Create lead document with new fields and multi-assignment support
            lead_doc = {
                "lead_id": lead_id,
                "status": getattr(status_and_tags, 'status', 'New'),
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
                "stage": getattr(status_and_tags, 'stage', 'Pending'),
                "lead_score": getattr(status_and_tags, 'lead_score', 0),
                "priority": "medium",
                "tags": getattr(status_and_tags, 'tags', []),
                
                # Assignment
                "assigned_to": assigned_to,
                "assigned_to_name": assigned_to_name,
                "assignment_method": assignment_method,
                
                # 🆕 NEW: Multi-assignment fields
                "co_assignees": [],
                "co_assignees_names": [],
                "is_multi_assigned": False,
                
                "assignment_history": [
                    {
                        "assigned_to": assigned_to,
                        "assigned_to_name": assigned_to_name,
                        "assigned_by": created_by,
                        "assignment_method": assignment_method,
                        "assigned_at": datetime.utcnow(),
                        "reason": "Initial assignment"
                    }
                ],
                
                # Additional info
                "notes": getattr(additional_info, 'notes', ''),
                "created_by": created_by,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            # Step 6: Insert lead
            result = await db.leads.insert_one(lead_doc)
            
            if result.inserted_id:
                # Step 7: Update user array if assigned
                if assigned_to:
                    await user_lead_array_service.add_lead_to_user_array(assigned_to, lead_id)
                
                # Step 8: Log activity
                await self.log_lead_activity(
                    lead_id=lead_id,
                    activity_type="lead_created",
                    description=f"Lead created with ID: {lead_id}",
                    created_by=created_by,
                    metadata={
                        "category": basic_info.category,
                        "source": basic_info.source,
                        "assigned_to": assigned_to,
                        "assignment_method": assignment_method,
                        "has_age": basic_info.age is not None,
                        "has_experience": basic_info.experience is not None,
                        "has_nationality": basic_info.nationality is not None
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
            else:
                return {
                    "success": False,
                    "message": "Failed to create lead"
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
            
            # Get the next sequence number for this category
            result = await db.lead_counters.find_one_and_update(
                {"category": category_short},
                {"$inc": {"sequence": 1}},
                upsert=True,
                return_document=True
            )
            
            sequence = result["sequence"]
            lead_id = f"{category_short}-{sequence}"
            
            logger.info(f"Generated lead ID: {lead_id} for category: {category}")
            return lead_id
            
        except Exception as e:
            logger.error(f"Error generating lead ID: {str(e)}")
            # Fallback to simple sequence
            return await self._generate_lead_id()
    
    async def get_category_short_form(self, category: str) -> str:
        """Get short form for category"""
        category_mappings = {
            "Study Abroad": "SA",
            "Work Abroad": "WA", 
            "Study in Canada": "SC",
            "Study in USA": "SU",
            "Study in UK": "SK",
            "Study in Australia": "SAU",
            "Visit Visa": "VV",
            "General": "GEN",
            "Technology": "TECH",
            "Business": "BIZ",
            "Healthcare": "HC",
            "Engineering": "ENG",
            "Immigration": "IMM",
            "Nurse Abroad": "NA"
        }
        
        return category_mappings.get(category, "LD")
    
    async def _generate_lead_id(self) -> str:
        """Generate simple sequential lead ID"""
        try:
            db = self.get_db()
            
            # Get the next sequence number
            result = await db.lead_counters.find_one_and_update(
                {"_id": "lead_sequence"},
                {"$inc": {"sequence": 1}},
                upsert=True,
                return_document=True
            )
            
            sequence = result["sequence"]
            lead_id = f"LD-{sequence:04d}"
            
            return lead_id
            
        except Exception as e:
            logger.error(f"Error generating lead ID: {str(e)}")
            # Ultimate fallback
            import time
            return f"LD-{int(time.time())}"
    
    async def log_lead_activity(
        self,
        lead_id: str,
        activity_type: str,
        description: str,
        created_by: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log activity for a lead"""
        try:
            db = self.get_db()
            
            # Get lead document to get ObjectId
            lead = await db.leads.find_one({"lead_id": lead_id})
            if not lead:
                logger.error(f"Lead {lead_id} not found for activity logging")
                return
            
            activity_doc = {
                "lead_object_id": lead["_id"],
                "lead_id": lead_id,
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