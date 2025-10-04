# app/routers/fcm_notifications.py
# FCM Token Management for Push Notifications

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from ..utils.dependencies import get_current_user
from ..config.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["FCM Notifications"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class FCMTokenRequest(BaseModel):
    """Request model for FCM token registration"""
    fcm_token: str = Field(..., min_length=1, description="Firebase Cloud Messaging token")
    device_info: Optional[str] = Field(None, description="Optional device information")
    
    class Config:
        json_schema_extra = {
            "example": {
                "fcm_token": "dXXXXXXXXXX:APA91bXXXXXXXXXXXXXXXXXXXXXX",
                "device_info": "Chrome on Windows"
            }
        }


class FCMTokenResponse(BaseModel):
    """Response model for FCM token operations"""
    success: bool
    message: str
    user_email: str
    token_registered_at: datetime
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "FCM token registered successfully",
                "user_email": "user@company.com",
                "token_registered_at": "2025-10-02T10:30:00Z"
            }
        }


# ============================================================================
# FCM TOKEN REGISTRATION ENDPOINTS
# ============================================================================

@router.post("/register-token", response_model=FCMTokenResponse)
async def register_fcm_token(
    request: FCMTokenRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Register or update FCM token for the authenticated user
    
    This endpoint is called:
    - When user logs in and grants notification permission
    - When FCM token is generated for the first time
    - When user manually updates notification settings
    
    The token is stored in the user's document for sending push notifications
    """
    try:
        db = get_database()
        user_email = current_user.get("email")
        
        if not user_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User email not found in token"
            )
        
        # Update user document with FCM token
        update_data = {
            "fcm_token": request.fcm_token,
            "fcm_token_updated_at": datetime.utcnow()
        }
        
        if request.device_info:
            update_data["fcm_device_info"] = request.device_info
        
        result = await db.users.update_one(
            {"email": user_email},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        logger.info(f"FCM token registered for user: {user_email}")
        
        return FCMTokenResponse(
            success=True,
            message="FCM token registered successfully",
            user_email=user_email,
            token_registered_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering FCM token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register FCM token: {str(e)}"
        )


@router.put("/update-token", response_model=FCMTokenResponse)
async def update_fcm_token(
    request: FCMTokenRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Update FCM token when it refreshes
    
    This endpoint is called:
    - When FCM token automatically refreshes (happens periodically)
    - When user switches devices/browsers
    
    Same functionality as register-token but uses PUT for semantic clarity
    """
    try:
        db = get_database()
        user_email = current_user.get("email")
        
        if not user_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User email not found in token"
            )
        
        # Update user document with new FCM token
        update_data = {
            "fcm_token": request.fcm_token,
            "fcm_token_updated_at": datetime.utcnow()
        }
        
        if request.device_info:
            update_data["fcm_device_info"] = request.device_info
        
        result = await db.users.update_one(
            {"email": user_email},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        logger.info(f"FCM token updated for user: {user_email}")
        
        return FCMTokenResponse(
            success=True,
            message="FCM token updated successfully",
            user_email=user_email,
            token_registered_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating FCM token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update FCM token: {str(e)}"
        )


@router.delete("/remove-token")
async def remove_fcm_token(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Remove FCM token from user account
    
    This endpoint is called:
    - When user logs out
    - When user revokes notification permission
    - For cleanup purposes
    """
    try:
        db = get_database()
        user_email = current_user.get("email")
        
        if not user_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User email not found in token"
            )
        
        # Remove FCM token from user document
        result = await db.users.update_one(
            {"email": user_email},
            {
                "$unset": {
                    "fcm_token": "",
                    "fcm_device_info": ""
                },
                "$set": {
                    "fcm_token_removed_at": datetime.utcnow()
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        logger.info(f"FCM token removed for user: {user_email}")
        
        return {
            "success": True,
            "message": "FCM token removed successfully",
            "user_email": user_email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing FCM token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove FCM token: {str(e)}"
        )


@router.get("/token-status")
async def get_fcm_token_status(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Check if user has FCM token registered
    
    Useful for frontend to check notification setup status
    """
    try:
        db = get_database()
        user_email = current_user.get("email")
        
        if not user_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User email not found in token"
            )
        
        user = await db.users.find_one(
            {"email": user_email},
            {"fcm_token": 1, "fcm_token_updated_at": 1, "fcm_device_info": 1}
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        has_token = "fcm_token" in user and user["fcm_token"]
        
        return {
            "success": True,
            "has_token": has_token,
            "token_registered": has_token,
            "last_updated": user.get("fcm_token_updated_at"),
            "device_info": user.get("fcm_device_info")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking FCM token status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check FCM token status: {str(e)}"
        )