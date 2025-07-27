# app/routers/tata_users.py
# Tata User Synchronization Router - User mapping between CRM and Tata systems

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
from bson import ObjectId

from ..services.tata_user_service import tata_user_service
from ..utils.dependencies import get_current_active_user, get_admin_user
from ..models.tata_user import (
    TataUserMapping, TataUserMappingCreate, TataUserMappingUpdate,
    TataUserMappingResponse, BulkUserSyncRequest, BulkUserSyncResponse,
    UserSyncStatistics, UserValidationResult
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
# USER MAPPING MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/mappings", response_model=List[TataUserMappingResponse])
async def get_user_mappings(
    limit: int = Query(50, ge=1, le=100, description="Number of mappings to return"),
    offset: int = Query(0, ge=0, description="Number of mappings to skip"),
    sync_status: Optional[str] = Query(None, description="Filter by sync status"),
    current_user: dict = Depends(get_admin_user)  # Admin only
):
    """
    Get list of user mappings between CRM and Tata systems
    
    - **Admin Only**: Only admins can view user mappings
    - **Filtering**: Filter by sync status (synced, pending, failed, unsynced)
    - **Pagination**: Support for large user lists
    """
    try:
        logger.info(f"Admin {current_user['email']} fetching user mappings")
        
        # Get mappings from service
        mappings = await tata_user_service.get_user_mappings(
            limit=limit,
            offset=offset,
            sync_status=sync_status
        )
        
        # Convert ObjectIds and return
        converted_mappings = convert_objectid_to_str(mappings)
        
        logger.info(f"Returned {len(converted_mappings)} user mappings")
        return converted_mappings
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error fetching user mappings: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching user mappings: {str(e)}"
        )

@router.post("/mappings", response_model=TataUserMappingResponse)
async def create_user_mapping(
    mapping_data: TataUserMappingCreate,
    current_user: dict = Depends(get_admin_user)  # Admin only
):
    """
    Create a new user mapping between CRM and Tata systems
    
    - **Admin Only**: Only admins can create mappings
    - **Validation**: Validates user exists in both systems
    - **Auto-sync**: Automatically syncs user to Tata if needed
    """
    try:
        logger.info(f"Admin {current_user['email']} creating user mapping for CRM user {mapping_data.crm_user_id}")
        
        # Create mapping through service
        result = await tata_user_service.create_user_mapping(
            mapping_data=mapping_data,
            created_by=current_user["user_id"]
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        # Convert ObjectIds and return
        mapping = convert_objectid_to_str(result["mapping"])
        
        logger.info(f"User mapping created successfully: {mapping['_id']}")
        return mapping
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error creating user mapping: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error creating user mapping: {str(e)}"
        )

@router.put("/mappings/{mapping_id}", response_model=TataUserMappingResponse)
async def update_user_mapping(
    mapping_id: str,
    mapping_update: TataUserMappingUpdate,
    current_user: dict = Depends(get_admin_user)  # Admin only
):
    """
    Update an existing user mapping
    
    - **Admin Only**: Only admins can update mappings
    - **Validation**: Validates updated data
    - **Re-sync**: Triggers re-sync if needed
    """
    try:
        logger.info(f"Admin {current_user['email']} updating user mapping {mapping_id}")
        
        # Update mapping through service
        result = await tata_user_service.update_user_mapping(
            mapping_id=mapping_id,
            mapping_update=mapping_update,
            updated_by=current_user["user_id"]
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        # Convert ObjectIds and return
        mapping = convert_objectid_to_str(result["mapping"])
        
        logger.info(f"User mapping updated successfully: {mapping_id}")
        return mapping
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error updating user mapping: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error updating user mapping: {str(e)}"
        )

