from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

class NoteType(str, Enum):
    """Note type enumeration"""
    GENERAL = "general"
    MEETING = "meeting"
    PHONE_CALL = "phone_call"
    EMAIL = "email"
    DOCUMENT_REVIEW = "document_review"
    FOLLOW_UP = "follow_up"
    REQUIREMENT = "requirement"
    FEEDBACK = "feedback"

class NoteBase(BaseModel):
    """Base note model"""
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=5000)
    note_type: NoteType = NoteType.GENERAL
    tags: Optional[List[str]] = Field(default_factory=list)
    is_important: bool = False
    is_private: bool = False  # Private notes visible only to creator

    @validator('tags')
    def validate_tags(cls, v):
        """Validate and clean tags"""
        if v:
            # Remove duplicates, strip whitespace, limit to 10 tags
            cleaned_tags = list(set([tag.strip() for tag in v if tag.strip()]))
            if len(cleaned_tags) > 10:
                raise ValueError('Maximum 10 tags allowed')
            return cleaned_tags[:10]
        return []

    @validator('title')
    def validate_title(cls, v):
        """Validate title"""
        if not v.strip():
            raise ValueError('Title cannot be empty')
        return v.strip()

class NoteCreate(NoteBase):
    """Note creation model"""
    class Config:
        json_schema_extra = {
            "example": {
                "title": "Student Requirements Discussion",
                "content": "Student is interested in Engineering programs in Canada. Prefers universities in Toronto or Vancouver. Has IELTS score of 7.5. Looking for Fall 2025 intake. Budget around $50,000 CAD per year.",
                "note_type": "meeting",
                "tags": ["Engineering", "Canada", "IELTS ready", "Fall 2025"],
                "is_important": True,
                "is_private": False
            }
        }

class NoteUpdate(BaseModel):
    """Note update model"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1, max_length=5000)
    note_type: Optional[NoteType] = None
    tags: Optional[List[str]] = None
    is_important: Optional[bool] = None
    is_private: Optional[bool] = None

    @validator('tags')
    def validate_tags(cls, v):
        """Validate and clean tags"""
        if v is not None:
            cleaned_tags = list(set([tag.strip() for tag in v if tag.strip()]))
            if len(cleaned_tags) > 10:
                raise ValueError('Maximum 10 tags allowed')
            return cleaned_tags[:10]
        return v

    @validator('title')
    def validate_title(cls, v):
        """Validate title"""
        if v is not None and not v.strip():
            raise ValueError('Title cannot be empty')
        return v.strip() if v else v

class NoteResponse(NoteBase):
    """Note response model"""
    id: str
    lead_id: str
    created_by: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None
    updated_by_name: Optional[str] = None

    class Config:
        from_attributes = True

class NoteListResponse(BaseModel):
    """Note list response model"""
    notes: List[NoteResponse]
    total: int
    page: int
    limit: int
    has_next: bool
    has_prev: bool
    available_tags: List[str] = []  # All tags used in lead's notes

class NoteStatsResponse(BaseModel):
    """Note statistics response"""
    total_notes: int = 0
    notes_by_type: dict = {}  # {"meeting": 5, "phone_call": 3}
    notes_by_author: dict = {}  # {"John Doe": 8, "Jane Smith": 3}
    most_used_tags: List[dict] = []  # [{"tag": "Engineering", "count": 5}]
    recent_notes_count: int = 0  # Notes created in last 7 days

class NoteSearchRequest(BaseModel):
    """Note search request"""
    query: Optional[str] = None  # Search in title and content
    tags: Optional[List[str]] = None  # Filter by tags
    note_type: Optional[NoteType] = None  # Filter by type
    author: Optional[str] = None  # Filter by author (user ID)
    is_important: Optional[bool] = None  # Filter important notes
    date_from: Optional[str] = None  # Date range filter
    date_to: Optional[str] = None
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=100)

class NoteBulkAction(BaseModel):
    """Bulk note action"""
    note_ids: List[str]
    action: str  # "delete", "add_tag", "remove_tag", "mark_important", "mark_private"
    tag: Optional[str] = None  # For add_tag/remove_tag actions
    value: Optional[bool] = None  # For mark_important/mark_private actions