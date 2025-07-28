# app/routers/tata_calls.py
# Tata Click-to-Call Router - Core calling functionality from CRM

from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import Dict, Any, Optional
import logging
from datetime import datetime
from bson import ObjectId

from ..services.tata_call_service import tata_call_service
from ..utils.dependencies import get_current_active_user, get_admin_user
from ..models.call_log import (
    ClickToCallRequest, ClickToCallResponse, SupportCallRequest,
    SupportCallResponse, CallPermissionResponse, CallWebhookPayload
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================================
# CLICK-TO-CALL ENDPOINTS
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
# PERMISSION AND STATUS ENDPOINTS
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
# WEBHOOK ENDPOINTS
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
# CALL MANAGEMENT ENDPOINTS
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
# ADMIN ENDPOINTS
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
router.tags = ["Tata Calls"]