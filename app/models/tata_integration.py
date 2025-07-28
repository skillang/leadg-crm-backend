# app/models/tata_integration.py
# Tata Tele Authentication and Integration Models
# Following LeadG CRM patterns and Tata Tele API specifications

from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

# ============================================================================
# ENUMS FOR TATA TELE INTEGRATION
# ============================================================================

class TataTokenType(str, Enum):
    """Token types supported by Tata Tele API"""
    BEARER = "bearer"

class TataUserStatus(str, Enum):
    """User status in Tata Tele system"""
    ENABLED = "enabled"   # Status = 1
    BLOCKED = "blocked"   # Status = 0

class TataAgentStatus(int, Enum):
    """Agent status codes from Tata Tele API"""
    ENABLED = 0
    BLOCKED = 1
    DISABLED = 2
    BUSY = 3
    OFFLINE = 4

class IntegrationStatus(str, Enum):
    """Integration status between CRM and Tata"""
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
    DISCONNECTED = "disconnected"

# ============================================================================
# TATA AUTHENTICATION REQUEST/RESPONSE MODELS
# ============================================================================

class TataLoginRequest(BaseModel):
    """Request model for Tata Tele login"""
    email: str = Field(..., description="Tata Tele login ID or email")  # ← Fixed: str instead of EmailStr
    password: str = Field(..., min_length=6, description="Tata Tele password")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@company.com",
                "password": "secure_password"
            }
        }

class TataLoginResponse(BaseModel):
    """Response model for successful Tata Tele login"""
    success: bool = Field(..., description="Login success status")
    access_token: str = Field(..., description="JWT access token from Tata")
    token_type: TataTokenType = Field(default=TataTokenType.BEARER, description="Token type")
    expires_in: int = Field(..., description="Token expiry time in seconds")
    number_of_days_left: Optional[int] = Field(None, description="Days until password expires")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "access_token": "eyJ0eXAiOiJKV1XXXXXXXXXXXXy_geJMxZywZb9v6M0igZkKTuys8",
                "token_type": "bearer",
                "expires_in": 3600,
                "number_of_days_left": 30
            }
        }

class TataLoginFailedResponse(BaseModel):
    """Response model for failed Tata Tele login"""
    success: bool = Field(default=False, description="Login failure status")
    message: str = Field(..., description="Error message")
    login_failed_count: Optional[int] = Field(None, description="Number of failed attempts")

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "message": "The username or password is incorrect.",
                "login_failed_count": 1
            }
        }

class TataRefreshTokenResponse(BaseModel):
    """Response model for Tata token refresh"""
    success: bool = Field(..., description="Refresh success status")
    access_token: str = Field(..., description="New JWT access token")
    token_type: TataTokenType = Field(default=TataTokenType.BEARER)
    expires_in: int = Field(..., description="Token expiry time in seconds")
    number_of_days_left: int = Field(..., description="Days until password expires")

class TataLogoutResponse(BaseModel):
    """Response model for Tata logout"""
    success: bool = Field(..., description="Logout success status")
    message: str = Field(..., description="Logout message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Successfully logged out"
            }
        }

# ============================================================================
# TATA USER DATA MODELS (FROM TATA API)
# ============================================================================

class TataUserRole(BaseModel):
    """User role in Tata Tele system"""
    id: int = Field(..., description="Role ID")
    name: str = Field(..., description="Role name")

class TataExtension(BaseModel):
    """Tata user extension details"""
    username: str = Field(..., description="Extension username")
    outbound_block: bool = Field(..., description="Whether outbound calling is blocked")

class TataTimeGroup(BaseModel):
    """Time group assignment for Tata user"""
    id: int = Field(..., description="Time group ID")
    name: str = Field(..., description="Time group name")

class TataFailoverDestination(BaseModel):
    """Failover destination configuration"""
    id: str = Field(..., description="Failover destination ID")
    name: str = Field(..., description="Failover destination name")
    type: str = Field(..., description="Destination type (agent, department, etc.)")

