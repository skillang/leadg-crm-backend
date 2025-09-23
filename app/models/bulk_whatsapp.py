# app/models/bulk_whatsapp.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from bson import ObjectId

# ================================
# REQUEST MODELS (SIMPLIFIED - SAME AS EMAIL PATTERN)
# ================================

class CreateBulkWhatsAppRequest(BaseModel):
    """Request model for creating bulk WhatsApp job - SIMPLIFIED like email system"""
    job_name: str = Field(..., min_length=1, max_length=100, description="Name for the bulk job")
    message_type: Literal["template", "text"] = Field(..., description="Type of message to send")
    
    # Template-specific fields
    template_name: Optional[str] = Field(None, description="WhatsApp template name (required for template type)")
    
    # Text message-specific fields  
    message_content: Optional[str] = Field(None, max_length=1000, description="Text message content (required for text type)")
    
    # SIMPLIFIED: Just lead IDs like email system
    lead_ids: List[str] = Field(..., min_items=1, description="Lead IDs to send messages to")
    
    # Scheduling options (same timezone handling as email)
    scheduled_time: Optional[datetime] = Field(None, description="When to send (IST timezone, will be converted to UTC)")
    
    # Processing settings
    batch_size: int = Field(default=10, ge=1, le=50, description="Number of messages to process at once")
    delay_between_messages: int = Field(default=2, ge=1, le=10, description="Delay between messages in seconds")
    
    # Validation rules (simplified)
    @validator('template_name')
    def validate_template_name(cls, v, values):
        if values.get('message_type') == 'template' and not v:
            raise ValueError('template_name is required for template messages')
        return v
    
    @validator('message_content')
    def validate_message_content(cls, v, values):
        if values.get('message_type') == 'text' and not v:
            raise ValueError('message_content is required for text messages')
        return v
    
    @validator('lead_ids')
    def validate_lead_ids(cls, v):
        if not v or len(v) == 0:
            raise ValueError('At least one lead_id is required')
        # Remove duplicates
        return list(set(v))

class CancelBulkJobRequest(BaseModel):
    """Request model for cancelling bulk job"""
    reason: Optional[str] = Field(None, max_length=200, description="Reason for cancellation")

# ================================
# DATABASE MODELS (SIMPLIFIED - SAME STRUCTURE AS EMAIL)
# ================================

class BulkWhatsAppRecipient(BaseModel):
    """Individual recipient in bulk job"""
    lead_id: str
    phone_number: str
    lead_name: str
    email: Optional[str] = None
    status: Literal["pending", "sent", "failed", "skipped"] = "pending"
    message_id: Optional[str] = None
    sent_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0

class BulkWhatsAppJob(BaseModel):
    """
    Database model for bulk WhatsApp job - SIMPLIFIED like your email system
    Stores in bulk_whatsapp_jobs collection
    """
    # Job identification
    job_id: str = Field(..., description="Unique job identifier")
    job_name: str
    
    # Message configuration (same as your email template structure)
    message_type: Literal["template", "text"]
    template_name: Optional[str] = None
    message_content: Optional[str] = None
    
    # Recipients (simplified - just the list like email)
    total_recipients: int
    recipients: List[BulkWhatsAppRecipient] = Field(default_factory=list)
    lead_ids: List[str] = Field(default_factory=list)  # Original lead IDs from request
    
    # Progress tracking (EXACT SAME as your email)
    processed_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    status: Literal["pending", "processing", "completed", "failed", "cancelled"] = "pending"
    
    # Scheduling (same timezone handling as email)
    is_scheduled: bool = False
    scheduled_time: Optional[datetime] = None  # Stored in UTC like your email
    
    # Processing settings
    batch_size: int = 10
    delay_between_messages: int = 2
    max_retries: int = 3
    
    # Results and error tracking
    results: List[Dict[str, Any]] = Field(default_factory=list)
    error_message: Optional[str] = None
    
    # Audit fields (SAME as your email)
    created_by: str  # ObjectId as string
    created_by_name: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    updated_at: datetime
    
    class Config:
        # Allow ObjectId serialization
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }

# ================================
# RESPONSE MODELS (SIMPLIFIED)
# ================================

class BulkJobResponse(BaseModel):
    """Response model for bulk job creation"""
    success: bool
    job_id: str
    message: str
    total_recipients: int
    scheduled: bool = False
    scheduled_time_ist: Optional[str] = None
    scheduled_time_utc: Optional[datetime] = None

class BulkJobStatusResponse(BaseModel):
    """Response model for job status - Same pattern as your email status"""
    job_id: str
    job_name: str
    message_type: str
    template_name: Optional[str] = None
    
    # Progress information
    status: str
    total_recipients: int
    processed_count: int
    success_count: int
    failed_count: int
    skipped_count: int
    progress_percentage: float
    
    # Timing information (same as email)
    is_scheduled: bool
    scheduled_time: Optional[datetime] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Metadata
    created_by_name: str
    estimated_completion: Optional[datetime] = None

class BulkJobListResponse(BaseModel):
    """Response model for listing bulk jobs"""
    jobs: List[BulkJobStatusResponse]
    pagination: Dict[str, Any]

class BulkStatsResponse(BaseModel):
    """Response model for bulk messaging statistics"""
    total_jobs: int
    active_jobs: int
    completed_jobs: int
    failed_jobs: int
    total_messages_sent: int
    total_messages_failed: int
    success_rate: float
    
    # Recent activity
    jobs_today: int
    messages_sent_today: int
    
    # Next scheduled job
    next_scheduled_job: Optional[Dict[str, Any]] = None

# ================================
# ENUMS AND CONSTANTS (SIMPLIFIED)
# ================================

class BulkJobStatus:
    """Job status constants - Same as your email"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class MessageType:
    """Message type constants"""
    TEMPLATE = "template"
    TEXT = "text"

class RecipientStatus:
    """Recipient status constants"""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"

# ================================
# VALIDATION FUNCTIONS (SIMPLIFIED)
# ================================

def validate_phone_number(phone: str) -> bool:
    """Validate phone number format for WhatsApp"""
    if not phone:
        return False
    
    # Remove common prefixes and formatting
    cleaned = phone.replace("+", "").replace("-", "").replace(" ", "")
    
    # Should be numeric and reasonable length
    return cleaned.isdigit() and 10 <= len(cleaned) <= 15

def validate_bulk_job_data(job_data: Dict[str, Any]) -> List[str]:
    """Validate bulk job data - returns list of errors (simplified)"""
    errors = []
    
    # Check required fields
    if not job_data.get("job_name"):
        errors.append("job_name is required")
    
    if not job_data.get("message_type"):
        errors.append("message_type is required")
    
    # Validate message type specific fields
    message_type = job_data.get("message_type")
    if message_type == "template" and not job_data.get("template_name"):
        errors.append("template_name is required for template messages")
    
    if message_type == "text" and not job_data.get("message_content"):
        errors.append("message_content is required for text messages")
    
    # Validate lead IDs (simplified)
    lead_ids = job_data.get("lead_ids", [])
    if not lead_ids or len(lead_ids) == 0:
        errors.append("At least one lead_id is required")
    
    return errors