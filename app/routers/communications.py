from fastapi import APIRouter, HTTPException, Depends
from app.services.communication_service import CommunicationService
from app.utils.dependencies import get_current_user
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/communications", tags=["communications"])

class LogCommunicationRequest(BaseModel):
    method: str  # email, phone, whatsapp, meeting
    notes: Optional[str] = None
    duration: Optional[int] = None  # For calls in minutes

@router.post("/leads/{lead_id}/log-contact")
async def log_communication(
    lead_id: str,
    communication: LogCommunicationRequest,
    current_user: dict = Depends(get_current_user)
):
    """Manually log a communication interaction"""
    success = await CommunicationService.update_last_contacted(
        lead_id, 
        communication.method
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    return {"message": "Communication logged successfully"}

@router.post("/leads/{lead_id}/log-email")
async def log_email(
    lead_id: str,
    email_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Log email sent to lead"""
    await CommunicationService.log_email_sent(
        lead_id,
        email_data.get("subject")
    )
    return {"message": "Email communication logged"}

@router.post("/leads/{lead_id}/log-call")
async def log_call(
    lead_id: str,
    call_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Log phone call to lead"""
    await CommunicationService.log_phone_call(
        lead_id,
        call_data.get("duration")
    )
    return {"message": "Call communication logged"}