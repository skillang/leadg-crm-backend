# app/models/lead_status.py - NEW FILE FOR DYNAMIC STATUS MANAGEMENT

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

class StatusBase(BaseModel):
    """Base status model"""
    name: str = Field(..., min_length=1, max_length=50, description="Status name (e.g., New, Contacted, Qualified)")
    display_name: str = Field(..., min_length=1, max_length=50, description="Display name for UI")
    description: Optional[str] = Field(None, max_length=200, description="Status description")
    color: Optional[str] = Field("#6B7280", description="Hex color for UI display")
    sort_order: int = Field(default=0, description="Order for displaying statuses")
    is_active: bool = Field(default=True, description="Whether status is active")
    is_default: bool = Field(default=False, description="Whether this is the default status for new leads")
    
    @validator('name')
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError("Status name cannot be empty")
        # Convert to title case and remove extra spaces
        cleaned = ' '.join(v.strip().split())
        return cleaned
    
    @validator('color')
    def validate_color(cls, v):
        if v and not v.startswith('#'):
            v = f"#{v}"
        if v and len(v) != 7:
            raise ValueError("Color must be valid hex format (#RRGGBB)")
        return v or "#6B7280"

class StatusCreate(StatusBase):
    """Status creation model"""
    pass

class StatusUpdate(BaseModel):
    """Status update model"""
    display_name: Optional[str] = Field(None, min_length=1, max_length=50)
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

class StatusResponse(BaseModel):
    """Status response model"""
    id: str
    name: str
    display_name: str
    description: Optional[str]
    color: str
    sort_order: int
    is_active: bool
    is_default: bool
    lead_count: int = Field(default=0, description="Number of leads with this status")
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class StatusListResponse(BaseModel):
    """Status list response"""
    statuses: List[StatusResponse]
    total: int
    active_count: int
    inactive_count: int

class StatusHelper:
    """Helper class for status operations"""
    
    @staticmethod
    async def get_all_statuses(include_lead_count: bool = False):
        """Get all statuses with optional lead count"""
        from ..config.database import get_database
        
        db = get_database()
        statuses = await db.lead_statuses.find({"is_active": True}).sort("sort_order", 1).to_list(None)
        
        if include_lead_count:
            for status in statuses:
                status["lead_count"] = await db.leads.count_documents({"status": status["name"]})
        
        return statuses
    
    @staticmethod
    async def get_default_status():
        """Get the default status for new leads"""
        from ..config.database import get_database
        
        db = get_database()
        default_status = await db.lead_statuses.find_one({"is_default": True, "is_active": True})
        
        if not default_status:
            # Fallback to first active status
            default_status = await db.lead_statuses.find_one({"is_active": True}, sort=[("sort_order", 1)])
        
        # If no statuses exist at all, return a fallback value
        return default_status["name"] if default_status else "New"
    
    @staticmethod
    async def validate_status_name(name: str, exclude_id: str = None):
        """Validate that status name is unique"""
        from ..config.database import get_database
        from bson import ObjectId
        
        db = get_database()
        query = {"name": name}
        
        if exclude_id:
            query["_id"] = {"$ne": ObjectId(exclude_id)}
        
        existing = await db.lead_statuses.find_one(query)
        return existing is None
    
    @staticmethod
    async def create_default_statuses():
        """DO NOT create any default statuses - admin must create all statuses manually"""
        from ..config.database import get_database
        
        db = get_database()
        
        # Check if any statuses exist
        existing_count = await db.lead_statuses.count_documents({})
        
        # Always return 0 - no default statuses will be created
        # Admin must create all statuses manually
        return 0