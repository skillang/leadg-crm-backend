# app/models/user.py - Fully Dynamic Department System

from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Union
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    """User roles enumeration"""
    ADMIN = "admin"
    USER = "user"

class CallingStatus(str, Enum):
    """Calling status enumeration for Smartflo integration"""
    PENDING = "pending"
    ACTIVE = "active"
    FAILED = "failed"
    DISABLED = "disabled"
    RETRYING = "retrying"

# 🚀 SIMPLIFIED: Only admin is predefined, everything else is dynamic
class DepartmentType(str, Enum):
    """Only essential predefined department"""
    ADMIN = "admin"  # Only admin is predefined

class UserBase(BaseModel):
    """Base user model with common fields"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    role: UserRole = UserRole.USER
    is_active: bool = True
    phone: Optional[str] = None
    
    # 🔥 DYNAMIC: Multi-department support with database validation
    departments: Union[str, List[str]] = Field(
        default_factory=list,
        description="Single department string for admin, array of departments for users"
    )

    @validator('departments')
    def validate_departments(cls, v, values):
        """Validate departments (admin is always valid, others checked at runtime)"""
        user_role = values.get('role', UserRole.USER)
        
        # Handle both string and list inputs
        if isinstance(v, str):
            departments_list = [v.strip()] if v and v.strip() else []
        elif isinstance(v, list):
            departments_list = [dept.strip() for dept in v if dept and dept.strip()]
        else:
            departments_list = []
        
        # Remove empty strings
        departments_list = [dept for dept in departments_list if dept]
        
        # Role-based validation
        if user_role == UserRole.ADMIN:
            # Admin can have single department
            if len(departments_list) > 1:
                raise ValueError("Admin users can only have one department")
            # Default admin department
            if not departments_list:
                return "admin"
            # Admin can only have "admin" department
            if departments_list[0] != "admin":
                raise ValueError("Admin users can only have 'admin' department")
            return departments_list[0]  # Return string for admin
        else:
            # Regular users must have at least one department, max 5
            if not departments_list:
                raise ValueError("Regular users must have at least one department")
            if len(departments_list) > 5:
                raise ValueError("Users cannot have more than 5 departments")
            
            # Remove duplicates and return list
            return list(set(departments_list))

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
                "departments": ["sales", "marketing"]  # Admin creates these first
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
    
    # 🔥 ENHANCED: Support both formats for backward compatibility
    departments: Union[str, List[str]] = Field(
        description="String for admin users, array for regular users"
    )
    
    # 🔥 NEW: Computed field for easy access
    department_list: List[str] = Field(
        description="Always returns departments as a list for consistency"
    )
    
    created_at: datetime
    last_login: Optional[datetime] = None
    
    # Existing fields
    assigned_leads: List[str] = Field(default_factory=list)
    total_assigned_leads: int = Field(default=0)
    
    # Smartflo integration fields
    extension_number: Optional[str] = Field(None)
    smartflo_agent_id: Optional[str] = Field(None)
    smartflo_user_id: Optional[str] = Field(None)
    calling_status: CallingStatus = Field(CallingStatus.PENDING)

    @validator('department_list', always=True)
    def compute_department_list(cls, v, values):
        """Compute department_list from departments field"""
        departments = values.get('departments', [])
        if isinstance(departments, str):
            return [departments]
        return departments if departments else []

class UserUpdate(BaseModel):
    """User update model"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    departments: Optional[Union[str, List[str]]] = None
    is_active: Optional[bool] = None

    @validator('departments')
    def validate_departments_update(cls, v):
        """Validate departments during update"""
        if v is None:
            return v
            
        # Handle both string and list inputs
        if isinstance(v, str):
            departments_list = [v] if v else []
        elif isinstance(v, list):
            departments_list = v
        else:
            return v
        
        return departments_list if len(departments_list) > 1 else (departments_list[0] if departments_list else None)

# 🚀 NEW: Department Management Models
class DepartmentCreate(BaseModel):
    """Model for creating new departments"""
    name: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = Field(None, max_length=200)
    is_active: bool = True

    @validator('name')
    def validate_name(cls, v):
        """Validate department name"""
        # Convert to lowercase with hyphens
        cleaned = v.strip().lower().replace(' ', '-').replace('_', '-')
        
        # Remove special characters except hyphens
        import re
        cleaned = re.sub(r'[^a-z0-9-]', '', cleaned)
        
        if len(cleaned) < 2:
            raise ValueError('Department name must be at least 2 characters')
        
        if cleaned == "admin":
            raise ValueError('Cannot create department named "admin" - it is reserved')
        
        return cleaned

