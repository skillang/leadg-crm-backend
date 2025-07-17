# app/services/status_service.py - NEW FILE FOR STATUS BUSINESS LOGIC

from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
import logging

from ..config.database import get_database
from ..models.lead_status import StatusCreate, StatusUpdate, StatusResponse, StatusHelper

logger = logging.getLogger(__name__)

class StatusService:
    """Service class for status management operations"""
    
    async def create_status(self, status_data: StatusCreate, created_by: str) -> Dict[str, Any]:
        """Create a new status"""
        try:
            db = get_database()
            
            # Validate unique name
            is_unique = await StatusHelper.validate_status_name(status_data.name)
            if not is_unique:
                raise ValueError(f"Status with name '{status_data.name}' already exists")
            
            # If this is set as default, unset other defaults
            if status_data.is_default:
                await db.lead_statuses.update_many(
                    {"is_default": True},
                    {"$set": {"is_default": False}}
                )
            
            # Create status document
            status_doc = {
                **status_data.dict(),
                "created_by": created_by,
                "created_at": datetime.utcnow(),
                "updated_at": None
            }
            
            result = await db.lead_statuses.insert_one(status_doc)
            
            # Get created status with ID
            created_status = await db.lead_statuses.find_one({"_id": result.inserted_id})
            created_status["id"] = str(created_status.pop("_id"))
            created_status["lead_count"] = 0  # New status has no leads
            
            logger.info(f"Status '{status_data.name}' created by {created_by}")
            
            return {
                "success": True,
                "message": f"Status '{status_data.name}' created successfully",
                "status": created_status
            }
            
        except ValueError as e:
            logger.error(f"Validation error creating status: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating status: {e}")
            raise Exception(f"Failed to create status: {str(e)}")
    
    async def get_all_statuses(self, include_lead_count: bool = False, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all statuses"""
        try:
            db = get_database()
            
            # Build query
            query = {}
            if active_only:
                query["is_active"] = True
            
            # Get statuses
            statuses = await db.lead_statuses.find(query).sort("sort_order", 1).to_list(None)
            
            # Add lead counts if requested
            if include_lead_count:
                for status in statuses:
                    status["lead_count"] = await db.leads.count_documents({"status": status["name"]})
            else:
                for status in statuses:
                    status["lead_count"] = 0
            
            # Convert ObjectId to string
            for status in statuses:
                status["id"] = str(status.pop("_id"))
            
            return statuses
            
        except Exception as e:
            logger.error(f"Error getting statuses: {e}")
            raise Exception(f"Failed to get statuses: {str(e)}")
    
    async def get_status_by_id(self, status_id: str) -> Dict[str, Any]:
        """Get a specific status by ID"""
        try:
            db = get_database()
            
            status = await db.lead_statuses.find_one({"_id": ObjectId(status_id)})
            if not status:
                raise ValueError(f"Status with ID {status_id} not found")
            
            # Add lead count
            status["lead_count"] = await db.leads.count_documents({"status": status["name"]})
            
            # Convert ObjectId to string
            status["id"] = str(status.pop("_id"))
            
            return status
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error getting status {status_id}: {e}")
            raise Exception(f"Failed to get status: {str(e)}")
    
    async def update_status(self, status_id: str, status_data: StatusUpdate, updated_by: str) -> Dict[str, Any]:
        """Update an existing status"""
        try:
            db = get_database()
            
            # Check if status exists
            existing_status = await db.lead_statuses.find_one({"_id": ObjectId(status_id)})
            if not existing_status:
                raise ValueError(f"Status with ID {status_id} not found")
            
            # Prepare update data
            update_data = {}
            for field, value in status_data.dict(exclude_unset=True).items():
                if value is not None:
                    update_data[field] = value
            
            # If setting as default, unset other defaults
            if update_data.get("is_default"):
                await db.lead_statuses.update_many(
                    {"_id": {"$ne": ObjectId(status_id)}, "is_default": True},
                    {"$set": {"is_default": False}}
                )
            
            # Add updated timestamp
            update_data["updated_at"] = datetime.utcnow()
            
            # Update status
            result = await db.lead_statuses.update_one(
                {"_id": ObjectId(status_id)},
                {"$set": update_data}
            )
            
            if result.modified_count == 0:
                raise ValueError("No changes were made to the status")
            
            # Get updated status
            updated_status = await self.get_status_by_id(status_id)
            
            logger.info(f"Status {status_id} updated by {updated_by}")
            
            return {
                "success": True,
                "message": f"Status '{updated_status['name']}' updated successfully",
                "status": updated_status
            }
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error updating status {status_id}: {e}")
            raise Exception(f"Failed to update status: {str(e)}")
    
    async def delete_status(self, status_id: str, deleted_by: str, force: bool = False) -> Dict[str, Any]:
        """Delete a status (or deactivate if it has leads)"""
        try:
            db = get_database()
            
            # Check if status exists
            status = await db.lead_statuses.find_one({"_id": ObjectId(status_id)})
            if not status:
                raise ValueError(f"Status with ID {status_id} not found")
            
            # Check if status has leads
            lead_count = await db.leads.count_documents({"status": status["name"]})
            
            if lead_count > 0 and not force:
                # Don't delete, just deactivate
                await db.lead_statuses.update_one(
                    {"_id": ObjectId(status_id)},
                    {
                        "$set": {
                            "is_active": False,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                return {
                    "success": True,
                    "message": f"Status '{status['name']}' deactivated (has {lead_count} leads)",
                    "action": "deactivated",
                    "lead_count": lead_count
                }
            else:
                # Actually delete the status
                await db.lead_statuses.delete_one({"_id": ObjectId(status_id)})
                
                logger.info(f"Status '{status['name']}' deleted by {deleted_by}")
                
                return {
                    "success": True,
                    "message": f"Status '{status['name']}' deleted successfully",
                    "action": "deleted",
                    "lead_count": lead_count
                }
                
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error deleting status {status_id}: {e}")
            raise Exception(f"Failed to delete status: {str(e)}")
    
    async def reorder_statuses(self, status_orders: List[Dict[str, Any]], updated_by: str) -> Dict[str, Any]:
        """Reorder statuses by updating sort_order"""
        try:
            db = get_database()
            
            updated_count = 0
            for item in status_orders:
                status_id = item["id"]
                new_order = item["sort_order"]
                
                result = await db.lead_statuses.update_one(
                    {"_id": ObjectId(status_id)},
                    {
                        "$set": {
                            "sort_order": new_order,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                if result.modified_count > 0:
                    updated_count += 1
            
            logger.info(f"Reordered {updated_count} statuses by {updated_by}")
            
            return {
                "success": True,
                "message": f"Reordered {updated_count} statuses successfully",
                "updated_count": updated_count
            }
            
        except Exception as e:
            logger.error(f"Error reordering statuses: {e}")
            raise Exception(f"Failed to reorder statuses: {str(e)}")

# Create service instance
status_service = StatusService()