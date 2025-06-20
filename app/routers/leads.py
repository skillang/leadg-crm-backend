# app/routers/leads.py - Updated for Comprehensive Lead Management

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta 
import logging
from bson import ObjectId

from ..config.database import get_database
from ..utils.dependencies import get_current_active_user, get_admin_user
from ..models.lead import (
    LeadCreateComprehensive, LeadUpdateComprehensive, LeadResponseComprehensive,
    LeadCreateResponseComprehensive, LeadAssign, LeadStatusUpdate, 
    LeadStatus, LeadSource, CourseLevel, LeadListResponse, 
    LeadCreate, LeadUpdate, LeadResponse  # Legacy models for backward compatibility
)
from ..schemas.lead import (
    LeadCreateResponse, LeadAssignResponse, LeadBulkAssign, 
    LeadBulkAssignResponse, LeadStatsResponse, LeadFilterParams
)
from ..services.lead_service import lead_service

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================================
# NEW COMPREHENSIVE ENDPOINTS
# ============================================================================

@router.post("/comprehensive", response_model=LeadCreateResponseComprehensive, status_code=status.HTTP_201_CREATED)
async def create_lead_comprehensive(
    lead_data: LeadCreateComprehensive,
    force_create: bool = Query(False, description="Create lead even if duplicates exist"),
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Only admins can create leads
):
    """
    Create a comprehensive lead with all sections and auto round-robin assignment:
    - Basic Info: name, email, contact_number, source
    - Status & Tags: stage, lead_score, priority, tags
    - Assignment: Always auto-assigned via round-robin
    - Additional Info: notes
    
    Features:
    - Automatic duplicate detection (email and phone)
    - Round-robin auto-assignment to balance workload
    - Comprehensive activity logging
    - Assignment history tracking
    """
    try:
        logger.info(f"Creating comprehensive lead by admin: {current_user['email']}")
        logger.info(f"Lead: {lead_data.basic_info.name} ({lead_data.basic_info.email})")
        
        # Create the comprehensive lead
        result = await lead_service.create_lead_comprehensive(
            lead_data, 
            current_user["_id"], 
            force_create
        )
        
        if not result["success"]:
            # Duplicate detected and force_create is False
            return LeadCreateResponseComprehensive(
                success=False,
                message=result["message"],
                lead=None,
                duplicate_check=result["duplicate_check"],
                assignment_info=None
            )
        
        # Success case
        assignment_info_text = ""
        if result.get("assignment_info") and result["assignment_info"]["assigned_to"]:
            assignee = result["assignment_info"]["assigned_to_name"]
            assignment_info_text = f" and auto-assigned to {assignee} via round-robin"
        
        logger.info(f"Lead {result['lead']['lead_id']} created successfully{assignment_info_text}")
        
        return LeadCreateResponseComprehensive(
            success=True,
            message=result["message"],
            lead=result["lead"],
            duplicate_check=result.get("duplicate_check"),
            assignment_info=result.get("assignment_info")
        )
        
    except Exception as e:
        logger.error(f"Comprehensive lead creation error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create lead: {str(e)}"
        )

@router.get("/comprehensive/{lead_id}")
async def get_lead_comprehensive(
    lead_id: str,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get comprehensive lead details with all information:
    - All basic info, status, tags, assignment details
    - Additional info including notes
    - Assignment history
    - Creator information
    """
    try:
        lead = await lead_service.get_lead_by_id_comprehensive(
            lead_id, 
            current_user.get("email", current_user.get("_id")), 
            current_user["role"]
        )
        
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found or you don't have permission to view it"
            )
        
        return {
            "success": True,
            "lead": lead
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get comprehensive lead error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve lead"
        )

@router.put("/comprehensive/{lead_id}")
async def update_lead_comprehensive(
    lead_id: str,
    lead_data: LeadUpdateComprehensive,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Update comprehensive lead with all sections:
    - Can update any section independently
    - Assignment changes are tracked in history
    - Comprehensive activity logging
    """
    try:
        logger.info(f"Updating comprehensive lead {lead_id} by {current_user['email']}")
        
        success = await lead_service.update_lead_comprehensive(
            lead_id, 
            lead_data, 
            current_user.get("email", current_user.get("_id")), 
            current_user["role"]
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found or you don't have permission to update it"
            )
        
        # Return updated lead
        updated_lead = await lead_service.get_lead_by_id_comprehensive(
            lead_id, 
            current_user.get("email", current_user.get("_id")), 
            current_user["role"]
        )
        
        return {
            "success": True,
            "message": "Lead updated successfully",
            "lead": updated_lead
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update comprehensive lead error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update lead"
        )

@router.post("/check-duplicates")
async def check_lead_duplicates(
    lead_data: LeadCreateComprehensive,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Check for duplicate leads before creation
    Returns detailed information about potential duplicates
    """
    try:
        duplicate_check = await lead_service.check_for_duplicates(lead_data)
        
        return {
            "success": True,
            "duplicate_check": duplicate_check,
            "message": f"Found {len(duplicate_check.duplicate_leads)} potential duplicates" if duplicate_check.is_duplicate else "No duplicates found"
        }
        
    except Exception as e:
        logger.error(f"Duplicate check error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check duplicates: {str(e)}"
        )

# ============================================================================
# ROUND-ROBIN AND ASSIGNMENT ENDPOINTS
# ============================================================================

@router.get("/round-robin/stats")
async def get_round_robin_statistics(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Get round-robin assignment statistics
    Shows lead distribution, balance metrics, and assignment efficiency
    """
    try:
        stats = await lead_service.get_round_robin_stats()
        
        return {
            "success": True,
            "message": "Round-robin statistics retrieved successfully",
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Error getting round-robin stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve statistics: {str(e)}"
        )

@router.post("/{lead_id}/reassign", response_model=LeadAssignResponse)
async def reassign_lead_manual(
    lead_id: str,
    assignment: LeadAssign,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Manually reassign a lead to a specific user (Admin only)
    Tracks assignment history and logs activity
    """
    try:
        logger.info(f"Manual reassignment of lead {lead_id} by admin {current_user['email']}")
        
        # Verify target user exists and is active
        db = get_database()
        assignee = await db.users.find_one({"email": assignment.assigned_to, "is_active": True})
        
        if not assignee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target user not found or inactive"
            )
        
        if assignee["role"] not in ["user", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only assign leads to users with 'user' or 'admin' role"
            )
        
        # Perform reassignment
        success = await lead_service.reassign_lead_manual(
            lead_id, 
            assignment.assigned_to, 
            current_user["_id"], 
            assignment.notes
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found or reassignment failed"
            )
        
        assignee_name = f"{assignee['first_name']} {assignee['last_name']}"
        
        logger.info(f"Lead {lead_id} manually reassigned to {assignee['email']} by {current_user['email']}")
        
        return LeadAssignResponse(
            success=True,
            message=f"Lead successfully reassigned to {assignee_name}",
            lead_id=lead_id,
            assigned_to=assignment.assigned_to,
            assigned_to_name=assignee_name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lead reassignment error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reassign lead: {str(e)}"
        )

@router.get("/assignment-history/{lead_id}")
async def get_lead_assignment_history(
    lead_id: str,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get complete assignment history for a lead
    Shows all assignment changes with timestamps and reasons
    """
    try:
        # Check lead access permissions
        if current_user["role"] != "admin":
            db = get_database()
            lead = await db.leads.find_one({
                "lead_id": lead_id,
                "assigned_to": current_user.get("email", current_user.get("_id"))
            })
            if not lead:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to view this lead's assignment history"
                )
        else:
            db = get_database()
            lead = await db.leads.find_one({"lead_id": lead_id})
            if not lead:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lead not found"
                )
        
        assignment_history = lead.get("assignment_history", [])
        
        return {
            "success": True,
            "lead_id": lead_id,
            "assignment_history": assignment_history,
            "total_assignments": len(assignment_history)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting assignment history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve assignment history: {str(e)}"
        )

@router.get("/users/assignable")
async def get_assignable_users(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Get list of users that can be assigned leads
    Returns active users with role 'user' or 'admin'
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

# ============================================================================
# LEGACY ENDPOINTS (For Backward Compatibility)
# ============================================================================

@router.post("/", response_model=LeadCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_lead_legacy(
    lead_data: LeadCreate,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Legacy lead creation endpoint (for backward compatibility)
    Automatically converts to comprehensive format and uses round-robin assignment
    """
    try:
        logger.info(f"Creating lead (legacy) by admin: {current_user['email']}")
        
        # Convert legacy format to comprehensive format
        comprehensive_data = LeadCreateComprehensive(
            basic_info={
                "name": lead_data.name,
                "email": lead_data.email,
                "contact_number": lead_data.phone_number,
                "source": lead_data.source or "website"
            },
            status_and_tags={
                "stage": "initial",
                "lead_score": 0,
                "priority": "medium",
                "tags": lead_data.tags or []
            },
            assignment={
                "assigned_to": None  # Always auto-assign
            },
            additional_info={
                "notes": lead_data.notes
            }
        )
        
        result = await lead_service.create_lead_comprehensive(
            comprehensive_data,
            current_user["_id"],
            False
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        return LeadCreateResponse(
            success=True,
            message=result["message"],
            lead={
                "id": result["lead"]["id"],
                "lead_id": result["lead"]["lead_id"],
                "name": result["lead"]["name"],
                "email": result["lead"]["email"],
                "status": result["lead"]["status"],
                "assigned_to": result["lead"]["assigned_to"],
                "assigned_to_name": result["lead"]["assigned_to_name"]
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Legacy lead creation error: {e}")
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
    - Admins see all leads
    - Users see only their assigned leads
    """
    try:
        filters = LeadFilterParams(
            page=page,
            limit=limit,
            status=status,
            assigned_to=assigned_to,
            source=source,
            course_level=course_level,
            country=country,
            search=search,
            created_from=created_from,
            created_to=created_to
        )
        
        result = await lead_service.get_leads(filters, current_user["email"], current_user["role"])
        
        return LeadListResponse(**result)
        
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
    Get leads assigned to current user
    """
    try:
        filters = LeadFilterParams(
            page=page,
            limit=limit,
            status=status,
            assigned_to=current_user["_id"],
            search=search
        )
        
        result = await lead_service.get_leads(filters, current_user["email"], "user")
        
        return LeadListResponse(**result)
        
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
    Get lead statistics for dashboard
    """
    try:
        stats = await lead_service.get_lead_stats(current_user["_id"], current_user["role"])
        return LeadStatsResponse(**stats)
        
    except Exception as e:
        logger.error(f"Get lead stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve lead statistics"
        )

@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: str,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get a specific lead by ID (Legacy endpoint)
    """
    try:
        lead = await lead_service.get_lead_by_id_comprehensive(lead_id, current_user["_id"], current_user["role"])
        
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found or you don't have permission to view it"
            )
        
        # Convert to legacy format
        legacy_lead = {
            "id": lead["id"],
            "lead_id": lead["lead_id"],
            "name": lead["name"],
            "email": lead["email"],
            "phone_number": lead["contact_number"],
            "status": lead["status"],
            "assigned_to": lead["assigned_to"],
            "assigned_to_name": lead["assigned_to_name"],
            "created_by": lead["created_by"],
            "created_by_name": lead.get("created_by_name", "Unknown"),
            "created_at": lead["created_at"],
            "updated_at": lead["updated_at"]
        }
        
        return LeadResponse(**legacy_lead)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get lead error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve lead"
        )

# ============================================================================
# DEBUG ENDPOINTS
# ============================================================================

@router.get("/debug/round-robin-test")
async def debug_round_robin_test(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """Debug endpoint to test round-robin assignment logic"""
    try:
        next_assignee = await lead_service.get_next_assignee_round_robin()
        stats = await lead_service.get_round_robin_stats()
        
        return {
            "success": True,
            "next_assignee": next_assignee,
            "current_stats": stats,
            "message": f"Round-robin would assign next lead to: {next_assignee}"
        }
        
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@router.post("/debug/test-duplicate-check")
async def debug_test_duplicate_check(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """Debug endpoint to test duplicate checking functionality"""
    try:
        # Test data that should trigger duplicate detection
        test_lead_data = LeadCreateComprehensive(
            basic_info={
                "name": "Test Duplicate User",
                "email": "existing@example.com",
                "contact_number": "+91-9876543210",
                "source": "website"
            }
        )
        
        duplicate_check = await lead_service.check_for_duplicates(test_lead_data)
        
        return {
            "success": True,
            "duplicate_check": duplicate_check,
            "message": "Duplicate check test completed"
        }
        
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }