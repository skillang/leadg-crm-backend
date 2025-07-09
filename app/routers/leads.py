# app/routers/leads.py - Updated with Comprehensive Structure Support

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta  # ✅ Add timedelta here
import logging
from bson import ObjectId

from ..config.database import get_database
from ..utils.dependencies import get_current_active_user, get_admin_user
from ..models.lead import (
    LeadCreate, LeadUpdate, LeadResponse, LeadListResponse, 
    LeadAssign, LeadStatusUpdate, LeadStatus, LeadSource, CourseLevel,
    LeadBulkCreate, LeadBulkCreateResponse  
)
from ..schemas.lead import (
    LeadCreateResponse, LeadAssignResponse, LeadBulkAssign, 
    LeadBulkAssignResponse, LeadStatsResponse, LeadFilterParams
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================================
# SUPER FAST ENDPOINTS (Using User Arrays)
# ============================================================================

# Add this function in app/routers/leads.py after imports, before the endpoints

def transform_lead_to_structured_format(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform flat lead document to structured comprehensive format
    """
    # Clean ObjectIds first
    clean_lead = {}
    for key, value in lead.items():
        if key == "_id" or key == "created_by":
            clean_lead[key] = str(value) if value else None
        elif isinstance(value, ObjectId):
            clean_lead[key] = str(value)
        elif isinstance(value, list):
            # Handle arrays that might contain ObjectIds (like assignment_history)
            clean_array = []
            for item in value:
                if isinstance(item, dict):
                    clean_item = {}
                    for sub_key, sub_value in item.items():
                        if isinstance(sub_value, ObjectId):
                            clean_item[sub_key] = str(sub_value)
                        else:
                            clean_item[sub_key] = sub_value
                    clean_array.append(clean_item)
                elif isinstance(item, ObjectId):
                    clean_array.append(str(item))
                else:
                    clean_array.append(item)
            clean_lead[key] = clean_array
        else:
            clean_lead[key] = value
    
    # Transform to structured format
    structured_lead = {
        "basic_info": {
            "name": clean_lead.get("name", ""),
            "email": clean_lead.get("email", ""),
            "contact_number": clean_lead.get("contact_number", ""),
            "source": clean_lead.get("source", "website"),
            "country_of_interest": clean_lead.get("country_of_interest", ""),
            "course_level": clean_lead.get("course_level", "")
        },
        "status_and_tags": {
            "stage": clean_lead.get("stage", "initial"),
            "lead_score": clean_lead.get("lead_score", 0),
            "priority": clean_lead.get("priority", "medium"),
            "tags": clean_lead.get("tags", [])
        },
        "assignment": {
            "assigned_to": clean_lead.get("assigned_to"),
            "assigned_to_name": clean_lead.get("assigned_to_name"),
            "assignment_method": clean_lead.get("assignment_method"),
            "assignment_history": clean_lead.get("assignment_history", [])
        },
        "additional_info": {
            "notes": clean_lead.get("notes", "")
        },
        "system_info": {
            "id": str(clean_lead["_id"]),
            "lead_id": clean_lead.get("lead_id", ""),
            "status": clean_lead.get("status", "open"),
            "created_by": clean_lead.get("created_by", ""),
            "created_at": clean_lead.get("created_at"),
            "updated_at": clean_lead.get("updated_at"),
            "last_contacted": clean_lead.get("last_contacted")
        }
    }
    
    return structured_lead

@router.get("/my-leads-fast")
async def get_my_leads_fast(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    SUPER FAST user leads using user array lookup
    Performance: 5-50x faster than traditional query
    """
    try:
        logger.info(f"Fast leads requested by user: {current_user.get('email')}")
        
        db = get_database()
        user_data = await db.users.find_one({"email": current_user["email"]})
        
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        lead_ids = user_data.get("assigned_leads", [])
        total_count = len(lead_ids)
        
        logger.info(f"User has {total_count} leads in array: {lead_ids}")
        
        if not lead_ids:
            return {
                "success": True,
                "leads": [],
                "total": 0,
                "message": "No leads assigned",
                "performance": "ultra_fast_array_lookup"
            }
        
        # Fetch lead details
        leads_cursor = db.leads.find({"lead_id": {"$in": lead_ids}})
        leads = await leads_cursor.to_list(None)
        
        # Fix ObjectId serialization issue
        clean_leads = []
        for lead in leads:
            clean_lead = {}
            for key, value in lead.items():
                if key == "_id" or key == "created_by":
                    clean_lead[key] = str(value) if value else None
                else:
                    clean_lead[key] = value
            
            clean_lead["id"] = clean_lead["_id"]
            clean_lead["assigned_to_name"] = f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user.get('email', 'Unknown')
            clean_lead["created_by_name"] = "Admin User"
            
            clean_leads.append(clean_lead)
        
        logger.info(f"✅ Fast lookup returned {len(clean_leads)} leads")
        
        return {
            "success": True,
            "leads": clean_leads,
            "total": total_count,
            "performance": "ultra_fast_array_lookup"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fast leads error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve fast leads: {str(e)}"
        )

@router.get("/admin/user-lead-stats")
async def get_admin_user_lead_stats(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    SUPER FAST admin stats using user arrays
    """
    try:
        logger.info(f"Admin user stats requested by: {current_user.get('email')}")
        
        db = get_database()
        
        users_cursor = db.users.find(
            {"role": {"$in": ["user", "admin"]}, "is_active": True},
            {"first_name": 1, "last_name": 1, "email": 1, "role": 1, "assigned_leads": 1, "total_assigned_leads": 1}
        )
        users = await users_cursor.to_list(None)
        
        user_stats = []
        total_assigned_leads = 0
        
        for user in users:
            lead_count = user.get("total_assigned_leads", len(user.get("assigned_leads", [])))
            total_assigned_leads += lead_count
            
            user_stats.append({
                "user_id": str(user["_id"]),
                "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                "email": user["email"],
                "role": user["role"],
                "assigned_leads_count": lead_count
            })
        
        user_stats.sort(key=lambda x: x["assigned_leads_count"], reverse=True)
        
        total_leads = await db.leads.count_documents({})
        unassigned_leads = await db.leads.count_documents({"assigned_to": None})
        
        return {
            "success": True,
            "user_stats": user_stats,
            "summary": {
                "total_users": len(user_stats),
                "total_leads": total_leads,
                "assigned_leads": total_assigned_leads,
                "unassigned_leads": unassigned_leads
            },
            "performance": "ultra_fast_array_lookup"
        }
        
    except Exception as e:
        logger.error(f"Admin stats error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get admin stats: {str(e)}"
        )

@router.post("/admin/sync-user-arrays")
async def sync_user_arrays(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Sync user arrays with actual lead assignments (Maintenance)
    """
    try:
        logger.info(f"Array sync requested by admin: {current_user.get('email')}")
        
        db = get_database()
        sync_count = 0
        
        users = await db.users.find({}).to_list(None)
        
        for user in users:
            user_email = user["email"]
            actual_leads = await db.leads.find({"assigned_to": user_email}, {"lead_id": 1}).to_list(None)
            actual_lead_ids = [lead["lead_id"] for lead in actual_leads]
            
            await db.users.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {
                        "assigned_leads": actual_lead_ids,
                        "total_assigned_leads": len(actual_lead_ids),
                        "array_last_synced": datetime.utcnow()
                    }
                }
            )
            sync_count += 1
        
        logger.info(f"✅ Synced arrays for {sync_count} users")
        
        return {
            "success": True,
            "message": f"Synced lead arrays for {sync_count} users",
            "synced_users": sync_count
        }
        
    except Exception as e:
        logger.error(f"Array sync error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync arrays: {str(e)}"
        )

# ============================================================================
# QUICK FIX ENDPOINT
# ============================================================================

@router.post("/fix-arrays-now")
async def fix_user_arrays_now(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    One-time fix for current wrong user arrays
    """
    try:
        db = get_database()
        
        print("🔧 Fixing user arrays...")
        
        # Get all active users
        users = await db.users.find(
            {"is_active": True}, 
            {"email": 1, "assigned_leads": 1, "total_assigned_leads": 1}
        ).to_list(length=None)
        
        fixed_count = 0
        
        for user in users:
            user_email = user["email"]
            
            # Get actual assigned leads from leads collection
            actual_leads = await db.leads.find(
                {"assigned_to": user_email},
                {"lead_id": 1}
            ).to_list(length=None)
            
            actual_lead_ids = [lead["lead_id"] for lead in actual_leads]
            current_array = user.get("assigned_leads", [])
            
            # Fix if different
            if set(actual_lead_ids) != set(current_array):
                await db.users.update_one(
                    {"email": user_email},
                    {
                        "$set": {
                            "assigned_leads": actual_lead_ids,
                            "total_assigned_leads": len(actual_lead_ids)
                        }
                    }
                )
                
                print(f"✅ Fixed {user_email}: {len(current_array)} -> {len(actual_lead_ids)} leads")
                fixed_count += 1
            else:
                print(f"✅ {user_email} already correct ({len(actual_lead_ids)} leads)")
        
        return {
            "success": True,
            "message": f"Fixed {fixed_count} users",
            "total_users_checked": len(users)
        }
        
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# CORE LEAD ENDPOINTS
# ============================================================================

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_lead(
    lead_data: dict,  # Accept any JSON structure
    force_create: bool = Query(False, description="Create lead even if duplicates exist"),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Create a new lead with comprehensive features:
    - Duplicate detection and prevention
    - Round-robin auto-assignment
    - Activity logging
    - User array updates
    """
    try:
        logger.info(f"Creating lead by admin: {current_user['email']}")
        
        db = get_database()
        
        # Step 1: Extract and validate data
        if "basic_info" in lead_data:
            # Nested structure (comprehensive format)
            basic_info = lead_data.get("basic_info", {})
            status_and_tags = lead_data.get("status_and_tags", {})
            assignment = lead_data.get("assignment", {})
            additional_info = lead_data.get("additional_info", {})
            
            name = basic_info.get("name", "")
            email = basic_info.get("email", "")
            contact_number = basic_info.get("contact_number", "")
            source = basic_info.get("source", "website")
            stage = status_and_tags.get("stage", "initial")
            lead_score = status_and_tags.get("lead_score", 0)
            priority = status_and_tags.get("priority", "medium")
            tags = status_and_tags.get("tags", [])
            manual_assigned_to = assignment.get("assigned_to")
            notes = additional_info.get("notes", "")
            country_of_interest = basic_info.get("country_of_interest", "")
            course_level = basic_info.get("course_level", "")
        else:
            # Flat structure (legacy format)
            name = lead_data.get("name", "")
            email = lead_data.get("email", "")
            contact_number = lead_data.get("phone_number", "")
            source = lead_data.get("source", "website")
            stage = "initial"
            lead_score = 0
            priority = "medium"
            tags = lead_data.get("tags", [])
            manual_assigned_to = lead_data.get("assigned_to")
            notes = lead_data.get("notes", "")
            country_of_interest = lead_data.get("country_of_interest", "")
            course_level = lead_data.get("course_level", "")
        
        # Validate required fields
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name is required")
        if not email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")
        if not contact_number:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contact number is required")
        
        # Step 2: Check for duplicates
        logger.info(f"Checking for duplicates: {email}, {contact_number}")
        
        duplicate_query = {
            "$or": [
                {"email": email.lower()},
                {"contact_number": contact_number},
                {"phone_number": contact_number}
            ]
        }
        
        existing_leads = await db.leads.find(duplicate_query).to_list(None)
        
        if existing_leads and not force_create:
            duplicate_info = []
            for lead in existing_leads:
                duplicate_info.append({
                    "lead_id": lead.get("lead_id"),
                    "name": lead.get("name"),
                    "email": lead.get("email"),
                    "contact_number": lead.get("contact_number"),
                    "created_at": lead.get("created_at")
                })
            
            logger.warning(f"Duplicate lead creation prevented: {email}")
            return {
                "success": False,
                "message": f"Duplicate lead found! A lead with this email or phone number already exists.",
                "duplicate_check": {
                    "is_duplicate": True,
                    "duplicate_leads": duplicate_info,
                    "match_criteria": ["email", "phone_number"]
                },
                "force_create_option": "Add ?force_create=true to create anyway"
            }
        
        # Step 3: Generate lead ID
        last_lead = await db.leads.find_one(sort=[("created_at", -1)])
        if last_lead and "lead_id" in last_lead:
            try:
                last_number = int(last_lead["lead_id"].split("-")[1])
                new_number = last_number + 1
            except (IndexError, ValueError):
                new_number = 1000
        else:
            new_number = 1000
        
        lead_id = f"LD-{new_number}"
        
        # Step 4: Assignment Logic (Round-Robin or Manual)
        assigned_to = None
        assigned_to_name = "Unassigned"
        assignment_method = "unassigned"
        assignment_history = []
        
        if manual_assigned_to:
            # Manual assignment
            assigned_user = await db.users.find_one({"email": manual_assigned_to, "is_active": True})
            if assigned_user:
                assigned_to = manual_assigned_to
                assigned_to_name = f"{assigned_user.get('first_name', '')} {assigned_user.get('last_name', '')}".strip()
                if not assigned_to_name:
                    assigned_to_name = assigned_user.get('email', 'Unknown')
                assignment_method = "manual"
                logger.info(f"Manual assignment: {assigned_to}")
        
        if not assigned_to:
            # Round-robin assignment
            logger.info("Using round-robin assignment")
            assignable_users = await db.users.find(
                {"role": "user", "is_active": True},
                {"email": 1, "first_name": 1, "last_name": 1, "total_assigned_leads": 1}
            ).to_list(None)
            
            if assignable_users:
                # Sort by total_assigned_leads for balanced distribution
                assignable_users.sort(key=lambda x: x.get("total_assigned_leads", 0))
                next_user = assignable_users[0]
                
                assigned_to = next_user["email"]
                assigned_to_name = f"{next_user.get('first_name', '')} {next_user.get('last_name', '')}".strip()
                if not assigned_to_name:
                    assigned_to_name = next_user.get('email', 'Unknown')
                assignment_method = "round_robin"
                logger.info(f"Round-robin assignment: {assigned_to} (had {next_user.get('total_assigned_leads', 0)} leads)")
        
        # Create assignment history
        if assigned_to:
            assignment_history.append({
                "assigned_to": assigned_to,
                "assigned_to_name": assigned_to_name,
                "assigned_by": current_user["_id"],
                "assigned_by_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip(),
                "assigned_at": datetime.utcnow(),
                "assignment_method": assignment_method,
                "notes": f"Initial assignment via {assignment_method}"
            })
        
        # Step 5: Create lead document
        lead_doc = {
            "lead_id": lead_id,
            "name": name,
            "email": email.lower(),
            "contact_number": contact_number,
            "phone_number": contact_number,
            "country_of_interest": country_of_interest,
            "course_level": course_level,
            "source": source,
            "stage": stage,
            "lead_score": lead_score,
            "priority": priority,
            "tags": tags,
            "status": "open",
            "assigned_to": assigned_to,
            "assigned_to_name": assigned_to_name,
            "assignment_method": assignment_method,
            "assignment_history": assignment_history,
            "notes": notes,
            "created_by": current_user["_id"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "last_contacted": None
        }
        
        # Step 6: Insert lead
        result = await db.leads.insert_one(lead_doc)
        lead_object_id = result.inserted_id
        
        # Step 7: Update user array if assigned
        if assigned_to:
            user_update_result = await db.users.update_one(
                {"email": assigned_to, "is_active": True},
                {
                    "$push": {"assigned_leads": lead_id},
                    "$inc": {"total_assigned_leads": 1}
                }
            )
            logger.info(f"Lead {lead_id} assigned to {assigned_to} via {assignment_method}")
        
        # Step 8: Log activity
        try:
            activity_doc = {
                "lead_id": lead_id,
                "activity_type": "lead_created",
                "description": f"Lead '{name}' created with score {lead_score}",
                "created_by": current_user["_id"],
                "created_by_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip(),
                "created_at": datetime.utcnow(),
                "metadata": {
                    "lead_id": lead_id,
                    "lead_name": name,
                    "email": email,
                    "source": source,
                    "assignment_method": assignment_method,
                    "assigned_to": assigned_to,
                    "assigned_to_name": assigned_to_name
                }
            }
            await db.lead_activities.insert_one(activity_doc)
            logger.info(f"✅ Activity logged for lead creation: {lead_id}")
        except Exception as activity_error:
            logger.warning(f"Failed to log activity: {activity_error}")
        
        # Step 9: Prepare response
        response_lead = {
            "id": str(lead_object_id),
            "lead_id": lead_id,
            "name": name,
            "email": email,
            "contact_number": contact_number,
            "phone_number": contact_number,
            "country_of_interest": country_of_interest,
            "course_level": course_level,
            "source": source,
            "stage": stage,
            "lead_score": lead_score,
            "priority": priority,
            "tags": tags,
            "status": "open",
            "assigned_to": assigned_to,
            "assigned_to_name": assigned_to_name,
            "assignment_method": assignment_method,
            "assignment_history": assignment_history,
            "notes": notes,
            "created_by": str(current_user["_id"]),
            "created_by_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip(),
            "created_at": lead_doc["created_at"],
            "updated_at": lead_doc["updated_at"]
        }
        
        assignment_message = ""
        if assignment_method == "round_robin":
            assignment_message = f" and auto-assigned to {assigned_to_name} via round-robin"
        elif assignment_method == "manual":
            assignment_message = f" and manually assigned to {assigned_to_name}"
        
        logger.info(f"✅ Lead created successfully: {lead_id}")
        
        return {
            "success": True,
            "message": f"Lead {lead_id} created successfully{assignment_message}",
            "lead": response_lead,
            "assignment_info": {
                "assigned_to": assigned_to,
                "assigned_to_name": assigned_to_name,
                "assignment_method": assignment_method,
                "assignment_history": assignment_history
            } if assigned_to else None,
            "duplicate_check": {
                "is_duplicate": False,
                "checked": True
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lead creation error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create lead: {str(e)}"
        )


@router.get("/", response_model=LeadListResponse)
async def get_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    lead_status: Optional[LeadStatus] = Query(None),
    assigned_to: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get leads with comprehensive error handling and data validation
    FIXED VERSION: Handles missing fields and ensures Pydantic validation
    """
    try:
        logger.info(f"Get leads requested by: {current_user.get('email')}")
        db = get_database()
        
        # Build query
        query = {}
        if current_user["role"] != "admin":
            query["assigned_to"] = current_user["email"]
        if lead_status:
            query["status"] = lead_status
        if assigned_to and current_user["role"] == "admin":
            query["assigned_to"] = assigned_to
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
                {"lead_id": {"$regex": search, "$options": "i"}}
            ]
        
        total = await db.leads.count_documents(query)
        skip = (page - 1) * limit
        
        leads = await db.leads.find(query).skip(skip).limit(limit).sort("created_at", -1).to_list(None)
        
        # 🔧 CRITICAL FIX: Ensure ALL required fields for Pydantic validation
        processed_leads = []
        
        for lead in leads:
            try:
                # Basic field transformations
                lead["id"] = str(lead["_id"])
                lead["created_by"] = str(lead.get("created_by", ""))
                
                # 🚨 CRITICAL: Ensure lead_score exists (required by LeadResponseComprehensive)
                if "lead_score" not in lead or lead["lead_score"] is None:
                    lead["lead_score"] = 0
                    logger.warning(f"Missing lead_score for lead {lead.get('lead_id', 'unknown')}, defaulting to 0")
                
                # 🚨 CRITICAL: Ensure stage is valid enum value
                valid_stages = ["initial", "contacted", "qualified", "proposal", "negotiation", "closed", "lost"]
                if lead.get("stage") not in valid_stages:
                    if lead.get("stage") == "open":
                        lead["stage"] = "initial"
                    else:
                        lead["stage"] = "initial"
                        logger.warning(f"Invalid stage '{lead.get('stage')}' for lead {lead.get('lead_id')}, defaulting to 'initial'")
                
                # 🚨 CRITICAL: Ensure all required fields have defaults
                required_defaults = {
                    "tags": [],
                    "contact_number": lead.get("phone_number", ""),
                    "source": "website",
                    "assigned_to_name": None,
                    "assignment_method": None,
                    "notes": None,
                    "last_contacted": None,
                    "assignment_history": None
                }
                
                for field, default_value in required_defaults.items():
                    if field not in lead or lead[field] is None:
                        lead[field] = default_value
                
                # Handle created_by_name
                created_by_id = lead.get("created_by")
                if created_by_id:
                    try:
                        user_info = await db.users.find_one({"_id": ObjectId(created_by_id)})
                        if user_info:
                            lead["created_by_name"] = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
                            if not lead["created_by_name"]:
                                lead["created_by_name"] = user_info.get('email', 'Unknown User')
                        else:
                            lead["created_by_name"] = "Unknown User"
                    except Exception as e:
                        logger.error(f"Error fetching created_by user info: {e}")
                        lead["created_by_name"] = "Unknown User"
                else:
                    lead["created_by_name"] = "Unknown User"
                
                # Handle assigned_to_name
                if lead.get("assigned_to") and not lead.get("assigned_to_name"):
                    try:
                        assigned_user = await db.users.find_one({"email": lead["assigned_to"]})
                        if assigned_user:
                            lead["assigned_to_name"] = f"{assigned_user.get('first_name', '')} {assigned_user.get('last_name', '')}".strip()
                            if not lead["assigned_to_name"]:
                                lead["assigned_to_name"] = assigned_user.get('email', 'Unknown')
                        else:
                            lead["assigned_to_name"] = lead["assigned_to"]
                    except Exception as e:
                        logger.error(f"Error fetching assigned_to user info: {e}")
                        lead["assigned_to_name"] = lead.get("assigned_to", "")
                
                # Ensure status has a default
                if "status" not in lead or not lead["status"]:
                    lead["status"] = "Followup"
                
                processed_leads.append(lead)
                
            except Exception as e:
                logger.error(f"Error processing lead {lead.get('lead_id', 'unknown')}: {e}")
                # Skip this lead rather than failing the entire request
                continue
        
        logger.info(f"Successfully processed {len(processed_leads)} leads out of {len(leads)} total")
        
        return LeadListResponse(
            leads=processed_leads,
            total=total,
            page=page,
            limit=limit,
            has_next=skip + limit < total,
            has_prev=page > 1
        )
        
    except Exception as e:
        logger.error(f"Get leads error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve leads"
        )
    

# 🔧 ADDITIONAL FIX: Database Migration to Add Missing Fields
@router.post("/fix-missing-fields")
async def fix_missing_lead_fields(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    One-time migration to fix leads missing required fields
    """
    try:
        db = get_database()
        
        # Find leads missing lead_score
        leads_missing_score = await db.leads.find({"lead_score": {"$exists": False}}).to_list(None)
        
        updated_count = 0
        for lead in leads_missing_score:
            await db.leads.update_one(
                {"_id": lead["_id"]},
                {"$set": {"lead_score": 0}}
            )
            updated_count += 1
        
        # Find leads with invalid stages
        leads_invalid_stage = await db.leads.find({
            "stage": {"$nin": ["initial", "contacted", "qualified", "proposal", "negotiation", "closed", "lost"]}
        }).to_list(None)
        
        stage_updated_count = 0
        for lead in leads_invalid_stage:
            new_stage = "initial" if lead.get("stage") == "open" else "initial"
            await db.leads.update_one(
                {"_id": lead["_id"]},
                {"$set": {"stage": new_stage}}
            )
            stage_updated_count += 1
        
        logger.info(f"Fixed {updated_count} leads missing lead_score and {stage_updated_count} leads with invalid stages")
        
        return {
            "success": True,
            "message": f"Fixed {updated_count} leads missing lead_score and {stage_updated_count} leads with invalid stages",
            "leads_updated": updated_count,
            "stages_updated": stage_updated_count
        }
        
    except Exception as e:
        logger.error(f"Fix missing fields error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fix missing fields"
        )

@router.get("/my-leads", response_model=LeadListResponse)
async def get_my_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    lead_status: Optional[LeadStatus] = Query(None),  # ✅ FIXED: Changed from 'status' to 'lead_status'
    search: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get leads assigned to current user (Traditional method)
    """
    try:
        db = get_database()
        query = {"assigned_to": current_user["email"]}
        
        # ✅ FIXED: Use lead_status instead of status
        if lead_status:
            query["status"] = lead_status
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
                {"lead_id": {"$regex": search, "$options": "i"}}
            ]
        
        total = await db.leads.count_documents(query)
        skip = (page - 1) * limit
        
        leads = await db.leads.find(query).skip(skip).limit(limit).sort("created_at", -1).to_list(None)
        
        # 🔧 FIX: ObjectId serialization and Pydantic validation issues
        for lead in leads:
            lead["id"] = str(lead["_id"])
            lead["created_by"] = str(lead.get("created_by", ""))
            lead["assigned_to_name"] = f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip()
            
# 🔧 FIX 1: Handle status and stage enum mismatches
            if lead.get("status") == "open":
                lead["status"] = "Followup"  # Replace 'open' with valid default

            if lead.get("stage") == "open":
                lead["stage"] = "initial"  # Replace invalid stage
            elif lead.get("stage") not in ["initial", "contacted", "qualified", "proposal", "negotiation", "closed", "lost"]:
                    lead["stage"] = "initial"
  # Default fallback
            
            # 🔧 FIX 2: Add missing created_by_name field
            created_by_id = lead.get("created_by")
            if created_by_id:
                try:
                    user_info = await db.users.find_one({"_id": ObjectId(created_by_id)})
                    if user_info:
                        lead["created_by_name"] = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
                        if not lead["created_by_name"]:
                            lead["created_by_name"] = user_info.get('email', 'Unknown User')
                    else:
                        lead["created_by_name"] = "Unknown User"
                except:
                    lead["created_by_name"] = "Unknown User"
            else:
                lead["created_by_name"] = "Unknown User"
            
            # Ensure assigned_to_name has a fallback
            if not lead["assigned_to_name"]:
                lead["assigned_to_name"] = current_user.get('email', 'Unknown')
        
        return LeadListResponse(
            leads=leads,
            total=total,
            page=page,
            limit=limit,
            has_next=skip + limit < total,
            has_prev=page > 1
        )
        
    except Exception as e:
        logger.error(f"Get my leads error: {e}")
        # ✅ FIXED: Now 'status' refers to the imported FastAPI status module
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve your leads"
        )

@router.get("/stats", response_model=LeadStatsResponse)
async def get_lead_stats(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get lead statistics for dashboard (custom statuses)
    """
    try:
        db = get_database()
        
        pipeline = []
        if current_user["role"] != "admin":
            pipeline.append({"$match": {"assigned_to": current_user["email"]}})
        
        pipeline.extend([
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }
            }
        ])
        
        result = await db.leads.aggregate(pipeline).to_list(None)
        
        # ✅ Your custom lead statuses
        custom_statuses = [
            "Followup", "Warm", "Prospect", "Junk", "Enrolled", "Yet to call",
            "Counseled", "DNP", "INVALID", "Call Back", "Busy", "NI", "Ringing", "Wrong Number"
        ]
        
        # ✅ Initialize stats dictionary
        stats = {status.lower().replace(" ", "_"): 0 for status in custom_statuses}
        stats["total_leads"] = 0
        stats["my_leads"] = 0
        stats["unassigned_leads"] = 0
        
        # ✅ Map aggregation result
        for item in result:
            status_val = item["_id"]
            count = item["count"]
            stats["total_leads"] += count

            key = status_val.lower().replace(" ", "_")
            if key in stats:
                stats[key] = count
        
        # ✅ Get my_leads / unassigned_leads
        if current_user["role"] != "admin":
            stats["my_leads"] = stats["total_leads"]
        else:
            admin_user = await db.users.find_one({"_id": ObjectId(current_user["_id"])})
            admin_email = admin_user["email"] if admin_user else ""
            stats["my_leads"] = await db.leads.count_documents({"assigned_to": admin_email})
            stats["unassigned_leads"] = await db.leads.count_documents({"assigned_to": None})
        
        return LeadStatsResponse(**stats)
    
    except Exception as e:
        logger.error(f"Get lead stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve lead statistics"
        )


@router.get("/{lead_id}")
async def get_lead(
    lead_id: str,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get a specific lead by ID in structured comprehensive format
    """
    try:
        db = get_database()
        
        query = {"lead_id": lead_id}
        if current_user["role"] != "admin":
            query["assigned_to"] = current_user["email"]
        
        lead = await db.leads.find_one(query)
        
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found or you don't have permission to view it"
            )
        
        # Transform to structured format
        structured_lead = transform_lead_to_structured_format(lead)
        
        return {
            "success": True,
            "lead": structured_lead
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get lead error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve lead"
        )

# ============================================================================
# ASSIGNMENT ENDPOINTS
# ============================================================================

@router.post("/{lead_id}/assign", response_model=LeadAssignResponse)
async def assign_lead(
    lead_id: str,
    assignment: LeadAssign,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Assign a lead to a user (Admin only) - Updates both lead and user array
    """
    try:
        db = get_database()
        
        # Verify user exists
        assignee = await db.users.find_one({"email": assignment.assigned_to})
        if not assignee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Get current lead
        lead = await db.leads.find_one({"lead_id": lead_id})
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found"
            )
        
        current_assignee = lead.get("assigned_to")
        
        # Update lead assignment
        await db.leads.update_one(
            {"lead_id": lead_id},
            {
                "$set": {
                    "assigned_to": assignment.assigned_to,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Update user arrays
        if current_assignee and current_assignee != assignment.assigned_to:
            await db.users.update_one(
                {"email": current_assignee},
                {
                    "$pull": {"assigned_leads": lead_id},
                    "$inc": {"total_assigned_leads": -1}
                }
            )
        
        if assignment.assigned_to != current_assignee:
            await db.users.update_one(
                {"email": assignment.assigned_to},
                {
                    "$push": {"assigned_leads": lead_id},
                    "$inc": {"total_assigned_leads": 1}
                }
            )
        
        logger.info(f"Lead {lead_id} assigned to {assignee['email']} by {current_user['email']}")
        
        return LeadAssignResponse(
            success=True,
            message=f"Lead assigned to {assignee['first_name']} {assignee['last_name']}",
            lead_id=lead_id,
            assigned_to=assignment.assigned_to,
            assigned_to_name=f"{assignee['first_name']} {assignee['last_name']}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lead assignment error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign lead"
        )

# ============================================================================
# UPDATE ENDPOINT (FIXED)
# ============================================================================

@router.put("/update")
async def update_lead_universal(
    update_request: dict,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Universal lead update endpoint with user array synchronization
    """
    try:
        # ✅ FIXED: Use correct import path
        from ..services.user_lead_array_service import user_lead_array_service
        
        logger.info(f"🔄 Update by {current_user.get('email')} with data: {update_request}")
        
        db = get_database()
        
        # Get lead_id
        lead_id = update_request.get("lead_id")
        if not lead_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="lead_id is required in update request"
            )
        
        # Get current lead
        lead = await db.leads.find_one({"lead_id": lead_id})
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found"
            )
        
        # Check permissions
        user_role = current_user.get("role", "user")
        if user_role != "admin" and lead.get("assigned_to") != current_user.get("email"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update leads assigned to you"
            )
        
        # Check if assignment is being changed
        current_assigned_to = lead.get("assigned_to")
        new_assigned_to = update_request.get("assigned_to")
        assignment_changed = False
        
        if "assigned_to" in update_request and current_assigned_to != new_assigned_to:
            assignment_changed = True
            logger.info(f"🔄 Assignment change: '{current_assigned_to}' -> '{new_assigned_to}'")
            
            # Only admins can reassign
            if user_role != "admin":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only admins can reassign leads"
                )
            
            # Validate new assignee exists
            if new_assigned_to:
                new_user = await db.users.find_one({"email": new_assigned_to, "is_active": True})
                if not new_user:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"User {new_assigned_to} not found or inactive"
                    )
                
                # Add assigned_to_name
                new_user_name = f"{new_user.get('first_name', '')} {new_user.get('last_name', '')}".strip() or new_assigned_to
                update_request["assigned_to_name"] = new_user_name
        
        # Prepare update data
        update_data = {k: v for k, v in update_request.items() if k != "lead_id"}
        update_data["updated_at"] = datetime.utcnow()
        
        # Update the lead document
        await db.leads.update_one(
            {"lead_id": lead_id},
            {"$set": update_data}
        )
        
        logger.info(f"✅ Lead {lead_id} document updated")
        
        # Handle user array synchronization if assignment changed
        if assignment_changed:
            try:
                array_sync_success = await user_lead_array_service.move_lead_between_users(
                    lead_id, current_assigned_to, new_assigned_to
                )
                
                if array_sync_success:
                    logger.info(f"✅ User arrays synchronized for lead {lead_id}")
                else:
                    logger.error(f"❌ Failed to synchronize user arrays for lead {lead_id}")
                    
            except Exception as sync_error:
                logger.error(f"💥 Array synchronization error: {str(sync_error)}")
        
        # Get updated lead
        updated_lead = await db.leads.find_one({"lead_id": lead_id})
        
        # Clean ObjectIds for response
        def clean_response(doc):
            clean_doc = {}
            for key, value in doc.items():
                if key == "_id" or key == "created_by":
                    clean_doc[key] = str(value) if value else None
                elif isinstance(value, ObjectId):
                    clean_doc[key] = str(value)
                else:
                    clean_doc[key] = value
            return clean_doc
        
        clean_lead = clean_response(updated_lead)
        
        return {
            "success": True,
            "message": f"Lead {lead_id} updated successfully",
            "assignment_changed": assignment_changed,
            "lead": clean_lead
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Update error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update lead: {str(e)}"
        )

# ============================================================================
# DELETE ENDPOINT
# ============================================================================

@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Delete a lead (Admin only) - Also removes from user arrays
    """
    try:
        db = get_database()
        
        # Get the lead first to know who it's assigned to
        lead = await db.leads.find_one({"lead_id": lead_id})
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found"
            )
        
        assigned_to = lead.get("assigned_to")
        
        # Delete the lead
        result = await db.leads.delete_one({"lead_id": lead_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found"
            )
        
        # Remove from user's array if assigned
        if assigned_to:
            await db.users.update_one(
                {"email": assigned_to},
                {
                    "$pull": {"assigned_leads": lead_id},
                    "$inc": {"total_assigned_leads": -1}
                }
            )
        
        logger.info(f"Lead {lead_id} deleted by {current_user['email']}")
        
        return {
            "success": True,
            "message": "Lead deleted successfully",
            "lead_id": lead_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete lead error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete lead"
        )

# ============================================================================
# BULK OPERATIONS
# ============================================================================

@router.post("/bulk-create", status_code=status.HTTP_201_CREATED)
async def bulk_create_leads(
    leads_data: List[dict],  # Array of lead objects
    force_create: bool = Query(False, description="Create leads even if duplicates exist"),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Create multiple leads at once with:
    - Individual duplicate checking
    - Round-robin assignment distribution
    - Activity logging for each lead
    - User array updates
    - Error handling for individual failures
    """
    try:
        logger.info(f"Bulk creating {len(leads_data)} leads by admin: {current_user['email']}")
        
        if len(leads_data) > 100:  # Limit bulk size
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 100 leads can be created at once"
            )
        
        db = get_database()
        results = []
        successful_creates = 0
        failed_creates = 0
        
        # Get next available user for round-robin
        assignable_users = await db.users.find(
            {"role": "user", "is_active": True},
            {"email": 1, "first_name": 1, "last_name": 1, "total_assigned_leads": 1}
        ).to_list(None)
        
        if assignable_users:
            assignable_users.sort(key=lambda x: x.get("total_assigned_leads", 0))
        
        current_user_index = 0
        
        for index, lead_data in enumerate(leads_data):
            try:
                # Extract lead info (similar to single create logic)
                if "basic_info" in lead_data:
                    basic_info = lead_data.get("basic_info", {})
                    name = basic_info.get("name", "")
                    email = basic_info.get("email", "")
                    contact_number = basic_info.get("contact_number", "")
                else:
                    name = lead_data.get("name", "")
                    email = lead_data.get("email", "")
                    contact_number = lead_data.get("contact_number", "")
                
                # Validate required fields
                if not name or not email or not contact_number:
                    results.append({
                        "index": index,
                        "status": "failed",
                        "error": "Missing required fields (name, email, contact_number)",
                        "input_data": lead_data
                    })
                    failed_creates += 1
                    continue
                
                # Check for duplicates
                duplicate_query = {
                    "$or": [
                        {"email": email.lower()},
                        {"contact_number": contact_number}
                    ]
                }
                
                existing_lead = await db.leads.find_one(duplicate_query)
                if existing_lead and not force_create:
                    results.append({
                        "index": index,
                        "status": "skipped",
                        "reason": "duplicate",
                        "existing_lead_id": existing_lead.get("lead_id"),
                        "input_data": lead_data
                    })
                    continue
                
                # Generate lead ID
                last_lead = await db.leads.find_one(sort=[("created_at", -1)])
                if last_lead and "lead_id" in last_lead:
                    try:
                        last_number = int(last_lead["lead_id"].split("-")[1])
                        new_number = last_number + 1 + index  # Increment for each lead
                    except (IndexError, ValueError):
                        new_number = 1000 + index
                else:
                    new_number = 1000 + index
                
                lead_id = f"LD-{new_number}"
                
                # Round-robin assignment
                assigned_to = None
                assigned_to_name = "Unassigned"
                assignment_method = "unassigned"
                
                if assignable_users:
                    user = assignable_users[current_user_index % len(assignable_users)]
                    assigned_to = user["email"]
                    assigned_to_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                    if not assigned_to_name:
                        assigned_to_name = user.get('email', 'Unknown')
                    assignment_method = "round_robin_bulk"
                    current_user_index += 1
                
                # Create lead document
                lead_doc = {
                    "lead_id": lead_id,
                    "name": name,
                    "email": email.lower(),
                    "contact_number": contact_number,
                    "phone_number": contact_number,
                    "source": lead_data.get("source", "bulk_import"),
                    "status": "open",
                    "assigned_to": assigned_to,
                    "assigned_to_name": assigned_to_name,
                    "assignment_method": assignment_method,
                    "tags": lead_data.get("tags", []),
                    "notes": lead_data.get("notes", ""),
                    "created_by": current_user["_id"],
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                
                # Insert lead
                result = await db.leads.insert_one(lead_doc)
                
                # Update user array if assigned
                if assigned_to:
                    await db.users.update_one(
                        {"email": assigned_to},
                        {
                            "$push": {"assigned_leads": lead_id},
                            "$inc": {"total_assigned_leads": 1}
                        }
                    )
                
                # Log activity
                await db.lead_activities.insert_one({
                    "lead_id": lead_id,
                    "activity_type": "lead_created",
                    "description": f"Lead '{name}' created via bulk import",
                    "created_by": current_user["_id"],
                    "created_by_name": f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip(),
                    "created_at": datetime.utcnow(),
                    "metadata": {
                        "bulk_import": True,
                        "batch_index": index,
                        "assignment_method": assignment_method
                    }
                })
                
                results.append({
                    "index": index,
                    "status": "created",
                    "lead_id": lead_id,
                    "assigned_to": assigned_to,
                    "assigned_to_name": assigned_to_name
                })
                
                successful_creates += 1
                
            except Exception as lead_error:
                logger.error(f"Error creating lead {index}: {str(lead_error)}")
                results.append({
                    "index": index,
                    "status": "failed",
                    "error": str(lead_error),
                    "input_data": lead_data
                })
                failed_creates += 1
        
        logger.info(f"✅ Bulk create completed: {successful_creates} created, {failed_creates} failed")
        
        return {
            "success": True,
            "message": f"Bulk creation completed: {successful_creates} leads created, {failed_creates} failed",
            "summary": {
                "total_attempted": len(leads_data),
                "successful_creates": successful_creates,
                "failed_creates": failed_creates,
                "duplicates_skipped": len([r for r in results if r.get("reason") == "duplicate"])
            },
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk lead creation error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create leads in bulk: {str(e)}"
        )