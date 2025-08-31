# app/models/password_reset.py
# Password Reset Models for LeadG CRM
# Handles both user self-service and admin-initiated password resets

from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

# ============================================================================
# ENUMS FOR PASSWORD RESET
# ============================================================================

class ResetTokenType(str, Enum):
    """Types of password reset tokens"""
    USER_INITIATED = "user_initiated"      # User forgot password
    ADMIN_INITIATED = "admin_initiated"    # Admin reset user password

class ResetTokenStatus(str, Enum):
    """Password reset token status"""
    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"
    REVOKED = "revoked"

class ResetMethod(str, Enum):
    """Password reset methods"""
    EMAIL_LINK = "email_link"             # Email with reset link
    ADMIN_TEMPORARY = "admin_temporary"   # Admin sets temporary password

# ============================================================================
# REQUEST MODELS
# ============================================================================

class ForgotPasswordRequest(BaseModel):
    """User forgot password request"""
    email: EmailStr = Field(..., description="Registered email address")
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@company.com"
            }
        }

class ResetPasswordRequest(BaseModel):
    """Reset password using token"""
    token: str = Field(..., min_length=1, description="Password reset token")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")
    confirm_password: str = Field(..., min_length=8, max_length=128, description="Confirm new password")
    
    @validator('confirm_password')
    def passwords_match(cls, v, values, **kwargs):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v
    
    @validator('new_password')
    def validate_password_strength(cls, v):
        """Basic password strength validation"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        
        # Check for at least one number and one letter
        has_letter = any(c.isalpha() for c in v)
        has_number = any(c.isdigit() for c in v)
        
        if not (has_letter and has_number):
            raise ValueError('Password must contain at least one letter and one number')
        
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                "new_password": "NewSecure123",
                "confirm_password": "NewSecure123"
            }
        }

class AdminResetPasswordRequest(BaseModel):
    """Admin-initiated password reset"""
    user_email: EmailStr = Field(..., description="Email of user whose password to reset")
    reset_method: ResetMethod = Field(default=ResetMethod.EMAIL_LINK, description="Reset method")
    temporary_password: Optional[str] = Field(None, min_length=8, description="Temporary password (for admin method)")
    force_change_on_login: bool = Field(default=True, description="Force user to change password on next login")
    notification_message: Optional[str] = Field(None, max_length=500, description="Optional message for user")
    
    @validator('temporary_password')
    def validate_temp_password(cls, v, values):
        """Validate temporary password if admin method is used"""
        if values.get('reset_method') == ResetMethod.ADMIN_TEMPORARY and not v:
            raise ValueError('Temporary password is required for admin temporary reset method')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_email": "user@company.com",
                "reset_method": "email_link",
                "force_change_on_login": True,
                "notification_message": "Your password has been reset by admin. Please check your email."
            }
        }

# ============================================================================
# RESPONSE MODELS
# ============================================================================

class ForgotPasswordResponse(BaseModel):
    """Forgot password response"""
    success: bool
    message: str
    email_sent: bool = Field(default=False, description="Whether email was sent")
    token_expires_in: Optional[int] = Field(None, description="Token expiration time in minutes")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "If your email is registered, you will receive a password reset link shortly.",
                "email_sent": True,
                "token_expires_in": 30
            }
        }

class ResetPasswordResponse(BaseModel):
    """Reset password response"""
    success: bool
    message: str
    user_email: Optional[str] = Field(None, description="Email of user whose password was reset")
    requires_login: bool = Field(default=True, description="Whether user needs to login again")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Password reset successfully. Please login with your new password.",
                "user_email": "user@company.com",
                "requires_login": True
            }
        }

class AdminResetPasswordResponse(BaseModel):
    """Admin password reset response"""
    success: bool
    message: str
    user_email: str
    reset_method: ResetMethod
    email_sent: bool = Field(default=False, description="Whether notification email was sent")
    temporary_password: Optional[str] = Field(None, description="Temporary password (if applicable)")
    force_change_on_login: bool
    reset_by: str = Field(..., description="Admin who initiated the reset")
    reset_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "User password reset successfully",
                "user_email": "user@company.com",
                "reset_method": "email_link",
                "email_sent": True,
                "force_change_on_login": True,
                "reset_by": "admin@company.com",
                "reset_at": "2024-01-15T10:30:00Z"
            }
        }

class ValidateResetTokenResponse(BaseModel):
    """Validate reset token response"""
    valid: bool
    token_type: Optional[ResetTokenType] = None
    user_email: Optional[str] = None
    expires_at: Optional[datetime] = None
    expires_in_minutes: Optional[int] = None
    message: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "valid": True,
                "token_type": "user_initiated",
                "user_email": "user@company.com",
                "expires_at": "2024-01-15T11:00:00Z",
                "expires_in_minutes": 25,
                "message": "Token is valid"
            }
        }

# ============================================================================
# DATABASE MODELS (For MongoDB storage)
# ============================================================================

class PasswordResetToken(BaseModel):
    """Password reset token database model"""
    token: str = Field(..., description="Hashed reset token")
    user_id: str = Field(..., description="User ObjectId as string")
    user_email: str = Field(..., description="User email for quick lookup")
    token_type: ResetTokenType = Field(..., description="Type of reset token")
    status: ResetTokenStatus = Field(default=ResetTokenStatus.ACTIVE)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(..., description="Token expiration time")
    created_by: Optional[str] = Field(None, description="Admin email if admin-initiated")
    used_at: Optional[datetime] = Field(None, description="When token was used")
    ip_address: Optional[str] = Field(None, description="IP address of requester")
    user_agent: Optional[str] = Field(None, description="User agent of requester")
    
    # Admin reset specific fields
    reset_method: Optional[ResetMethod] = Field(None)
    force_change_on_login: bool = Field(default=False)
    notification_message: Optional[str] = Field(None)
    
    class Config:
        json_schema_extra = {
            "example": {
                "token": "hashed_token_here",
                "user_id": "507f1f77bcf86cd799439011",
                "user_email": "user@company.com",
                "token_type": "user_initiated",
                "status": "active",
                "created_at": "2024-01-15T10:00:00Z",
                "expires_at": "2024-01-15T11:00:00Z",
                "ip_address": "192.168.1.1",
                "user_agent": "Mozilla/5.0..."
            }
        }

# ============================================================================
# UTILITY MODELS
# ============================================================================

class PasswordResetStats(BaseModel):
    """Password reset statistics for admin dashboard"""
    total_requests_today: int = Field(default=0)
    total_requests_this_week: int = Field(default=0)
    total_requests_this_month: int = Field(default=0)
    successful_resets_today: int = Field(default=0)
    pending_tokens: int = Field(default=0)
    expired_tokens: int = Field(default=0)
    admin_initiated_resets: int = Field(default=0)
    user_initiated_resets: int = Field(default=0)
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_requests_today": 5,
                "total_requests_this_week": 23,
                "total_requests_this_month": 87,
                "successful_resets_today": 4,
                "pending_tokens": 8,
                "expired_tokens": 15,
                "admin_initiated_resets": 12,
                "user_initiated_resets": 75
            }
        }

class ResetTokenInfo(BaseModel):
    """Token information for admin management"""
    token_id: str
    user_email: str
    user_name: str
    token_type: ResetTokenType
    status: ResetTokenStatus
    created_at: datetime
    expires_at: datetime
    created_by: Optional[str] = None
    ip_address: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "token_id": "507f1f77bcf86cd799439011",
                "user_email": "user@company.com",
                "user_name": "John Doe",
                "token_type": "user_initiated",
                "status": "active",
                "created_at": "2024-01-15T10:00:00Z",
                "expires_at": "2024-01-15T11:00:00Z",
                "ip_address": "192.168.1.1"
            }
        }