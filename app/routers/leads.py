# app/routers/leads.py - Complete Updated with Selective Round Robin & Multi-Assignment (CORRECTED)

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, date
import logging
from bson import ObjectId
from ..services.tata_call_service import tata_call_service
from app.decorators.timezone_decorator import convert_lead_dates, convert_dates_to_ist
from ..services.user_lead_array_service import user_lead_array_service
from ..services.lead_assignment_service import lead_assignment_service
from app.services import lead_category_service
from ..services.lead_category_service import lead_category_service
from ..config.database import get_database
from ..utils.dependencies import get_current_active_user, get_admin_user, get_user_with_single_lead_permission, get_user_with_bulk_lead_permission

# Updated imports with new models
from ..models.lead import (
    LeadCreate, 
    LeadUpdate, 
    LeadResponse, 
    LeadListResponse, 
    LeadAssign, 
  
    LeadBulkCreate, 
    LeadBulkCreateResponse,
    LeadCreateComprehensive,
    LeadResponseComprehensive, 
    LeadStatusUpdate,
   
    ExperienceLevel,
    # New models for selective round robin and multi-assignment
    SelectiveRoundRobinRequest,
    MultiUserAssignmentRequest,
    RemoveFromAssignmentRequest,
    BulkAssignmentRequest,
    MultiUserAssignmentResponse,
    BulkAssignmentResponse,
    SelectiveRoundRobinResponse,
    LeadResponseExtended,
    UserSelectionResponse,
    UserSelectionOption,
    CallCountRefreshRequest,
    CallCountRefreshResponse,
    BulkCallCountRefreshRequest,
    BulkCallCountRefreshResponse,
     CallStatsModel,
)

# Check if these exist - if not, comment them out
from ..schemas.lead import (
    LeadCreateResponse, 
    LeadAssignResponse, 
    LeadBulkAssign, 
    LeadBulkAssignResponse, 
    LeadStatsResponse, 
    LeadFilterParams
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================================
# OBJECTID CONVERSION UTILITY
# ============================================================================

def convert_objectid_to_str(obj):
    """Recursively convert ObjectId to string in any data structure"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: convert_objectid_to_str(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid_to_str(item) for item in obj]
    else:
        return obj

# ============================================================================
# STATUS MIGRATION UTILITIES
# ============================================================================


DEFAULT_NEW_LEAD_STATUS = "Initial"


# ============================================================================
# 🆕 NEW: SELECTIVE ROUND ROBIN ENDPOINTS
# ============================================================================

@router.post("/assignment/selective-round-robin/test", response_model=SelectiveRoundRobinResponse)
async def test_selective_round_robin(
    request: SelectiveRoundRobinRequest,
    current_user: dict = Depends(get_admin_user)
):
    """Test selective round robin assignment (Admin only)"""
    try:
        selected_user = await lead_assignment_service.get_next_assignee_selective_round_robin(
            request.selected_user_emails
        )
        
        if selected_user:
            return SelectiveRoundRobinResponse(
                success=True,
                message=f"User {selected_user} would be selected for assignment",
                selected_user=selected_user,
                available_users=request.selected_user_emails
            )
        else:
            return SelectiveRoundRobinResponse(
                success=False,
                message="No valid users available for assignment",
                selected_user=None,
                available_users=request.selected_user_emails
            )
    
    except Exception as e:
        logger.error(f"Error in selective round robin test: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test selective round robin: {str(e)}"
        )

@router.post("/assignment/bulk-assign-selective", response_model=BulkAssignmentResponse)
async def bulk_assign_leads_selective(
    request: BulkAssignmentRequest,
    current_user: dict = Depends(get_admin_user)
):
    """Bulk assign leads using selective round robin or all users (Admin only)"""
    try:
        db = get_database()
        admin_email = current_user.get("email")
        
        # Validate lead IDs exist
        existing_leads = await db.leads.find(
            {"lead_id": {"$in": request.lead_ids}},
            {"lead_id": 1}
        ).to_list(None)
        
        existing_lead_ids = [lead["lead_id"] for lead in existing_leads]
        invalid_lead_ids = set(request.lead_ids) - set(existing_lead_ids)
        
        if invalid_lead_ids:
            logger.warning(f"Invalid lead IDs: {invalid_lead_ids}")
        
        assignment_summary = []
        failed_assignments = []
        successfully_assigned = 0
        
        # Process each valid lead
        for lead_id in existing_lead_ids:
            try:
                # Get next assignee based on method
                if request.assignment_method == "selected_users":
                    assignee = await lead_assignment_service.get_next_assignee_selective_round_robin(
                        request.selected_user_emails
                    )
                else:  # all_users
                    assignee = await lead_assignment_service.get_next_assignee_round_robin()
                
                if assignee:
                    # Assign the lead
                    success = await lead_assignment_service.assign_lead_to_user(
                        lead_id=lead_id,
                        user_email=assignee,
                        assigned_by=admin_email,
                        reason=f"Bulk assignment ({request.assignment_method})"
                    )
                    
                    if success:
                        assignment_summary.append({
                            "lead_id": lead_id,
                            "assigned_to": assignee,
                            "status": "success"
                        })
                        successfully_assigned += 1
                    else:
                        failed_assignments.append({
                            "lead_id": lead_id,
                            "error": "Failed to update lead assignment"
                        })
                        assignment_summary.append({
                            "lead_id": lead_id,
                            "assigned_to": None,
                            "status": "failed",
                            "error": "Assignment update failed"
                        })
                else:
                    failed_assignments.append({
                        "lead_id": lead_id,
                        "error": "No assignee available"
                    })
                    assignment_summary.append({
                        "lead_id": lead_id,
                        "assigned_to": None,
                        "status": "failed",
                        "error": "No assignee available"
                    })
            
            except Exception as e:
                logger.error(f"Error assigning lead {lead_id}: {str(e)}")
                failed_assignments.append({
                    "lead_id": lead_id,
                    "error": str(e)
                })
                assignment_summary.append({
                    "lead_id": lead_id,
                    "assigned_to": None,
                    "status": "failed",
                    "error": str(e)
                })
        
        # Add failed assignments for invalid lead IDs
        for invalid_id in invalid_lead_ids:
            failed_assignments.append({
                "lead_id": invalid_id,
                "error": "Lead ID not found"
            })
        
        return BulkAssignmentResponse(
            success=len(failed_assignments) == 0,
            message=f"Bulk assignment completed: {successfully_assigned}/{len(request.lead_ids)} successful",
            total_leads=len(request.lead_ids),
            successfully_assigned=successfully_assigned,
            failed_assignments=failed_assignments,
            assignment_method=request.assignment_method,
            selected_users=request.selected_user_emails if request.assignment_method == "selected_users" else None,
            assignment_summary=assignment_summary
        )
    
    except Exception as e:
        logger.error(f"Error in bulk selective assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to perform bulk assignment: {str(e)}"
        )

# ============================================================================
# 🆕 NEW: MULTI-USER ASSIGNMENT ENDPOINTS
# ============================================================================

@router.post("/leads/{lead_id}/assign-multiple", response_model=MultiUserAssignmentResponse)
async def assign_lead_to_multiple_users(
    lead_id: str,
    request: MultiUserAssignmentRequest,
    current_user: dict = Depends(get_admin_user)
):
    """Assign a lead to multiple users (Admin only)"""
    try:
        db = get_database()
        
        # Validate lead exists
        lead = await db.leads.find_one({"lead_id": lead_id})
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lead {lead_id} not found"
            )
        
        admin_email = current_user.get("email")
        
        # Perform multi-user assignment
        result = await lead_assignment_service.assign_lead_to_multiple_users(
            lead_id=lead_id,
            user_emails=request.user_emails,
            assigned_by=admin_email,
            reason=request.reason
        )
        
        if result["success"]:
            return MultiUserAssignmentResponse(**result)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in multi-user assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign lead to multiple users: {str(e)}"
        )

@router.delete("/leads/{lead_id}/remove-user")
async def remove_user_from_assignment(
    lead_id: str,
    request: RemoveFromAssignmentRequest,
    current_user: dict = Depends(get_admin_user)
):
    """Remove a user from a multi-user assignment (Admin only)"""
    try:
        db = get_database()
        
        # Validate lead exists
        lead = await db.leads.find_one({"lead_id": lead_id})
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lead {lead_id} not found"
            )
        
        admin_email = current_user.get("email")
        
        # Remove user from assignment
        success = await lead_assignment_service.remove_user_from_multi_assignment(
            lead_id=lead_id,
            user_email=request.user_email,
            removed_by=admin_email,
            reason=request.reason
        )
        
        if success:
            return {
                "success": True,
                "message": f"User {request.user_email} removed from lead {lead_id}"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to remove user from assignment"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing user from assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove user from assignment: {str(e)}"
        )

@router.get("/leads/{lead_id}/assignments")
async def get_lead_assignment_details(
    lead_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Get detailed assignment information for a lead"""
    try:
        db = get_database()
        
        # Get lead with assignment details
        lead = await db.leads.find_one({"lead_id": lead_id})
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lead {lead_id} not found"
            )
        
        # Check permissions
        user_role = current_user.get("role", "user")
        user_email = current_user.get("email")
        
        if user_role != "admin":
            # Check if user is assigned to this lead
            assigned_to = lead.get("assigned_to")
            co_assignees = lead.get("co_assignees", [])
            
            if user_email not in [assigned_to] + co_assignees:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view this lead's assignment details"
                )
        
        # Prepare assignment details
        assignment_details = {
            "lead_id": lead_id,
            "assigned_to": lead.get("assigned_to"),
            "assigned_to_name": lead.get("assigned_to_name"),
            "co_assignees": lead.get("co_assignees", []),
            "co_assignees_names": lead.get("co_assignees_names", []),
            "is_multi_assigned": lead.get("is_multi_assigned", False),
            "assignment_method": lead.get("assignment_method"),
            "assignment_history": lead.get("assignment_history", []),
            "total_assignees": (1 if lead.get("assigned_to") else 0) + len(lead.get("co_assignees", []))
        }
        
        return convert_objectid_to_str(assignment_details)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting assignment details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get assignment details: {str(e)}"
        )

# ============================================================================
# 🆕 NEW: USER SELECTION ENDPOINTS
# ============================================================================

