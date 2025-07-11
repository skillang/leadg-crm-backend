from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

class LeadCategoryBase(BaseModel):
    """Base lead category model"""
    name: str = Field(..., min_length=1, max_length=50, description="Category name (e.g., Nursing, Study Abroad)")
    short_form: str = Field(..., min_length=2, max_length=4, description="Short form for lead ID (e.g., NS, SA, WA)")
    description: Optional[str] = Field(None, max_length=200, description="Category description")
    is_active: bool = Field(default=True, description="Whether category is active")
    
    @validator('name')
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError("Category name cannot be empty")
        return v.strip().title()
    
    @validator('short_form')
    def validate_short_form(cls, v):
        if not v.strip():
            raise ValueError("Short form cannot be empty")
        # Convert to uppercase and remove special characters
        cleaned = v.strip().upper().replace(" ", "").replace("-", "").replace("_", "")
        if not cleaned.isalpha():
            raise ValueError("Short form must contain only letters")
        if len(cleaned) < 2 or len(cleaned) > 4:
            raise ValueError("Short form must be 2-4 characters")
        return cleaned

class LeadCategoryCreate(LeadCategoryBase):
    """Lead category creation model"""
    pass

class LeadCategoryUpdate(BaseModel):
    """Lead category update model"""
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None
    # Note: short_form cannot be updated to maintain lead ID consistency

class LeadCategoryResponse(BaseModel):
    """Lead category response model"""
    id: str
    name: str
    short_form: str
    description: Optional[str]
    is_active: bool
    lead_count: int = Field(default=0, description="Number of leads in this category")
    next_lead_number: int = Field(default=1, description="Next lead number for this category")
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class LeadCategoryListResponse(BaseModel):
    """Lead category list response"""
    categories: List[LeadCategoryResponse]
    total: int
    active_count: int
    inactive_count: int