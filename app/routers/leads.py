# app/routers/leads.py - Complete Updated with ObjectId Fix and Enhanced User Array Sync

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging
from bson import ObjectId

from ..services.user_lead_array_service import user_lead_array_service
from app.services import lead_category_service
from ..services.lead_category_service import lead_category_service
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
# OBJECTID CONVERSION UTILITY - CRITICAL FIX
# ============================================================================

def convert_objectid_to_str(obj):
    """
    Recursively convert ObjectId to string in any data structure
    This function fixes the JSON serialization error
    """
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

# Complete mapping from old status values to new ones
OLD_TO_NEW_STATUS_MAPPING = {
    "open": "Initial",           # 🆕 Changed from "Yet to call"
    "new": "Initial",            # 🆕 Changed from "Yet to call"  
    "pending": "Initial",        # 🆕 Changed from "Yet to call"
    "cold": "Initial",           # 🆕 Changed from "Yet to call"
    "initial": "Initial",  # 🔥 NEW: Open leads become "Yet to call"
    "in_progress": "Warm", 
    "contacted": "Prospect",
    "qualified": "Prospect",
    "closed_won": "Enrolled",
    "closed_lost": "Junk",
    "lost": "Junk",
    "closed": "Enrolled",
    "follow_up": "Followup",
    "followup": "Followup",
    "hot": "Warm",
    
    "converted": "Enrolled",
    "rejected": "Junk",
    "invalid": "INVALID",
    "callback": "Call Back",
    "call_back": "Call Back",
    "no_response": "NI",
    "no_interest": "NI",
    "busy": "Busy",
    "ringing": "Ringing",
    "wrong_number": "Wrong Number",
    "dnp": "DNP",
    "enrolled": "Enrolled",
    # If status accidentally set to 'initial'
}

# Valid new status values
VALID_NEW_STATUSES = [
    "Initial", "Followup", "Warm", "Prospect", "Junk", "Enrolled", "Yet to call",
    "Counseled", "DNP", "INVALID", "Call Back", "Busy", "NI", "Ringing", "Wrong Number"
]

# Valid stage values
VALID_STAGES = ["Initial", "Followup", "Warm", "Prospect", "Junk", "Enrolled", "Yet to call",
    "Counseled", "DNP", "INVALID", "Call Back", "Busy", "NI", "Ringing", "Wrong Number"]

# 🎯 NEW LEAD DEFAULT STATUS
DEFAULT_NEW_LEAD_STATUS = "Initial"

def migrate_status_value(status: str) -> str:
    """
    Migrate old status values to new ones during transition period
    """
    if not status:
        return DEFAULT_NEW_LEAD_STATUS  # Default for empty/null status
    
    # If already valid, return as-is
    if status in VALID_NEW_STATUSES:
        return status
    
    # Map old status to new status
    mapped_status = OLD_TO_NEW_STATUS_MAPPING.get(status, DEFAULT_NEW_LEAD_STATUS)
    
    if status != mapped_status:
        logger.debug(f"Status migration: '{status}' → '{mapped_status}'")
    
    return mapped_status

# def migrate_stage_value(stage: str) -> str:
#     """
#     Migrate old stage values to new ones during transition period
#     """
#     if not stage:
#         return "initial"  # Default
    
#     # If already valid, return as-is
#     if stage in VALID_STAGES:
#         return stage
    
#     # Map common invalid stages
#     stage_mapping = {
#         "open": "initial",
#         "closed_won": "closed",
#         "closed_lost": "lost",
#         "new": "initial",
#         "pending": "initial"
#     }
    
#     mapped_stage = stage_mapping.get(stage, "initial")
    
#     if stage != mapped_stage:
#         logger.debug(f"Stage migration: '{stage}' → '{mapped_stage}'")
    
#     return mapped_stage

async def process_lead_for_response(lead: Dict[str, Any], db, current_user: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Process a lead document for API response with complete data transformation
    This function ensures all leads are properly formatted for Pydantic validation
    """
    try:
        # Basic field transformations
        lead["id"] = str(lead["_id"])
        lead["created_by"] = str(lead.get("created_by", ""))
        
        # 🔧 CRITICAL: Migrate status and stage values
        original_status = lead.get("status")
        lead["status"] = migrate_status_value(original_status)
        
        original_stage = lead.get("stage")
        # lead["stage"] = migrate_stage_value(original_stage)
        
        # Log migrations for monitoring
        if original_status != lead["status"]:
            logger.info(f"Migrated status for lead {lead.get('lead_id', 'unknown')}: '{original_status}' → '{lead['status']}'")
        if original_stage != lead["stage"]:
            logger.info(f"Migrated stage for lead {lead.get('lead_id', 'unknown')}: '{original_stage}' → '{lead['stage']}'")
        
        # Ensure lead_score exists and is valid
        if "lead_score" not in lead or lead["lead_score"] is None:
            lead["lead_score"] = 0
        elif not isinstance(lead["lead_score"], (int, float)):
            lead["lead_score"] = 0
        
        # Ensure all required fields have proper defaults
        required_defaults = {
            "tags": [],
            "contact_number": lead.get("phone_number", ""),
            "phone_number": lead.get("contact_number", ""),  # Ensure both exist
            "source": "website",
            "notes": None,
            "last_contacted": None,
            "assignment_method": None,
            "assignment_history": None,
            "country_of_interest": "",
            "course_level": None,
            "priority": "medium"
        }
        
        for field, default_value in required_defaults.items():
            if field not in lead or lead[field] is None:
                lead[field] = default_value
        
        # Ensure contact_number and phone_number are consistent
        if lead["contact_number"] and not lead["phone_number"]:
            lead["phone_number"] = lead["contact_number"]
        elif lead["phone_number"] and not lead["contact_number"]:
            lead["contact_number"] = lead["phone_number"]
        
        # Handle created_by_name
        created_by_id = lead.get("created_by")
        if created_by_id and created_by_id != "":
            try:
                user_info = await db.users.find_one({"_id": ObjectId(created_by_id)})
                if user_info:
                    full_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
                    lead["created_by_name"] = full_name if full_name else user_info.get('email', 'Unknown User')
                else:
                    lead["created_by_name"] = "Unknown User"
            except Exception as e:
                logger.error(f"Error fetching created_by user info: {e}")
                lead["created_by_name"] = "Unknown User"
        else:
            lead["created_by_name"] = "Unknown User"
        
        # Handle assigned_to_name
        if lead.get("assigned_to"):
            if not lead.get("assigned_to_name"):
                try:
                    assigned_user = await db.users.find_one({"email": lead["assigned_to"]})
                    if assigned_user:
                        full_name = f"{assigned_user.get('first_name', '')} {assigned_user.get('last_name', '')}".strip()
                        lead["assigned_to_name"] = full_name if full_name else assigned_user.get('email', 'Unknown')
                    else:
                        lead["assigned_to_name"] = lead["assigned_to"]
                except Exception as e:
                    logger.error(f"Error fetching assigned_to user info: {e}")
                    lead["assigned_to_name"] = lead.get("assigned_to", "")
        elif current_user:
            # If no assigned_to but we have current_user (for my-leads endpoint)
            full_name = f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip()
            lead["assigned_to_name"] = full_name if full_name else current_user.get('email', 'Unknown')
        else:
            lead["assigned_to_name"] = None
        
        return lead
        
    except Exception as e:
        logger.error(f"Error processing lead {lead.get('lead_id', 'unknown')}: {e}")
        # Return lead with minimal processing to avoid complete failure
        lead["id"] = str(lead["_id"])
        lead["status"] = migrate_status_value(lead.get("status", DEFAULT_NEW_LEAD_STATUS))
        lead["stage"] = migrate_stage_value(lead.get("stage", "initial"))
        lead["lead_score"] = 0
        lead["created_by_name"] = "Unknown User"
        lead["assigned_to_name"] = "Unknown"
        lead["tags"] = []
        lead["contact_number"] = lead.get("phone_number", "")
        lead["source"] = "website"
        return lead

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def transform_lead_to_structured_format(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform flat lead document to structured comprehensive format
    """
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
            "category": clean_lead.get("category", ""),  # 🔥 ADD THIS LINE
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
            "id": str(clean_lead["_id"]) if "_id" in clean_lead else clean_lead.get("id"),
            "lead_id": clean_lead.get("lead_id", ""),
            "status": migrate_status_value(clean_lead.get("status", DEFAULT_NEW_LEAD_STATUS)),  # 🔥 Updated default
            "created_by": clean_lead.get("created_by", ""),
            "created_at": clean_lead.get("created_at"),
            "updated_at": clean_lead.get("updated_at"),
            "last_contacted": clean_lead.get("last_contacted")
        }
    }
    
    return structured_lead

