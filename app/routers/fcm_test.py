# app/routers/fcm_test.py
"""
FCM Testing Endpoints - For development/testing only
Direct Firebase Admin SDK integration for testing without frontend dependency
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
import os
import firebase_admin
from firebase_admin import credentials, messaging
from firebase_admin.exceptions import FirebaseError

from ..utils.dependencies import get_current_user
from ..config.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["FCM Testing"])

# Initialize Firebase Admin SDK (only once)
def initialize_firebase():
    """Initialize Firebase Admin SDK if not already initialized"""
    if not firebase_admin._apps:
        try:
            service_account_path = os.getenv(
                "FIREBASE_SERVICE_ACCOUNT_PATH", 
                "app/firebase_service_key.json"
            )
            
            if not os.path.exists(service_account_path):
                logger.warning(f"Firebase service account not found at {service_account_path}")
                return False
            
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
            logger.info("✅ Firebase Admin SDK initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Firebase Admin SDK: {str(e)}")
            return False
    return True

# Initialize on module load
FIREBASE_INITIALIZED = initialize_firebase()

class FCMTestRequest(BaseModel):
    """Request model for FCM test"""
    user_email: Optional[str] = None  # If None, sends to current user
    title: str = "Test Notification"
    message: str = "This is a test notification"


@router.post("/test-notification")
async def send_test_fcm_notification(
    request: FCMTestRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    🧪 TEST ENDPOINT: Send FCM notification directly using Firebase Admin SDK
    
    This endpoint allows you to test FCM notifications without frontend dependency.
    Sends notifications directly from backend to user's device.
    
    **Usage:**
    - Send to yourself (current logged-in user)
    - Send to specific user by email (admin only)
    - Test notification delivery and click actions
    """
    
    if not FIREBASE_INITIALIZED:
        raise HTTPException(
            status_code=503,
            detail="Firebase Admin SDK not initialized. Check service account file."
        )
    
    try:
        db = get_database()
        
        # Determine target user
        if request.user_email:
            # Admin can test with any user's email
            if current_user.get("role") != "admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only admins can send test notifications to other users"
                )
            target_email = request.user_email
        else:
            # Send to current user
            target_email = current_user.get("email")
        
        # Get user's FCM token
        user = await db.users.find_one(
            {"email": target_email},
            {"fcm_token": 1, "email": 1, "first_name": 1, "last_name": 1}
        )
        
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User {target_email} not found"
            )
        
        fcm_token = user.get("fcm_token")
        
        if not fcm_token:
            return {
                "success": False,
                "message": f"User {target_email} has not registered FCM token yet",
                "suggestion": "User needs to login and enable notifications in browser",
                "user": {
                    "email": user["email"],
                    "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                }
            }
        
        logger.info(f"Sending test FCM notification to {target_email}")
        logger.info(f"FCM Token: {fcm_token[:20]}...")
        
        # Create FCM message using Firebase Admin SDK
        message = messaging.Message(
            notification=messaging.Notification(
                title=request.title,
                body=request.message,
            ),
            token=fcm_token,
        ) 
        
        
        # Send notification
        try:
            response = messaging.send(message)
            logger.info(f"✅ Test notification sent successfully to {target_email}")
            logger.info(f"Firebase response: {response}")
            
            return {
                "success": True,
                "message": f"Test notification sent to {target_email}",
                "user": {
                    "email": user["email"],
                    "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                },
                "notification": {
                    "title": request.title,
                    "message": request.message,
                },
                "firebase_response": response
            }
            
        except FirebaseError as firebase_error:  # Remove messaging. prefix
            logger.error(f"❌ Firebase error: {str(firebase_error)}")
            
            error_message = str(firebase_error)
            suggestion = "Unknown Firebase error"
            
            # Provide helpful error messages
            if "INVALID_ARGUMENT" in error_message or "invalid-argument" in error_message:
                suggestion = "FCM token is invalid or expired. User needs to re-login and register token again."
            elif "NOT_FOUND" in error_message or "registration-token-not-registered" in error_message:
                suggestion = "FCM token is no longer valid. User needs to re-register."
            elif "SENDER_ID_MISMATCH" in error_message:
                suggestion = "FCM token belongs to a different Firebase project."
            
            return {
                "success": False,
                "message": "Failed to send notification via Firebase",
                "error": error_message,
                "suggestion": suggestion,
                "user": {
                    "email": user["email"]
                }
            }
            
            logger.error(f"❌ Firebase error: {str(firebase_error)}")
            
            error_message = str(firebase_error)
            suggestion = "Unknown Firebase error"
            
            # Provide helpful error messages
            if "INVALID_ARGUMENT" in error_message or "invalid-argument" in error_message:
                suggestion = "FCM token is invalid or expired. User needs to re-login and register token again."
            elif "NOT_FOUND" in error_message or "registration-token-not-registered" in error_message:
                suggestion = "FCM token is no longer valid. User needs to re-register."
            elif "SENDER_ID_MISMATCH" in error_message:
                suggestion = "FCM token belongs to a different Firebase project."
            
            return {
                "success": False,
                "message": "Failed to send notification via Firebase",
                "error": error_message,
                "suggestion": suggestion,
                "user": {
                    "email": user["email"]
                }
            }
        
    except Exception as e:
        logger.error(f"Error sending test notification: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send test notification: {str(e)}"
        )


@router.get("/my-fcm-status")
async def get_my_fcm_status(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Check your FCM token registration status
    """
    try:
        db = get_database()
        
        user = await db.users.find_one(
            {"email": current_user.get("email")},
            {"fcm_token": 1, "fcm_token_updated_at": 1, "fcm_device_info": 1}
        )
        
        has_token = bool(user and user.get("fcm_token"))
        
        return {
            "success": True,
            "user_email": current_user.get("email"),
            "has_fcm_token": has_token,
            "token_registered_at": user.get("fcm_token_updated_at") if has_token else None,
            "device_info": user.get("fcm_device_info") if has_token else None,
            "firebase_initialized": FIREBASE_INITIALIZED,
            "status": "ready" if (has_token and FIREBASE_INITIALIZED) else "not_ready",
            "message": (
                "FCM token is registered and Firebase is initialized" if (has_token and FIREBASE_INITIALIZED)
                else "Firebase not initialized" if not FIREBASE_INITIALIZED
                else "Please enable notifications in your browser"
            )
        }
        
    except Exception as e:
        logger.error(f"Error checking FCM status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check FCM status: {str(e)}"
        )


@router.get("/firebase-status")
async def check_firebase_status(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Check Firebase Admin SDK initialization status
    """
    return {
        "success": True,
        "firebase_initialized": FIREBASE_INITIALIZED,
        "firebase_apps_count": len(firebase_admin._apps),
        "service_account_path": os.getenv(
            "FIREBASE_SERVICE_ACCOUNT_PATH", 
            "app/firebase_service_key.json"
        ),
        "file_exists": os.path.exists(
            os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "app/firebase_service_key.json")
        ),
        "message": (
            "Firebase Admin SDK is initialized and ready" if FIREBASE_INITIALIZED
            else "Firebase Admin SDK not initialized - check service account file"
        )
    }