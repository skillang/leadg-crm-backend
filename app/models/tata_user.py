# app/models/tata_user.py
# User Mapping Models for LeadG CRM and Tata Tele Integration
# Handles synchronization and mapping between CRM users and Tata agents

from pydantic import BaseModel, EmailStr, Field, validator, root_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import re

# ============================================================================
# ENUMS FOR USER MAPPING
# ============================================================================

class SyncStatus(str, Enum):
    """Synchronization status between CRM and Tata"""
    PENDING = "pending"              # Sync not yet attempted
    SYNCED = "synced"               # Successfully synchronized
    FAILED = "failed"               # Sync failed
    PARTIAL = "partial"             # Partially synchronized
    CONFLICT = "conflict"           # Data conflicts detected
    DISABLED = "disabled"           # Sync disabled for this user

class TataUserType(str, Enum):
    """Types of users in Tata Tele system"""
    AGENT = "agent"                 # Regular agent
    SUPERVISOR = "supervisor"       # Team supervisor
    ADMIN = "admin"                # System administrator
    MANAGER = "manager"            # Manager role

class UserStatus(str, Enum):
    """User status in both systems"""
    ACTIVE = "active"              # User is active and available
    INACTIVE = "inactive"          # User is inactive
    BLOCKED = "blocked"            # User is blocked
    SUSPENDED = "suspended"        # User is temporarily suspended

class RouteCallThrough(int, Enum):
    """Call routing preferences from Tata API"""
    ONLY_AGENT = 0                 # Route only through agent
    ONLY_EXTENSION = 1             # Route only through extension
    BOTH = 2                       # Route through both

# ============================================================================
# CRM USER MODELS (EXTENDED)
# ============================================================================

class CRMUserProfile(BaseModel):
    """Extended CRM user profile for Tata integration"""
    user_id: str = Field(..., description="CRM user database ID")
    email: EmailStr = Field(..., description="User email address")
    full_name: str = Field(..., description="User full name")
    phone_number: Optional[str] = Field(None, description="User primary phone number")
    role: str = Field(..., description="CRM user role (admin/user)")
    department: Optional[str] = Field(None, description="User department")
    designation: Optional[str] = Field(None, description="User job designation")
    is_active: bool = Field(default=True, description="Whether user is active in CRM")
    created_at: datetime = Field(..., description="CRM account creation date")
    last_login: Optional[datetime] = Field(None, description="Last CRM login timestamp")

    @validator('phone_number')
    def validate_phone_number(cls, v):
        if v is not None:
            cleaned = re.sub(r'[^\d+]', '', v)
            if not re.match(r'^\+?[1-9]\d{1,14}$', cleaned):
                raise ValueError('Invalid phone number format')
        return v

# ============================================================================
# TATA USER MAPPING MODELS
# ============================================================================

