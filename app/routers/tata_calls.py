# app/routers/tata_calls.py
# Enhanced Tata Calls Router - With Progressive Dialer Support
# Core calling functionality from CRM + Progressive Bulk Calling

from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime
from bson import ObjectId

# 🔧 FIX: Setup logging FIRST before using logger anywhere
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from ..services.tata_call_service import tata_call_service
from ..utils.dependencies import get_current_active_user, get_admin_user
from ..models.call_log import (
    ClickToCallRequest, ClickToCallResponse, SupportCallRequest,
    SupportCallResponse, CallPermissionResponse, CallWebhookPayload
)

# 🆕 NEW: Import Progressive Dialer Service (NOW logger is available)
try:
    from ..services.progressive_dialer_service import progressive_dialer_service
    PROGRESSIVE_DIALER_AVAILABLE = True
    logger.info("✅ Progressive Dialer service imported successfully")
except ImportError as e:
    PROGRESSIVE_DIALER_AVAILABLE = False
    logger.warning(f"⚠️ Progressive Dialer not available: {e}")

router = APIRouter()

# ============================================================================
# 🆕 NEW: PROGRESSIVE DIALER ENDPOINTS
# ============================================================================

@router.post("/start-progressive-dialer")
async def start_progressive_dialer_session(
    request: Dict[str, Any],
    current_user: dict = Depends(get_current_active_user)
):
    """
    🎯 Start Progressive Dialer Session - Multi-lead Sequential Calling
    
    - **Multi-lead Calling**: Select multiple leads for sequential calling
    - **Agent Session**: Agent stays connected throughout the session  
    - **Auto-dialing**: System automatically dials next lead after each call
    - **Real-time Control**: Pause/resume/end session as needed
    - **Lead Validation**: Ensures all leads have valid phone numbers
    """
    
    if not PROGRESSIVE_DIALER_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Progressive Dialer service is not available"
        )
    
    try:
        lead_ids = request.get("lead_ids", [])
        session_name = request.get("session_name", f"Progressive Session - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        logger.info(f"User {current_user['email']} starting progressive dialer with {len(lead_ids)} leads")
        
        # Validation
        if not lead_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one lead ID is required"
            )
        
        if len(lead_ids) > 50:  # Reasonable limit
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 50 leads allowed per session"
            )
        
        # Check if user has calling enabled
        if not current_user.get("calling_enabled"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Calling not enabled for your account. Please contact admin to set up Tata integration."
            )
        
        # Start progressive dialer session
        result = await progressive_dialer_service.start_progressive_dialer_session(
            lead_ids=lead_ids,
            current_user=current_user,
            session_name=session_name
        )
        
        if result.get("success"):
            logger.info(f"✅ Progressive dialer started successfully: Session {result.get('session_id')}")
            return {
                "success": True,
                "message": result.get("message"),
                "session_id": result.get("session_id"),
                "campaign_id": result.get("campaign_id"),
                "total_leads": result.get("total_leads"),
                "leads_preview": result.get("leads_preview", []),
                "next_steps": [
                    "1. Answer your phone when it rings to join the session",
                    "2. Leads will be connected to you automatically one by one",
                    "3. Use the session control endpoints to pause/resume/end as needed"
                ],
                "session_controls": {
                    "status_endpoint": f"/api/v1/tata-calls/dialer-session/{result.get('session_id')}/status",
                    "pause_endpoint": f"/api/v1/tata-calls/dialer-session/{result.get('session_id')}/pause",
                    "end_endpoint": f"/api/v1/tata-calls/dialer-session/{result.get('session_id')}/end"
                },
                "started_at": datetime.utcnow()
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to start progressive dialer")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Progressive dialer endpoint error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error starting progressive dialer: {str(e)}"
        )

