# app/models/lead.py - Updated with dynamic stages, statuses, course levels, sources, and new assignment features

from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

# ============================================================================
# DYNAMIC VALIDATION HELPERS (For stages, statuses, course levels, and sources)
# ============================================================================

async def validate_stage_exists(stage_name: str) -> bool:
    """Validate that a stage exists and is active"""
    try:
        from ..config.database import get_database
        
        db = get_database()
        stage = await db.lead_stages.find_one({
            "name": stage_name,
            "is_active": True
        })
        return stage is not None
    except:
        return True  # Fallback - if validation fails, allow the stage

async def validate_status_exists(status_name: str) -> bool:
    """Validate that a status exists and is active"""
    try:
        from ..config.database import get_database
        
        db = get_database()
        status = await db.lead_statuses.find_one({
            "name": status_name,
            "is_active": True
        })
        return status is not None
    except:
        return True  # Fallback - if validation fails, allow the status

async def get_default_stage() -> str:
    """Get the default stage for new leads"""
    try:
        from ..config.database import get_database
        
        db = get_database()
        default_stage = await db.lead_stages.find_one({
            "is_default": True,
            "is_active": True
        })
        
        if default_stage:
            return default_stage["name"]
        
        # Fallback to first active stage
        first_stage = await db.lead_stages.find_one(
            {"is_active": True},
            sort=[("sort_order", 1)]
        )
        
        return first_stage["name"] if first_stage else "Pending"
    except:
        return "Pending"

async def get_default_status() -> str:
    """Get the default status for new leads"""
    try:
        from ..config.database import get_database
        
        db = get_database()
        default_status = await db.lead_statuses.find_one({
            "is_default": True,
            "is_active": True
        })
        
        if default_status:
            return default_status["name"]
        
        # Fallback to first active status
        first_status = await db.lead_statuses.find_one(
            {"is_active": True},
            sort=[("sort_order", 1)]
        )
        
        return first_status["name"] if first_status else "New"
    except:
        return "New"

# 🆕 NEW: Dynamic Course Level Functions
async def get_default_course_level() -> str:
    """Get the default course level for new leads"""
    try:
        from ..config.database import get_database
        
        db = get_database()
        default_course_level = await db.course_levels.find_one({
            "is_default": True,
            "is_active": True
        })
        
        if default_course_level:
            return default_course_level["name"]
        
        # Fallback to first active course level
        first_course_level = await db.course_levels.find_one(
            {"is_active": True},
            sort=[("sort_order", 1)]
        )
        
        return first_course_level["name"] if first_course_level else "undergraduate"
    except:
        return "undergraduate"

async def validate_course_level_exists(course_level: str) -> bool:
    """Validate if course level exists and is active"""
    try:
        from ..config.database import get_database
        
        db = get_database()
        course_level_doc = await db.course_levels.find_one({
            "name": course_level,
            "is_active": True
        })
        
        return course_level_doc is not None
    except:
        return True  # Fallback - if validation fails, allow the course level

# 🆕 NEW: Dynamic Source Functions
async def get_default_source() -> str:
    """Get the default source for new leads"""
    try:
        from ..config.database import get_database
        
        db = get_database()
        default_source = await db.sources.find_one({
            "is_default": True,
            "is_active": True
        })
        
        if default_source:
            return default_source["name"]
        
        # Fallback to first active source
        first_source = await db.sources.find_one(
            {"is_active": True},
            sort=[("sort_order", 1)]
        )
        
        return first_source["name"] if first_source else "website"
    except:
        return "website"

async def validate_source_exists(source: str) -> bool:
    """Validate if source exists and is active"""
    try:
        from ..config.database import get_database
        
        db = get_database()
        source_doc = await db.sources.find_one({
            "name": source,
            "is_active": True
        })
        
        return source_doc is not None
    except:
        return True  # Fallback - if validation fails, allow the source

# ============================================================================
# ENUMERATION CLASSES (Only Experience Level remains as enum)
# ============================================================================

