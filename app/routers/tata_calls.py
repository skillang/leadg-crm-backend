# app/routers/tata_calls.py
# Enhanced Tata Calls Router - CLEANED VERSION (No Call Logging)
# Core calling functionality from CRM + User syncing functionality preserved

from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, Field

from app.decorators.timezone_decorator import convert_dates_to_ist

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import existing services (calling and user sync preserved)
from ..services.tata_user_service import tata_user_service
from ..services.tata_call_service import tata_call_service
from ..utils.dependencies import get_current_active_user, get_admin_user

# =============================================================================
# SIMPLE INLINE MODELS (No Database Storage - Just API Request/Response)
# =============================================================================

class ClickToCallRequestSimple(BaseModel):
    lead_id: str = Field(..., description="Lead ID to call")
    notes: Optional[str] = Field(None, description="Call notes")
    call_purpose: Optional[str] = Field(None, description="Purpose of call")

class ClickToCallRequest(BaseModel):
    lead_id: str = Field(..., description="Lead ID")
    destination_number: str = Field(..., description="Phone number to call")
    caller_id: Optional[str] = Field(None, description="Caller ID")
    notes: Optional[str] = Field(None, description="Call notes")
    call_timeout: Optional[int] = Field(None, description="Call timeout in seconds")

class ClickToCallResponse(BaseModel):
    success: bool = Field(..., description="Call success status")
    message: str = Field(..., description="Response message")
    call_id: Optional[str] = Field(None, description="Call ID")
    tata_call_id: Optional[str] = Field(None, description="TATA API call ID")
    call_status: str = Field("initiated", description="Call status")
    estimated_connection_time: int = Field(30, description="Estimated connection time")
    initiated_at: datetime = Field(default_factory=datetime.utcnow, description="Call initiation time")
    caller_number: Optional[str] = Field(None, description="Caller number")
    destination_number: Optional[str] = Field(None, description="Destination number")

class SupportCallRequest(BaseModel):
    issue_type: str = Field(..., description="Type of issue")
    priority: Optional[str] = Field("normal", description="Priority level")
    description: Optional[str] = Field(None, description="Issue description")
    related_lead_id: Optional[str] = Field(None, description="Related lead ID")

class SupportCallResponse(BaseModel):
    success: bool = Field(..., description="Support call success")
    message: str = Field(..., description="Response message")
    support_call_id: str = Field(..., description="Support call ID")
    ticket_number: Optional[str] = Field(None, description="Ticket number")
    priority: str = Field(..., description="Priority level")
    estimated_callback_time: int = Field(300, description="Estimated callback time")
    support_agent_info: Optional[dict] = Field(None, description="Support agent info")
    submitted_at: datetime = Field(default_factory=datetime.utcnow, description="Submission time")

class CallPermissionResponse(BaseModel):
    user_id: str = Field(..., description="User ID")
    can_make_calls: bool = Field(..., description="Can make calls")
    has_tata_mapping: bool = Field(..., description="Has TATA mapping")
    tata_agent_id: Optional[str] = Field(None, description="TATA agent ID")
    call_limit_remaining: Optional[int] = Field(None, description="Remaining call limit")
    daily_call_count: int = Field(0, description="Daily call count")
    permission_errors: list = Field(default_factory=list, description="Permission errors")
    last_call_time: Optional[datetime] = Field(None, description="Last call time")
    checked_at: datetime = Field(default_factory=datetime.utcnow, description="Check time")

class CallWebhookPayload(BaseModel):
    event_type: str = Field(..., description="Event type")
    call_id: str = Field(..., description="Call ID")
    data: dict = Field(default_factory=dict, description="Event data")

class CallValidationRequest(BaseModel):
    lead_id: str = Field(..., description="Lead ID to validate")

class CallValidationResponse(BaseModel):
    can_call: bool = Field(..., description="Can make call")
    validation_errors: list = Field(default_factory=list, description="Validation errors")
    lead_found: bool = Field(False, description="Lead found")
    lead_phone: Optional[str] = Field(None, description="Lead phone number")
    user_can_call: bool = Field(False, description="User can make calls")
    user_agent_id: Optional[str] = Field(None, description="User agent ID")
    estimated_setup_time: int = Field(0, description="Setup time estimate")
    recommendations: list = Field(default_factory=list, description="Recommendations")