@router.get("/users/assignable-with-details", response_model=UserSelectionResponse)
async def get_assignable_users_with_details(
    current_user: dict = Depends(get_admin_user)
):
    """Get all assignable users with their current lead counts and details (Admin only)"""
    try:
        db = get_database()
        
        # Get all active users with user role
        users = await db.users.find(
            {"role": "user", "is_active": True},
            {
                "email": 1,
                "first_name": 1,
                "last_name": 1,
                "total_assigned_leads": 1,
                "departments": 1,
                "is_active": 1
            }
        ).to_list(None)
        
        user_options = []
        for user in users:
            user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            if not user_name:
                user_name = user.get('email', 'Unknown')
            
            user_options.append(UserSelectionOption(
                email=user["email"],
                name=user_name,
                current_lead_count=user.get("total_assigned_leads", 0),
                is_active=user.get("is_active", True),
                departments=user.get("departments", [])
            ))
        
        # Sort by lead count (ascending) for better load balancing
        user_options.sort(key=lambda x: x.current_lead_count)
        
        return UserSelectionResponse(
            total_users=len(user_options),
            users=user_options
        )
    
    except Exception as e:
        logger.error(f"Error getting assignable users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get assignable users: {str(e)}"
        )

@router.get("/assignment/round-robin-preview")
async def preview_round_robin_assignment(
    selected_users: Optional[str] = Query(None, description="Comma-separated list of user emails for selective round robin"),
    current_user: dict = Depends(get_admin_user)
):
    """Preview next assignments in round robin without actually assigning (Admin only)"""
    try:
        selected_user_emails = None
        if selected_users:
            selected_user_emails = [email.strip() for email in selected_users.split(",") if email.strip()]
        
        # Get next few assignments
        preview_assignments = []
        for i in range(5):  # Preview next 5 assignments
            if selected_user_emails:
                next_user = await lead_assignment_service.get_next_assignee_selective_round_robin(
                    selected_user_emails
                )
            else:
                next_user = await lead_assignment_service.get_next_assignee_round_robin()
            
            preview_assignments.append({
                "position": i + 1,
                "would_assign_to": next_user
            })
        
        return {
            "assignment_method": "selected_users" if selected_user_emails else "all_users",
            "selected_users": selected_user_emails,
            "preview_assignments": preview_assignments,
            "note": "This is a preview - no actual assignments were made"
        }
    
    except Exception as e:
        logger.error(f"Error in round robin preview: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview round robin: {str(e)}"
        )

# ============================================================================
# 🆕 NEW: ENHANCED LEAD LISTING WITH MULTI-ASSIGNMENT INFO
# ============================================================================
@router.get("/leads-extended/", response_model=List[LeadResponseExtended])
async def get_leads_with_multi_assignment_info(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    include_multi_assigned: bool = Query(False, description="Filter for multi-assigned leads only"),
    assigned_to_user: Optional[str] = Query(None, description="Filter by user email (includes co-assignments)"),
    current_user: dict = Depends(get_current_active_user)
):
    """Get leads with extended multi-assignment information"""
    try:
        db = get_database()
        user_role = current_user.get("role", "user")
        user_email = current_user.get("email")
        
        # Build query filters
        query_filters = {}
        
        if user_role != "admin":
            # Regular users see leads where they are assigned (primary or co-assignee)
            query_filters["$or"] = [
                {"assigned_to": user_email},
                {"co_assignees": user_email}
            ]
        
        if include_multi_assigned:
            query_filters["is_multi_assigned"] = True
        
        if assigned_to_user:
            if user_role == "admin":  # Only admins can filter by other users
                # Fix: Handle existing query structure properly
                if "$or" in query_filters:
                    # Combine with existing conditions using $and
                    existing_or = query_filters.pop("$or")
                    query_filters = {
                        "$and": [
                            {"$or": existing_or},
                            {"$or": [
                                {"assigned_to": assigned_to_user},
                                {"co_assignees": assigned_to_user}
                            ]}
                        ]
                    }
                else:
                    query_filters["$or"] = [
                        {"assigned_to": assigned_to_user},
                        {"co_assignees": assigned_to_user}
                    ]
        
        # Get total count
        total_count = await db.leads.count_documents(query_filters)
        
        # Get leads with pagination
        skip = (page - 1) * limit
        leads = await db.leads.find(query_filters).skip(skip).limit(limit).to_list(None)
        
        # Convert to extended response format with proper processing
        extended_leads = []
        for lead in leads:
            try:
                # Process the lead through the standard processing function first
                processed_lead = await process_lead_for_response(lead, db, current_user)
                
                # Create the extended lead response
                extended_lead = LeadResponseExtended(
                    lead_id=processed_lead["lead_id"],
                    status=processed_lead.get("status", "Unknown"),
                    name=processed_lead.get("name", ""),
                    email=processed_lead.get("email", ""),
                    contact_number=processed_lead.get("contact_number"),
                    source=processed_lead.get("source"),  # This will now be correct after processing
                    category=processed_lead.get("category"),
                    assigned_to=processed_lead.get("assigned_to"),
                    assigned_to_name=processed_lead.get("assigned_to_name"),
                    co_assignees=processed_lead.get("co_assignees", []),
                    co_assignees_names=processed_lead.get("co_assignees_names", []),
                    is_multi_assigned=processed_lead.get("is_multi_assigned", False),
                    assignment_method=processed_lead.get("assignment_method"),
                    created_at=processed_lead.get("created_at", datetime.utcnow()),
                    updated_at=processed_lead.get("updated_at")
                )
                extended_leads.append(extended_lead)
            except Exception as lead_error:
                logger.error(f"Error processing lead {lead.get('lead_id', 'unknown')} in extended view: {lead_error}")
                # Create a minimal response for failed leads
                try:
                    extended_lead = LeadResponseExtended(
                        lead_id=lead.get("lead_id", "unknown"),
                        status=lead.get("status", "Unknown"),
                        name=lead.get("name", ""),
                        email=lead.get("email", ""),
                        contact_number=lead.get("contact_number", ""),
                        source=lead.get("source", "website"),  # Use default if processing failed
                        category=lead.get("category", ""),
                        assigned_to=lead.get("assigned_to"),
                        assigned_to_name=lead.get("assigned_to_name", "Unknown"),
                        co_assignees=lead.get("co_assignees", []),
                        co_assignees_names=lead.get("co_assignees_names", []),
                        is_multi_assigned=lead.get("is_multi_assigned", False),
                        assignment_method=lead.get("assignment_method"),
                        created_at=lead.get("created_at", datetime.utcnow()),
                        updated_at=lead.get("updated_at")
                    )
                    extended_leads.append(extended_lead)
                except Exception as fallback_error:
                    logger.error(f"Failed to create even minimal response for lead {lead.get('lead_id', 'unknown')}: {fallback_error}")
                    continue
        
        # Convert ObjectIds to strings for JSON serialization
        final_leads = convert_objectid_to_str(extended_leads)
        
        # Return with pagination metadata
        return {
            "leads": final_leads,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_count,
                "total_pages": (total_count + limit - 1) // limit,
                "has_next": skip + limit < total_count,
                "has_prev": page > 1
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting extended leads: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get leads: {str(e)}"
        )



# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def process_lead_for_response(lead: Dict[str, Any], db, current_user: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Process a lead document for API response with complete data transformation
    This function ensures all leads are properly formatted for Pydantic validation
    """
    try:
        # Basic field transformations
        lead["id"] = str(lead["_id"])
        lead["created_by"] = str(lead.get("created_by", ""))
        
       
        if not lead.get("status"):
            lead["status"] = DEFAULT_NEW_LEAD_STATUS
        
        
        if "lead_score" not in lead or lead["lead_score"] is None:
            lead["lead_score"] = 0
        elif not isinstance(lead["lead_score"], (int, float)):
            lead["lead_score"] = 0
        
        # 🆕 NEW: Handle new optional fields with proper defaults
        lead["age"] = lead.get("age")  # Keep None if not set
        lead["experience"] = lead.get("experience","")  # Keep None if not set
        lead["nationality"] = lead.get("nationality","")  # Keep None if not set
        lead["current_location"] = lead.get("current_location","")
        lead["date_of_birth"] = lead.get("date_of_birth","") 
        
        # Ensure all required fields have proper defaults
        required_defaults = {
            "tags": [],
            "contact_number": lead.get("phone_number", ""),
            "source": "website",
            "category": lead.get("category", ""),
        }
        
        for field, default_value in required_defaults.items():
            if field not in lead or lead[field] is None:
                lead[field] = default_value
        
        # Handle new multi-assignment fields
        lead["co_assignees"] = lead.get("co_assignees", [])
        lead["co_assignees_names"] = lead.get("co_assignees_names", [])
        lead["is_multi_assigned"] = lead.get("is_multi_assigned", False)
        
        # Fetch user info for created_by
        # FIXED CODE with ObjectId validation
        created_by = lead.get("created_by")
        user = None
        if created_by:
            if ObjectId.is_valid(created_by):
                # created_by is a valid ObjectId
                user = await db.users.find_one({"_id": ObjectId(created_by)})
            else:
                # created_by is likely an email address (legacy data)
                user = await db.users.find_one({"email": created_by})
        if user:
            full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            lead["created_by_name"] = full_name if full_name else user.get('email', 'Unknown User')
        else:
            lead["created_by_name"] = "Unknown User"
        
        # Fetch assigned user info
        if lead.get("assigned_to"):
            assigned_user = await db.users.find_one({"email": lead["assigned_to"]})
            if assigned_user:
                full_name = f"{assigned_user.get('first_name', '')} {assigned_user.get('last_name', '')}".strip()
                lead["assigned_to_name"] = full_name if full_name else assigned_user.get('email', 'Unknown')
            else:
                lead["assigned_to_name"] = lead["assigned_to"]
        
        # Fetch co-assignee names
        if lead.get("co_assignees"):
            co_assignee_names = []
            for email in lead["co_assignees"]:
                user = await db.users.find_one({"email": email})
                if user:
                    full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                    co_assignee_names.append(full_name if full_name else email)
                else:
                    co_assignee_names.append(email)
            lead["co_assignees_names"] = co_assignee_names
        
        # Handle current user name
        if current_user:
            full_name = f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip()
            lead["assigned_to_name"] = full_name if full_name else current_user.get('email', 'Unknown')
        else:
            lead["assigned_to_name"] = None
        
        return lead
        
    except Exception as e:
        logger.error(f"Error processing lead {lead.get('lead_id', 'unknown')}: {e}")
        # Return lead with minimal processing to avoid complete failure
        lead["id"] = str(lead["_id"])
        # REMOVED: Automatic migration here too
        # lead["status"] = migrate_status_value(lead.get("status", DEFAULT_NEW_LEAD_STATUS))
        
        # Just use status as-is with default if empty
        if not lead.get("status"):
            lead["status"] = DEFAULT_NEW_LEAD_STATUS
            
        lead["lead_score"] = 0
        lead["created_by_name"] = "Unknown User"
        lead["assigned_to_name"] = "Unknown"
        lead["tags"] = []
        lead["contact_number"] = lead.get("phone_number", "")
        lead["source"] = "website"
        lead["category"] = lead.get("category", "")
        # Set defaults for new fields
        lead["age"] = lead.get("age")
        lead["experience"] = lead.get("experience","")
        lead["nationality"] = lead.get("nationality","")
        lead["date_of_birth"]=lead.get("date_of_birth")
        lead["current_location"] = lead.get("current_location","")
        # Set defaults for multi-assignment fields
        lead["co_assignees"] = lead.get("co_assignees", [])
        lead["co_assignees_names"] = lead.get("co_assignees_names", [])
        lead["is_multi_assigned"] = lead.get("is_multi_assigned", False)
        return lead
def transform_lead_to_structured_format(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Transform flat lead document to structured comprehensive format"""
    # Clean ObjectIds first using our utility function
    clean_lead = convert_objectid_to_str(lead)
    
    # Transform to structured format
    structured_lead = {
        "basic_info": {
            "name": clean_lead.get("name", ""),
            "email": clean_lead.get("email", ""),
            "contact_number": clean_lead.get("contact_number", ""),
            "source": clean_lead.get("source", "website"),
            "country_of_interest": clean_lead.get("country_of_interest", ""),
            "course_level": clean_lead.get("course_level", ""),
            "category": clean_lead.get("category", ""),
            # Add new fields to structured format
            "age": clean_lead.get("age"),
            "experience": clean_lead.get("experience"),
            "nationality": clean_lead.get("nationality"),
            "date_of_birth": clean_lead.get("date_of_birth"),
            "current_location": clean_lead.get("current_location",""),
            "call_stats": clean_lead.get("call_stats"),
        },
        "status_and_tags": {
            "stage": clean_lead.get("stage", "initial"),
            "status":clean_lead.get("status"),
            "lead_score": clean_lead.get("lead_score", 0),
            "priority": clean_lead.get("priority", "medium"),
            "tags": clean_lead.get("tags", [])
        },
        "assignment": {
            "assigned_to": clean_lead.get("assigned_to"),
            "assigned_to_name": clean_lead.get("assigned_to_name"),
            "co_assignees": clean_lead.get("co_assignees", []),
            "co_assignees_names": clean_lead.get("co_assignees_names", []),
            "is_multi_assigned": clean_lead.get("is_multi_assigned", False),
            "assignment_method": clean_lead.get("assignment_method"),
            "assignment_history": clean_lead.get("assignment_history", [])
        },
        "additional_info": {
            "notes": clean_lead.get("notes", "")
        },
        "system_info": {
            "id": str(clean_lead["_id"]) if "_id" in clean_lead else clean_lead.get("id"),
            "lead_id": clean_lead.get("lead_id", ""),
            "status": clean_lead.get("status") or DEFAULT_NEW_LEAD_STATUS,
            "created_by": clean_lead.get("created_by", ""),
            "created_at": clean_lead.get("created_at"),
            "updated_at": clean_lead.get("updated_at"),
            "last_contacted": clean_lead.get("last_contacted")
        }
    }
    
    return structured_lead

