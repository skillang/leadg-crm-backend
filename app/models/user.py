# app/models/user.py - Enhanced with Smartflo Integration

from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    """User roles enumeration"""
    ADMIN = "admin"
    USER = "user"

# 🚀 NEW: Smartflo calling status enumeration
class CallingStatus(str, Enum):
    """Calling status enumeration for Smartflo integration"""
    PENDING = "pending"      # Smartflo setup not attempted yet
    ACTIVE = "active"        # Smartflo agent created successfully, can make calls
    FAILED = "failed"        # Smartflo setup failed, needs retry
    DISABLED = "disabled"    # Calling manually disabled by admin
    RETRYING = "retrying"    # Currently retrying Smartflo setup

class UserBase(BaseModel):
    """Base user model with common fields"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    role: UserRole = UserRole.USER
    is_active: bool = True
    phone: Optional[str] = None
    department: Optional[str] = None

class UserCreate(UserBase):
    """User creation model"""
    password: str = Field(..., min_length=8, max_length=100)

    @validator('password')
    def validate_password(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "email": "john.doe@example.com",
                "username": "johndoe",
                "first_name": "John",
                "last_name": "Doe",
                "password": "SecurePass123",
                "role": "user",
                "phone": "+1-555-123-4567",
                "department": "Sales"
            }
        }

class UserResponse(BaseModel):
    """User response model (without sensitive data)"""
    id: str
    email: str
    username: str
    first_name: str
    last_name: str
    role: UserRole
    is_active: bool
    phone: Optional[str] = None
    department: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None
    
    # ✅ EXISTING: Include assigned leads info in response
    assigned_leads: List[str] = Field(default_factory=list, description="Array of assigned lead IDs")
    total_assigned_leads: int = Field(default=0, description="Quick count of assigned leads")
    
    # 🚀 NEW: Smartflo calling integration fields
    extension_number: Optional[str] = Field(None, description="Smartflo extension number (e.g., '06047530226')")
    smartflo_agent_id: Optional[str] = Field(None, description="Smartflo agent ID")
    smartflo_user_id: Optional[str] = Field(None, description="Smartflo user ID")
    calling_status: CallingStatus = Field(CallingStatus.PENDING, description="Current calling setup status")
    can_make_calls: bool = Field(False, description="Whether user can make calls through Smartflo")
    smartflo_setup_attempts: int = Field(0, description="Number of Smartflo setup attempts")
    smartflo_setup_at: Optional[datetime] = Field(None, description="When Smartflo was successfully set up")
    smartflo_last_error: Optional[str] = Field(None, description="Last Smartflo setup error message")

    class Config:
        from_attributes = True

class UserInDB(UserBase):
    """User model as stored in database"""
    id: str
    hashed_password: str
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    login_count: int = 0
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    
    # ✅ EXISTING: Assigned leads array for fast lookups
    assigned_leads: List[str] = Field(default_factory=list, description="Array of assigned lead IDs (e.g., ['LD-1000', 'LD-1001'])")
    total_assigned_leads: int = Field(default=0, description="Quick count of assigned leads")
    
    # 🚀 NEW: Smartflo calling integration fields in database
    extension_number: Optional[str] = Field(None, description="Smartflo extension number")
    smartflo_agent_id: Optional[str] = Field(None, description="Smartflo agent ID")
    smartflo_user_id: Optional[str] = Field(None, description="Smartflo user ID")
    calling_status: CallingStatus = Field(CallingStatus.PENDING, description="Current calling setup status")
    can_make_calls: bool = Field(False, description="Whether user can make calls")
    smartflo_setup_attempts: int = Field(0, description="Number of setup attempts")
    smartflo_setup_at: Optional[datetime] = Field(None, description="When setup completed")
    smartflo_last_error: Optional[str] = Field(None, description="Last error message")

    class Config:
        from_attributes = True

# 🚀 NEW: Smartflo-specific models
class SmartfloSetupRequest(BaseModel):
    """Request model for Smartflo setup/retry"""
    user_id: str = Field(..., description="User ID to set up calling for")
    force_retry: bool = Field(False, description="Force retry even if max attempts reached")

class SmartfloSetupResponse(BaseModel):
    """Response model for Smartflo setup"""
    success: bool
    message: str
    user_id: str
    extension_number: Optional[str] = None
    calling_status: CallingStatus
    attempts_used: int
    can_retry: bool

class CallingStatusUpdate(BaseModel):
    """Model for updating calling status (admin only)"""
    calling_status: CallingStatus
    notes: Optional[str] = Field(None, description="Admin notes for status change")

class UserCallingInfo(BaseModel):
    """Calling information summary for user"""
    user_id: str
    user_name: str
    email: str
    extension_number: Optional[str]
    calling_status: CallingStatus
    can_make_calls: bool
    setup_attempts: int
    last_error: Optional[str]
    setup_date: Optional[datetime]

class CallingDashboardResponse(BaseModel):
    """Response for calling dashboard (admin view)"""
    total_users: int
    users_with_calling: int
    users_pending_setup: int
    users_failed_setup: int
    users_disabled: int
    recent_setups: List[UserCallingInfo]
    failed_setups: List[UserCallingInfo]