# =============================================================================
# DISABLE PROGRESSIVE DIALER (No Call Logging Dependencies)
# =============================================================================

PROGRESSIVE_DIALER_AVAILABLE = False  # Disabled since we removed call logging

# =============================================================================
# CREATE ROUTER
# =============================================================================

router = APIRouter()

# =============================================================================
# SIMPLIFIED CLICK-TO-CALL ENDPOINT (AUTO-FETCH) - PRESERVED
# =============================================================================

@router.post("/click-to-call-simple", response_model=ClickToCallResponse)
async def initiate_click_to_call_simple(
    call_request: ClickToCallRequestSimple,
    current_user: dict = Depends(get_current_active_user)
):
    """
    🎯 Simplified Click-to-Call - Only Lead ID Required
    
    **Auto-fetch Features:**
    - **Lead Phone**: Automatically fetches phone number from lead data
    - **User Agent**: Automatically uses user's Tata sync data  
    - **No Manual Input**: Frontend only needs to send lead_id
    - **Smart Validation**: Pre-validates lead and user before calling
    - **No Logging**: Direct call to TATA API without local storage
    
    **Usage:**
    ```json
    {
        "lead_id": "LEAD_12345",
        "notes": "Follow-up call regarding course inquiry",
        "call_purpose": "Sales Follow-up"
    }
    ```
    """
    try:
        logger.info(f"🎯 User {current_user['email']} initiating simplified click-to-call for lead {call_request.lead_id}")
        
        # Validate request
        if not call_request.lead_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lead ID is required"
            )
        
        # Use the simplified service method (preserved - no logging)
        success, result = await tata_call_service.initiate_click_to_call_simple(
            lead_id=call_request.lead_id,
            current_user=current_user,
            notes=call_request.notes,
            call_purpose=call_request.call_purpose
        )
        
        # Handle response
        if not success:
            error_detail = result.get("message", "Call initiation failed")
            
            # Provide specific error messages for common issues
            if "phone not found" in error_detail.lower():
                error_detail = f"No phone number found for lead {call_request.lead_id}. Please add a phone number to the lead."
            elif "not synchronized" in error_detail.lower():
                error_detail = "Your account is not synchronized with the calling system. Please contact admin to enable calling."
            elif "agent id not found" in error_detail.lower():
                error_detail = "Calling not configured for your account. Please contact admin for setup."
            
            logger.warning(f"❌ Click-to-call failed for {call_request.lead_id}: {error_detail}")
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail
            )
        
        # Success response
        logger.info(f"✅ Simplified click-to-call initiated successfully for lead {call_request.lead_id}")
        
        return ClickToCallResponse(
            success=True,
            message="Call initiated successfully",
            call_id=result.get("call_id"),
            tata_call_id=result.get("tata_call_id"),
            call_status=result.get("status", "initiated"),
            estimated_connection_time=30,
            initiated_at=datetime.utcnow(),
            caller_number=result.get("caller_number"),
            destination_number=result.get("destination_number")
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"❌ Error in simplified click-to-call: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error initiating call: {str(e)}"
        )

# =============================================================================
# CALL VALIDATION ENDPOINT - PRESERVED
# =============================================================================