def format_lead_response(lead_doc: dict) -> dict:
    """Format lead document for API response with new fields"""
    if not lead_doc:
        return None
        
    return {
        "id": str(lead_doc["_id"]),
        "lead_id": lead_doc["lead_id"],
        "name": lead_doc["name"],
        "email": lead_doc["email"],
        "phone_number": lead_doc.get("phone_number", ""),
        "contact_number": lead_doc.get("contact_number", ""),
        "country_of_interest": lead_doc.get("country_of_interest", ""),
        "course_level": lead_doc.get("course_level", ""),
        "source": lead_doc["source"],
        "category": lead_doc.get("category", ""),
        
        # Include new fields in response
        "age": lead_doc.get("age",""),
        "experience": lead_doc.get("experience",""),
        "nationality": lead_doc.get("nationality",""),
        "date_of_birth": lead_doc.get("birth_of_date"),
        "current_location": lead_doc.get("current_location",""),  # 🆕 NEW: Added current_location with default
        
        # Multi-assignment fields
        "co_assignees": lead_doc.get("co_assignees", []),
        "co_assignees_names": lead_doc.get("co_assignees_names", []),
        "is_multi_assigned": lead_doc.get("is_multi_assigned", False),
        
        "stage": lead_doc.get("stage", "initial"),
        "lead_score": lead_doc.get("lead_score", 0),
        "priority": lead_doc.get("priority", "medium"),
        "tags": lead_doc.get("tags", []),
        "status": lead_doc["status"],
        "assigned_to": lead_doc.get("assigned_to"),
        "assigned_to_name": lead_doc.get("assigned_to_name"),
        "assignment_method": lead_doc.get("assignment_method"),
        "assignment_history": lead_doc.get("assignment_history", []),
        "notes": lead_doc.get("notes"),
        "created_by": lead_doc["created_by"],
        "created_by_name": lead_doc.get("created_by_name", "Unknown"),
        "created_at": lead_doc["created_at"],
        "updated_at": lead_doc["updated_at"]
    }

def get_activity_type_for_field(field_key: str) -> str:
    """Get specific activity type based on field"""
    activity_mapping = {
        "status": "status_changed",
        "stage": "stage_changed", 
        "assigned_to": "lead_reassigned",
        "name": "contact_info_updated",
        "email": "contact_info_updated",
        "phone_number": "contact_info_updated",
        "contact_number": "contact_info_updated",
        "source": "source_updated",
        "category": "category_updated",
        "priority": "priority_updated",
        "lead_score": "lead_score_updated",
        "notes": "notes_updated",
        "country_of_interest": "preferences_updated",
        "course_level": "preferences_updated",
        # Activity types for new fields
        "age": "personal_info_updated",
        "experience": "personal_info_updated",
        "nationality": "personal_info_updated",
        "date_of_birth":"date_of_birth",
        "current_location": "personal_info_updated",
    }
    return activity_mapping.get(field_key, "field_updated")

def get_field_change_description(field_name: str, old_value: any, new_value: any) -> str:
    """Generate human-readable description for field changes"""
    # Handle None values
    old_display = old_value if old_value is not None else "None"
    new_display = new_value if new_value is not None else "None"
    
    # Special cases for different field types
    if field_name == "Assigned To":
        old_display = old_display or "Unassigned"
        new_display = new_display or "Unassigned"
        return f"Lead reassigned from '{old_display}' to '{new_display}'"
    elif field_name in ["Lead Score"]:
        return f"{field_name} updated from {old_display} to {new_display}"
    else:
        return f"{field_name} changed from '{old_display}' to '{new_display}'"

# ============================================================================
# CORE ENDPOINTS (UPDATED WITH NEW FEATURES)
# ============================================================================
# ============================================================================
# 🔄 UPDATED: MAIN LEAD CREATION ENDPOINT WITH NEW ID GENERATION
# ============================================================================

