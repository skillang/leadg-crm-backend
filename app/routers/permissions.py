# app/routers/permissions.py - Admin Permission Management Endpoints
"""
API endpoints for managing user lead creation permissions.
All endpoints require admin authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from datetime import datetime
import logging

from ..services.permission_service import permission_service
from ..utils.dependencies import get_admin_user
from ..models.user import (
    PermissionUpdateRequest, 
    PermissionUpdateResponse
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# ============================================================================
# PERMISSION MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/users")
async def get_users_permissions(
    include_admins: bool = Query(False, description="Include admin users in results"),
    current_user: dict = Depends(get_admin_user)
):
    """
    Get all users with their current lead creation permissions (Admin only)
    
    Returns:
        Dict: List of users with permission details (simplified response)
    """
    try:
        logger.info(f"Permission list requested by admin: {current_user.get('email')}")
        
        # Get users with permissions
        users = await permission_service.get_users_with_permissions(include_admins=include_admins)
        
        # Get permission summary
        summary = await permission_service.get_permission_summary()
        
        # Add admin stats if including admins
        if include_admins:
            from ..config.database import get_database
            db = get_database()
            admin_count = await db.users.count_documents({"role": "admin", "is_active": True})
            summary["admin_users"] = admin_count
            summary["total_users"] += admin_count
        
        logger.info(f"Retrieved {len(users)} users for permission management")
        
        return {
            "success": True,
            "users": users,
            "total": len(users),
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Error getting users permissions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve user permissions: {str(e)}"
        )

@router.post("/users/update", response_model=PermissionUpdateResponse)
async def update_user_permissions(
    request: PermissionUpdateRequest,
    current_user: dict = Depends(get_admin_user)
):
    """
    Update user lead creation permissions (Admin only)
    
    Args:
        request: Permission update request with user email and new permissions
        current_user: Current admin user (from dependency)
        
    Returns:
        PermissionUpdateResponse: Update result with new permission state
    """
    try:
        logger.info(f"Permission update requested by admin {current_user.get('email')} for user {request.user_email}")
        
        # Update permissions using service
        result = await permission_service.update_user_permissions(
            user_email=request.user_email,
            permissions={
                "can_create_single_lead": request.can_create_single_lead,
                "can_create_bulk_leads": request.can_create_bulk_leads
            },
            admin_user=current_user,
            reason=request.reason
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        # Create response
        from ..models.user import UserPermissions
        
        updated_permissions = UserPermissions(
            can_create_single_lead=result["new_permissions"]["can_create_single_lead"],
            can_create_bulk_leads=result["new_permissions"]["can_create_bulk_leads"],
            granted_by=result["new_permissions"]["granted_by"],
            granted_at=result["new_permissions"]["granted_at"],
            last_modified_by=result["new_permissions"]["last_modified_by"],
            last_modified_at=result["new_permissions"]["last_modified_at"]
        )
        
        logger.info(f"✅ Successfully updated permissions for {request.user_email}")
        
        return PermissionUpdateResponse(
            success=True,
            message=result["message"],
            user_email=request.user_email,
            updated_permissions=updated_permissions,
            updated_by=current_user.get("email"),
            updated_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user permissions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update permissions: {str(e)}"
        )

@router.post("/users/{user_email}/revoke-all")
async def revoke_all_permissions(
    user_email: str,
    reason: Optional[str] = Query(None, description="Reason for revoking permissions"),
    current_user: dict = Depends(get_admin_user)
):
    """
    Revoke all lead creation permissions from a user (Admin only)
    
    Args:
        user_email: Email of user to revoke permissions from
        reason: Optional reason for revocation
        current_user: Current admin user (from dependency)
        
    Returns:
        dict: Revocation result
    """
    try:
        logger.info(f"Permission revocation requested by admin {current_user.get('email')} for user {user_email}")
        
        # Revoke all permissions using service
        result = await permission_service.revoke_all_permissions(
            user_email=user_email,
            admin_user=current_user,
            reason=reason or "All permissions revoked by admin"
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        logger.info(f"✅ Successfully revoked all permissions for {user_email}")
        
        return {
            "success": True,
            "message": result["message"],
            "user_email": user_email,
            "revoked_by": current_user.get("email"),
            "revoked_at": datetime.utcnow(),
            "reason": reason
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking user permissions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke permissions: {str(e)}"
        )

@router.post("/users/{user_email}/grant-single")
async def grant_single_lead_permission(
    user_email: str,
    reason: Optional[str] = Query(None, description="Reason for granting permission"),
    current_user: dict = Depends(get_admin_user)
):
    """
    Grant single lead creation permission to a user (Admin only)
    
    Args:
        user_email: Email of user to grant permission to
        reason: Optional reason for granting permission
        current_user: Current admin user (from dependency)
        
    Returns:
        dict: Grant result
    """
    try:
        logger.info(f"Single lead permission grant requested by admin {current_user.get('email')} for user {user_email}")
        
        # Grant single lead permission
        result = await permission_service.update_user_permissions(
            user_email=user_email,
            permissions={
                "can_create_single_lead": True,
                "can_create_bulk_leads": False  # Only grant single, not bulk
            },
            admin_user=current_user,
            reason=reason or "Single lead creation permission granted"
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        logger.info(f"✅ Successfully granted single lead permission to {user_email}")
        
        return {
            "success": True,
            "message": f"Single lead creation permission granted to {user_email}",
            "user_email": user_email,
            "permission_granted": "can_create_single_lead",
            "granted_by": current_user.get("email"),
            "granted_at": datetime.utcnow(),
            "reason": reason
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error granting single lead permission: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to grant permission: {str(e)}"
        )

@router.post("/users/{user_email}/grant-bulk")
async def grant_bulk_lead_permission(
    user_email: str,
    reason: Optional[str] = Query(None, description="Reason for granting permission"),
    current_user: dict = Depends(get_admin_user)
):
    """
    Grant bulk lead creation permission to a user (Admin only)
    This automatically includes single lead permission as well.
    
    Args:
        user_email: Email of user to grant permission to
        reason: Optional reason for granting permission
        current_user: Current admin user (from dependency)
        
    Returns:
        dict: Grant result
    """
    try:
        logger.info(f"Bulk lead permission grant requested by admin {current_user.get('email')} for user {user_email}")
        
        # Grant both single and bulk permissions (bulk implies single)
        result = await permission_service.update_user_permissions(
            user_email=user_email,
            permissions={
                "can_create_single_lead": True,
                "can_create_bulk_leads": True
            },
            admin_user=current_user,
            reason=reason or "Bulk lead creation permission granted (includes single)"
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        logger.info(f"✅ Successfully granted bulk lead permission to {user_email}")
        
        return {
            "success": True,
            "message": f"Bulk lead creation permission granted to {user_email} (includes single lead permission)",
            "user_email": user_email,
            "permissions_granted": ["can_create_single_lead", "can_create_bulk_leads"],
            "granted_by": current_user.get("email"),
            "granted_at": datetime.utcnow(),
            "reason": reason
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error granting bulk lead permission: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to grant permission: {str(e)}"
        )

# ============================================================================
# PERMISSION STATISTICS AND REPORTING
# ============================================================================

@router.get("/summary")
async def get_permission_summary(
    current_user: dict = Depends(get_admin_user)
):
    """
    Get summary statistics of permission distribution (Admin only)
    
    Returns:
        dict: Permission distribution statistics
    """
    try:
        logger.info(f"Permission summary requested by admin: {current_user.get('email')}")
        
        # Get permission summary
        summary = await permission_service.get_permission_summary()
        
        # Add additional context
        summary["generated_by"] = current_user.get("email")
        summary["generated_at"] = datetime.utcnow()
        
        logger.info(f"Permission summary generated: {summary['users_with_any_permission']}/{summary['total_users']} users have permissions")
        
        return {
            "success": True,
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Error generating permission summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate permission summary: {str(e)}"
        )

@router.get("/audit-log")
async def get_permission_audit_log(
    limit: int = Query(50, ge=1, le=500, description="Number of log entries to return"),
    skip: int = Query(0, ge=0, description="Number of log entries to skip"),
    user_email: Optional[str] = Query(None, description="Filter by specific user email"),
    current_user: dict = Depends(get_admin_user)
):
    """
    Get permission change audit log (Admin only)
    
    Args:
        limit: Maximum number of entries to return
        skip: Number of entries to skip (for pagination)
        user_email: Optional filter by specific user
        current_user: Current admin user (from dependency)
        
    Returns:
        dict: Audit log entries
    """
    try:
        logger.info(f"Permission audit log requested by admin: {current_user.get('email')}")
        
        from ..config.database import get_database
        db = get_database()
        
        # Build query
        query = {}
        if user_email:
            query["target_user_email"] = user_email
        
        # Get total count
        total_count = await db.permission_audit_log.count_documents(query)
        
        # Get audit log entries
        cursor = db.permission_audit_log.find(query).sort("timestamp", -1).skip(skip).limit(limit)
        audit_entries = await cursor.to_list(None)
        
        # Convert ObjectIds to strings
        for entry in audit_entries:
            entry["_id"] = str(entry["_id"])
        
        logger.info(f"Retrieved {len(audit_entries)} audit log entries")
        
        return {
            "success": True,
            "audit_entries": audit_entries,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "skip": skip,
                "has_more": skip + limit < total_count
            },
            "filter": {
                "user_email": user_email
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting permission audit log: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit log: {str(e)}"
        )

# ============================================================================
# PERMISSION TESTING AND VALIDATION
# ============================================================================

@router.get("/users/{user_email}/check")
async def check_user_permissions(
    user_email: str,
    current_user: dict = Depends(get_admin_user)
):
    """
    Check specific user's current permissions (Admin only)
    
    Args:
        user_email: Email of user to check
        current_user: Current admin user (from dependency)
        
    Returns:
        dict: User's current permission status
    """
    try:
        logger.info(f"Permission check requested by admin {current_user.get('email')} for user {user_email}")
        
        from ..config.database import get_database
        db = get_database()
        
        # Get user data
        user = await db.users.find_one(
            {"email": user_email}, 
            {"email": 1, "first_name": 1, "last_name": 1, "role": 1, "permissions": 1, "is_active": 1}
        )
        
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User {user_email} not found"
            )
        
        # Get permissions
        permissions = user.get("permissions", {})
        
        # Build response
        permission_status = {
            "user_email": user_email,
            "user_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
            "role": user.get("role"),
            "is_active": user.get("is_active", False),
            "permissions": {
                "can_create_single_lead": permissions.get("can_create_single_lead", False),
                "can_create_bulk_leads": permissions.get("can_create_bulk_leads", False),
                "granted_by": permissions.get("granted_by"),
                "granted_at": permissions.get("granted_at"),
                "last_modified_by": permissions.get("last_modified_by"),
                "last_modified_at": permissions.get("last_modified_at")
            },
            "effective_permissions": {
                "can_access_single_lead_creation": (
                    user.get("role") == "admin" or 
                    permissions.get("can_create_single_lead", False)
                ),
                "can_access_bulk_lead_creation": (
                    user.get("role") == "admin" or 
                    permissions.get("can_create_bulk_leads", False)
                ),
                "permission_source": "admin_role" if user.get("role") == "admin" else "user_permissions"
            }
        }
        
        logger.info(f"Permission check completed for {user_email}")
        
        return {
            "success": True,
            "permission_status": permission_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking user permissions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check user permissions: {str(e)}"
        )

@router.post("/validate")
async def validate_permission_system(
    current_user: dict = Depends(get_admin_user)
):
    """
    Validate the permission system integrity (Admin only)
    Checks for users without permission fields and other issues.
    
    Returns:
        dict: Validation results and recommendations
    """
    try:
        logger.info(f"Permission system validation requested by admin: {current_user.get('email')}")
        
        from ..config.database import get_database
        db = get_database()
        
        # Check for users without permissions field
        users_without_permissions = await db.users.count_documents({"permissions": {"$exists": False}})
        
        # Check for inactive users with permissions
        inactive_users_with_permissions = await db.users.count_documents({
            "is_active": False,
            "$or": [
                {"permissions.can_create_single_lead": True},
                {"permissions.can_create_bulk_leads": True}
            ]
        })
        
        # Check for admin users with explicit permissions (they don't need them)
        admin_users_with_explicit_permissions = await db.users.count_documents({
            "role": "admin",
            "$or": [
                {"permissions.can_create_single_lead": True},
                {"permissions.can_create_bulk_leads": True}
            ]
        })
        
        # Check for orphaned permissions (users who no longer exist)
        # This is theoretical since permissions are embedded in user documents
        
        # Build validation results
        issues = []
        recommendations = []
        
        if users_without_permissions > 0:
            issues.append(f"{users_without_permissions} users don't have permission fields")
            recommendations.append("Run the migration script to add default permissions")
        
        if inactive_users_with_permissions > 0:
            issues.append(f"{inactive_users_with_permissions} inactive users still have permissions")
            recommendations.append("Consider revoking permissions from inactive users")
        
        if admin_users_with_explicit_permissions > 0:
            issues.append(f"{admin_users_with_explicit_permissions} admin users have explicit permissions (unnecessary)")
            recommendations.append("Admin users don't need explicit permissions - consider clearing them")
        
        validation_status = "healthy" if len(issues) == 0 else "issues_found"
        
        logger.info(f"Permission system validation completed - Status: {validation_status}")
        
        return {
            "success": True,
            "validation_status": validation_status,
            "issues_found": len(issues),
            "issues": issues,
            "recommendations": recommendations,
            "statistics": {
                "users_without_permissions": users_without_permissions,
                "inactive_users_with_permissions": inactive_users_with_permissions,
                "admin_users_with_explicit_permissions": admin_users_with_explicit_permissions
            },
            "validated_by": current_user.get("email"),
            "validated_at": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Error validating permission system: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate permission system: {str(e)}"
        )