@router.post("/validate-call", response_model=CallValidationResponse)
async def validate_call_parameters(
    validation_request: CallValidationRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    🔍 Validate Call Parameters Before Making Call
    
    **Pre-call Validation:**
    - **Lead Exists**: Checks if lead exists and has phone number
    - **User Permissions**: Validates user can make calls
    - **Tata Sync**: Confirms user is synchronized with Tata system
    - **Recommendations**: Provides setup recommendations if needed
    
    **Usage:**
    ```json
    {
        "lead_id": "LEAD_12345"
    }
    ```
    """
    try:
        logger.info(f"🔍 User {current_user['email']} validating call for lead {validation_request.lead_id}")
        
        user_id = str(current_user.get("user_id") or current_user.get("_id"))
        validation_errors = []
        recommendations = []
        
        # 1. Check if lead exists and has phone
        lead_phone = await tata_call_service._get_lead_phone_number(validation_request.lead_id)
        lead_found = lead_phone is not None
        
        if not lead_found:
            validation_errors.append(f"Lead {validation_request.lead_id} not found")
        elif not lead_phone:
            validation_errors.append(f"Lead {validation_request.lead_id} has no phone number")
            recommendations.append("Add a phone number to the lead before calling")
        
        # 2. Check user calling permissions using TataUserService
        user_mapping = await tata_user_service.get_user_mapping(user_id)
        
        user_can_call = False
        user_agent_id = None
        
        if user_mapping:
            user_can_call = user_mapping.get("can_make_calls", False)
            user_agent_id = user_mapping.get("tata_agent_id")
            
            # Additional check for caller ID or DID
            caller_id = user_mapping.get("tata_caller_id") or user_mapping.get("tata_did_number")
            if not caller_id and user_can_call:
                validation_errors.append("User has no caller ID configured")
                recommendations.append("Contact admin to configure caller ID/DID")
                user_can_call = False
        else:
            validation_errors.append("User is not synchronized with calling system")
            recommendations.append("Contact admin to set up calling permissions")
        
        if not user_agent_id:
            validation_errors.append("No Tata agent ID found for user")
            recommendations.append("Complete Tata system synchronization")
        
        # 3. Overall validation result
        can_call = len(validation_errors) == 0
        
        if can_call:
            recommendations.append("All validations passed - ready to make call")
        
        logger.info(f"🔍 Call validation for {validation_request.lead_id}: {'✅ PASS' if can_call else '❌ FAIL'}")
        
        return CallValidationResponse(
            can_call=can_call,
            validation_errors=validation_errors,
            lead_found=lead_found,
            lead_phone=lead_phone,
            user_can_call=user_can_call,
            user_agent_id=user_agent_id,
            estimated_setup_time=0 if can_call else 10,
            recommendations=recommendations
        )
        
    except Exception as e:
        logger.error(f"❌ Error validating call: {str(e)}")
        return CallValidationResponse(
            can_call=False,
            validation_errors=[f"Validation failed: {str(e)}"],
            lead_found=False,
            user_can_call=False,
            recommendations=["Contact support for assistance"]
        )

# =============================================================================
# PROGRESSIVE DIALER ENDPOINTS - DISABLED (PLACEHOLDER RESPONSES)
# =============================================================================

@router.post("/start-progressive-dialer")
async def start_progressive_dialer_session(
    request: Dict[str, Any],
    current_user: dict = Depends(get_current_active_user)
):
    """Progressive Dialer - DISABLED (No Call Logging)"""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Progressive Dialer service is disabled (no call logging)"
    )

@router.get("/dialer-session/{session_id}/status")
async def get_dialer_session_status(
    session_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Progressive Dialer Status - DISABLED (No Call Logging)"""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Progressive Dialer service is disabled (no call logging)"
    )

@router.post("/dialer-session/{session_id}/pause")
async def pause_dialer_session(
    session_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Progressive Dialer Pause - DISABLED (No Call Logging)"""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Progressive Dialer service is disabled (no call logging)"
    )

@router.post("/dialer-session/{session_id}/resume")
async def resume_dialer_session(
    session_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Progressive Dialer Resume - DISABLED (No Call Logging)"""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Progressive Dialer service is disabled (no call logging)"
    )

@router.post("/dialer-session/{session_id}/end")
async def end_dialer_session(
    session_id: str,
    session_summary: Optional[Dict[str, Any]] = None,
    current_user: dict = Depends(get_current_active_user)
):
    """Progressive Dialer End - DISABLED (No Call Logging)"""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Progressive Dialer service is disabled (no call logging)"
    )

@router.get("/dialer-sessions/my-sessions")
async def get_my_dialer_sessions(
    status: Optional[str] = None,
    limit: int = 20,
    current_user: dict = Depends(get_current_active_user)
):
    """Progressive Dialer Sessions - DISABLED (No Call Logging)"""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Progressive Dialer service is disabled (no call logging)"
    )

# =============================================================================
# LEGACY CLICK-TO-CALL ENDPOINT - PRESERVED (BACKWARD COMPATIBILITY)
# =============================================================================

