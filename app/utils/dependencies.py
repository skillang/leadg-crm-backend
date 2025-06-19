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