class TataUserMapping(BaseModel):
    """Core model for mapping CRM users to Tata users"""
    id: Optional[str] = Field(None, description="Mapping record ID")
    crm_user_id: str = Field(..., description="CRM user ID")
    tata_user_id: Optional[str] = Field(None, description="Tata user ID")
    tata_agent_id: Optional[str] = Field(None, description="Tata agent ID")
    tata_login_id: Optional[str] = Field(None, description="Tata login ID")
    tata_email: Optional[EmailStr] = Field(None, description="Email used in Tata system")
    tata_phone: Optional[str] = Field(None, description="Phone number in Tata system")
    tata_extension: Optional[str] = Field(None, description="Tata extension number")
    
    # Sync status and metadata
    sync_status: SyncStatus = Field(default=SyncStatus.PENDING, description="Current sync status")
    last_synced: Optional[datetime] = Field(None, description="Last successful sync timestamp")
    sync_attempts: int = Field(default=0, description="Number of sync attempts")
    last_sync_error: Optional[str] = Field(None, description="Last sync error message")
    
    # Tata-specific configuration
    tata_user_type: Optional[TataUserType] = Field(None, description="User type in Tata system")
    tata_role_id: Optional[int] = Field(None, description="Tata role ID")
    tata_role_name: Optional[str] = Field(None, description="Tata role name")
    is_login_based_calling: bool = Field(default=True, description="Login-based calling enabled")
    is_international_outbound: bool = Field(default=False, description="International calling enabled")
    is_web_login_blocked: bool = Field(default=False, description="Web login blocked status")
    route_call_through: Optional[RouteCallThrough] = Field(None, description="Call routing preference")
    
    # Agent-specific fields
    agent_intercom: Optional[int] = Field(None, description="Agent intercom number")
    agent_status: Optional[int] = Field(None, description="Agent status code")
    is_outbound_blocked: bool = Field(default=False, description="Outbound calling blocked")
    time_group_id: Optional[int] = Field(None, description="Assigned time group ID")
    time_group_name: Optional[str] = Field(None, description="Time group name")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Mapping creation time")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update time")
    
    # Status flags
    is_active: bool = Field(default=True, description="Whether mapping is active")
    auto_sync_enabled: bool = Field(default=True, description="Whether auto-sync is enabled")

    class Config:
        json_schema_extra = {
            "example": {
                "crm_user_id": "507f1f77bcf86cd799439011",
                "tata_user_id": "288256",
                "tata_agent_id": "0502842370002",
                "tata_login_id": "john_smith",
                "tata_email": "john.smith@company.com",
                "tata_phone": "+919999999999",
                "tata_extension": "0602842370077",
                "sync_status": "synced",
                "last_synced": "2024-01-15T10:30:00Z",
                "tata_user_type": "agent",
                "tata_role_id": 54742,
                "tata_role_name": "Sales Agent",
                "is_login_based_calling": True,
                "agent_intercom": 1002,
                "agent_status": 0
            }
        }

class TataUserMappingCreate(BaseModel):
    """Model for creating new user mapping"""
    crm_user_id: str = Field(..., description="CRM user ID to map")
    tata_email: Optional[EmailStr] = Field(None, description="Email to use in Tata (defaults to CRM email)")
    tata_login_id: Optional[str] = Field(None, description="Login ID for Tata (auto-generated if not provided)")
    tata_phone: Optional[str] = Field(None, description="Phone number for Tata user")
    designation: Optional[str] = Field(None, description="Job designation")
    department: Optional[str] = Field(None, description="Department assignment")
    tata_role_id: Optional[int] = Field(None, description="Tata role ID to assign")
    auto_create_agent: bool = Field(default=True, description="Whether to create agent in Tata")
    enable_extension: bool = Field(default=True, description="Whether to assign extension")
    caller_ids: Optional[List[int]] = Field(None, description="Caller IDs to assign")
    
    @validator('tata_login_id')
    def validate_login_id(cls, v):
        if v is not None:
            if not re.match(r'^[a-zA-Z0-9_]{3,20}$', v):
                raise ValueError('Login ID must be 3-20 characters, alphanumeric and underscore only')
        return v

class TataUserMappingUpdate(BaseModel):
    """Model for updating existing user mapping"""
    tata_email: Optional[EmailStr] = Field(None, description="Update Tata email")
    tata_phone: Optional[str] = Field(None, description="Update Tata phone")
    designation: Optional[str] = Field(None, description="Update designation")
    tata_role_id: Optional[int] = Field(None, description="Update Tata role")
    is_login_based_calling: Optional[bool] = Field(None, description="Update calling preference")
    is_international_outbound: Optional[bool] = Field(None, description="Update international calling")
    is_web_login_blocked: Optional[bool] = Field(None, description="Update web login status")
    auto_sync_enabled: Optional[bool] = Field(None, description="Update auto-sync preference")
    time_group_id: Optional[int] = Field(None, description="Update time group assignment")
    
