# app/models/course_level.py - UPDATED - Admin must create all course levels manually

from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime
from enum import Enum

class CourseLevelCreate(BaseModel):
    """Course level creation model"""
    name: str = Field(..., min_length=1, max_length=50, description="Unique course level name")
    display_name: str = Field(..., min_length=1, max_length=100, description="Display name for UI")
    description: Optional[str] = Field(None, max_length=200, description="Course level description")
    color: Optional[str] = Field("#007bff", description="Hex color for UI display")
    sort_order: int = Field(default=0, description="Sort order for display")
    is_active: bool = Field(default=True, description="Is course level active")
    is_default: bool = Field(default=False, description="Is this the default course level")
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Course level name is required")
        # Convert to lowercase and replace spaces with underscores
        return v.strip().lower().replace(' ', '_')
    
    @validator('display_name')
    def validate_display_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Display name is required")
        return v.strip()
    
    @validator('color')
    def validate_color(cls, v):
        if v and not v.startswith('#'):
            v = f"#{v}"
        if v and len(v) != 7:
            raise ValueError("Color must be valid hex format (#RRGGBB)")
        return v

class CourseLevelUpdate(BaseModel):
    """Course level update model"""
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=200)
    color: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    
    @validator('color')
    def validate_color(cls, v):
        if v and not v.startswith('#'):
            v = f"#{v}"
        if v and len(v) != 7:
            raise ValueError("Color must be valid hex format (#RRGGBB)")
        return v

class CourseLevelResponse(BaseModel):
    """Course level response model"""
    id: str
    name: str
    display_name: str
    description: Optional[str]
    color: str
    sort_order: int
    is_active: bool
    is_default: bool
    lead_count: int = Field(default=0, description="Number of leads with this course level")
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class CourseLevelListResponse(BaseModel):
    """Course level list response"""
    course_levels: List[CourseLevelResponse]
    total: int
    active_count: int
    inactive_count: int

class CourseLevelHelper:
    """Helper class for course level operations"""
    
    @staticmethod
    async def get_all_course_levels(include_lead_count: bool = False):
        """Get all course levels with optional lead count"""
        from ..config.database import get_database
        
        db = get_database()
        course_levels = await db.course_levels.find({"is_active": True}).sort("sort_order", 1).to_list(None)
        
        if include_lead_count:
            for course_level in course_levels:
                course_level["lead_count"] = await db.leads.count_documents({"course_level": course_level["name"]})
        
        return course_levels
    
    @staticmethod
    async def get_default_course_level():
        """Get the default course level for new leads - returns None if no course levels exist"""
        from ..config.database import get_database
        
        db = get_database()
        default_course_level = await db.course_levels.find_one({"is_default": True, "is_active": True})
        
        if not default_course_level:
            # Fallback to first active course level
            default_course_level = await db.course_levels.find_one({"is_active": True}, sort=[("sort_order", 1)])
        
        # Return None if no course levels exist - admin must create them
        return default_course_level["name"] if default_course_level else None
    
    @staticmethod
    async def validate_course_level_name(name: str, exclude_id: str = None):
        """Validate that course level name is unique"""
        from ..config.database import get_database
        from bson import ObjectId
        
        db = get_database()
        query = {"name": name}
        
        if exclude_id:
            query["_id"] = {"$ne": ObjectId(exclude_id)}
        
        existing = await db.course_levels.find_one(query)
        return existing is None
    
    @staticmethod
    async def create_default_course_levels():
        """DO NOT create any default course levels - admin must create all course levels manually"""
        from ..config.database import get_database
        
        db = get_database()
        
        # Check if any course levels exist
        existing_count = await db.course_levels.count_documents({})
        
        # Always return 0 - no default course levels will be created
        # Admin must create all course levels manually via the API endpoints
        return 0