# app/models/admin_dashboard.py - Fix CallRecord model for null circle values

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, List, Any, Union
from datetime import datetime
from enum import Enum

# ============================================================================
# ENUMS
# ============================================================================

class CallStatusFilter(str, Enum):
    ALL = "all"
    ANSWERED = "answered"
    MISSED = "missed"
    FAILED = "failed"

class CallDirectionFilter(str, Enum):
    ALL = "all"
    INBOUND = "inbound"
    OUTBOUND = "outbound"

class PerformancePeriod(str, Enum):
    """Enum for performance analysis periods"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"

# ============================================================================
# CALL RECORD MODEL - FIXED for null circle values
# ============================================================================

class CircleInfo(BaseModel):
    """Circle information model with optional fields for null values"""
    operator: Optional[str] = Field(None, description="Telecom operator name")
    circle: Optional[str] = Field(None, description="Telecom circle/region")

class CallRecord(BaseModel):
    """
    🔧 FIXED: Call record model from TATA API with proper null handling
    """
    # Core call identifiers
    call_id: str = Field(..., description="Call ID")
    uuid: Optional[str] = Field(None, description="Call UUID")
    id: Optional[str] = Field(None, description="TATA internal ID")
    
    # Call details
    direction: str = Field(..., description="Call direction (inbound/outbound)")
    status: str = Field(..., description="Call status")
    description: Optional[str] = Field(None, description="Call description")
    detailed_description: Optional[str] = Field(None, description="Detailed description")
    service: Optional[str] = Field(None, description="Service type")
    
    # Timing information
    date: str = Field(..., description="Call date (YYYY-MM-DD)")
    time: str = Field(..., description="Call time (HH:MM:SS)")
    end_stamp: Optional[str] = Field(None, description="Call end timestamp")
    call_duration: int = Field(default=0, description="Total call duration in seconds")
    answered_seconds: int = Field(default=0, description="Answered duration in seconds")
    
    # Numbers and agents
    agent_number: Optional[str] = Field(None, description="Agent phone number")
    agent_number_with_prefix: Optional[str] = Field(None, description="Agent number with prefix")
    agent_name: Optional[str] = Field(None, description="Agent name")
    client_number: Optional[str] = Field(None, description="Client/customer number")
    did_number: Optional[str] = Field(None, description="DID number used")
    caller_id_num: Optional[str] = Field(None, description="Caller ID number")
    
    # Call metadata
    recording_url: Optional[str] = Field(None, description="Call recording URL")
    reason: Optional[str] = Field(None, description="Call end reason")
    hangup_cause: Optional[str] = Field(None, description="Hangup cause")
    notes: Optional[str] = Field(None, description="Call notes")
    
    # ✅ FIXED: Circle info with optional fields
    circle: Optional[CircleInfo] = Field(None, description="Telecom operator and circle info")
    
    # Business data
    lead_id: Optional[str] = Field(None, description="Associated lead ID")
    support_api_call: bool = Field(default=False, description="Is support API call")
    
    # Additional fields from TATA
    blocked_number_id: Optional[str] = Field(None, description="Blocked number ID")
    broadcast_id: Optional[str] = Field(None, description="Broadcast ID")
    dtmf_input: Optional[str] = Field(None, description="DTMF input")
    minutes_consumed: int = Field(default=0, description="Minutes consumed")
    charges: float = Field(default=0.0, description="Call charges")
    department_name: Optional[str] = Field(None, description="Department name")
    contact_details: Optional[Dict[str, Any]] = Field(None, description="Contact details")
    missed_agents: List[Dict[str, Any]] = Field(default=[], description="Missed agents list")
    call_flow: List[Dict[str, Any]] = Field(default=[], description="Call flow events")
    accountid: Optional[str] = Field(None, description="Account ID")
    agent_ring_time: Optional[str] = Field(None, description="Agent ring time")
    agent_hangup_data: Optional[Dict[str, Any]] = Field(None, description="Agent hangup data")
    transfer_missed_agent: List[Dict[str, Any]] = Field(default=[], description="Transfer missed agents")
    call_hint: Optional[str] = Field(None, description="Call hint")
    sid: Optional[str] = Field(None, description="SID")
    sname: Optional[str] = Field(None, description="SName")
    is_incoming_from_broadcast: bool = Field(default=False, description="Is incoming from broadcast")
    sip_agent_ids: Optional[str] = Field(None, description="SIP agent IDs")
    dialer_call_details: Optional[Dict[str, Any]] = Field(None, description="Dialer call details")
    custom_status: Optional[str] = Field(None, description="Custom status")
    is_whatsapp: int = Field(default=0, description="Is WhatsApp call")
    lead_data: List[Dict[str, Any]] = Field(default=[], description="Lead data")
    voicemail_recording: bool = Field(default=False, description="Has voicemail recording")
    aws_call_recording_identifier: Optional[str] = Field(None, description="AWS recording identifier")
    
    # Mapped fields (populated by admin service)
    user_id: Optional[str] = Field(None, description="Mapped CRM user ID")
    user_name: Optional[str] = Field(None, description="Mapped CRM user name")

    @validator('circle', pre=True)
    def validate_circle(cls, v):
        """Handle null circle values from TATA API"""
        if v is None:
            return CircleInfo(operator=None, circle=None)
        elif isinstance(v, dict):
            return CircleInfo(
                operator=v.get('operator'),
                circle=v.get('circle')
            )
        return v

# ============================================================================
# USER CALL STATISTICS
# ============================================================================

class UserCallStats(BaseModel):
    """Statistics for a user's call performance"""
    user_id: str = Field(..., description="User ID")
    user_name: str = Field(..., description="User display name")
    agent_number: Optional[str] = Field(None, description="Agent phone number")
    
    # Daily stats
    daily_calls: int = Field(default=0, description="Calls made today")
    daily_answered: int = Field(default=0, description="Calls answered today")
    daily_missed: int = Field(default=0, description="Calls missed today")
    daily_duration: int = Field(default=0, description="Total call duration today (seconds)")
    daily_recordings: int = Field(default=0, description="Calls with recordings today")
    
    # Weekly stats (optional)
    weekly_calls: Optional[int] = Field(None, description="Calls made this week")
    weekly_answered: Optional[int] = Field(None, description="Calls answered this week")
    weekly_missed: Optional[int] = Field(None, description="Calls missed this week")
    weekly_duration: Optional[int] = Field(None, description="Total call duration this week")
    weekly_recordings: Optional[int] = Field(None, description="Calls with recordings this week")
    
    # Monthly stats (optional)
    monthly_calls: Optional[int] = Field(None, description="Calls made this month")
    monthly_answered: Optional[int] = Field(None, description="Calls answered this month")
    monthly_missed: Optional[int] = Field(None, description="Calls missed this month")
    monthly_duration: Optional[int] = Field(None, description="Total call duration this month")
    monthly_recordings: Optional[int] = Field(None, description="Calls with recordings this month")
    
    # Performance metrics
    success_rate: float = Field(default=0.0, description="Call success rate percentage")
    avg_call_duration: float = Field(default=0.0, description="Average call duration in seconds")

