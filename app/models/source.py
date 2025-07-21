# app/models/source.py - UPDATED - Admin must create all sources manually

from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime
from enum import Enum

class SourceCreate(BaseModel):
    """Source creation model"""
    name: str = Field(..., min_length=1, max_length=50, description="Unique source name")
    display_name: str = Field(..., min_length=1, max_length=100, description="Display name for UI")
    description: Optional[str] = Field(None, max_length=200, description="Source description")
    color: Optional[str] = Field("#007bff", description="Hex color for UI display")
    sort_order: int = Field(default=0, description="Sort order for display")
    is_active: bool = Field(default=True, description="Is source active")
    is_default: bool = Field(default=False, description="Is this the default source")
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Source name is required")
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

class SourceUpdate(BaseModel):
    """Source update model"""
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

class SourceResponse(BaseModel):
    """Source response model"""
    id: str
    name: str
    display_name: str
    description: Optional[str]
    color: str
    sort_order: int
    is_active: bool
    is_default: bool
    lead_count: int = Field(default=0, description="Number of leads from this source")
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class SourceListResponse(BaseModel):
    """Source list response"""
    sources: List[SourceResponse]
    total: int
    active_count: int
    inactive_count: int

class SourceHelper:
    """Helper class for source operations"""
    
    @staticmethod
    async def get_all_sources(include_lead_count: bool = False):
        """Get all sources with optional lead count"""
        from ..config.database import get_database
        
        db = get_database()
        sources = await db.sources.find({"is_active": True}).sort("sort_order", 1).to_list(None)
        
        if include_lead_count:
            for source in sources:
                source["lead_count"] = await db.leads.count_documents({"source": source["name"]})
        
        return sources
    
    @staticmethod
    async def get_default_source():
        """Get the default source for new leads - returns None if no sources exist"""
        from ..config.database import get_database
        
        db = get_database()
        default_source = await db.sources.find_one({"is_default": True, "is_active": True})
        
        if not default_source:
            # Fallback to first active source
            default_source = await db.sources.find_one({"is_active": True}, sort=[("sort_order", 1)])
        
        # Return None if no sources exist - admin must create them
        return default_source["name"] if default_source else None
    
    @staticmethod
    async def validate_source_name(name: str, exclude_id: str = None):
        """Validate that source name is unique"""
        from ..config.database import get_database
        from bson import ObjectId
        
        db = get_database()
        query = {"name": name}
        
        if exclude_id:
            query["_id"] = {"$ne": ObjectId(exclude_id)}
        
        existing = await db.sources.find_one(query)
        return existing is None
    
    @staticmethod
    async def create_default_sources():
        """DO NOT create any default sources - admin must create all sources manually"""
        from ..config.database import get_database
        
        db = get_database()
        
        # Check if any sources exist
        existing_count = await db.sources.count_documents({})
        
        # Always return 0 - no default sources will be created
        # Admin must create all sources manually via the API endpoints
        return 0