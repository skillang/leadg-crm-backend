# app/models/document.py
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

class DocumentType(str, Enum):
    """Document type enumeration matching your UI"""
    PASSPORT = "Passport"
    RESUME = "Resume"
    CERTIFICATE = "Certificate"
    TRANSCRIPT = "Transcript"
    ACCOUNT = "Account"
    ESSENTIALS = "Essentials"
    OTHER = "Other"

class DocumentStatus(str, Enum):
    """Document approval status"""
    PENDING = "Pending"
    APPROVED = "Approved" 
    REJECTED = "Rejected"
    REQUEST_TO_VIEW = "Request to view"

class DocumentCreate(BaseModel):
    """Model for document creation"""
    document_type: DocumentType
    notes: Optional[str] = Field(None, description="Additional notes about the document")
    expiry_date: Optional[datetime] = Field(None, description="Document expiry date (for passports, etc.)")

class DocumentUpdate(BaseModel):
    """Model for document updates"""
    document_type: Optional[DocumentType] = None
    notes: Optional[str] = None
    expiry_date: Optional[datetime] = None

class DocumentApproval(BaseModel):
    """Model for document approval/rejection"""
    approval_notes: str = Field(..., description="Notes from admin for approval/rejection")

class DocumentResponse(BaseModel):
    """Model for document API response"""
    id: str
    lead_id: str
    filename: str
    document_type: str
    file_size: int
    mime_type: str
    status: str
    uploaded_by_name: str
    uploaded_at: datetime
    notes: Optional[str] = None
    expiry_date: Optional[datetime] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    approval_notes: Optional[str] = None
    lead_context: Optional[Dict[str, Any]] = None  # Added for admin/user context

class DocumentListResponse(BaseModel):
    """Model for paginated document list response with timeline-compatible pagination"""
    documents: list[DocumentResponse]
    pagination: Dict[str, Any] = Field(
        ..., 
        description="Pagination information with page, limit, total, pages, has_next, has_prev"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "documents": [],
                "pagination": {
                    "page": 1,
                    "limit": 10,
                    "total": 25,
                    "pages": 3,
                    "has_next": True,
                    "has_prev": False
                }
            }
        }

class BulkDocumentAction(BaseModel):
    """Model for bulk document operations"""
    document_ids: list[str] = Field(..., description="List of document IDs")
    action: str = Field(..., description="Action to perform: approve, reject, delete")
    notes: Optional[str] = Field(None, description="Notes for the bulk action")