# ============================================================================
# DASHBOARD FILTERS
# ============================================================================

class DashboardFilters(BaseModel):
    """Filters for admin call dashboard"""
    date_from: str = Field(..., description="Start date (YYYY-MM-DD)")
    date_to: str = Field(..., description="End date (YYYY-MM-DD)")
    period: str = Field(default="daily", description="Period type (daily/weekly/monthly)")
    user_ids: Optional[List[str]] = Field(None, description="Filter by specific users")
    call_status: CallStatusFilter = Field(default=CallStatusFilter.ALL, description="Call status filter")
    call_direction: CallDirectionFilter = Field(default=CallDirectionFilter.ALL, description="Call direction filter")
    limit: int = Field(default=50, ge=1, le=500, description="Number of records to return")
    page: int = Field(default=1, ge=1, description="Page number for pagination")

# ============================================================================
# PERFORMANCE AND RANKING MODELS
# ============================================================================

class PerformerRanking(BaseModel):
    """Model for ranking top performers"""
    rank: int = Field(..., description="Performer rank (1, 2, 3, etc.)")
    user_id: str = Field(..., description="User ID")
    user_name: str = Field(..., description="User display name")
    agent_number: Optional[str] = Field(None, description="Agent phone number")
    score: float = Field(..., description="Performance score")
    total_calls: int = Field(..., description="Total calls made")
    success_rate: float = Field(..., description="Call success rate percentage")
    total_duration: int = Field(..., description="Total call duration in seconds")
    avg_duration: float = Field(..., description="Average call duration in seconds")
    recordings_count: int = Field(default=0, description="Number of calls with recordings")
    
    class Config:
        json_schema_extra = {
            "example": {
                "rank": 1,
                "user_id": "user123",
                "user_name": "John Doe",
                "agent_number": "+1234567890",
                "score": 95.5,
                "total_calls": 150,
                "success_rate": 78.5,
                "total_duration": 18000,
                "avg_duration": 120.0,
                "recordings_count": 145
            }
        }