# Experience Level Enumeration (Keep as enum - not dynamic)
class ExperienceLevel(str, Enum):
    """Experience level enumeration"""
    FRESHER = "fresher"
    LESS_THAN_1_YEAR = "less_than_1_year"
    ONE_TO_THREE_YEARS = "1_to_3_years"
    THREE_TO_FIVE_YEARS = "3_to_5_years"
    FIVE_TO_TEN_YEARS = "5_to_10_years"
    MORE_THAN_TEN_YEARS = "more_than_10_years"

# ============================================================================
# BASIC LEAD MODELS (UPDATED FOR DYNAMIC FIELDS)
# ============================================================================

# Basic Info Section (Tab 1) - UPDATED with dynamic fields
class LeadBasicInfo(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr = Field(...)
    contact_number: str = Field(..., min_length=10, max_length=20)
    source: str = Field(default="website", description="Lead source (dynamic)")  # 🔄 CHANGED: str instead of enum
    category: str = Field(..., min_length=1, description="Lead category (required)")
    
    # Optional additional fields
    age: Optional[int] = Field(None, ge=16, le=100, description="Age of the lead (16-100)")
    experience: Optional[ExperienceLevel] = Field(None, description="Work experience level")
    nationality: Optional[str] = Field(None, max_length=100, description="Nationality of the lead")
    current_location: Optional[str] = Field(None, max_length=150, description="Current location of the lead")
    
    # 🆕 NEW: Dynamic course level field
    course_level: Optional[str] = Field(None, description="Course level (dynamic)")  # 🔄 CHANGED: str instead of enum
    
    @validator('category')
    def validate_category(cls, v):
        if not v.strip():
            raise ValueError("Category is required")
        return v.strip()
    
    @validator('nationality')
    def validate_nationality(cls, v):
        if v and not v.strip():
            return None
        return v.strip() if v else None
    
    @validator('current_location')
    def validate_current_location(cls, v):
        """Validate current_location field - auto-default to 'Not mentioned' if not provided"""
        if v and v.strip():
            return v.strip()
        return "Not mentioned"  # Auto-default value
    
    @validator('source')
    def validate_source_string(cls, v):
        """Basic source validation - detailed validation at service level"""
        if not v or not v.strip():
            return "website"  # Default fallback
        return v.strip().lower().replace(' ', '_')
    
    @validator('course_level')
    def validate_course_level_string(cls, v):
        """Basic course level validation - detailed validation at service level"""
        if not v or not v.strip():
            return None  # Optional field
        return v.strip().lower().replace(' ', '_')
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Dani Sharma",
                "email": "dani.sharma@example.com",
                "contact_number": "+91-9876543210",
                "source": "website",
                "category": "Study Abroad",
                "age": 24,
                "experience": "1_to_3_years",
                "nationality": "Indian",
                "current_location": "Mumbai, India",
                "course_level": "undergraduate"
            }
        }

# Status & Tags Section (Tab 2) 
class LeadStatusAndTags(BaseModel):
    """Status and tags section with dynamic stage and status"""
    stage: str = Field(default="Pending", description="Current lead stage (dynamic)")
    status: str = Field(default="New", description="Current lead status (dynamic)")
    lead_score: int = Field(default=0, ge=0, le=100, description="Lead score (0-100)")
    tags: List[str] = Field(default_factory=list, description="Lead tags (e.g., IELTS Ready, Engineering)")
    
    @validator('stage')
    def validate_stage(cls, v):
        """Basic stage validation - more validation done at service level"""
        if not v or not v.strip():
            return "Pending"  # Default fallback
        return v.strip()
    
    @validator('status')
    def validate_status(cls, v):
        """Basic status validation - more validation done at service level"""
        if not v or not v.strip():
            return "New"  # Default fallback
        return v.strip()
    
    @validator('tags')
    def validate_tags(cls, v):
        """Ensure tags are properly formatted"""
        if v:
            # Remove empty tags and strip whitespace
            return [tag.strip() for tag in v if tag.strip()]
        return []

# Assignment Section (Tab 3)
class LeadAssignmentInfo(BaseModel):
    """Assignment information section - always auto-assign via round-robin"""
    assigned_to: Optional[str] = Field(None, description="Leave None for automatic round-robin assignment")

    class Config:
        json_schema_extra = {
            "example": {
                "assigned_to": None  # Always use None for auto-assignment
            }
        }

