# app/services/lead_category_service.py - UPDATED - CATEGORY-SOURCE COMBINATION LEAD ID GENERATION

from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
import logging

from ..config.database import get_database
from ..models.lead_category import LeadCategoryCreate, LeadCategoryUpdate, LeadCategoryResponse
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class LeadCategoryService:
    """Lead category management service with combination-based lead ID generation"""
    
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
                "next_lead_number": 1,  # Kept for backward compatibility
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
    
    async def get_category_short_form(self, category_name: str) -> str:
        """Get short form for category from database - CRITICAL for lead ID generation"""
        try:
            db = self.get_db()
            
            # Look up category in database
            category_doc = await db.lead_categories.find_one({"name": category_name, "is_active": True})
            
            if category_doc and "short_form" in category_doc:
                logger.info(f"Found short form '{category_doc['short_form']}' for category '{category_name}'")
                return category_doc["short_form"]
            
            # Log warning if category not found
            logger.warning(f"Category '{category_name}' not found in database, using fallback 'LD'")
            return "LD"  # Fallback if not found
            
        except Exception as e:
            logger.error(f"Error getting category short form from database: {str(e)}")
            return "LD"  # Fallback in case of error
    
    async def get_source_short_form(self, source_name: str) -> str:
        """Get short form for source from database - CRITICAL for lead ID generation"""
        try:
            db = self.get_db()
            
            # Look up source in database
            source_doc = await db.sources.find_one({"name": source_name, "is_active": True})
            
            if source_doc and "short_form" in source_doc:
                logger.info(f"Found short form '{source_doc['short_form']}' for source '{source_name}'")
                return source_doc["short_form"]
            
            # Log warning if source not found
            logger.warning(f"Source '{source_name}' not found in database, using fallback 'UN'")
            return "UN"  # Unknown source fallback
            
        except Exception as e:
            logger.error(f"Error getting source short form from database: {str(e)}")
            return "UN"  # Fallback in case of error
    
    async def get_next_combination_number(self, category_short: str, source_short: str) -> int:
        """Get and increment next lead number for category-source combination"""
        try:
            db = self.get_db()
            
            # Create composite key for the combination
            combination_key = f"{category_short}-{source_short}"
            
            # Find combination counter and increment atomically
            result = await db.lead_counters.find_one_and_update(
                {"combination_key": combination_key},
                {
                    "$inc": {"sequence": 1},
                    "$set": {
                        "category_short": category_short,
                        "source_short": source_short,
                        "updated_at": datetime.utcnow()
                    },
                    "$setOnInsert": {
                        "created_at": datetime.utcnow()
                    }
                },
                upsert=True,  # Create if doesn't exist
                return_document=True  # Return updated document
            )
            
            sequence = result["sequence"]
            last_lead_id = f"{category_short}-{source_short}-{sequence}"
            
            # Update the last_lead_id for tracking
            await db.lead_counters.update_one(
                {"combination_key": combination_key},
                {"$set": {"last_lead_id": last_lead_id}}
            )
            
            logger.info(f"Generated sequence {sequence} for combination {combination_key}")
            return sequence
            
        except Exception as e:
            logger.error(f"Error getting next combination number: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def generate_lead_id_by_category_and_source(self, category: str, source: str) -> str:
        """
        NEW: Generate lead ID based on category AND source combination
        Format: {CATEGORY_SHORT}-{SOURCE_SHORT}-{NUMBER}
        Example: NS-WB-1, SA-SM-2, WA-RF-1
        """
        try:
            # Get short forms for both category and source
            category_short = await self.get_category_short_form(category)
            source_short = await self.get_source_short_form(source)
            
            # Get next sequence number for this specific combination
            sequence = await self.get_next_combination_number(category_short, source_short)
            
            # Generate lead ID: {CATEGORY_SHORT}-{SOURCE_SHORT}-{NUMBER}
            lead_id = f"{category_short}-{source_short}-{sequence}"
            
            logger.info(f"Generated lead ID: {lead_id} for category '{category}' and source '{source}'")
            return lead_id
            
        except Exception as e:
            logger.error(f"Error generating combination lead ID: {str(e)}")
            # Fallback to old format if there's an issue
            return await self.generate_lead_id_fallback(category)
    
    async def generate_lead_id_fallback(self, category: str) -> str:
        """Fallback lead ID generation (old format) in case of errors"""
        try:
            # Get category short form
            category_short = await self.get_category_short_form(category)
            
            # Get simple sequence number
            db = self.get_db()
            result = await db.lead_counters.find_one_and_update(
                {"_id": "fallback_sequence"},
                {"$inc": {"sequence": 1}},
                upsert=True,
                return_document=True
            )
            
            sequence = result["sequence"]
            lead_id = f"{category_short}-FB-{sequence}"  # FB = Fallback
            
            logger.warning(f"Generated fallback lead ID: {lead_id} for category: {category}")
            return lead_id
            
        except Exception as e:
            logger.error(f"Error generating fallback lead ID: {str(e)}")
            # Ultimate fallback
            import time
            return f"LD-UN-{int(time.time())}"
    
    async def get_combination_statistics(self) -> Dict[str, Any]:
        """Get statistics about category-source combinations"""
        try:
            db = self.get_db()
            
            # Get all combination counters
            counters = await db.lead_counters.find({
                "combination_key": {"$exists": True}
            }).to_list(None)
            
            # Group by category and source
            stats = {
                "total_combinations": len(counters),
                "combinations": [],
                "by_category": {},
                "by_source": {}
            }
            
            for counter in counters:
                combo_info = {
                    "combination": counter["combination_key"],
                    "category": counter.get("category_short", ""),
                    "source": counter.get("source_short", ""),
                    "lead_count": counter.get("sequence", 0),
                    "last_lead_id": counter.get("last_lead_id", "")
                }
                stats["combinations"].append(combo_info)
                
                # Group by category
                category = counter.get("category_short", "Unknown")
                if category not in stats["by_category"]:
                    stats["by_category"][category] = {"total_leads": 0, "sources": []}
                stats["by_category"][category]["total_leads"] += counter.get("sequence", 0)
                stats["by_category"][category]["sources"].append(counter.get("source_short", ""))
                
                # Group by source
                source = counter.get("source_short", "Unknown")
                if source not in stats["by_source"]:
                    stats["by_source"][source] = {"total_leads": 0, "categories": []}
                stats["by_source"][source]["total_leads"] += counter.get("sequence", 0)
                stats["by_source"][source]["categories"].append(counter.get("category_short", ""))
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting combination statistics: {str(e)}")
            return {"error": str(e)}
    
    # ============================================================================
    # LEGACY METHODS (Kept for backward compatibility)
    # ============================================================================
    
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
        """LEGACY: Get and increment next lead number for category (kept for compatibility)"""
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
        """LEGACY: Generate lead ID based on category only (kept for compatibility)"""
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
            
            logger.info(f"Generated legacy lead ID: {lead_id} for category: {category}")
            return lead_id
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating lead ID: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

# Create service instance
lead_category_service = LeadCategoryService()