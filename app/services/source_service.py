# app/services/source_service.py - UPDATED - SOURCE BUSINESS LOGIC WITH SHORT FORM SUPPORT

from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
import logging

from ..config.database import get_database
from ..models.source import SourceCreate, SourceUpdate, SourceResponse, SourceHelper

logger = logging.getLogger(__name__)

class SourceService:
    """Service class for source management operations"""
    
    async def create_source(self, source_data: SourceCreate, created_by: str) -> Dict[str, Any]:
        """Create a new source with short form validation"""
        try:
            db = get_database()
            
            # Validate unique name
            is_unique_name = await SourceHelper.validate_source_name(source_data.name)
            if not is_unique_name:
                raise ValueError(f"Source with name '{source_data.name}' already exists")
            
            # Validate unique short form
            is_unique_short_form = await SourceHelper.validate_source_short_form(source_data.short_form)
            if not is_unique_short_form:
                raise ValueError(f"Source with short form '{source_data.short_form}' already exists")
            
            # If this is set as default, unset other defaults
            if source_data.is_default:
                await db.sources.update_many(
                    {"is_default": True},
                    {"$set": {"is_default": False}}
                )
            
            # Create source document
            source_doc = {
                **source_data.dict(),
                "created_by": created_by,
                "created_at": datetime.utcnow(),
                "updated_at": None
            }
            
            result = await db.sources.insert_one(source_doc)
            
            # Get created source with ID
            created_source = await db.sources.find_one({"_id": result.inserted_id})
            created_source["id"] = str(created_source.pop("_id"))
            created_source["lead_count"] = 0  # New source has no leads
            
            logger.info(f"Source '{source_data.name}' with short form '{source_data.short_form}' created by {created_by}")
            
            return {
                "success": True,
                "message": f"Source '{source_data.name}' created successfully with short form '{source_data.short_form}'",
                "source": created_source
            }
            
        except ValueError as e:
            logger.error(f"Validation error creating source: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating source: {e}")
            raise Exception(f"Failed to create source: {str(e)}")
    
    async def get_source_short_form(self, source_name: str) -> str:
        """Get short form for a source by name - CRITICAL for lead ID generation"""
        try:
            db = get_database()
            
            source = await db.sources.find_one({"name": source_name, "is_active": True})
            
            if source and "short_form" in source:
                logger.info(f"Found short form '{source['short_form']}' for source '{source_name}'")
                return source["short_form"]
            
            # Log warning if source not found
            logger.warning(f"Source '{source_name}' not found in database, using fallback 'UN'")
            return "UN"  # Unknown source fallback
            
        except Exception as e:
            logger.error(f"Error getting source short form: {str(e)}")
            return "UN"  # Fallback in case of error
    
    async def validate_source_exists(self, source_name: str) -> bool:
        """Validate if source exists and is active"""
        try:
            db = get_database()
            
            source = await db.sources.find_one({"name": source_name, "is_active": True})
            return source is not None
            
        except Exception as e:
            logger.error(f"Error validating source existence: {str(e)}")
            return False
    
    async def get_all_sources(self, include_lead_count: bool = False, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all sources"""
        try:
            db = get_database()
            
            # Build query
            query = {}
            if active_only:
                query["is_active"] = True
            
            # Get sources
            sources = await db.sources.find(query).sort("sort_order", 1).to_list(None)
            
            # Add lead counts if requested
            if include_lead_count:
                for source in sources:
                    source["lead_count"] = await db.leads.count_documents({"source": source["name"]})
            else:
                for source in sources:
                    source["lead_count"] = 0
            
            # Convert ObjectId to string
            for source in sources:
                source["id"] = str(source.pop("_id"))
            
            return sources
            
        except Exception as e:
            logger.error(f"Error getting sources: {e}")
            raise Exception(f"Failed to get sources: {str(e)}")
    
    async def get_source_by_id(self, source_id: str) -> Dict[str, Any]:
        """Get a specific source by ID"""
        try:
            db = get_database()
            
            source = await db.sources.find_one({"_id": ObjectId(source_id)})
            if not source:
                raise ValueError(f"Source with ID {source_id} not found")
            
            # Add lead count
            source["lead_count"] = await db.leads.count_documents({"source": source["name"]})
            
            # Convert ObjectId to string
            source["id"] = str(source.pop("_id"))
            
            return source
            
        except ValueError as e:
            logger.error(f"Source not found: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting source: {e}")
            raise Exception(f"Failed to get source: {str(e)}")
    
    async def update_source(self, source_id: str, update_data: SourceUpdate, updated_by: str) -> Dict[str, Any]:
        """Update an existing source - Note: short_form cannot be updated"""
        try:
            db = get_database()
            
            # Check if source exists
            existing_source = await db.sources.find_one({"_id": ObjectId(source_id)})
            if not existing_source:
                raise ValueError(f"Source with ID {source_id} not found")
            
            # Prepare update data (short_form is excluded from SourceUpdate model)
            update_dict = {k: v for k, v in update_data.dict().items() if v is not None}
            
            if not update_dict:
                return {
                    "success": True,
                    "message": "No changes to update",
                    "source": existing_source
                }
            
            # If name is being updated, validate uniqueness
            if "name" in update_dict:
                is_unique = await SourceHelper.validate_source_name(
                    update_dict["name"], 
                    exclude_id=source_id
                )
                if not is_unique:
                    raise ValueError(f"Source with name '{update_dict['name']}' already exists")
            
            # If setting as default, unset other defaults
            if update_dict.get("is_default"):
                await db.sources.update_many(
                    {"is_default": True, "_id": {"$ne": ObjectId(source_id)}},
                    {"$set": {"is_default": False}}
                )
            
            # Add metadata
            update_dict["updated_at"] = datetime.utcnow()
            
            # Update source
            result = await db.sources.update_one(
                {"_id": ObjectId(source_id)},
                {"$set": update_dict}
            )
            
            if result.modified_count == 0:
                logger.warning(f"Source {source_id} update resulted in no changes")
            
            # Get updated source
            updated_source = await db.sources.find_one({"_id": ObjectId(source_id)})
            updated_source["id"] = str(updated_source.pop("_id"))
            updated_source["lead_count"] = await db.leads.count_documents({"source": updated_source["name"]})
            
            logger.info(f"Source {source_id} updated by {updated_by}")
            
            return {
                "success": True,
                "message": f"Source '{updated_source['name']}' updated successfully",
                "source": updated_source
            }
            
        except ValueError as e:
            logger.error(f"Validation error updating source: {e}")
            raise
        except Exception as e:
            logger.error(f"Error updating source: {e}")
            raise Exception(f"Failed to update source: {str(e)}")
    
    async def delete_source(self, source_id: str, deleted_by: str) -> Dict[str, Any]:
        """Delete a source (only if no leads are using it)"""
        try:
            db = get_database()
            
            # Check if source exists
            source = await db.sources.find_one({"_id": ObjectId(source_id)})
            if not source:
                raise ValueError(f"Source with ID {source_id} not found")
            
            # Check if any leads are using this source
            lead_count = await db.leads.count_documents({"source": source["name"]})
            if lead_count > 0:
                raise ValueError(f"Cannot delete source '{source['name']}' as {lead_count} leads are using it")
            
            # Check if this is the default source
            if source.get("is_default"):
                raise ValueError("Cannot delete the default source")
            
            # Delete source
            result = await db.sources.delete_one({"_id": ObjectId(source_id)})
            
            if result.deleted_count == 0:
                raise ValueError(f"Failed to delete source {source_id}")
            
            logger.info(f"Source '{source['name']}' (short form: {source.get('short_form', 'N/A')}) deleted by {deleted_by}")
            
            return {
                "success": True,
                "message": f"Source '{source['name']}' deleted successfully"
            }
            
        except ValueError as e:
            logger.error(f"Validation error deleting source: {e}")
            raise
        except Exception as e:
            logger.error(f"Error deleting source: {e}")
            raise Exception(f"Failed to delete source: {str(e)}")
    
    async def get_source_suggestions(self, partial_name: str = "") -> List[Dict[str, str]]:
        """Get source creation suggestions with auto-generated short forms"""
        try:
            # Common source suggestions with their logical short forms
            suggestions = [
                {"name": "website", "short_form": "WB", "display_name": "Website"},
                {"name": "social_media", "short_form": "SM", "display_name": "Social Media"},
                {"name": "referral", "short_form": "RF", "display_name": "Referral"},
                {"name": "email_campaign", "short_form": "EM", "display_name": "Email Campaign"},
                {"name": "cold_call", "short_form": "CC", "display_name": "Cold Call"},
                {"name": "walk_in", "short_form": "WI", "display_name": "Walk-in"},
                {"name": "advertisement", "short_form": "AD", "display_name": "Advertisement"},
                {"name": "events", "short_form": "EV", "display_name": "Events"},
                {"name": "partnership", "short_form": "PT", "display_name": "Partnership"},
            ]
            
            # Filter by partial name if provided
            if partial_name:
                suggestions = [s for s in suggestions if partial_name.lower() in s["name"]]
            
            # Check if short forms are already taken
            db = get_database()
            for suggestion in suggestions:
                existing = await db.sources.find_one({"short_form": suggestion["short_form"]})
                if existing:
                    suggestion["short_form"] = f"{suggestion['short_form']}1"  # Add number if taken
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting source suggestions: {str(e)}")
            return []

# Create service instance
source_service = SourceService()