class CallTrend(BaseModel):
    """Model for call trend data over time"""
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    total_calls: int = Field(..., description="Total calls on this date")
    answered_calls: int = Field(..., description="Answered calls on this date")
    missed_calls: int = Field(..., description="Missed calls on this date")
    total_duration: int = Field(..., description="Total call duration on this date")
    success_rate: float = Field(..., description="Success rate for this date")
    recordings_count: int = Field(default=0, description="Calls with recordings on this date")
    calls_change: int = Field(default=0, description="Change from previous day")
    calls_change_percent: float = Field(default=0.0, description="Percentage change from previous day")
    trend: str = Field(default="stable", description="Trend direction (up/down/stable)")

class DayComparisonStats(BaseModel):
    """Model for day-to-day comparison statistics"""
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    total_calls: int = Field(..., description="Total calls on this date")
    answered_calls: int = Field(..., description="Answered calls on this date")
    missed_calls: int = Field(..., description="Missed calls on this date")
    total_duration: int = Field(..., description="Total call duration on this date (seconds)")
    success_rate: float = Field(..., description="Success rate percentage for this date")
    recordings_count: int = Field(default=0, description="Calls with recordings on this date")
    calls_change: int = Field(default=0, description="Change from previous day")
    calls_change_percent: float = Field(default=0.0, description="Percentage change from previous day")
    trend: str = Field(default="stable", description="Trend direction (up/down/stable)")
    
    # Additional metrics for comparison
    avg_call_duration: float = Field(default=0.0, description="Average call duration for this date")
    productivity_score: float = Field(default=0.0, description="Daily productivity score")
    efficiency_rating: str = Field(default="average", description="Efficiency rating (low/average/high)")

class TeamPerformanceMetrics(BaseModel):
    """Model for team-wide performance metrics"""
    total_team_calls: int = Field(..., description="Total calls made by team")
    team_success_rate: float = Field(..., description="Team overall success rate")
    team_avg_duration: float = Field(..., description="Team average call duration")
    most_productive_hour: Optional[str] = Field(None, description="Most productive hour of day")
    least_productive_hour: Optional[str] = Field(None, description="Least productive hour of day")
    top_performer: Optional[PerformerRanking] = Field(None, description="Top performing agent")
    improvement_areas: List[str] = Field(default=[], description="Areas for improvement")
    team_goals_status: Dict[str, Any] = Field(default={}, description="Team goals and progress")
    
    # Performance trends
    week_over_week_change: float = Field(default=0.0, description="Week over week performance change")
    month_over_month_change: float = Field(default=0.0, description="Month over month performance change")
    
    # Team efficiency metrics
    total_talk_time: int = Field(default=0, description="Total talk time across team")
    average_calls_per_agent: float = Field(default=0.0, description="Average calls per agent")
    team_utilization_rate: float = Field(default=0.0, description="Team utilization rate percentage")

# ============================================================================
# ANALYTICS AND REPORTING MODELS
# ============================================================================

class CallAnalytics(BaseModel):
    """Advanced analytics model for call data"""
    total_calls: int = Field(..., description="Total calls analyzed")
    successful_calls: int = Field(default=0, description="Successfully completed calls")
    failed_calls: int = Field(default=0, description="Failed or unsuccessful calls")
    success_rate: float = Field(default=0.0, description="Call success rate percentage")
    average_call_duration: float = Field(default=0.0, description="Average call duration in seconds")
    total_call_time: int = Field(default=0, description="Total call time in seconds")
    
    # Call breakdown by outcome and status
    calls_by_outcome: Dict[str, int] = Field(default={}, description="Distribution of call outcomes")
    calls_by_status: Dict[str, int] = Field(default={}, description="Distribution of call statuses")
    
    # Trend analysis
    daily_call_trends: List[Dict[str, Any]] = Field(default=[], description="Daily call trends")
    hourly_call_patterns: Dict[str, float] = Field(default={}, description="Hourly calling patterns")
    
    # Performance metrics
    user_performance: List[Dict[str, Any]] = Field(default=[], description="Individual user performance")
    productivity_score: float = Field(default=0.0, description="Overall productivity score")
    
    # Contact analysis
    unique_leads_contacted: int = Field(default=0, description="Unique leads contacted")
    conversion_rate: float = Field(default=0.0, description="Lead to success conversion rate")
    average_calls_per_lead: float = Field(default=0.0, description="Average calls per lead")
    peak_calling_hours: List[str] = Field(default=[], description="Most active calling hours")
    
    # Time series data
    monthly_trend: List[Dict[str, Any]] = Field(default=[], description="Monthly call trends")
    weekly_patterns: Dict[str, float] = Field(default={}, description="Weekly calling patterns")
    agent_comparison: List[Dict[str, Any]] = Field(default=[], description="Agent performance comparison")
    
    # Metadata
    date_range: Dict[str, datetime] = Field(..., description="Analysis date range")
    generated_at: datetime = Field(..., description="Report generation timestamp")

