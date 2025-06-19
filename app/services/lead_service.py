from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
import random
import string

from ..config.database import get_database
from ..models.lead import LeadCreate, LeadUpdate, LeadStatus
from ..schemas.lead import LeadFilterParams

class LeadService:
    def __init__(self):
        pass  # Don't store db connection here
    
    def get_db(self):
        """Get database connection"""
        return get_database()
    
    async def generate_lead_id(self) -> str:
        """Generate unique lead ID like LD-1029"""
        db = self.get_db()
        
        # Get the last lead number from database
        last_lead = await db.leads.find_one(
            sort=[("created_at", -1)]
        )
        
        if last_lead and "lead_id" in last_lead:
            # Extract number from last lead ID (e.g., LD-1029 -> 1029)
            try:
                last_number = int(last_lead["lead_id"].split("-")[1])
                new_number = last_number + 1
            except (IndexError, ValueError):
                new_number = 1000
        else:
            new_number = 1000
        
        return f"LD-{new_number}"
    
    async def create_lead(self, lead_data: LeadCreate, created_by: str) -> Dict[str, Any]:
        """Create a new lead"""
        db = self.get_db()
        
        # Generate unique lead ID
        lead_id = await self.generate_lead_id()
        
        # Prepare lead document
        lead_doc = {
            "lead_id": lead_id,
            "name": lead_data.name,
            "email": lead_data.email,
            "phone_number": lead_data.phone_number,
            "country_of_interest": lead_data.country_of_interest,
            "course_level": lead_data.course_level,
            "source": lead_data.source,
            "tags": lead_data.tags or [],
            "notes": lead_data.notes,
            "status": LeadStatus.OPEN,
            "assigned_to": lead_data.assigned_to,
            "created_by": created_by,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "last_contacted": None
        }
        
        # Insert into database
        result = await db.leads.insert_one(lead_doc)
        lead_doc["_id"] = str(result.inserted_id)
        
        return lead_doc
    
    async def get_leads(self, filters: LeadFilterParams, user_id: str, user_role: str) -> Dict[str, Any]:
        """Get leads with filters and pagination"""
        db = self.get_db()
        query = {}
        
        # Role-based filtering
        if user_role != "admin":
            # Regular users see only their assigned leads
            query["assigned_to"] = user_id
        
        # Apply filters
        if filters.status:
            query["status"] = filters.status
        
        if filters.assigned_to and user_role == "admin":
            query["assigned_to"] = filters.assigned_to
        
        if filters.source:
            query["source"] = filters.source
        
        if filters.course_level:
            query["course_level"] = filters.course_level
        
        if filters.country:
            query["country_of_interest"] = {"$regex": filters.country, "$options": "i"}
        
        if filters.tags:
            query["tags"] = {"$in": filters.tags}
        
        if filters.search:
            query["$or"] = [
                {"name": {"$regex": filters.search, "$options": "i"}},
                {"email": {"$regex": filters.search, "$options": "i"}},
                {"lead_id": {"$regex": filters.search, "$options": "i"}}
            ]
        
        # Date range filtering
        if filters.created_from or filters.created_to:
            date_query = {}
            if filters.created_from:
                date_query["$gte"] = datetime.fromisoformat(filters.created_from)
            if filters.created_to:
                date_query["$lte"] = datetime.fromisoformat(filters.created_to)
            query["created_at"] = date_query
        
        # Count total documents
        total = await db.leads.count_documents(query)
        
        # Calculate pagination
        skip = (filters.page - 1) * filters.limit
        has_next = skip + filters.limit < total
        has_prev = filters.page > 1
        
        # Execute query with pagination
        cursor = db.leads.find(query).skip(skip).limit(filters.limit).sort("created_at", -1)
        leads = await cursor.to_list(length=filters.limit)
        
        # Enrich leads with user names
        enriched_leads = []
        for lead in leads:
            enriched_lead = await self._enrich_lead_with_names(lead)
            enriched_leads.append(enriched_lead)
        
        return {
            "leads": enriched_leads,
            "total": total,
            "page": filters.page,
            "limit": filters.limit,
            "has_next": has_next,
            "has_prev": has_prev
        }
    
    async def get_lead_by_id(self, lead_id: str, user_id: str, user_role: str) -> Optional[Dict[str, Any]]:
        """Get a specific lead by ID"""
        db = self.get_db()
        query = {"_id": ObjectId(lead_id)}
        
        # Role-based access control
        if user_role != "admin":
            query["assigned_to"] = user_id
        
        lead = await db.leads.find_one(query)
        
        if lead:
            return await self._enrich_lead_with_names(lead)
        
        return None
    
    async def update_lead(self, lead_id: str, lead_data: LeadUpdate, user_id: str, user_role: str) -> bool:
        """Update a lead"""
        db = self.get_db()
        query = {"_id": ObjectId(lead_id)}
        
        # Role-based access control
        if user_role != "admin":
            query["assigned_to"] = user_id
        
        # Prepare update data
        update_data = {}
        for field, value in lead_data.dict(exclude_unset=True).items():
            if value is not None:
                update_data[field] = value
        
        update_data["updated_at"] = datetime.utcnow()
        
        result = await db.leads.update_one(query, {"$set": update_data})
        return result.modified_count > 0
    
    async def assign_lead(self, lead_id: str, assigned_to: str, notes: Optional[str] = None) -> bool:
        """Assign a lead to a user (Admin only)"""
        db = self.get_db()
        update_data = {
            "assigned_to": assigned_to,
            "updated_at": datetime.utcnow()
        }
        
        if notes:
            update_data["assignment_notes"] = notes
        
        result = await db.leads.update_one(
            {"_id": ObjectId(lead_id)},
            {"$set": update_data}
        )
        return result.modified_count > 0
    
    async def delete_lead(self, lead_id: str) -> bool:
        """Delete a lead (Admin only)"""
        db = self.get_db()
        result = await db.leads.delete_one({"_id": ObjectId(lead_id)})
        return result.deleted_count > 0
    
    async def get_lead_stats(self, user_id: str, user_role: str) -> Dict[str, int]:
        """Get lead statistics"""
        db = self.get_db()
        pipeline = []
        
        # Role-based filtering
        if user_role != "admin":
            pipeline.append({"$match": {"assigned_to": user_id}})
        
        pipeline.extend([
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }
            }
        ])
        
        result = await db.leads.aggregate(pipeline).to_list(None)
        
        # Initialize stats
        stats = {
            "total_leads": 0,
            "open_leads": 0,
            "in_progress_leads": 0,
            "closed_won_leads": 0,
            "closed_lost_leads": 0,
            "my_leads": 0,
            "unassigned_leads": 0
        }
        
        # Process results
        for item in result:
            status = item["_id"]
            count = item["count"]
            stats["total_leads"] += count
            
            if status == "open":
                stats["open_leads"] = count
            elif status == "in_progress":
                stats["in_progress_leads"] = count
            elif status == "closed_won":
                stats["closed_won_leads"] = count
            elif status == "closed_lost":
                stats["closed_lost_leads"] = count
        
        # Get user-specific stats
        if user_role != "admin":
            stats["my_leads"] = stats["total_leads"]
        else:
            my_leads_count = await db.leads.count_documents({"assigned_to": user_id})
            stats["my_leads"] = my_leads_count
            
            unassigned_count = await db.leads.count_documents({"assigned_to": None})
            stats["unassigned_leads"] = unassigned_count
        
        return stats
    
    async def _enrich_lead_with_names(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich lead with user names"""
        db = self.get_db()
        lead["id"] = str(lead["_id"])
        
        # Get assigned user name
        if lead.get("assigned_to"):
            assigned_user = await db.users.find_one({"_id": ObjectId(lead["assigned_to"])})
            if assigned_user:
                lead["assigned_to_name"] = f"{assigned_user['first_name']} {assigned_user['last_name']}"
        
        # Get creator name
        if lead.get("created_by"):
            creator = await db.users.find_one({"_id": ObjectId(lead["created_by"])})
            if creator:
                lead["created_by_name"] = f"{creator['first_name']} {creator['last_name']}"
        
        return lead

# Global service instance
lead_service = LeadService()