class TataUsersForCDR(BaseModel):
    """CDR view configuration"""
    type: str = Field(..., description="Type of users for CDR view (all, none, user)")
    value: Optional[str] = Field(None, description="Value of users selected for CDR view")

class TataTeamMember(BaseModel):
    """Team member details from Tata API"""
    designation: Optional[str] = Field(None, description="User designation")
    email: EmailStr = Field(..., description="Team member email")
    login_id: str = Field(..., description="Login ID for team member")
    status: int = Field(..., description="Team member status (0=BLOCK, 1=UNBLOCK)")
    role: TataUserRole = Field(..., description="User role information")
    is_login_based_calling: bool = Field(..., description="Login-based calling enabled")
    is_web_login_block: bool = Field(..., description="Web login blocked status")
    users_for_cdr: TataUsersForCDR = Field(..., description="CDR view configuration")

class TataAgent(BaseModel):
    """Agent details from Tata API"""
    id: str = Field(..., description="Agent ID")
    intercom: int = Field(..., description="Agent intercom number")
    number: str = Field(..., description="Agent phone number")
    agent_status: TataAgentStatus = Field(..., description="Agent status")
    extension: TataExtension = Field(..., description="Extension details")
    sticky_Agent: Optional[Dict[str, Any]] = Field(None, description="Sticky agent configuration")
    time_group: TataTimeGroup = Field(..., description="Time group assignment")
    failover_destination: TataFailoverDestination = Field(..., description="Failover destination")
    is_international_outbound_enabled: bool = Field(..., description="International outbound enabled")

class TataUserData(BaseModel):
    """Complete user data from Tata Tele API"""
    id: str = Field(..., description="Tata user ID")
    name: str = Field(..., description="User full name")
    number: str = Field(..., description="User phone number")
    team_member: TataTeamMember = Field(..., description="Team member details")
    agent: TataAgent = Field(..., description="Agent details")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "288256",
                "name": "John Doe",
                "number": "+91999999999",
                "team_member": {
                    "designation": "Sales Agent",
                    "email": "john@company.com",
                    "login_id": "john123",
                    "status": 1,
                    "role": {"id": 54742, "name": "Admin New"},
                    "is_login_based_calling": True,
                    "is_web_login_block": False,
                    "users_for_cdr": {"type": "all", "value": None}
                },
                "agent": {
                    "id": "0502842370002",
                    "intercom": 1002,
                    "number": "+919999999999",
                    "agent_status": 0,
                    "extension": {"username": "0602842370077", "outbound_block": False},
                    "sticky_Agent": None,
                    "time_group": {"id": 23743, "name": "TEster OCT NOV"},
                    "failover_destination": {"id": "50757", "name": "OFF hours OB", "type": "auto_attendant"},
                    "is_international_outbound_enabled": False
                }
            }
        }

# ============================================================================
# TATA USERS LIST MODELS
# ============================================================================

class TataUserSimple(BaseModel):
    """Simplified user data from Tata users list API"""
    id: int = Field(..., description="User ID")
    name: str = Field(..., description="User name")
    login_id: str = Field(..., description="Login ID")
    is_login_based_calling_enabled: bool = Field(..., description="Login-based calling status")
    is_international_outbound_enabled: bool = Field(..., description="International outbound status")
    user_status: int = Field(..., description="User account status")
    
    # Agent details (simplified)
    agent_id: Optional[str] = Field(None, description="Agent ID")
    agent_name: Optional[str] = Field(None, description="Agent name")
    agent_status: Optional[int] = Field(None, description="Agent status")
    follow_me_number: Optional[str] = Field(None, description="Agent phone number")
    
    # Role details
    user_role_id: Optional[int] = Field(None, description="User role ID")
    user_role_name: Optional[str] = Field(None, description="User role name")
    
    # Extension
    extension: Optional[str] = Field(None, description="Extension assigned to user")

class TataUsersListResponse(BaseModel):
    """Response model for Tata users list API"""
    has_more: bool = Field(..., description="Whether there are more records")
    count: int = Field(..., description="Total number of records in current page")
    last_seen_id: int = Field(..., description="Reference ID of last user in current page")
    data: List[TataUserSimple] = Field(..., description="List of users")