class CallSummaryReport(BaseModel):
    """Summary report model for call data"""
    report_id: str = Field(..., description="Unique report ID")
    report_period: str = Field(..., description="Report period type")
    start_date: datetime = Field(..., description="Report start date")
    end_date: datetime = Field(..., description="Report end date")
    
    # Call volume metrics
    total_calls: int = Field(..., description="Total calls in period")
    total_answered: int = Field(default=0, description="Total answered calls")
    total_missed: int = Field(default=0, description="Total missed calls")
    total_duration: int = Field(default=0, description="Total call duration in seconds")
    
    # Performance metrics
    overall_success_rate: float = Field(default=0.0, description="Overall success rate")
    average_call_duration: float = Field(default=0.0, description="Average call duration")
    calls_per_agent: float = Field(default=0.0, description="Average calls per agent")
    
    # Agent performance
    top_performers: List[PerformerRanking] = Field(default=[], description="Top performing agents")
    agent_statistics: List[Dict[str, Any]] = Field(default=[], description="Detailed agent statistics")
    
    # Trends and patterns
    daily_breakdown: List[Dict[str, Any]] = Field(default=[], description="Daily call breakdown")
    hourly_patterns: Dict[str, int] = Field(default={}, description="Hourly call patterns")
    
    # Quality metrics
    call_quality_score: float = Field(default=0.0, description="Overall call quality score")
    customer_satisfaction: float = Field(default=0.0, description="Customer satisfaction score")
    
    # Operational metrics
    system_uptime: float = Field(default=100.0, description="System uptime percentage")
    api_response_time: float = Field(default=0.0, description="Average API response time")
    
    # Recommendations and insights
    insights: List[str] = Field(default=[], description="Key insights from the data")
    recommendations: List[str] = Field(default=[], description="Recommendations for improvement")
    
    # Report metadata
    generated_at: datetime = Field(..., description="Report generation timestamp")
    generated_by: str = Field(..., description="User who generated the report")
    report_format: str = Field(default="json", description="Report format")

# ============================================================================
# DASHBOARD RESPONSE MODELS
# ============================================================================

class CallDashboardResponse(BaseModel):
    """Complete response model for admin call dashboard"""
    success: bool = Field(..., description="Request success status")
    total_calls: int = Field(..., description="Total calls in period")
    total_users: int = Field(..., description="Total active users")
    total_recordings: int = Field(..., description="Total calls with recordings")
    overall_success_rate: float = Field(..., description="Overall team success rate")
    
    # User performance data
    user_stats: List[UserCallStats] = Field(..., description="Individual user statistics")
    recent_calls: List[CallRecord] = Field(..., description="Recent call records")
    top_performers: List[PerformerRanking] = Field(..., description="Top performing agents")
    
    # Trends and analytics
    call_trends: Optional[List[CallTrend]] = Field(None, description="Call trends over time")
    team_metrics: Optional[TeamPerformanceMetrics] = Field(None, description="Team performance metrics")
    
    # Request metadata
    filters_applied: DashboardFilters = Field(..., description="Filters applied to data")
    date_range: str = Field(..., description="Date range queried")
    data_fetched_at: datetime = Field(..., description="When data was fetched")
    total_pages: int = Field(default=1, description="Total pages available")
    current_page: int = Field(default=1, description="Current page number")

# Alias for backward compatibility
AdminDashboardResponse = CallDashboardResponse