@router.get("/dialer-session/{session_id}/status")
async def get_dialer_session_status(
    session_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    📊 Get Real-time Progressive Dialer Session Status
    
    - **Live Monitoring**: Real-time session progress and statistics
    - **Call Status**: Current call information and duration
    - **Progress Tracking**: Leads called, connected, remaining
    - **Performance Metrics**: Success rates and call statistics
    """
    
    if not PROGRESSIVE_DIALER_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Progressive Dialer service is not available"
        )
    
    try:
        user_id = str(current_user.get("user_id") or current_user.get("_id"))
        
        logger.info(f"User {current_user['email']} checking dialer session status: {session_id}")
        
        # Get session status
        result = await progressive_dialer_service.get_session_status(
            session_id=session_id,
            user_id=user_id
        )
        
        if result.get("success"):
            return {
                "success": True,
                "session_id": session_id,
                "status": result.get("status"),
                "agent_status": result.get("agent_status"),
                "current_call": result.get("current_call", {}),
                "progress": result.get("progress", {}),
                "session_duration": result.get("session_duration"),
                "performance_metrics": {
                    "total_leads": result.get("progress", {}).get("total_leads", 0),
                    "leads_called": result.get("progress", {}).get("leads_called", 0),
                    "leads_connected": result.get("progress", {}).get("leads_connected", 0),
                    "leads_remaining": result.get("progress", {}).get("leads_remaining", 0),
                    "success_rate": round(
                        (result.get("progress", {}).get("leads_connected", 0) / 
                         max(result.get("progress", {}).get("leads_called", 1), 1)) * 100, 2
                    ) if result.get("progress", {}).get("leads_called", 0) > 0 else 0
                },
                "last_updated": result.get("last_updated"),
                "checked_at": datetime.utcnow()
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result.get("message", "Session not found")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session status error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session status: {str(e)}"
        )

@router.post("/dialer-session/{session_id}/pause")
async def pause_dialer_session(
    session_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    ⏸️ Pause Progressive Dialer Session
    
    - **Session Control**: Temporarily pause the dialer session
    - **Call Completion**: Current call will complete, no new calls will be initiated
    - **Resume Ready**: Session can be resumed later
    """
    
    if not PROGRESSIVE_DIALER_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Progressive Dialer service is not available"
        )
    
    try:
        user_id = str(current_user.get("user_id") or current_user.get("_id"))
        
        logger.info(f"User {current_user['email']} pausing dialer session: {session_id}")
        
        # Pause session
        result = await progressive_dialer_service.control_session(
            session_id=session_id,
            action="pause",
            user_id=user_id
        )
        
        if result.get("success"):
            return {
                "success": True,
                "message": "Progressive dialer session paused successfully",
                "session_id": session_id,
                "status": "paused",
                "paused_at": datetime.utcnow(),
                "note": "Current call will complete. No new calls will be initiated until resumed."
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to pause session")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session pause error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause session: {str(e)}"
        )