@router.post("/click-to-call", response_model=ClickToCallResponse)
async def initiate_click_to_call(
    call_request: ClickToCallRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    📞 Legacy Click-to-Call (Complex Parameters) - BACKWARD COMPATIBILITY
    
    - **Authentication Required**: User must be logged in
    - **Permission Check**: Validates user has access to the lead
    - **User Mapping**: Checks if user is mapped to Tata system
    - **No Logging**: Direct call to TATA API without local storage
    
    **Note**: Use `/click-to-call-simple` for easier integration
    """
    try:
        logger.info(f"User {current_user['email']} initiating legacy click-to-call to {call_request.destination_number}")
        
        # Validate request
        if not call_request.destination_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Destination number is required"
            )
        
        if not call_request.lead_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lead ID is required"
            )
        
        # Initiate call through service (preserved functionality)
        success, result = await tata_call_service.initiate_click_to_call(
            lead_id=call_request.lead_id,
            destination_number=call_request.destination_number,
            current_user=current_user,
            caller_id=call_request.caller_id,
            notes=call_request.notes,
            call_timeout=call_request.call_timeout
        )
        
        # Handle tuple response from service
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Call initiation failed")
            )
        
        logger.info(f"Click-to-call initiated successfully: {result.get('call_id')}")
        
        return ClickToCallResponse(
            success=True,
            message="Call initiated successfully",
            call_id=result.get("call_id"),
            tata_call_id=result.get("tata_call_id"),
            call_status="initiated",
            estimated_connection_time=result.get("estimated_connection_time", 30),
            initiated_at=datetime.utcnow(),
            caller_number=result.get("caller_number"),
            destination_number=call_request.destination_number
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error in click-to-call: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error initiating call: {str(e)}"
        )

# =============================================================================
# SUPPORT CALL ENDPOINT - SIMPLIFIED (NO LOGGING)
# =============================================================================

@router.post("/support-call", response_model=SupportCallResponse)
async def initiate_support_call(
    support_request: SupportCallRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Initiate support call for user assistance - NO LOGGING
    
    - **Authentication Required**: User must be logged in
    - **Direct TATA API Call**: No local storage or logging
    """
    try:
        logger.info(f"User {current_user['email']} requesting support call for: {support_request.issue_type}")
        
        # Validate request
        if not support_request.issue_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Issue type is required"
            )
        
        # Initiate support call through service (preserved)
        success, result = await tata_call_service.initiate_support_call(
            customer_number=current_user.get("phone", ""),
            current_user=current_user,
            lead_id=support_request.related_lead_id,
            notes=f"{support_request.issue_type}: {support_request.description or ''}"
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Support call failed")
            )
        
        logger.info(f"Support call initiated successfully")
        
        return SupportCallResponse(
            success=True,
            message="Support call request submitted successfully",
            support_call_id=result.get("tata_call_id", "support_call"),
            ticket_number=None,
            priority=support_request.priority,
            estimated_callback_time=300,
            support_agent_info=None,
            submitted_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error in support call request: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error requesting support call: {str(e)}"
        )

# =============================================================================
# PERMISSION ENDPOINT - PRESERVED (USER SYNC FUNCTIONALITY)
# =============================================================================

