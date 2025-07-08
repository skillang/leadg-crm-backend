# app/models/lead.py - Comprehensive Lead Models Based on UI Analysis

from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class LeadStatus(str, Enum):
    """Lead status enumeration"""

    followup = "Followup"
    warm = "Warm"
    prospect = "Prospect"
    junk = "Junk"
    enrolled = "Enrolled"
    yet_to_call = "Yet to call"
    counseled = "Counseled"
    dnp = "DNP"
    invalid = "INVALID"
    call_back = "Call Back"
    busy = "Busy"
    ni = "NI"
    ringing = "Ringing"
    wrong_number = "Wrong Number"
class LeadStage(str, Enum):
    """Lead stage enumeration (from Status & Tags tab)"""
    INITIAL = "initial"
    CONTACTED = "contacted" 
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED = "closed"
    LOST = "lost"

class CourseLevel(str, Enum):
    """Course level enumeration"""
    BACHELORS = "bachelor's_degree"
    MASTERS = "master's_degree"
    PHD = "phd"
    DIPLOMA = "diploma"
    CERTIFICATE = "certificate"

class LeadSource(str, Enum):
    """Lead source enumeration"""
    WEBSITE = "website"
    SOCIAL_MEDIA = "social_media"
    EMAIL_CAMPAIGN = "email_campaign"
    REFERRAL = "referral"
    ADVERTISEMENT = "advertisement"
    COLD_CALL = "cold_call"
    WALK_IN = "walk_in"
    WHATSAPP = "whatsapp"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    REDDIT = "reddit"
    YOUTUBE = "youtube"
    BULK_UPLOAD = "bulk upload"

class LeadPriority(str, Enum):
    """Lead priority enumeration - REMOVED"""
    pass

# Basic Info Section (Tab 1)
class LeadBasicInfo(BaseModel):
    """Basic information section"""
    name: str = Field(..., min_length=1, max_length=100, description="Lead's full name")
    email: EmailStr = Field(..., description="Lead's email address")
    contact_number: str = Field(..., min_length=10, max_length=20, description="Lead's phone number")
    source: LeadSource = Field(default=LeadSource.WEBSITE, description="How the lead was acquired")

# Status & Tags Section (Tab 2) 
class LeadStatusAndTags(BaseModel):
    """Status and tags section"""
    stage: LeadStage = Field(default=LeadStage.INITIAL, description="Current lead stage")
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

# Complete Lead Creation Model
class LeadCreateComprehensive(BaseModel):
    """Comprehensive lead creation model with all sections"""
    
    # Basic Info (Required)
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
                    "source": "website"
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
                    "notes": "These are the custom notes added by the user. Student is very interested and has IELTS score of 7.5. Prefers Canada for studies."
                }
            }
        }

# Lead Update Model (for editing)
class LeadUpdateComprehensive(BaseModel):
    """Comprehensive lead update model"""
    
    # Basic Info
    basic_info: Optional[LeadBasicInfo] = None
    
    # Status & Tags
    status_and_tags: Optional[LeadStatusAndTags] = None
    
    # Assignment (for reassignment)
    assignment: Optional[LeadAssignmentInfo] = None
    
    # Additional Info
    additional_info: Optional[LeadAdditionalInfo] = None

# Lead Response Model (what gets returned)
class LeadResponseComprehensive(BaseModel):
    """Comprehensive lead response model"""
    
    # System fields
    id: str
    lead_id: str  # Auto-generated (e.g., LD-1029)
    status: LeadStatus = LeadStatus.followup
    
    # Basic Info
    name: str
    email: str
    contact_number: str
    source: LeadSource
    
    # Status & Tags
    stage: LeadStage
    lead_score: int
    tags: List[str]
    
    # Assignment Info
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    assignment_method: Optional[str] = None
    
    # Additional Info
    notes: Optional[str] = None  # Just the additional notes field
    
    # System metadata
    created_by: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    last_contacted: Optional[datetime] = None
    assignment_history: Optional[List[Dict[str, Any]]] = None
    
    class Config:
        from_attributes = True

# Duplicate Check Result
class DuplicateCheckResult(BaseModel):
    """Result of duplicate check"""
    is_duplicate: bool
    duplicate_leads: List[Dict[str, Any]] = Field(default_factory=list)
    match_criteria: List[str] = Field(default_factory=list)  # What matched (email, phone, etc.)

# Lead Creation Response
class LeadCreateResponseComprehensive(BaseModel):
    """Comprehensive lead creation response"""
    success: bool
    message: str
    lead: Optional[LeadResponseComprehensive] = None
    duplicate_check: Optional[DuplicateCheckResult] = None
    assignment_info: Optional[Dict[str, Any]] = None  # Round-robin assignment details

# Legacy models for backward compatibility
class LeadCreate(LeadBasicInfo):
    """Legacy lead creation model for backward compatibility"""
    assigned_to: Optional[str] = None
    country_of_interest: Optional[str] = None
    course_level: Optional[CourseLevel] = None
    source: Optional[LeadSource] = LeadSource.WEBSITE
    tags: Optional[List[str]] = Field(default_factory=list)
    notes: Optional[str] = None

class LeadUpdate(BaseModel):
    """Legacy lead update model"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, min_length=10, max_length=20)
    country_of_interest: Optional[str] = Field(None, max_length=200)
    course_level: Optional[CourseLevel] = None
    source: Optional[LeadSource] = None
    status: Optional[LeadStatus] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=1000)

class LeadAssign(BaseModel):
    """Lead assignment/reassignment model"""
    assigned_to: str = Field(..., description="User email to assign the lead to")
    notes: Optional[str] = Field(None, max_length=500, description="Reason for assignment/reassignment")

class LeadResponse(BaseModel):
    """Legacy lead response model"""
    id: str
    lead_id: str
    name: str
    email: str
    phone_number: str
    status: LeadStatus
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    created_by: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime

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