# ============================================================================
# ADMIN MIGRATION ENDPOINTS
# ============================================================================

@router.post("/admin/migrate-all-statuses")
async def migrate_all_lead_statuses(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Admin endpoint to migrate all lead statuses from old to new values
    This updates the database records permanently
    """
    try:
        logger.info(f"Admin migration requested by: {current_user.get('email')}")
        db = get_database()
        
        total_updated = 0
        migration_details = []
        
        # Migrate each old status to new status
        for old_status, new_status in OLD_TO_NEW_STATUS_MAPPING.items():
            count = await db.leads.count_documents({"status": old_status})
            
            if count > 0:
                result = await db.leads.update_many(
                    {"status": old_status},
                    {
                        "$set": {
                            "status": new_status,
                            "status_migration_date": datetime.utcnow(),
                            "previous_status": old_status
                        }
                    }
                )
                
                updated_count = result.modified_count
                total_updated += updated_count
                
                migration_details.append({
                    "old_status": old_status,
                    "new_status": new_status,
                    "leads_found": count,
                    "leads_updated": updated_count
                })
                
                logger.info(f"Migrated {updated_count} leads: '{old_status}' → '{new_status}'")
        
        # Fix invalid stages
        stage_fixes = 0
        invalid_stages = await db.leads.find({
            "stage": {"$nin": VALID_STAGES}
        }).to_list(None)
        
        for lead in invalid_stages:
            old_stage = lead.get("stage")
            new_stage = migrate_stage_value(old_stage)
            
            await db.leads.update_one(
                {"_id": lead["_id"]},
                {
                    "$set": {
                        "stage": new_stage,
                        "stage_migration_date": datetime.utcnow(),
                        "previous_stage": old_stage
                    }
                }
            )
            stage_fixes += 1
        
        # Ensure required fields
        field_fixes = 0
        
        # Add missing lead_score
        missing_score = await db.leads.count_documents({"lead_score": {"$exists": False}})
        if missing_score > 0:
            await db.leads.update_many(
                {"lead_score": {"$exists": False}},
                {"$set": {"lead_score": 0}}
            )
            field_fixes += missing_score
        
        # Add missing tags
        missing_tags = await db.leads.count_documents({"tags": {"$exists": False}})
        if missing_tags > 0:
            await db.leads.update_many(
                {"tags": {"$exists": False}},
                {"$set": {"tags": []}}
            )
            field_fixes += missing_tags
        
        return {
            "success": True,
            "message": f"Migration completed successfully",
            "summary": {
                "status_migrations": total_updated,
                "stage_fixes": stage_fixes,
                "field_fixes": field_fixes,
                "total_changes": total_updated + stage_fixes + field_fixes
            },
            "migration_details": migration_details
        }
        
    except Exception as e:
        logger.error(f"Admin migration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to migrate lead statuses: {str(e)}"
        )

@router.get("/admin/status-analysis")
async def analyze_lead_statuses(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Analyze current status values in the database
    """
    try:
        db = get_database()
        
        # Get status distribution
        status_pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        
        status_results = await db.leads.aggregate(status_pipeline).to_list(None)
        
        valid_statuses = []
        invalid_statuses = []
        
        for item in status_results:
            status_value = item["_id"]
            count = item["count"]
            
            if status_value in VALID_NEW_STATUSES:
                valid_statuses.append({"status": status_value, "count": count, "valid": True})
            else:
                mapped_to = OLD_TO_NEW_STATUS_MAPPING.get(status_value, DEFAULT_NEW_LEAD_STATUS)
                invalid_statuses.append({
                    "status": status_value, 
                    "count": count, 
                    "valid": False,
                    "will_migrate_to": mapped_to
                })
        
        return {
            "success": True,
            "analysis": {
                "statuses": {
                    "valid": valid_statuses,
                    "invalid": invalid_statuses,
                    "needs_migration": len(invalid_statuses) > 0
                },
                "default_new_lead_status": DEFAULT_NEW_LEAD_STATUS,
                "total_valid_statuses": len(VALID_NEW_STATUSES)
            }
        }
        
    except Exception as e:
        logger.error(f"Status analysis error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze statuses: {str(e)}"
        )

# ============================================================================
# SUPER FAST ENDPOINTS (Using User Arrays) - FIXED FOR OBJECTID
# ============================================================================

@router.get("/my-leads-fast")
async def get_my_leads_fast(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    SUPER FAST user leads using user array lookup - FIXED ObjectId serialization
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
        
        # Process leads with migration support
        clean_leads = []
        for lead in leads:
            try:
                processed_lead = await process_lead_for_response(lead, db, current_user)
                clean_leads.append(processed_lead)
            except Exception as e:
                logger.error(f"Error processing lead {lead.get('lead_id', 'unknown')}: {e}")
                continue
        
        # 🔥 CRITICAL FIX: Convert all ObjectIds to strings before returning
        final_leads = convert_objectid_to_str(clean_leads)
        
        logger.info(f"✅ Fast lookup returned {len(final_leads)} leads")
        
        return {
            "success": True,
            "leads": final_leads,
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
    SUPER FAST admin stats using user arrays - FIXED ObjectId serialization
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
        
        # 🔥 CRITICAL FIX: Ensure ObjectIds are converted
        final_response = convert_objectid_to_str({
            "success": True,
            "user_stats": user_stats,
            "summary": {
                "total_users": len(user_stats),
                "total_leads": total_leads,
                "assigned_leads": total_assigned_leads,
                "unassigned_leads": unassigned_leads
            },
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
# CORE LEAD ENDPOINTS - FIXED FOR OBJECTID
# ============================================================================
# Replace the create_lead endpoint in app/routers/leads.py with this:

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_lead(
    lead_data: dict,  # Accept any JSON structure
    force_create: bool = Query(False, description="Create lead even if duplicates exist"),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Create a new lead with category-based ID generation:
    - Category-based lead IDs (NS-1, SA-1, WA-1, etc.)
    - Duplicate detection and prevention
    - Round-robin auto-assignment
    - Activity logging
    - User array updates
    """
    try:
        logger.info(f"Creating lead by admin: {current_user['email']}")
        
        # Step 1: Parse and validate incoming data
        if "basic_info" in lead_data:
            # Comprehensive format - convert to LeadCreateComprehensive
            try:
                from ..models.lead import LeadCreateComprehensive, LeadBasicInfo, LeadStatusAndTags, LeadAssignmentInfo, LeadAdditionalInfo
                
                # Extract sections
                basic_info_data = lead_data.get("basic_info", {})
                status_and_tags_data = lead_data.get("status_and_tags", {})
                assignment_data = lead_data.get("assignment", {})
                additional_info_data = lead_data.get("additional_info", {})
                
                # Validate category is provided
                if not basic_info_data.get("category"):
                    raise HTTPException(
                        status_code=400,
                        detail="Category is required. Please select a valid lead category."
                    )
                
                # Create structured data
                structured_lead_data = LeadCreateComprehensive(
                    basic_info=LeadBasicInfo(
                        name=basic_info_data.get("name", ""),
                        email=basic_info_data.get("email", ""),
                        contact_number=basic_info_data.get("contact_number", ""),
                        source=basic_info_data.get("source", "website"),
                        category=basic_info_data.get("category")  # 🆕 Required category
                    ),
                    status_and_tags=LeadStatusAndTags(
                        stage=status_and_tags_data.get("stage", "initial"),
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
            # Legacy flat format - convert to comprehensive
            try:
                from ..models.lead import LeadCreateComprehensive, LeadBasicInfo, LeadStatusAndTags, LeadAdditionalInfo
                
                # Validate category for legacy format too
                if not lead_data.get("category"):
                    raise HTTPException(
                        status_code=400,
                        detail="Category is required. Please select a valid lead category."
                    )
                
                structured_lead_data = LeadCreateComprehensive(
                    basic_info=LeadBasicInfo(
                        name=lead_data.get("name", ""),
                        email=lead_data.get("email", ""),
                        contact_number=lead_data.get("contact_number", ""),
                        source=lead_data.get("source", "website"),
                        category=lead_data.get("category")  # 🆕 Required category
                    ),
                    status_and_tags=LeadStatusAndTags(
                        stage=lead_data.get("stage", "initial"),
                        lead_score=lead_data.get("lead_score", 0),
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
        
        # Step 2: Use the lead service to create lead with category support
        from ..services.lead_service import lead_service
        
        result = await lead_service.create_lead_comprehensive(
            lead_data=structured_lead_data,
            created_by=str(current_user["_id"]),
            force_create=force_create
        )
        
        if not result["success"]:
            # Handle duplicate case
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
        
        logger.info(f"✅ Lead created successfully: {result['lead']['lead_id']} in category {structured_lead_data.basic_info.category}")
        
        # Step 3: Return successful response
        return convert_objectid_to_str({
            "success": True,
            "message": result["message"],
            "lead": result["lead"],
            "assignment_info": result.get("assignment_info"),
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
    lead_status: Optional[LeadStatus] = Query(None),
    assigned_to: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get leads with complete status migration support - FIXED ObjectId serialization
    This endpoint handles both old and new status values seamlessly
    """
    try:
        logger.info(f"Get leads requested by: {current_user.get('email')}")
        db = get_database()
        
        # Build query
        query = {}
        if current_user["role"] != "admin":
            query["assigned_to"] = current_user["email"]
        
        # Handle status filtering (support both old and new values)
        if lead_status:
            # Create OR query to match both old and new status values
            possible_old_statuses = [k for k, v in OLD_TO_NEW_STATUS_MAPPING.items() if v == lead_status.value]
            status_conditions = [{"status": lead_status.value}]
            if possible_old_statuses:
                status_conditions.extend([{"status": old_status} for old_status in possible_old_statuses])
            query["$or"] = status_conditions
        
        if assigned_to and current_user["role"] == "admin":
            if "$or" in query:
                # Combine with existing OR condition
                query = {"$and": [{"assigned_to": assigned_to}, {"$or": query["$or"]}]}
            else:
                query["assigned_to"] = assigned_to
        
        if search:
            search_condition = {
                "$or": [
                    {"name": {"$regex": search, "$options": "i"}},
                    {"email": {"$regex": search, "$options": "i"}},
                    {"lead_id": {"$regex": search, "$options": "i"}}
                ]
            }
            if "$and" in query:
                query["$and"].append(search_condition)
            elif "$or" in query:
                query = {"$and": [{"$or": query["$or"]}, search_condition]}
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
        
        # 🔥 CRITICAL FIX: Convert ObjectIds before creating response model
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
    lead_status: Optional[LeadStatus] = Query(None),
    search: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get leads assigned to current user with complete migration support - FIXED ObjectId
    """
    try:
        db = get_database()
        query = {"assigned_to": current_user["email"]}
        
        # Handle status filtering with migration support
        if lead_status:
            possible_old_statuses = [k for k, v in OLD_TO_NEW_STATUS_MAPPING.items() if v == lead_status.value]
            status_conditions = [{"status": lead_status.value}]
            if possible_old_statuses:
                status_conditions.extend([{"status": old_status} for old_status in possible_old_statuses])
            query["$or"] = status_conditions
        
        if search:
            search_condition = {
                "$or": [
                    {"name": {"$regex": search, "$options": "i"}},
                    {"email": {"$regex": search, "$options": "i"}},
                    {"lead_id": {"$regex": search, "$options": "i"}}
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
        
        # 🔥 CRITICAL FIX: Convert ObjectIds before response
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
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get lead statistics with migration-aware status counting
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
        
        # Initialize stats with your new status values
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
            
            # Migrate status value if needed
            migrated_status = migrate_status_value(status_val)
            
            # Map to stats key
            key = migrated_status.lower().replace(" ", "_")
            if key in stats:
                stats[key] += count
        
        # Calculate additional stats
        if current_user["role"] != "admin":
            stats["my_leads"] = stats["total_leads"]
        else:
            stats["my_leads"] = await db.leads.count_documents({"assigned_to": current_user["email"]})
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
    Get a specific lead by ID in structured comprehensive format - FIXED ObjectId
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
        
        # Transform to structured format with migration support and ObjectId conversion
        structured_lead = transform_lead_to_structured_format(lead)
        
        # 🔥 CRITICAL FIX: Already handled in transform_lead_to_structured_format
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
# ASSIGNMENT ENDPOINTS - FIXED FOR OBJECTID
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
# UPDATE ENDPOINT - ENHANCED WITH BETTER USER ARRAY SYNC
# ============================================================================

@router.put("/update")
async def update_lead_universal(
    update_request: dict,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Universal lead update endpoint with ENHANCED USER ARRAY SYNC
    """
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
        
        # Check permissions
        user_role = current_user.get("role", "user")
        if user_role != "admin" and lead.get("assigned_to") != current_user.get("email"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update leads assigned to you"
            )
        
        # Handle assignment change validation
        assignment_changed = False
        old_assignee = lead.get("assigned_to")
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
        
        # 🔥 PERFORM THE ACTUAL DATABASE UPDATE
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
        
        # 🔥 ENHANCED USER ARRAY UPDATES - Only if assignment changed
        assignment_sync_error = None
        if assignment_changed:
            logger.info(f"🔄 Processing user array updates for assignment change")
            
            try:
                # Remove from old assignee's array
                if old_assignee:
                    logger.info(f"📤 Removing lead {lead_id} from {old_assignee}")
                    await update_user_lead_array(old_assignee, lead_id, "remove")
                    logger.info(f"✅ Successfully removed lead {lead_id} from {old_assignee}")
                
                # Add to new assignee's array
                if new_assignee:
                    logger.info(f"📥 Adding lead {lead_id} to {new_assignee}")
                    await update_user_lead_array(new_assignee, lead_id, "add")
                    logger.info(f"✅ Successfully added lead {lead_id} to {new_assignee}")
                
                # Log assignment activity
                if old_assignee != new_assignee:
                    assignment_activity = {
                        "activity_type": "lead_reassigned",
                        "description": f"Lead reassigned from '{old_assignee or 'Unassigned'}' to '{new_assignee or 'Unassigned'}'",
                        "metadata": {
                            "old_assignee": old_assignee,
                            "new_assignee": new_assignee,
                            "reassigned_by": current_user.get("email")
                        }
                    }
                    activities_to_log.append(assignment_activity)
                    
            except Exception as array_error:
                logger.error(f"❌ CRITICAL: User array update failed: {str(array_error)}")
                logger.error(f"❌ Assignment details: {old_assignee} → {new_assignee}")
                
                # 🚨 IMPORTANT: Don't fail the lead update, but log prominently
                logger.error(f"❌ USER ARRAYS ARE NOW OUT OF SYNC FOR LEAD {lead_id}")
                logger.error(f"❌ MANUAL SYNC REQUIRED: Run /admin/sync-user-arrays")
                
                # Add error to response so admin knows
                assignment_sync_error = {
                    "error": "User array sync failed",
                    "details": str(array_error),
                    "recommendation": "Run /admin/sync-user-arrays endpoint"
                }
        else:
            logger.info(f"ℹ️ No assignment change, skipping user array updates")
        
        # 🔥 LOG ALL ACTIVITIES
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
                # Don't fail the update if activity logging fails
        
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


# Helper function to format lead response (add this if it doesn't exist)
def format_lead_response(lead_doc: dict) -> dict:
    """Format lead document for API response"""
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


# ENHANCED Helper function for user array updates
async def update_user_lead_array(user_email: str, lead_id: str, action: str):
    """Update user's assigned_leads array with enhanced validation and logging"""
    try:
        db = get_database()
        
        logger.info(f"🔄 User array update: {action} lead {lead_id} for {user_email}")
        
        if action == "add":
            # Verify user exists and is active before adding
            user = await db.users.find_one({"email": user_email, "is_active": True})
            if not user:
                raise Exception(f"User {user_email} not found or inactive")
            
            result = await db.users.update_one(
                {"email": user_email, "is_active": True},
                {
                    "$addToSet": {"assigned_leads": lead_id},
                    "$inc": {"total_assigned_leads": 1}
                }
            )
            
            if result.modified_count == 0:
                # Check if lead was already in array
                user_after = await db.users.find_one({"email": user_email})
                if user_after and lead_id in user_after.get("assigned_leads", []):
                    logger.info(f"ℹ️ Lead {lead_id} already in {user_email}'s array")
                else:
                    logger.warning(f"⚠️ Failed to add lead {lead_id} to {user_email} - no documents modified")
            else:
                logger.info(f"✅ Added lead {lead_id} to {user_email}'s array")
            
        elif action == "remove":
            result = await db.users.update_one(
                {"email": user_email},
                {
                    "$pull": {"assigned_leads": lead_id},
                    "$inc": {"total_assigned_leads": -1}
                }
            )
            
            # Ensure count doesn't go below 0
            await db.users.update_one(
                {"email": user_email, "total_assigned_leads": {"$lt": 0}},
                {"$set": {"total_assigned_leads": 0}}
            )
            
            if result.modified_count == 0:
                logger.warning(f"⚠️ No documents modified when removing lead {lead_id} from {user_email}")
            else:
                logger.info(f"✅ Removed lead {lead_id} from {user_email}'s array")
        else:
            raise Exception(f"Invalid action: {action}. Must be 'add' or 'remove'")
            
    except Exception as e:
        logger.error(f"❌ User array update error for {user_email}: {str(e)}")
        raise  # Re-raise so calling function knows it failed
    

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
        "course_level": "preferences_updated"
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

def format_tag_changes(added_tags: set, removed_tags: set) -> str:
    """Format tag changes for description"""
    parts = []
    if added_tags:
        parts.append(f"Added: {', '.join(added_tags)}")
    if removed_tags:
        parts.append(f"Removed: {', '.join(removed_tags)}")
    return " | ".join(parts)

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
# BULK OPERATIONS - FIXED FOR OBJECTID
# ============================================================================

@router.post("/bulk-create", status_code=status.HTTP_201_CREATED)
async def bulk_create_leads(
    leads_data: List[dict],  
    force_create: bool = Query(False, description="Create leads even if duplicates exist"),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    ✅ SIMPLEST FIX: Just call the single lead endpoint multiple times
    """
    try:
        logger.info(f"Bulk creating {len(leads_data)} leads")
        
        results = []
        successful_creates = 0
        failed_creates = 0
        duplicates_skipped = 0
        
        for index, lead_data in enumerate(leads_data):
            try:
                # ✅ Call the working single lead endpoint
                result = await create_lead(
                    lead_data=lead_data,
                    force_create=force_create,
                    current_user=current_user
                )
                
                if result.get("success"):
                    lead_info = result.get("lead", {})
                    results.append({
                        "index": index,
                        "status": "created",
                        "lead_id": lead_info.get("lead_id"),
                        "assigned_to": lead_info.get("assigned_to"),
                        "assigned_to_name": lead_info.get("assigned_to_name")
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
            "summary": {
                "total_attempted": len(leads_data),
                "successful_creates": successful_creates,
                "failed_creates": failed_creates,
                "duplicates_skipped": duplicates_skipped
            },
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Bulk error: {e}")
        raise HTTPException(status_code=500, detail=str(e))