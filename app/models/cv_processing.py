# app/models/cv_processing.py - CV Processing Models for LeadG CRM

from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

# ============================================================================
# ENUMERATIONS
# ============================================================================

class CVProcessingStatus(str, Enum):
    """CV Processing status enumeration"""
    PROCESSING = "processing"
    PENDING_REVIEW = "pending_review"
    READY_FOR_CONVERSION = "ready_for_conversion"
    CONVERTED = "converted"
    FAILED = "failed"

class CVFileType(str, Enum):
    """Supported CV file types"""
    PDF = "application/pdf"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    DOC = "application/msword"

# ============================================================================
# CORE CV PROCESSING MODELS
# ============================================================================

class CVExtractionData(BaseModel):
    """Extracted data structure from CV"""
    name: Optional[str] = Field(None, description="Extracted full name")
    email: Optional[str] = Field(None, description="Extracted email address")
    phone: Optional[str] = Field(None, description="Extracted phone number")
    age: Optional[int] = Field(None, ge=16, le=80, description="Extracted or calculated age")
    skills: Optional[str] = Field(None, description="Comma-separated extracted skills")
    education: Optional[str] = Field(None, description="Educational background summary")
    experience: Optional[str] = Field(None, description="Work experience summary")
    
    # Quality metrics
    extraction_confidence: Dict[str, float] = Field(default_factory=dict, description="Confidence scores for each field")
    raw_text_length: Optional[int] = Field(None, description="Length of extracted raw text")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "john.doe@example.com",
                "phone": "+1234567890",
                "age": 28,
                "skills": "Python, React, Node.js, AWS, MongoDB",
                "education": "Bachelor of Computer Science, State University",
                "experience": "5 years software development experience",
                "extraction_confidence": {
                    "name": 0.95,
                    "email": 0.98,
                    "phone": 0.87,
                    "skills": 0.92,
                    "education": 0.89,
                    "experience": 0.76
                },
                "raw_text_length": 2450
            }
        }

class CVFileMetadata(BaseModel):
    """CV file metadata"""
    original_filename: str = Field(..., description="Original uploaded filename")
    file_size: int = Field(..., ge=1, description="File size in bytes")
    mime_type: str = Field(..., description="MIME type of the file")
    processing_time_ms: Optional[int] = Field(None, description="Processing time in milliseconds")
    extractor_version: str = Field(default="1.0", description="Version of extraction engine used")
    
    class Config:
        json_schema_extra = {
            "example": {
                "original_filename": "john_doe_resume.pdf",
                "file_size": 2048576,
                "mime_type": "application/pdf",
                "processing_time_ms": 1250,
                "extractor_version": "1.0"
            }
        }

class CVProcessingResult(BaseModel):
    """Complete CV processing result"""
    processing_id: str = Field(..., description="Unique processing identifier")
    status: CVProcessingStatus
    extracted_data: Optional[CVExtractionData] = None
    file_metadata: CVFileMetadata
    
    # Processing metadata
    uploaded_by: str = Field(..., description="User ID who uploaded the CV")
    uploaded_by_email: str = Field(..., description="Email of user who uploaded")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Review and conversion tracking
    reviewed: bool = Field(default=False, description="Whether the extraction has been reviewed")
    reviewed_by: Optional[str] = Field(None, description="User ID who reviewed")
    reviewed_at: Optional[datetime] = Field(None, description="When the review was completed")
    
    converted_to_lead: bool = Field(default=False, description="Whether converted to lead")
    lead_id: Optional[str] = Field(None, description="Lead ID if converted")
    converted_by: Optional[str] = Field(None, description="User ID who converted to lead")
    converted_at: Optional[datetime] = Field(None, description="When converted to lead")
    
    # Error handling
    error_message: Optional[str] = Field(None, description="Error message if processing failed")
    extraction_errors: List[str] = Field(default_factory=list, description="List of extraction issues")
    processing_notes: Optional[str] = Field(None, description="Additional processing notes")
    
    class Config:
        json_schema_extra = {
            "example": {
                "processing_id": "cv_20250901_001",
                "status": "ready_for_conversion",
                "extracted_data": {
                    "name": "John Doe",
                    "email": "john.doe@example.com",
                    "phone": "+1234567890",
                    "skills": "Python, React, AWS"
                },
                "file_metadata": {
                    "original_filename": "resume.pdf",
                    "file_size": 1024000,
                    "mime_type": "application/pdf"
                },
                "uploaded_by": "user123",
                "uploaded_by_email": "admin@company.com",
                "created_at": "2025-09-01T10:30:00Z",
                "reviewed": True,
                "converted_to_lead": False
            }
        }

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class CVUploadResponse(BaseModel):
    """Response after CV upload"""
    success: bool
    message: str
    processing_id: Optional[str] = None
    status: Optional[CVProcessingStatus] = None
    estimated_processing_time: Optional[int] = Field(None, description="Estimated processing time in seconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "CV uploaded successfully and processing started",
                "processing_id": "cv_20250901_001",
                "status": "processing",
                "estimated_processing_time": 30
            }
        }

