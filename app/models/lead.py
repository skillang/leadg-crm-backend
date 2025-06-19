from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

class LeadStatus(str, Enum):
    """Lead status enumeration"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"

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

class LeadBase(BaseModel):
    """Base lead model with common fields"""
    # Required fields
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone_number: str = Field(..., min_length=10, max_length=20)
    
    # Optional fields
    country_of_interest: Optional[str] = Field(None, max_length=200)
    course_level: Optional[CourseLevel] = None
    source: Optional[LeadSource] = LeadSource.WEBSITE
    tags: Optional[List[str]] = Field(default_factory=list)
    notes: Optional[str] = Field(None, max_length=1000)

class LeadCreate(LeadBase):
    """Lead creation model"""
    assigned_to: Optional[str] = None  # User ID to assign the lead to
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Rahul Sharma",
                "email": "rahul.sharma@example.com",
                "phone_number": "+91-9876543210",
                "country_of_interest": "Canada, USA, UK, Germany",
                "course_level": "master's_degree",
                "source": "website",
                "tags": ["IELTS ready", "Engineering", "MBA"],
                "notes": "Interested in fall 2025 intake",
                "assigned_to": None
            }
        }

class LeadUpdate(BaseModel):
    """Lead update model"""
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
    """Lead assignment model"""
    assigned_to: str  # User ID
    notes: Optional[str] = Field(None, max_length=500)

class LeadResponse(LeadBase):
    """Lead response model"""
    id: str
    lead_id: str  # Auto-generated ID like LD-1029
    status: LeadStatus
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None  # Name of assigned user
    created_by: str
    created_by_name: str  # Name of creator
    created_at: datetime
    updated_at: datetime
    last_contacted: Optional[datetime] = None

    class Config:
        from_attributes = True

class LeadInDB(LeadBase):
    """Lead model as stored in database"""
    id: str
    lead_id: str  # Auto-generated ID like LD-1029
    status: LeadStatus = LeadStatus.OPEN
    assigned_to: Optional[str] = None
    created_by: str  # User ID who created the lead
    created_at: datetime
    updated_at: datetime
    last_contacted: Optional[datetime] = None

    class Config:
        from_attributes = True

class LeadListResponse(BaseModel):
    """Lead list response model"""
    leads: List[LeadResponse]
    total: int
    page: int
    limit: int
    has_next: bool
    has_prev: bool

class LeadStatusUpdate(BaseModel):
    """Lead status update model"""
    status: LeadStatus
    notes: Optional[str] = Field(None, max_length=500)