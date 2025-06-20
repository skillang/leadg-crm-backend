# app/services/lead_service.py - Fixed Complete Lead Service

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from bson import ObjectId
import random
import string
import logging
import re

from ..config.database import get_database
from ..models.lead import (
    LeadCreateComprehensive, LeadUpdateComprehensive, LeadStatus, LeadStage,
    DuplicateCheckResult, LeadResponseComprehensive, LeadCreate, LeadUpdate
)
from ..schemas.lead import LeadFilterParams

logger = logging.getLogger(__name__)

class LeadService:
    def __init__(self):
        pass
    
    def get_db(self):
        """Get database connection"""
        return get_database()
    
    async def check_for_duplicates(self, lead_data: LeadCreateComprehensive) -> DuplicateCheckResult:
        """
        Check for duplicate leads based on email and phone number
        Returns detailed duplicate check result
        """
        db = self.get_db()
        
        try:
            email = lead_data.basic_info.email.lower()
            contact_number = self._normalize_phone_number(lead_data.basic_info.contact_number)
            
            # Build query to check for duplicates
            duplicate_queries = []
            match_criteria = []
            
            # Check for email duplicates
            duplicate_queries.append({"email": email})
            
            # Check for phone number duplicates (exact and normalized)
            phone_queries = [
                {"contact_number": lead_data.basic_info.contact_number},
                {"contact_number": contact_number}
            ]
            
            # Also check against legacy phone_number field for backward compatibility
            phone_queries.extend([
                {"phone_number": lead_data.basic_info.contact_number},
                {"phone_number": contact_number}
            ])
            
            duplicate_queries.extend(phone_queries)
            
            # Execute duplicate check
            duplicate_leads = []
            
            # Check email duplicates
            email_duplicates = await db.leads.find({"email": email}).to_list(None)
            if email_duplicates:
                match_criteria.append("email")
                duplicate_leads.extend(email_duplicates)
            
            # Check phone duplicates
            phone_duplicate_query = {
                "$or": [
                    {"contact_number": lead_data.basic_info.contact_number},
                    {"contact_number": contact_number},
                    {"phone_number": lead_data.basic_info.contact_number},
                    {"phone_number": contact_number}
                ]
            }
            
            phone_duplicates = await db.leads.find(phone_duplicate_query).to_list(None)
            if phone_duplicates:
                match_criteria.append("contact_number")
                # Avoid adding same lead twice if both email and phone match
                for phone_dup in phone_duplicates:
                    if not any(dup["_id"] == phone_dup["_id"] for dup in duplicate_leads):
                        duplicate_leads.append(phone_dup)
            
            # Format duplicate leads for response
            formatted_duplicates = []
            for dup in duplicate_leads:
                formatted_duplicates.append({
                    "lead_id": dup.get("lead_id"),
                    "name": dup.get("name"),
                    "email": dup.get("email"),
                    "contact_number": dup.get("contact_number") or dup.get("phone_number"),
                    "status": dup.get("status"),
                    "assigned_to": dup.get("assigned_to"),
                    "created_at": dup.get("created_at")
                })
            
            is_duplicate = len(duplicate_leads) > 0
            
            if is_duplicate:
                logger.warning(f"Duplicate lead detected: {email} - {len(duplicate_leads)} existing leads found")
            
            return DuplicateCheckResult(
                is_duplicate=is_duplicate,
                duplicate_leads=formatted_duplicates,
                match_criteria=list(set(match_criteria))  # Remove duplicates
            )
            
        except Exception as e:
            logger.error(f"Error checking for duplicates: {str(e)}")
            # Return safe result if check fails
            return DuplicateCheckResult(
                is_duplicate=False,
                duplicate_leads=[],
                match_criteria=[]
            )
    
    def _normalize_phone_number(self, phone: str) -> str:
        """Normalize phone number for duplicate checking"""
        if not phone:
            return ""
        
        # Remove all non-digit characters
        digits_only = re.sub(r'\D', '', phone)
        
        # Handle common country code patterns
        if digits_only.startswith('91') and len(digits_only) == 12:  # India
            return '+91-' + digits_only[2:]
        elif digits_only.startswith('1') and len(digits_only) == 11:  # US/Canada
            return '+1-' + digits_only[1:]
        elif len(digits_only) == 10:  # Assume local number
            return digits_only
        
        return digits_only
    
    async def get_next_assignee_round_robin(self) -> Optional[str]:
        """Get next user for round-robin assignment"""
        db = self.get_db()
        
        try:
            # Get all active users with 'user' role
            active_users = await db.users.find(
                {"role": "user", "is_active": True},
                {"email": 1, "_id": 1, "first_name": 1, "last_name": 1}
            ).to_list(None)
            
            if not active_users:
                logger.warning("No active users found for round-robin assignment")
                return None
            
            logger.info(f"Found {len(active_users)} active users for round-robin")
            
            # Get lead counts for each user
            user_lead_counts = {}
            for user in active_users:
                user_email = user["email"]
                lead_count = await db.leads.count_documents({"assigned_to": user_email})
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
    
    async def generate_lead_id(self) -> str:
        """Generate unique lead ID like LD-1029"""
        db = self.get_db()
        
        # Get the last lead number from database
        last_lead = await db.leads.find_one(sort=[("created_at", -1)])
        
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
    
    async def create_lead_comprehensive(
        self, 
        lead_data: LeadCreateComprehensive, 
        created_by: str,
        force_create: bool = False
    ) -> Dict[str, Any]:
        """
        Create a comprehensive lead with all sections and duplicate checking
        
        Args:
            lead_data: Comprehensive lead data
            created_by: User ID who is creating the lead
            force_create: If True, create even if duplicates exist
        
        Returns:
            Dict with creation result including duplicate check info
        """
        db = self.get_db()
        
        try:
            # Step 1: Check for duplicates
            duplicate_check = await self.check_for_duplicates(lead_data)
            
            if duplicate_check.is_duplicate and not force_create:
                logger.warning(f"Duplicate lead creation attempted: {lead_data.basic_info.email}")
                return {
                    "success": False,
                    "message": f"Duplicate lead found. Matches existing lead(s) by: {', '.join(duplicate_check.match_criteria)}",
                    "duplicate_check": duplicate_check,
                    "lead": None
                }
            
            # Step 2: Generate lead ID
            lead_id = await self.generate_lead_id()
            
            # Step 3: Handle assignment - ALWAYS auto-assign via round-robin
            assigned_to = None
            assigned_to_name = "Unassigned"
            assignment_method = "round_robin"
            
            # Always use round-robin assignment regardless of input
            assigned_to = await self.get_next_assignee_round_robin()
            if not assigned_to:
                assignment_method = "none"
            
            # Get assigned user's name
            if assigned_to:
                assigned_user = await db.users.find_one({"email": assigned_to})
                if assigned_user:
                    first_name = assigned_user.get('first_name', '')
                    last_name = assigned_user.get('last_name', '')
                    assigned_to_name = f"{first_name} {last_name}".strip() or assigned_user.get('email', 'Unknown')
                else:
                    logger.warning(f"Assigned user {assigned_to} not found")
                    assigned_to = None
                    assignment_method = "none"
            
            # Step 4: Prepare comprehensive lead document
            lead_doc = {
                # System fields
                "lead_id": lead_id,
                "status": LeadStatus.OPEN,
                
                # Basic Info
                "name": lead_data.basic_info.name,
                "email": lead_data.basic_info.email.lower(),
                "contact_number": lead_data.basic_info.contact_number,
                "phone_number": lead_data.basic_info.contact_number,  # Backward compatibility
                "source": lead_data.basic_info.source,
                
                # Status & Tags
                "stage": lead_data.status_and_tags.stage if lead_data.status_and_tags else LeadStage.INITIAL,
                "lead_score": lead_data.status_and_tags.lead_score if lead_data.status_and_tags else 0,
                "tags": lead_data.status_and_tags.tags if lead_data.status_and_tags else [],
                
                # Assignment
                "assigned_to": assigned_to,
                "assigned_to_name": assigned_to_name,
                "assignment_method": assignment_method,
                
                # Additional Info - just notes
                "notes": lead_data.additional_info.notes if lead_data.additional_info else None,
                
                # System metadata
                "created_by": created_by,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "last_contacted": None,
                
                # Assignment history
                "assignment_history": [
                    {
                        "assigned_to": assigned_to,
                        "assigned_to_name": assigned_to_name,
                        "assigned_by": created_by,
                        "assignment_method": assignment_method,
                        "assigned_at": datetime.utcnow(),
                        "reason": "Initial auto-assignment via round-robin"
                    }
                ] if assigned_to else []
            }
            
            # Step 5: Insert into database
            result = await db.leads.insert_one(lead_doc)
            lead_doc["_id"] = str(result.inserted_id)
            lead_doc["id"] = str(result.inserted_id)
            
            # Step 5.5: Get creator name for response
            try:
                creator = await db.users.find_one({"_id": ObjectId(created_by)})
                if creator:
                    first_name = creator.get('first_name', '')
                    last_name = creator.get('last_name', '')
                    created_by_name = f"{first_name} {last_name}".strip() or creator.get('email', 'Unknown User')
                else:
                    created_by_name = "Unknown User"
                lead_doc["created_by_name"] = created_by_name
            except Exception:
                lead_doc["created_by_name"] = "Unknown User"
            
            # Step 6: Log creation activity
            try:
                activity_doc = {
                    "lead_id": lead_id,
                    "activity_type": "lead_created",
                    "description": f"Lead '{lead_data.basic_info.name}' created with score {lead_doc['lead_score']}",
                    "created_by": ObjectId(created_by),
                    "created_at": datetime.utcnow(),
                    "metadata": {
                        "lead_id": lead_id,
                        "name": lead_data.basic_info.name,
                        "email": lead_data.basic_info.email,
                        "stage": lead_doc["stage"],
                        "lead_score": lead_doc["lead_score"],
                        "assigned_to": assigned_to,
                        "assigned_to_name": assigned_to_name,
                        "assignment_method": assignment_method,
                        "source": lead_data.basic_info.source,
                        "tags": lead_doc["tags"]
                    }
                }
                await db.lead_activities.insert_one(activity_doc)
            except Exception as activity_error:
                logger.warning(f"Failed to log lead creation activity: {activity_error}")
            
            assignment_info = {
                "assigned_to": assigned_to,
                "assigned_to_name": assigned_to_name,
                "assignment_method": assignment_method
            }
            
            success_message = f"Lead {lead_id} created successfully"
            if assigned_to:
                success_message += f" and auto-assigned to {assigned_to_name} via round-robin"
            
            if duplicate_check.is_duplicate and force_create:
                success_message += " (created despite duplicates)"
            
            logger.info(f"Lead {lead_id} created: {lead_data.basic_info.name} ({lead_data.basic_info.email})")
            
            return {
                "success": True,
                "message": success_message,
                "lead": self._format_lead_response(lead_doc),
                "duplicate_check": duplicate_check if duplicate_check.is_duplicate else None,
                "assignment_info": assignment_info
            }
            
        except Exception as e:
            logger.error(f"Error creating comprehensive lead: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise Exception(f"Failed to create lead: {str(e)}")
    
    def _format_lead_response(self, lead_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Format lead document for API response"""
        # Get creator name if not already set
        created_by_name = lead_doc.get("created_by_name", "Unknown User")
        
        return {
            "id": str(lead_doc.get("_id", "")),
            "lead_id": lead_doc.get("lead_id"),
            "name": lead_doc.get("name"),
            "email": lead_doc.get("email"),
            "contact_number": lead_doc.get("contact_number"),
            "source": lead_doc.get("source"),
            "stage": lead_doc.get("stage"),
            "lead_score": lead_doc.get("lead_score", 0),
            "tags": lead_doc.get("tags", []),
            "status": lead_doc.get("status"),
            "assigned_to": lead_doc.get("assigned_to"),
            "assigned_to_name": lead_doc.get("assigned_to_name"),
            "assignment_method": lead_doc.get("assignment_method"),
            "notes": lead_doc.get("notes"),
            "created_by": lead_doc.get("created_by"),
            "created_by_name": created_by_name,  # ✅ Always include this field
            "created_at": lead_doc.get("created_at"),
            "updated_at": lead_doc.get("updated_at"),
            "last_contacted": lead_doc.get("last_contacted"),
            "assignment_history": lead_doc.get("assignment_history", [])
        }
    
    async def update_lead_comprehensive(
        self, 
        lead_id: str, 
        lead_data: LeadUpdateComprehensive, 
        updated_by: str, 
        user_role: str
    ) -> bool:
        """Update a lead with comprehensive data"""
        db = self.get_db()
        
        try:
            # Build query with access control
            query = {"lead_id": lead_id}
            if user_role != "admin":
                # Regular users can only update leads assigned to them
                query["assigned_to"] = updated_by  # Assuming updated_by is email for non-admin
            
            # Get current lead
            current_lead = await db.leads.find_one(query)
            if not current_lead:
                return False
            
            # Prepare update data
            update_data = {"updated_at": datetime.utcnow()}
            
            # Update basic info
            if lead_data.basic_info:
                update_data.update({
                    "name": lead_data.basic_info.name,
                    "email": lead_data.basic_info.email.lower(),
                    "contact_number": lead_data.basic_info.contact_number,
                    "phone_number": lead_data.basic_info.contact_number,  # Backward compatibility
                    "source": lead_data.basic_info.source
                })
            
            # Update status and tags
            if lead_data.status_and_tags:
                update_data.update({
                    "stage": lead_data.status_and_tags.stage,
                    "lead_score": lead_data.status_and_tags.lead_score,
                    "tags": lead_data.status_and_tags.tags
                })
            
            # Update additional info
            if lead_data.additional_info:
                update_data.update({
                    "notes": lead_data.additional_info.notes
                })
            
            # Handle assignment change
            if lead_data.assignment and lead_data.assignment.assigned_to:
                new_assignee = lead_data.assignment.assigned_to
                current_assignee = current_lead.get("assigned_to")
                
                if new_assignee != current_assignee:
                    # Assignment is changing - get new assignee info
                    new_assignee_user = await db.users.find_one({"email": new_assignee})
                    if new_assignee_user:
                        new_assignee_name = f"{new_assignee_user.get('first_name', '')} {new_assignee_user.get('last_name', '')}".strip()
                        if not new_assignee_name:
                            new_assignee_name = new_assignee_user.get('email', 'Unknown')
                        
                        update_data.update({
                            "assigned_to": new_assignee,
                            "assigned_to_name": new_assignee_name,
                            "assignment_method": "manual_update"
                        })
                        
                        # Add to assignment history
                        assignment_entry = {
                            "assigned_to": new_assignee,
                            "assigned_to_name": new_assignee_name,
                            "assigned_by": updated_by,
                            "assignment_method": "manual_update",
                            "assigned_at": datetime.utcnow(),
                            "reason": "Updated during lead editing",
                            "previous_assignee": current_assignee,
                            "previous_assignee_name": current_lead.get("assigned_to_name", "Unassigned")
                        }
                        
                        # Use $push to add to assignment history
                        await db.leads.update_one(
                            query,
                            {
                                "$set": update_data,
                                "$push": {"assignment_history": assignment_entry}
                            }
                        )
                        
                        # Log assignment change activity
                        try:
                            activity_doc = {
                                "lead_id": lead_id,
                                "activity_type": "lead_reassigned",
                                "description": f"Lead reassigned from {current_lead.get('assigned_to_name', 'Unassigned')} to {new_assignee_name}",
                                "created_by": ObjectId(updated_by),
                                "created_at": datetime.utcnow(),
                                "metadata": {
                                    "lead_id": lead_id,
                                    "previous_assignee": current_assignee,
                                    "new_assignee": new_assignee,
                                    "new_assignee_name": new_assignee_name,
                                    "reason": "Lead update"
                                }
                            }
                            await db.lead_activities.insert_one(activity_doc)
                        except Exception as activity_error:
                            logger.warning(f"Failed to log reassignment activity: {activity_error}")
                        
                        return True
            
            # Regular update without assignment change
            result = await db.leads.update_one(query, {"$set": update_data})
            
            if result.modified_count > 0:
                # Log update activity
                try:
                    activity_doc = {
                        "lead_id": lead_id,
                        "activity_type": "lead_updated",
                        "description": f"Lead information updated",
                        "created_by": ObjectId(updated_by),
                        "created_at": datetime.utcnow(),
                        "metadata": {
                            "lead_id": lead_id,
                            "updated_fields": list(update_data.keys())
                        }
                    }
                    await db.lead_activities.insert_one(activity_doc)
                except Exception as activity_error:
                    logger.warning(f"Failed to log update activity: {activity_error}")
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error updating comprehensive lead: {str(e)}")
            return False
    
    async def get_lead_by_id_comprehensive(self, lead_id: str, user_id: str, user_role: str) -> Optional[Dict[str, Any]]:
        """Get a comprehensive lead by ID with all details"""
        db = self.get_db()
        
        try:
            # Build query with access control
            query = {"lead_id": lead_id}
            if user_role != "admin":
                query["assigned_to"] = user_id  # Assuming user_id is email for non-admin
            
            lead = await db.leads.find_one(query)
            
            if lead:
                # Enrich with creator name
                if lead.get("created_by"):
                    try:
                        creator = await db.users.find_one({"_id": ObjectId(lead["created_by"])})
                        if creator:
                            first_name = creator.get('first_name', '')
                            last_name = creator.get('last_name', '')
                            lead["created_by_name"] = f"{first_name} {last_name}".strip() or creator.get('email', 'Unknown')
                        else:
                            lead["created_by_name"] = "Unknown User"
                    except Exception:
                        lead["created_by_name"] = "Unknown User"
                
                return self._format_lead_response(lead)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting comprehensive lead: {str(e)}")
            return None
    
    async def get_round_robin_stats(self) -> Dict[str, Any]:
        """Get statistics about lead distribution among users"""
        db = self.get_db()
        
        try:
            # Get all active users
            active_users = await db.users.find(
                {"role": "user", "is_active": True},
                {"email": 1, "first_name": 1, "last_name": 1}
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
            
            # Calculate lead counts per user
            lead_counts = []
            for user in active_users:
                user_email = user["email"]
                lead_count = await db.leads.count_documents({"assigned_to": user_email})
                
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
    
    async def reassign_lead_manual(self, lead_id: str, new_assignee: str, reassigned_by: str, reason: Optional[str] = None) -> bool:
        """Manually reassign a lead to a specific user"""
        db = self.get_db()
        
        try:
            # Get current lead
            lead = await db.leads.find_one({"lead_id": lead_id})
            if not lead:
                return False
            
            # Get new assignee info
            new_assignee_user = await db.users.find_one({"email": new_assignee})
            if not new_assignee_user:
                logger.error(f"New assignee {new_assignee} not found")
                return False
            
            new_assignee_name = f"{new_assignee_user.get('first_name', '')} {new_assignee_user.get('last_name', '')}".strip()
            if not new_assignee_name:
                new_assignee_name = new_assignee_user.get('email', 'Unknown User')
            
            # Store previous assignment
            previous_assignee = lead.get("assigned_to")
            previous_assignee_name = lead.get("assigned_to_name", "Unassigned")
            
            # Create assignment history entry
            assignment_entry = {
                "assigned_to": new_assignee,
                "assigned_to_name": new_assignee_name,
                "assigned_by": reassigned_by,
                "assignment_method": "manual_reassignment",
                "assigned_at": datetime.utcnow(),
                "reason": reason or "Manual reassignment by admin",
                "previous_assignee": previous_assignee,
                "previous_assignee_name": previous_assignee_name
            }
            
            # Update lead
            update_data = {
                "assigned_to": new_assignee,
                "assigned_to_name": new_assignee_name,
                "assignment_method": "manual_reassignment",
                "updated_at": datetime.utcnow()
            }
            
            result = await db.leads.update_one(
                {"lead_id": lead_id},
                {
                    "$set": update_data,
                    "$push": {"assignment_history": assignment_entry}
                }
            )
            
            if result.modified_count > 0:
                # Log reassignment activity
                try:
                    activity_doc = {
                        "lead_id": lead_id,
                        "activity_type": "lead_reassigned",
                        "description": f"Lead reassigned from {previous_assignee_name} to {new_assignee_name}",
                        "created_by": ObjectId(reassigned_by),
                        "created_at": datetime.utcnow(),
                        "metadata": {
                            "lead_id": lead_id,
                            "previous_assignee": previous_assignee,
                            "previous_assignee_name": previous_assignee_name,
                            "new_assignee": new_assignee,
                            "new_assignee_name": new_assignee_name,
                            "reason": reason
                        }
                    }
                    await db.lead_activities.insert_one(activity_doc)
                except Exception as activity_error:
                    logger.warning(f"Failed to log reassignment activity: {activity_error}")
                
                logger.info(f"Lead {lead_id} reassigned from {previous_assignee} to {new_assignee}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error reassigning lead: {str(e)}")
            return False

    # Legacy methods for backward compatibility
    async def create_lead(self, lead_data: LeadCreate, created_by: str) -> Dict[str, Any]:
        """Legacy create lead method for backward compatibility"""
        # Convert legacy format to comprehensive format
        comprehensive_data = LeadCreateComprehensive(
            basic_info={
                "name": lead_data.name,
                "email": lead_data.email,
                "contact_number": getattr(lead_data, 'phone_number', lead_data.contact_number if hasattr(lead_data, 'contact_number') else '+1234567890'),
                "source": lead_data.source or "website"
            },
            status_and_tags={
                "stage": "initial",
                "lead_score": 0,
                "tags": lead_data.tags or []
            },
            assignment={
                "assigned_to": None  # Always auto-assign
            },
            additional_info={
                "notes": getattr(lead_data, 'notes', None)
            }
        )
        
        result = await self.create_lead_comprehensive(comprehensive_data, created_by)
        return result.get("lead", {})

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
        """Get a specific lead by ID (Legacy method)"""
        return await self.get_lead_by_id_comprehensive(lead_id, user_id, user_role)
    
    async def update_lead(self, lead_id: str, lead_data: LeadUpdate, user_id: str, user_role: str) -> bool:
        """Update a lead (Legacy method)"""
        # Convert legacy update to comprehensive format
        comprehensive_update = LeadUpdateComprehensive()
        
        if any([lead_data.name, lead_data.email, getattr(lead_data, 'phone_number', None), lead_data.source]):
            comprehensive_update.basic_info = {
                "name": lead_data.name,
                "email": lead_data.email,
                "contact_number": getattr(lead_data, 'phone_number', None),
                "source": lead_data.source
            }
        
        if lead_data.tags:
            comprehensive_update.status_and_tags = {
                "tags": lead_data.tags
            }
        
        if getattr(lead_data, 'notes', None):
            comprehensive_update.additional_info = {
                "notes": lead_data.notes
            }
        
        return await self.update_lead_comprehensive(lead_id, comprehensive_update, user_id, user_role)
    
    async def assign_lead(self, lead_id: str, assigned_to: str, notes: Optional[str] = None) -> bool:
        """Assign a lead to a user (Legacy method)"""
        return await self.reassign_lead_manual(lead_id, assigned_to, "admin", notes)
    
    async def delete_lead(self, lead_id: str) -> bool:
        """Delete a lead (Admin only)"""
        db = self.get_db()
        
        try:
            result = await db.leads.delete_one({"lead_id": lead_id})
            
            if result.deleted_count > 0:
                # Log deletion activity
                try:
                    activity_doc = {
                        "lead_id": lead_id,
                        "activity_type": "lead_deleted",
                        "description": f"Lead {lead_id} deleted",
                        "created_by": ObjectId("000000000000000000000000"),  # System user
                        "created_at": datetime.utcnow(),
                        "metadata": {
                            "lead_id": lead_id
                        }
                    }
                    await db.lead_activities.insert_one(activity_doc)
                except Exception as activity_error:
                    logger.warning(f"Failed to log deletion activity: {activity_error}")
                
                logger.info(f"Lead {lead_id} deleted")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error deleting lead: {str(e)}")
            return False
    
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
            # For admin, get their email first
            admin_user = await db.users.find_one({"_id": ObjectId(user_id)})
            admin_email = admin_user["email"] if admin_user else ""
            my_leads_count = await db.leads.count_documents({"assigned_to": admin_email})
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
            try:
                assigned_user = await db.users.find_one({"email": lead["assigned_to"]})
                if assigned_user:
                    first_name = assigned_user.get('first_name', '')
                    last_name = assigned_user.get('last_name', '')
                    lead["assigned_to_name"] = f"{first_name} {last_name}".strip() or assigned_user.get('email', 'Unknown')
            except Exception:
                lead["assigned_to_name"] = "Unknown User"
        
        # Get creator name
        if lead.get("created_by"):
            try:
                creator = await db.users.find_one({"_id": ObjectId(lead["created_by"])})
                if creator:
                    first_name = creator.get('first_name', '')
                    last_name = creator.get('last_name', '')
                    lead["created_by_name"] = f"{first_name} {last_name}".strip() or creator.get('email', 'Unknown')
            except Exception:
                lead["created_by_name"] = "Unknown User"
        
        return lead

# Global service instance
lead_service = LeadService()