class CVExtractionUpdateRequest(BaseModel):
    """Request to update extracted CV data"""
    name: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=20)
    age: Optional[int] = Field(None, ge=16, le=80)
    skills: Optional[str] = Field(None, max_length=1000)
    education: Optional[str] = Field(None, max_length=500)
    experience: Optional[str] = Field(None, max_length=500)
    processing_notes: Optional[str] = Field(None, max_length=1000)
    
    @validator('email')
    def validate_email(cls, v):
        if v and v.strip():
            # Basic email validation
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, v.strip()):
                raise ValueError('Invalid email format')
            return v.strip()
        return None
    
    @validator('phone')
    def validate_phone(cls, v):
        if v and v.strip():
            # Remove common phone formatting
            import re
            cleaned_phone = re.sub(r'[^\d+]', '', v.strip())
            if len(cleaned_phone) < 10 or len(cleaned_phone) > 15:
                raise ValueError('Phone number must be 10-15 digits')
            return cleaned_phone
        return None
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "john.doe@corrected.com",
                "phone": "+1234567890",
                "age": 29,
                "skills": "Python, React, Node.js, Docker, AWS",
                "education": "Bachelor of Computer Science, Updated University",
                "experience": "5+ years in full-stack development",
                "processing_notes": "Corrected email address and added Docker to skills"
            }
        }

class CVToLeadRequest(BaseModel):
    """Request to convert CV extraction to lead"""
    processing_id: str = Field(..., description="CV processing ID to convert")
    
    # Lead creation overrides (optional - use extracted data if not provided)
    name: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = None
    contact_number: Optional[str] = Field(None, max_length=20)
    age: Optional[int] = Field(None, ge=16, le=80)
    experience: Optional[str] = Field(None, max_length=500)
    nationality: Optional[str] = Field(None, max_length=50)
    
    # Standard lead creation fields
    source: Optional[str] = Field(default="cv_upload", max_length=50)
    category: Optional[str] = Field(None, description="Lead category (required)")
    course_level: Optional[str] = Field(None, description="Course level")
    stage: Optional[str] = Field(default="initial", max_length=50)
    lead_score: Optional[int] = Field(default=0, ge=0, le=100)
    tags: List[str] = Field(default_factory=list, description="Additional tags for the lead")
    notes: Optional[str] = Field(None, max_length=2000, description="Additional notes for the lead")
    
    # Assignment options
    assign_to: Optional[str] = Field(None, description="User email to assign to")
    assignment_method: Optional[str] = Field(default="unassigned", description="Assignment method")
    
    @validator('category')
    def validate_category(cls, v):
        if not v or not v.strip():
            raise ValueError('Category is required for lead creation')
        return v.strip()
    
    @validator('email')
    def validate_email(cls, v):
        if v and v.strip():
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, v.strip()):
                raise ValueError('Invalid email format')
            return v.strip()
        return None
    
    @validator('tags')
    def validate_tags(cls, v):
        if v:
            # Clean and validate tags
            cleaned_tags = []
            for tag in v:
                if isinstance(tag, str) and tag.strip():
                    cleaned_tags.append(tag.strip())
            return cleaned_tags
        return []
    
    class Config:
        json_schema_extra = {
            "example": {
                "processing_id": "cv_20250901_001",
                "name": "John Doe",
                "email": "john.doe@example.com",
                "contact_number": "+1234567890",
                "category": "Software Development",
                "course_level": "Intermediate",
                "source": "cv_upload",
                "stage": "initial",
                "lead_score": 75,
                "tags": ["CV Upload", "Python Developer", "Remote Work"],
                "notes": "Converted from CV. Strong technical background in Python and React.",
                "assign_to": "recruiter@company.com",
                "assignment_method": "manual"
            }
        }

