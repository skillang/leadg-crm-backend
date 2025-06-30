# app/models/contact.py - Contact Models (Fixed Pydantic V2)
from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List
from enum import Enum
from datetime import datetime

class ContactRole(str, Enum):
    """Contact roles for business relationship"""
    DECISION_MAKER = "Decision Maker"
    INFLUENCER = "Influencer"
    END_USER = "End User"
    PARENT = "Parent"
    GUARDIAN = "Guardian"
    COUNSELOR = "Counselor"

class ContactRelationship(str, Enum):
    """Contact relationship to the lead/student"""
    STUDENT = "Student"
    PARENT = "Parent"
    COUNSELOR = "Counselor"
    AGENT = "Agent"
    GUARDIAN = "Guardian"
    FAMILY_MEMBER = "Family Member"

class ContactBase(BaseModel):
    """Base contact model with common fields"""
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    role: ContactRole
    relationship: ContactRelationship
    is_primary: bool = False
    address: Optional[str] = None
    notes: Optional[str] = None
    linked_leads: Optional[List[str]] = []

    @validator('first_name', 'last_name')
    def validate_names(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        if len(v.strip()) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v.strip().title()

    @validator('phone')
    def validate_phone(cls, v):
        if v is not None:
            # Remove spaces and dashes for validation
            cleaned = v.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            if not cleaned.startswith('+') and not cleaned.isdigit():
                raise ValueError("Phone number must contain only digits, spaces, dashes, parentheses, or start with +")
            if len(cleaned) < 10:
                raise ValueError("Phone number must be at least 10 digits")
        return v

    @validator('linked_leads')
    def validate_linked_leads(cls, v):
        if v is None:
            return []
        # Validate lead ID format
        for lead_id in v:
            if not lead_id.startswith('LD-'):
                raise ValueError(f"Invalid lead ID format: {lead_id}. Must start with 'LD-'")
        return v

    @validator('notes')
    def validate_notes(cls, v):
        if v is not None and len(v.strip()) > 1000:
            raise ValueError("Notes cannot exceed 1000 characters")
        return v.strip() if v else None

class ContactCreate(ContactBase):
    """Model for creating a new contact"""
    
    class Config:
        json_schema_extra = {  # Fixed: Changed from schema_extra to json_schema_extra
            "example": {
                "first_name": "Sarah",
                "last_name": "Johnson",
                "email": "sarah.johnson@example.com",
                "phone": "+1-555-123-4567",
                "role": "Decision Maker",
                "relationship": "Parent",
                "is_primary": True,
                "address": "123 Oak Street, Springfield, IL 62701",
                "notes": "Parent of multiple children applying to different programs. Prefers email communication.",
                "linked_leads": ["LD-1000", "LD-1001"]
            }
        }

class ContactUpdate(BaseModel):
    """Model for updating an existing contact"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    role: Optional[ContactRole] = None
    relationship: Optional[ContactRelationship] = None
    is_primary: Optional[bool] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    linked_leads: Optional[List[str]] = None

    @validator('first_name', 'last_name')
    def validate_names(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError("Name cannot be empty")
            if len(v.strip()) < 2:
                raise ValueError("Name must be at least 2 characters")
            return v.strip().title()
        return v

    @validator('phone')
    def validate_phone(cls, v):
        if v is not None:
            # Remove spaces and dashes for validation
            cleaned = v.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            if not cleaned.startswith('+') and not cleaned.isdigit():
                raise ValueError("Phone number must contain only digits, spaces, dashes, parentheses, or start with +")
            if len(cleaned) < 10:
                raise ValueError("Phone number must be at least 10 digits")
        return v

    @validator('linked_leads')
    def validate_linked_leads(cls, v):
        if v is not None:
            # Validate lead ID format
            for lead_id in v:
                if not lead_id.startswith('LD-'):
                    raise ValueError(f"Invalid lead ID format: {lead_id}. Must start with 'LD-'")
        return v

    @validator('notes')
    def validate_notes(cls, v):
        if v is not None and len(v.strip()) > 1000:
            raise ValueError("Notes cannot exceed 1000 characters")
        return v.strip() if v else None

    class Config:
        json_schema_extra = {  # Fixed: Changed from schema_extra to json_schema_extra
            "example": {
                "first_name": "Sarah",
                "last_name": "Johnson",
                "email": "sarah.johnson.updated@example.com",
                "phone": "+1-555-123-9999",
                "role": "Decision Maker",
                "relationship": "Parent",
                "is_primary": True,
                "address": "456 New Address, Springfield, IL 62701",
                "notes": "Updated notes about the contact",
                "linked_leads": ["LD-1000", "LD-1002"]
            }
        }

class ContactResponse(BaseModel):
    """Model for contact response data"""
    id: str
    lead_id: str
    first_name: str
    last_name: str
    full_name: str
    email: str
    phone: Optional[str] = None
    role: str
    relationship: str
    is_primary: bool
    address: Optional[str] = None
    notes: Optional[str] = None
    linked_leads: List[str] = []
    created_by_name: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {  # Fixed: Changed from schema_extra to json_schema_extra
            "example": {
                "id": "60d5ecb74b24a8001f5e4b23",
                "lead_id": "LD-1000",
                "first_name": "Sarah",
                "last_name": "Johnson",
                "full_name": "Sarah Johnson",
                "email": "sarah.johnson@example.com",
                "phone": "+1-555-123-4567",
                "role": "Decision Maker",
                "relationship": "Parent",
                "is_primary": True,
                "address": "123 Oak Street, Springfield, IL 62701",
                "notes": "Parent of multiple children applying to different programs.",
                "linked_leads": ["LD-1000", "LD-1001"],
                "created_by_name": "Admin User",
                "created_at": "2025-06-30T10:30:00Z",
                "updated_at": "2025-06-30T11:15:00Z"
            }
        }

class ContactListResponse(BaseModel):
    """Model for contact list response"""
    lead_id: str
    lead_info: Optional[dict] = None
    contacts: List[ContactResponse]
    total_count: int
    primary_contact: Optional[ContactResponse] = None
    contact_summary: dict

    class Config:
        json_schema_extra = {  # Fixed: Changed from schema_extra to json_schema_extra
            "example": {
                "lead_id": "LD-1000",
                "lead_info": {
                    "lead_id": "LD-1000",
                    "name": "John Doe",
                    "email": "john@example.com",
                    "status": "open"
                },
                "contacts": [
                    {
                        "id": "contact1",
                        "first_name": "Sarah",
                        "last_name": "Johnson",
                        "relationship": "Parent",
                        "is_primary": True
                    }
                ],
                "total_count": 3,
                "primary_contact": {
                    "id": "contact1",
                    "first_name": "Sarah",
                    "last_name": "Johnson",
                    "is_primary": True
                },
                "contact_summary": {
                    "total": 3,
                    "by_role": {
                        "Decision Maker": 1,
                        "End User": 1,
                        "Counselor": 1
                    },
                    "by_relationship": {
                        "Parent": 1,
                        "Student": 1,
                        "Counselor": 1
                    }
                }
            }
        }

# Contact operation response models
class ContactCreateResponse(BaseModel):
    """Response model for contact creation"""
    id: str
    message: str
    linked_leads: List[str]
    warning: Optional[str] = None

class ContactUpdateResponse(BaseModel):
    """Response model for contact updates"""
    id: str
    message: str
    updated_fields: List[str]

class ContactDeleteResponse(BaseModel):
    """Response model for contact deletion"""
    id: str
    message: str
    deleted_contact: dict

class ContactPrimaryResponse(BaseModel):
    """Response model for setting primary contact"""
    id: str
    message: str
    primary_contact: dict

# NEW: Added the missing SetPrimaryContactRequest model
class SetPrimaryContactRequest(BaseModel):
    """Request model for setting primary contact (if needed for body data)"""
    pass  # This endpoint typically doesn't need body data, but keeping for compatibility

# Utility models for filtering and statistics
class ContactRoleCount(BaseModel):
    """Model for role-based contact counts"""
    role: str
    count: int

class ContactRelationshipCount(BaseModel):
    """Model for relationship-based contact counts"""
    relationship: str
    count: int

class ContactStatistics(BaseModel):
    """Model for contact statistics"""
    total_contacts: int
    primary_contacts: int
    role_distribution: List[ContactRoleCount]
    relationship_distribution: List[ContactRelationshipCount]
    linked_leads_count: int