from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
import logging

from ..config.database import get_database
from ..models.lead_category import LeadCategoryCreate, LeadCategoryUpdate, LeadCategoryResponse
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class LeadCategoryService:
    """Lead category management service"""
    
    def __init__(self):
        pass
    
    def get_db(self):
        return get_database()
    
    async def create_category(self, category_data: LeadCategoryCreate, created_by: str) -> Dict[str, Any]:
        """Create a new lead category"""
        db = self.get_db()
        
        try:
            # Check if name or short_form already exists
            existing = await db.lead_categories.find_one({
                "$or": [
                    {"name": {"$regex": f"^{category_data.name}$", "$options": "i"}},
                    {"short_form": category_data.short_form}
                ]
            })
            
            if existing:
                if existing["name"].lower() == category_data.name.lower():
                    raise HTTPException(status_code=400, detail=f"Category with name '{category_data.name}' already exists")
                if existing["short_form"] == category_data.short_form:
                    raise HTTPException(status_code=400, detail=f"Short form '{category_data.short_form}' already exists")
            
            # Create category document
            category_doc = {
                "name": category_data.name,
                "short_form": category_data.short_form,
                "description": category_data.description,
                "is_active": category_data.is_active,
                "lead_count": 0,
                "next_lead_number": 1,
                "created_by": created_by,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            result = await db.lead_categories.insert_one(category_doc)
            category_doc["_id"] = str(result.inserted_id)
            category_doc["id"] = str(result.inserted_id)
            
            logger.info(f"Created lead category: {category_data.name} ({category_data.short_form})")
            
            return {
                "success": True,
                "message": "Lead category created successfully",
                "category": category_doc
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating lead category: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def get_all_categories(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Get all lead categories"""
        db = self.get_db()
        
        try:
            filter_query = {} if include_inactive else {"is_active": True}
            
            categories = await db.lead_categories.find(filter_query).sort("name", 1).to_list(length=None)
            
            # Convert ObjectId to string
            for category in categories:
                category["id"] = str(category["_id"])
                del category["_id"]
            
            return categories
            
        except Exception as e:
            logger.error(f"Error fetching categories: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def update_category(self, category_id: str, category_data: LeadCategoryUpdate) -> Dict[str, Any]:
        """Update lead category (cannot update short_form)"""
        db = self.get_db()
        
        try:
            # Check if category exists
            category = await db.lead_categories.find_one({"_id": ObjectId(category_id)})
            if not category:
                raise HTTPException(status_code=404, detail="Category not found")
            
            # Build update data
            update_data = {"updated_at": datetime.utcnow()}
            
            if category_data.name is not None:
                # Check if new name already exists (excluding current category)
                existing = await db.lead_categories.find_one({
                    "name": {"$regex": f"^{category_data.name}$", "$options": "i"},
                    "_id": {"$ne": ObjectId(category_id)}
                })
                if existing:
                    raise HTTPException(status_code=400, detail=f"Category with name '{category_data.name}' already exists")
                update_data["name"] = category_data.name
            
            if category_data.description is not None:
                update_data["description"] = category_data.description
            
            if category_data.is_active is not None:
                update_data["is_active"] = category_data.is_active
            
            # Update category
            await db.lead_categories.update_one(
                {"_id": ObjectId(category_id)},
                {"$set": update_data}
            )
            
            # Get updated category
            updated_category = await db.lead_categories.find_one({"_id": ObjectId(category_id)})
            updated_category["id"] = str(updated_category["_id"])
            del updated_category["_id"]
            
            return {
                "success": True,
                "message": "Category updated successfully",
                "category": updated_category
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating category: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def get_next_lead_number(self, category_short_form: str) -> int:
        """Get and increment next lead number for category"""
        db = self.get_db()
        
        try:
            # Find category and increment next_lead_number atomically
            result = await db.lead_categories.find_one_and_update(
                {"short_form": category_short_form, "is_active": True},
                {"$inc": {"next_lead_number": 1, "lead_count": 1}},
                return_document=True  # Return updated document
            )
            
            if not result:
                raise HTTPException(status_code=404, detail=f"Active category with short form '{category_short_form}' not found")
            
            return result["next_lead_number"] - 1  # Return the number before increment
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting next lead number: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def generate_lead_id(self, category: str) -> str:
        """Generate lead ID based on category"""
        try:
            # Get category details
            db = self.get_db()
            category_doc = await db.lead_categories.find_one({"name": category, "is_active": True})
            
            if not category_doc:
                raise HTTPException(status_code=400, detail=f"Active category '{category}' not found")
            
            # Get next lead number
            lead_number = await self.get_next_lead_number(category_doc["short_form"])
            
            # Generate lead ID: {SHORT_FORM}-{NUMBER}
            lead_id = f"{category_doc['short_form']}-{lead_number}"
            
            logger.info(f"Generated lead ID: {lead_id} for category: {category}")
            return lead_id
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating lead ID: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

# Create service instance
lead_category_service = LeadCategoryService()