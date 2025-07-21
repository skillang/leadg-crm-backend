# app/services/course_level_service.py - NEW FILE FOR COURSE LEVEL BUSINESS LOGIC

from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
import logging

from ..config.database import get_database
from ..models.course_level import CourseLevelCreate, CourseLevelUpdate, CourseLevelResponse, CourseLevelHelper

logger = logging.getLogger(__name__)

class CourseLevelService:
    """Service class for course level management operations"""
    
    async def create_course_level(self, course_level_data: CourseLevelCreate, created_by: str) -> Dict[str, Any]:
        """Create a new course level"""
        try:
            db = get_database()
            
            # Validate unique name
            is_unique = await CourseLevelHelper.validate_course_level_name(course_level_data.name)
            if not is_unique:
                raise ValueError(f"Course level with name '{course_level_data.name}' already exists")
            
            # If this is set as default, unset other defaults
            if course_level_data.is_default:
                await db.course_levels.update_many(
                    {"is_default": True},
                    {"$set": {"is_default": False}}
                )
            
            # Create course level document
            course_level_doc = {
                **course_level_data.dict(),
                "created_by": created_by,
                "created_at": datetime.utcnow(),
                "updated_at": None
            }
            
            result = await db.course_levels.insert_one(course_level_doc)
            
            # Get created course level with ID
            created_course_level = await db.course_levels.find_one({"_id": result.inserted_id})
            created_course_level["id"] = str(created_course_level.pop("_id"))
            created_course_level["lead_count"] = 0  # New course level has no leads
            
            logger.info(f"Course level '{course_level_data.name}' created by {created_by}")
            
            return {
                "success": True,
                "message": f"Course level '{course_level_data.name}' created successfully",
                "course_level": created_course_level
            }
            
        except ValueError as e:
            logger.error(f"Validation error creating course level: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating course level: {e}")
            raise Exception(f"Failed to create course level: {str(e)}")
    
    async def get_all_course_levels(self, include_lead_count: bool = False, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all course levels"""
        try:
            db = get_database()
            
            # Build query
            query = {}
            if active_only:
                query["is_active"] = True
            
            # Get course levels
            course_levels = await db.course_levels.find(query).sort("sort_order", 1).to_list(None)
            
            # Add lead counts if requested
            if include_lead_count:
                for course_level in course_levels:
                    course_level["lead_count"] = await db.leads.count_documents({"course_level": course_level["name"]})
            else:
                for course_level in course_levels:
                    course_level["lead_count"] = 0
            
            # Convert ObjectId to string
            for course_level in course_levels:
                course_level["id"] = str(course_level.pop("_id"))
            
            return course_levels
            
        except Exception as e:
            logger.error(f"Error getting course levels: {e}")
            raise Exception(f"Failed to get course levels: {str(e)}")
    
    async def get_course_level_by_id(self, course_level_id: str) -> Dict[str, Any]:
        """Get a specific course level by ID"""
        try:
            db = get_database()
            
            course_level = await db.course_levels.find_one({"_id": ObjectId(course_level_id)})
            if not course_level:
                raise ValueError(f"Course level with ID {course_level_id} not found")
            
            # Add lead count
            course_level["lead_count"] = await db.leads.count_documents({"course_level": course_level["name"]})
            
            # Convert ObjectId to string
            course_level["id"] = str(course_level.pop("_id"))
            
            return course_level
            
        except ValueError as e:
            logger.error(f"Course level not found: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting course level: {e}")
            raise Exception(f"Failed to get course level: {str(e)}")
    
    async def update_course_level(self, course_level_id: str, update_data: CourseLevelUpdate, updated_by: str) -> Dict[str, Any]:
        """Update an existing course level"""
        try:
            db = get_database()
            
            # Check if course level exists
            existing_course_level = await db.course_levels.find_one({"_id": ObjectId(course_level_id)})
            if not existing_course_level:
                raise ValueError(f"Course level with ID {course_level_id} not found")
            
            # Prepare update data
            update_dict = {k: v for k, v in update_data.dict().items() if v is not None}
            
            if not update_dict:
                return {
                    "success": True,
                    "message": "No changes to update",
                    "course_level": existing_course_level
                }
            
            # If name is being updated, validate uniqueness
            if "name" in update_dict:
                is_unique = await CourseLevelHelper.validate_course_level_name(
                    update_dict["name"], 
                    exclude_id=course_level_id
                )
                if not is_unique:
                    raise ValueError(f"Course level with name '{update_dict['name']}' already exists")
            
            # If setting as default, unset other defaults
            if update_dict.get("is_default"):
                await db.course_levels.update_many(
                    {"is_default": True, "_id": {"$ne": ObjectId(course_level_id)}},
                    {"$set": {"is_default": False}}
                )
            
            # Add metadata
            update_dict["updated_at"] = datetime.utcnow()
            
            # Update course level
            result = await db.course_levels.update_one(
                {"_id": ObjectId(course_level_id)},
                {"$set": update_dict}
            )
            
            if result.modified_count == 0:
                logger.warning(f"Course level {course_level_id} update resulted in no changes")
            
            # Get updated course level
            updated_course_level = await db.course_levels.find_one({"_id": ObjectId(course_level_id)})
            updated_course_level["id"] = str(updated_course_level.pop("_id"))
            updated_course_level["lead_count"] = await db.leads.count_documents({"course_level": updated_course_level["name"]})
            
            logger.info(f"Course level {course_level_id} updated by {updated_by}")
            
            return {
                "success": True,
                "message": f"Course level '{updated_course_level['name']}' updated successfully",
                "course_level": updated_course_level
            }
            
        except ValueError as e:
            logger.error(f"Validation error updating course level: {e}")
            raise
        except Exception as e:
            logger.error(f"Error updating course level: {e}")
            raise Exception(f"Failed to update course level: {str(e)}")
    
    async def delete_course_level(self, course_level_id: str, deleted_by: str) -> Dict[str, Any]:
        """Delete a course level (only if no leads are using it)"""
        try:
            db = get_database()
            
            # Check if course level exists
            course_level = await db.course_levels.find_one({"_id": ObjectId(course_level_id)})
            if not course_level:
                raise ValueError(f"Course level with ID {course_level_id} not found")
            
            # Check if any leads are using this course level
            lead_count = await db.leads.count_documents({"course_level": course_level["name"]})
            if lead_count > 0:
                raise ValueError(f"Cannot delete course level '{course_level['name']}' as {lead_count} leads are using it")
            
            # Check if this is the default course level
            if course_level.get("is_default"):
                raise ValueError("Cannot delete the default course level")
            
            # Delete course level
            result = await db.course_levels.delete_one({"_id": ObjectId(course_level_id)})
            
            if result.deleted_count == 0:
                raise ValueError(f"Failed to delete course level {course_level_id}")
            
            logger.info(f"Course level '{course_level['name']}' deleted by {deleted_by}")
            
            return {
                "success": True,
                "message": f"Course level '{course_level['name']}' deleted successfully"
            }
            
        except ValueError as e:
            logger.error(f"Validation error deleting course level: {e}")
            raise
        except Exception as e:
            logger.error(f"Error deleting course level: {e}")
            raise Exception(f"Failed to delete course level: {str(e)}")

# Create service instance
course_level_service = CourseLevelService()