@router.get("/permissions/{user_id}", response_model=CallPermissionResponse)
async def check_call_permissions(
    user_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Check if user has permissions to make calls - PRESERVED
    
    - **Self or Admin**: Users can check their own permissions, admins can check any user
    - **Tata Mapping**: Checks if user is mapped to Tata system
    - **No Call Logging**: Just permission checks
    """
    try:
        # Permission check: users can check their own permissions, admins can check any user
        if current_user["user_id"] != user_id and current_user.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only check your own call permissions"
            )
        
        logger.info(f"Checking call permissions for user {user_id}")
        
        # Get user mapping (preserved functionality)
        user_mapping = await tata_user_service.get_user_mapping(user_id)
        
        if user_mapping:
            return CallPermissionResponse(
                user_id=user_id,
                can_make_calls=user_mapping.get("can_make_calls", False),
                has_tata_mapping=True,
                tata_agent_id=user_mapping.get("tata_agent_id"),
                call_limit_remaining=None,  # No logging = no limits
                daily_call_count=0,  # No logging = no count
                permission_errors=[],
                last_call_time=None,  # No logging = no last call time
                checked_at=datetime.utcnow()
            )
        else:
            return CallPermissionResponse(
                user_id=user_id,
                can_make_calls=False,
                has_tata_mapping=False,
                tata_agent_id=None,
                permission_errors=["User not synchronized with TATA system"],
                checked_at=datetime.utcnow()
            )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error checking call permissions for user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error checking call permissions: {str(e)}"
        )

# =============================================================================
# SIMPLIFIED STATUS/MANAGEMENT ENDPOINTS (NO LOGGING)
# =============================================================================

@router.get("/status/{call_id}")
async def get_call_status(
    call_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get call status - SIMPLIFIED (No local logging)
    Returns basic status without database lookups
    """
    try:
        logger.info(f"User {current_user['email']} checking status for call {call_id}")
        
        # Since we don't store call logs, return basic response
        return {
            "success": True,
            "call_id": call_id,
            "message": "Call status not tracked (no logging enabled)",
            "note": "Use TATA dashboard for detailed call tracking",
            "checked_at": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Error checking call status {call_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error checking call status: {str(e)}"
        )

@router.post("/end/{call_id}")
async def end_call(
    call_id: str,
    call_outcome: Optional[str] = None,
    notes: Optional[str] = None,
    current_user: dict = Depends(get_current_active_user)
):
    """
    End call - SIMPLIFIED (No logging)
    Just returns success without database operations
    """
    try:
        logger.info(f"User {current_user['email']} ending call {call_id}")
        
        # Since we don't store call logs, return basic response
        return {
            "success": True,
            "message": "Call end acknowledged (no logging enabled)",
            "call_id": call_id,
            "note": "Call outcomes not stored locally - use TATA dashboard",
            "ended_at": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Error ending call {call_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error ending call: {str(e)}"
        )

@router.get("/my-active-calls")
async def get_my_active_calls(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get active calls - SIMPLIFIED (No logging)
    Returns empty since we don't track calls locally
    """
    try:
        logger.info(f"User {current_user['email']} fetching active calls")
        
        return {
            "success": True,
            "active_calls": [],
            "total_active": 0,
            "message": "Active calls not tracked locally (no logging enabled)",
            "note": "Use TATA dashboard for call monitoring",
            "retrieved_at": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Error fetching active calls: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching active calls: {str(e)}"
        )

# =============================================================================
# ADMIN ENDPOINTS - SIMPLIFIED (NO LOGGING)
# =============================================================================

@router.get("/admin/all-active-calls")
@convert_dates_to_ist()
async def get_all_active_calls(
    current_user: dict = Depends(get_admin_user)  # Admin only
):
    """
    Get all active calls - SIMPLIFIED (No logging)
    Returns empty since we don't track calls locally
    """
    try:
        logger.info(f"Admin {current_user['email']} fetching all active calls")
        
        return {
            "success": True,
            "active_calls": [],
            "total_active": 0,
            "message": "Active calls not tracked locally (no logging enabled)",
            "note": "Use TATA dashboard for system-wide call monitoring",
            "retrieved_at": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Error fetching all active calls: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching all active calls: {str(e)}"
        )

# =============================================================================
# WEBHOOK ENDPOINT - SIMPLIFIED (NO LOGGING)
# =============================================================================

@router.post("/webhook")
async def handle_tata_webhook(
    request: Request,
    webhook_payload: CallWebhookPayload
):
    """
    Handle TATA webhooks - SIMPLIFIED (No logging)
    Just acknowledges webhooks without storing data
    """
    try:
        # Get raw body for logging
        raw_body = await request.body()
        
        logger.info(f"Received Tata webhook: {webhook_payload.event_type} for call {webhook_payload.call_id}")
        logger.info(f"Webhook acknowledged but not processed (no logging enabled)")
        
        return {
            "success": True,
            "message": "Webhook acknowledged (no logging enabled)",
            "event_type": webhook_payload.event_type,
            "call_id": webhook_payload.call_id,
            "note": "Webhook data not stored locally",
            "processed_at": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error processing webhook: {str(e)}"
        )

# =============================================================================
# ROUTER METADATA
# =============================================================================

router.tags = ["Tata Calls", "Simplified Calling"]