@router.post("/", status_code=status.HTTP_201_CREATED)
@convert_lead_dates()
async def create_lead(
    lead_data: dict,
    force_create: bool = Query(False, description="Create lead even if duplicates exist"),
    # 🆕 NEW: Support for selective round robin
    selected_user_emails: Optional[str] = Query(None, description="Comma-separated list of user emails for selective round robin"),
    current_user: Dict[str, Any] = Depends(get_user_with_single_lead_permission) 
):
    """
    🔄 UPDATED: Create a new lead with enhanced assignment options:
    - 🆕 NEW: Category-Source combination lead IDs (NS-WB-1, SA-SM-2, WA-RF-3, etc.)
    - 🆕 NEW: Selective round robin assignment
    - 🆕 NEW: AGE, EXPERIENCE, Nationality fields (optional)
    - Duplicate detection and prevention
    - Activity logging and user array updates
    """
    try:
        logger.info(f"Creating lead by admin: {current_user['email']}")
        
        # Parse selective round robin parameter
        selected_users = None
        if selected_user_emails:
            selected_users = [email.strip() for email in selected_user_emails.split(",") if email.strip()]
        
        # Step 1: Parse and validate incoming data
        if "basic_info" in lead_data:
            # Comprehensive format
            try:
                basic_info_data = lead_data.get("basic_info", {})
                status_and_tags_data = lead_data.get("status_and_tags", {})
                assignment_data = lead_data.get("assignment", {})
                additional_info_data = lead_data.get("additional_info", {})
                
                if not basic_info_data.get("category"):
                    raise HTTPException(
                        status_code=400,
                        detail="Category is required. Please select a valid lead category."
                    )
                
                # 🆕 NEW: Validate source is provided for new ID format
                if not basic_info_data.get("source"):
                    raise HTTPException(
                        status_code=400,
                        detail="Source is required. Please select a valid lead source."
                    )
                
                # Create structured data using the classes
                from ..models.lead import LeadCreateComprehensive, LeadBasicInfo, LeadStatusAndTags, LeadAssignmentInfo, LeadAdditionalInfo
                
                structured_lead_data = LeadCreateComprehensive(
                    basic_info=LeadBasicInfo(
                        name=basic_info_data.get("name", ""),
                        email=basic_info_data.get("email", ""),
                        contact_number=basic_info_data.get("contact_number", ""),
                        source=basic_info_data.get("source"),  # 🔄 UPDATED: Now required
                        category=basic_info_data.get("category"),
                        # Handle new optional fields
                        age=basic_info_data.get("age"),
                        experience=basic_info_data.get("experience"),
                        nationality=basic_info_data.get("nationality"),
                        current_location=basic_info_data.get("current_location"),
                        date_of_birth=basic_info_data.get("date_of_birth"),
                         call_stats=basic_info_data.get("call_stats") or CallStatsModel.create_default()
                    ),
                    status_and_tags=LeadStatusAndTags(
                        stage=status_and_tags_data.get("stage", "initial"),
                        status=status_and_tags_data.get("status", "init"),
                        lead_score=status_and_tags_data.get("lead_score", 0),
                        tags=status_and_tags_data.get("tags", [])
                    ) if status_and_tags_data else None,
                    assignment=LeadAssignmentInfo(
                        assigned_to=assignment_data.get("assigned_to")
                    ) if assignment_data else None,
                    additional_info=LeadAdditionalInfo(
                        notes=additional_info_data.get("notes")
                    ) if additional_info_data else None
                )
                
            except Exception as e:
                logger.error(f"Error parsing comprehensive lead data: {str(e)}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid lead data format: {str(e)}"
                )
        else:
            # Legacy flat format
            try:
                if not lead_data.get("category"):
                    raise HTTPException(
                        status_code=400,
                        detail="Category is required. Please select a valid lead category."
                    )
                
                # 🆕 NEW: Validate source is provided for new ID format
                if not lead_data.get("source"):
                    raise HTTPException(
                        status_code=400,
                        detail="Source is required. Please select a valid lead source."
                    )
                
                from ..models.lead import LeadCreateComprehensive, LeadBasicInfo, LeadStatusAndTags, LeadAdditionalInfo
                
                structured_lead_data = LeadCreateComprehensive(
                    basic_info=LeadBasicInfo(
                        name=lead_data.get("name", ""),
                        email=lead_data.get("email", ""),
                        contact_number=lead_data.get("contact_number", ""),
                        source=lead_data.get("source"),  # 🔄 UPDATED: Now required
                        category=lead_data.get("category"),
                        # Handle new optional fields in legacy format
                        age=lead_data.get("age"),
                        experience=lead_data.get("experience"),
                        nationality=lead_data.get("nationality"),
                        current_location=lead_data.get("current_location"),
                        date_of_birth=lead_data.get("date_of_birth"),
                        call_stats=lead_data.get("call_stats") or CallStatsModel.create_default()
                    ),
                    status_and_tags=LeadStatusAndTags(
                        stage=lead_data.get("stage", "initial"),
                        lead_score=lead_data.get("lead_score", 0),
                        status=lead_data.get("status", "init"),
                        tags=lead_data.get("tags", [])
                    ),
                    additional_info=LeadAdditionalInfo(
                        notes=lead_data.get("notes")
                    )
                )
                
            except Exception as e:
                logger.error(f"Error parsing legacy lead data: {str(e)}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid lead data format: {str(e)}"
                )
        
        # Step 2: Use the enhanced lead service with NEW ID generation
        from ..services.lead_service import lead_service
        
        # Use selective assignment if users are specified
        if selected_users and hasattr(lead_service, 'create_lead_with_selective_assignment'):
            result = await lead_service.create_lead_with_selective_assignment(
                basic_info=structured_lead_data.basic_info,
                status_and_tags=structured_lead_data.status_and_tags,
                assignment_info=structured_lead_data.assignment,
                additional_info=structured_lead_data.additional_info,
                created_by=str(current_user["_id"]),
                selected_user_emails=selected_users
            )
        else:
            # Use regular creation method with NEW ID generation
            result = await lead_service.create_lead_comprehensive(
                lead_data=structured_lead_data,
                created_by=str(current_user["_id"]),
                force_create=force_create
            )
        
        if not result["success"]:
            if result.get("duplicate_check", {}).get("is_duplicate"):
                duplicate_info = result["duplicate_check"]
                logger.warning(f"🚫 Duplicate detected: {duplicate_info.get('message', 'Duplicate found')}")
                
                # Provide detailed duplicate information
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Duplicate lead detected",
                        "message": duplicate_info.get("message"),
                        "duplicate_field": duplicate_info.get("duplicate_field"),
                        "existing_lead_id": duplicate_info.get("existing_lead_id"),
                        "existing_lead_name": duplicate_info.get("existing_lead_name"),
                        "duplicate_value": duplicate_info.get("duplicate_value")
                    }
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=result["message"]
                )
        
        logger.info(f"✅ Lead created successfully: {result.get('lead_id', 'unknown')} with NEW format (category-source-number)")
        
        # Step 3: Return successful response with enhanced info
        return convert_objectid_to_str({
            "success": True,
            "message": result.get("message", "Lead created successfully"),
            "lead_id": result.get("lead_id"),
            "lead_id_format": "category_source_combination",  # 🆕 NEW: Track format used
            "assigned_to": result.get("assigned_to"),
            "assignment_method": result.get("assignment_method"),
            "selected_users_pool": selected_users,
            "lead_id_info": result.get("lead_id_info", {}),  # 🆕 NEW: ID generation details
            "duplicate_check": result.get("duplicate_check", {
                "is_duplicate": False,
                "checked": True
            })
        })
        
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

@router.get("/")
@convert_lead_dates()  # <-- ADD THIS LINE
async def get_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    lead_status: Optional[str] = Query(None),  # ✅ Changed from LeadStatus to str
    assigned_to: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    # 🆕 NEW: Add the missing filter parameters
    stage: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    course_level: Optional[str] = Query(None),
    created_from: Optional[str] = Query(None),
    created_to: Optional[str] = Query(None),
    updated_from: Optional[str] = Query(None),     
    updated_to: Optional[str] = Query(None),       
    last_contacted_from: Optional[str] = Query(None),  
    last_contacted_to: Optional[str] = Query(None),    
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get leads with comprehensive filtering support
    """
    try:
        logger.info(f"Get leads requested by: {current_user.get('email')}")
        db = get_database()
        
        # Build query
        query = {}
        if current_user["role"] != "admin":
            query["$or"] = [
                {"assigned_to": current_user["email"]},
                {"co_assignees": {"$in": [current_user["email"]]}}
            ]
                
        # 🆕 NEW: Handle stage filter
        if stage:
            query["stage"] = stage
            
        # 🆕 NEW: Handle status filter (prefer new 'status' over old 'lead_status')
        if status:
            query["status"] = status
        elif lead_status:
            # Handle old parameter for backward compatibility
            possible_old_statuses = [k for k, v in OLD_TO_NEW_STATUS_MAPPING.items() if v == lead_status.value]
            status_conditions = [{"status": lead_status.value}]
            if possible_old_statuses:
                status_conditions.extend([{"status": old_status} for old_status in possible_old_statuses])
            query["$or"] = status_conditions
            
        # 🆕 NEW: Handle category filter
        if category:
            query["category"] = category
            
        # 🆕 NEW: Handle source filter
        if source:
            query["source"] = source
            
        # 🆕 NEW: Handle course_level filter
        if course_level:
            query["course_level"] = course_level
            
        # 🆕 NEW: Handle date range filter
        if created_from or created_to:
            date_query = {}
            if created_from:
                try:
                    date_query["$gte"] = datetime.fromisoformat(created_from)
                except ValueError:
                    pass  # Skip invalid date
            if created_to:
                try:
                    date_query["$lte"] = datetime.fromisoformat(created_to)
                except ValueError:
                    pass  # Skip invalid date
            if date_query:
                query["created_at"] = date_query

        # Handle assigned_to filter (admin only)
        if assigned_to and current_user["role"] == "admin":
            if "$or" in query:
                # Combine with existing OR condition
                query = {"$and": [{"assigned_to": assigned_to}, {"$or": query["$or"]}]}
            else:
                query["assigned_to"] = assigned_to

        # Handle updated_at date range
        if updated_from or updated_to:
            date_query = {}
            if updated_from:
                date_query["$gte"] = datetime.fromisoformat(updated_from)
            if updated_to:
                # Add end of day to include full day
                end_date = datetime.fromisoformat(updated_to)
                if updated_to == updated_from:  # Same day filter
                    end_date = end_date.replace(hour=23, minute=59, second=59)
                date_query["$lte"] = end_date
            if date_query:
                query["updated_at"] = date_query

        # Handle last_contacted date range  
        if last_contacted_from or last_contacted_to:
            date_query = {}
            if last_contacted_from:
                date_query["$gte"] = datetime.fromisoformat(last_contacted_from)
            if last_contacted_to:
                date_query["$lte"] = datetime.fromisoformat(last_contacted_to)
            if date_query:
                query["last_contacted"] = date_query
        
        # Handle search
        if search:
            search_condition = {
                "$or": [
                    {"name": {"$regex": search, "$options": "i"}},
                    {"email": {"$regex": search, "$options": "i"}},
                    {"lead_id": {"$regex": search, "$options": "i"}},
                    {"contact_number": {"$regex": search, "$options": "i"}},
                    {"phone_number": {"$regex": search, "$options": "i"}}
                ]
            }
            if "$and" in query:
                query["$and"].append(search_condition)
            elif "$or" in query:
                query = {"$and": [{"$or": query["$or"]}, search_condition]}
            else:
                query.update(search_condition)
        
        logger.info(f"Final query: {query}")  # 🔍 Debug log
        
        total = await db.leads.count_documents(query)
        skip = (page - 1) * limit
        
        leads = await db.leads.find(query).skip(skip).limit(limit).sort("created_at", -1).to_list(None)
        
        # Process leads with migration support
        processed_leads = []
        for lead in leads:
            try:
                processed_lead = await process_lead_for_response(lead, db, current_user)
                processed_leads.append(processed_lead)
            except Exception as e:
                logger.error(f"Failed to process lead {lead.get('lead_id', 'unknown')}: {e}")
                continue
        
        # Convert ObjectIds before response
        final_leads = convert_objectid_to_str(processed_leads)
        
        logger.info(f"Successfully processed {len(final_leads)} leads out of {len(leads)} total")
        
        return {
            "leads": final_leads,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit,
                "has_next": page * limit < total,
                "has_prev": page > 1
            }
        }
        
    except Exception as e:
        logger.error(f"Get leads error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve leads"
        )

@router.get("/my-leads")
@convert_lead_dates()
async def get_my_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    lead_status: Optional[str] = Query(None),  # ✅ Changed from LeadStatus to str
    search: Optional[str] = Query(None),
    # 🆕 NEW: Add the missing filter parameters
    stage: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    course_level: Optional[str] = Query(None),
    created_from: Optional[str] = Query(None),
    created_to: Optional[str] = Query(None),
    updated_from: Optional[str] = Query(None),    
    updated_to: Optional[str] = Query(None),      
    last_contacted_from: Optional[str] = Query(None), 
    last_contacted_to: Optional[str] = Query(None),   
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get leads assigned to current user with filtering support
    """
    try:
        db = get_database()
        
        # Base query to include both primary assignments and co-assignments
        base_user_query = {
            "$or": [
                {"assigned_to": current_user["email"]},
                 {"co_assignees": {"$in": [current_user["email"]]}}
            ]
        }
        
        # Start with the base user query
        query = base_user_query
        
        # 🆕 NEW: Add the same filtering logic as get_leads
        if stage:
            query["stage"] = stage
            
        if status:
            query["status"] = status
        elif lead_status:
            possible_old_statuses = [k for k, v in OLD_TO_NEW_STATUS_MAPPING.items() if v == lead_status.value]
            status_conditions = [{"status": lead_status.value}]
            if possible_old_statuses:
                status_conditions.extend([{"status": old_status} for old_status in possible_old_statuses])
            query["$or"] = status_conditions
            
        if category:
            query["category"] = category
            
        if source:
            query["source"] = source
            
        if course_level:
            query["course_level"] = course_level
            
        # Handle date range
        if created_from or created_to:
            date_query = {}
            if created_from:
                try:
                    date_query["$gte"] = datetime.fromisoformat(created_from)
                except ValueError:
                    pass
            if created_to:
                try:
                    date_query["$lte"] = datetime.fromisoformat(created_to)
                except ValueError:
                    pass
            if date_query:
                query["created_at"] = date_query
        
        # Handle updated_at date range
        if updated_from or updated_to:
            date_query = {}
            if updated_from:
                date_query["$gte"] = datetime.fromisoformat(updated_from)
            if updated_to:
                # Add end of day to include full day
                end_date = datetime.fromisoformat(updated_to)
                if updated_to == updated_from:  # Same day filter
                    end_date = end_date.replace(hour=23, minute=59, second=59)
                date_query["$lte"] = end_date
            if date_query:
                query["updated_at"] = date_query

        # Handle last_contacted date range  
        if last_contacted_from or last_contacted_to:
            date_query = {}
            if last_contacted_from:
                date_query["$gte"] = datetime.fromisoformat(last_contacted_from)
            if last_contacted_to:
                date_query["$lte"] = datetime.fromisoformat(last_contacted_to)
            if date_query:
                query["last_contacted"] = date_query
        
        # Handle search
        if search:
            search_condition = {
                "$or": [
                    {"name": {"$regex": search, "$options": "i"}},
                    {"email": {"$regex": search, "$options": "i"}},
                    {"lead_id": {"$regex": search, "$options": "i"}},
                    {"contact_number": {"$regex": search, "$options": "i"}},
                    {"phone_number": {"$regex": search, "$options": "i"}}
                ]
            }
            if "$or" in query:
                query = {
                    "$and": [
                        {"assigned_to": current_user["email"]},
                        {"$or": query["$or"]},
                        search_condition
                    ]
                }
            else:
                query = {
                    "$and": [
                        {"assigned_to": current_user["email"]},
                        search_condition
                    ]
                }
        
        total = await db.leads.count_documents(query)
        skip = (page - 1) * limit
        
        leads = await db.leads.find(query).skip(skip).limit(limit).sort("created_at", -1).to_list(None)
        
        # Process leads with migration support
        processed_leads = []
        for lead in leads:
            try:
                processed_lead = await process_lead_for_response(lead, db, current_user)
                processed_leads.append(processed_lead)
            except Exception as e:
                logger.error(f"Failed to process lead {lead.get('lead_id', 'unknown')}: {e}")
                continue
        
        # Convert ObjectIds before response
        final_leads = convert_objectid_to_str(processed_leads)
        
        return {
            "leads": final_leads,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit,
                "has_next": page * limit < total,
                "has_prev": page > 1
            }
        }
        
    except Exception as e:
        logger.error(f"Get my leads error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve your leads"
        )

