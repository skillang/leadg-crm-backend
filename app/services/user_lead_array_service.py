from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
import logging

from ..config.database import get_database

logger = logging.getLogger(__name__)

class UserLeadArrayService:
    """Service for managing user assigned_leads arrays"""
    
    def __init__(self):
        pass
    
    def get_db(self):
        """Get database connection"""
        return get_database()
    
    async def add_lead_to_user_array(self, user_email: str, lead_id: str) -> bool:
        """Add lead_id to user's assigned_leads array"""
        db = self.get_db()
        
        try:
            result = await db.users.update_one(
                {"email": user_email, "is_active": True},
                {
                    "$addToSet": {"assigned_leads": lead_id},  # $addToSet prevents duplicates
                    "$inc": {"total_assigned_leads": 1}
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"Added lead {lead_id} to user {user_email} array")
                return True
            else:
                # Check if lead was already in array
                user = await db.users.find_one({"email": user_email})
                if user and lead_id in user.get("assigned_leads", []):
                    logger.info(f"Lead {lead_id} already in user {user_email} array")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error adding lead to user array: {str(e)}")
            return False
    
    async def remove_lead_from_user_array(self, user_email: str, lead_id: str) -> bool:
        """Remove lead_id from user's assigned_leads array"""
        db = self.get_db()
        
        try:
            result = await db.users.update_one(
                {"email": user_email},
                {
                    "$pull": {"assigned_leads": lead_id},
                    "$inc": {"total_assigned_leads": -1}
                }
            )
            
            # Ensure total_assigned_leads doesn't go below 0
            await db.users.update_one(
                {"email": user_email, "total_assigned_leads": {"$lt": 0}},
                {"$set": {"total_assigned_leads": 0}}
            )
            
            if result.modified_count > 0:
                logger.info(f"Removed lead {lead_id} from user {user_email} array")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error removing lead from user array: {str(e)}")
            return False
    
    async def move_lead_between_users(self, lead_id: str, old_user_email: str, new_user_email: str) -> bool:
        """Move lead from one user's array to another"""
        db = self.get_db()
        
        try:
            # Use transaction for atomic operation
            async with await db.client.start_session() as session:
                async with session.start_transaction():
                    # Remove from old user
                    if old_user_email:
                        await db.users.update_one(
                            {"email": old_user_email},
                            {
                                "$pull": {"assigned_leads": lead_id},
                                "$inc": {"total_assigned_leads": -1}
                            },
                            session=session
                        )
                    
                    # Add to new user
                    await db.users.update_one(
                        {"email": new_user_email, "is_active": True},
                        {
                            "$addToSet": {"assigned_leads": lead_id},
                            "$inc": {"total_assigned_leads": 1}
                        },
                        session=session
                    )
                    
                    # Fix negative counts
                    await db.users.update_many(
                        {"total_assigned_leads": {"$lt": 0}},
                        {"$set": {"total_assigned_leads": 0}},
                        session=session
                    )
            
            logger.info(f"Moved lead {lead_id} from {old_user_email} to {new_user_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error moving lead between users: {str(e)}")
            return False
    
    async def get_user_leads_fast(self, user_email: str) -> Dict[str, Any]:
        """Get user's leads using their assigned_leads array (FAST)"""
        db = self.get_db()
        
        try:
            # Get user with their assigned leads array
            user = await db.users.find_one(
                {"email": user_email, "is_active": True},
                {"assigned_leads": 1, "total_assigned_leads": 1, "first_name": 1, "last_name": 1}
            )
            
            if not user:
                return {"leads": [], "total": 0, "user_info": None}
            
            lead_ids = user.get("assigned_leads", [])
            
            if not lead_ids:
                return {"leads": [], "total": 0, "user_info": user}
            
            # Get full lead details for these IDs
            leads = await db.leads.find(
                {"lead_id": {"$in": lead_ids}}
            ).sort("created_at", -1).to_list(None)
            
            # Enrich leads with user names
            from .lead_service import lead_service
            enriched_leads = []
            for lead in leads:
                enriched_lead = await lead_service._enrich_lead_with_names(lead)
                enriched_leads.append(enriched_lead)
            
            return {
                "leads": enriched_leads,
                "total": len(enriched_leads),
                "user_info": {
                    "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                    "total_assigned_leads": user.get("total_assigned_leads", 0)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting user leads fast: {str(e)}")
            return {"leads": [], "total": 0, "user_info": None}
    
    async def sync_user_lead_arrays(self) -> Dict[str, Any]:
        """Sync user assigned_leads arrays with actual lead assignments"""
        db = self.get_db()
        
        try:
            # Get all users
            users = await db.users.find({"role": "user", "is_active": True}).to_list(None)
            sync_results = []
            
            for user in users:
                user_email = user["email"]
                
                # Get actual assigned leads from leads collection
                actual_leads = await db.leads.find(
                    {"assigned_to": user_email},
                    {"lead_id": 1}
                ).to_list(None)
                
                actual_lead_ids = [lead["lead_id"] for lead in actual_leads]
                current_array = user.get("assigned_leads", [])
                
                # Update user array if different
                if set(actual_lead_ids) != set(current_array):
                    await db.users.update_one(
                        {"_id": user["_id"]},
                        {
                            "$set": {
                                "assigned_leads": actual_lead_ids,
                                "total_assigned_leads": len(actual_lead_ids)
                            }
                        }
                    )
                    
                    sync_results.append({
                        "user": user_email,
                        "old_count": len(current_array),
                        "new_count": len(actual_lead_ids),
                        "status": "updated"
                    })
                else:
                    sync_results.append({
                        "user": user_email,
                        "count": len(actual_lead_ids),
                        "status": "already_synced"
                    })
            
            return {
                "success": True,
                "message": f"Synced {len(users)} users",
                "results": sync_results
            }
            
        except Exception as e:
            logger.error(f"Error syncing user lead arrays: {str(e)}")
            return {"success": False, "error": str(e)}

# Global service instance
user_lead_array_service = UserLeadArrayService()