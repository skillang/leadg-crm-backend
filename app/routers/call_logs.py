# app/routers/call_logs.py
# Call Logs & Analytics Router - Call history, analytics, and reporting

from fastapi import APIRouter, HTTPException, status, Depends, Query, Response
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime, timedelta
from bson import ObjectId

from ..services.call_log_service import call_log_service
from ..utils.dependencies import get_current_active_user, get_admin_user
from ..models.call_log import (
    CallLogResponse, CallLogListResponse, CallAnalytics,
    CallHistoryFilter, CallbackRequest, CallbackResponse,
    CallExportRequest, CallExportResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================================
# OBJECTID CONVERSION UTILITY
# ============================================================================

def convert_objectid_to_str(obj):
    """Recursively convert ObjectId to string in any data structure"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: convert_objectid_to_str(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid_to_str(item) for item in obj]
    else:
        return obj

# ============================================================================
# CALL HISTORY ENDPOINTS
# ============================================================================

@router.get("/", response_model=CallLogListResponse)
async def get_call_history(
    # Pagination
    limit: int = Query(50, ge=1, le=100, description="Number of calls to return"),
    offset: int = Query(0, ge=0, description="Number of calls to skip"),
    
    # Filtering
    call_status: Optional[str] = Query(None, description="Filter by call status"),
    call_outcome: Optional[str] = Query(None, description="Filter by call outcome"),
    assigned_user: Optional[str] = Query(None, description="Filter by user (Admin only)"),
    lead_id: Optional[str] = Query(None, description="Filter by lead ID"),
    
    # Date filtering
    start_date: Optional[datetime] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[datetime] = Query(None, description="End date (YYYY-MM-DD)"),
    
    # Sorting
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get call history with advanced filtering and pagination
    
    - **Role-based Access**: Users see only their calls, Admins see all calls
    - **Advanced Filtering**: Filter by status, outcome, user, lead, date range
    - **Pagination**: Efficient pagination for large call histories
    - **Sorting**: Sort by various fields
    """
    try:
        logger.info(f"User {current_user['email']} fetching call history")
        
        # Build filter object
        filters = CallHistoryFilter(
            call_status=call_status,
            call_outcome=call_outcome,
            assigned_user=assigned_user if current_user.get("role") == "admin" else current_user["user_id"],
            lead_id=lead_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        # Get call history through service
        result = await call_log_service.get_call_history(
            filters=filters,
            requesting_user_id=current_user["user_id"],
            user_role=current_user.get("role", "user")
        )
        
        # Convert ObjectIds
        converted_calls = convert_objectid_to_str(result["calls"])
        
        logger.info(f"Returned {len(converted_calls)} call records")
        
        return CallLogListResponse(
            calls=converted_calls,
            total_count=result["total_count"],
            limit=limit,
            offset=offset,
            has_more=result["has_more"],
            filters_applied=filters.dict(exclude_none=True),
            retrieved_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error fetching call history: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching call history: {str(e)}"
        )

@router.get("/{call_id}", response_model=CallLogResponse)
async def get_call_details(
    call_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get detailed information about a specific call
    
    - **Access Control**: Users can only view their own calls or assigned leads
    - **Complete Details**: Full call information including recordings, notes
    - **Lead Context**: Associated lead information
    """
    try:
        logger.info(f"User {current_user['email']} fetching call details: {call_id}")
        
        # Get call details through service
        call_details = await call_log_service.get_call_by_id(
            call_id=call_id,
            requesting_user_id=current_user["user_id"],
            user_role=current_user.get("role", "user")
        )
        
        if not call_details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call not found or access denied"
            )
        
        # Convert ObjectIds
        converted_call = convert_objectid_to_str(call_details)
        
        return converted_call
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error fetching call details {call_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching call details: {str(e)}"
        )

@router.get("/leads/{lead_id}")
async def get_lead_call_history(
    lead_id: str,
    limit: int = Query(20, ge=1, le=50, description="Number of calls to return"),
    offset: int = Query(0, ge=0, description="Number of calls to skip"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get call history for a specific lead
    
    - **Lead-specific**: All calls related to a specific lead
    - **Access Control**: Users can only view calls for assigned leads
    - **Timeline View**: Chronological call history for lead
    """
    try:
        logger.info(f"User {current_user['email']} fetching call history for lead: {lead_id}")
        
        # Get lead call history through service
        result = await call_log_service.get_lead_call_history(
            lead_id=lead_id,
            requesting_user_id=current_user["user_id"],
            user_role=current_user.get("role", "user"),
            limit=limit,
            offset=offset
        )
        
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found or access denied"
            )
        
        # Convert ObjectIds
        converted_calls = convert_objectid_to_str(result["calls"])
        
        return {
            "success": True,
            "lead_id": lead_id,
            "calls": converted_calls,
            "total_calls": result["total_calls"],
            "limit": limit,
            "offset": offset,
            "lead_info": result.get("lead_info", {}),
            "retrieved_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error fetching lead call history {lead_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching lead call history: {str(e)}"
        )

# ============================================================================
# CALLBACK MANAGEMENT ENDPOINTS
# ============================================================================

@router.post("/callbacks", response_model=CallbackResponse)
async def schedule_callback(
    callback_request: CallbackRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Schedule a callback for a lead
    
    - **Lead Association**: Associates callback with specific lead
    - **Scheduling**: Flexible scheduling options
    - **Notifications**: Optional notification reminders
    - **Auto-logging**: Logs callback creation to lead timeline
    """
    try:
        logger.info(f"User {current_user['email']} scheduling callback for lead: {callback_request.lead_id}")
        
        # Validate request
        if not callback_request.lead_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lead ID is required"
            )
        
        if not callback_request.scheduled_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Scheduled time is required"
            )
        
        # Schedule callback through service
        result = await call_log_service.schedule_callback(
            callback_request=callback_request,
            created_by=current_user["user_id"]
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        logger.info(f"Callback scheduled successfully: {result['callback_id']}")
        
        return CallbackResponse(
            success=True,
            message="Callback scheduled successfully",
            callback_id=result["callback_id"],
            scheduled_time=callback_request.scheduled_time,
            reminder_sent=result.get("reminder_sent", False),
            created_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error scheduling callback: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error scheduling callback: {str(e)}"
        )

@router.get("/callbacks/upcoming")
async def get_upcoming_callbacks(
    hours_ahead: int = Query(24, ge=1, le=168, description="Hours to look ahead"),
    limit: int = Query(50, ge=1, le=100, description="Number of callbacks to return"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get upcoming callbacks for the user
    
    - **User-specific**: Shows callbacks assigned to current user
    - **Time Range**: Configurable time range (default 24 hours)
    - **Reminders**: Shows callbacks needing attention
    """
    try:
        logger.info(f"User {current_user['email']} fetching upcoming callbacks")
        
        # Get upcoming callbacks through service
        callbacks = await call_log_service.get_upcoming_callbacks(
            user_id=current_user["user_id"],
            hours_ahead=hours_ahead,
            limit=limit
        )
        
        # Convert ObjectIds
        converted_callbacks = convert_objectid_to_str(callbacks)
        
        return {
            "success": True,
            "callbacks": converted_callbacks,
            "total_count": len(converted_callbacks),
            "hours_ahead": hours_ahead,
            "retrieved_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error fetching upcoming callbacks: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching upcoming callbacks: {str(e)}"
        )

@router.put("/callbacks/{callback_id}")
async def update_callback(
    callback_id: str,
    callback_update: CallbackRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Update an existing callback
    
    - **Access Control**: Users can only update their own callbacks
    - **Flexible Updates**: Update time, notes, priority
    - **Auto-logging**: Logs callback updates to lead timeline
    """
    try:
        logger.info(f"User {current_user['email']} updating callback: {callback_id}")
        
        # Update callback through service
        result = await call_log_service.update_callback(
            callback_id=callback_id,
            callback_update=callback_update,
            updated_by=current_user["user_id"]
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        logger.info(f"Callback updated successfully: {callback_id}")
        
        return {
            "success": True,
            "message": "Callback updated successfully",
            "callback_id": callback_id,
            "updated_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error updating callback {callback_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error updating callback: {str(e)}"
        )

# ============================================================================
# ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/analytics", response_model=CallAnalytics)
async def get_call_analytics(
    # Time range
    start_date: Optional[datetime] = Query(None, description="Start date for analytics"),
    end_date: Optional[datetime] = Query(None, description="End date for analytics"),
    
    # Grouping
    group_by: str = Query("day", description="Group by: hour, day, week, month"),
    
    # Filtering (Admin only)
    user_id: Optional[str] = Query(None, description="Filter by user (Admin only)"),
    team_id: Optional[str] = Query(None, description="Filter by team (Admin only)"),
    
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get comprehensive call analytics and statistics
    
    - **Role-based Data**: Users see their analytics, Admins see team analytics
    - **Time Range**: Flexible date range selection
    - **Performance Metrics**: Success rates, call duration, productivity
    - **Trend Analysis**: Call volume trends and patterns
    """
    try:
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)  # Default 30 days
        
        logger.info(f"User {current_user['email']} fetching call analytics from {start_date} to {end_date}")
        
        # Admin-only filters
        if current_user.get("role") != "admin":
            user_id = current_user["user_id"]  # Non-admins can only see their own data
            team_id = None
        
        # Get analytics through service
        analytics = await call_log_service.get_call_analytics(
            user_id=user_id,
            team_id=team_id,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by,
            requesting_user_role=current_user.get("role", "user")
        )
        
        return CallAnalytics(
            total_calls=analytics["total_calls"],
            successful_calls=analytics["successful_calls"],
            failed_calls=analytics["failed_calls"],
            success_rate=analytics["success_rate"],
            average_call_duration=analytics["average_call_duration"],
            total_call_time=analytics["total_call_time"],
            calls_by_outcome=analytics["calls_by_outcome"],
            calls_by_status=analytics["calls_by_status"],
            daily_call_trends=analytics["daily_call_trends"],
            hourly_call_patterns=analytics["hourly_call_patterns"],
            user_performance=analytics.get("user_performance", []),
            productivity_score=analytics.get("productivity_score", 0),
            date_range={
                "start_date": start_date,
                "end_date": end_date
            },
            generated_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error fetching call analytics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching call analytics: {str(e)}"
        )

# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@router.post("/export", response_model=CallExportResponse)
async def export_call_data(
    export_request: CallExportRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Export call data to various formats (CSV, Excel, PDF)
    
    - **Multiple Formats**: CSV, Excel, PDF export options
    - **Filtered Export**: Export based on filters and date ranges
    - **Role-based Access**: Users export their data, Admins export team data
    - **Background Processing**: Large exports processed in background
    """
    try:
        logger.info(f"User {current_user['email']} requesting call data export: {export_request.export_format}")
        
        # Validate export request
        if not export_request.export_format:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Export format is required"
            )
        
        # Process export through service
        result = await call_log_service.export_call_data(
            export_request=export_request,
            requesting_user_id=current_user["user_id"],
            user_role=current_user.get("role", "user")
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        logger.info(f"Call data export initiated: {result['export_id']}")
        
        return CallExportResponse(
            success=True,
            message="Export initiated successfully",
            export_id=result["export_id"],
            export_format=export_request.export_format,
            estimated_completion_time=result.get("estimated_completion_time"),
            download_url=result.get("download_url"),  # Immediate for small exports
            status="processing",
            initiated_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error initiating call data export: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error initiating export: {str(e)}"
        )

@router.get("/export/{export_id}/status")
async def get_export_status(
    export_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get status of an export job
    
    - **Export Tracking**: Track export progress and completion
    - **Download Links**: Get download URL when export is complete
    - **Error Handling**: Get error details if export failed
    """
    try:
        logger.info(f"User {current_user['email']} checking export status: {export_id}")
        
        # Get export status through service
        status_result = await call_log_service.get_export_status(
            export_id=export_id,
            requesting_user_id=current_user["user_id"]
        )
        
        if not status_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Export not found or access denied"
            )
        
        return {
            "success": True,
            "export_id": export_id,
            "status": status_result["status"],
            "progress": status_result.get("progress", 0),
            "download_url": status_result.get("download_url"),
            "error_message": status_result.get("error_message"),
            "completed_at": status_result.get("completed_at"),
            "expires_at": status_result.get("expires_at"),
            "checked_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error checking export status {export_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error checking export status: {str(e)}"
        )

# ============================================================================
# ROUTER METADATA
# ============================================================================

# Router tags and metadata for API documentation
router.tags = ["Call Logs & Analytics"]