class CVToLeadResponse(BaseModel):
    """Response after converting CV to lead"""
    success: bool
    message: str
    processing_id: str
    lead_id: Optional[str] = None
    lead_details: Optional[Dict[str, Any]] = None
    assignment_info: Optional[Dict[str, Any]] = None
    validation_errors: List[str] = Field(default_factory=list)
    cleanup_completed: bool = Field(default=False, description="Whether CV data was cleaned up after conversion")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "CV successfully converted to lead",
                "processing_id": "cv_20250901_001",
                "lead_id": "LD-SD-WS-001",
                "lead_details": {
                    "name": "John Doe",
                    "email": "john.doe@example.com",
                    "category": "Software Development",
                    "source": "cv_upload"
                },
                "assignment_info": {
                    "assigned_to": "recruiter@company.com",
                    "assignment_method": "manual"
                },
                "validation_errors": [],
                "cleanup_completed": True
            }
        }

class CVExtractionListResponse(BaseModel):
    """Response for listing CV extractions"""
    extractions: List[CVProcessingResult]
    total_count: int
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)
    total_pages: int
    filters_applied: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('total_pages', always=True)
    def calculate_total_pages(cls, v, values):
        total_count = values.get('total_count', 0)
        limit = values.get('limit', 20)
        return (total_count + limit - 1) // limit
    
    class Config:
        json_schema_extra = {
            "example": {
                "extractions": [
                    {
                        "processing_id": "cv_20250901_001",
                        "status": "ready_for_conversion",
                        "extracted_data": {
                            "name": "John Doe",
                            "email": "john.doe@example.com"
                        },
                        "created_at": "2025-09-01T10:30:00Z"
                    }
                ],
                "total_count": 25,
                "page": 1,
                "limit": 20,
                "total_pages": 2,
                "filters_applied": {
                    "status": "ready_for_conversion"
                }
            }
        }

class CVProcessingStatsResponse(BaseModel):
    """CV processing statistics response"""
    total_uploads: int
    processing_count: int
    pending_review_count: int
    ready_for_conversion_count: int
    converted_count: int
    failed_count: int
    user_upload_count: int = Field(description="Uploads by current user")
    user_pending_count: int = Field(description="User's pending conversions")
    average_processing_time_ms: Optional[float] = None
    success_rate: Optional[float] = Field(None, ge=0, le=100)
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_uploads": 150,
                "processing_count": 3,
                "pending_review_count": 12,
                "ready_for_conversion_count": 8,
                "converted_count": 125,
                "failed_count": 2,
                "user_upload_count": 25,
                "user_pending_count": 5,
                "average_processing_time_ms": 1850.5,
                "success_rate": 98.7
            }
        }

# ============================================================================
# VALIDATION HELPER MODELS
# ============================================================================

class CVValidationResult(BaseModel):
    """CV file validation result"""
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    file_info: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "valid": True,
                "errors": [],
                "warnings": ["Low confidence extraction for experience field"],
                "file_info": {
                    "size_mb": 2.1,
                    "pages": 2,
                    "text_extractable": True
                }
            }
        }

class ExtractionQualityMetrics(BaseModel):
    """Quality metrics for extraction results"""
    overall_confidence: float = Field(ge=0, le=1, description="Overall extraction confidence")
    field_completeness: float = Field(ge=0, le=1, description="Percentage of expected fields extracted")
    data_quality_score: float = Field(ge=0, le=100, description="Overall data quality score")
    recommended_review: bool = Field(description="Whether manual review is recommended")
    quality_issues: List[str] = Field(default_factory=list)
    
    class Config:
        json_schema_extra = {
            "example": {
                "overall_confidence": 0.87,
                "field_completeness": 0.92,
                "data_quality_score": 85.5,
                "recommended_review": False,
                "quality_issues": ["Phone number format unclear"]
            }
        }