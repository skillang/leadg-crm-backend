# app/models/integration.py - Skillang Integration Models
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

class SkillangFormData(BaseModel):
    """Model for Skillang form submission data"""
    # Core required fields
    name: str = Field(..., min_length=1, max_length=100, description="Full name of the applicant")
    email: EmailStr = Field(..., description="Valid email address")
    phone: str = Field(..., min_length=10, max_length=15, description="Phone number")
    category: str = Field(..., description="Lead category (Nursing, Study Abroad, etc.)")
    
    # Standard optional fields
    pincode: Optional[str] = Field(None, max_length=10, description="Postal/ZIP code")
    experience: Optional[str] = Field(None, description="Experience level (0-1 Years, 1-3 Years, etc.)")
    country: Optional[str] = Field(None, max_length=50, description="Country of origin")
    qualification: Optional[str] = Field(None, max_length=100, description="Educational qualification")
    age: Optional[int] = Field(None, ge=16, le=80, description="Age of the applicant")
    form_source: Optional[str] = Field(None, max_length=50, description="Form source identifier")
    
    # NEW: Additional fields for enhanced forms
    preferred_call_type: Optional[str] = Field(None, description="Preferred call type (Voice, Video, WhatsApp)")
    preferred_language: Optional[str] = Field(None, description="Preferred communication language")
    status: Optional[str] = Field(None, description="Current status or stage")
    preferred_time: Optional[str] = Field(None, description="Preferred contact time")
    budget_range: Optional[str] = Field(None, description="Budget range for services")
    urgency_level: Optional[str] = Field(None, description="Urgency level (Low, Medium, High)")
    referral_source: Optional[str] = Field(None, description="How they heard about us")
    special_requirements: Optional[str] = Field(None, description="Any special requirements")
    
    # NEW: Specific fields from your form data
    german_status: Optional[str] = Field(None, description="German language learning status")
    start_planning: Optional[str] = Field(None, description="When planning to start (Immediately, Next Month, etc.)")
    call_back: Optional[str] = Field(None, description="Preferred callback time (Morning, Afternoon, Evening)")
    
    # NEW: Flexible extra_info field for any additional data
    extra_info: Optional[Dict[str, Any]] = Field(None, description="Additional form data as key-value pairs")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Priya Sharma",
                "email": "priya.sharma@email.com",
                "phone": "+91-9876543210",
                "pincode": "600001",
                "category": "Nursing",
                "experience": "1-3 Years",
                "country": "India",
                "qualification": "B.Sc Nursing",
                "age": 25,
                "form_source": "Nursing Page Form",
                "preferred_call_type": "WhatsApp",
                "preferred_language": "Tamil",
                "urgency_level": "High",
                "budget_range": "50,000 - 1,00,000 INR",
                "preferred_time": "Evening (6-8 PM)",
                "referral_source": "Google Search",
                "special_requirements": "Need weekend availability",
                "german_status": "Not yet started",
                "start_planning": "Immediately", 
                "call_back": "Morning",
                "extra_info": {
                    "shift_preference": "Night Shift",
                    "visa_status": "Student Visa",
                    "work_experience_abroad": "Yes"
                }
            }
        }

class IntegrationResponse(BaseModel):
    """Standard integration response model"""
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    lead_id: Optional[str] = Field(None, description="Generated lead ID")
    category: Optional[str] = Field(None, description="Lead category")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Lead created successfully and confirmation email sent",
                "lead_id": "NU-WB-1",
                "category": "Nursing",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }

class IntegrationErrorResponse(BaseModel):
    """Integration error response model"""
    success: bool = Field(default=False, description="Always false for errors")
    message: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Error code for debugging")
    details: Optional[dict] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "message": "Lead with this email already exists",
                "error_code": "DUPLICATE_EMAIL",
                "details": {"existing_lead_id": "NU-WB-1"},
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }

class SkillangIntegrationStats(BaseModel):
    """Skillang integration statistics model"""
    total_leads_created: int = Field(..., description="Total leads created via integration")
    leads_by_category: dict = Field(..., description="Lead count by category")
    success_rate: float = Field(..., ge=0, le=100, description="Success rate percentage")
    average_response_time: float = Field(..., ge=0, description="Average API response time in seconds")
    last_submission: Optional[datetime] = Field(None, description="Last form submission timestamp")
    email_success_rate: float = Field(..., ge=0, le=100, description="Email delivery success rate")

    class Config:
        json_schema_extra = {
            "example": {
                "total_leads_created": 150,
                "leads_by_category": {
                    "Nursing": 45,
                    "Study Abroad": 38,
                    "German Language": 32,
                    "Work Abroad": 25,
                    "Institution": 10
                },
                "success_rate": 98.5,
                "average_response_time": 0.45,
                "last_submission": "2024-01-15T10:30:00Z",
                "email_success_rate": 96.8
            }
        }

class IntegrationHealthCheck(BaseModel):
    """Integration health check response"""
    status: str = Field(..., description="Health status")
    integration_enabled: bool = Field(..., description="Whether integration is enabled")
    email_service_status: str = Field(..., description="Email service status")
    database_status: str = Field(..., description="Database connection status")
    last_successful_submission: Optional[datetime] = Field(None, description="Last successful form submission")
    configuration_valid: bool = Field(..., description="Whether configuration is valid")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "integration_enabled": True,
                "email_service_status": "connected",
                "database_status": "connected",
                "last_successful_submission": "2024-01-15T10:25:00Z",
                "configuration_valid": True
            }
        }

# Experience level mapping for validation
EXPERIENCE_LEVELS = {
    "0-1 Years": "less_than_1_year",
    "1-3 Years": "1_to_3_years",
    "3-5 Years": "3_to_5_years",
    "5+ Years": "more_than_10_years"
}

class IntegrationValidationError(Exception):
    """Custom exception for integration validation errors"""
    def __init__(self, message: str, error_code: str = None, details: dict = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)