# Additional Info Section (Tab 4)
class LeadAdditionalInfo(BaseModel):
    """Additional information section - just custom notes"""
    notes: Optional[str] = Field(None, max_length=2000, description="Custom notes added by the admin/user")

# Complete Lead Creation Model - UPDATED
class LeadCreateComprehensive(BaseModel):
    """Comprehensive lead creation model with all sections"""
    
    # Basic Info (Required) - Now includes dynamic course level and source
    basic_info: LeadBasicInfo
    
    # Status & Tags (Optional with defaults)
    status_and_tags: Optional[LeadStatusAndTags] = Field(default_factory=LeadStatusAndTags)
    
    # Assignment (Optional - will auto-assign if not provided)
    assignment: Optional[LeadAssignmentInfo] = Field(default_factory=LeadAssignmentInfo)
    
    # Additional Info (Optional)
    additional_info: Optional[LeadAdditionalInfo] = Field(default_factory=LeadAdditionalInfo)
    
    class Config:
        json_schema_extra = {
            "example": {
                "basic_info": {
                    "name": "Dani Sharma",
                    "email": "dani.sharma@example.com",
                    "contact_number": "+91-9876543210",
                    "source": "website",
                    "category": "Study Abroad",
                    "age": 24,
                    "experience": "1_to_3_years",
                    "nationality": "Indian",
                    "current_location": "Mumbai, India",
                    "course_level": "undergraduate"
                },
                "status_and_tags": {
                    "stage": "contacted",
                    "lead_score": 45,
                    "tags": ["IELTS Ready", "Engineering", "MBA"]
                },
                "assignment": {
                    "assigned_to": None  # Always None for auto round-robin assignment
                },
                "additional_info": {
                    "notes": "Student is very interested and has IELTS score of 7.5. Currently based in Mumbai."
                }
            }
        }

# ============================================================================
# 🆕 NEW: SELECTIVE ROUND ROBIN & MULTI-ASSIGNMENT MODELS
# ============================================================================

class SelectiveRoundRobinRequest(BaseModel):
    """Request model for selective round robin assignment"""
    selected_user_emails: List[str] = Field(..., description="List of user emails to include in round robin")
    
    @validator('selected_user_emails')
    def validate_selected_users(cls, v):
        if not v:
            raise ValueError("At least one user must be selected for round robin")
        
        # Remove duplicates and empty emails
        unique_emails = list(set([email.strip().lower() for email in v if email.strip()]))
        
        if not unique_emails:
            raise ValueError("No valid email addresses provided")
        
        return unique_emails
    
    class Config:
        json_schema_extra = {
            "example": {
                "selected_user_emails": [
                    "john.doe@leadg.com",
                    "jane.smith@leadg.com",
                    "mike.johnson@leadg.com"
                ]
            }
        }

class MultiUserAssignmentRequest(BaseModel):
    """Request model for assigning lead to multiple users"""
    user_emails: List[str] = Field(..., description="List of user emails to assign the lead to")
    reason: Optional[str] = Field("Multi-user assignment", description="Reason for assignment")
    
    @validator('user_emails')
    def validate_user_emails(cls, v):
        if not v:
            raise ValueError("At least one user must be provided for assignment")
        
        # Remove duplicates and empty emails
        unique_emails = list(set([email.strip().lower() for email in v if email.strip()]))
        
        if not unique_emails:
            raise ValueError("No valid email addresses provided")
        
        if len(unique_emails) > 10:  # Reasonable limit
            raise ValueError("Cannot assign to more than 10 users at once")
        
        return unique_emails
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_emails": [
                    "john.doe@leadg.com",
                    "jane.smith@leadg.com"
                ],
                "reason": "Team collaboration required"
            }
        }

class RemoveFromAssignmentRequest(BaseModel):
    """Request model for removing user from multi-assignment"""
    user_email: str = Field(..., description="Email of user to remove from assignment")
    reason: Optional[str] = Field("Removed from assignment", description="Reason for removal")
    
    @validator('user_email')
    def validate_user_email(cls, v):
        if not v or not v.strip():
            raise ValueError("User email is required")
        return v.strip().lower()
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_email": "john.doe@leadg.com",
                "reason": "User no longer available"
            }
        }

