from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta 
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
from ..services.lead_service import lead_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/", response_model=LeadCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    lead_data: LeadCreate,
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Only admins can create leads
):
    """
    Create a new lead (Admin only)
    """
    try:
        # Create the lead
        new_lead = await lead_service.create_lead(lead_data, current_user["_id"])
        
        logger.info(f"New lead created: {new_lead['lead_id']} by {current_user['email']}")
        
        return LeadCreateResponse(
            success=True,
            message=f"Lead {new_lead['lead_id']} created successfully",
            lead={
                "id": new_lead["_id"],
                "lead_id": new_lead["lead_id"],
                "name": new_lead["name"],
                "email": new_lead["email"],
                "status": new_lead["status"]
            }
        )
        
    except Exception as e:
        logger.error(f"Lead creation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create lead"
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
        
        result = await lead_service.get_leads(filters, current_user["_id"], current_user["role"])
        
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
        
        result = await lead_service.get_leads(filters, current_user["_id"], "user")  # Force user role
        
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
    Get a specific lead by ID
    - Admins can see any lead
    - Users can only see their assigned leads
    """
    try:
        lead = await lead_service.get_lead_by_id(lead_id, current_user["_id"], current_user["role"])
        
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found or you don't have permission to view it"
            )
        
        return LeadResponse(**lead)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get lead error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve lead"
        )

@router.put("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: str,
    lead_data: LeadUpdate,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Update a lead
    - Admins can update any lead
    - Users can only update their assigned leads
    """
    try:
        success = await lead_service.update_lead(lead_id, lead_data, current_user["_id"], current_user["role"])
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found or you don't have permission to update it"
            )
        
        # Return updated lead
        updated_lead = await lead_service.get_lead_by_id(lead_id, current_user["_id"], current_user["role"])
        return LeadResponse(**updated_lead)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update lead error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update lead"
        )

@router.post("/{lead_id}/assign", response_model=LeadAssignResponse)
async def assign_lead(
    lead_id: str,
    assignment: LeadAssign,
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Only admins can assign leads
):
    """
    Assign a lead to a user (Admin only)
    """
    try:
        # Verify the user exists and has role "user"
        db = get_database()
        assignee = await db.users.find_one({"_id": ObjectId(assignment.assigned_to)})
        
        if not assignee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if assignee["role"] not in ["user", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only assign leads to users with 'user' or 'admin' role"
            )
        
        # Assign the lead
        success = await lead_service.assign_lead(lead_id, assignment.assigned_to, assignment.notes)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found"
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

@router.post("/bulk-assign", response_model=LeadBulkAssignResponse)
async def bulk_assign_leads(
    bulk_assignment: LeadBulkAssign,
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Only admins
):
    """
    Assign multiple leads to a user (Admin only)
    """
    try:
        # Verify the user exists
        db = get_database()
        assignee = await db.users.find_one({"_id": ObjectId(bulk_assignment.assigned_to)})
        
        if not assignee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        assigned_count = 0
        failed_leads = []
        
        for lead_id in bulk_assignment.lead_ids:
            try:
                success = await lead_service.assign_lead(
                    lead_id, 
                    bulk_assignment.assigned_to, 
                    bulk_assignment.notes
                )
                if success:
                    assigned_count += 1
                else:
                    failed_leads.append(lead_id)
            except Exception:
                failed_leads.append(lead_id)
        
        logger.info(f"Bulk assignment: {assigned_count} leads assigned to {assignee['email']} by {current_user['email']}")
        
        return LeadBulkAssignResponse(
            success=True,
            message=f"Successfully assigned {assigned_count} leads to {assignee['first_name']} {assignee['last_name']}",
            assigned_count=assigned_count,
            failed_leads=failed_leads
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk assignment error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign leads"
        )

@router.patch("/{lead_id}/status")
async def update_lead_status(
    lead_id: str,
    status_update: LeadStatusUpdate,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Update lead status
    - Users can update status of their assigned leads
    - Admins can update any lead status
    """
    try:
        lead_data = LeadUpdate(status=status_update.status)
        success = await lead_service.update_lead(lead_id, lead_data, current_user["_id"], current_user["role"])
        
        if not success:
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

@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Only admins can delete
):
    """
    Delete a lead (Admin only)
    """
    try:
        success = await lead_service.delete_lead(lead_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found"
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

@router.get("/users/assignable")
async def get_assignable_users(
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Only admins
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




@router.get("/debug/test")
async def debug_test(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """Debug endpoint to test components"""
    try:
        # Test database connection
        db = get_database()
        
        # Test collections
        collections = await db.list_collection_names()
        
        # Test lead service import
        from ..services.lead_service import lead_service
        
        # Test lead ID generation
        test_lead_id = await lead_service.generate_lead_id()
        
        return {
            "success": True,
            "user": current_user["email"],
            "database_connected": db is not None,
            "lead_service_loaded": True,
            "test_lead_id": test_lead_id,
            "collections": collections
        }
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        }

@router.post("/debug/simple-create")
async def debug_simple_create(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """Simple lead creation test"""
    try:
        db = get_database()
        
        # Simple document insert test
        test_doc = {
            "name": "Test Lead",
            "email": "test@example.com",
            "phone_number": "+1234567890",
            "created_by": current_user["_id"],
            "created_at": datetime.utcnow()
        }
        
        result = await db.leads.insert_one(test_doc)
        
        return {
            "success": True,
            "message": "Simple lead created",
            "lead_id": str(result.inserted_id)
        }
        
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }