# REPLACE THE IMPORT SECTION AT THE TOP OF YOUR app/routers/auth.py

from fastapi import APIRouter, HTTPException, status, Request, Depends, Query # type: ignore
from datetime import datetime, timedelta
from typing import Dict, Any, List, Union
import logging
from bson import ObjectId

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
    Get current user information with multi-department support
    Handles both old and new department formats
    """
    try:
        # 🔥 FIXED: Handle both old and new department formats
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
            departments=departments_field,  # 🔥 FIXED: Properly set departments
            department_list=department_list,  # 🔥 FIXED: Always as list
            created_at=current_user["created_at"],
            last_login=current_user.get("last_login"),
            assigned_leads=current_user.get("assigned_leads", []),
            total_assigned_leads=current_user.get("total_assigned_leads", 0),
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


# Add this to your app/routers/auth.py file (TEMPORARY)

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
            "login_count": 0
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
    
# Add this TEMPORARY diagnostic endpoint to app/routers/auth.py

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
                "created_by": 1
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
    
# ADD THESE ENDPOINTS TO app/routers/auth.py

# 🚀 NEW: Department Management Endpoints

# UPDATE THESE FUNCTIONS IN app/routers/auth.py

@router.get("/departments", response_model=Dict[str, Any])
async def get_all_departments(
    include_user_count: bool = Query(False, description="Include user count for each department"),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get all available departments (only admin is predefined, rest are custom)
    Used for dropdowns in user creation and lead assignment
    """
    try:
        from ..models.user import DepartmentHelper
        
        logger.info(f"Getting departments for user: {current_user.get('email')}")
        
        # Get all departments (only admin predefined, rest custom)
        all_departments = await DepartmentHelper.get_all_departments()
        
        # Add user counts if requested
        if include_user_count:
            for dept in all_departments:
                dept["user_count"] = await DepartmentHelper.get_department_users_count(dept["name"])
        
        # Separate predefined (only admin) and custom
        predefined = [dept for dept in all_departments if dept.get("is_predefined", False)]
        custom = [dept for dept in all_departments if not dept.get("is_predefined", False)]
        
        return {
            "success": True,
            "departments": {
                "predefined": predefined,  # Only admin
                "custom": custom,          # All others
                "all": all_departments
            },
            "total_count": len(all_departments),
            "predefined_count": len(predefined),  # Should be 1 (admin)
            "custom_count": len(custom),
            "message": "Only 'admin' is predefined. All other departments are created by admins."
        }
        
    except Exception as e:
        logger.error(f"Error getting departments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get departments"
        )

