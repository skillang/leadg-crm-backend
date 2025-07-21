# app/schemas/lead.py - UPDATED TO USE DYNAMIC COURSE LEVELS AND SOURCES

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
# ✅ UPDATED: Removed LeadSource and CourseLevel enum imports since they're now dynamic
# Only import ExperienceLevel which remains as enum
from ..models.lead import ExperienceLevel

class LeadFilterParams(BaseModel):
    """Lead filter parameters with dynamic course levels and sources"""
    status: Optional[str] = None  # Dynamic status
    assigned_to: Optional[str] = None
    source: Optional[str] = None  # 🔄 CHANGED: str instead of LeadSource enum
    course_level: Optional[str] = None  # 🔄 CHANGED: str instead of CourseLevel enum
    stage: Optional[str] = None  # 🆕 NEW: Dynamic stage filter
    category: Optional[str] = None  # 🆕 NEW: Category filter
    country: Optional[str] = None
    tags: Optional[List[str]] = None
    created_from: Optional[str] = None  # Date string
    created_to: Optional[str] = None    # Date string
    search: Optional[str] = None        # Search in name, email
    
    # 🆕 NEW: Filters for new fields
    age_min: Optional[int] = None  # Minimum age filter
    age_max: Optional[int] = None  # Maximum age filter
    experience: Optional[ExperienceLevel] = None  # Experience level filter
    nationality: Optional[str] = None  # Nationality filter
    
    # Pagination
    page: int = 1
    limit: int = 20

class LeadCreateResponse(BaseModel):
    """Lead creation response"""
    success: bool
    message: str
    lead: Dict[str, Any]

class LeadAssignResponse(BaseModel):
    """Lead assignment response"""
    success: bool
    message: str
    lead_id: str
    assigned_to: str
    assigned_to_name: str

class LeadBulkAssign(BaseModel):
    """Bulk lead assignment"""
    lead_ids: List[str]
    assigned_to: str
    notes: Optional[str] = None

class LeadBulkAssignResponse(BaseModel):
    """Bulk assignment response"""
    success: bool
    message: str
    assigned_count: int
    failed_leads: List[str] = []

class LeadStatsResponse(BaseModel):
    """Lead statistics response with dynamic statuses, stages, sources, and course levels"""
    total_leads: int
    my_leads: int
    unassigned_leads: int
    
    # ✅ UPDATED: Dynamic breakdowns instead of hardcoded fields
    status_breakdown: Optional[Dict[str, int]] = None  # Dynamic status counts
    stage_breakdown: Optional[Dict[str, int]] = None   # 🆕 NEW: Dynamic stage counts
    source_breakdown: Optional[Dict[str, int]] = None  # 🆕 NEW: Dynamic source counts
    course_level_breakdown: Optional[Dict[str, int]] = None  # 🆕 NEW: Dynamic course level counts
    category_breakdown: Optional[Dict[str, int]] = None  # 🆕 NEW: Category breakdown
    
    # 🆕 NEW: Additional statistics
    experience_breakdown: Optional[Dict[str, int]] = None  # Experience level counts
    nationality_breakdown: Optional[Dict[str, int]] = None  # Top nationalities
    age_group_breakdown: Optional[Dict[str, int]] = None  # Age group distribution

