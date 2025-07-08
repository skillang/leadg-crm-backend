from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from ..models.lead import LeadStatus, LeadSource, CourseLevel

class LeadFilterParams(BaseModel):
    """Lead filter parameters"""
    status: Optional[LeadStatus] = None
    assigned_to: Optional[str] = None
    source: Optional[LeadSource] = None
    course_level: Optional[CourseLevel] = None
    country: Optional[str] = None
    tags: Optional[List[str]] = None
    created_from: Optional[str] = None  # Date string
    created_to: Optional[str] = None    # Date string
    search: Optional[str] = None        # Search in name, email
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
    """Lead statistics response with custom statuses"""
    total_leads: int
    followup: int
    warm: int 
    prospect: int 
    junk: int 
    enrolled: int 
    yet_to_call: int 
    counseled: int 
    dnp: int 
    invalid: int 
    call_back: int 
    busy: int 
    ni: int 
    ringing: int
    wrong_number: int 
    my_leads: int
    unassigned_leads: int