class TataUserMappingResponse(BaseModel):
    """Response model for user mapping with enriched data"""
    id: str = Field(..., description="Mapping record ID")
    
    # CRM user data
    crm_user_id: str = Field(..., description="CRM user ID")
    crm_user_name: Optional[str] = Field(None, description="CRM user full name")
    crm_user_email: Optional[str] = Field(None, description="CRM user email")
    crm_user_role: Optional[str] = Field(None, description="CRM user role")
    
    # Tata user data
    tata_user_id: Optional[str] = Field(None, description="Tata user ID")
    tata_agent_id: Optional[str] = Field(None, description="Tata agent ID")
    tata_login_id: Optional[str] = Field(None, description="Tata login ID")
    tata_email: Optional[str] = Field(None, description="Tata email")
    tata_phone: Optional[str] = Field(None, description="Tata phone")
    tata_extension: Optional[str] = Field(None, description="Tata extension")
    
    # Status and configuration
    sync_status: SyncStatus = Field(..., description="Current sync status")
    last_synced: Optional[datetime] = Field(None, description="Last sync timestamp")
    sync_attempts: int = Field(..., description="Number of sync attempts")
    last_sync_error: Optional[str] = Field(None, description="Last error message")
    
    # Tata configuration
    tata_user_type: Optional[str] = Field(None, description="Tata user type")
    tata_role_name: Optional[str] = Field(None, description="Tata role name")
    is_login_based_calling: bool = Field(..., description="Login-based calling status")
    is_international_outbound: bool = Field(..., description="International calling status")
    agent_status: Optional[int] = Field(None, description="Agent status code")
    agent_status_text: Optional[str] = Field(None, description="Agent status description")
    
    # Timestamps
    created_at: datetime = Field(..., description="Mapping creation time")
    updated_at: datetime = Field(..., description="Last update time")
    
    # Flags
    is_active: bool = Field(..., description="Whether mapping is active")
    auto_sync_enabled: bool = Field(..., description="Auto-sync enabled status")
    can_make_calls: bool = Field(..., description="Whether user can make calls")

# ============================================================================
# BULK OPERATIONS MODELS
# ============================================================================

class BulkUserSyncRequest(BaseModel):
    """Request model for bulk user synchronization"""
    user_ids: Optional[List[str]] = Field(None, description="Specific user IDs to sync (all if empty)")
    force_sync: bool = Field(default=False, description="Force sync even if already synced")
    create_missing_agents: bool = Field(default=True, description="Create agents in Tata if missing")
    update_existing: bool = Field(default=True, description="Update existing Tata users")
    sync_configuration: Optional[Dict[str, Any]] = Field(None, description="Default sync configuration")
    
    @validator('user_ids')
    def validate_user_ids(cls, v):
        if v is not None and len(v) > 50:
            raise ValueError('Cannot sync more than 50 users at once')
        return v

class UserSyncResult(BaseModel):
    """Individual user sync result"""
    crm_user_id: str = Field(..., description="CRM user ID")
    user_name: Optional[str] = Field(None, description="User name")
    sync_status: SyncStatus = Field(..., description="Sync result status")
    tata_user_id: Optional[str] = Field(None, description="Tata user ID (if successful)")
    tata_agent_id: Optional[str] = Field(None, description="Tata agent ID (if successful)")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    actions_taken: List[str] = Field(default_factory=list, description="Actions performed during sync")
    sync_duration: Optional[float] = Field(None, description="Sync duration in seconds")

class BulkUserSyncResponse(BaseModel):
    """Response model for bulk user synchronization"""
    total_requested: int = Field(..., description="Total users requested for sync")
    successful: int = Field(..., description="Successfully synced users")
    failed: int = Field(..., description="Failed sync attempts")
    skipped: int = Field(..., description="Skipped users")
    created_new: int = Field(..., description="New Tata users created")
    updated_existing: int = Field(..., description="Existing Tata users updated")
    
    results: List[UserSyncResult] = Field(..., description="Individual sync results")
    summary_message: str = Field(..., description="Overall operation summary")
    started_at: datetime = Field(..., description="Sync operation start time")
    completed_at: datetime = Field(..., description="Sync operation completion time")
    total_duration: float = Field(..., description="Total operation duration in seconds")

# ============================================================================
# USER SYNC STATISTICS AND REPORTING
# ============================================================================

