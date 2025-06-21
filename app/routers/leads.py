# app/routers/leads.py - Updated with Comprehensive Structure Support

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from bson import ObjectId

from ..config.database import get_database
from ..utils.dependencies import get_current_active_user, get_admin_user
from ..models.lead import (
    LeadCreate, LeadUpdate, LeadResponse, LeadListResponse, 
    LeadAssign, LeadStatusUpdate, LeadStatus, LeadSource, CourseLevel
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
# CORE LEAD ENDPOINTS
# ============================================================================

# Replace the create_lead endpoint in your app/routers/leads.py with this version
# This includes round-robin assignment like your previous version
# Replace the create_lead endpoint in your app/routers/leads.py
# This integrates with all your services properly

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
    status: Optional[LeadStatus] = Query(None),
    assigned_to: Optional[str] = Query(None),
    source: Optional[LeadSource] = Query(None),
    course_level: Optional[CourseLevel] = Query(None),
    country: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    created_from: Optional[str] = Query(None),
    created_to: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get leads with filters and pagination
    """
    try:
        db = get_database()
        query = {}
        
        # Role-based filtering
        if current_user["role"] != "admin":
            query["assigned_to"] = current_user["email"]
        
        # Apply filters
        if status:
            query["status"] = status
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
                {"lead_id": {"$regex": search, "$options": "i"}}
            ]
        
        total = await db.leads.count_documents(query)
        skip = (page - 1) * limit
        
        leads = await db.leads.find(query).skip(skip).limit(limit).sort("created_at", -1).to_list(None)
        
        # Fix ObjectId serialization
        for lead in leads:
            lead["id"] = str(lead["_id"])
            lead["created_by"] = str(lead.get("created_by", ""))
        
        return LeadListResponse(
            leads=leads,
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

@router.get("/my-leads", response_model=LeadListResponse)
async def get_my_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[LeadStatus] = Query(None),
    search: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get leads assigned to current user (Traditional method)
    """
    try:
        db = get_database()
        query = {"assigned_to": current_user["email"]}
        
        if status:
            query["status"] = status
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
                {"lead_id": {"$regex": search, "$options": "i"}}
            ]
        
        total = await db.leads.count_documents(query)
        skip = (page - 1) * limit
        
        leads = await db.leads.find(query).skip(skip).limit(limit).sort("created_at", -1).to_list(None)
        
        # Fix ObjectId serialization
        for lead in leads:
            lead["id"] = str(lead["_id"])
            lead["created_by"] = str(lead.get("created_by", ""))
            lead["assigned_to_name"] = f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip()
        
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve your leads"
        )

@router.get("/stats", response_model=LeadStatsResponse)
async def get_lead_stats(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get lead statistics for dashboard (FIXED VERSION)
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
        
        stats = {
            "total_leads": 0,
            "open_leads": 0,
            "in_progress_leads": 0,
            "closed_won_leads": 0,
            "closed_lost_leads": 0,
            "my_leads": 0,
            "unassigned_leads": 0
        }
        
        for item in result:
            status_val = item["_id"]
            count = item["count"]
            stats["total_leads"] += count
            
            if status_val == "open":
                stats["open_leads"] = count
            elif status_val == "in_progress":
                stats["in_progress_leads"] = count
            elif status_val == "closed_won":
                stats["closed_won_leads"] = count
            elif status_val == "closed_lost":
                stats["closed_lost_leads"] = count
        
        # FIXED: Get user-specific stats
        if current_user["role"] != "admin":
            stats["my_leads"] = stats["total_leads"]
        else:
            # For admin, get their email first, then count their leads
            admin_user = await db.users.find_one({"_id": ObjectId(current_user["_id"])})
            admin_email = admin_user["email"] if admin_user else ""
            my_leads_count = await db.leads.count_documents({"assigned_to": admin_email})
            stats["my_leads"] = my_leads_count
            
            unassigned_count = await db.leads.count_documents({"assigned_to": None})
            stats["unassigned_leads"] = unassigned_count
        
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
    Get a specific lead by ID
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
        
        # Fix ObjectId serialization
        lead["id"] = str(lead["_id"])
        lead["created_by"] = str(lead.get("created_by", ""))
        
        return {
            "success": True,
            "lead": lead
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get lead error: {e}")
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

@router.patch("/{lead_id}/status")
async def update_lead_status(
    lead_id: str,
    status_update: LeadStatusUpdate,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Update lead status
    """
    try:
        db = get_database()
        
        query = {"lead_id": lead_id}
        if current_user["role"] != "admin":
            query["assigned_to"] = current_user["email"]
        
        result = await db.leads.update_one(
            query,
            {
                "$set": {
                    "status": status_update.status,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found or you don't have permission to update it"
            )
        
        return {
            "success": True,
            "message": f"Lead status updated to {status_update.status}",
            "lead_id": lead_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update lead status error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update lead status"
        )
# Replace the update_lead endpoint in your app/routers/leads.py

@router.put("/{lead_id}")
async def update_lead(
    lead_id: str,
    lead_data: LeadUpdate,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Update a lead - FIXED ObjectId serialization
    """
    try:
        db = get_database()
        
        # Check permissions
        query = {"lead_id": lead_id}
        if current_user["role"] != "admin":
            query["assigned_to"] = current_user["email"]
        
        # Prepare update data
        update_data = {}
        for field, value in lead_data.dict(exclude_unset=True).items():
            if value is not None:
                update_data[field] = value
        
        update_data["updated_at"] = datetime.utcnow()
        
        result = await db.leads.update_one(query, {"$set": update_data})
        
        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found or you don't have permission to update it"
            )
        
        # Return updated lead with ObjectId conversion
        updated_lead = await db.leads.find_one({"lead_id": lead_id})
        
        # ✅ FIX: Convert ALL ObjectIds to strings
        clean_lead = {}
        for key, value in updated_lead.items():
            if key == "_id" or key == "created_by":
                clean_lead[key] = str(value) if value else None
            elif isinstance(value, list):
                # Handle arrays that might contain ObjectIds
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
                    else:
                        clean_array.append(item)
                clean_lead[key] = clean_array
            else:
                clean_lead[key] = value
        
        clean_lead["id"] = clean_lead["_id"]
        
        return {
            "success": True,
            "message": "Lead updated successfully",
            "lead": clean_lead
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update lead error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update lead"
        )

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
# UTILITY ENDPOINTS
# ============================================================================

@router.get("/users/assignable")
async def get_assignable_users(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Get list of users that can be assigned leads (Admin only)
    """
    try:
        db = get_database()
        users = await db.users.find(
            {"role": {"$in": ["user", "admin"]}, "is_active": True},
            {"first_name": 1, "last_name": 1, "email": 1, "role": 1, "department": 1}
        ).to_list(None)
        
        assignable_users = []
        for user in users:
            assignable_users.append({
                "id": str(user["_id"]),
                "name": f"{user['first_name']} {user['last_name']}",
                "email": user["email"],
                "role": user["role"],
                "department": user.get("department")
            })
        
        return {
            "success": True,
            "users": assignable_users
        }
        
    except Exception as e:
        logger.error(f"Get assignable users error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve assignable users"
        )