@router.post("/dialer-session/{session_id}/resume")
async def resume_dialer_session(
    session_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    ▶️ Resume Progressive Dialer Session
    
    - **Session Control**: Resume paused dialer session
    - **Continuation**: Continues calling remaining leads
    - **State Preservation**: Maintains progress and statistics
    """
    
    if not PROGRESSIVE_DIALER_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Progressive Dialer service is not available"
        )
    
    try:
        user_id = str(current_user.get("user_id") or current_user.get("_id"))
        
        logger.info(f"User {current_user['email']} resuming dialer session: {session_id}")
        
        # Resume session
        result = await progressive_dialer_service.control_session(
            session_id=session_id,
            action="resume",
            user_id=user_id
        )
        
        if result.get("success"):
            return {
                "success": True,
                "message": "Progressive dialer session resumed successfully",
                "session_id": session_id,
                "status": "active",
                "resumed_at": datetime.utcnow(),
                "note": "Dialer will continue with remaining leads."
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to resume session")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session resume error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume session: {str(e)}"
        )

@router.post("/dialer-session/{session_id}/end")
async def end_dialer_session(
    session_id: str,
    session_summary: Optional[Dict[str, Any]] = None,
    current_user: dict = Depends(get_current_active_user)
):
    """
    🛑 End Progressive Dialer Session
    
    - **Session Termination**: Completely end the dialer session
    - **Final Summary**: Provides complete session statistics
    - **Call Completion**: Current call will complete before ending
    - **Data Preservation**: All call logs and statistics are saved
    """
    
    if not PROGRESSIVE_DIALER_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Progressive Dialer service is not available"
        )
    
    try:
        user_id = str(current_user.get("user_id") or current_user.get("_id"))
        
        logger.info(f"User {current_user['email']} ending dialer session: {session_id}")
        
        # End session
        result = await progressive_dialer_service.control_session(
            session_id=session_id,
            action="end",
            user_id=user_id,
            session_summary=session_summary
        )
        
        if result.get("success"):
            return {
                "success": True,
                "message": "Progressive dialer session ended successfully",
                "session_id": session_id,
                "status": "completed",
                "ended_at": datetime.utcnow(),
                "final_summary": result.get("final_summary", {}),
                "session_statistics": result.get("session_statistics", {}),
                "note": "All call data has been saved. Session is now closed."
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to end session")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session end error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to end session: {str(e)}"
        )

@router.get("/dialer-sessions/my-sessions")
async def get_my_dialer_sessions(
    status: Optional[str] = None,
    limit: int = 20,
    current_user: dict = Depends(get_current_active_user)
):
    """
    📋 Get My Progressive Dialer Sessions
    
    - **User Sessions**: Shows all dialer sessions for current user
    - **Status Filtering**: Filter by active, paused, completed sessions
    - **Session History**: View past session performance
    """
    
    if not PROGRESSIVE_DIALER_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Progressive Dialer service is not available"
        )
    
    try:
        user_id = str(current_user.get("user_id") or current_user.get("_id"))
        
        logger.info(f"User {current_user['email']} fetching dialer sessions")
        
        # Get user's dialer sessions
        result = await progressive_dialer_service.get_user_sessions(
            user_id=user_id,
            status_filter=status,
            limit=limit
        )
        
        if result.get("success"):
            return {
                "success": True,
                "sessions": result.get("sessions", []),
                "total_sessions": result.get("total_count", 0),
                "active_sessions": result.get("active_count", 0),
                "retrieved_at": datetime.utcnow()
            }
        else:
            return {
                "success": True,
                "sessions": [],
                "total_sessions": 0,
                "active_sessions": 0,
                "message": "No sessions found",
                "retrieved_at": datetime.utcnow()
            }
            
    except Exception as e:
        logger.error(f"Error fetching user sessions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch sessions: {str(e)}"
        )

# ============================================================================
# EXISTING CLICK-TO-CALL ENDPOINTS - UNCHANGED
# (All your existing endpoints remain exactly the same)
# ============================================================================

@router.post("/click-to-call", response_model=ClickToCallResponse)
async def initiate_click_to_call(
    call_request: ClickToCallRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Initiate click-to-call from CRM to customer
    
    - **Authentication Required**: User must be logged in
    - **Permission Check**: Validates user has access to the lead
    - **User Mapping**: Checks if user is mapped to Tata system
    - **Auto-logging**: Automatically logs call to lead timeline
    """
    try:
        logger.info(f"User {current_user['email']} initiating click-to-call to {call_request.destination_number}")
        
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
        
        # Extract user_id with fallbacks (same pattern as other endpoints)
        user_id_fallback = (current_user.get("user_id") or 
                           current_user.get("_id") or 
                           current_user.get("id") or 
                           current_user.get("email"))
        
        # Initiate call through service (fix parameters and return handling)
        success, result = await tata_call_service.initiate_click_to_call(
            lead_id=call_request.lead_id,
            destination_number=call_request.destination_number,
            current_user=current_user,  # ← Pass whole user dict
            caller_id=call_request.caller_id,  # ← Add caller_id
            notes=call_request.notes,
            call_timeout=call_request.call_timeout  # ← Add timeout if exists
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

@router.post("/support-call", response_model=SupportCallResponse)
async def initiate_support_call(
    support_request: SupportCallRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Initiate support call for user assistance
    
    - **Authentication Required**: User must be logged in
    - **Support Priority**: Automatic priority assignment based on user role
    - **Issue Tracking**: Links call to specific issue or lead
    - **Escalation**: Auto-escalation for critical issues
    """
    try:
        logger.info(f"User {current_user['email']} requesting support call for: {support_request.issue_type}")
        
        # Validate request
        if not support_request.issue_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Issue type is required"
            )
        
        # Initiate support call through service
        result = await tata_call_service.initiate_support_call(
            user_id=current_user["user_id"],
            issue_type=support_request.issue_type,
            priority=support_request.priority,
            description=support_request.description,
            related_lead_id=support_request.related_lead_id
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        logger.info(f"Support call initiated successfully: {result['support_call_id']}")
        
        return SupportCallResponse(
            success=True,
            message="Support call request submitted successfully",
            support_call_id=result["support_call_id"],
            ticket_number=result.get("ticket_number"),
            priority=result["priority"],
            estimated_callback_time=result.get("estimated_callback_time", 300),  # 5 minutes default
            support_agent_info=result.get("support_agent_info"),
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

# ============================================================================
# PERMISSION AND STATUS ENDPOINTS - UNCHANGED
# ============================================================================

@router.get("/permissions/{user_id}", response_model=CallPermissionResponse)
async def check_call_permissions(
    user_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Check if user has permissions to make calls
    
    - **Self or Admin**: Users can check their own permissions, admins can check any user
    - **Tata Mapping**: Checks if user is mapped to Tata system
    - **Call Quotas**: Checks remaining call quotas and limits
    """
    try:
        # Permission check: users can check their own permissions, admins can check any user
        if current_user["user_id"] != user_id and current_user.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only check your own call permissions"
            )
        
        logger.info(f"Checking call permissions for user {user_id}")
        
        # Check permissions through service
        permissions = await tata_call_service.check_user_call_permissions(user_id)
        
        return CallPermissionResponse(
            user_id=user_id,
            can_make_calls=permissions["can_make_calls"],
            has_tata_mapping=permissions["has_tata_mapping"],
            tata_agent_id=permissions.get("tata_agent_id"),
            call_limit_remaining=permissions.get("call_limit_remaining"),
            daily_call_count=permissions.get("daily_call_count", 0),
            permission_errors=permissions.get("permission_errors", []),
            last_call_time=permissions.get("last_call_time"),
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

@router.get("/status/{call_id}")
async def get_call_status(
    call_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get real-time status of a specific call
    
    - **Authentication Required**: User must be logged in
    - **Access Control**: Users can only check status of their own calls or assigned leads
    - **Real-time**: Returns current call status from Tata API
    """
    try:
        logger.info(f"User {current_user['email']} checking status for call {call_id}")
        
        # Get call status through service
        status_result = await tata_call_service.get_call_status(
            call_id=call_id,
            requesting_user_id=current_user["user_id"]
        )
        
        if not status_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=status_result["message"]
            )
        
        return {
            "success": True,
            "call_id": call_id,
            "call_status": status_result["call_status"],
            "call_duration": status_result.get("call_duration"),
            "connection_time": status_result.get("connection_time"),
            "end_time": status_result.get("end_time"),
            "call_outcome": status_result.get("call_outcome"),
            "last_updated": status_result.get("last_updated"),
            "tata_call_details": status_result.get("tata_call_details", {}),
            "checked_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error checking call status {call_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error checking call status: {str(e)}"
        )

# ============================================================================
# WEBHOOK ENDPOINTS - UNCHANGED
# ============================================================================

@router.post("/webhook")
async def handle_tata_webhook(
    request: Request,
    webhook_payload: CallWebhookPayload
):
    """
    Handle webhooks from Tata Tele API
    
    - **Public Endpoint**: No authentication required (webhook from Tata)
    - **Signature Verification**: Verifies webhook signature for security
    - **Event Processing**: Processes call status updates, recordings, etc.
    - **Auto-logging**: Updates call logs and lead timelines automatically
    """
    try:
        # Get raw body for signature verification
        raw_body = await request.body()
        
        logger.info(f"Received Tata webhook: {webhook_payload.event_type} for call {webhook_payload.call_id}")
        
        # Process webhook through service
        result = await tata_call_service.process_webhook(
            webhook_payload=webhook_payload,
            raw_body=raw_body,
            headers=dict(request.headers)
        )
        
        if not result["success"]:
            logger.warning(f"Webhook processing failed: {result['message']}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        logger.info(f"Webhook processed successfully: {webhook_payload.event_type}")
        
        return {
            "success": True,
            "message": "Webhook processed successfully",
            "event_type": webhook_payload.event_type,
            "call_id": webhook_payload.call_id,
            "processed_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error processing webhook: {str(e)}"
        )

# ============================================================================
# CALL MANAGEMENT ENDPOINTS - UNCHANGED
# ============================================================================

@router.post("/end/{call_id}")
async def end_call(
    call_id: str,
    call_outcome: Optional[str] = None,
    notes: Optional[str] = None,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Manually end a call and update outcome
    
    - **Authentication Required**: User must be logged in
    - **Access Control**: Users can only end their own calls
    - **Call Summary**: Updates call outcome and notes
    - **Auto-logging**: Updates lead timeline with call results
    """
    try:
        logger.info(f"User {current_user['email']} ending call {call_id}")
        
        # End call through service
        result = await tata_call_service.end_call(
            call_id=call_id,
            user_id=current_user["user_id"],
            call_outcome=call_outcome,
            notes=notes
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        logger.info(f"Call ended successfully: {call_id}")
        
        return {
            "success": True,
            "message": "Call ended successfully",
            "call_id": call_id,
            "final_status": result["final_status"],
            "call_duration": result.get("call_duration"),
            "call_outcome": call_outcome,
            "ended_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
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
    Get list of user's currently active calls
    
    - **Authentication Required**: User must be logged in
    - **User Specific**: Only returns calls for the current user
    - **Real-time**: Shows current call status
    """
    try:
        logger.info(f"User {current_user['email']} fetching active calls")
        
        # Get active calls through service
        active_calls = await tata_call_service.get_user_active_calls(
            user_id=current_user["user_id"]
        )
        
        return {
            "success": True,
            "active_calls": active_calls,
            "total_active": len(active_calls),
            "retrieved_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error fetching active calls for user {current_user['user_id']}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching active calls: {str(e)}"
        )

# ============================================================================
# ADMIN ENDPOINTS - UNCHANGED
# ============================================================================

@router.get("/admin/all-active-calls")
async def get_all_active_calls(
    current_user: dict = Depends(get_admin_user)  # Admin only
):
    """
    Get list of all currently active calls (Admin only)
    
    - **Admin Only**: Only admins can view all active calls
    - **System Overview**: Shows all active calls across all users
    - **Call Monitoring**: For call center management
    """
    try:
        logger.info(f"Admin {current_user['email']} fetching all active calls")
        
        # Get all active calls through service
        all_active_calls = await tata_call_service.get_all_active_calls()
        
        return {
            "success": True,
            "active_calls": all_active_calls,
            "total_active": len(all_active_calls),
            "retrieved_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error fetching all active calls: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching all active calls: {str(e)}"
        )

# ============================================================================
# ROUTER METADATA
# ============================================================================

# Router tags and metadata for API documentation
router.tags = ["Tata Calls", "Progressive Dialer"]