class BulkAssignmentRequest(BaseModel):
    """Request model for bulk lead assignment with selective round robin"""
    lead_ids: List[str] = Field(..., description="List of lead IDs to assign")
    assignment_method: str = Field(..., description="Assignment method: 'all_users' or 'selected_users'")
    selected_user_emails: Optional[List[str]] = Field(None, description="Required if assignment_method is 'selected_users'")
    
    @validator('assignment_method')
    def validate_assignment_method(cls, v):
        if v not in ['all_users', 'selected_users']:
            raise ValueError("Assignment method must be 'all_users' or 'selected_users'")
        return v
    
    @validator('selected_user_emails')
    def validate_selected_users_conditional(cls, v, values):
        assignment_method = values.get('assignment_method')
        
        if assignment_method == 'selected_users':
            if not v:
                raise ValueError("selected_user_emails is required when assignment_method is 'selected_users'")
            
            # Remove duplicates and empty emails
            unique_emails = list(set([email.strip().lower() for email in v if email.strip()]))
            
            if not unique_emails:
                raise ValueError("No valid email addresses provided")
            
            return unique_emails
        
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "lead_ids": ["LD-1001", "LD-1002", "LD-1003"],
                "assignment_method": "selected_users",
                "selected_user_emails": [
                    "john.doe@leadg.com",
                    "jane.smith@leadg.com"
                ]
            }
        }

# ============================================================================
# 🆕 NEW: RESPONSE MODELS
# ============================================================================

class MultiUserAssignmentResponse(BaseModel):
    """Response model for multi-user assignment"""
    success: bool
    message: str
    assigned_users: List[str]
    invalid_users: List[str]
    primary_assignee: Optional[str]
    co_assignees: List[str]
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Lead assigned to 2 users successfully",
                "assigned_users": ["john.doe@leadg.com", "jane.smith@leadg.com"],
                "invalid_users": [],
                "primary_assignee": "john.doe@leadg.com",
                "co_assignees": ["jane.smith@leadg.com"]
            }
        }

class BulkAssignmentResponse(BaseModel):
    """Response model for bulk assignment with selective round robin"""
    success: bool
    message: str
    total_leads: int
    successfully_assigned: int
    failed_assignments: List[Dict[str, str]]
    assignment_method: str
    selected_users: Optional[List[str]]
    assignment_summary: List[Dict[str, Any]]
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Bulk assignment completed",
                "total_leads": 3,
                "successfully_assigned": 3,
                "failed_assignments": [],
                "assignment_method": "selected_users",
                "selected_users": ["john.doe@leadg.com", "jane.smith@leadg.com"],
                "assignment_summary": [
                    {"lead_id": "LD-1001", "assigned_to": "john.doe@leadg.com", "status": "success"},
                    {"lead_id": "LD-1002", "assigned_to": "jane.smith@leadg.com", "status": "success"},
                    {"lead_id": "LD-1003", "assigned_to": "john.doe@leadg.com", "status": "success"}
                ]
            }
        }

class SelectiveRoundRobinResponse(BaseModel):
    """Response model for selective round robin assignment"""
    success: bool
    message: str
    selected_user: Optional[str]
    available_users: List[str]
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "User selected for assignment",
                "selected_user": "john.doe@leadg.com",
                "available_users": ["john.doe@leadg.com", "jane.smith@leadg.com"]
            }
        }

# ============================================================================
# 🆕 NEW: EXTENDED LEAD RESPONSE WITH MULTI-ASSIGNMENT INFO
# ============================================================================