class UserSyncStatistics(BaseModel):
    """Statistics for user synchronization"""
    total_crm_users: int = Field(..., description="Total users in CRM")
    total_mappings: int = Field(..., description="Total user mappings")
    synced_users: int = Field(..., description="Successfully synced users")
    pending_sync: int = Field(..., description="Users pending sync")
    failed_sync: int = Field(..., description="Users with failed sync")
    disabled_sync: int = Field(..., description="Users with disabled sync")
    
    # Tata system stats
    total_tata_users: int = Field(default=0, description="Total users in Tata system")
    active_agents: int = Field(default=0, description="Active agents in Tata")
    inactive_agents: int = Field(default=0, description="Inactive agents in Tata")
    
    # Performance metrics
    sync_success_rate: float = Field(..., description="Overall sync success rate percentage")
    average_sync_time: Optional[float] = Field(None, description="Average sync time per user")
    last_bulk_sync: Optional[datetime] = Field(None, description="Last bulk sync timestamp")
    next_scheduled_sync: Optional[datetime] = Field(None, description="Next scheduled sync")
    
    # Recent activity
    syncs_last_24h: int = Field(default=0, description="Syncs in last 24 hours")
    syncs_last_week: int = Field(default=0, description="Syncs in last week")
    errors_last_24h: int = Field(default=0, description="Sync errors in last 24 hours")

class UserMappingListResponse(BaseModel):
    """Response model for user mapping list with pagination"""
    mappings: List[TataUserMappingResponse] = Field(..., description="List of user mappings")
    total_count: int = Field(..., description="Total number of mappings")
    page: int = Field(..., description="Current page number")
    limit: int = Field(..., description="Records per page")
    total_pages: int = Field(..., description="Total number of pages")
    has_more: bool = Field(..., description="Whether there are more pages")
    statistics: Optional[UserSyncStatistics] = Field(None, description="Sync statistics")

# ============================================================================
# FILTER AND SEARCH MODELS
# ============================================================================

class UserMappingFilter(BaseModel):
    """Filter parameters for user mapping queries"""
    sync_status: Optional[SyncStatus] = Field(None, description="Filter by sync status")
    tata_user_type: Optional[TataUserType] = Field(None, description="Filter by Tata user type")
    is_active: Optional[bool] = Field(None, description="Filter by active status")
    auto_sync_enabled: Optional[bool] = Field(None, description="Filter by auto-sync status")
    has_tata_user: Optional[bool] = Field(None, description="Filter by Tata user existence")
    has_agent: Optional[bool] = Field(None, description="Filter by agent existence")
    has_extension: Optional[bool] = Field(None, description="Filter by extension existence")
    
    # Date filters
    created_after: Optional[datetime] = Field(None, description="Filter mappings created after date")
    created_before: Optional[datetime] = Field(None, description="Filter mappings created before date")
    synced_after: Optional[datetime] = Field(None, description="Filter by last sync date")
    
    # Search
    search_query: Optional[str] = Field(None, description="Search in names, emails, login IDs")
    
    # Pagination and sorting
    page: int = Field(default=1, ge=1, description="Page number")
    limit: int = Field(default=20, ge=1, le=100, description="Records per page")
    sort_by: str = Field(default="created_at", description="Sort field")
    sort_order: str = Field(default="desc", description="Sort order (asc/desc)")
    
    @validator('sort_by')
    def validate_sort_by(cls, v):
        allowed_fields = [
            'created_at', 'updated_at', 'last_synced', 'sync_status', 
            'crm_user_name', 'tata_email', 'sync_attempts'
        ]
        if v not in allowed_fields:
            raise ValueError(f'sort_by must be one of: {allowed_fields}')
        return v

# ============================================================================
# ERROR AND VALIDATION MODELS
# ============================================================================

class UserSyncError(BaseModel):
    """Model for user sync error details"""
    error_code: str = Field(..., description="Error code")
    error_message: str = Field(..., description="Human-readable error message")
    error_type: str = Field(..., description="Type of error (validation, api, network, etc.)")
    field_errors: Optional[Dict[str, str]] = Field(None, description="Field-specific errors")
    suggested_action: Optional[str] = Field(None, description="Suggested action to resolve error")
    retry_allowed: bool = Field(..., description="Whether retry is allowed for this error")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

