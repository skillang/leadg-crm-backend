# app/routers/leads.py - Complete Updated with Selective Round Robin & Multi-Assignment (CORRECTED)

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, date
import logging
from bson import ObjectId


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

# OLD_TO_NEW_STATUS_MAPPING = {
#     "open": "Initial",
#     "new": "Initial",
#     "pending": "Initial",
#     "cold": "Initial",
#     "initial": "Initial",
#     "in_progress": "Warm", 
#     "contacted": "Prospect",
#     "qualified": "Prospect",
#     "closed_won": "Enrolled",
#     "closed_lost": "Junk",
#     "lost": "Junk",
#     "closed": "Enrolled",
#     "follow_up": "Followup",
#     "followup": "Followup",
#     "hot": "Warm",
#     "converted": "Enrolled",
#     "rejected": "Junk",
#     "invalid": "INVALID",
#     "callback": "Call Back",
#     "call_back": "Call Back",
#     "no_response": "NI",
#     "no_interest": "NI",
#     "busy": "Busy",
#     "ringing": "Ringing",
#     "wrong_number": "Wrong Number",
#     "dnp": "DNP",
#     "enrolled": "Enrolled",
# }

# VALID_NEW_STATUSES = [
#     "Initial", "Followup", "Warm", "Prospect", "Junk", "Enrolled", "Yet to call",
#     "Counseled", "DNP", "INVALID", "Call Back", "Busy", "NI", "Ringing", "Wrong Number"
# ]

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
                query_filters["$or"] = [
                    {"assigned_to": assigned_to_user},
                    {"co_assignees": assigned_to_user}
                ]
        
        # Get total count
        total_count = await db.leads.count_documents(query_filters)
        
        # Get leads with pagination
        skip = (page - 1) * limit
        leads = await db.leads.find(query_filters).skip(skip).limit(limit).to_list(None)
        
        # Convert to extended response format
        extended_leads = []
        for lead in leads:
            extended_lead = LeadResponseExtended(
                lead_id=lead["lead_id"],
                status=lead.get("status", "Unknown"),
                name=lead.get("name", ""),
                email=lead.get("email", ""),
                contact_number=lead.get("contact_number"),
                source=lead.get("source"),
                category=lead.get("category"),
                assigned_to=lead.get("assigned_to"),
                assigned_to_name=lead.get("assigned_to_name"),
                co_assignees=lead.get("co_assignees", []),
                co_assignees_names=lead.get("co_assignees_names", []),
                is_multi_assigned=lead.get("is_multi_assigned", False),
                assignment_method=lead.get("assignment_method"),
                created_at=lead.get("created_at", datetime.utcnow()),
                updated_at=lead.get("updated_at")
            )
            extended_leads.append(extended_lead)
        
        return extended_leads
    
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
        user = await db.users.find_one({"_id": ObjectId(lead.get("created_by"))}) if lead.get("created_by") else None
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
                        date_of_birth=basic_info_data.get("date_of_birth")
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
                        date_of_birth=lead_data.get("date_of_birth")
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
                logger.warning(f"Duplicate lead detected: {structured_lead_data.basic_info.email}")
                raise HTTPException(
                    status_code=400,
                    detail=result["message"]
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

@router.get("/", response_model=LeadListResponse)
async def get_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    lead_status: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    # 🆕 NEW: Multi-assignment filters
    include_multi_assigned: bool = Query(False, description="Include multi-assigned leads"),
    assigned_to_me: bool = Query(False, description="Include leads where I'm primary or co-assignee"),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Get leads with enhanced multi-assignment support"""
    try:
        logger.info(f"Get leads requested by: {current_user.get('email')}")
        db = get_database()
        
        # Build query
        query = {}
        user_role = current_user.get("role", "user")
        user_email = current_user.get("email")
        
        if user_role != "admin":
            # Enhanced query for multi-assignment
            if assigned_to_me:
                query["$or"] = [
                    {"assigned_to": user_email},
                    {"co_assignees": user_email}
                ]
            else:
                query["assigned_to"] = user_email
        
        # Handle status filtering with migration support
        if lead_status:
            possible_old_statuses = [k for k, v in OLD_TO_NEW_STATUS_MAPPING.items() if v == lead_status]
            status_conditions = [{"status": lead_status}]
            if possible_old_statuses:
                status_conditions.extend([{"status": old_status} for old_status in possible_old_statuses])
            
            if "$or" in query:
                query = {"$and": [query, {"$or": status_conditions}]}
            else:
                query["$or"] = status_conditions
        
        # Multi-assignment filter
        if include_multi_assigned:
            multi_condition = {"is_multi_assigned": True}
            if "$and" in query:
                query["$and"].append(multi_condition)
            else:
                query.update(multi_condition)
        
        if assigned_to and user_role == "admin":
            assigned_condition = {
                "$or": [
                    {"assigned_to": assigned_to},
                    {"co_assignees": assigned_to}
                ]
            }
            if "$and" in query:
                query["$and"].append(assigned_condition)
            else:
                query.update(assigned_condition)
        
        if search:
            search_condition = {
                "$or": [
                    {"name": {"$regex": search, "$options": "i"}},
                    {"email": {"$regex": search, "$options": "i"}},
                    {"lead_id": {"$regex": search, "$options": "i"}},
                    {"contact_number": {"$regex": search, "$options": "i"}},  # Add this line
                    {"phone_number": {"$regex": search, "$options": "i"}}     
                ]
            }
            if "$and" in query:
                query["$and"].append(search_condition)
            else:
                query.update(search_condition)
        
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
        
        # Convert ObjectIds before creating response model
        final_leads = convert_objectid_to_str(processed_leads)
        
        logger.info(f"Successfully processed {len(final_leads)} leads out of {len(leads)} total")
        
        return LeadListResponse(
            leads=final_leads,
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
    lead_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    # 🆕 NEW: Include co-assignments
    include_co_assignments: bool = Query(True, description="Include leads where I'm a co-assignee"),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Get leads assigned to current user with enhanced multi-assignment support"""
    try:
        db = get_database()
        user_email = current_user["email"]
        
        # Enhanced query for multi-assignment
        if include_co_assignments:
            query = {
                "$or": [
                    {"assigned_to": user_email},
                    {"co_assignees": user_email}
                ]
            }
        else:
            query = {"assigned_to": user_email}
        
        # Handle status filtering with migration support
        if lead_status:
            possible_old_statuses = [k for k, v in OLD_TO_NEW_STATUS_MAPPING.items() if v == lead_status]
            status_conditions = [{"status": lead_status}]
            if possible_old_statuses:
                status_conditions.extend([{"status": old_status} for old_status in possible_old_statuses])
            
            query = {
                "$and": [
                    query,
                    {"$or": status_conditions}
                ]
            }
        
        if search:
            search_condition = {
                "$or": [
                    {"name": {"$regex": search, "$options": "i"}},
                    {"email": {"$regex": search, "$options": "i"}},
                    {"lead_id": {"$regex": search, "$options": "i"}},
                    {"contact_number": {"$regex": search, "$options": "i"}},  # Add this line
                    {"phone_number": {"$regex": search, "$options": "i"}}     
                ]
            }
            query = {
                "$and": [
                    query,
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
        
        return LeadListResponse(
            leads=final_leads,
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
    # 🆕 NEW: Include multi-assignment stats
    include_multi_assignment_stats: bool = Query(True, description="Include multi-assignment statistics"),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Get lead statistics with enhanced multi-assignment support"""
    try:
        db = get_database()
        user_role = current_user.get("role", "user")
        user_email = current_user.get("email")
        
        # Base pipeline
        pipeline = []
        if user_role != "admin":
            if include_multi_assignment_stats:
                # Include both primary and co-assignments
                pipeline.append({
                    "$match": {
                        "$or": [
                            {"assigned_to": user_email},
                            {"co_assignees": user_email}
                        ]
                    }
                })
            else:
                pipeline.append({"$match": {"assigned_to": user_email}})
        
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
            "followup": 0,
            "warm": 0,
            "prospect": 0,
            "junk": 0,
            "enrolled": 0,
            "yet_to_call": 0,
            "counseled": 0,
            "dnp": 0,
            "invalid": 0,
            "call_back": 0,
            "busy": 0,
            "ni": 0,
            "ringing": 0,
            "wrong_number": 0,
            "total_leads": 0,
            "my_leads": 0,
            "unassigned_leads": 0
        }
        
        # Process aggregation result with migration awareness
        for item in result:
            status_val = item["_id"]
            count = item["count"]
            stats["total_leads"] += count
            
           # Just use the status as-is and map to stats key
        if status_val:
            key = status_val.lower().replace(" ", "_")
            if key in stats:
                stats[key] += count
        # Calculate additional stats
        if user_role != "admin":
            stats["my_leads"] = stats["total_leads"]
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
            
            stats["my_leads"] = my_leads_count
            stats["unassigned_leads"] = await db.leads.count_documents({"assigned_to": None})
        
        # Add multi-assignment stats if requested
        if include_multi_assignment_stats and user_role == "admin":
            multi_assigned_count = await db.leads.count_documents({"is_multi_assigned": True})
            stats["multi_assigned_leads"] = multi_assigned_count
        
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