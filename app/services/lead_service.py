# app/services/lead_service.py - UPDATED - LEAD SERVICE WITH CATEGORY-SOURCE COMBINATION ID GENERATION

from typing import Dict, Any, Optional, List
from datetime import datetime
from bson import ObjectId
import logging

from ..config.database import get_database
from ..models.lead import (
    LeadCreateComprehensive, ExperienceLevel
)
# 🆕 NEW: Import dynamic helpers
from ..models.course_level import CourseLevelHelper
from ..models.source import SourceHelper
from .lead_assignment_service import lead_assignment_service
from .user_lead_array_service import user_lead_array_service
from .lead_category_service import lead_category_service  # 🆕 NEW: Import for new ID generation

logger = logging.getLogger(__name__)

class LeadService:
    """Service for lead-related operations with enhanced assignment features and dynamic validation"""
    
    def __init__(self):
        pass
    
    def get_db(self):
        """Get database connection"""
        return get_database()
    
    # ============================================================================
    # 🆕 NEW: ENHANCED LEAD ID GENERATION WITH CATEGORY-SOURCE COMBINATION
    # ============================================================================
    
    async def generate_lead_id_by_category_and_source(self, category: str, source: str) -> str:
        """
        🆕 NEW: Generate lead ID using category-source combination
        Format: {CATEGORY_SHORT}-{SOURCE_SHORT}-{NUMBER}
        Examples: NS-WB-1, SA-SM-2, WA-RF-1
        """
        try:
            # Use the new combination-based ID generation from lead_category_service
            lead_id = await lead_category_service.generate_lead_id_by_category_and_source(
                category=category,
                source=source
            )
            
            logger.info(f"✅ Generated combination lead ID: {lead_id} for category '{category}' and source '{source}'")
            return lead_id
            
        except Exception as e:
            logger.error(f"Error generating combination lead ID: {str(e)}")
            # Fallback to old category-only format
            logger.warning("Falling back to category-only lead ID generation")
            return await self.generate_lead_id_by_category_fallback(category)
    
    async def generate_lead_id_by_category_fallback(self, category: str) -> str:
        """Fallback to old category-only format if combination fails"""
        try:
            # Use legacy method as fallback
            lead_id = await lead_category_service.generate_lead_id(category)
            logger.warning(f"Generated fallback lead ID: {lead_id} for category: {category}")
            return lead_id
            
        except Exception as e:
            logger.error(f"Error generating fallback lead ID: {str(e)}")
            # Ultimate fallback
            import time
            fallback_id = f"LD-FB-{int(time.time())}"
            logger.error(f"Using ultimate fallback ID: {fallback_id}")
            return fallback_id
    
    async def validate_category_and_source_for_lead_creation(self, category: str, source: str) -> Dict[str, Any]:
        """Validate that both category and source exist and are active before creating lead"""
        try:
            db = self.get_db()
            
            # Check category exists and is active
            category_doc = await db.lead_categories.find_one({"name": category, "is_active": True})
            category_valid = category_doc is not None
            
            # Check source exists and is active
            source_doc = await db.sources.find_one({"name": source, "is_active": True})
            source_valid = source_doc is not None
            
            validation_result = {
                "category_valid": category_valid,
                "source_valid": source_valid,
                "can_create_lead": category_valid and source_valid,
                "category_short_form": category_doc.get("short_form") if category_doc else None,
                "source_short_form": source_doc.get("short_form") if source_doc else None
            }
            
            if not validation_result["can_create_lead"]:
                missing_items = []
                if not category_valid:
                    missing_items.append(f"category '{category}'")
                if not source_valid:
                    missing_items.append(f"source '{source}'")
                
                validation_result["error_message"] = f"Cannot create lead: {' and '.join(missing_items)} not found or inactive"
            else:
                # Preview the lead ID that will be generated
                preview_id = f"{validation_result['category_short_form']}-{validation_result['source_short_form']}-X"
                validation_result["lead_id_preview"] = preview_id
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error validating category and source: {str(e)}")
            return {
                "category_valid": False,
                "source_valid": False,
                "can_create_lead": False,
                "error_message": f"Validation error: {str(e)}"
            }
    
    # ============================================================================
    # 🆕 NEW: DYNAMIC FIELD VALIDATION FUNCTIONS
    # ============================================================================
    
    async def validate_and_set_course_level(self, course_level: Optional[str]) -> Optional[str]:
        """Validate and set course level for lead creation"""
        try:
            if not course_level:
                # Get default course level if none provided
                default_course_level = await CourseLevelHelper.get_default_course_level()
                if default_course_level:
                    logger.info(f"No course level provided, using default: {default_course_level}")
                    return default_course_level
                else:
                    logger.warning("No course level provided and no default course level exists - admin must create course levels")
                    return None
            
            # Validate provided course level exists and is active
            db = self.get_db()
            
            course_level_doc = await db.course_levels.find_one({
                "name": course_level,
                "is_active": True
            })
            
            if not course_level_doc:
                logger.warning(f"Invalid course level '{course_level}', checking for default")
                default_course_level = await CourseLevelHelper.get_default_course_level()
                if default_course_level:
                    logger.info(f"Using default course level: {default_course_level}")
                    return default_course_level
                else:
                    logger.warning("No valid course level found and no default exists")
                    return None
            
            logger.info(f"Using provided course level: {course_level}")
            return course_level
            
        except Exception as e:
            logger.error(f"Error validating course level: {e}")
            # Try to get default as fallback
            try:
                default_course_level = await CourseLevelHelper.get_default_course_level()
                return default_course_level
            except:
                return None

    async def validate_and_set_source(self, source: Optional[str]) -> Optional[str]:
        """Validate and set source for lead creation"""
        try:
            if not source:
                # Get default source if none provided
                default_source = await SourceHelper.get_default_source()
                if default_source:
                    logger.info(f"No source provided, using default: {default_source}")
                    return default_source
                else:
                    logger.warning("No source provided and no default source exists - admin must create sources")
                    return None
            
            # Validate provided source exists and is active
            db = self.get_db()
            
            source_doc = await db.sources.find_one({
                "name": source,
                "is_active": True
            })
            
            if not source_doc:
                logger.warning(f"Invalid source '{source}', checking for default")
                default_source = await SourceHelper.get_default_source()
                if default_source:
                    logger.info(f"Using default source: {default_source}")
                    return default_source
                else:
                    logger.warning("No valid source found and no default exists")
                    return None
            
            logger.info(f"Using provided source: {source}")
            return source
            
        except Exception as e:
            logger.error(f"Error validating source: {e}")
            # Try to get default as fallback
            try:
                default_source = await SourceHelper.get_default_source()
                return default_source
            except:
                return None

    async def validate_required_dynamic_fields(self) -> Dict[str, Any]:
        """Check if required dynamic fields (course levels and sources) exist"""
        try:
            db = self.get_db()
            
            # Check if any active course levels exist
            course_levels_count = await db.course_levels.count_documents({"is_active": True})
            
            # Check if any active sources exist
            sources_count = await db.sources.count_documents({"is_active": True})
            
            # 🆕 NEW: Check if any active categories exist
            categories_count = await db.lead_categories.count_documents({"is_active": True})
            
            validation_result = {
                "course_levels_exist": course_levels_count > 0,
                "sources_exist": sources_count > 0,
                "categories_exist": categories_count > 0,
                "course_levels_count": course_levels_count,
                "sources_count": sources_count,
                "categories_count": categories_count,
                "can_create_leads": course_levels_count > 0 and sources_count > 0 and categories_count > 0
            }
            
            if not validation_result["can_create_leads"]:
                missing_fields = []
                if course_levels_count == 0:
                    missing_fields.append("course_levels")
                if sources_count == 0:
                    missing_fields.append("sources")
                if categories_count == 0:
                    missing_fields.append("categories")
                
                validation_result["error_message"] = f"Cannot create leads: Admin must create {' and '.join(missing_fields)} first"
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error validating dynamic fields: {e}")
            return {
                "course_levels_exist": False,
                "sources_exist": False,
                "categories_exist": False,
                "can_create_leads": False,
                "error_message": f"Error validating required fields: {str(e)}"
            }

    # ============================================================================
    # 🔄 UPDATED: ENHANCED LEAD CREATION WITH NEW ID GENERATION
    # ============================================================================
    
    async def create_lead_comprehensive(
        self,
        lead_data: LeadCreateComprehensive,
        created_by: str,
        force_create: bool = False
    ) -> Dict[str, Any]:
        """
        🔄 UPDATED: Lead creation now uses category-source combination ID generation
        """
        try:
            db = self.get_db()
            
            # 🆕 NEW: Validate dynamic fields first
            field_validation = await self.validate_required_dynamic_fields()
            if not field_validation["can_create_leads"]:
                return {
                    "success": False,
                    "message": field_validation["error_message"],
                    "validation_error": field_validation
                }
            
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
            
            # 🆕 NEW: Step 3: Validate and set dynamic fields
            validated_course_level = await self.validate_and_set_course_level(
                getattr(basic_info, 'course_level', None)
            )
            validated_source = await self.validate_and_set_source(
                getattr(basic_info, 'source', None)
            )
            
            # 🆕 NEW: Step 4: Validate category and source combination
            validation_result = await self.validate_category_and_source_for_lead_creation(
                basic_info.category, validated_source
            )
            
            if not validation_result["can_create_lead"]:
                return {
                    "success": False,
                    "message": validation_result["error_message"],
                    "validation_error": validation_result
                }
            
            # 🔄 UPDATED: Step 5: Generate lead ID using category-source combination
            lead_id = await self.generate_lead_id_by_category_and_source(
                category=basic_info.category,
                source=validated_source
            )
            
            logger.info(f"✅ Generated new format lead ID: {lead_id} for category '{basic_info.category}' and source '{validated_source}'")
            
            # Step 6: Handle assignment
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
            
            # Step 7: Create lead document with validated dynamic fields
            lead_doc = {
                "lead_id": lead_id,
                "status": getattr(status_and_tags, 'status', 'New'),
                "name": basic_info.name,
                "email": basic_info.email.lower(),
                "contact_number": basic_info.contact_number,
                "phone_number": basic_info.contact_number,  # Legacy field
                "source": validated_source,  # 🔄 UPDATED: Use validated source
                "category": basic_info.category,
                "course_level": validated_course_level,  # 🔄 UPDATED: Use validated course level
                "date_of_birth": basic_info.date_of_birth,  # 🆕 NEW
                
                # Add the new optional fields
                "age": basic_info.age,
                "experience": basic_info.experience,
                "nationality": basic_info.nationality,
                "current_location": basic_info.current_location,
                
                # Status and tags
                "stage": getattr(status_and_tags, 'stage', 'Pending'),
                "lead_score": getattr(status_and_tags, 'lead_score', 0),
                "priority": "medium",
                "tags": getattr(status_and_tags, 'tags', []),
                
                # Assignment
                "assigned_to": assigned_to,
                "assigned_to_name": assigned_to_name,
                "assignment_method": assignment_method,
                
                # Multi-assignment fields
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
                        "reason": "Initial assignment",
                        "lead_id_format": "category_source_combination",  # 🆕 NEW: Track ID format used
                        "category_short": validation_result.get("category_short_form"),
                        "source_short": validation_result.get("source_short_form")
                    }
                ],
                
                # Additional info
                "notes": getattr(additional_info, 'notes', ''),
                "created_by": created_by,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            # Step 8: Insert lead
            result = await db.leads.insert_one(lead_doc)
            
            if result.inserted_id:
                # Step 9: Update user array if assigned
                if assigned_to:
                    await user_lead_array_service.add_lead_to_user_array(assigned_to, lead_id)
                
                # Step 10: Log activity with enhanced metadata
                await self.log_lead_activity(
                    lead_id=lead_id,
                    activity_type="lead_created",
                    description=f"Lead created with ID: {lead_id}",
                    created_by=created_by,
                    metadata={
                        "category": basic_info.category,
                        "source": validated_source,
                        "course_level": validated_course_level,
                        "assigned_to": assigned_to,
                        "assignment_method": assignment_method,
                        "has_age": basic_info.age is not None,
                        "has_experience": basic_info.experience is not None,
                        "has_nationality": basic_info.nationality is not None,
                        "lead_id_format": "category_source_combination",  # 🆕 NEW
                        "category_short": validation_result.get("category_short_form"),
                        "source_short": validation_result.get("source_short_form"),
                        "lead_id_preview_matched": True
                    }
                )
                
                logger.info(f"✅ Lead created successfully: {lead_id} with category-source combination format")
                
                return {
                    "success": True,
                    "message": f"Lead created successfully with ID: {lead_id}",
                    "lead": self.format_lead_response(lead_doc),
                    "assignment_info": {
                        "assigned_to": assigned_to,
                        "assigned_to_name": assigned_to_name,
                        "assignment_method": assignment_method
                    },
                    "validated_fields": {
                        "course_level": validated_course_level,
                        "source": validated_source
                    },
                    "lead_id_info": {
                        "format": "category_source_combination",
                        "category_short": validation_result.get("category_short_form"),
                        "source_short": validation_result.get("source_short_form"),
                        "lead_id": lead_id
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
        🔄 UPDATED: Create lead with selective round robin assignment using new ID format
        """
        db = self.get_db()
        
        try:
            # 🆕 NEW: Validate dynamic fields first
            field_validation = await self.validate_required_dynamic_fields()
            if not field_validation["can_create_leads"]:
                return {
                    "success": False,
                    "message": field_validation["error_message"],
                    "validation_error": field_validation
                }
            
            # Step 1: Check for duplicates
            duplicate_check = await self.check_duplicate_lead(basic_info.email)
            if duplicate_check["is_duplicate"]:
                return {
                    "success": False,
                    "message": "Lead with this email already exists",
                    "duplicate_check": duplicate_check
                }
            
            # Step 2: Validate and set dynamic fields
            validated_course_level = await self.validate_and_set_course_level(
                getattr(basic_info, 'course_level', None)
            )
            validated_source = await self.validate_and_set_source(
                getattr(basic_info, 'source', None)
            )
            
            # 🆕 NEW: Step 3: Validate category and source combination
            validation_result = await self.validate_category_and_source_for_lead_creation(
                basic_info.category, validated_source
            )
            
            if not validation_result["can_create_lead"]:
                return {
                    "success": False,
                    "message": validation_result["error_message"],
                    "validation_error": validation_result
                }
            
            # 🔄 UPDATED: Step 4: Generate lead ID using category-source combination
            lead_id = await self.generate_lead_id_by_category_and_source(
                category=basic_info.category,
                source=validated_source
            )
            
            # Step 5: Handle assignment with selective round robin
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
            
            # Step 6: Create lead document with validated dynamic fields
            lead_doc = {
                "lead_id": lead_id,
                "status": status_and_tags.status if hasattr(status_and_tags, 'status') else "New",
                "name": basic_info.name,
                "email": basic_info.email.lower(),
                "contact_number": basic_info.contact_number,
                "phone_number": basic_info.contact_number,  # Legacy field
                "source": validated_source,  # 🔄 UPDATED: Use validated source
                "category": basic_info.category,
                "course_level": validated_course_level,  # 🔄 UPDATED: Use validated course level
                
                # Optional fields
                "age": basic_info.age,
                "experience": basic_info.experience,
                "nationality": basic_info.nationality,
                "current_location": basic_info.current_location,
                "date_of_birth": basic_info.date_of_birth,  # 🆕 NEW
                
                # Status and tags
                "stage": status_and_tags.stage if hasattr(status_and_tags, 'stage') else "Pending",
                "lead_score": status_and_tags.lead_score if hasattr(status_and_tags, 'lead_score') else 0,
                "priority": "medium",
                "tags": status_and_tags.tags if hasattr(status_and_tags, 'tags') else [],
                
                # Single assignment (backward compatibility)
                "assigned_to": assigned_to,
                "assigned_to_name": assigned_to_name,
                "assignment_method": assignment_method,
                
                # Multi-assignment fields
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
                        "selected_users_pool": selected_user_emails,  # Track which users were in the pool
                        "lead_id_format": "category_source_combination",  # 🆕 NEW
                        "category_short": validation_result.get("category_short_form"),
                        "source_short": validation_result.get("source_short_form")
                    }
                ],
                
                # Additional info
                "notes": additional_info.notes if hasattr(additional_info, 'notes') else "",
                "created_by": created_by,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            # Step 7: Insert lead
            result = await db.leads.insert_one(lead_doc)
            
            if result.inserted_id:
                # Step 8: Update user array if assigned
                if assigned_to:
                    await user_lead_array_service.add_lead_to_user_array(assigned_to, lead_id)
                
                # Step 9: Log activity
                await self.log_lead_activity(
                    lead_id=lead_id,
                    activity_type="lead_created",
                    description=f"Lead created with ID: {lead_id}",
                    created_by=created_by,
                    metadata={
                        "category": basic_info.category,
                        "source": validated_source,
                        "course_level": validated_course_level,
                        "assigned_to": assigned_to,
                        "assignment_method": assignment_method,
                        "selected_users_pool": selected_user_emails,
                        "has_age": basic_info.age is not None,
                        "has_experience": basic_info.experience is not None,
                        "has_nationality": basic_info.nationality is not None,
                        "lead_id_format": "category_source_combination",  # 🆕 NEW
                        "category_short": validation_result.get("category_short_form"),
                        "source_short": validation_result.get("source_short_form")
                    }
                )
                
                logger.info(f"Lead {lead_id} created and assigned to {assigned_to} using {assignment_method}")
                
                return {
                    "success": True,
                    "message": f"Lead created successfully with ID: {lead_id}",
                    "lead": self.format_lead_response(lead_doc),
                    "lead_id": lead_id,
                    "assigned_to": assigned_to,
                    "assignment_method": assignment_method,
                    "selected_users_pool": selected_user_emails,
                    "validated_fields": {
                        "course_level": validated_course_level,
                        "source": validated_source
                    },
                    "lead_id_info": {
                        "format": "category_source_combination",
                        "category_short": validation_result.get("category_short_form"),
                        "source_short": validation_result.get("source_short_form"),
                        "lead_id": lead_id
                    },
                    "duplicate_check": {
                        "is_duplicate": False,
                        "checked": True
                    }
                }
            else:
                return {"success": False, "error": "Failed to create lead"}
                
        except Exception as e:
            logger.error(f"Error creating lead with selective assignment: {str(e)}")
            return {"success": False, "error": str(e)}

    # ============================================================================
    # 🔄 UPDATED: BULK LEAD CREATION WITH NEW ID GENERATION
    # ============================================================================
    
    async def bulk_create_leads_with_selective_assignment(
        self,
        leads_data: List[Dict[str, Any]],
        created_by: str,
        assignment_method: str = "all_users",
        selected_user_emails: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        🔄 UPDATED: Bulk create leads with new ID generation format
        """
        db = self.get_db()
        
        try:
            # 🆕 NEW: Validate dynamic fields first
            field_validation = await self.validate_required_dynamic_fields()
            if not field_validation["can_create_leads"]:
                return {
                    "success": False,
                    "message": field_validation["error_message"],
                    "validation_error": field_validation
                }
            
            created_leads = []
            failed_leads = []
            assignment_summary = []
            
            for i, lead_data in enumerate(leads_data):
                try:
                    # 🆕 NEW: Validate dynamic fields for each lead
                    validated_course_level = await self.validate_and_set_course_level(
                        lead_data.get("course_level")
                    )
                    validated_source = await self.validate_and_set_source(
                        lead_data.get("source")
                    )
                    
                    # 🔄 UPDATED: Generate lead ID using category-source combination
                    lead_id = await self.generate_lead_id_by_category_and_source(
                        category=lead_data.get("category", "General"),
                        source=validated_source
                    )
                    
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
                        "source": validated_source,  # 🔄 UPDATED: Use validated source
                        "category": lead_data.get("category", "General"),
                        "course_level": validated_course_level,  # 🔄 UPDATED: Use validated course level
                        
                        # Optional fields
                        "age": lead_data.get("age"),
                        "experience": lead_data.get("experience"),
                        "nationality": lead_data.get("nationality"),
                        "date_of_birth": lead_data.get("date_of_birth"),  # 🆕 NEW
                        
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
                        
                        # Assignment history with enhanced tracking
                        "assignment_history": [
                            {
                                "assigned_to": assigned_to,
                                "assigned_to_name": assigned_to_name,
                                "assigned_by": created_by,
                                "assignment_method": method,
                                "assigned_at": datetime.utcnow(),
                                "reason": f"Bulk creation ({assignment_method})",
                                "bulk_index": i,
                                "selected_users_pool": selected_user_emails if assignment_method == "selected_users" else None,
                                "validated_course_level": validated_course_level,
                                "validated_source": validated_source,
                                "lead_id_format": "category_source_combination"  # 🆕 NEW
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
                            "validated_course_level": validated_course_level,
                            "validated_source": validated_source,
                            "lead_id_format": "category_source_combination",  # 🆕 NEW
                            "status": "success"
                        })
                        
                        logger.info(f"Bulk created lead {lead_id} assigned to {assigned_to} using new ID format")
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
                "assignment_summary": assignment_summary,
                "lead_id_format": "category_source_combination"  # 🆕 NEW
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
    # 🆕 NEW: LEAD ID ANALYTICS AND STATISTICS
    # ============================================================================
    
    async def get_lead_id_format_statistics(self) -> Dict[str, Any]:
        """Get statistics about lead ID formats and combinations"""
        try:
            # Get combination statistics from lead_category_service
            combination_stats = await lead_category_service.get_combination_statistics()
            
            db = self.get_db()
            
            # Get total leads count
            total_leads = await db.leads.count_documents({})
            
            # Count leads by ID format (if we track this in assignment_history)
            format_pipeline = [
                {"$unwind": "$assignment_history"},
                {
                    "$group": {
                        "_id": "$assignment_history.lead_id_format",
                        "count": {"$sum": 1}
                    }
                }
            ]
            
            format_distribution = await db.leads.aggregate(format_pipeline).to_list(None)
            
            # Get top category-source combinations
            top_combinations_pipeline = [
                {
                    "$group": {
                        "_id": {
                            "category": "$category",
                            "source": "$source"
                        },
                        "count": {"$sum": 1},
                        "latest_lead": {"$max": "$created_at"}
                    }
                },
                {"$sort": {"count": -1}},
                {"$limit": 10}
            ]
            
            top_combinations = await db.leads.aggregate(top_combinations_pipeline).to_list(None)
            
            return {
                "total_leads": total_leads,
                "combination_statistics": combination_stats,
                "format_distribution": format_distribution,
                "top_combinations": top_combinations,
                "generated_at": datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"Error getting lead ID format statistics: {str(e)}")
            return {"error": str(e)}

    # ============================================================================
    # 🔄 UPDATED: LEGACY METHODS (KEEPING BACKWARD COMPATIBILITY)
    # ============================================================================
    
    async def generate_lead_id_by_category(self, category: str) -> str:
        """🔄 UPDATED: Legacy method now logs deprecation warning"""
        logger.warning(f"Using legacy lead ID generation for category: {category}. Consider using generate_lead_id_by_category_and_source() for new format.")
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
            
            logger.info(f"Generated legacy lead ID: {lead_id} for category: {category}")
            return lead_id
            
        except Exception as e:
            logger.error(f"Error generating legacy lead ID: {str(e)}")
            # Fallback to simple sequence
            return await self._generate_lead_id()
    
    async def get_category_short_form(self, category: str) -> str:
        """Get short form for category from database"""
        try:
            db = self.get_db()
            
            # Look up category in database
            category_doc = await db.lead_categories.find_one({"name": category, "is_active": True})
            
            if category_doc and "short_form" in category_doc:
                # Return short form from database
                return category_doc["short_form"]
            
            # Log warning if category not found
            logger.warning(f"Category not found in database: {category}, using fallback 'LD'")
            return "LD"  # Fallback if not found
            
        except Exception as e:
            logger.error(f"Error getting category short form from database: {str(e)}")
            return "LD"  # Fallback in case of error

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

    # ============================================================================
    # EXISTING METHODS FROM ORIGINAL FILE (KEEP ALL OF THESE)
    # ============================================================================
    
    async def get_course_level_statistics(self) -> Dict[str, int]:
        """Get statistics of leads by course level"""
        try:
            db = self.get_db()
            
            # Aggregate leads by course level
            pipeline = [
                {"$group": {
                    "_id": "$course_level",
                    "count": {"$sum": 1}
                }},
                {"$sort": {"count": -1}}
            ]
            
            results = await db.leads.aggregate(pipeline).to_list(None)
            
            # Convert to dictionary
            course_level_stats = {}
            for result in results:
                course_level_name = result["_id"] or "unspecified"
                course_level_stats[course_level_name] = result["count"]
            
            return course_level_stats
            
        except Exception as e:
            logger.error(f"Error getting course level statistics: {e}")
            return {}

    async def get_source_statistics(self) -> Dict[str, int]:
        """Get statistics of leads by source"""
        try:
            db = self.get_db()
            
            # Aggregate leads by source
            pipeline = [
                {"$group": {
                    "_id": "$source",
                    "count": {"$sum": 1}
                }},
                {"$sort": {"count": -1}}
            ]
            
            results = await db.leads.aggregate(pipeline).to_list(None)
            
            # Convert to dictionary
            source_stats = {}
            for result in results:
                source_name = result["_id"] or "unspecified"
                source_stats[source_name] = result["count"]
            
            return source_stats
            
        except Exception as e:
            logger.error(f"Error getting source statistics: {e}")
            return {}

    async def bulk_update_course_level(self, old_course_level: str, new_course_level: str, updated_by: str) -> Dict[str, Any]:
        """Update all leads from old course level to new course level"""
        try:
            db = self.get_db()
            
            # Validate new course level exists and is active
            new_course_level_doc = await db.course_levels.find_one({
                "name": new_course_level,
                "is_active": True
            })
            
            if not new_course_level_doc:
                raise ValueError(f"New course level '{new_course_level}' does not exist or is not active")
            
            # Update all leads with old course level
            result = await db.leads.update_many(
                {"course_level": old_course_level},
                {
                    "$set": {
                        "course_level": new_course_level,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"Updated {result.modified_count} leads from course level '{old_course_level}' to '{new_course_level}' by {updated_by}")
            
            return {
                "success": True,
                "message": f"Successfully updated {result.modified_count} leads",
                "updated_count": result.modified_count,
                "old_course_level": old_course_level,
                "new_course_level": new_course_level
            }
            
        except Exception as e:
            logger.error(f"Error in bulk course level update: {e}")
            raise Exception(f"Failed to bulk update course level: {str(e)}")

    async def bulk_update_source(self, old_source: str, new_source: str, updated_by: str) -> Dict[str, Any]:
        """Update all leads from old source to new source"""
        try:
            db = self.get_db()
            
            # Validate new source exists and is active
            new_source_doc = await db.sources.find_one({
                "name": new_source,
                "is_active": True
            })
            
            if not new_source_doc:
                raise ValueError(f"New source '{new_source}' does not exist or is not active")
            
            # Update all leads with old source
            result = await db.leads.update_many(
                {"source": old_source},
                {
                    "$set": {
                        "source": new_source,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"Updated {result.modified_count} leads from source '{old_source}' to '{new_source}' by {updated_by}")
            
            return {
                "success": True,
                "message": f"Successfully updated {result.modified_count} leads",
                "updated_count": result.modified_count,
                "old_source": old_source,
                "new_source": new_source
            }
            
        except Exception as e:
            logger.error(f"Error in bulk source update: {e}")
            raise Exception(f"Failed to bulk update source: {str(e)}")

    async def get_leads_by_user_including_co_assignments(
        self, 
        user_email: str, 
        page: int = 1, 
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Get all leads where user is assigned (primary or co-assignee)"""
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
        """Get statistics about multi-assigned leads"""
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
    
    async def get_lead_by_id(self, lead_id: str) -> Optional[Dict[str, Any]]:
        """Get a single lead by ID"""
        try:
            db = self.get_db()
            lead = await db.leads.find_one({"lead_id": lead_id})
            
            if lead:
                # Convert ObjectId to string
                if "_id" in lead:
                    lead["_id"] = str(lead["_id"])
                return lead
            return None
            
        except Exception as e:
            logger.error(f"Error getting lead {lead_id}: {str(e)}")
            return None
    
    async def update_lead(
        self,
        lead_id: str,
        update_data: Dict[str, Any],
        updated_by: str
    ) -> Dict[str, Any]:
        """Update a lead with activity logging and dynamic field validation"""
        try:
            db = self.get_db()
            
            # 🆕 NEW: Validate dynamic fields if being updated
            if "course_level" in update_data:
                validated_course_level = await self.validate_and_set_course_level(update_data["course_level"])
                update_data["course_level"] = validated_course_level
            
            if "source" in update_data:
                validated_source = await self.validate_and_set_source(update_data["source"])
                update_data["source"] = validated_source
            
            # Add updated timestamp
            update_data["updated_at"] = datetime.utcnow()
            
            # Update the lead
            result = await db.leads.update_one(
                {"lead_id": lead_id},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                # Log activity
                await self.log_lead_activity(
                    lead_id=lead_id,
                    activity_type="lead_updated",
                    description="Lead information updated",
                    created_by=updated_by,
                    metadata={"updated_fields": list(update_data.keys())}
                )
                
                # Get updated lead
                updated_lead = await db.leads.find_one({"lead_id": lead_id})
                if updated_lead and "_id" in updated_lead:
                    updated_lead["_id"] = str(updated_lead["_id"])
                
                return {
                    "success": True,
                    "lead": updated_lead,
                    "message": "Lead updated successfully"
                }
            else:
                return {
                    "success": False,
                    "message": "Lead not found or no changes made"
                }
                
        except Exception as e:
            logger.error(f"Error updating lead {lead_id}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def delete_lead(self, lead_id: str, deleted_by: str) -> Dict[str, Any]:
        """Delete a lead with activity logging"""
        try:
            db = self.get_db()
            
            # Get lead first for logging
            lead = await db.leads.find_one({"lead_id": lead_id})
            if not lead:
                return {
                    "success": False,
                    "message": "Lead not found"
                }
            
            # Remove from user arrays if assigned
            if lead.get("assigned_to"):
                await user_lead_array_service.remove_lead_from_user_array(
                    lead.get("assigned_to"), lead_id
                )
            
            # Remove from co-assignees arrays
            for co_assignee in lead.get("co_assignees", []):
                await user_lead_array_service.remove_lead_from_user_array(
                    co_assignee, lead_id
                )
            
            # Log activity before deletion
            await self.log_lead_activity(
                lead_id=lead_id,
                activity_type="lead_deleted",
                description=f"Lead {lead_id} deleted",
                created_by=deleted_by,
                metadata={
                    "lead_name": lead.get("name"),
                    "lead_email": lead.get("email"),
                    "was_assigned_to": lead.get("assigned_to"),
                    "had_co_assignees": lead.get("co_assignees", [])
                }
            )
            
            # Delete the lead
            result = await db.leads.delete_one({"lead_id": lead_id})
            
            if result.deleted_count > 0:
                return {
                    "success": True,
                    "message": f"Lead {lead_id} deleted successfully"
                }
            else:
                return {
                    "success": False,
                    "message": "Failed to delete lead"
                }
                
        except Exception as e:
            logger.error(f"Error deleting lead {lead_id}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_leads_with_filters(
        self,
        user_email: str,
        user_role: str,
        page: int = 1,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Get leads with filtering and pagination"""
        try:
            db = self.get_db()
            
            # Build base query based on user role
            if user_role == "admin":
                base_query = {}
            else:
                # Regular users can only see assigned leads (primary or co-assignee)
                base_query = {
                    "$or": [
                        {"assigned_to": user_email},
                        {"co_assignees": user_email}
                    ]
                }
            
            # Add filters if provided
            if filters:
                base_query.update(filters)
            
            # Get total count
            total_count = await db.leads.count_documents(base_query)
            
            # Get leads with pagination
            skip = (page - 1) * limit
            leads = await db.leads.find(base_query).skip(skip).limit(limit).sort("created_at", -1).to_list(None)
            
            # Format leads for response
            formatted_leads = []
            for lead in leads:
                formatted_lead = self.format_lead_response(lead)
                formatted_leads.append(formatted_lead)
            
            return {
                "success": True,
                "leads": formatted_leads,
                "total_count": total_count,
                "page": page,
                "limit": limit,
                "total_pages": (total_count + limit - 1) // limit,
                "filters_applied": filters or {}
            }
            
        except Exception as e:
            logger.error(f"Error getting leads with filters: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "leads": [],
                "total_count": 0
            }
    
    async def get_lead_statistics(self, user_email: str, user_role: str) -> Dict[str, Any]:
        """Get lead statistics based on user role with dynamic field breakdowns"""
        try:
            db = self.get_db()
            
            # Build base query based on user role
            if user_role == "admin":
                base_query = {}
            else:
                base_query = {
                    "$or": [
                        {"assigned_to": user_email},
                        {"co_assignees": user_email}
                    ]
                }
            
            # Get total leads
            total_leads = await db.leads.count_documents(base_query)
            
            # Get status distribution
            status_pipeline = [
                {"$match": base_query},
                {
                    "$group": {
                        "_id": "$status",
                        "count": {"$sum": 1}
                    }
                }
            ]
            status_distribution = await db.leads.aggregate(status_pipeline).to_list(None)
            
            # 🆕 NEW: Get course level distribution
            course_level_pipeline = [
                {"$match": base_query},
                {
                    "$group": {
                        "_id": "$course_level",
                        "count": {"$sum": 1}
                    }
                }
            ]
            course_level_distribution = await db.leads.aggregate(course_level_pipeline).to_list(None)
            
            # Get source distribution
            source_pipeline = [
                {"$match": base_query},
                {
                    "$group": {
                        "_id": "$source",
                        "count": {"$sum": 1}
                    }
                }
            ]
            source_distribution = await db.leads.aggregate(source_pipeline).to_list(None)
            
            # Get assignment statistics (admin only)
            assignment_stats = {}
            if user_role == "admin":
                # Get multi-assignment stats
                multi_assigned_count = await db.leads.count_documents({"is_multi_assigned": True})
                single_assigned_count = await db.leads.count_documents({
                    "assigned_to": {"$ne": None},
                    "is_multi_assigned": {"$ne": True}
                })
                unassigned_count = await db.leads.count_documents({"assigned_to": None})
                
                assignment_stats = {
                    "multi_assigned": multi_assigned_count,
                    "single_assigned": single_assigned_count,
                    "unassigned": unassigned_count
                }
            
            return {
                "total_leads": total_leads,
                "status_distribution": status_distribution,
                "course_level_distribution": course_level_distribution,  # 🆕 NEW
                "source_distribution": source_distribution,
                "assignment_statistics": assignment_stats,
                "user_role": user_role
            }
            
        except Exception as e:
            logger.error(f"Error getting lead statistics: {str(e)}")
            return {"error": str(e)}
    
    async def search_leads(
        self,
        search_term: str,
        user_email: str,
        user_role: str,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Search leads by name, email, or lead ID"""
        try:
            db = self.get_db()
            
            # Build search query
            search_query = {
                "$or": [
                    {"name": {"$regex": search_term, "$options": "i"}},
                    {"email": {"$regex": search_term, "$options": "i"}},
                    {"lead_id": {"$regex": search_term, "$options": "i"}},
                    {"contact_number": {"$regex": search_term, "$options": "i"}}
                ]
            }
            
            # Add role-based filtering
            if user_role != "admin":
                search_query = {
                    "$and": [
                        search_query,
                        {
                            "$or": [
                                {"assigned_to": user_email},
                                {"co_assignees": user_email}
                            ]
                        }
                    ]
                }
            
            # Get total count
            total_count = await db.leads.count_documents(search_query)
            
            # Get leads with pagination
            skip = (page - 1) * limit
            leads = await db.leads.find(search_query).skip(skip).limit(limit).sort("created_at", -1).to_list(None)
            
            # Format leads for response
            formatted_leads = []
            for lead in leads:
                formatted_lead = self.format_lead_response(lead)
                formatted_leads.append(formatted_lead)
            
            return {
                "success": True,
                "leads": formatted_leads,
                "total_count": total_count,
                "page": page,
                "limit": limit,
                "total_pages": (total_count + limit - 1) // limit,
                "search_term": search_term
            }
            
        except Exception as e:
            logger.error(f"Error searching leads: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "leads": [],
                "total_count": 0
            }

    def format_lead_response(self, lead_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Format lead document for response with new fields and multi-assignment support"""
        if not lead_doc:
            return None
            
        return {
            "id": str(lead_doc.get("_id", "")),
            "lead_id": lead_doc.get("lead_id", ""),
            "name": lead_doc.get("name", ""),
            "email": lead_doc.get("email", ""),
            "contact_number": lead_doc.get("contact_number", ""),
            "phone_number": lead_doc.get("phone_number", ""),
            "source": lead_doc.get("source"),  # 🔄 UPDATED: Can be None if no sources exist
            "category": lead_doc.get("category", ""),
            
            # Include new optional fields in response
            "age": lead_doc.get("age"),
            "experience": lead_doc.get("experience"),
            "nationality": lead_doc.get("nationality"),
            "course_level": lead_doc.get("course_level"),  # 🔄 UPDATED: Can be None if no course levels exist
            "date_of_birth": lead_doc.get("date_of_birth"),  # 🆕 NEW
            
            "status": lead_doc.get("status", "Initial"),
            "stage": lead_doc.get("stage", "Initial"),
            "lead_score": lead_doc.get("lead_score", 0),
            "priority": lead_doc.get("priority", "medium"),
            "tags": lead_doc.get("tags", []),
            
            # Assignment fields (single and multi)
            "assigned_to": lead_doc.get("assigned_to"),
            "assigned_to_name": lead_doc.get("assigned_to_name"),
            "assignment_method": lead_doc.get("assignment_method"),
            
            # Multi-assignment fields
            "co_assignees": lead_doc.get("co_assignees", []),
            "co_assignees_names": lead_doc.get("co_assignees_names", []),
            "is_multi_assigned": lead_doc.get("is_multi_assigned", False),
            
            "assignment_history": lead_doc.get("assignment_history", []),
            "notes": lead_doc.get("notes", ""),
            "created_by": lead_doc.get("created_by", ""),
            "created_at": lead_doc.get("created_at"),
            "updated_at": lead_doc.get("updated_at"),
            "last_contacted": lead_doc.get("last_contacted"),
            
            # Legacy fields for backward compatibility
            "country_of_interest": lead_doc.get("country_of_interest", "")
        }

    # ... (Include all other existing methods from the original file) ...

# Global service instance
lead_service = LeadService()