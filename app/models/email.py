# app/models/email.py
from pydantic import BaseModel, EmailStr, validator, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from bson import ObjectId

# ============================================================================
# EMAIL RECIPIENT MODELS
# ============================================================================

class EmailRecipient(BaseModel):
    """Individual email recipient with status tracking"""
    email: EmailStr
    name: str
    lead_id: str
    status: Literal["pending", "sent", "failed"] = "pending"
    sent_at: Optional[datetime] = None
    error: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# ============================================================================
# EMAIL REQUEST MODELS (Input from frontend)
# ============================================================================

class EmailRequest(BaseModel):
    """Single lead email request"""
    template_key: str = Field(..., description="Template key from CMS")
    sender_email_prefix: str = Field(..., description="Email prefix like 'info', 'noreply'")
    scheduled_time: Optional[datetime] = Field(None, description="Schedule email for future delivery")
    
    @validator('sender_email_prefix')
    def validate_sender_prefix(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Sender email prefix cannot be empty')
        # Remove any @ or domain parts, just keep the prefix
        return v.strip().split('@')[0]
    
    @validator('scheduled_time')
    def validate_scheduled_time(cls, v):
        if v:
            # Don't validate future time here - let the service handle timezone conversion
            # Just ensure it's a valid datetime
            return v
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        schema_extra = {
            "example": {
                "template_key": "welcome_template",
                "sender_email_prefix": "info",
                "scheduled_time": "2025-07-25T10:00:00Z"
            }
        }

class BulkEmailRequest(BaseModel):
    """Bulk email request for multiple leads"""
    lead_ids: List[str] = Field(..., description="List of lead IDs to send email to")
    template_key: str = Field(..., description="Template key from CMS")
    sender_email_prefix: str = Field(..., description="Email prefix like 'info', 'marketing'")
    scheduled_time: Optional[datetime] = Field(None, description="Schedule email for future delivery")
    
    @validator('lead_ids')
    def validate_lead_ids(cls, v):
        if not v or len(v) == 0:
            raise ValueError('At least one lead ID is required')
        if len(v) > 500:  # From settings.max_bulk_recipients
            raise ValueError('Maximum 500 leads allowed in bulk email')
        # Remove duplicates
        return list(set(v))
    
    @validator('sender_email_prefix')
    def validate_sender_prefix(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Sender email prefix cannot be empty')
        return v.strip().split('@')[0]
    
    @validator('scheduled_time')
    def validate_scheduled_time(cls, v):
        if v:
            # Don't validate future time here - let the service handle timezone conversion
            # Just ensure it's a valid datetime
            return v
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        schema_extra = {
            "example": {
                "lead_ids": ["LD-1001", "LD-1002", "LD-1003"],
                "template_key": "newsletter_template",
                "sender_email_prefix": "marketing",
                "scheduled_time": "2025-07-25T10:00:00Z"
            }
        }

# ============================================================================
# EMAIL RESPONSE MODELS (Output to frontend)
# ============================================================================

class EmailResponse(BaseModel):
    """Standard email operation response"""
    success: bool
    message: str
    email_id: Optional[str] = None
    lead_id: Optional[str] = None  # For single lead emails
    lead_ids: Optional[List[str]] = None  # For bulk emails
    total_recipients: int = 0
    scheduled: bool = False
    scheduled_time: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class EmailHistoryItem(BaseModel):
    """Single email history item for lead timeline"""
    email_id: str
    template_key: str
    template_name: Optional[str] = None
    sender_email: str
    recipient_email: str
    recipient_name: str
    status: Literal["pending", "sent", "failed", "cancelled"]
    scheduled: bool = False
    scheduled_time: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    error: Optional[str] = None
    created_by_name: str
    created_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class EmailHistoryResponse(BaseModel):
    """Email history response for a lead"""
    lead_id: str
    emails: List[EmailHistoryItem]
    total: int
    page: int = 1
    limit: int = 10

# ============================================================================
# SCHEDULED EMAIL MODELS
# ============================================================================

class ScheduledEmailItem(BaseModel):
    """Single scheduled email item"""
    email_id: str
    template_key: str
    template_name: Optional[str] = None
    sender_email: str
    total_recipients: int
    lead_id: Optional[str] = None  # For single emails
    lead_ids: Optional[List[str]] = None  # For bulk emails
    scheduled_time: datetime
    status: Literal["pending", "sent", "failed", "cancelled"]
    created_by_name: str
    created_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ScheduledEmailsResponse(BaseModel):
    """Response for scheduled emails list"""
    emails: List[ScheduledEmailItem]
    total: int
    pending_count: int = 0
    page: int = 1
    limit: int = 20

# ============================================================================
# EMAIL STATISTICS MODELS
# ============================================================================

class EmailStats(BaseModel):
    """Email usage statistics"""
    emails_sent_today: int = 0
    emails_sent_week: int = 0
    emails_sent_month: int = 0
    emails_scheduled: int = 0
    emails_failed_today: int = 0
    top_template: Optional[str] = None
    top_template_count: int = 0
    delivery_rate: float = 0.0  # Percentage

class EmailStatsResponse(BaseModel):
    """Email statistics response"""
    success: bool
    stats: EmailStats
    user_specific: bool = False  # True if stats are for current user only

# ============================================================================
# TEMPLATE MODELS (for completeness, though frontend will handle)
# ============================================================================

class EmailTemplate(BaseModel):
    """Email template structure"""
    key: str
    name: str
    subject: Optional[str] = ""
    description: Optional[str] = ""

class EmailTemplatesResponse(BaseModel):
    """Email templates response"""
    success: bool
    templates: List[EmailTemplate] = []
    total: int = 0

# ============================================================================
# DATABASE DOCUMENT MODELS (for internal use)
# ============================================================================

class EmailDocument(BaseModel):
    """Email document structure for MongoDB"""
    email_id: str
    lead_id: Optional[str] = None  # For single lead emails
    lead_ids: Optional[List[str]] = None  # For bulk emails
    email_type: Literal["single", "bulk"] = "single"
    
    # Email details
    template_key: str
    template_name: Optional[str] = None
    sender_email: str
    
    # Recipients
    recipients: List[EmailRecipient]
    
    # Status and scheduling
    status: Literal["pending", "sent", "failed", "cancelled"] = "pending"
    is_scheduled: bool = False
    scheduled_time: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    
    # Metadata
    total_recipients: int
    sent_count: int = 0
    failed_count: int = 0
    error_message: Optional[str] = None
    
    # User tracking (following your CRM pattern)
    created_by: str  # ObjectId as string
    created_by_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }