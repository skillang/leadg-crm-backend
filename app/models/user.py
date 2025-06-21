# app/models/user.py - Updated with Assigned Leads Array

from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    """User roles enumeration"""
    ADMIN = "admin"
    USER = "user"

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
    # ✅ NEW: Include assigned leads info in response
    assigned_leads: List[str] = Field(default_factory=list, description="Array of assigned lead IDs")
    total_assigned_leads: int = Field(default=0, description="Quick count of assigned leads")

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
    # ✅ NEW: Assigned leads array for fast lookups
    assigned_leads: List[str] = Field(default_factory=list, description="Array of assigned lead IDs (e.g., ['LD-1000', 'LD-1001'])")
    total_assigned_leads: int = Field(default=0, description="Quick count of assigned leads")

    class Config:
        from_attributes = True