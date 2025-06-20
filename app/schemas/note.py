from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from ..models.note import NoteType

class NoteFilterParams(BaseModel):
    """Note filter parameters"""
    note_type: Optional[NoteType] = None
    tags: Optional[List[str]] = None
    is_important: Optional[bool] = None
    is_private: Optional[bool] = None
    author: Optional[str] = None  # User ID
    created_from: Optional[str] = None  # Date string
    created_to: Optional[str] = None    # Date string
    search: Optional[str] = None        # Search in title, content
    page: int = 1
    limit: int = 20

class NoteCreateResponse(BaseModel):
    """Note creation response"""
    success: bool
    message: str
    note_id: str
    note_title: str
    lead_id: str

class NoteUpdateResponse(BaseModel):
    """Note update response"""
    success: bool
    message: str
    note: Dict[str, Any]

class NoteBulkActionResponse(BaseModel):
    """Bulk note action response"""
    success: bool
    message: str
    processed_count: int
    failed_notes: List[str] = []

class NoteSearchResponse(BaseModel):
    """Note search response"""
    success: bool
    results: Dict[str, Any]

class NoteTagsResponse(BaseModel):
    """Available tags response"""
    success: bool
    tags: List[Dict[str, Any]]  # [{"tag": "Engineering", "count": 5}]

class NoteActivityResponse(BaseModel):
    """Note activity response for timeline integration"""
    activity_type: str
    description: str
    created_by_name: str
    created_at: str
    metadata: Dict[str, Any]