from fastapi import APIRouter, HTTPException, status, Request, Depends
from datetime import datetime, timedelta
from typing import Dict, Any
import logging
from bson import ObjectId

from ..config.database import get_database
from ..utils.security import security, verify_password, get_password_hash
from ..utils.dependencies import get_current_active_user
from ..schemas.auth import (
    LoginRequest, LoginResponse, RegisterResponse,
    RefreshTokenRequest, RefreshTokenResponse,
    LogoutRequest, AuthResponse
)


from ..utils.dependencies import get_admin_user
from ..models.user import UserCreate, UserResponse

logger = logging.getLogger(__name__)
router = APIRouter()
# REPLACE your existing register_user function in app/routers/auth.py with this:

# Updated register_user function for app/routers/auth.py - WITH CALL ROUTING

@router.post("/register", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Register a new user with call routing capability (no fixed extensions)
    Admin only endpoint with TATA Call Routing integration
    """
    try:
        db = get_database()
        logger.info(f"Admin {current_user.get('email')} registering new user: {user_data.email}")
        
        # Check if user already exists
        existing_user = await db.users.find_one({"email": user_data.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Hash password
        hashed_password = get_password_hash(user_data.password)
        
        # Prepare user document
        user_doc = {
            "email": user_data.email,
            "username": user_data.username,
            "first_name": user_data.first_name,
            "last_name": user_data.last_name,
            "full_name": f"{user_data.first_name} {user_data.last_name}",
            "hashed_password": hashed_password,
            "role": user_data.role,
            "phone": user_data.phone,
            "department": user_data.department,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "created_by": current_user.get("email"),
            
            # Initialize call routing fields
            "calling_enabled": False,
            "routing_method": None,
            "tata_agent_pool": [],
            "calling_status": "pending",
            "calling_setup_date": None
        }
        
        # Insert user first
        result = await db.users.insert_one(user_doc)
        user_id = str(result.inserted_id)
        
        logger.info(f"User created with ID: {user_id}")
        
        # Now try to setup call routing
        calling_setup_successful = False
        calling_error = None
        available_agents = 0
        routing_method = None
        
        try:
            logger.info(f"Setting up call routing for user: {user_data.email}")
            
            smartflo_user_data = {
                "first_name": user_data.first_name,
                "last_name": user_data.last_name,
                "email": user_data.email,
                "phone": user_data.phone,
                "department": user_data.department
            }
            
            routing_result = await smartflo_jwt_service.create_agent(smartflo_user_data)
            
            if routing_result.get("success"):
                available_agents = routing_result.get("available_agents", 0)
                routing_method = routing_result.get("routing_method")
                
                # Update user with call routing information
                update_success = await smartflo_jwt_service.update_user_calling_info(
                    user_id=user_id,
                    routing_info=routing_result
                )
                
                if update_success:
                    calling_setup_successful = True
                    logger.info(f"✅ Call routing setup complete! {available_agents} agents available")
                else:
                    calling_error = "Failed to update user with routing info"
                    logger.error(calling_error)
            else:
                calling_error = routing_result.get("error", "Unknown routing setup error")
                logger.error(f"❌ Call routing setup failed: {calling_error}")
                
        except Exception as e:
            calling_error = f"Call routing integration error: {str(e)}"
            logger.error(calling_error)
        
        # Get the updated user data
        updated_user = await db.users.find_one({"_id": ObjectId(user_id)})
        
        # Prepare response
        user_response = {
            "id": user_id,
            "email": updated_user["email"],
            "username": updated_user["username"],
            "first_name": updated_user["first_name"],
            "last_name": updated_user["last_name"],
            "role": updated_user["role"],
            "phone": updated_user["phone"],
            "department": updated_user["department"],
            "is_active": updated_user["is_active"],
            "calling_enabled": updated_user.get("calling_enabled", False),
            "routing_method": updated_user.get("routing_method"),
            "calling_status": updated_user.get("calling_status"),
            "created_at": updated_user["created_at"].isoformat()
        }
        
        # Success message with call routing info
        if calling_setup_successful:
            success_message = f"User registered successfully! 📞 Call routing enabled ({available_agents} agents available)"
        elif calling_error:
            success_message = f"User registered successfully! ⚠️ Call routing setup failed: {calling_error}"
        else:
            success_message = "User registered successfully! 📞 Call routing pending"
        
        response = {
            "success": True,
            "message": success_message,
            "user": user_response
        }
        
        # Add call routing setup info
        if calling_setup_successful:
            response["calling_setup"] = {
                "setup_successful": True,
                "routing_method": routing_method,
                "available_agents": available_agents,
                "authentication_method": "JWT Bearer Token",
                "note": f"Calls will route through {available_agents} available TATA agents"
            }
        elif calling_error:
            response["calling_setup"] = {
                "setup_successful": False,
                "error": calling_error,
                "authentication_method": "JWT Bearer Token"
            }
        
        logger.info(f"✅ User registration complete: {user_data.email}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration failed: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )

@router.post("/login", response_model=LoginResponse)
async def login_user(request: Request, login_data: LoginRequest):
    """
    User login endpoint
    """
    db = get_database()
    
    # Find user by email
    user = await db.users.find_one({"email": login_data.email})
    if not user:
        logger.warning(f"Login attempt with non-existent email: {login_data.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Check if account is locked
    if user.get("locked_until") and user["locked_until"] > datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is temporarily locked due to too many failed attempts"
        )
    
    # Verify password
    if not verify_password(login_data.password, user["hashed_password"]):
        # Increment failed login attempts
        failed_attempts = user.get("failed_login_attempts", 0) + 1
        update_data = {"failed_login_attempts": failed_attempts}
        
        # Lock account after 5 failed attempts
        if failed_attempts >= 5:
            update_data["locked_until"] = datetime.utcnow() + timedelta(minutes=30)
        
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": update_data}
        )
        
        logger.warning(f"Failed login attempt for {login_data.email}. Attempts: {failed_attempts}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Check if user is active
    if not user.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is disabled"
        )
    
    # Reset failed login attempts and update login info
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "last_login": datetime.utcnow(),
                "last_activity": datetime.utcnow(),
                "failed_login_attempts": 0,
                "locked_until": None
            },
            "$inc": {"login_count": 1}
        }
    )
    
    # Create tokens
    token_data = {
        "sub": str(user["_id"]),
        "email": user["email"],
        "username": user["username"],
        "role": user["role"]
    }
    
    access_token = security.create_access_token(token_data)
    refresh_token = security.create_refresh_token(token_data)
    
    # Store session info
    session_data = {
        "user_id": str(user["_id"]),
        "session_id": security.verify_token(access_token)["jti"],
        "created_at": datetime.utcnow(),
        "last_activity": datetime.utcnow(),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    await db.user_sessions.insert_one(session_data)
    
    logger.info(f"Successful login for user: {user['email']}")
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=security.access_token_expire_minutes * 60,
        user={
            "id": str(user["_id"]),
            "email": user["email"],
            "username": user["username"],
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "role": user["role"]
        }
    )

@router.post("/logout", response_model=AuthResponse)
async def logout_user(
    logout_data: LogoutRequest,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    User logout endpoint
    """
    db = get_database()
    
    try:
        # Remove user session
        await db.user_sessions.delete_many({"user_id": current_user["_id"]})
        
        logger.info(f"User logged out: {current_user['email']}")
        
        return AuthResponse(
            success=True,
            message="Successfully logged out"
        )
        
    except Exception as e:
        logger.error(f"Logout error for user {current_user['email']}: {e}")
        return AuthResponse(
            success=True,  # Return success even if session cleanup fails
            message="Logged out"
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get current user information
    """
    return UserResponse(
        id=current_user["_id"],
        email=current_user["email"],
        username=current_user["username"],
        first_name=current_user["first_name"],
        last_name=current_user["last_name"],
        role=current_user["role"],
        is_active=current_user["is_active"],
        phone=current_user.get("phone"),
        department=current_user.get("department"),
        created_at=current_user["created_at"],
        last_login=current_user.get("last_login")
    )