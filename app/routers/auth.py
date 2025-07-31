# app/routers/auth.py
# Updated with Tata Tele Auto-Sync Integration - LOGGER FIXED

from fastapi import APIRouter, HTTPException, status, Request, Depends, Query # type: ignore
from datetime import datetime, timedelta
from typing import Dict, Any, List, Union
import logging
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase as Database

# 🔧 FIX: Setup logging FIRST before using logger anywhere
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from ..config.database import get_database
from ..utils.security import security, verify_password, get_password_hash
from ..utils.dependencies import get_current_active_user, get_admin_user
from ..schemas.auth import (
    LoginRequest, LoginResponse, RegisterResponse,
    RefreshTokenRequest, RefreshTokenResponse,
    LogoutRequest, AuthResponse
)

# 🔥 FIXED: Import only the classes that exist in user models
from ..models.user import (
    UserCreate, UserResponse, UserUpdate, DepartmentHelper, 
    DepartmentCreate, DepartmentType
)
from ..config.settings import settings  # For token expiry settings

# 🆕 NEW: Import Tata services for auto-sync (NOW logger is available)
try:
    from ..services.tata_user_service import tata_user_service
    TATA_INTEGRATION_AVAILABLE = True
    logger.info("✅ Tata integration services imported successfully")
except ImportError as e:
    TATA_INTEGRATION_AVAILABLE = False
    logger.warning(f"⚠️ Tata integration not available: {e}")

router = APIRouter()

