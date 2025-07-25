from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from ..config.database import get_database
from ..utils.security import security
import logging

logger = logging.getLogger(__name__)

# Security scheme
security_scheme = HTTPBearer()

class AuthenticationError(HTTPException):
    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme)
) -> Dict[str, Any]:
    """
    Dependency to get current authenticated user from JWT token
    Enhanced to include user permissions for lead creation
    """
    token = credentials.credentials
    
    # Verify token
    payload = security.verify_token(token)
    if payload is None:
        raise AuthenticationError("Invalid token")
    
    # Check token type
    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type")
    
    # Check if token is blacklisted
    token_jti = payload.get("jti")
    if token_jti and await security.is_token_blacklisted(token_jti):
        raise AuthenticationError("Token has been revoked")
    
    # Get user from database
    user_id = payload.get("sub")
    if user_id is None:
        raise AuthenticationError("Invalid token payload")
    
    db = get_database()
    user_data = await db.users.find_one({"_id": ObjectId(user_id)})
    
    if user_data is None:
        raise AuthenticationError("User not found")
    
    # Check if user is active
    if not user_data.get("is_active", False):
        raise AuthenticationError("User account is disabled")
    
    # 🆕 NEW: Ensure permissions field exists for backward compatibility
    if "permissions" not in user_data:
        user_data["permissions"] = {
            "can_create_single_lead": False,
            "can_create_bulk_leads": False,
            "granted_by": None,
            "granted_at": None,
            "last_modified_by": None,
            "last_modified_at": None
        }
    
    # Update last activity
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"last_activity": datetime.utcnow()}}
    )
    
    # Convert ObjectId to string for JSON serialization
    user_data["_id"] = str(user_data["_id"])
    return user_data

async def get_current_active_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Dependency to get current active user
    """
    if not current_user.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

async def get_admin_user(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Dependency to ensure current user is admin
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions. Admin access required."
        )
    return current_user

# 🆕 NEW: Permission-based dependencies for lead creation

async def get_user_with_single_lead_permission(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Dependency to allow admins OR users with single lead creation permission
    Used for: POST /api/v1/leads/ (single lead creation)
    """
    user_role = current_user.get("role")
    
    # Admins always have permission
    if user_role == "admin":
        logger.info(f"Admin user {current_user.get('email')} accessing single lead creation")
        return current_user
    
    # Check user permissions
    permissions = current_user.get("permissions", {})
    if permissions.get("can_create_single_lead", False):
        logger.info(f"User {current_user.get('email')} has single lead creation permission")
        return current_user
    
    # Log permission denial
    logger.warning(f"User {current_user.get('email')} denied single lead creation - no permission")
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have permission to create leads. Contact your administrator to request access."
    )

async def get_user_with_bulk_lead_permission(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Dependency to allow admins OR users with bulk lead creation permission
    Used for: POST /api/v1/leads/bulk-create (bulk lead creation)
    """
    user_role = current_user.get("role")
    
    # Admins always have permission
    if user_role == "admin":
        logger.info(f"Admin user {current_user.get('email')} accessing bulk lead creation")
        return current_user
    
    # Check user permissions
    permissions = current_user.get("permissions", {})
    if permissions.get("can_create_bulk_leads", False):
        logger.info(f"User {current_user.get('email')} has bulk lead creation permission")
        return current_user
    
    # Log permission denial
    logger.warning(f"User {current_user.get('email')} denied bulk lead creation - no permission")
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have permission to create bulk leads. Contact your administrator to request access."
    )

# 🆕 NEW: Helper function to check specific permissions
def check_user_permission(current_user: Dict[str, Any], permission_name: str) -> bool:
    """
    Helper function to check if user has specific permission
    
    Args:
        current_user: Current user data from JWT
        permission_name: Name of permission to check (e.g., 'can_create_single_lead')
    
    Returns:
        bool: True if user has permission, False otherwise
    """
    # Admins always have all permissions
    if current_user.get("role") == "admin":
        return True
    
    # Check specific permission
    permissions = current_user.get("permissions", {})
    return permissions.get(permission_name, False)

# 🆕 NEW: Get user permissions summary
def get_user_permissions_summary(current_user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a summary of user's permissions for UI display
    
    Returns:
        dict: Summary of user permissions and capabilities
    """
    user_role = current_user.get("role")
    permissions = current_user.get("permissions", {})
    
    if user_role == "admin":
        return {
            "is_admin": True,
            "can_create_single_lead": True,
            "can_create_bulk_leads": True,
            "can_manage_permissions": True,
            "can_assign_leads": True,
            "can_view_all_leads": True,
            "permission_source": "admin_role"
        }
    
    return {
        "is_admin": False,
        "can_create_single_lead": permissions.get("can_create_single_lead", False),
        "can_create_bulk_leads": permissions.get("can_create_bulk_leads", False),
        "can_manage_permissions": False,
        "can_assign_leads": False,
        "can_view_all_leads": False,
        "permission_source": "user_permissions",
        "granted_by": permissions.get("granted_by"),
        "granted_at": permissions.get("granted_at")
    }