@router.get("/stats", response_model=LeadStatsResponse)
@convert_dates_to_ist()
async def get_lead_stats(
    include_multi_assignment_stats: bool = Query(True, description="Include multi-assignment statistics"),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Get lead statistics with enhanced breakdown support"""
    try:
        db = get_database()
        user_role = current_user.get("role", "user")
        user_email = current_user.get("email")
        
        # Base query based on role
        if user_role != "admin":
            if include_multi_assignment_stats:
                base_query = {
                    "$or": [
                        {"assigned_to": user_email},
                        {"co_assignees": user_email}
                    ]
                }
            else:
                base_query = {"assigned_to": user_email}
        else:
            base_query = {}
        
        # Get total leads
        total_leads = await db.leads.count_documents(base_query)
        
        # Get status breakdown
        status_pipeline = [
            {"$match": base_query},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        status_result = await db.leads.aggregate(status_pipeline).to_list(None)
        
        # Get stage breakdown
        stage_pipeline = [
            {"$match": base_query},
            {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        stage_result = await db.leads.aggregate(stage_pipeline).to_list(None)
        
        # Process breakdowns into dictionaries
        status_breakdown = {item["_id"]: item["count"] for item in status_result if item["_id"]}
        stage_breakdown = {item["_id"]: item["count"] for item in stage_result if item["_id"]}
        
        # Calculate core metrics
        dnp_count = status_breakdown.get("dnp", 0)
        counseled_count = status_breakdown.get("counselled", 0)
        conversion_rate = round((counseled_count / total_leads * 100), 1) if total_leads > 0 else 0.0
        
        # Calculate my_leads and unassigned_leads
        if user_role != "admin":
            my_leads = total_leads
            unassigned_leads = 0
        else:
            if include_multi_assignment_stats:
                my_leads_count = await db.leads.count_documents({
                    "$or": [
                        {"assigned_to": user_email},
                        {"co_assignees": user_email}
                    ]
                })
            else:
                my_leads_count = await db.leads.count_documents({"assigned_to": user_email})
            
            my_leads = my_leads_count
            unassigned_leads = await db.leads.count_documents({"assigned_to": None})
        
        # Build response
        response_data = {
            "total_leads": total_leads,
            "my_leads": my_leads,
            "unassigned_leads": unassigned_leads,
            "dnp_count": dnp_count,
            "counseled_count": counseled_count,
            "conversion_rate": conversion_rate,
            "status_breakdown": status_breakdown,
            "stage_breakdown": stage_breakdown
        }
        
        # Add assignment stats for admins
        if user_role == "admin" and include_multi_assignment_stats:
            # Get workload distribution with enhanced user details
            workload_pipeline = [
                {"$match": {"assigned_to": {"$ne": None}}},
                {"$group": {"_id": "$assigned_to", "total_leads": {"$sum": 1}}},
                {"$sort": {"total_leads": -1}}
            ]
            workload_result = await db.leads.aggregate(workload_pipeline).to_list(None)
            
            # Enhanced workload distribution array
            enhanced_workload = []
            
            for item in workload_result:
                user_email = item["_id"]
                total_leads = item["total_leads"]
                
                # Get user details
                user = await db.users.find_one({"email": user_email})
                user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() if user else user_email.split('@')[0]
                
                # Get DNP count for this user from stage breakdown
                dnp_count = await db.leads.count_documents({
                    "assigned_to": user_email,
                    "stage": "dnp"
                })
                
                # Get Counselled count for this user from stage breakdown  
                counselled_count = await db.leads.count_documents({
                    "assigned_to": user_email,
                    "stage": "counselled"
                })
                
                enhanced_workload.append({
                    "name": user_name,
                    "email": user_email,
                    "total_leads": total_leads,
                    "dnp_count": dnp_count,
                    "counselled_count": counselled_count
                })
            
            multi_assigned_count = await db.leads.count_documents({"is_multi_assigned": True})
            
            # Calculate balance score
            if workload_result:
                counts = [item["total_leads"] for item in workload_result]
                avg_leads = sum(counts) / len(counts)
                variance = sum((x - avg_leads) ** 2 for x in counts) / len(counts)
                balance_score = max(0, 100 - (variance / avg_leads * 10)) if avg_leads > 0 else 100
            else:
                avg_leads = 0
                balance_score = 100
            
            response_data["assignment_stats"] = {
                "multi_assigned_leads": multi_assigned_count,
                "workload_distribution": enhanced_workload,
                "average_leads_per_user": round(avg_leads, 1),
                "assignment_balance_score": round(balance_score, 1)
            }
        
        return LeadStatsResponse(**response_data)
        
    except Exception as e:
        logger.error(f"Get lead stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve lead statistics"
        )


@router.get("/{lead_id}")
@convert_lead_dates()
async def get_lead(
    lead_id: str,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Get a specific lead by ID with enhanced multi-assignment support"""
    try:
        db = get_database()
        
        query = {"lead_id": lead_id}
        user_role = current_user.get("role", "user")
        user_email = current_user.get("email")
        
        if user_role != "admin":
            # Check both primary and co-assignments
            query = {
                "lead_id": lead_id,
                "$or": [
                    {"assigned_to": user_email},
                    {"co_assignees": user_email}
                ]
            }
        
        lead = await db.leads.find_one(query)
        
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found or you don't have permission to view it"
            )
        
        # Transform to structured format with migration support and ObjectId conversion
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
# EXISTING ENDPOINTS CONTINUED...
# ============================================================================
# Add all the remaining endpoints here (assign, update, delete, bulk operations, admin endpoints, etc.)
# Due to length limits, I'm focusing on the core corrected structure

# app/routers/leads.py - Part 2: Remaining Endpoints with Multi-Assignment Support

# ============================================================================
# ASSIGNMENT ENDPOINTS
# ============================================================================