class LeadResponseExtended(BaseModel):
    """Extended lead response with multi-assignment information"""
    lead_id: str
    status: str
    name: str
    email: str
    contact_number: Optional[str]
    source: Optional[str]  # 🔄 CHANGED: str instead of enum
    category: Optional[str]
    
    # Single assignment fields (backward compatibility)
    assigned_to: Optional[str]
    assigned_to_name: Optional[str]
    
    # Multi-assignment fields
    co_assignees: List[str] = Field(default_factory=list, description="Additional users assigned to this lead")
    co_assignees_names: List[str] = Field(default_factory=list, description="Names of co-assignees")
    is_multi_assigned: bool = Field(default=False, description="Whether lead is assigned to multiple users")
    
    # Assignment metadata
    assignment_method: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    
    # All assignees (computed field)
    all_assignees: List[str] = Field(default_factory=list, description="All users assigned to this lead")
    all_assignees_names: List[str] = Field(default_factory=list, description="Names of all assignees")
    
    def __init__(self, **data):
        super().__init__(**data)
        
        # Compute all_assignees and all_assignees_names
        all_assignees = []
        all_assignees_names = []
        
        if self.assigned_to:
            all_assignees.append(self.assigned_to)
            all_assignees_names.append(self.assigned_to_name or self.assigned_to)
        
        if self.co_assignees:
            all_assignees.extend(self.co_assignees)
            all_assignees_names.extend(self.co_assignees_names or self.co_assignees)
        
        self.all_assignees = all_assignees
        self.all_assignees_names = all_assignees_names
    
    class Config:
        json_schema_extra = {
            "example": {
                "lead_id": "LD-1001",
                "status": "New",
                "name": "John Smith",
                "email": "john.smith@example.com",
                "contact_number": "+1-555-0123",
                "source": "website",
                "category": "Technology",
                "assigned_to": "john.doe@leadg.com",
                "assigned_to_name": "John Doe",
                "co_assignees": ["jane.smith@leadg.com"],
                "co_assignees_names": ["Jane Smith"],
                "is_multi_assigned": True,
                "assignment_method": "multi_user_manual",
                "all_assignees": ["john.doe@leadg.com", "jane.smith@leadg.com"],
                "all_assignees_names": ["John Doe", "Jane Smith"]
            }
        }

# ============================================================================
# 🆕 NEW: USER SELECTION MODELS
# ============================================================================

class UserSelectionOption(BaseModel):
    """Model for user selection in assignment interfaces"""
    email: str
    name: str
    current_lead_count: int
    is_active: bool
    departments: List[str] = Field(default_factory=list)
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "john.doe@leadg.com",
                "name": "John Doe",
                "current_lead_count": 15,
                "is_active": True,
                "departments": ["sales"]
            }
        }

class UserSelectionResponse(BaseModel):
    """Response model for getting assignable users"""
    total_users: int
    users: List[UserSelectionOption]
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_users": 3,
                "users": [
                    {
                        "email": "john.doe@leadg.com",
                        "name": "John Doe",
                        "current_lead_count": 15,
                        "is_active": True,
                        "departments": ["sales"]
                    },
                    {
                        "email": "jane.smith@leadg.com",
                        "name": "Jane Smith",
                        "current_lead_count": 12,
                        "is_active": True,
                        "departments": ["sales"]
                    }
                ]
            }
        }

# ============================================================================
# LEGACY MODELS FOR BACKWARD COMPATIBILITY (UPDATED FOR DYNAMIC FIELDS)
# ============================================================================

# Lead Response Model - UPDATED
class LeadResponseComprehensive(BaseModel):
    """Comprehensive lead response model"""
    # System Info
    id: str
    lead_id: str
    status: str  # Uses dynamic status instead of enum
    created_by: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    last_contacted: Optional[datetime] = None
    
    # Basic Info - UPDATED with dynamic fields including current_location
    name: str
    email: str
    contact_number: str
    source: str  # 🔄 CHANGED: str instead of LeadSource enum
    category: str
    age: Optional[int] = None
    experience: Optional[ExperienceLevel] = None
    nationality: Optional[str] = None
    current_location: Optional[str] = None  # 🆕 NEW: Added current_location field
    
    # Status & Tags
    stage: str
    lead_score: int
    priority: str = "medium"
    tags: List[str] = Field(default_factory=list)
    
    # Assignment (enhanced for multi-assignment)
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    co_assignees: List[str] = Field(default_factory=list)
    co_assignees_names: List[str] = Field(default_factory=list)
    is_multi_assigned: bool = Field(default=False)
    assignment_method: Optional[str] = None
    assignment_history: Optional[List[Dict[str, Any]]] = None
    
    # Additional Info
    notes: Optional[str] = None
    
    # Legacy fields for backward compatibility
    phone_number: Optional[str] = None
    country_of_interest: Optional[str] = None
    course_level: Optional[str] = None  # 🔄 CHANGED: str instead of CourseLevel enum