class UserPerformanceResponse(BaseModel):
    """Response model for individual user performance data"""
    user_id: str = Field(..., description="User ID")
    user_name: str = Field(..., description="User display name")
    user_email: str = Field(..., description="User email address")
    agent_number: Optional[str] = Field(None, description="Agent phone number")
    
    # Performance metrics
    total_calls: int = Field(default=0, description="Total calls made")
    answered_calls: int = Field(default=0, description="Calls answered")
    missed_calls: int = Field(default=0, description="Calls missed")
    success_rate: float = Field(default=0.0, description="Call success rate percentage")
    
    # Duration metrics
    total_duration: int = Field(default=0, description="Total call duration in seconds")
    avg_call_duration: float = Field(default=0.0, description="Average call duration")
    
    # Recording metrics
    recordings_count: int = Field(default=0, description="Calls with recordings")
    recording_rate: float = Field(default=0.0, description="Percentage of calls recorded")
    
    # Performance scores
    performance_score: float = Field(default=0.0, description="Overall performance score")
    efficiency_rating: str = Field(default="average", description="Efficiency rating")
    productivity_rank: Optional[int] = Field(None, description="Rank among team members")
    
    # Time-based breakdown
    daily_stats: Optional[Dict[str, int]] = Field(None, description="Daily call breakdown")
    weekly_stats: Optional[Dict[str, int]] = Field(None, description="Weekly call breakdown")
    monthly_stats: Optional[Dict[str, int]] = Field(None, description="Monthly call breakdown")
    
    # Metadata
    last_call_at: Optional[datetime] = Field(None, description="Timestamp of last call")
    analysis_period: str = Field(..., description="Period analyzed (daily/weekly/monthly)")
    analyzed_at: datetime = Field(default_factory=datetime.utcnow, description="Analysis timestamp")

class CallStatistics(BaseModel):
    """General call statistics model"""
    total_calls: int = Field(..., description="Total number of calls")
    answered_calls: int = Field(default=0, description="Number of answered calls")
    missed_calls: int = Field(default=0, description="Number of missed calls")
    failed_calls: int = Field(default=0, description="Number of failed calls")
    
    # Rates and percentages
    success_rate: float = Field(default=0.0, description="Success rate percentage")
    answer_rate: float = Field(default=0.0, description="Answer rate percentage")
    completion_rate: float = Field(default=0.0, description="Completion rate percentage")
    
    # Duration statistics
    total_talk_time: int = Field(default=0, description="Total talk time in seconds")
    avg_call_duration: float = Field(default=0.0, description="Average call duration")
    longest_call: int = Field(default=0, description="Longest call duration")
    shortest_call: int = Field(default=0, description="Shortest call duration")
    
    # Quality metrics
    recordings_available: int = Field(default=0, description="Calls with recordings")
    quality_score: float = Field(default=0.0, description="Overall quality score")

class DashboardSummary(BaseModel):
    """Summary model for dashboard overview"""
    period_type: str = Field(..., description="Summary period (daily/weekly/monthly)")
    total_calls: int = Field(..., description="Total calls in period")
    total_agents: int = Field(..., description="Total active agents")
    success_rate: float = Field(..., description="Overall success rate")
    avg_call_duration: float = Field(..., description="Average call duration")
    total_talk_time: int = Field(..., description="Total talk time in seconds")
    calls_vs_previous_period: int = Field(default=0, description="Change from previous period")
    performance_trend: str = Field(default="stable", description="Performance trend")
    
    # Quick stats
    answered_calls: int = Field(default=0, description="Answered calls")
    missed_calls: int = Field(default=0, description="Missed calls")
    recordings_available: int = Field(default=0, description="Calls with recordings")
    
    # Top metrics
    busiest_hour: Optional[str] = Field(None, description="Busiest calling hour")
    most_productive_agent: Optional[str] = Field(None, description="Most productive agent name")
    best_success_rate: Optional[float] = Field(None, description="Best agent success rate")

class PerformanceComparison(BaseModel):
    """Model for comparing performance between periods or users"""
    comparison_type: str = Field(..., description="Type of comparison (period/user)")
    base_period: str = Field(..., description="Base period for comparison")
    compare_period: str = Field(..., description="Comparison period")
    
    # Metrics comparison
    calls_change: int = Field(default=0, description="Change in call volume")
    calls_change_percent: float = Field(default=0.0, description="Percentage change in calls")
    success_rate_change: float = Field(default=0.0, description="Change in success rate")
    duration_change: int = Field(default=0, description="Change in total duration")
    
    # Trend indicators
    trend_direction: str = Field(default="stable", description="Overall trend direction")
    improvement_areas: List[str] = Field(default=[], description="Areas showing improvement")
    decline_areas: List[str] = Field(default=[], description="Areas showing decline")
    
    # Recommendations
    recommendations: List[str] = Field(default=[], description="Performance recommendations")