@router.post("/{lead_id}/assign", response_model=LeadAssignResponse)
async def assign_lead(
    lead_id: str,
    assignment: LeadAssign,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """Assign a lead to a user (Admin only) - Enhanced with multi-assignment cleanup"""
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
        current_co_assignees = lead.get("co_assignees", [])
        
        # Use the assignment service for consistency
        success = await lead_assignment_service.assign_lead_to_user(
            lead_id=lead_id,
            user_email=assignment.assigned_to,
            assigned_by=current_user.get("email"),
            reason=assignment.notes or "Manual assignment"
        )
        
        if success:
            logger.info(f"Lead {lead_id} assigned to {assignee['email']} by {current_user['email']}")
            
            return LeadAssignResponse(
                success=True,
                message=f"Lead assigned to {assignee['first_name']} {assignee['last_name']}",
                lead_id=lead_id,
                assigned_to=assignment.assigned_to,
                assigned_to_name=f"{assignee['first_name']} {assignee['last_name']}"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to assign lead"
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
# UPDATE ENDPOINT WITH MULTI-ASSIGNMENT SUPPORT
# ============================================================================

@router.put("/update")
async def update_lead_universal(
    update_request: dict,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Universal lead update endpoint with enhanced multi-assignment support"""
    try:
        logger.info(f"🔄 Update by {current_user.get('email')} with data: {update_request}")
        
        db = get_database()
        
        # Get lead_id
        lead_id = update_request.get("lead_id")
        if not lead_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="lead_id is required in update request"
            )
        
        # Get current lead BEFORE updating
        lead = await db.leads.find_one({"lead_id": lead_id})
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found"
            )
        
        logger.info(f"📋 Found lead {lead_id}, currently assigned to: {lead.get('assigned_to')}")
        
        # Enhanced permission checking for multi-assignment
        user_role = current_user.get("role", "user")
        user_email = current_user.get("email")
        
        if user_role != "admin":
            # Check if user has access (primary or co-assignee)
            assigned_to = lead.get("assigned_to")
            co_assignees = lead.get("co_assignees", [])
            
            if user_email not in [assigned_to] + co_assignees:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only update leads assigned to you"
                )
        
        # Handle assignment change validation
        assignment_changed = False
        old_assignee = lead.get("assigned_to")
        old_co_assignees = lead.get("co_assignees", [])
        new_assignee = None
        
        if "assigned_to" in update_request:
            new_assignee = update_request.get("assigned_to")
            assignment_changed = (old_assignee != new_assignee)
            
            logger.info(f"🔄 Assignment change detected: '{old_assignee}' → '{new_assignee}' (Changed: {assignment_changed})")
            
            if assignment_changed and user_role != "admin":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only admins can reassign leads"
                )
            
            # Validate new assignee exists (if not None)
            if new_assignee:
                assignee = await db.users.find_one({"email": new_assignee, "is_active": True})
                if not assignee:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"User {new_assignee} not found or inactive"
                    )
                
                # Add assignee name for update
                update_request["assigned_to_name"] = f"{assignee.get('first_name', '')} {assignee.get('last_name', '')}".strip()
                logger.info(f"✅ New assignee validated: {new_assignee}")
            else:
                # Unassignment case
                update_request["assigned_to_name"] = None
                logger.info(f"🔄 Unassigning lead from {old_assignee}")
        
        # Remove lead_id from update data
        update_data = {k: v for k, v in update_request.items() if k != "lead_id"}
        
        # Prepare activities list for changes
        activities_to_log = []
        
        # Track field changes for activity logging
        for field, new_value in update_data.items():
            if field in ["updated_at", "assigned_to_name"]:  # Skip system fields
                continue
                
            old_value = lead.get(field)
            
            # Only log if value actually changed
            if old_value != new_value:
                activity_type = get_activity_type_for_field(field)
                description = get_field_change_description(field.replace("_", " ").title(), old_value, new_value)
                
                activities_to_log.append({
                    "activity_type": activity_type,
                    "description": description,
                    "metadata": {
                        "field": field,
                        "old_value": str(old_value) if old_value is not None else None,
                        "new_value": str(new_value) if new_value is not None else None
                    }
                })
        
        # Add timestamp
        update_data["updated_at"] = datetime.utcnow()
        
        # Perform the actual database update
        result = await db.leads.update_one(
            {"lead_id": lead_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found for update"
            )
        
        logger.info(f"✅ Lead {lead_id} updated in database successfully")
        
        # Enhanced user array updates for multi-assignment
        assignment_sync_error = None
        if assignment_changed:
            logger.info(f"🔄 Processing enhanced user array updates for assignment change")
            
            try:
                # Remove from old assignee's array
                if old_assignee:
                    logger.info(f"📤 Removing lead {lead_id} from {old_assignee}")
                    await user_lead_array_service.remove_lead_from_user_array(old_assignee, lead_id)
                    logger.info(f"✅ Successfully removed lead {lead_id} from {old_assignee}")
                
                # Remove from all co-assignees' arrays
                for co_assignee in old_co_assignees:
                    logger.info(f"📤 Removing lead {lead_id} from co-assignee {co_assignee}")
                    await user_lead_array_service.remove_lead_from_user_array(co_assignee, lead_id)
                    logger.info(f"✅ Successfully removed lead {lead_id} from co-assignee {co_assignee}")
                
                # Add to new assignee's array
                if new_assignee:
                    logger.info(f"📥 Adding lead {lead_id} to {new_assignee}")
                    await user_lead_array_service.add_lead_to_user_array(new_assignee, lead_id)
                    logger.info(f"✅ Successfully added lead {lead_id} to {new_assignee}")
                
                # Log assignment activity
                if old_assignee != new_assignee:
                    assignment_activity = {
                        "activity_type": "lead_reassigned",
                        "description": f"Lead reassigned from '{old_assignee or 'Unassigned'}' to '{new_assignee or 'Unassigned'}'",
                        "metadata": {
                            "old_assignee": old_assignee,
                            "new_assignee": new_assignee,
                            "reassigned_by": current_user.get("email"),
                            "previous_co_assignees": old_co_assignees
                        }
                    }
                    activities_to_log.append(assignment_activity)
                    
            except Exception as array_error:
                logger.error(f"❌ CRITICAL: Enhanced user array update failed: {str(array_error)}")
                logger.error(f"❌ Assignment details: {old_assignee} → {new_assignee}")
                
                assignment_sync_error = {
                    "error": "User array sync failed",
                    "details": str(array_error),
                    "recommendation": "Run /admin/sync-user-arrays endpoint"
                }
        else:
            logger.info(f"ℹ️ No assignment change, skipping user array updates")
        
        # Log all activities
        user_id = current_user.get("_id") or current_user.get("id")
        user_name = f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip()
        if not user_name:
            user_name = current_user.get('email', 'Unknown User')
        
        for activity in activities_to_log:
            try:
                activity_doc = {
                    "lead_object_id": lead["_id"],
                    "lead_id": lead_id,
                    "activity_type": activity["activity_type"],
                    "description": activity["description"],
                    "created_by": ObjectId(user_id) if ObjectId.is_valid(str(user_id)) else user_id,
                    "created_by_name": user_name,
                    "created_at": datetime.utcnow(),
                    "is_system_generated": True,
                    "metadata": activity["metadata"]
                }
                
                await db.lead_activities.insert_one(activity_doc)
                logger.info(f"✅ Activity logged: {activity['activity_type']} for lead {lead_id}")
                
            except Exception as activity_error:
                logger.error(f"❌ Failed to log activity for lead {lead_id}: {str(activity_error)}")
        
        # Get updated lead for response
        updated_lead = await db.leads.find_one({"lead_id": lead_id})
        formatted_lead = format_lead_response(updated_lead) if updated_lead else None
        
        logger.info(f"✅ Lead {lead_id} update completed successfully with {len(activities_to_log)} activities logged")
        
        response = {
            "success": True,
            "message": "Lead updated successfully",
            "lead": formatted_lead,
            "activities_logged": len(activities_to_log),
            "assignment_changed": assignment_changed
        }
        
        # Add sync error info if it occurred
        if assignment_changed and assignment_sync_error:
            response["warning"] = assignment_sync_error
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Update lead error: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update lead"
        )

# ============================================================================
# DELETE ENDPOINT WITH MULTI-ASSIGNMENT CLEANUP
# ============================================================================

@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """Delete a lead (Admin only) - Enhanced with multi-assignment cleanup"""
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
        co_assignees = lead.get("co_assignees", [])
        
        # Delete the lead
        result = await db.leads.delete_one({"lead_id": lead_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found"
            )
        
        # Remove from all assignees' arrays
        try:
            # Remove from primary assignee's array
            if assigned_to:
                await user_lead_array_service.remove_lead_from_user_array(assigned_to, lead_id)
            
            # Remove from all co-assignees' arrays
            for co_assignee in co_assignees:
                await user_lead_array_service.remove_lead_from_user_array(co_assignee, lead_id)
                
        except Exception as array_error:
            logger.error(f"Error updating user arrays after lead deletion: {str(array_error)}")
            # Don't fail the deletion if array update fails
        
        logger.info(f"Lead {lead_id} deleted by {current_user['email']}")
        
        return {
            "success": True,
            "message": "Lead deleted successfully",
            "lead_id": lead_id,
            "removed_from_users": [assigned_to] + co_assignees if assigned_to else co_assignees
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
# BULK OPERATIONS WITH ENHANCED ASSIGNMENT SUPPORT
# ============================================================================

@router.post("/bulk-create", status_code=status.HTTP_201_CREATED)
async def bulk_create_leads(
    leads_data: List[dict],  
    force_create: bool = Query(False, description="Create leads even if duplicates exist"),
    # 🆕 NEW: Bulk creation with selective round robin
    assignment_method: str = Query("all_users", description="Assignment method: 'all_users' or 'selected_users'"),
    selected_user_emails: Optional[str] = Query(None, description="Comma-separated user emails for selective round robin"),
    current_user: Dict[str, Any] = Depends(get_user_with_bulk_lead_permission) 
):
    """
    🔄 UPDATED: Bulk create leads with enhanced assignment options and NEW ID format
    - 🆕 NEW: Category-Source combination lead IDs (NS-WB-1, SA-SM-2, etc.)
    """
    try:
        logger.info(f"Bulk creating {len(leads_data)} leads with assignment method: {assignment_method}")
        
        # Parse selective round robin parameter
        selected_users = None
        if assignment_method == "selected_users" and selected_user_emails:
            selected_users = [email.strip() for email in selected_user_emails.split(",") if email.strip()]
            
            if not selected_users:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="selected_user_emails is required when assignment_method is 'selected_users'"
                )
        
        # 🆕 NEW: Validate all leads have required fields for new ID format
        for index, lead_data in enumerate(leads_data):
            if not lead_data.get("category"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Lead at index {index}: Category is required for new ID format"
                )
            if not lead_data.get("source"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Lead at index {index}: Source is required for new ID format"
                )
        
        # Use enhanced bulk creation service with NEW ID generation
        from ..services.lead_service import lead_service
        
        # Check if enhanced bulk creation method exists
        if hasattr(lead_service, 'bulk_create_leads_with_selective_assignment'):
            result = await lead_service.bulk_create_leads_with_selective_assignment(
                leads_data=leads_data,
                created_by=str(current_user["_id"]),
                assignment_method=assignment_method,
                selected_user_emails=selected_users
            )
            
            # 🆕 NEW: Add format info to response
            result["lead_id_format"] = "category_source_combination"
            result["format_info"] = "Generated IDs use format: {CATEGORY_SHORT}-{SOURCE_SHORT}-{NUMBER}"
            
            return convert_objectid_to_str(result)
        else:
            # Fallback to individual creation with NEW ID format
            results = []
            successful_creates = 0
            failed_creates = 0
            duplicates_skipped = 0
            
            for index, lead_data in enumerate(leads_data):
                try:
                    # Call the updated single lead endpoint
                    result = await create_lead(
                        lead_data=lead_data,
                        force_create=force_create,
                        selected_user_emails=selected_user_emails,
                        current_user=current_user
                    )
                    
                    if result.get("success"):
                        results.append({
                            "index": index,
                            "status": "created",
                            "lead_id": result.get("lead_id"),
                            "lead_id_format": "category_source_combination",  # 🆕 NEW
                            "assigned_to": result.get("assigned_to"),
                            "assignment_method": result.get("assignment_method")
                        })
                        successful_creates += 1
                    else:
                        results.append({
                            "index": index,
                            "status": "failed",
                            "error": "Single lead creation returned failure"
                        })
                        failed_creates += 1
                        
                except HTTPException as http_error:
                    if "duplicate" in str(http_error.detail).lower():
                        results.append({
                            "index": index,
                            "status": "skipped",
                            "reason": "duplicate"
                        })
                        duplicates_skipped += 1
                    else:
                        results.append({
                            "index": index,
                            "status": "failed",
                            "error": str(http_error.detail)
                        })
                        failed_creates += 1
                        
                except Exception as e:
                    results.append({
                        "index": index,
                        "status": "failed",
                        "error": str(e)
                    })
                    failed_creates += 1
            
            return {
                "success": True,
                "message": f"Bulk creation completed: {successful_creates} leads created, {duplicates_skipped} duplicates skipped, {failed_creates} failed",
                "assignment_method": assignment_method,
                "selected_users": selected_users,
                "lead_id_format": "category_source_combination",  # 🆕 NEW
                "format_info": "Generated IDs use format: {CATEGORY_SHORT}-{SOURCE_SHORT}-{NUMBER}",  # 🆕 NEW
                "summary": {
                    "total_attempted": len(leads_data),
                    "successful_creates": successful_creates,
                    "failed_creates": failed_creates,
                    "duplicates_skipped": duplicates_skipped
                },
                "results": results
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk creation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to bulk create leads: {str(e)}"
        )

# ============================================================================
# ADMIN ENDPOINTS WITH MULTI-ASSIGNMENT ENHANCEMENTS
# ============================================================================

@router.get("/my-leads-fast")
@convert_lead_dates()
async def get_my_leads_fast(
    # 🆕 NEW: Include co-assignments in fast lookup
    include_co_assignments: bool = Query(True, description="Include leads where I'm a co-assignee"),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """SUPER FAST user leads using user array lookup with enhanced multi-assignment support"""
    try:
        logger.info(f"Fast leads requested by user: {current_user.get('email')}")
        
        db = get_database()
        user_email = current_user["email"]
        user_data = await db.users.find_one({"email": user_email})
        
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        lead_ids = user_data.get("assigned_leads", [])
        
        # If including co-assignments, get those leads too
        if include_co_assignments:
            co_assigned_leads = await db.leads.find(
                {"co_assignees": user_email},
                {"lead_id": 1}
            ).to_list(None)
            
            co_assigned_ids = [lead["lead_id"] for lead in co_assigned_leads]
            
            # Combine and deduplicate
            all_lead_ids = list(set(lead_ids + co_assigned_ids))
        else:
            all_lead_ids = lead_ids
        
        total_count = len(all_lead_ids)
        
        logger.info(f"User has {total_count} leads (including co-assignments: {include_co_assignments})")
        
        if not all_lead_ids:
            return {
                "success": True,
                "leads": [],
                "total": 0,
                "message": "No leads assigned",
                "performance": "ultra_fast_array_lookup",
                "include_co_assignments": include_co_assignments
            }
        
        # Fetch lead details
        leads_cursor = db.leads.find({"lead_id": {"$in": all_lead_ids}})
        leads = await leads_cursor.to_list(None)
        
        # Process leads with migration support
        clean_leads = []
        for lead in leads:
            try:
                processed_lead = await process_lead_for_response(lead, db, current_user)
                clean_leads.append(processed_lead)
            except Exception as e:
                logger.error(f"Error processing lead {lead.get('lead_id', 'unknown')}: {e}")
                continue
        
        # Convert all ObjectIds to strings before returning
        final_leads = convert_objectid_to_str(clean_leads)
        
        logger.info(f"✅ Fast lookup returned {len(final_leads)} leads")
        
        return {
            "success": True,
            "leads": final_leads,
            "total": total_count,
            "performance": "ultra_fast_array_lookup",
            "include_co_assignments": include_co_assignments
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
    # 🆕 NEW: Include multi-assignment stats
    include_multi_assignment_stats: bool = Query(True, description="Include multi-assignment statistics"),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """SUPER FAST admin stats with enhanced multi-assignment support"""
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
            user_email = user["email"]
            lead_count = user.get("total_assigned_leads", len(user.get("assigned_leads", [])))
            
            # Get co-assignment count if requested
            co_assignment_count = 0
            if include_multi_assignment_stats:
                co_assignment_count = await db.leads.count_documents({"co_assignees": user_email})
            
            total_assigned_leads += lead_count
            
            user_stat = {
                "user_id": str(user["_id"]),
                "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                "email": user_email,
                "role": user["role"],
                "assigned_leads_count": lead_count,
            }
            
            if include_multi_assignment_stats:
                user_stat["co_assigned_leads_count"] = co_assignment_count
                user_stat["total_lead_access"] = lead_count + co_assignment_count
            
            user_stats.append(user_stat)
        
        user_stats.sort(key=lambda x: x.get("total_lead_access", x["assigned_leads_count"]), reverse=True)
        
        total_leads = await db.leads.count_documents({})
        unassigned_leads = await db.leads.count_documents({"assigned_to": None})
        
        summary = {
            "total_users": len(user_stats),
            "total_leads": total_leads,
            "assigned_leads": total_assigned_leads,
            "unassigned_leads": unassigned_leads
        }
        
        # Add multi-assignment summary if requested
        if include_multi_assignment_stats:
            multi_assigned_count = await db.leads.count_documents({"is_multi_assigned": True})
            summary["multi_assigned_leads"] = multi_assigned_count
        
        final_response = convert_objectid_to_str({
            "success": True,
            "user_stats": user_stats,
            "summary": summary,
            "include_multi_assignment_stats": include_multi_assignment_stats,
            "performance": "ultra_fast_array_lookup"
        })
        
        return final_response
        
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
    """Sync user arrays with actual lead assignments including multi-assignments"""
    try:
        logger.info(f"Enhanced array sync requested by admin: {current_user.get('email')}")
        
        db = get_database()
        sync_count = 0
        
        users = await db.users.find({}).to_list(None)
        
        for user in users:
            user_email = user["email"]
            
            # Get all leads where user is primary assignee
            primary_leads = await db.leads.find(
                {"assigned_to": user_email}, 
                {"lead_id": 1}
            ).to_list(None)
            
            # Get all leads where user is co-assignee
            co_assigned_leads = await db.leads.find(
                {"co_assignees": user_email}, 
                {"lead_id": 1}
            ).to_list(None)
            
            # Combine primary and co-assigned leads
            primary_lead_ids = [lead["lead_id"] for lead in primary_leads]
            co_assigned_ids = [lead["lead_id"] for lead in co_assigned_leads]
            
            # For user arrays, we typically track only primary assignments
            # But we can track total access in a separate field
            all_accessible_leads = list(set(primary_lead_ids + co_assigned_ids))
            
            await db.users.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {
                        "assigned_leads": primary_lead_ids,
                        "total_assigned_leads": len(primary_lead_ids),
                        "co_assigned_leads": co_assigned_ids,
                        "total_accessible_leads": len(all_accessible_leads),
                        "array_last_synced": datetime.utcnow()
                    }
                }
            )
            sync_count += 1
        
        logger.info(f"✅ Enhanced sync completed for {sync_count} users")
        
        return {
            "success": True,
            "message": f"Enhanced sync completed for {sync_count} users",
            "synced_users": sync_count,
            "includes_multi_assignment_sync": True
        }
        
    except Exception as e:
        logger.error(f"Enhanced array sync error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync arrays: {str(e)}"
        )

# ============================================================================
# MIGRATION AND ANALYSIS ENDPOINTS
# ============================================================================


# ============================================================================
# ADDITIONAL UTILITY ENDPOINTS
# ============================================================================

@router.get("/users/assignable")
async def get_assignable_users(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """Get list of users that can be assigned leads (Admin only)"""
    try:
        db = get_database()
        
        users = await db.users.find(
            {"role": "user", "is_active": True},
            {"email": 1, "first_name": 1, "last_name": 1}
        ).to_list(None)
        
        assignable_users = []
        for user in users:
            full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            assignable_users.append({
                "email": user["email"],
                "name": full_name if full_name else user["email"]
            })
        
        return {
            "success": True,
            "users": assignable_users,
            "total": len(assignable_users)
        }
        
    except Exception as e:
        logger.error(f"Get assignable users error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get assignable users"
        )

@router.post("/bulk-assign")
async def bulk_assign_leads(
    bulk_assign: LeadBulkAssign,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """Bulk assign multiple leads to users (Admin only)"""
    try:
        db = get_database()
        admin_email = current_user.get("email")
        
        results = []
        successful_assignments = 0
        failed_assignments = 0
        
        for lead_id in bulk_assign.lead_ids:
            try:
                # Check if lead exists
                lead = await db.leads.find_one({"lead_id": lead_id})
                if not lead:
                    results.append({
                        "lead_id": lead_id,
                        "status": "failed",
                        "error": "Lead not found"
                    })
                    failed_assignments += 1
                    continue
                
                # Get next assignee using round robin
                if bulk_assign.assignment_method == "round_robin":
                    assignee = await lead_assignment_service.get_next_assignee_round_robin()
                elif bulk_assign.assignment_method == "specific_user":
                    assignee = bulk_assign.assigned_to
                else:
                    assignee = None
                
                if assignee:
                    # Assign the lead
                    success = await lead_assignment_service.assign_lead_to_user(
                        lead_id=lead_id,
                        user_email=assignee,
                        assigned_by=admin_email,
                        reason="Bulk assignment"
                    )
                    
                    if success:
                        results.append({
                            "lead_id": lead_id,
                            "status": "success",
                            "assigned_to": assignee
                        })
                        successful_assignments += 1
                    else:
                        results.append({
                            "lead_id": lead_id,
                            "status": "failed",
                            "error": "Assignment failed"
                        })
                        failed_assignments += 1
                else:
                    results.append({
                        "lead_id": lead_id,
                        "status": "failed",
                        "error": "No assignee available"
                    })
                    failed_assignments += 1
                    
            except Exception as e:
                logger.error(f"Error assigning lead {lead_id}: {str(e)}")
                results.append({
                    "lead_id": lead_id,
                    "status": "failed",
                    "error": str(e)
                })
                failed_assignments += 1
        
        return LeadBulkAssignResponse(
            success=failed_assignments == 0,
            message=f"Bulk assignment completed: {successful_assignments} successful, {failed_assignments} failed",
            total_leads=len(bulk_assign.lead_ids),
            successful_assignments=successful_assignments,
            failed_assignments=failed_assignments,
            results=results
        )
        
    except Exception as e:
        logger.error(f"Bulk assign error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to bulk assign leads"
        )

@router.patch("/{lead_id}/status")
async def update_lead_status(
    lead_id: str,
    status_update: LeadStatusUpdate,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Update lead status (Users can update leads assigned to them)"""
    try:
        db = get_database()
        user_role = current_user.get("role", "user")
        user_email = current_user.get("email")
        
        # Build query based on permissions
        query = {"lead_id": lead_id}
        if user_role != "admin":
            # Users can only update leads assigned to them (primary or co-assignee)
            query["$or"] = [
                {"assigned_to": user_email},
                {"co_assignees": user_email}
            ]
        
        lead = await db.leads.find_one(query)
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found or you don't have permission to update it"
            )
        
        # Migrate status value if needed
        new_status = migrate_status_value(status_update.status)
        old_status = lead.get("status")
        
        # Update the lead status
        update_data = {
            "status": new_status,
            "updated_at": datetime.utcnow()
        }
        
        result = await db.leads.update_one(
            {"lead_id": lead_id},
            {"$set": update_data}
        )
        
        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found"
            )
        
        # Log activity
        try:
            user_id = current_user.get("_id") or current_user.get("id")
            user_name = f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip()
            if not user_name:
                user_name = current_user.get('email', 'Unknown User')
            
            activity_doc = {
                "lead_object_id": lead["_id"],
                "lead_id": lead_id,
                "activity_type": "status_changed",
                "description": f"Status changed from '{old_status}' to '{new_status}'",
                "created_by": ObjectId(user_id) if ObjectId.is_valid(str(user_id)) else user_id,
                "created_by_name": user_name,
                "created_at": datetime.utcnow(),
                "is_system_generated": True,
                "metadata": {
                    "field": "status",
                    "old_value": old_status,
                    "new_value": new_status,
                    "notes": status_update.notes
                }
            }
            
            await db.lead_activities.insert_one(activity_doc)
            
        except Exception as activity_error:
            logger.error(f"Failed to log status change activity: {str(activity_error)}")
        
        logger.info(f"Lead {lead_id} status updated from '{old_status}' to '{new_status}' by {user_email}")
        
        return {
            "success": True,
            "message": f"Lead status updated to {new_status}",
            "lead_id": lead_id,
            "old_status": old_status,
            "new_status": new_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update lead status error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update lead status"
        )

# ============================================================================
# HEALTH CHECK AND DEBUG ENDPOINTS
# ============================================================================


@router.get("/constants/experience-levels")
async def get_experience_levels():
    """
    Get all hardcoded experience levels from the ExperienceLevel enum
    
    Returns:
        List of experience levels with value and label
    """
    try:
        experience_levels = []
        for level in ExperienceLevel:
            # Convert enum values to readable labels
            label_map = {
                "fresher": "Fresher",
                "less_than_1_year": "Less than 1 Year", 
                "1_to_3_years": "1-3 Years",
                "3_to_5_years": "3-5 Years",
                "5_to_10_years": "5-10 Years",
                "more_than_10_years": "More than 10 Years"
            }
            
            experience_levels.append({
                "value": level.value,
                "label": label_map.get(level.value, level.value.replace("_", " ").title())
            })
        
        return {
            "success": True,
            "data": experience_levels,
            "total": len(experience_levels)
        }
    except Exception as e:
        logger.error(f"Error fetching experience levels: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch experience levels"
        )
    

@router.post("/{lead_id}/refresh-call-count", response_model=CallCountRefreshResponse)
async def refresh_lead_call_count(
    lead_id: str,
    force_refresh: bool = Query(False, description="Force refresh even if recently updated"),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Refresh call count for a specific lead
    - Users can refresh leads assigned to them
    - Admins can refresh any lead
    """
    try:
        db = get_database()
        user_role = current_user.get("role", "user")
        user_email = current_user.get("email")
        
        # Check permissions
        if user_role != "admin":
            # Users can only refresh leads assigned to them (primary or co-assignee)
            lead = await db.leads.find_one({
                "lead_id": lead_id,
                "$or": [
                    {"assigned_to": user_email},
                    {"co_assignees": user_email}
                ]
            })
            if not lead:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lead not found or you don't have permission to refresh it"
                )
        else:
            # Admin check - just verify lead exists
            lead = await db.leads.find_one({"lead_id": lead_id})
            if not lead:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lead not found"
                )
        
        logger.info(f"Manual call count refresh requested for lead {lead_id} by {user_email}")
        
        # Use the call service to refresh
        result = await tata_call_service.refresh_lead_call_count(
            lead_id=lead_id,
            force_refresh=force_refresh
        )
        
        if result.get("success"):
            return CallCountRefreshResponse(
                success=True,
                message=result.get("message", "Call count refreshed successfully"),
                lead_id=lead_id,
                call_stats=result.get("call_stats"),
                refresh_time=datetime.utcnow()
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Failed to refresh call count")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing call count for lead {lead_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh call count: {str(e)}"
        )

@router.post("/bulk-refresh-call-counts", response_model=BulkCallCountRefreshResponse)
async def bulk_refresh_call_counts(
    request: BulkCallCountRefreshRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Admin only for bulk operations
):
    """
    Bulk refresh call counts for multiple leads (Admin only)
    - Can refresh specific leads by ID
    - Can refresh all leads assigned to a user
    - Can refresh all leads if no filters specified
    """
    try:
        admin_email = current_user.get("email")
        logger.info(f"Bulk call count refresh requested by admin: {admin_email}")
        
        # Use the call service for bulk refresh
        result = await tata_call_service.bulk_refresh_call_counts(
            lead_ids=request.lead_ids,
            assigned_to_user=request.assigned_to_user,
            force_refresh=request.force_refresh,
            batch_size=request.batch_size
        )
        
        if result.get("success"):
            return BulkCallCountRefreshResponse(
                success=True,
                message=result.get("message", "Bulk refresh completed"),
                total_leads=result.get("total_leads", 0),
                successful_refreshes=result.get("successful_refreshes", 0),
                failed_refreshes=result.get("failed_refreshes", 0),
                processing_time=result.get("processing_time", 0),
                failed_lead_ids=result.get("failed_lead_ids", []),
                refresh_time=datetime.utcnow()
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Bulk refresh failed")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk call count refresh: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to bulk refresh call counts: {str(e)}"
        )

@router.get("/{lead_id}/call-stats")
async def get_lead_call_stats(
    lead_id: str,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get call statistics for a specific lead
    - Shows total calls, answered calls, missed calls
    - Shows per-user breakdown
    - Users can view stats for leads assigned to them
    """
    try:
        db = get_database()
        user_role = current_user.get("role", "user")
        user_email = current_user.get("email")
        
        # Check permissions
        query = {"lead_id": lead_id}
        if user_role != "admin":
            query["$or"] = [
                {"assigned_to": user_email},
                {"co_assignees": user_email}
            ]
        
        lead = await db.leads.find_one(query)
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found or you don't have permission to view it"
            )
        
        call_stats = lead.get("call_stats")
        
        if not call_stats:
            return {
                "success": True,
                "lead_id": lead_id,
                "call_stats": None,
                "message": "No call statistics available. Click 'Refresh' to fetch call data.",
                "has_phone_number": bool(lead.get("contact_number") or lead.get("phone_number"))
            }
        
        # If user is not admin, filter user_calls to show only their own stats
        if user_role != "admin" and call_stats.get("user_calls"):
            current_user_id = str(current_user.get("_id") or current_user.get("user_id", ""))
            if current_user_id in call_stats["user_calls"]:
                user_specific_stats = {
                    **call_stats,
                    "user_calls": {current_user_id: call_stats["user_calls"][current_user_id]},
                    "your_calls": call_stats["user_calls"][current_user_id]
                }
            else:
                user_specific_stats = {
                    **call_stats,
                    "user_calls": {},
                    "your_calls": {"total": 0, "answered": 0, "missed": 0}
                }
            call_stats = user_specific_stats
        
        return {
            "success": True,
            "lead_id": lead_id,
            "call_stats": call_stats,
            "last_updated": call_stats.get("last_updated"),
            "phone_tracked": call_stats.get("phone_tracked")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting call stats for lead {lead_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get call statistics: {str(e)}"
        )

@router.post("/admin/migrate-historical-calls")
async def migrate_historical_call_data(
    batch_size: int = Query(50, ge=1, le=200, description="Number of leads to process at once"),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    One-time migration to populate call stats for existing leads (Admin only)
    This endpoint is for migrating historical data for leads that already have call history
    """
    try:
        admin_email = current_user.get("email")
        logger.info(f"Historical call data migration requested by admin: {admin_email}")
        
        # Run bulk refresh for ALL leads with force_refresh=True
        result = await tata_call_service.bulk_refresh_call_counts(
            lead_ids=None,  # All leads
            assigned_to_user=None,  # All users
            force_refresh=True,  # Force refresh even if recently updated
            batch_size=batch_size
        )
        
        if result.get("success"):
            return {
                "success": True,
                "message": "Historical call data migration completed",
                "migration_summary": {
                    "total_leads_processed": result.get("total_leads", 0),
                    "successful_migrations": result.get("successful_refreshes", 0),
                    "failed_migrations": result.get("failed_refreshes", 0),
                    "processing_time_seconds": result.get("processing_time", 0),
                    "failed_lead_ids": result.get("failed_lead_ids", [])
                },
                "next_steps": "Call statistics are now available for all leads. Users can view counts in lead details.",
                "note": "This was a one-time migration. Future calls will automatically update counts."
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Migration failed")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in historical call data migration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to migrate historical call data: {str(e)}"
        )