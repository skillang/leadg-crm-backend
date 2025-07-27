# app/models/call.py - CREATE THIS FILE

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class CallRequest(BaseModel):
    """Request model for making a call"""
    lead_id: str = Field(..., description="Lead ID (e.g., LD-1000)")
    phone_number: str = Field(..., description="Phone number to call")
    lead_name: Optional[str] = Field(None, description="Lead name for display")
    call_type: str = Field("outbound", description="Call type")
    notes: Optional[str] = Field(None, description="Call notes")

    class Config:
        json_schema_extra = {
            "example": {
                "lead_id": "LD-1000",
                "phone_number": "+91-9876543210",
                "lead_name": "Rahul Sharma",
                "call_type": "outbound",
                "notes": "Initial contact call"
            }
        }

class CallResponse(BaseModel):
    """Response model for call operations"""
    success: bool
    call_id: Optional[str] = None
    status: Optional[str] = None
    routed_agent: Optional[str] = None
    agent_name: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None

class CallStatus(BaseModel):
    """Call status information"""
    call_id: str
    status: str  # connecting, active, ended, failed
    duration: Optional[int] = None  # seconds
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    routed_agent: Optional[str] = None
    agent_name: Optional[str] = None

class CallHistoryItem(BaseModel):
    """Individual call history item"""
    call_id: str
    lead_id: str
    lead_name: Optional[str] = None
    phone_number: str
    status: str
    duration: Optional[int] = None
    routed_agent: Optional[str] = None
    agent_name: Optional[str] = None
    created_at: datetime
    notes: Optional[str] = None

class UserCallingStatus(BaseModel):
    """User's calling capability status"""
    calling_enabled: bool
    routing_method: Optional[str] = None
    available_agents: int = 0
    calling_status: str  # active, pending, disabled, failed
    tata_agent_pool: List[str] = []

class CallEndRequest(BaseModel):
    """Request to end a call"""
    call_notes: Optional[str] = Field(None, description="Notes about the call outcome")
    outcome: Optional[str] = Field(None, description="Call outcome (answered, busy, no_answer, etc.)")