class UserValidationResult(BaseModel):
    """Model for user data validation results"""
    is_valid: bool = Field(..., description="Whether user data is valid for sync")
    crm_user_id: str = Field(..., description="CRM user ID being validated")
    validation_errors: List[str] = Field(default_factory=list, description="List of validation errors")
    validation_warnings: List[str] = Field(default_factory=list, description="List of validation warnings")
    required_fields: List[str] = Field(default_factory=list, description="Missing required fields")
    suggested_values: Optional[Dict[str, str]] = Field(None, description="Suggested values for missing fields")
    can_auto_fix: bool = Field(default=False, description="Whether issues can be auto-fixed")

# ============================================================================
# CONFIGURATION AND SETTINGS MODELS
# ============================================================================

class TataUserSyncConfig(BaseModel):
    """Configuration model for user synchronization"""
    auto_sync_enabled: bool = Field(default=True, description="Enable automatic synchronization")
    sync_interval_hours: int = Field(default=24, ge=1, le=168, description="Sync interval in hours")
    
    # Default user creation settings
    default_create_agent: bool = Field(default=True, description="Create agent by default")
    default_assign_extension: bool = Field(default=True, description="Assign extension by default")
    default_enable_calling: bool = Field(default=True, description="Enable calling by default")
    default_tata_role_id: Optional[int] = Field(None, description="Default Tata role ID")
    
    # Sync behavior settings
    update_existing_users: bool = Field(default=True, description="Update existing Tata users")
    skip_inactive_users: bool = Field(default=True, description="Skip inactive CRM users")
    max_sync_batch_size: int = Field(default=10, ge=1, le=50, description="Maximum users per sync batch")
    sync_retry_attempts: int = Field(default=3, ge=1, le=10, description="Number of retry attempts")
    sync_retry_delay_minutes: int = Field(default=5, ge=1, le=60, description="Delay between retries")
    
    # Validation settings
    require_phone_number: bool = Field(default=True, description="Require phone number for sync")
    require_department: bool = Field(default=False, description="Require department for sync")
    validate_email_domain: bool = Field(default=False, description="Validate email domain")
    allowed_email_domains: Optional[List[str]] = Field(None, description="Allowed email domains")
    
    # Notification settings
    notify_on_sync_completion: bool = Field(default=True, description="Send notifications on sync completion")
    notify_on_sync_errors: bool = Field(default=True, description="Send notifications on sync errors")
    notification_email: Optional[EmailStr] = Field(None, description="Email for sync notifications")
    
    @validator('sync_interval_hours')
    def validate_sync_interval(cls, v):
        if v < 1 or v > 168:  # 1 hour to 1 week
            raise ValueError('Sync interval must be between 1 and 168 hours')
        return v

class TataIntegrationSettings(BaseModel):
    """Overall integration settings model"""
    integration_enabled: bool = Field(default=True, description="Whether integration is enabled")
    api_base_url: str = Field(..., description="Tata API base URL")
    api_timeout_seconds: int = Field(default=30, ge=5, le=300, description="API timeout in seconds")
    api_retry_attempts: int = Field(default=3, ge=1, le=10, description="API retry attempts")
    
    # Authentication settings
    token_refresh_threshold_minutes: int = Field(default=5, description="Refresh token before expiry")
    auto_login_on_startup: bool = Field(default=True, description="Auto-login on system startup")
    store_credentials_encrypted: bool = Field(default=True, description="Encrypt stored credentials")
    
    # User sync settings
    user_sync_config: TataUserSyncConfig = Field(..., description="User synchronization configuration")
    
    # Call integration settings
    enable_click_to_call: bool = Field(default=True, description="Enable click-to-call feature")
    enable_call_logging: bool = Field(default=True, description="Enable automatic call logging")
    default_call_timeout: int = Field(default=300, ge=30, le=3600, description="Default call timeout")
    auto_log_activities: bool = Field(default=True, description="Auto-log call activities to lead timeline")
    
    # Health monitoring
    health_check_interval_minutes: int = Field(default=15, description="Health check interval")
    alert_on_integration_failure: bool = Field(default=True, description="Alert on integration failures")
    max_consecutive_failures: int = Field(default=5, description="Max failures before alerting")
    
    # Data retention
    retain_call_logs_days: int = Field(default=365, description="Call log retention period in days")
    retain_sync_logs_days: int = Field(default=90, description="Sync log retention period in days")
    cleanup_old_data: bool = Field(default=True, description="Enable automatic data cleanup")