@router.delete("/mappings/{mapping_id}")
async def delete_user_mapping(
    mapping_id: str,
    current_user: dict = Depends(get_admin_user)  # Admin only
):
    """
    Delete a user mapping
    
    - **Admin Only**: Only admins can delete mappings
    - **Audit Trail**: Logs deletion for audit purposes
    - **Cleanup**: Cleans up related sync data
    """
    try:
        logger.info(f"Admin {current_user['email']} deleting user mapping {mapping_id}")
        
        # Delete mapping through service
        result = await tata_user_service.delete_user_mapping(
            mapping_id=mapping_id,
            deleted_by=current_user["user_id"]
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        logger.info(f"User mapping deleted successfully: {mapping_id}")
        return {
            "success": True,
            "message": "User mapping deleted successfully",
            "deleted_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error deleting user mapping: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error deleting user mapping: {str(e)}"
        )

# ============================================================================
# USER SYNCHRONIZATION ENDPOINTS
# ============================================================================

@router.post("/sync/{user_id}")
async def sync_single_user(
    user_id: str,
    current_user: dict = Depends(get_admin_user)  # Admin only
):
    """
    Synchronize a single user with Tata system
    
    - **Admin Only**: Only admins can trigger sync
    - **Validation**: Validates user before sync
    - **Auto-creation**: Creates Tata user if doesn't exist
    - **Mapping**: Creates/updates user mapping
    """
    try:
        logger.info(f"Admin {current_user['email']} syncing user {user_id}")
        
        # Sync user through service
        result = await tata_user_service.sync_single_user(
            crm_user_id=user_id,
            initiated_by=current_user["user_id"]
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        logger.info(f"User sync completed for {user_id}: {result['sync_status']}")
        return {
            "success": True,
            "message": f"User sync completed: {result['sync_status']}",
            "sync_status": result["sync_status"],
            "tata_user_id": result.get("tata_user_id"),
            "mapping_id": str(result.get("mapping_id")) if result.get("mapping_id") else None,
            "synced_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error syncing user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error syncing user: {str(e)}"
        )

@router.post("/bulk-sync", response_model=BulkUserSyncResponse)
async def bulk_sync_users(
    sync_request: BulkUserSyncRequest,
    current_user: dict = Depends(get_admin_user)  # Admin only
):
    """
    Bulk synchronize multiple users with Tata system
    
    - **Admin Only**: Only admins can trigger bulk sync
    - **Batch Processing**: Processes users in configurable batches
    - **Progress Tracking**: Returns detailed progress information
    - **Error Recovery**: Continues processing even if some users fail
    """
    try:
        logger.info(f"Admin {current_user['email']} initiating bulk user sync for {len(sync_request.user_ids)} users")
        
        # Validate batch size
        if len(sync_request.user_ids) > 50:  # Configurable limit
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bulk sync limited to 50 users per request"
            )
        
        # Bulk sync through service
        result = await tata_user_service.bulk_sync_users(
            user_ids=sync_request.user_ids,
            sync_options=sync_request.sync_options,
            initiated_by=current_user["user_id"]
        )
        
        logger.info(f"Bulk sync completed: {result['successful_syncs']} successful, {result['failed_syncs']} failed")
        
        return BulkUserSyncResponse(
            total_requested=result["total_requested"],
            successful_syncs=result["successful_syncs"],
            failed_syncs=result["failed_syncs"],
            skipped_syncs=result["skipped_syncs"],
            sync_results=result["sync_results"],
            operation_id=result["operation_id"],
            started_at=result["started_at"],
            completed_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error in bulk user sync: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error in bulk user sync: {str(e)}"
        )

@router.get("/statistics", response_model=UserSyncStatistics)
async def get_sync_statistics(
    current_user: dict = Depends(get_admin_user)  # Admin only
):
    """
    Get user synchronization statistics
    
    - **Admin Only**: Only admins can view sync statistics
    - **Comprehensive Stats**: Total users, sync status breakdown, performance metrics
    - **Health Monitoring**: Sync health and performance indicators
    """
    try:
        logger.info(f"Admin {current_user['email']} fetching sync statistics")
        
        # Get statistics from service
        stats = await tata_user_service.get_sync_statistics()
        
        return UserSyncStatistics(
            total_crm_users=stats["total_crm_users"],
            total_mappings=stats["total_mappings"],
            synced_users=stats["synced_users"],
            pending_users=stats["pending_users"],
            failed_users=stats["failed_users"],
            unsynced_users=stats["unsynced_users"],
            last_sync_time=stats.get("last_sync_time"),
            sync_success_rate=stats["sync_success_rate"],
            average_sync_time=stats.get("average_sync_time"),
            last_24h_syncs=stats["last_24h_syncs"],
            generated_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error fetching sync statistics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching sync statistics: {str(e)}"
        )

@router.get("/unmapped")
async def get_unmapped_users(
    limit: int = Query(50, ge=1, le=100, description="Number of users to return"),
    offset: int = Query(0, ge=0, description="Number of users to skip"),
    current_user: dict = Depends(get_admin_user)  # Admin only
):
    """
    Get list of CRM users without Tata mappings
    
    - **Admin Only**: Only admins can view unmapped users
    - **Pagination**: Support for large user lists
    - **Sync Ready**: Users ready for synchronization
    """
    try:
        logger.info(f"Admin {current_user['email']} fetching unmapped users")
        
        # Get unmapped users from service
        unmapped_users = await tata_user_service.get_unmapped_users(
            limit=limit,
            offset=offset
        )
        
        # Convert ObjectIds and return
        converted_users = convert_objectid_to_str(unmapped_users)
        
        logger.info(f"Returned {len(converted_users)} unmapped users")
        return {
            "success": True,
            "unmapped_users": converted_users,
            "total_count": len(converted_users),
            "limit": limit,
            "offset": offset,
            "retrieved_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error fetching unmapped users: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching unmapped users: {str(e)}"
        )

# ============================================================================
# VALIDATION ENDPOINTS
# ============================================================================

@router.post("/validate/{user_id}", response_model=UserValidationResult)
async def validate_user_for_sync(
    user_id: str,
    current_user: dict = Depends(get_admin_user)  # Admin only
):
    """
    Validate a user before synchronization
    
    - **Admin Only**: Only admins can validate users
    - **Pre-sync Check**: Validates user data before actual sync
    - **Requirement Check**: Checks if user meets sync requirements
    """
    try:
        logger.info(f"Admin {current_user['email']} validating user {user_id} for sync")
        
        # Validate user through service
        validation_result = await tata_user_service.validate_user_for_sync(user_id)
        
        return UserValidationResult(
            user_id=user_id,
            is_valid=validation_result["is_valid"],
            validation_errors=validation_result["validation_errors"],
            validation_warnings=validation_result["validation_warnings"],
            can_sync=validation_result["can_sync"],
            required_fields=validation_result["required_fields"],
            recommended_actions=validation_result["recommended_actions"],
            validated_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error validating user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error validating user: {str(e)}"
        )

# ============================================================================
# ROUTER METADATA
# ============================================================================

# Router tags and metadata for API documentation
router.tags = ["Tata User Sync"]