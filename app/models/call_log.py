# app/models/call_log.py
# Call History and Logging Models for Tata Tele Integration
# Comprehensive call tracking and analytics models

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum
import re

# ============================================================================
# ENUMS FOR CALL MANAGEMENT
# ============================================================================

class CallType(str, Enum):
    """Types of calls supported by the system"""
    CLICK_TO_CALL = "click_to_call"
    SUPPORT_CALL = "support_call"
    MANUAL_CALL = "manual_call"
    CALLBACK = "callback"
    FOLLOW_UP = "follow_up"

class CallStatus(str, Enum):
    """Call status progression"""
    INITIATED = "initiated"
    RINGING = "ringing"
    ANSWERED = "answered"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BUSY = "busy"
    NO_ANSWER = "no_answer"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

class CallDirection(str, Enum):
    """Call direction from agent perspective"""
    OUTBOUND = "outbound"
    INBOUND = "inbound"

class CallPriority(str, Enum):
    """Call priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

class CallOutcome(str, Enum):
    """Call outcome/result"""
    SUCCESSFUL = "successful"
    NO_RESPONSE = "no_response"
    WRONG_NUMBER = "wrong_number"
    BUSY_SIGNAL = "busy_signal"
    VOICEMAIL = "voicemail"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    CALLBACK_REQUESTED = "callback_requested"
    INFORMATION_PROVIDED = "information_provided"
    MEETING_SCHEDULED = "meeting_scheduled"

# ============================================================================
# TATA TELE API REQUEST MODELS
# ============================================================================

class ClickToCallRequest(BaseModel):
    """Request model for Tata Click-to-Call API"""
    lead_id: Optional[str] = Field(None, description="Lead ID for tracking")
    notes: Optional[str] = Field(None, description="Call notes")
    agent_number: str = Field(..., description="Smartflo agent number")
    destination_number: str = Field(..., description="Customer number to call")
    caller_id: Optional[str] = Field(None, description="Caller ID shown to customer")
    async_call: int = Field(default=1, description="1 for async, 0 for sync")
    call_timeout: Optional[int] = Field(None, description="Call timeout in seconds")
    get_call_id: Optional[int] = Field(None, description="1 to return call_id in response")
    custom_identifier: Optional[str] = Field(None, description="Custom parameter for webhook")

    @validator('agent_number', 'destination_number')
    def validate_phone_number(cls, v):
        cleaned = re.sub(r'[^\d+]', '', v)
        if not cleaned:
            raise ValueError('Phone number cannot be empty')
        if not re.match(r'^\+?[1-9]\d{1,14}$', cleaned):
            raise ValueError('Invalid phone number format')
        return cleaned

    @validator('async_call')
    def validate_async_call(cls, v):
        if v not in [0, 1]:
            raise ValueError('async_call must be 0 or 1')
        return v

class SupportCallRequest(BaseModel):
    """Request model for Tata Support Call API"""
    customer_number: str = Field(..., description="Customer's phone number")
    api_key: str = Field(..., description="API key for authentication")
    get_call_id: Optional[int] = Field(None, description="1 to return call_id in response")
    caller_id: Optional[str] = Field(None, description="DID number to use for call")

    @validator('customer_number')
    def validate_customer_number(cls, v):
        cleaned = re.sub(r'[^\d+]', '', v)
        if len(cleaned) < 10 or len(cleaned) > 15:
            raise ValueError('Customer number must be between 10-15 digits')
        return cleaned

# ============================================================================
# CALL LOG DATABASE MODELS
# ============================================================================

class CallLogCreate(BaseModel):
    """Model for creating a new call log entry"""
    lead_id: str = Field(..., description="Lead ID (LD-XXXX format)")
    caller_user_id: str = Field(..., description="CRM user ID who initiated the call")
    destination_number: str = Field(..., description="Phone number being called")
    caller_id: Optional[str] = Field(None, description="Caller ID used for the call")
    call_type: CallType = Field(default=CallType.CLICK_TO_CALL, description="Type of call")
    call_priority: CallPriority = Field(default=CallPriority.NORMAL, description="Call priority")
    notes: Optional[str] = Field(None, max_length=1000, description="Pre-call notes or context")
    scheduled_at: Optional[datetime] = Field(None, description="Scheduled call time (for callbacks)")
    custom_identifier: Optional[str] = Field(None, description="Custom identifier for tracking")

    @validator('destination_number')
    def validate_destination_number(cls, v):
        cleaned = re.sub(r'[^\d+]', '', v)
        if len(cleaned) < 10 or len(cleaned) > 15:
            raise ValueError('Destination number must be between 10-15 digits')
        return cleaned

class CallLogUpdate(BaseModel):
    """Model for updating call log status and details"""
    call_status: Optional[CallStatus] = Field(None, description="Updated call status")
    call_duration: Optional[int] = Field(None, ge=0, description="Call duration in seconds")
    call_outcome: Optional[CallOutcome] = Field(None, description="Call result/outcome")
    notes: Optional[str] = Field(None, max_length=2000, description="Call notes and details")
    tata_call_id: Optional[str] = Field(None, description="Call ID from Tata system")
    ended_at: Optional[datetime] = Field(None, description="Call end timestamp")
    answered_at: Optional[datetime] = Field(None, description="Call answer timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional call metadata")

    @validator('call_duration')
    def validate_call_duration(cls, v):
        if v is not None and v < 0:
            raise ValueError('Call duration cannot be negative')
        if v is not None and v > 86400:
            raise ValueError('Call duration cannot exceed 24 hours')
        return v

class CallLogResponse(BaseModel):
    """Response model for call log data"""
    id: str = Field(..., description="Call log database ID")
    lead_id: str = Field(..., description="Associated lead ID")
    caller_user_id: str = Field(..., description="User who made the call")
    caller_name: Optional[str] = Field(None, description="Name of user who made the call")
    destination_number: str = Field(..., description="Phone number called")
    caller_id: Optional[str] = Field(None, description="Caller ID used")
    call_type: CallType = Field(..., description="Type of call")
    call_status: CallStatus = Field(..., description="Current call status")
    call_priority: CallPriority = Field(..., description="Call priority")
    call_direction: CallDirection = Field(default=CallDirection.OUTBOUND, description="Call direction")
    call_duration: Optional[int] = Field(None, description="Call duration in seconds")
    call_outcome: Optional[CallOutcome] = Field(None, description="Call outcome")
    notes: Optional[str] = Field(None, description="Call notes")
    tata_call_id: Optional[str] = Field(None, description="Tata system call ID")
    custom_identifier: Optional[str] = Field(None, description="Custom tracking identifier")
    
    # Timestamps
    created_at: datetime = Field(..., description="Call log creation time")
    initiated_at: Optional[datetime] = Field(None, description="Call initiation time")
    answered_at: Optional[datetime] = Field(None, description="Call answer time")
    ended_at: Optional[datetime] = Field(None, description="Call end time")
    scheduled_at: Optional[datetime] = Field(None, description="Scheduled call time")
    
    # Metadata
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    is_overdue: Optional[bool] = Field(None, description="Whether scheduled call is overdue")
    
    # Lead information (populated from database)
    lead_name: Optional[str] = Field(None, description="Lead name")
    lead_email: Optional[str] = Field(None, description="Lead email")
    lead_status: Optional[str] = Field(None, description="Current lead status")

# ============================================================================
# CALL ANALYTICS AND REPORTING MODELS
# ============================================================================

class CallAnalytics(BaseModel):
    """Call analytics and statistics model"""
    total_calls: int = Field(default=0, description="Total number of calls")
    successful_calls: int = Field(default=0, description="Successfully completed calls")
    failed_calls: int = Field(default=0, description="Failed or unsuccessful calls")
    average_duration: float = Field(default=0.0, description="Average call duration in seconds")
    total_duration: int = Field(default=0, description="Total call time in seconds")
    success_rate: float = Field(default=0.0, description="Call success rate percentage")
    
    # Call type breakdown
    click_to_call_count: int = Field(default=0)
    support_call_count: int = Field(default=0)
    manual_call_count: int = Field(default=0)
    callback_count: int = Field(default=0)
    
    # Call outcome breakdown
    interested_count: int = Field(default=0)
    not_interested_count: int = Field(default=0)
    no_response_count: int = Field(default=0)
    callback_requested_count: int = Field(default=0)
    
    # Time-based analytics
    calls_today: int = Field(default=0)
    calls_this_week: int = Field(default=0)
    calls_this_month: int = Field(default=0)
    
    # Performance metrics
    average_answer_time: Optional[float] = Field(None, description="Average time to answer in seconds")
    peak_calling_hour: Optional[int] = Field(None, description="Hour with most calls (0-23)")
    most_productive_day: Optional[str] = Field(None, description="Day with most successful calls")

class CallHistoryFilter(BaseModel):
    """Filter parameters for call history queries"""
    lead_id: Optional[str] = Field(None, description="Filter by specific lead")
    user_id: Optional[str] = Field(None, description="Filter by specific user")
    call_type: Optional[CallType] = Field(None, description="Filter by call type")
    call_status: Optional[CallStatus] = Field(None, description="Filter by call status")
    call_outcome: Optional[CallOutcome] = Field(None, description="Filter by call outcome")
    date_from: Optional[datetime] = Field(None, description="Filter calls from this date")
    date_to: Optional[datetime] = Field(None, description="Filter calls until this date")
    min_duration: Optional[int] = Field(None, ge=0, description="Minimum call duration filter")
    max_duration: Optional[int] = Field(None, ge=0, description="Maximum call duration filter")
    phone_number: Optional[str] = Field(None, description="Filter by destination phone number")
    
    # Pagination
    page: int = Field(default=1, ge=1, description="Page number for pagination")
    limit: int = Field(default=20, ge=1, le=100, description="Number of records per page")
    
    # Sorting
    sort_by: str = Field(default="created_at", description="Sort field")
    sort_order: str = Field(default="desc", description="Sort order (asc/desc)")
    
    @validator('sort_by')
    def validate_sort_by(cls, v):
        allowed_fields = [
            'created_at', 'initiated_at', 'ended_at', 'call_duration', 
            'call_status', 'call_outcome', 'lead_id', 'caller_name'
        ]
        if v not in allowed_fields:
            raise ValueError(f'sort_by must be one of: {allowed_fields}')
        return v
    
    @validator('sort_order')
    def validate_sort_order(cls, v):
        if v.lower() not in ['asc', 'desc']:
            raise ValueError('sort_order must be asc or desc')
        return v.lower()

class CallHistoryResponse(BaseModel):
    """Response model for call history with pagination"""
    calls: List[CallLogResponse] = Field(..., description="List of call logs")
    total_count: int = Field(..., description="Total number of calls matching filter")
    page: int = Field(..., description="Current page number")
    limit: int = Field(..., description="Records per page")
    total_pages: int = Field(..., description="Total number of pages")
    has_more: bool = Field(..., description="Whether there are more pages")
    analytics: Optional[CallAnalytics] = Field(None, description="Analytics for filtered calls")

class CallSummaryReport(BaseModel):
    """Summary report model for call activities"""
    report_period: str = Field(..., description="Report period (daily, weekly, monthly)")
    start_date: datetime = Field(..., description="Report start date")
    end_date: datetime = Field(..., description="Report end date")
    
    # Overall metrics
    total_calls: int = Field(..., description="Total calls in period")
    total_duration_hours: float = Field(..., description="Total call time in hours")
    unique_leads_contacted: int = Field(..., description="Number of unique leads contacted")
    unique_callers: int = Field(..., description="Number of unique callers")
    
    # Performance metrics
    success_rate: float = Field(..., description="Overall success rate percentage")
    average_call_duration: float = Field(..., description="Average call duration in minutes")
    conversion_rate: float = Field(..., description="Lead conversion rate from calls")
    
    # Breakdown by status
    status_breakdown: Dict[str, int] = Field(..., description="Calls by status")
    outcome_breakdown: Dict[str, int] = Field(..., description="Calls by outcome")
    type_breakdown: Dict[str, int] = Field(..., description="Calls by type")
    
    # Top performers
    top_callers: List[Dict[str, Any]] = Field(..., description="Top performing callers")
    busiest_hours: List[Dict[str, Any]] = Field(..., description="Peak calling hours")
    
    # Trends
    daily_call_trend: List[Dict[str, Any]] = Field(..., description="Daily call volume trend")
    success_trend: List[Dict[str, Any]] = Field(..., description="Success rate trend")

# ============================================================================
# CALLBACK AND SCHEDULING MODELS
# ============================================================================

class CallbackRequest(BaseModel):
    """Model for scheduling callback calls"""
    lead_id: str = Field(..., description="Lead ID for callback")
    scheduled_at: datetime = Field(..., description="When to make the callback")
    priority: CallPriority = Field(default=CallPriority.NORMAL, description="Callback priority")
    notes: Optional[str] = Field(None, max_length=500, description="Callback notes or context")
    assigned_to: Optional[str] = Field(None, description="Specific user to handle callback")
    
    @validator('scheduled_at')
    def validate_scheduled_at(cls, v):
        if v <= datetime.utcnow():
            raise ValueError('Callback must be scheduled for future time')
        if v > datetime.utcnow() + timedelta(days=365):
            raise ValueError('Callback cannot be scheduled more than 1 year in advance')
        return v

class CallbackResponse(BaseModel):
    """Response model for callback scheduling"""
    id: str = Field(..., description="Callback ID")
    lead_id: str = Field(..., description="Associated lead ID")
    lead_name: Optional[str] = Field(None, description="Lead name")
    scheduled_at: datetime = Field(..., description="Scheduled callback time")
    priority: CallPriority = Field(..., description="Callback priority")
    notes: Optional[str] = Field(None, description="Callback notes")
    assigned_to: Optional[str] = Field(None, description="Assigned user ID")
    assigned_to_name: Optional[str] = Field(None, description="Assigned user name")
    status: CallStatus = Field(default=CallStatus.INITIATED, description="Callback status")
    created_at: datetime = Field(..., description="Callback creation time")
    created_by: str = Field(..., description="User who scheduled callback")
    created_by_name: Optional[str] = Field(None, description="Name of user who scheduled")
    is_overdue: bool = Field(default=False, description="Whether callback is overdue")

class UpcomingCallbacksResponse(BaseModel):
    """Response model for upcoming callbacks list"""
    callbacks: List[CallbackResponse] = Field(..., description="List of upcoming callbacks")
    overdue_count: int = Field(..., description="Number of overdue callbacks")
    today_count: int = Field(..., description="Callbacks scheduled for today")
    this_week_count: int = Field(..., description="Callbacks scheduled for this week")
    total_count: int = Field(..., description="Total upcoming callbacks")

# ============================================================================
# TATA API RESPONSE MODELS
# ============================================================================

class TataCallResponse(BaseModel):
    """Response model from Tata Click-to-Call API"""
    success: bool = Field(..., description="Call initiation success status")
    message: Optional[str] = Field(None, description="Response message")
    call_id: Optional[str] = Field(None, description="Call ID if get_call_id was set to 1")
    error: Optional[str] = Field(None, description="Error message if call failed")

class TataSupportCallResponse(BaseModel):
    """Response model from Tata Support Call API"""
    success: bool = Field(..., description="Support call initiation success status")
    message: Optional[str] = Field(None, description="Response message")
    call_id: Optional[str] = Field(None, description="Call ID if requested")
    error: Optional[str] = Field(None, description="Error message if call failed")

# ============================================================================
# BULK OPERATIONS MODELS
# ============================================================================

class BulkCallRequest(BaseModel):
    """Model for bulk call operations"""
    lead_ids: List[str] = Field(..., min_items=1, max_items=50, description="List of lead IDs")
    call_type: CallType = Field(default=CallType.CLICK_TO_CALL, description="Type of calls")
    priority: CallPriority = Field(default=CallPriority.NORMAL, description="Call priority")
    scheduled_at: Optional[datetime] = Field(None, description="Schedule calls for later")
    notes: Optional[str] = Field(None, max_length=500, description="Notes for all calls")
    stagger_minutes: int = Field(default=0, ge=0, le=60, description="Minutes between calls")
    
    @validator('lead_ids')
    def validate_lead_ids(cls, v):
        for lead_id in v:
            if not re.match(r'^LD-\d+$', lead_id):
                raise ValueError(f'Invalid lead ID format: {lead_id}')
        return v

class BulkCallResponse(BaseModel):
    """Response model for bulk call operations"""
    total_requested: int = Field(..., description="Total calls requested")
    successful: int = Field(..., description="Successfully initiated calls")
    failed: int = Field(..., description="Failed call initiations")
    scheduled: int = Field(..., description="Scheduled calls")
    results: List[Dict[str, Any]] = Field(..., description="Individual call results")
    message: str = Field(..., description="Overall operation message")

# ============================================================================
# EXPORT AND REPORTING MODELS
# ============================================================================

class CallExportRequest(BaseModel):
    """Request model for exporting call data"""
    format: str = Field(..., description="Export format (csv, excel, pdf)")
    filter_params: Optional[CallHistoryFilter] = Field(None, description="Filter parameters")
    include_analytics: bool = Field(default=True, description="Include analytics in export")
    date_range_preset: Optional[str] = Field(None, description="Preset date range")
    
    @validator('format')
    def validate_format(cls, v):
        if v.lower() not in ['csv', 'excel', 'pdf']:
            raise ValueError('Export format must be csv, excel, or pdf')
        return v.lower()

class CallExportResponse(BaseModel):
    """Response model for call data export"""
    success: bool = Field(..., description="Export success status")
    download_url: Optional[str] = Field(None, description="Download URL for exported file")
    file_name: str = Field(..., description="Generated file name")
    record_count: int = Field(..., description="Number of records exported")
    file_size: Optional[str] = Field(None, description="File size in human readable format")
    expires_at: datetime = Field(..., description="Download link expiry time")
    message: str = Field(..., description="Export status message")

# ============================================================================
# SYSTEM HEALTH MODEL (Add this to your call_log.py)
# ============================================================================

class CallSystemHealth(BaseModel):
    """System health status for call functionality"""
    overall_status: str = Field(..., description="Overall system health status")
    tata_api_status: str = Field(..., description="Tata API connectivity status")
    call_service_status: str = Field(..., description="Call service status")
    database_status: str = Field(..., description="Database connectivity status")
    active_calls: int = Field(default=0, description="Currently active calls")
    calls_last_hour: int = Field(default=0, description="Calls made in last hour")
    success_rate_24h: float = Field(default=0.0, description="24-hour success rate percentage")
    average_response_time: float = Field(default=0.0, description="Average API response time")
    recent_errors: List[str] = Field(default=[], description="Recent error messages")
    system_alerts: List[str] = Field(default=[], description="Current system alerts")
    last_health_check: datetime = Field(default_factory=datetime.utcnow, description="Last health check timestamp")
    
    @validator('overall_status')
    def validate_overall_status(cls, v):
        allowed_statuses = ['healthy', 'degraded', 'unhealthy']
        if v not in allowed_statuses:
            raise ValueError(f'Overall status must be one of: {allowed_statuses}')
        return v
# MISSING RESPONSE MODELS (Add these to your call_log.py)

class ClickToCallResponse(BaseModel):
    """Response model for click-to-call initiation"""
    success: bool = Field(..., description="Call initiation success")
    message: str = Field(..., description="Response message")
    call_id: Optional[str] = Field(None, description="Internal call log ID")
    tata_call_id: Optional[str] = Field(None, description="Tata API call ID")
    call_status: str = Field(..., description="Current call status")
    estimated_connection_time: int = Field(..., description="Estimated connection time in seconds")
    initiated_at: datetime = Field(..., description="Call initiation timestamp")
    caller_number: Optional[str] = Field(None, description="Caller's number")
    destination_number: str = Field(..., description="Destination number")

class SupportCallResponse(BaseModel):
    """Response model for support call requests"""
    success: bool = Field(..., description="Support request success")
    message: str = Field(..., description="Response message")
    support_call_id: str = Field(..., description="Support call ID")
    ticket_number: Optional[str] = Field(None, description="Support ticket number")
    priority: str = Field(..., description="Assigned priority")
    estimated_callback_time: int = Field(..., description="Estimated callback time in seconds")
    support_agent_info: Optional[Dict[str, Any]] = Field(None, description="Assigned support agent info")
    submitted_at: datetime = Field(..., description="Support request timestamp")

class CallPermissionResponse(BaseModel):
    """Response model for call permissions check"""
    user_id: str = Field(..., description="User ID")
    can_make_calls: bool = Field(..., description="Whether user can make calls")
    has_tata_mapping: bool = Field(..., description="Whether user has Tata mapping")
    tata_agent_id: Optional[str] = Field(None, description="Tata agent ID if mapped")
    call_limit_remaining: Optional[int] = Field(None, description="Remaining call limit")
    daily_call_count: int = Field(default=0, description="Calls made today")
    permission_errors: List[str] = Field(default=[], description="Permission error messages")
    last_call_time: Optional[datetime] = Field(None, description="Last call timestamp")
    checked_at: datetime = Field(..., description="Permission check timestamp")

class CallWebhookPayload(BaseModel):
    """Webhook payload from Tata Tele API"""
    event_type: str = Field(..., description="Type of webhook event")
    call_id: str = Field(..., description="Call ID from Tata")
    status: Optional[str] = Field(None, description="Call status")
    timestamp: datetime = Field(..., description="Event timestamp")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional event data")
# Add this to your call_log.py file

class CallLogListResponse(BaseModel):
    """Response model for call log lists with pagination"""
    calls: List[CallLogResponse] = Field(..., description="List of call logs")
    total_count: int = Field(..., description="Total number of calls matching filter")
    limit: int = Field(..., description="Records per page")
    offset: int = Field(..., description="Number of records skipped")
    has_more: bool = Field(..., description="Whether there are more records")
    filters_applied: Dict[str, Any] = Field(..., description="Applied filters")
    retrieved_at: datetime = Field(..., description="Data retrieval timestamp")