class AgentActivity(BaseModel):
    """Model for tracking agent activity and availability"""
    agent_id: str = Field(..., description="Agent ID")
    agent_name: str = Field(..., description="Agent name")
    agent_number: Optional[str] = Field(None, description="Agent phone number")
    
    # Activity status
    current_status: str = Field(..., description="Current agent status")
    last_activity: datetime = Field(..., description="Last activity timestamp")
    login_time: Optional[datetime] = Field(None, description="Login time today")
    total_online_time: int = Field(default=0, description="Total online time in seconds")
    
    # Call activity
    calls_today: int = Field(default=0, description="Calls made today")
    current_call_id: Optional[str] = Field(None, description="Current active call ID")
    next_scheduled_call: Optional[datetime] = Field(None, description="Next scheduled call")
    
    # Performance indicators
    availability_rate: float = Field(default=0.0, description="Availability rate percentage")
    utilization_rate: float = Field(default=0.0, description="Utilization rate percentage")
    
class DashboardConfig(BaseModel):
    """Configuration model for dashboard display settings"""
    default_period: str = Field(default="daily", description="Default time period")
    refresh_interval: int = Field(default=300, description="Auto-refresh interval in seconds")
    timezone: str = Field(default="UTC", description="Display timezone")
    
    # Display preferences
    show_recordings: bool = Field(default=True, description="Show recording statistics")
    show_trends: bool = Field(default=True, description="Show trend analysis")
    show_comparisons: bool = Field(default=True, description="Show period comparisons")
    max_recent_calls: int = Field(default=50, description="Max recent calls to display")
    
    # Alert thresholds
    low_success_rate_threshold: float = Field(default=50.0, description="Low success rate alert threshold")
    high_success_rate_threshold: float = Field(default=80.0, description="High success rate threshold")
    min_daily_calls_threshold: int = Field(default=10, description="Minimum daily calls threshold")

# ============================================================================
# ANALYTICS AND REPORTING MODELS
# ============================================================================

class CallAnalytics(BaseModel):
    """Advanced analytics model for call data"""
    total_calls: int = Field(..., description="Total calls analyzed")
    unique_leads_contacted: int = Field(default=0, description="Unique leads contacted")
    conversion_rate: float = Field(default=0.0, description="Lead to success conversion rate")
    average_calls_per_lead: float = Field(default=0.0, description="Average calls per lead")
    peak_calling_hours: List[str] = Field(default=[], description="Most active calling hours")
    call_outcome_distribution: Dict[str, int] = Field(default={}, description="Distribution of call outcomes")
    monthly_trend: List[Dict[str, Any]] = Field(default=[], description="Monthly call trends")
    weekly_patterns: Dict[str, float] = Field(default={}, description="Weekly calling patterns")
    agent_comparison: List[Dict[str, Any]] = Field(default=[], description="Agent performance comparison")

class ReportingPeriod(BaseModel):
    """Model for reporting period configuration"""
    period_type: str = Field(..., description="Type of period (daily/weekly/monthly/quarterly)")
    start_date: datetime = Field(..., description="Period start date")
    end_date: datetime = Field(..., description="Period end date")
    business_days_only: bool = Field(default=False, description="Include only business days")
    timezone: str = Field(default="UTC", description="Timezone for date calculations")

# ============================================================================
# ADMIN ACTIVITY LOG
# ============================================================================

class AdminActivityLog(BaseModel):
    """Model for logging admin activities"""
    admin_user_id: str = Field(..., description="Admin user ID")
    admin_email: str = Field(..., description="Admin email")
    action: str = Field(..., description="Action performed")
    target_user_id: Optional[str] = Field(None, description="Target user ID (if applicable)")
    target_user_name: Optional[str] = Field(None, description="Target user name (if applicable)")
    details: Dict[str, Any] = Field(default={}, description="Additional action details")
    ip_address: Optional[str] = Field(None, description="Admin IP address")
    user_agent: Optional[str] = Field(None, description="Admin user agent")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Action timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "admin_user_id": "admin123",
                "admin_email": "admin@company.com",
                "action": "viewed_call_dashboard",
                "details": {"filters": {"date_from": "2024-01-01", "date_to": "2024-01-31"}},
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }

class PerformanceRankingResponse(BaseModel):
    """Response model for performance rankings"""
    success: bool = Field(..., description="Request success status")
    period: str = Field(..., description="Performance period analyzed")
    rankings: List[PerformerRanking] = Field(..., description="List of ranked performers")
    total_users: int = Field(..., description="Total users in ranking")
    date_range: str = Field(..., description="Date range analyzed")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Report generation time")

class RecordingPlayResponse(BaseModel):
    """Response model for recording playback requests"""
    success: bool = Field(..., description="Request success status")
    message: str = Field(..., description="Response message")
    recording_url: Optional[str] = Field(None, description="URL to access the recording")
    access_logged: bool = Field(default=True, description="Whether access was logged for compliance")
    expires_at: Optional[datetime] = Field(None, description="When the recording URL expires")
    call_id: Optional[str] = Field(None, description="Call ID for the recording")
    
class FilterOptionsResponse(BaseModel):
    """Response model for dashboard filter options"""
    success: bool = Field(..., description="Request success status")
    available_users: List[Dict[str, str]] = Field(..., description="List of available users for filtering")
    min_date: str = Field(..., description="Minimum selectable date (YYYY-MM-DD)")
    max_date: str = Field(..., description="Maximum selectable date (YYYY-MM-DD)")
    call_statuses: List[str] = Field(..., description="Available call status options")
    call_directions: List[str] = Field(..., description="Available call direction options")
    performance_periods: List[str] = Field(..., description="Available performance period options")

class UserPerformanceRequest(BaseModel):
    """Request model for user performance data"""
    user_id: str = Field(..., description="User ID to analyze")
    period: str = Field(default="weekly", description="Analysis period")
    date_from: Optional[str] = Field(None, description="Start date (YYYY-MM-DD)")
    date_to: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")
    include_comparisons: bool = Field(default=True, description="Include period comparisons")

class PlayRecordingRequest(BaseModel):
    """Request model for playing call recordings"""
    call_id: str = Field(..., description="Call ID to play recording for")
    user_id: str = Field(..., description="User ID associated with the call")
    reason: str = Field(..., description="Reason for accessing the recording")

class DashboardError(BaseModel):
    """Error response model for dashboard operations"""
    success: bool = Field(default=False, description="Request success status")
    error_code: str = Field(..., description="Error code for client handling")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

# ============================================================================
# ADDITIONAL MISSING MODELS FROM YOUR ROUTER
# ============================================================================

class DayComparisonResponse(BaseModel):
    """Response model for day-to-day comparison data"""
    success: bool = Field(..., description="Request success status")
    user_id: str = Field(..., description="User ID analyzed")
    date_range: str = Field(..., description="Date range analyzed")
    daily_stats: List[DayComparisonStats] = Field(..., description="Day-by-day statistics")
    summary: Optional[Dict[str, Any]] = Field(None, description="Summary statistics")

class CallTrendResponse(BaseModel):
    """Response model for call trend analysis"""
    success: bool = Field(..., description="Request success status")
    period: str = Field(..., description="Analysis period")
    trends: List[CallTrend] = Field(..., description="Call trend data points")
    insights: List[str] = Field(default=[], description="Generated insights from trends")

# ============================================================================
# ENHANCED USER PERFORMANCE RESPONSE (Update existing one)
# ============================================================================

class UserPerformanceResponse(BaseModel):
    """Enhanced response model for individual user performance data"""
    success: bool = Field(..., description="Request success status")
    user_id: str = Field(..., description="User ID")
    user_name: str = Field(..., description="User display name")
    agent_number: Optional[str] = Field(None, description="Agent phone number")
    
    # Main statistics
    stats: UserCallStats = Field(..., description="User call statistics")
    
    # Optional additional data
    day_comparison: Optional[List[DayComparisonStats]] = Field(None, description="Day-to-day comparison")
    call_records: Optional[List[CallRecord]] = Field(None, description="Recent call records")
    ranking: Optional[PerformerRanking] = Field(None, description="User's performance ranking")
    
    # Metadata
    period_analyzed: str = Field(..., description="Period that was analyzed")
    analysis_date: datetime = Field(default_factory=datetime.utcnow, description="When analysis was performed")

# ============================================================================
# ADMIN DASHBOARD MAIN RESPONSE (Already exists, but ensure it's complete)
# ============================================================================