# ============================================================================
# AUDIT AND LOGGING MODELS
# ============================================================================

class UserSyncAuditLog(BaseModel):
    """Audit log model for user sync operations"""
    id: Optional[str] = Field(None, description="Audit log ID")
    operation_type: str = Field(..., description="Type of operation (create, update, sync, delete)")
    crm_user_id: str = Field(..., description="CRM user ID")
    tata_user_id: Optional[str] = Field(None, description="Tata user ID")
    
    # Operation details
    operation_status: str = Field(..., description="Operation status (success, failure, partial)")
    initiated_by: str = Field(..., description="User who initiated the operation")
    changes_made: Optional[Dict[str, Any]] = Field(None, description="Changes made during operation")
    previous_values: Optional[Dict[str, Any]] = Field(None, description="Previous values before changes")
    
    # Metadata
    operation_duration: Optional[float] = Field(None, description="Operation duration in seconds")
    error_details: Optional[str] = Field(None, description="Error details if operation failed")
    api_calls_made: int = Field(default=0, description="Number of API calls made")
    retry_count: int = Field(default=0, description="Number of retries attempted")
    
    # Timestamps
    started_at: datetime = Field(..., description="Operation start time")
    completed_at: Optional[datetime] = Field(None, description="Operation completion time")
    
    # Context
    ip_address: Optional[str] = Field(None, description="IP address of requester")
    user_agent: Optional[str] = Field(None, description="User agent of requester")
    session_id: Optional[str] = Field(None, description="Session ID")

class UserSyncReport(BaseModel):
    """Comprehensive user sync report model"""
    report_id: str = Field(..., description="Unique report ID")
    report_type: str = Field(..., description="Type of report (daily, weekly, monthly, custom)")
    generated_at: datetime = Field(..., description="Report generation timestamp")
    generated_by: str = Field(..., description="User who generated the report")
    
    # Report period
    period_start: datetime = Field(..., description="Report period start")
    period_end: datetime = Field(..., description="Report period end")
    
    # Summary statistics
    total_sync_operations: int = Field(..., description="Total sync operations in period")
    successful_syncs: int = Field(..., description="Successful sync operations")
    failed_syncs: int = Field(..., description="Failed sync operations")
    new_mappings_created: int = Field(..., description="New user mappings created")
    existing_mappings_updated: int = Field(..., description="Existing mappings updated")
    
    # Performance metrics
    average_sync_duration: float = Field(..., description="Average sync duration in seconds")
    total_api_calls: int = Field(..., description="Total API calls made")
    api_success_rate: float = Field(..., description="API success rate percentage")
    
    # Error analysis
    common_errors: List[Dict[str, Any]] = Field(..., description="Most common errors and their frequency")
    error_trends: List[Dict[str, Any]] = Field(..., description="Error trends over time")
    
    # Recommendations
    recommendations: List[str] = Field(default_factory=list, description="System recommendations")
    action_items: List[str] = Field(default_factory=list, description="Suggested action items")
    
    # Detailed data
    daily_breakdown: List[Dict[str, Any]] = Field(..., description="Daily breakdown of sync activities")
    user_activity: List[Dict[str, Any]] = Field(..., description="Per-user sync activity")
    
    # Health indicators
    system_health_score: float = Field(..., ge=0, le=100, description="Overall system health score")
    integration_stability: str = Field(..., description="Integration stability rating")

# ============================================================================
# EXPORT AND IMPORT MODELS
# ============================================================================