# Legacy models for backward compatibility - UPDATED
class LeadCreate(LeadBasicInfo):
    """Legacy lead creation model for backward compatibility"""
    assigned_to: Optional[str] = None
    country_of_interest: Optional[str] = None
    course_level: Optional[str] = None  # 🔄 CHANGED: str instead of enum
    source: Optional[str] = "website"   # 🔄 CHANGED: str instead of enum
    tags: Optional[List[str]] = Field(default_factory=list)
    notes: Optional[str] = None
    # Include all new fields in legacy model too
    age: Optional[int] = Field(None, ge=16, le=100)
    experience: Optional[ExperienceLevel] = None
    nationality: Optional[str] = Field(None, max_length=100)
    current_location: Optional[str] = Field(None, max_length=150)  # 🆕 NEW: Added current_location field

class LeadUpdate(BaseModel):
    """Legacy lead update model - UPDATED"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, min_length=10, max_length=20)
    contact_number: Optional[str] = Field(None, min_length=10, max_length=20)
    country_of_interest: Optional[str] = Field(None, max_length=200)
    course_level: Optional[str] = None  # 🔄 CHANGED: str instead of enum
    source: Optional[str] = None        # 🔄 CHANGED: str instead of enum
    status: Optional[str] = None
    stage: Optional[str] = None         # 🆕 NEW: Dynamic stage
    lead_score: Optional[int] = Field(None, ge=0, le=100)
    priority: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=1000)
    category: Optional[str] = Field(None, min_length=1)
    # Add all new fields to update model
    age: Optional[int] = Field(None, ge=16, le=100)
    experience: Optional[ExperienceLevel] = None
    nationality: Optional[str] = Field(None, max_length=100)
    current_location: Optional[str] = Field(None, max_length=150)  # 🆕 NEW: Added current_location field

class LeadAssign(BaseModel):
    """Lead assignment/reassignment model"""
    assigned_to: str = Field(..., description="User email to assign the lead to")
    notes: Optional[str] = Field(None, max_length=500, description="Reason for assignment/reassignment")

class LeadResponse(BaseModel):
    """Legacy lead response model - UPDATED"""
    id: str
    lead_id: str
    name: str
    email: str
    phone_number: str
    contact_number: str
    status: str
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    created_by: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    source: str  # 🔄 CHANGED: str instead of LeadSource enum
    category: str
    # Add all new fields to response
    age: Optional[int] = None
    experience: Optional[ExperienceLevel] = None
    nationality: Optional[str] = None
    current_location: Optional[str] = None  # 🆕 NEW: Added current_location field
    course_level: Optional[str] = None  # 🔄 CHANGED: str instead of enum

class LeadListResponse(BaseModel):
    """Lead list response model"""
    leads: List[LeadResponseComprehensive]
    total: int
    page: int
    limit: int
    has_next: bool
    has_prev: bool

class LeadStatusUpdate(BaseModel):
    """Lead status update model"""
    status: str
    notes: Optional[str] = Field(None, max_length=500)

class LeadBulkCreate(BaseModel):
    """Bulk lead creation model"""
    leads: List[LeadCreateComprehensive]
    force_create: bool = False

class LeadBulkCreateResponse(BaseModel):
    """Bulk lead creation response"""
    success: bool
    message: str
    summary: Dict[str, Any]
    results: List[Dict[str, Any]]

# Lead Creation Response
class LeadCreateResponseComprehensive(BaseModel):
    """Comprehensive lead creation response"""
    success: bool
    message: str
    lead: Optional[LeadResponseComprehensive] = None
    duplicate_check: Optional[Dict[str, Any]] = None
    assignment_info: Optional[Dict[str, Any]] = None

# Duplicate Check Result
class DuplicateCheckResult(BaseModel):
    """Duplicate check result"""
    is_duplicate: bool
    checked: bool
    existing_lead_id: Optional[str] = None
    duplicate_field: Optional[str] = None
    message: Optional[str] = None