# =============================================================================
# EXISTING USER REGISTRATION - UNCHANGED
# =============================================================================

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
            "department": user_data.departments,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "created_by": current_user.get("email"),
            
            # 🆕 NEW: Initialize Tata calling fields
            "calling_enabled": False,
            "tata_agent_id": None,
            "tata_extension": None,
            "tata_sync_status": "pending",
            "last_tata_sync": None,
            "auto_sync_enabled": True,
            "routing_method": None,
            "tata_agent_pool": [],
            "calling_status": "pending",
            "calling_setup_date": None
        }
        
        # Insert user first
        result = await db.users.insert_one(user_doc)
        user_id = str(result.inserted_id)
        
        logger.info(f"User created with ID: {user_id}")
        
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
            "tata_sync_status": updated_user.get("tata_sync_status", "pending"),
            "calling_status": updated_user.get("calling_status"),
            "created_at": updated_user["created_at"].isoformat(),
            "last_login": user_data.get("last_login"),
            "permissions": user_data.get("permissions", {}),

        }
        
        success_message = f"User registered successfully! 📞 Tata calling will be enabled on first login"
        
        response = {
            "success": True,
            "message": success_message,
            "user": user_response,
            "note": "User will be auto-synced with Tata agents on first login"
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

# =============================================================================
# 🆕 ENHANCED LOGIN WITH TATA AUTO-SYNC
# =============================================================================

@router.post("/login", response_model=LoginResponse)
async def login_user(request: Request, login_data: LoginRequest):
    """
    Enhanced user login endpoint with Tata Tele auto-sync
    
    - Standard CRM authentication
    - Automatic Tata agent sync on login
    - Phone number matching with Tata agents
    - Extension/DID retrieval for calling
    - Enhanced response with calling status
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
    
    # 🆕 NEW: Auto-sync with Tata agents during login
    calling_status = {
        "enabled": False,
        "sync_status": "not_attempted",
        "message": "Tata integration not available"
    }
    
    if TATA_INTEGRATION_AVAILABLE and user.get("auto_sync_enabled", True):
        try:
            logger.info(f"Starting Tata auto-sync for user: {user['email']}")
            calling_status = await tata_user_service.auto_sync_on_login(user)
            
            # Update user record with calling status
            await db.users.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {
                        "calling_enabled": calling_status.get("enabled", False),
                        "tata_extension": calling_status.get("extension"),
                        "tata_agent_id": calling_status.get("agent_id"),
                        "tata_sync_status": calling_status.get("sync_status", "unknown"),
                        "last_tata_sync": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"Tata auto-sync completed for {user['email']}: {calling_status.get('sync_status')}")
            
        except Exception as e:
            logger.warning(f"Tata auto-sync failed for {user['email']}: {str(e)}")
            calling_status = {
                "enabled": False,
                "sync_status": "failed",
                "message": f"Auto-sync failed: {str(e)}"
            }
    else:
        if not TATA_INTEGRATION_AVAILABLE:
            logger.debug("Tata integration not available - skipping auto-sync")
        else:
            logger.debug(f"Auto-sync disabled for user {user['email']}")
    
    # Create tokens
    token_data = {
        "sub": str(user["_id"]),
        "email": user["email"],
        "username": user["username"],
        "role": user["role"]
    }
    
    access_token = security.create_access_token(token_data)

    # Use remember_me for refresh token expiry
    if login_data.remember_me:
        refresh_token = security.create_refresh_token(token_data, expire_days=30)
    else:
        refresh_token = security.create_refresh_token(token_data, expire_days=7)
        
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
    
    # 🆕 ENHANCED: Login response with calling status
    user_response = {
        "id": str(user["_id"]),
        "email": user["email"],
        "username": user["username"],
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "role": user["role"],
        
        # 🆕 NEW: Tata calling fields
        "calling_enabled": calling_status.get("enabled", False),
        "tata_extension": calling_status.get("extension"),
        "tata_agent_id": calling_status.get("agent_id"),
        "sync_status": calling_status.get("sync_status", "unknown"),
        "ready_to_call": calling_status.get("enabled", False)
    }
    
    # Log successful login with calling status
    if calling_status.get("enabled"):
        logger.info(f"✅ Successful login for {user['email']} - Calling enabled (Ext: {calling_status.get('extension')})")
    else:
        logger.info(f"✅ Successful login for {user['email']} - Calling status: {calling_status.get('sync_status')}")
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=security.access_token_expire_minutes * 60,
        user=user_response,
        # 🆕 NEW: Include calling status in response
        calling_status=calling_status.get("sync_status", "unknown"),
        message=calling_status.get("message") if not calling_status.get("enabled") else None
    )

# =============================================================================
# EXISTING ENDPOINTS - UNCHANGED (keeping all your existing code)
# =============================================================================

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
    Get current user information with multi-department support and calling status
    """
    try:
        # Handle both old and new department formats
        departments = current_user.get("departments")
        old_department = current_user.get("department")
        
        # Determine departments field based on what's available
        if departments is not None:
            # New format - use departments field
            if isinstance(departments, str):
                department_list = [departments]
                departments_field = departments
            elif isinstance(departments, list):
                department_list = departments
                departments_field = departments
            else:
                department_list = []
                departments_field = [] if current_user.get("role") == "user" else "admin"
        elif old_department is not None:
            # Old format - convert old department field
            if current_user.get("role") == "admin":
                departments_field = "admin"  # Admin gets string
                department_list = ["admin"]
            else:
                departments_field = [old_department.lower()]  # User gets array
                department_list = [old_department.lower()]
        else:
            # No department field at all - set defaults
            if current_user.get("role") == "admin":
                departments_field = "admin"
                department_list = ["admin"]
            else:
                departments_field = []
                department_list = []
        
        return UserResponse(
            id=str(current_user["_id"]),
            email=current_user["email"],
            username=current_user["username"],
            first_name=current_user["first_name"],
            last_name=current_user["last_name"],
            role=current_user["role"],
            is_active=current_user["is_active"],
            phone=current_user.get("phone"),
            departments=departments_field,
            department_list=department_list,
            created_at=current_user["created_at"],
            last_login=current_user.get("last_login"),
            assigned_leads=current_user.get("assigned_leads", []),
            total_assigned_leads=current_user.get("total_assigned_leads", 0),
            
            # 🆕 NEW: Include Tata calling fields
            calling_enabled=current_user.get("calling_enabled", False),
            tata_extension=current_user.get("tata_extension"),
            tata_agent_id=current_user.get("tata_agent_id"),
            tata_sync_status=current_user.get("tata_sync_status", "pending"),
            
            # Legacy fields (if still needed)
            extension_number=current_user.get("extension_number"),
            smartflo_agent_id=current_user.get("smartflo_agent_id"),
            smartflo_user_id=current_user.get("smartflo_user_id"),
            calling_status=current_user.get("calling_status", "pending")
        )
        
    except Exception as e:
        logger.error(f"Error getting user info: {e}")
        logger.error(f"User data: {current_user}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user information"
        )

# =============================================================================
# EMERGENCY ADMIN AND DEBUG ENDPOINTS - UNCHANGED
# =============================================================================

@router.post("/emergency-admin", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_emergency_admin(user_data: UserCreate):
    """
    🚨 EMERGENCY ENDPOINT: Create admin when database has no admins
    ⚠️ REMOVE THIS ENDPOINT AFTER CREATING YOUR ADMIN!
    """
    try:
        db = get_database()
        
        # Security check: Only allow if NO admin users exist
        admin_count = await db.users.count_documents({"role": "admin"})
        if admin_count > 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Emergency endpoint disabled - Admin users already exist. Use regular registration."
            )
        
        logger.warning("🚨 EMERGENCY ADMIN CREATION INITIATED - NO ADMINS FOUND IN DATABASE")
        
        # Check if user already exists
        existing_user = await db.users.find_one({"email": user_data.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Force admin role for security
        user_data.role = "admin"
        
        # Hash password
        hashed_password = get_password_hash(user_data.password)
        
        # Create admin user document
        user_doc = {
            "email": user_data.email,
            "username": user_data.username,
            "first_name": user_data.first_name,
            "last_name": user_data.last_name,
            "full_name": f"{user_data.first_name} {user_data.last_name}",
            "hashed_password": hashed_password,
            "role": "admin",
            "phone": user_data.phone,
            "department": user_data.department,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "created_by": "emergency_system",
            "failed_login_attempts": 0,
            "login_count": 0,
            
            # Initialize Tata fields
            "calling_enabled": False,
            "tata_sync_status": "pending",
            "auto_sync_enabled": True
        }
        
        # Insert admin user
        result = await db.users.insert_one(user_doc)
        user_id = str(result.inserted_id)
        
        logger.warning(f"🚨 EMERGENCY ADMIN CREATED: {user_data.email}")
        
        return {
            "success": True,
            "message": "🚨 EMERGENCY ADMIN CREATED! Remove this endpoint immediately for security!",
            "user": {
                "user_id": user_id,
                "email": user_data.email,
                "username": user_data.username,
                "first_name": user_data.first_name,
                "last_name": user_data.last_name,
                "role": "admin",
                "created_at": user_doc["created_at"]
            },
            "next_steps": [
                "1. Test login with new admin credentials",
                "2. Remove this /emergency-admin endpoint from code",
                "3. Use regular /register endpoint for future users"
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Emergency admin creation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Emergency admin creation failed: {str(e)}"
        )

@router.get("/debug-admin-users")
async def debug_admin_users():
    """
    🔍 TEMPORARY DIAGNOSTIC: Show existing admin users (emails only for security)
    ⚠️ REMOVE THIS ENDPOINT AFTER DEBUGGING!
    """
    try:
        db = get_database()
        
        # Find all admin users (but only return safe fields)
        admin_users = await db.users.find(
            {"role": "admin"}, 
            {
                "email": 1, 
                "username": 1, 
                "first_name": 1, 
                "last_name": 1, 
                "is_active": 1,
                "created_at": 1,
                "created_by": 1,
                "calling_enabled": 1,
                "tata_sync_status": 1
            }
        ).to_list(None)
        
        # Count total users by role
        admin_count = await db.users.count_documents({"role": "admin"})
        user_count = await db.users.count_documents({"role": "user"})
        total_count = await db.users.count_documents({})
        
        return {
            "database_status": "connected",
            "admin_users_found": admin_count,
            "regular_users_found": user_count,
            "total_users": total_count,
            "admin_users": [
                {
                    "email": user["email"],
                    "username": user.get("username", "N/A"),
                    "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                    "is_active": user.get("is_active", False),
                    "calling_enabled": user.get("calling_enabled", False),
                    "tata_sync_status": user.get("tata_sync_status", "unknown"),
                    "created_at": user.get("created_at"),
                    "created_by": user.get("created_by", "unknown")
                }
                for user in admin_users
            ],
            "next_steps": [
                "1. Try logging in with one of these admin emails",
                "2. If you forgot the password, you may need to reset it",
                "3. Remove this diagnostic endpoint after debugging"
            ]
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "database_status": "connection_failed"
        }

# =============================================================================
# ALL OTHER EXISTING ENDPOINTS REMAIN EXACTLY THE SAME...
# (Department management, user management, refresh token, etc.)
# I'm keeping the complete file structure but showing key sections
# =============================================================================

@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: Database = Depends(get_database)
):
    """
    Refresh access token using refresh token with token rotation
    """
    try:
        # Verify refresh token
        payload = security.verify_token(request.refresh_token)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Check token type
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        # Check if token is blacklisted
        token_jti = payload.get("jti")
        if token_jti and await security.is_token_blacklisted(token_jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked"
            )
        
        # Get user from database
        user_id = payload.get("sub")
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        
        if not user or not user.get("is_active", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # Create new tokens with same user data
        token_data = {
            "sub": str(user["_id"]),
            "email": user["email"],
            "username": user["username"],
            "role": user["role"]
        }

        new_access_token = security.create_access_token(token_data)
        new_refresh_token = security.create_refresh_token(token_data, expire_days=7)

        # Blacklist the old refresh token for security
        if token_jti:
            await security.blacklist_token(token_jti)

        # Update last activity
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"last_activity": datetime.utcnow()}}
        )

        logger.info(f"Token refreshed for user: {user['email']} (with token rotation)")

        return RefreshTokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=security.access_token_expire_minutes * 60
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not refresh token"
        )

