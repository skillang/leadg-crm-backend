# app/models/lead.py - Updated with AGE, EXPERIENCE, and Nationality fields

from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

# Lead Status Enumeration
class LeadStatus(str, Enum):
    """Lead status enumeration"""
    INITIAL = "Initial"
    FOLLOWUP = "Followup"
    WARM = "Warm"
    PROSPECT = "Prospect"
    JUNK = "Junk"
    ENROLLED = "Enrolled"
    YET_TO_CALL = "Yet to call"
    COUNSELED = "Counseled"
    DNP = "DNP"
    INVALID = "INVALID"
    CALL_BACK = "Call Back"
    BUSY = "Busy"
    NI = "NI"
    RINGING = "Ringing"
    WRONG_NUMBER = "Wrong Number"



# Course Level Enumeration
class CourseLevel(str, Enum):
    """Course level enumeration"""
    CERTIFICATE = "certificate"
    DIPLOMA = "diploma"
    UNDERGRADUATE = "undergraduate"
    GRADUATE = "graduate"
    POSTGRADUATE = "postgraduate"
    DOCTORATE = "doctorate"
    PROFESSIONAL = "professional"
    VOCATIONAL = "vocational"

# Lead Source Enumeration
class LeadSource(str, Enum):
    """Lead source enumeration"""
    WEBSITE = "website"
    REFERRAL = "referral"
    SOCIAL_MEDIA = "social media"
    EMAIL_MARKETING = "email marketing"
    COLD_CALLING = "cold calling"
    WALK_IN = "walk in"
    ADVERTISEMENT = "advertisement"
    PARTNERSHIP = "partnership"
    EVENT = "event"
    ORGANIC_SEARCH = "organic search"
    PAID_SEARCH = "paid search"
    LINKEDIN = "linkedin"
    TWITTER = "twitter"
    WHATSAPP = "whatsapp"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    REDDIT = "reddit"
    YOUTUBE = "youtube"
    BULK_UPLOAD = "bulk upload"
    NAUKRI = "naukri"

# 🆕 NEW: Experience Level Enumeration
class ExperienceLevel(str, Enum):
    """Experience level enumeration"""
    FRESHER = "fresher"
    LESS_THAN_1_YEAR = "less_than_1_year"
    ONE_TO_THREE_YEARS = "1_to_3_years"
    THREE_TO_FIVE_YEARS = "3_to_5_years"
    FIVE_TO_TEN_YEARS = "5_to_10_years"
    MORE_THAN_TEN_YEARS = "more_than_10_years"

# Basic Info Section (Tab 1) - UPDATED with new fields
class LeadBasicInfo(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr = Field(...)
    contact_number: str = Field(..., min_length=10, max_length=20)
    source: LeadSource = Field(default=LeadSource.WEBSITE)
    category: str = Field(..., min_length=1, description="Lead category (required)")
    
    # 🆕 NEW: Optional additional fields
    age: Optional[int] = Field(None, ge=16, le=100, description="Age of the lead (16-100)")
    experience: Optional[ExperienceLevel] = Field(None, description="Work experience level")
    nationality: Optional[str] = Field(None, max_length=100, description="Nationality of the lead")
    
    @validator('category')
    def validate_category(cls, v):
        if not v.strip():
            raise ValueError("Category is required")
        return v.strip()
    
    @validator('nationality')
    def validate_nationality(cls, v):
        if v:
            return v.strip()
        return v
    
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
                "nationality": "Indian"
            }
        }

# Status & Tags Section (Tab 2) 
class LeadStatusAndTags(BaseModel):
    """Status and tags section"""
    stage: str = Field(default="Initial", description="Current lead stage")
    lead_score: int = Field(default=0, ge=0, le=100, description="Lead score (0-100)")
    tags: List[str] = Field(default_factory=list, description="Lead tags (e.g., IELTS Ready, Engineering)")
    
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
    
    # Basic Info (Required) - Now includes AGE, EXPERIENCE, Nationality
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
                    "nationality": "Indian"
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
                    "notes": "Student is very interested and has IELTS score of 7.5. Prefers Canada for studies."
                }
            }
        }

# Lead Response Model - UPDATED
class LeadResponseComprehensive(BaseModel):
    """Comprehensive lead response model"""
    # System Info
    id: str
    lead_id: str
    status: LeadStatus
    created_by: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    last_contacted: Optional[datetime] = None
    
    # Basic Info - UPDATED with new fields
    name: str
    email: str
    contact_number: str
    source: LeadSource
    category: str
    age: Optional[int] = None  # 🆕 NEW
    experience: Optional[ExperienceLevel] = None  # 🆕 NEW
    nationality: Optional[str] = None  # 🆕 NEW
    
    # Status & Tags
    stage: str  # ✅ FIXED - was LeadStage
    lead_score: int
    priority: str = "medium"
    tags: List[str] = Field(default_factory=list)
    
    # Assignment
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    assignment_method: Optional[str] = None
    assignment_history: Optional[List[Dict[str, Any]]] = None
    
    # Additional Info
    notes: Optional[str] = None
    
    # Legacy fields for backward compatibility
    phone_number: Optional[str] = None
    country_of_interest: Optional[str] = None
    course_level: Optional[CourseLevel] = None

# Legacy models for backward compatibility - UPDATED
class LeadCreate(LeadBasicInfo):
    """Legacy lead creation model for backward compatibility"""
    assigned_to: Optional[str] = None
    country_of_interest: Optional[str] = None
    course_level: Optional[CourseLevel] = None
    source: Optional[LeadSource] = LeadSource.WEBSITE
    tags: Optional[List[str]] = Field(default_factory=list)
    notes: Optional[str] = None
    # 🆕 NEW: Include the new fields in legacy model too
    age: Optional[int] = Field(None, ge=16, le=100)
    experience: Optional[ExperienceLevel] = None
    nationality: Optional[str] = Field(None, max_length=100)

class LeadUpdate(BaseModel):
    """Legacy lead update model - UPDATED"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, min_length=10, max_length=20)
    contact_number: Optional[str] = Field(None, min_length=10, max_length=20)
    country_of_interest: Optional[str] = Field(None, max_length=200)
    course_level: Optional[CourseLevel] = None
    source: Optional[LeadSource] = None
    status: Optional[LeadStatus] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=1000)
    category: Optional[str] = Field(None, min_length=1)
    # 🆕 NEW: Add new fields to update model
    age: Optional[int] = Field(None, ge=16, le=100)
    experience: Optional[ExperienceLevel] = None
    nationality: Optional[str] = Field(None, max_length=100)

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
    status: LeadStatus
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    created_by: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    source: LeadSource
    category: str
    # 🆕 NEW: Add new fields to response
    age: Optional[int] = None
    experience: Optional[ExperienceLevel] = None
    nationality: Optional[str] = None

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
    status: LeadStatus
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