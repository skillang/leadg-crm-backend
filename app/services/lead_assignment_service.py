
from typing import Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
import logging

from ..config.database import get_database
from .user_lead_array_service import user_lead_array_service

logger = logging.getLogger(__name__)

class LeadAssignmentService:
    """Service for lead assignment and round-robin logic"""
    
    def __init__(self):
        pass
    
    def get_db(self):
        """Get database connection"""
        return get_database()
    
    async def get_next_assignee_round_robin(self) -> Optional[str]:
        """Get next user for round-robin assignment"""
        db = self.get_db()
        
        try:
            # Get all active users with 'user' role
            active_users = await db.users.find(
                {"role": "user", "is_active": True},
                {"email": 1, "_id": 1, "first_name": 1, "last_name": 1, "total_assigned_leads": 1}
            ).to_list(None)
            
            if not active_users:
                logger.warning("No active users found for round-robin assignment")
                return None
            
            logger.info(f"Found {len(active_users)} active users for round-robin")
            
            # Use total_assigned_leads from user document (fast!)
            user_lead_counts = {}
            for user in active_users:
                user_email = user["email"]
                lead_count = user.get("total_assigned_leads", 0)
                user_lead_counts[user_email] = lead_count
                logger.info(f"User {user_email} has {lead_count} leads")
            
            # Find user with minimum leads
            min_leads = min(user_lead_counts.values())
            users_with_min_leads = [
                email for email, count in user_lead_counts.items() 
                if count == min_leads
            ]
            
            # If multiple users have same minimum, pick the one assigned longest ago
            if len(users_with_min_leads) > 1:
                logger.info(f"Multiple users with {min_leads} leads: {users_with_min_leads}")
                
                last_assigned_times = {}
                for user_email in users_with_min_leads:
                    last_lead = await db.leads.find_one(
                        {"assigned_to": user_email},
                        sort=[("created_at", -1)]
                    )
                    last_assigned_times[user_email] = last_lead["created_at"] if last_lead else datetime.min
                
                selected_user = min(last_assigned_times.keys(), key=lambda x: last_assigned_times[x])
            else:
                selected_user = users_with_min_leads[0]
            
            logger.info(f"Round-robin selected: {selected_user}")
            return selected_user
            
        except Exception as e:
            logger.error(f"Error in round-robin assignment: {str(e)}")
            return None
    
    async def assign_lead_to_user(self, lead_id: str, user_email: str, assigned_by: str, reason: str = "Auto-assignment") -> bool:
        """Assign a lead to a user and update user array"""
        db = self.get_db()
        
        try:
            # Get user info
            user = await db.users.find_one({"email": user_email, "is_active": True})
            if not user:
                logger.error(f"User {user_email} not found or inactive")
                return False
            
            user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user_email
            
            # Update lead document
            result = await db.leads.update_one(
                {"lead_id": lead_id},
                {
                    "$set": {
                        "assigned_to": user_email,
                        "assigned_to_name": user_name,
                        "assignment_method": "round_robin",
                        "updated_at": datetime.utcnow()
                    },
                    "$push": {
                        "assignment_history": {
                            "assigned_to": user_email,
                            "assigned_to_name": user_name,
                            "assigned_by": assigned_by,
                            "assignment_method": "round_robin",
                            "assigned_at": datetime.utcnow(),
                            "reason": reason
                        }
                    }
                }
            )
            
            if result.modified_count > 0:
                # Add to user's assigned_leads array
                await user_lead_array_service.add_lead_to_user_array(user_email, lead_id)
                logger.info(f"Lead {lead_id} assigned to {user_email}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error assigning lead: {str(e)}")
            return False
    
    async def reassign_lead(self, lead_id: str, new_user_email: str, reassigned_by: str, reason: str = "Manual reassignment") -> bool:
        """Reassign a lead to a different user"""
        db = self.get_db()
        
        try:
            # Get current lead
            lead = await db.leads.find_one({"lead_id": lead_id})
            if not lead:
                return False
            
            old_user_email = lead.get("assigned_to")
            
            # Get new user info
            new_user = await db.users.find_one({"email": new_user_email, "is_active": True})
            if not new_user:
                logger.error(f"New assignee {new_user_email} not found")
                return False
            
            new_user_name = f"{new_user.get('first_name', '')} {new_user.get('last_name', '')}".strip() or new_user_email
            
            # Update lead document
            result = await db.leads.update_one(
                {"lead_id": lead_id},
                {
                    "$set": {
                        "assigned_to": new_user_email,
                        "assigned_to_name": new_user_name,
                        "assignment_method": "manual_reassignment",
                        "updated_at": datetime.utcnow()
                    },
                    "$push": {
                        "assignment_history": {
                            "assigned_to": new_user_email,
                            "assigned_to_name": new_user_name,
                            "assigned_by": reassigned_by,
                            "assignment_method": "manual_reassignment",
                            "assigned_at": datetime.utcnow(),
                            "reason": reason,
                            "previous_assignee": old_user_email,
                            "previous_assignee_name": lead.get("assigned_to_name", "Unassigned")
                        }
                    }
                }
            )
            
            if result.modified_count > 0:
                # Update user arrays
                await user_lead_array_service.move_lead_between_users(lead_id, old_user_email, new_user_email)
                logger.info(f"Lead {lead_id} reassigned from {old_user_email} to {new_user_email}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error reassigning lead: {str(e)}")
            return False
    
    async def get_round_robin_stats(self) -> Dict[str, Any]:
        """Get round-robin assignment statistics using user arrays (FAST)"""
        db = self.get_db()
        
        try:
            # Get all active users with their lead counts from user documents
            active_users = await db.users.find(
                {"role": "user", "is_active": True},
                {"email": 1, "first_name": 1, "last_name": 1, "total_assigned_leads": 1}
            ).to_list(None)
            
            stats = {
                "total_active_users": len(active_users),
                "user_lead_distribution": [],
                "total_leads": 0,
                "unassigned_leads": 0,
                "average_leads_per_user": 0,
                "distribution_variance": 0
            }
            
            if not active_users:
                return stats
            
            # Use the fast user array data
            lead_counts = []
            for user in active_users:
                user_email = user["email"]
                lead_count = user.get("total_assigned_leads", 0)
                
                user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                if not user_name:
                    user_name = user_email
                
                user_stats = {
                    "user_email": user_email,
                    "user_name": user_name,
                    "lead_count": lead_count
                }
                stats["user_lead_distribution"].append(user_stats)
                lead_counts.append(lead_count)
                stats["total_leads"] += lead_count
            
            # Calculate unassigned leads
            stats["unassigned_leads"] = await db.leads.count_documents({"assigned_to": None})
            
            # Calculate distribution metrics
            if lead_counts:
                stats["average_leads_per_user"] = sum(lead_counts) / len(lead_counts)
                avg = stats["average_leads_per_user"]
                variance = sum((count - avg) ** 2 for count in lead_counts) / len(lead_counts)
                stats["distribution_variance"] = variance
            
            # Sort by lead count for easy viewing
            stats["user_lead_distribution"].sort(key=lambda x: x["lead_count"])
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting round-robin stats: {str(e)}")
            return {"error": str(e)}

# Global service instance
lead_assignment_service = LeadAssignmentService()