# =============================================================================
# 🆕 NEW: TATA SYNC MANAGEMENT ENDPOINTS
# =============================================================================

@router.post("/force-tata-sync", response_model=Dict[str, Any])
async def force_tata_sync(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Force Tata sync for current user (manual trigger)
    
    - **Manual Sync**: Trigger Tata agent sync outside of login
    - **Status Update**: Updates user's calling status immediately
    - **Error Handling**: Provides detailed sync failure information  
    """
    if not TATA_INTEGRATION_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tata integration service is not available"
        )
    
    try:
        db = get_database()
        user_id = str(current_user["_id"])
        
        logger.info(f"Manual Tata sync requested by user: {current_user['email']}")
        
        # Perform sync
        calling_status = await tata_user_service.auto_sync_on_login(current_user)
        
        # Update user record
        await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "calling_enabled": calling_status.get("enabled", False),
                    "tata_extension": calling_status.get("extension"),
                    "tata_agent_id": calling_status.get("agent_id"),
                    "tata_sync_status": calling_status.get("sync_status", "unknown"),
                    "last_tata_sync": datetime.utcnow()
                }
            }
        )
        
        return {
            "success": True,
            "message": "Tata sync completed",
            "sync_result": calling_status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Manual Tata sync failed for {current_user['email']}: {str(e)}")
        return {
            "success": False,
            "message": f"Tata sync failed: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        }

@router.get("/tata-sync-status", response_model=Dict[str, Any])
async def get_tata_sync_status(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get current user's Tata sync status and calling information
    
    - **Status Check**: Current sync status and calling capability
    - **Extension Info**: User's assigned Tata extension/DID  
    - **Sync History**: Last sync time and result
    """
    try:
        return {
            "success": True,
            "user_id": str(current_user["_id"]),
            "email": current_user["email"],
            "calling_enabled": current_user.get("calling_enabled", False),
            "tata_extension": current_user.get("tata_extension"),
            "tata_agent_id": current_user.get("tata_agent_id"), 
            "sync_status": current_user.get("tata_sync_status", "unknown"),
            "last_sync": current_user.get("last_tata_sync"),
            "auto_sync_enabled": current_user.get("auto_sync_enabled", True),
            "integration_available": TATA_INTEGRATION_AVAILABLE
        }
        
    except Exception as e:
        logger.error(f"Error getting Tata sync status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get sync status"
        )

# =============================================================================
# NOTE: ALL OTHER DEPARTMENT MANAGEMENT ENDPOINTS FROM YOUR ORIGINAL FILE
# ARE PRESERVED EXACTLY AS THEY WERE - I'm not including them here to keep
# the response manageable, but they should all be copied over unchanged
# =============================================================================