class DepartmentResponse(BaseModel):
    """Department response model"""
    id: str
    name: str
    display_name: str
    description: Optional[str]
    is_predefined: bool
    is_active: bool
    user_count: int
    created_at: datetime
    created_by: Optional[str] = None

class DepartmentUpdate(BaseModel):
    """Model for updating departments"""
    description: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None

# 🚀 UPDATED: Dynamic Department Helper Functions
class DepartmentHelper:
    """Helper class for department operations"""
    
    @staticmethod
    async def get_all_departments():
        """Get all available departments (only admin is predefined, rest are custom)"""
        from ..config.database import get_database
        
        # Only admin is predefined now
        predefined = [
            {
                "name": "admin",
                "display_name": "Admin",
                "is_predefined": True,
                "is_active": True,
                "description": "System administration and management"
            }
        ]
        
        # Get all custom departments from database
        db = get_database()
        custom_departments = await db.departments.find(
            {"is_active": True}
        ).to_list(None)
        
        custom = [
            {
                "id": str(dept["_id"]),
                "name": dept["name"],
                "display_name": dept.get("display_name", dept["name"].replace('-', ' ').title()),
                "description": dept.get("description"),
                "is_predefined": False,
                "is_active": dept.get("is_active", True),
                "created_at": dept.get("created_at"),
                "created_by": dept.get("created_by")
            }
            for dept in custom_departments
        ]
        
        return predefined + custom
    
    @staticmethod
    async def is_department_valid(department_name: str) -> bool:
        """Check if department name is valid (admin or exists in database)"""
        # Admin is always valid
        if department_name == "admin":
            return True
        
        # Check if custom department exists
        from ..config.database import get_database
        db = get_database()
        custom_dept = await db.departments.find_one({
            "name": department_name,
            "is_active": True
        })
        
        return custom_dept is not None
    
    @staticmethod
    async def get_department_users_count(department_name: str) -> int:
        """Get count of users in a department"""
        from ..config.database import get_database
        db = get_database()
        
        # Count users with this department
        count = await db.users.count_documents({
            "$or": [
                {"departments": department_name},  # String format (admin)
                {"departments": {"$in": [department_name]}}  # Array format (users)
            ],
            "is_active": True
        })
        
        return count
    
    @staticmethod
    def normalize_departments(departments: Union[str, List[str]], role: str) -> Union[str, List[str]]:
        """Normalize departments based on role"""
        if isinstance(departments, str):
            departments_list = [departments]
        else:
            departments_list = departments or []
        
        if role == "admin":
            return "admin"  # Admin always gets "admin"
        else:
            return list(set(departments_list)) if departments_list else []

# 🚀 NEW: Initial Setup Helper
class DepartmentSetupHelper:
    """Helper for setting up initial departments"""
    
    @staticmethod
    async def create_starter_departments():
        """Create a basic set of starter departments for new installations"""
        from ..config.database import get_database
        
        db = get_database()
        
        # Check if any custom departments exist
        existing_count = await db.departments.count_documents({})
        
        if existing_count > 0:
            return  # Already have departments, don't create defaults
        
        # Create basic starter departments
        starter_departments = [
            {
                "name": "sales",
                "display_name": "Sales",
                "description": "Sales and business development",
                "is_active": True,
                "is_predefined": False,
                "created_at": datetime.utcnow(),
                "created_by": "system_setup"
            },
            {
                "name": "support",
                "display_name": "Support", 
                "description": "Customer support and assistance",
                "is_active": True,
                "is_predefined": False,
                "created_at": datetime.utcnow(),
                "created_by": "system_setup"
            },
            {
                "name": "operations",
                "display_name": "Operations",
                "description": "Business operations and processes", 
                "is_active": True,
                "is_predefined": False,
                "created_at": datetime.utcnow(),
                "created_by": "system_setup"
            }
        ]
        
        # Insert starter departments
        await db.departments.insert_many(starter_departments)
        
        return len(starter_departments)