# 🆕 NEW: Advanced Filter Models
class AdvancedLeadFilterParams(BaseModel):
    """Advanced lead filter parameters with range filters and sorting"""
    # Basic filters (from LeadFilterParams)
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    source: Optional[str] = None
    course_level: Optional[str] = None
    stage: Optional[str] = None
    category: Optional[str] = None
    
    # Range filters
    lead_score_min: Optional[int] = None
    lead_score_max: Optional[int] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    
    # Multiple selection filters
    sources: Optional[List[str]] = None  # Filter by multiple sources
    course_levels: Optional[List[str]] = None  # Filter by multiple course levels
    stages: Optional[List[str]] = None  # Filter by multiple stages
    statuses: Optional[List[str]] = None  # Filter by multiple statuses
    categories: Optional[List[str]] = None  # Filter by multiple categories
    
    # Date range filters
    created_from: Optional[str] = None
    created_to: Optional[str] = None
    updated_from: Optional[str] = None
    updated_to: Optional[str] = None
    
    # Assignment filters
    assignment_method: Optional[str] = None  # Filter by assignment method
    is_multi_assigned: Optional[bool] = None  # Filter multi-assigned leads
    
    # Text search
    search: Optional[str] = None
    search_fields: Optional[List[str]] = None  # Fields to search in
    
    # Sorting
    sort_by: Optional[str] = "created_at"  # Field to sort by
    sort_order: Optional[str] = "desc"  # asc or desc
    
    # Pagination
    page: int = 1
    limit: int = 20

class LeadExportParams(BaseModel):
    """Parameters for lead export functionality"""
    # Use same filters as AdvancedLeadFilterParams
    filters: Optional[AdvancedLeadFilterParams] = None
    
    # Export specific options
    format: str = "csv"  # csv, excel, pdf
    include_fields: Optional[List[str]] = None  # Specific fields to include
    exclude_fields: Optional[List[str]] = None  # Fields to exclude
    
    # Grouping options
    group_by: Optional[str] = None  # Group by field (source, course_level, etc.)
    include_summary: bool = False  # Include summary statistics

class LeadImportParams(BaseModel):
    """Parameters for lead import functionality"""
    file_format: str  # csv, excel
    mapping: Dict[str, str]  # Column mapping: {"file_column": "lead_field"}
    skip_duplicates: bool = True
    update_existing: bool = False
    validate_only: bool = False  # Only validate, don't import
    
    # Default values for missing fields
    default_source: Optional[str] = "bulk_upload"
    default_course_level: Optional[str] = None
    default_stage: Optional[str] = None
    default_status: Optional[str] = None

class LeadImportResponse(BaseModel):
    """Response for lead import operations"""
    success: bool
    message: str
    total_processed: int
    successful_imports: int
    failed_imports: int
    skipped_duplicates: int
    validation_errors: List[Dict[str, Any]]
    import_summary: Dict[str, Any]

# 🆕 NEW: Analytics Models
class LeadAnalyticsParams(BaseModel):
    """Parameters for lead analytics queries"""
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    group_by: str = "source"  # source, course_level, stage, status, category, etc.
    metrics: List[str] = ["count"]  # count, conversion_rate, avg_score, etc.
    filters: Optional[AdvancedLeadFilterParams] = None

class LeadAnalyticsResponse(BaseModel):
    """Response for lead analytics data"""
    success: bool
    data: List[Dict[str, Any]]
    summary: Dict[str, Any]
    period: Dict[str, str]  # date_from, date_to
    total_leads: int

# 🆕 NEW: Validation Models
class DynamicFieldValidationRequest(BaseModel):
    """Request to validate dynamic field values"""
    field_type: str  # "source", "course_level", "stage", "status"
    field_value: str
    check_active_only: bool = True

class DynamicFieldValidationResponse(BaseModel):
    """Response for dynamic field validation"""
    is_valid: bool
    exists: bool
    is_active: bool
    suggested_value: Optional[str] = None  # If invalid, suggest closest match
    available_values: Optional[List[str]] = None

# 🆕 NEW: Bulk Operation Models
class BulkLeadUpdateParams(BaseModel):
    """Parameters for bulk lead updates"""
    lead_ids: List[str]
    updates: Dict[str, Any]  # Fields to update
    update_method: str = "partial"  # partial or complete
    reason: Optional[str] = None

class BulkLeadUpdateResponse(BaseModel):
    """Response for bulk lead updates"""
    success: bool
    message: str
    total_leads: int
    successfully_updated: int
    failed_updates: List[Dict[str, str]]
    update_summary: Dict[str, Any]