@router.post("/departments", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_department(
    department_data: DepartmentCreate,
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Admin only
):
    """
    Create a new custom department (Admin only)
    All departments except 'admin' are created this way
    """
    try:
        from ..models.user import DepartmentHelper
        
        db = get_database()
        logger.info(f"Admin {current_user.get('email')} creating new department: {department_data.name}")
        
        # Check if department already exists (custom departments only, admin is always reserved)
        if department_data.name == "admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create department named 'admin' - it is reserved for system administration"
            )
        
        # Check custom departments
        existing_custom = await db.departments.find_one({"name": department_data.name})
        if existing_custom:
            if existing_custom.get("is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Department '{department_data.name}' already exists"
                )
            else:
                # Reactivate if it was deactivated
                await db.departments.update_one(
                    {"_id": existing_custom["_id"]},
                    {
                        "$set": {
                            "is_active": True,
                            "description": department_data.description,
                            "updated_at": datetime.utcnow(),
                            "reactivated_by": current_user.get("email")
                        }
                    }
                )
                return {
                    "success": True,
                    "message": f"Department '{department_data.name}' reactivated successfully",
                    "department_id": str(existing_custom["_id"]),
                    "action": "reactivated"
                }
        
        # Create new department
        department_doc = {
            "name": department_data.name,
            "display_name": department_data.name.replace('-', ' ').title(),
            "description": department_data.description,
            "is_active": department_data.is_active,
            "is_predefined": False,  # All created departments are custom
            "created_at": datetime.utcnow(),
            "created_by": current_user.get("email"),
            "updated_at": datetime.utcnow()
        }
        
        result = await db.departments.insert_one(department_doc)
        department_id = str(result.inserted_id)
        
        logger.info(f"✅ Custom department created: {department_data.name} by {current_user.get('email')}")
        
        return {
            "success": True,
            "message": f"Department '{department_data.name}' created successfully",
            "department": {
                "id": department_id,
                "name": department_data.name,
                "display_name": department_doc["display_name"],
                "description": department_data.description,
                "is_predefined": False,
                "is_active": True
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating department: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create department: {str(e)}"
        )

# 🚀 NEW: Bulk department creation endpoint
@router.post("/departments/bulk", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_departments_bulk(
    departments_list: List[DepartmentCreate],
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Admin only
):
    """
    Create multiple departments at once (Admin only)
    Useful for initial setup or migrating from other systems
    """
    try:
        db = get_database()
        logger.info(f"Admin {current_user.get('email')} creating {len(departments_list)} departments in bulk")
        
        created_departments = []
        failed_departments = []
        
        for dept_data in departments_list:
            try:
                # Check if department already exists
                if dept_data.name == "admin":
                    failed_departments.append({
                        "name": dept_data.name,
                        "error": "Cannot create 'admin' department - it is reserved"
                    })
                    continue
                
                existing = await db.departments.find_one({"name": dept_data.name})
                if existing and existing.get("is_active", True):
                    failed_departments.append({
                        "name": dept_data.name,
                        "error": "Department already exists"
                    })
                    continue
                
                # Create department
                department_doc = {
                    "name": dept_data.name,
                    "display_name": dept_data.name.replace('-', ' ').title(),
                    "description": dept_data.description,
                    "is_active": dept_data.is_active,
                    "is_predefined": False,
                    "created_at": datetime.utcnow(),
                    "created_by": current_user.get("email"),
                    "updated_at": datetime.utcnow()
                }
                
                result = await db.departments.insert_one(department_doc)
                
                created_departments.append({
                    "id": str(result.inserted_id),
                    "name": dept_data.name,
                    "display_name": department_doc["display_name"],
                    "description": dept_data.description
                })
                
            except Exception as e:
                failed_departments.append({
                    "name": dept_data.name,
                    "error": str(e)
                })
        
        return {
            "success": True,
            "message": f"Bulk department creation completed",
            "created_count": len(created_departments),
            "failed_count": len(failed_departments),
            "created_departments": created_departments,
            "failed_departments": failed_departments
        }
        
    except Exception as e:
        logger.error(f"Error in bulk department creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create departments in bulk: {str(e)}"
        )

# 🚀 NEW: Setup starter departments endpoint
@router.post("/departments/setup-starter", response_model=Dict[str, Any])
async def setup_starter_departments(
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Admin only
):
    """
    Create a basic set of common departments for new installations
    Only works if no custom departments exist yet
    """
    try:
        from ..models.user import DepartmentSetupHelper
        
        db = get_database()
        logger.info(f"Admin {current_user.get('email')} setting up starter departments")
        
        # Check if any custom departments already exist
        existing_count = await db.departments.count_documents({})
        
        if existing_count > 0:
            existing_depts = await db.departments.find({}, {"name": 1}).to_list(None)
            dept_names = [dept["name"] for dept in existing_depts]
            
            return {
                "success": False,
                "message": "Starter departments not created - custom departments already exist",
                "existing_departments": dept_names,
                "suggestion": "Use the regular 'Create Department' endpoint to add more departments"
            }
        
        # Create starter departments
        starter_departments = [
            {
                "name": "sales",
                "display_name": "Sales",
                "description": "Sales and business development",
                "is_active": True,
                "is_predefined": False,
                "created_at": datetime.utcnow(),
                "created_by": current_user.get("email")
            },
            {
                "name": "marketing",
                "display_name": "Marketing", 
                "description": "Marketing and lead generation",
                "is_active": True,
                "is_predefined": False,
                "created_at": datetime.utcnow(),
                "created_by": current_user.get("email")
            },
            {
                "name": "support",
                "display_name": "Support",
                "description": "Customer support and assistance",
                "is_active": True,
                "is_predefined": False,
                "created_at": datetime.utcnow(),
                "created_by": current_user.get("email")
            },
            {
                "name": "operations",
                "display_name": "Operations",
                "description": "Business operations and processes",
                "is_active": True,
                "is_predefined": False,
                "created_at": datetime.utcnow(),
                "created_by": current_user.get("email")
            },
            {
                "name": "hr",
                "display_name": "HR",
                "description": "Human resources management",
                "is_active": True,
                "is_predefined": False,
                "created_at": datetime.utcnow(),
                "created_by": current_user.get("email")
            }
        ]
        
        # Insert starter departments
        result = await db.departments.insert_many(starter_departments)
        
        created_names = [dept["name"] for dept in starter_departments]
        
        logger.info(f"✅ Created {len(starter_departments)} starter departments: {created_names}")
        
        return {
            "success": True,
            "message": f"Created {len(starter_departments)} starter departments",
            "created_departments": created_names,
            "note": "You can now create users with these departments or add more departments as needed"
        }
        
    except Exception as e:
        logger.error(f"Error setting up starter departments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to setup starter departments: {str(e)}"
        )


@router.post("/departments", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_department(
    department_data: DepartmentCreate,
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Admin only
):
    """
    Create a new custom department (Admin only)
    """
    try:
        from ..models.user import DepartmentHelper, DepartmentType
        
        db = get_database()
        logger.info(f"Admin {current_user.get('email')} creating new department: {department_data.name}")
        
        # Check if department already exists (predefined or custom)
        # Check predefined departments
        predefined_names = [dept.value for dept in DepartmentType]
        if department_data.name in predefined_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Department '{department_data.name}' already exists as a predefined department"
            )
        
        # Check custom departments
        existing_custom = await db.departments.find_one({"name": department_data.name})
        if existing_custom:
            if existing_custom.get("is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Department '{department_data.name}' already exists"
                )
            else:
                # Reactivate if it was deactivated
                await db.departments.update_one(
                    {"_id": existing_custom["_id"]},
                    {
                        "$set": {
                            "is_active": True,
                            "description": department_data.description,
                            "updated_at": datetime.utcnow(),
                            "reactivated_by": current_user.get("email")
                        }
                    }
                )
                return {
                    "success": True,
                    "message": f"Department '{department_data.name}' reactivated successfully",
                    "department_id": str(existing_custom["_id"]),
                    "action": "reactivated"
                }
        
        # Create new department
        department_doc = {
            "name": department_data.name,
            "display_name": department_data.name.replace('-', ' ').title(),
            "description": department_data.description,
            "is_active": department_data.is_active,
            "is_predefined": False,
            "created_at": datetime.utcnow(),
            "created_by": current_user.get("email"),
            "updated_at": datetime.utcnow()
        }
        
        result = await db.departments.insert_one(department_doc)
        department_id = str(result.inserted_id)
        
        logger.info(f"✅ Custom department created: {department_data.name} by {current_user.get('email')}")
        
        return {
            "success": True,
            "message": f"Department '{department_data.name}' created successfully",
            "department": {
                "id": department_id,
                "name": department_data.name,
                "display_name": department_doc["display_name"],
                "description": department_data.description,
                "is_predefined": False,
                "is_active": True
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating department: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create department: {str(e)}"
        )

@router.put("/users/{user_id}/departments", response_model=Dict[str, Any])
async def update_user_departments(
    user_id: str,
    departments_data: Dict[str, Union[str, List[str]]],
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Admin only
):
    """
    Update user departments (Admin only)
    Supports both single department (for admin) and multiple departments (for users)
    """
    try:
        from ..models.user import DepartmentHelper
        
        db = get_database()
        
        # Validate user exists
        target_user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        new_departments = departments_data.get("departments")
        if new_departments is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Departments field is required"
            )
        
        # Convert to list for validation
        if isinstance(new_departments, str):
            dept_list = [new_departments]
        else:
            dept_list = new_departments
        
        # Validate all departments exist
        invalid_departments = []
        for dept in dept_list:
            if not await DepartmentHelper.is_department_valid(dept):
                invalid_departments.append(dept)
        
        if invalid_departments:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid departments: {invalid_departments}. Use GET /departments to see available departments."
            )
        
        # 🔥 Normalize departments based on user role
        user_role = target_user.get("role", "user")
        normalized_departments = DepartmentHelper.normalize_departments(
            new_departments, 
            user_role
        )
        
        # Update user
        update_result = await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "departments": normalized_departments,
                    "updated_at": datetime.utcnow(),
                    "departments_updated_by": current_user.get("email")
                }
            }
        )
        
        if update_result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No changes made to user departments"
            )
        
        logger.info(f"Admin {current_user.get('email')} updated departments for user {target_user.get('email')}: {normalized_departments}")
        
        return {
            "success": True,
            "message": f"Departments updated for user {target_user.get('email')}",
            "user": {
                "id": user_id,
                "email": target_user.get("email"),
                "name": f"{target_user.get('first_name', '')} {target_user.get('last_name', '')}".strip(),
                "role": user_role,
                "old_departments": target_user.get("departments", []),
                "new_departments": normalized_departments
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user departments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user departments: {str(e)}"
        )

@router.get("/departments/{department_name}/users", response_model=Dict[str, Any])
async def get_department_users(
    department_name: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Admin only
):
    """
    Get all users in a specific department (Admin only)
    """
    try:
        from ..models.user import DepartmentHelper
        
        db = get_database()
        
        # Validate department exists
        if not await DepartmentHelper.is_department_valid(department_name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Department '{department_name}' not found"
            )
        
        # Get users in this department
        users_cursor = db.users.find(
            {
                "$or": [
                    {"departments": department_name},  # String format (admin)
                    {"departments": {"$in": [department_name]}}  # Array format (users)
                ],
                "is_active": True
            },
            {
                "hashed_password": 0  # Exclude password
            }
        )
        
        users = await users_cursor.to_list(None)
        
        # Process users for response
        department_users = []
        for user in users:
            departments = user.get("departments", [])
            department_users.append({
                "id": str(user["_id"]),
                "email": user["email"],
                "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                "role": user.get("role", "user"),
                "departments": departments,
                "assigned_leads_count": user.get("total_assigned_leads", 0),
                "created_at": user.get("created_at"),
                "last_login": user.get("last_login")
            })
        
        return {
            "success": True,
            "department": department_name,
            "users": department_users,
            "total_users": len(department_users)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting department users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get department users"
        )

@router.delete("/departments/{department_id}", response_model=Dict[str, Any])
async def deactivate_department(
    department_id: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Admin only
):
    """
    Deactivate a custom department (Admin only)
    Note: Cannot delete predefined departments, only custom ones
    """
    try:
        db = get_database()
        
        # Find the department
        department = await db.departments.find_one({"_id": ObjectId(department_id)})
        if not department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found"
            )
        
        if department.get("is_predefined", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate predefined departments"
            )
        
        # Check if any users are using this department
        user_count = await db.users.count_documents({
            "$or": [
                {"departments": department["name"]},
                {"departments": {"$in": [department["name"]]}}
            ],
            "is_active": True
        })
        
        if user_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot deactivate department '{department['name']}'. {user_count} users are currently assigned to this department. Please reassign users first."
            )
        
        # Deactivate department
        await db.departments.update_one(
            {"_id": ObjectId(department_id)},
            {
                "$set": {
                    "is_active": False,
                    "deactivated_at": datetime.utcnow(),
                    "deactivated_by": current_user.get("email")
                }
            }
        )
        
        logger.info(f"Admin {current_user.get('email')} deactivated department: {department['name']}")
        
        return {
            "success": True,
            "message": f"Department '{department['name']}' deactivated successfully",
            "department_id": department_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating department: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate department"
        )

# 🔥 NEW: Import the models at the top of auth.py