# ============================================================================
# INTEGRATION STATUS AND HEALTH MODELS
# ============================================================================

class TataIntegrationHealth(BaseModel):
    """Health check model for Tata integration"""
    tata_api_status: str = Field(..., description="Tata API connectivity status")
    token_valid: bool = Field(..., description="Whether stored token is valid")
    last_sync: Optional[datetime] = Field(None, description="Last successful sync timestamp")
    users_synced: int = Field(default=0, description="Number of users successfully synced")
    integration_status: IntegrationStatus = Field(..., description="Overall integration status")
    error_message: Optional[str] = Field(None, description="Last error message if any")

class TataIntegrationStats(BaseModel):
    """Statistics model for Tata integration"""
    total_crm_users: int = Field(..., description="Total users in CRM")
    total_tata_users: int = Field(..., description="Total users in Tata")
    synced_users: int = Field(..., description="Successfully synced users")
    pending_sync: int = Field(..., description="Users pending sync")
    failed_sync: int = Field(..., description="Users with failed sync")
    last_sync_timestamp: Optional[datetime] = Field(None, description="Last sync attempt")
    sync_success_rate: float = Field(..., description="Sync success rate percentage")

# ============================================================================
# DATABASE STORAGE MODELS
# ============================================================================

class TataTokenStorage(BaseModel):
    """Model for storing Tata tokens in database"""
    user_id: str = Field(..., description="CRM user ID")
    access_token: str = Field(..., description="Encrypted access token")
    token_type: TataTokenType = Field(default=TataTokenType.BEARER)
    expires_in: int = Field(..., description="Token expiry time in seconds")
    expires_at: datetime = Field(..., description="Token expiry timestamp")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_refreshed: Optional[datetime] = Field(None, description="Last token refresh timestamp")
    is_active: bool = Field(default=True, description="Whether token is active")

class TataIntegrationLog(BaseModel):
    """Model for logging integration events"""
    event_type: str = Field(..., description="Type of integration event")
    user_id: Optional[str] = Field(None, description="Related CRM user ID")
    tata_user_id: Optional[str] = Field(None, description="Related Tata user ID")
    status: str = Field(..., description="Event status (success, failure, warning)")
    message: str = Field(..., description="Event message or error details")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional event metadata")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "event_type": "user_sync",
                "user_id": "507f1f77bcf86cd799439011",
                "tata_user_id": "288256",
                "status": "success",
                "message": "User successfully synced with Tata Tele",
                "metadata": {"sync_duration": 1.2, "fields_updated": ["phone", "email"]},
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }

# ============================================================================
# REQUEST/RESPONSE WRAPPERS
# ============================================================================

class TataApiResponse(BaseModel):
    """Generic wrapper for Tata API responses"""
    success: bool = Field(..., description="Response success status")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")
    message: Optional[str] = Field(None, description="Response message")
    error: Optional[str] = Field(None, description="Error message if any")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class TataIntegrationRequest(BaseModel):
    """Request model for manual integration operations"""
    operation: str = Field(..., description="Operation to perform")
    user_ids: Optional[List[str]] = Field(None, description="Specific user IDs to process")
    force_sync: bool = Field(default=False, description="Force sync even if already synced")
    
    @validator('operation')
    def validate_operation(cls, v):
        allowed_operations = ['sync_users', 'refresh_tokens', 'health_check', 'reset_integration']
        if v not in allowed_operations:
            raise ValueError(f'Operation must be one of: {allowed_operations}')
        return v

class TataIntegrationResponse(BaseModel):
    """Response model for integration operations"""
    success: bool = Field(..., description="Operation success status")
    operation: str = Field(..., description="Operation that was performed")
    results: Dict[str, Any] = Field(..., description="Operation results")
    stats: Optional[TataIntegrationStats] = Field(None, description="Updated integration stats")
    message: str = Field(..., description="Operation message")
    timestamp: datetime = Field(default_factory=datetime.utcnow)