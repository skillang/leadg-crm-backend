# app/services/stage_service.py - NEW FILE FOR STAGE BUSINESS LOGIC

from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
import logging

from ..config.database import get_database
from ..models.lead_stage import StageCreate, StageUpdate, StageResponse, StageHelper

logger = logging.getLogger(__name__)

class StageService:
    """Service class for stage management operations"""
    
    async def create_stage(self, stage_data: StageCreate, created_by: str) -> Dict[str, Any]:
        """Create a new stage"""
        try:
            db = get_database()
            
            # Validate unique name
            is_unique = await StageHelper.validate_stage_name(stage_data.name)
            if not is_unique:
                raise ValueError(f"Stage with name '{stage_data.name}' already exists")
            
            # If this is set as default, unset other defaults
            if stage_data.is_default:
                await db.lead_stages.update_many(
                    {"is_default": True},
                    {"$set": {"is_default": False}}
                )
            
            # Create stage document
            stage_doc = {
                **stage_data.dict(),
                "created_by": created_by,
                "created_at": datetime.utcnow(),
                "updated_at": None
            }
            
            result = await db.lead_stages.insert_one(stage_doc)
            
            # Get created stage with ID
            created_stage = await db.lead_stages.find_one({"_id": result.inserted_id})
            created_stage["id"] = str(created_stage.pop("_id"))
            created_stage["lead_count"] = 0  # New stage has no leads
            
            logger.info(f"Stage '{stage_data.name}' created by {created_by}")
            
            return {
                "success": True,
                "message": f"Stage '{stage_data.name}' created successfully",
                "stage": created_stage
            }
            
        except ValueError as e:
            logger.error(f"Validation error creating stage: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating stage: {e}")
            raise Exception(f"Failed to create stage: {str(e)}")
    
    async def get_all_stages(self, include_lead_count: bool = False, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all stages"""
        try:
            db = get_database()
            
            # Build query
            query = {}
            if active_only:
                query["is_active"] = True
            
            # Get stages
            stages = await db.lead_stages.find(query).sort("sort_order", 1).to_list(None)
            
            # Add lead counts if requested
            if include_lead_count:
                for stage in stages:
                    stage["lead_count"] = await db.leads.count_documents({"stage": stage["name"]})
            else:
                for stage in stages:
                    stage["lead_count"] = 0
            
            # Convert ObjectId to string
            for stage in stages:
                stage["id"] = str(stage.pop("_id"))
            
            return stages
            
        except Exception as e:
            logger.error(f"Error getting stages: {e}")
            raise Exception(f"Failed to get stages: {str(e)}")
    
    async def get_stage_by_id(self, stage_id: str) -> Dict[str, Any]:
        """Get a specific stage by ID"""
        try:
            db = get_database()
            
            stage = await db.lead_stages.find_one({"_id": ObjectId(stage_id)})
            if not stage:
                raise ValueError(f"Stage with ID {stage_id} not found")
            
            # Add lead count
            stage["lead_count"] = await db.leads.count_documents({"stage": stage["name"]})
            
            # Convert ObjectId to string
            stage["id"] = str(stage.pop("_id"))
            
            return stage
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error getting stage {stage_id}: {e}")
            raise Exception(f"Failed to get stage: {str(e)}")
    
    async def update_stage(self, stage_id: str, stage_data: StageUpdate, updated_by: str) -> Dict[str, Any]:
        """Update an existing stage"""
        try:
            db = get_database()
            
            # Check if stage exists
            existing_stage = await db.lead_stages.find_one({"_id": ObjectId(stage_id)})
            if not existing_stage:
                raise ValueError(f"Stage with ID {stage_id} not found")
            
            # Prepare update data
            update_data = {}
            for field, value in stage_data.dict(exclude_unset=True).items():
                if value is not None:
                    update_data[field] = value
            
            # If setting as default, unset other defaults
            if update_data.get("is_default"):
                await db.lead_stages.update_many(
                    {"_id": {"$ne": ObjectId(stage_id)}, "is_default": True},
                    {"$set": {"is_default": False}}
                )
            
            # Add updated timestamp
            update_data["updated_at"] = datetime.utcnow()
            
            # Update stage
            result = await db.lead_stages.update_one(
                {"_id": ObjectId(stage_id)},
                {"$set": update_data}
            )
            
            if result.modified_count == 0:
                raise ValueError("No changes were made to the stage")
            
            # Get updated stage
            updated_stage = await self.get_stage_by_id(stage_id)
            
            logger.info(f"Stage {stage_id} updated by {updated_by}")
            
            return {
                "success": True,
                "message": f"Stage '{updated_stage['name']}' updated successfully",
                "stage": updated_stage
            }
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error updating stage {stage_id}: {e}")
            raise Exception(f"Failed to update stage: {str(e)}")
    
    async def delete_stage(self, stage_id: str, deleted_by: str, force: bool = False) -> Dict[str, Any]:
        """Delete a stage (or deactivate if it has leads)"""
        try:
            db = get_database()
            
            # Check if stage exists
            stage = await db.lead_stages.find_one({"_id": ObjectId(stage_id)})
            if not stage:
                raise ValueError(f"Stage with ID {stage_id} not found")
            
            # Check if stage has leads
            lead_count = await db.leads.count_documents({"stage": stage["name"]})
            
            if lead_count > 0 and not force:
                # Don't delete, just deactivate
                await db.lead_stages.update_one(
                    {"_id": ObjectId(stage_id)},
                    {
                        "$set": {
                            "is_active": False,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                return {
                    "success": True,
                    "message": f"Stage '{stage['name']}' deactivated (has {lead_count} leads)",
                    "action": "deactivated",
                    "lead_count": lead_count
                }
            else:
                # Actually delete the stage
                await db.lead_stages.delete_one({"_id": ObjectId(stage_id)})
                
                logger.info(f"Stage '{stage['name']}' deleted by {deleted_by}")
                
                return {
                    "success": True,
                    "message": f"Stage '{stage['name']}' deleted successfully",
                    "action": "deleted",
                    "lead_count": lead_count
                }
                
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error deleting stage {stage_id}: {e}")
            raise Exception(f"Failed to delete stage: {str(e)}")
    
    async def reorder_stages(self, stage_orders: List[Dict[str, Any]], updated_by: str) -> Dict[str, Any]:
        """Reorder stages by updating sort_order"""
        try:
            db = get_database()
            
            updated_count = 0
            for item in stage_orders:
                stage_id = item["id"]
                new_order = item["sort_order"]
                
                result = await db.lead_stages.update_one(
                    {"_id": ObjectId(stage_id)},
                    {
                        "$set": {
                            "sort_order": new_order,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                if result.modified_count > 0:
                    updated_count += 1
            
            logger.info(f"Reordered {updated_count} stages by {updated_by}")
            
            return {
                "success": True,
                "message": f"Reordered {updated_count} stages successfully",
                "updated_count": updated_count
            }
            
        except Exception as e:
            logger.error(f"Error reordering stages: {e}")
            raise Exception(f"Failed to reorder stages: {str(e)}")

# Create service instance
stage_service = StageService()