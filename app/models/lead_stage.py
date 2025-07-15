# app/models/lead_stage.py - NEW FILE FOR DYNAMIC STAGE MANAGEMENT

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

class StageBase(BaseModel):
    """Base stage model"""
    name: str = Field(..., min_length=1, max_length=50, description="Stage name (e.g., Initial, Warm, Prospect)")
    display_name: str = Field(..., min_length=1, max_length=50, description="Display name for UI")
    description: Optional[str] = Field(None, max_length=200, description="Stage description")
    color: Optional[str] = Field("#6B7280", description="Hex color for UI display")
    sort_order: int = Field(default=0, description="Order for displaying stages")
    is_active: bool = Field(default=True, description="Whether stage is active")
    is_default: bool = Field(default=False, description="Whether this is the default stage for new leads")
    
    @validator('name')
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError("Stage name cannot be empty")
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

class StageCreate(StageBase):
    """Stage creation model"""
    pass

class StageUpdate(BaseModel):
    """Stage update model"""
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

class StageResponse(BaseModel):
    """Stage response model"""
    id: str
    name: str
    display_name: str
    description: Optional[str]
    color: str
    sort_order: int
    is_active: bool
    is_default: bool
    lead_count: int = Field(default=0, description="Number of leads in this stage")
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class StageListResponse(BaseModel):
    """Stage list response"""
    stages: List[StageResponse]
    total: int
    active_count: int
    inactive_count: int

class StageHelper:
    """Helper class for stage operations"""
    
    @staticmethod
    async def get_all_stages(include_lead_count: bool = False):
        """Get all stages with optional lead count"""
        from ..config.database import get_database
        
        db = get_database()
        stages = await db.lead_stages.find({"is_active": True}).sort("sort_order", 1).to_list(None)
        
        if include_lead_count:
            for stage in stages:
                stage["lead_count"] = await db.leads.count_documents({"stage": stage["name"]})
        
        return stages
    
    @staticmethod
    async def get_default_stage():
        """Get the default stage for new leads"""
        from ..config.database import get_database
        
        db = get_database()
        default_stage = await db.lead_stages.find_one({"is_default": True, "is_active": True})
        
        if not default_stage:
            # Fallback to first active stage
            default_stage = await db.lead_stages.find_one({"is_active": True}, sort=[("sort_order", 1)])
        
        # If no stages exist at all, return a fallback value
        return default_stage["name"] if default_stage else "Pending"
    
    @staticmethod
    async def validate_stage_name(name: str, exclude_id: str = None):
        """Validate that stage name is unique"""
        from ..config.database import get_database
        from bson import ObjectId
        
        db = get_database()
        query = {"name": name}
        
        if exclude_id:
            query["_id"] = {"$ne": ObjectId(exclude_id)}
        
        existing = await db.lead_stages.find_one(query)
        return existing is None
    
    @staticmethod
    async def create_default_stages():
        """DO NOT create any default stages - admin must create all stages manually"""
        from ..config.database import get_database
        
        db = get_database()
        
        # Check if any stages exist
        existing_count = await db.lead_stages.count_documents({})
        
        # Always return 0 - no default stages will be created
        # Admin must create all stages manually
        return 0