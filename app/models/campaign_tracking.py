# app/models/campaign_tracking.py
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from enum import Enum


class TrackingStatus(str, Enum):
    """Tracking status enum"""
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CRITERIA_NOT_MATCHED = "criteria_not_matched"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    """Job type enum"""
    ENROLLMENT = "enrollment"
    MESSAGE_JOB = "message_job"


class CampaignEnrollment(BaseModel):
    """Track lead enrollment in campaign"""
    campaign_id: str = Field(..., description="Campaign ID")
    lead_id: str = Field(..., description="Lead ID")
    
    # Enrollment details
    enrolled_at: datetime = Field(default_factory=datetime.utcnow)
    enrolled_with_stage: Optional[str] = Field(None, description="Stage when enrolled")
    enrolled_with_source: Optional[str] = Field(None, description="Source when enrolled")
    
    # Progress tracking
    messages_sent: int = Field(default=0, ge=0, description="Messages sent to this lead")
    current_sequence: int = Field(default=0, ge=0, description="Current template sequence number")
    
    # Status
    status: TrackingStatus = Field(default=TrackingStatus.ACTIVE)
    
    # Timestamps
    last_message_sent_at: Optional[datetime] = None
    next_scheduled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CampaignJob(BaseModel):
    """Individual message job for campaign"""
    campaign_id: str = Field(..., description="Campaign ID")
    lead_id: str = Field(..., description="Lead ID")
    
    # Job details
    job_type: JobType = Field(default=JobType.MESSAGE_JOB)
    channel: Literal["whatsapp", "email"] = Field(..., description="Message channel")
    template_id: str = Field(..., description="Template ID")
    template_name: str = Field(..., description="Template name")
    sequence_order: int = Field(..., ge=1, description="Message sequence order")
    
    # Scheduling
    execute_at: datetime = Field(..., description="When to execute this job")
    
    # Status tracking
    status: TrackingStatus = Field(default=TrackingStatus.PENDING)
    attempts: int = Field(default=0, ge=0, description="Execution attempts")
    max_attempts: int = Field(default=3, ge=1, description="Maximum retry attempts")
    
    # Error handling
    error_message: Optional[str] = None
    last_error_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    executed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class EnrollmentSummary(BaseModel):
    """Summary of campaign enrollments"""
    campaign_id: str
    total_enrolled: int
    active: int
    paused: int
    completed: int
    criteria_not_matched: int
    failed: int


class JobSummary(BaseModel):
    """Summary of campaign jobs"""
    campaign_id: str
    total_jobs: int
    pending: int
    processing: int
    completed: int
    failed: int
    cancelled: int


class CampaignProgressResponse(BaseModel):
    """Response for campaign progress"""
    campaign_id: str
    campaign_name: str
    enrollment_summary: EnrollmentSummary
    job_summary: JobSummary
    next_scheduled_job: Optional[datetime] = None