class UserMappingExportRequest(BaseModel):
    """Request model for exporting user mapping data"""
    export_format: str = Field(..., description="Export format (csv, excel, json)")
    include_inactive: bool = Field(default=False, description="Include inactive mappings")
    include_sensitive_data: bool = Field(default=False, description="Include sensitive data (requires admin)")
    filter_params: Optional[UserMappingFilter] = Field(None, description="Filter parameters")
    custom_fields: Optional[List[str]] = Field(None, description="Custom fields to include")
    
    @validator('export_format')
    def validate_export_format(cls, v):
        if v.lower() not in ['csv', 'excel', 'json']:
            raise ValueError('Export format must be csv, excel, or json')
        return v.lower()

class UserMappingImportRequest(BaseModel):
    """Request model for importing user mapping data"""
    import_format: str = Field(..., description="Import format (csv, excel, json)")
    file_data: str = Field(..., description="Base64 encoded file data")
    update_existing: bool = Field(default=True, description="Update existing mappings")
    create_missing_users: bool = Field(default=False, description="Create missing CRM users")
    validate_only: bool = Field(default=False, description="Only validate, don't import")
    mapping_options: Optional[Dict[str, str]] = Field(None, description="Field mapping options")

class UserMappingImportResult(BaseModel):
    """Result model for user mapping import operation"""
    total_records: int = Field(..., description="Total records in import file")
    processed_records: int = Field(..., description="Successfully processed records")
    created_mappings: int = Field(..., description="New mappings created")
    updated_mappings: int = Field(..., description="Existing mappings updated")
    skipped_records: int = Field(..., description="Records skipped")
    error_records: int = Field(..., description="Records with errors")
    
    validation_errors: List[Dict[str, Any]] = Field(..., description="Validation errors")
    processing_errors: List[Dict[str, Any]] = Field(..., description="Processing errors")
    
    success_rate: float = Field(..., description="Import success rate percentage")
    import_duration: float = Field(..., description="Import duration in seconds")
    
    summary_message: str = Field(..., description="Import operation summary")

# ============================================================================
# WEBHOOK AND NOTIFICATION MODELS
# ============================================================================

class UserSyncWebhookPayload(BaseModel):
    """Webhook payload for user sync events"""
    event_type: str = Field(..., description="Type of sync event")
    event_id: str = Field(..., description="Unique event ID")
    timestamp: datetime = Field(..., description="Event timestamp")
    
    # User information
    crm_user_id: str = Field(..., description="CRM user ID")
    tata_user_id: Optional[str] = Field(None, description="Tata user ID")
    user_email: Optional[str] = Field(None, description="User email")
    
    # Event details
    sync_status: SyncStatus = Field(..., description="Sync status")
    previous_status: Optional[SyncStatus] = Field(None, description="Previous sync status")
    changes_made: Optional[List[str]] = Field(None, description="List of changes made")
    error_message: Optional[str] = Field(None, description="Error message if applicable")
    
    # Metadata
    operation_duration: Optional[float] = Field(None, description="Operation duration")
    retry_count: int = Field(default=0, description="Number of retries")
    
class UserSyncNotification(BaseModel):
    """Notification model for user sync events"""
    notification_id: str = Field(..., description="Unique notification ID")
    notification_type: str = Field(..., description="Type of notification")
    priority: str = Field(..., description="Notification priority (low, normal, high, urgent)")
    
    # Content
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional notification details")
    
    # Recipients
    recipients: List[str] = Field(..., description="List of recipient user IDs or emails")
    channels: List[str] = Field(..., description="Notification channels (email, sms, in-app)")
    
    # Timing
    created_at: datetime = Field(..., description="Notification creation time")
    scheduled_at: Optional[datetime] = Field(None, description="Scheduled delivery time")
    sent_at: Optional[datetime] = Field(None, description="Actual sent time")
    expires_at: Optional[datetime] = Field(None, description="Notification expiry time")
    
    # Status
    status: str = Field(default="pending", description="Notification status")
    delivery_attempts: int = Field(default=0, description="Number of delivery attempts")
    delivery_errors: Optional[List[str]] = Field(None, description="Delivery error messages")
    
    # Actions
    action_buttons: Optional[List[Dict[str, str]]] = Field(None, description="Action buttons for notification")
    callback_url: Optional[str] = Field(None, description="Callback URL for actions")

# ============================================================================
# HEALTH AND MONITORING MODELS
# ============================================================================

class UserSyncHealthCheck(BaseModel):
    """Health check model for user synchronization system"""
    overall_status: str = Field(..., description="Overall health status (healthy, degraded, unhealthy)")
    timestamp: datetime = Field(..., description="Health check timestamp")
    
    # Component health
    tata_api_health: str = Field(..., description="Tata API connectivity health")
    database_health: str = Field(..., description="Database connectivity health")
    sync_service_health: str = Field(..., description="Sync service health")
    
    # Performance metrics
    active_sync_operations: int = Field(..., description="Currently active sync operations")
    pending_sync_queue: int = Field(..., description="Number of pending sync operations")
    average_response_time: float = Field(..., description="Average API response time in milliseconds")
    error_rate_24h: float = Field(..., description="Error rate in last 24 hours")
    
    # Recent activity
    successful_syncs_1h: int = Field(..., description="Successful syncs in last hour")
    failed_syncs_1h: int = Field(..., description="Failed syncs in last hour")
    last_successful_sync: Optional[datetime] = Field(None, description="Last successful sync timestamp")
    last_failed_sync: Optional[datetime] = Field(None, description="Last failed sync timestamp")
    
    # System resources
    memory_usage_percent: Optional[float] = Field(None, description="Memory usage percentage")
    cpu_usage_percent: Optional[float] = Field(None, description="CPU usage percentage")
    disk_usage_percent: Optional[float] = Field(None, description="Disk usage percentage")
    
    # Alerts and warnings
    active_alerts: List[str] = Field(default_factory=list, description="Active system alerts")
    warnings: List[str] = Field(default_factory=list, description="System warnings")
    recommendations: List[str] = Field(default_factory=list, description="Performance recommendations")
    
    # Uptime and availability
    uptime_seconds: int = Field(..., description="System uptime in seconds")
    availability_24h: float = Field(..., description="System availability in last 24 hours")
    last_downtime: Optional[datetime] = Field(None, description="Last downtime occurrence")

# ============================================================================
# INTEGRATION TEST MODELS
# ============================================================================

class UserSyncTestRequest(BaseModel):
    """Request model for testing user sync functionality"""
    test_type: str = Field(..., description="Type of test to perform")
    test_user_id: Optional[str] = Field(None, description="Specific user ID to test")
    mock_data: Optional[Dict[str, Any]] = Field(None, description="Mock data for testing")
    skip_actual_api_calls: bool = Field(default=True, description="Skip actual API calls during test")
    
    @validator('test_type')
    def validate_test_type(cls, v):
        allowed_types = ['connectivity', 'authentication', 'user_creation', 'user_update', 'full_sync']
        if v not in allowed_types:
            raise ValueError(f'Test type must be one of: {allowed_types}')
        return v

class UserSyncTestResult(BaseModel):
    """Result model for user sync testing"""
    test_type: str = Field(..., description="Type of test performed")
    test_status: str = Field(..., description="Test result status (passed, failed, warning)")
    test_duration: float = Field(..., description="Test duration in seconds")
    
    # Test results
    passed_checks: List[str] = Field(..., description="List of passed test checks")
    failed_checks: List[str] = Field(..., description="List of failed test checks")
    warnings: List[str] = Field(default_factory=list, description="Test warnings")
    
    # Detailed results
    api_connectivity: bool = Field(..., description="API connectivity test result")
    authentication_test: bool = Field(..., description="Authentication test result")
    data_validation: bool = Field(..., description="Data validation test result")
    
    # Performance metrics
    api_response_times: List[float] = Field(..., description="API response times during test")
    memory_usage: Optional[float] = Field(None, description="Memory usage during test")
    
    # Recommendations
    issues_found: List[str] = Field(default_factory=list, description="Issues found during testing")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations for improvement")
    
    # Test metadata
    test_timestamp: datetime = Field(..., description="Test execution timestamp")
    test_environment: str = Field(..., description="Test environment information")
    tester_id: Optional[str] = Field(None, description="ID of user who ran the test")