# The AdminDashboardResponse should already exist in your file, but if it's missing:
class AdminDashboardResponse(BaseModel):
    """Complete response model for admin call dashboard"""
    success: bool = Field(..., description="Request success status")
    total_calls: int = Field(..., description="Total calls in period")
    total_users: int = Field(..., description="Total active users")
    total_recordings: int = Field(..., description="Total calls with recordings")
    overall_success_rate: float = Field(..., description="Overall team success rate")
    
    # User performance data
    user_stats: List[UserCallStats] = Field(..., description="Individual user statistics")
    recent_calls: List[CallRecord] = Field(..., description="Recent call records")
    top_performers: List[PerformerRanking] = Field(..., description="Top performing agents")
    
    # Trends and analytics
    call_trends: Optional[List[CallTrend]] = Field(None, description="Call trends over time")
    team_metrics: Optional[TeamPerformanceMetrics] = Field(None, description="Team performance metrics")
    
    # Request metadata
    filters_applied: DashboardFilters = Field(..., description="Filters applied to data")
    date_range: str = Field(..., description="Date range queried")
    data_fetched_at: datetime = Field(default_factory=datetime.utcnow, description="When data was fetched")
    total_pages: int = Field(default=1, description="Total pages available")
    current_page: int = Field(default=1, description="Current page number")

# ============================================================================
# IMPORT VALIDATION HELPER
# ============================================================================

def validate_admin_dashboard_models():
    """Helper function to validate all required models exist"""
    required_models = [
        'CallRecord', 'UserCallStats', 'PerformerRanking', 'DashboardFilters',
        'CallStatusFilter', 'CallDirectionFilter', 'PerformancePeriod',
        'AdminDashboardResponse', 'UserPerformanceResponse', 'PerformanceRankingResponse',
        'RecordingPlayResponse', 'FilterOptionsResponse', 'UserPerformanceRequest',
        'PlayRecordingRequest', 'DashboardError'
    ]
    
    missing_models = []
    current_module = globals()
    
    for model_name in required_models:
        if model_name not in current_module:
            missing_models.append(model_name)
    
    if missing_models:
        print(f"❌ Missing models: {missing_models}")
        return False
    else:
        print("✅ All required models are available")
        return True




class PlayRecordingRequest(BaseModel):
    """Request model for playing call recordings"""
    call_id: str = Field(..., description="Call ID to play recording for")
    user_id: str = Field(..., description="User ID associated with the call")
    reason: str = Field(..., description="Reason for accessing the recording")

    class Config:
        json_schema_extra = {
            "example": {
                "call_id": "68a2d41ee46eb844ab7d7e0b",
                "user_id": "686f894b1ca17da22b3533e7",
                "reason": "Quality review for training purposes"
            }
        }

class RecordingPlayResponse(BaseModel):
    """Response model for recording playback requests"""
    success: bool = Field(..., description="Request success status")
    message: str = Field(..., description="Response message")
    recording_url: Optional[str] = Field(None, description="Complete URL to access the recording")
    call_id: Optional[str] = Field(None, description="Call ID for the recording")
    call_info: Optional[Dict[str, Any]] = Field(None, description="Additional call information")
    access_logged: bool = Field(default=True, description="Whether access was logged for compliance")
    expires_at: Optional[datetime] = Field(None, description="When the recording URL expires")
    accessed_by: Optional[str] = Field(None, description="Admin who accessed the recording")
    access_reason: Optional[str] = Field(None, description="Reason for accessing")

class UserRecordingsResponse(BaseModel):
    """Response model for user recordings list"""
    success: bool = Field(..., description="Request success status")
    user_id: str = Field(..., description="User ID")
    user_name: str = Field(..., description="User display name")
    agent_number: Optional[str] = Field(None, description="Agent phone number")
    recordings: List[Dict[str, Any]] = Field(..., description="List of recordings")
    pagination: Dict[str, Any] = Field(..., description="Pagination information")
    statistics: Dict[str, Any] = Field(..., description="Recording statistics")
    date_range: str = Field(..., description="Date range analyzed")
    retrieved_at: datetime = Field(..., description="Data retrieval timestamp")

class RecordingDetailsResponse(BaseModel):
    """Response model for recording details"""
    success: bool = Field(..., description="Request success status")
    has_recording: bool = Field(..., description="Whether recording exists")
    recording_url: Optional[str] = Field(None, description="Recording URL if available")
    call_details: Dict[str, Any] = Field(..., description="Complete call information")
    user_info: Dict[str, str] = Field(..., description="Associated user information")
    recording_info: Optional[Dict[str, Any]] = Field(None, description="Recording metadata")
    retrieved_at: datetime = Field(..., description="Data retrieval timestamp")