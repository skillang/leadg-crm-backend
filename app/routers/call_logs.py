# app/routers/call_logs.py
# Call Logs & Analytics Router - Call history, analytics, and reporting with Role-based Access Control

from fastapi import APIRouter, HTTPException, status, Depends, Query, Response
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime, timedelta
from bson import ObjectId

from ..services.call_log_service import call_log_service
from ..utils.dependencies import get_current_active_user
from ..models.call_log import (
    CallLogResponse, CallLogListResponse, CallAnalytics,
    CallHistoryFilter, CallbackRequest, CallbackResponse,
    CallExportRequest, CallExportResponse
)
from ..utils.tata_access_validator import validate_user_tata_access, get_empty_call_response

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================================
# UTILITY FUNCTIONS
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

def apply_role_based_filter(current_user: Dict, requested_user_id: Optional[str] = None) -> str:
    """Apply role-based filtering for user data access"""
    user_role = current_user.get("role")
    current_user_id = str(current_user.get("user_id") or current_user.get("_id", ""))
    
    if user_role == "admin":
        # Admins can access any user's data
        return requested_user_id or current_user_id
    else:
        # Regular users can only access their own data
        if requested_user_id and requested_user_id != current_user_id:
            logger.warning(f"User {current_user.get('email')} attempted to access data for user {requested_user_id}")
        return current_user_id

# ============================================================================
# CALL HISTORY ENDPOINTS - ENHANCED WITH ROLE-BASED ACCESS
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
    Get call history with advanced filtering and pagination - Role-based access
    
    - **Role-based Access**: Users see only their calls, Admins see all calls
    - **Advanced Filtering**: Filter by status, outcome, user, lead, date range
    - **Pagination**: Efficient pagination for large call histories
    - **Sorting**: Sort by various fields
    """
    try:
        user_role = current_user.get("role")
        current_user_id = str(current_user.get("user_id") or current_user.get("_id", ""))
        
        # Role-based filtering for assigned_user
        if user_role != "admin":
            # Non-admin users can only see their own calls
            assigned_user = current_user_id
            logger.info(f"Non-admin user {current_user.get('email')} restricted to own call history")
        else:
            # Admins can filter by specific user or see all
            logger.info(f"Admin {current_user.get('email')} fetching call history - User filter: {assigned_user or 'all users'}")
        
        logger.info(f"User {current_user['email']} fetching call history - Role: {user_role}")
        
        # Build filter object with role-based restrictions
        filters = CallHistoryFilter(
            call_status=call_status,
            call_outcome=call_outcome,
            assigned_user=assigned_user,
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
            requesting_user_id=current_user_id,
            user_role=user_role
        )
        
        # Convert ObjectIds
        converted_calls = convert_objectid_to_str(result["calls"])
        
        logger.info(f"Returned {len(converted_calls)} call records for {user_role}")
        
        return CallLogListResponse(
            calls=converted_calls,
            total_count=result["total_count"],
            limit=limit,
            offset=offset,
            has_more=result["has_more"],
            user_role=user_role,
            data_scope="all_users" if user_role == "admin" else "current_user_only",
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
    Get detailed information about a specific call - Role-based access
    
    - **Access Control**: Users can only view their own calls or assigned leads
    - **Complete Details**: Full call information including recordings, notes
    - **Lead Context**: Associated lead information
    """
    try:
        user_role = current_user.get("role")
        current_user_id = str(current_user.get("user_id") or current_user.get("_id", ""))
        
        logger.info(f"User {current_user['email']} fetching call details: {call_id} - Role: {user_role}")
        
        # Get call details through service with role-based access
        call_details = await call_log_service.get_call_by_id(
            call_id=call_id,
            requesting_user_id=current_user_id,
            user_role=user_role
        )
        
        if not call_details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call not found or access denied"
            )
        
        # Convert ObjectIds
        converted_call = convert_objectid_to_str(call_details)
        
        # Add role information to response
        converted_call["viewer_role"] = user_role
        converted_call["access_level"] = "admin" if user_role == "admin" else "own_data_only"
        
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
    Get call history for a specific lead - Role-based access
    
    - **Lead-specific**: All calls related to a specific lead
    - **Access Control**: Users can only view calls for assigned leads
    - **Timeline View**: Chronological call history for lead
    """
    try:
        user_role = current_user.get("role")
        current_user_id = str(current_user.get("user_id") or current_user.get("_id", ""))
        
        logger.info(f"User {current_user['email']} fetching call history for lead: {lead_id} - Role: {user_role}")
        
        # Get lead call history through service with role-based access
        result = await call_log_service.get_lead_call_history(
            lead_id=lead_id,
            requesting_user_id=current_user_id,
            user_role=user_role,
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
            "viewer_role": user_role,
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
# CALLBACK MANAGEMENT ENDPOINTS - ENHANCED WITH ROLE-BASED ACCESS
# ============================================================================

@router.post("/callbacks", response_model=CallbackResponse)
async def schedule_callback(
    callback_request: CallbackRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Schedule a callback for a lead - Role-based access
    
    - **Lead Association**: Associates callback with specific lead
    - **Scheduling**: Flexible scheduling options
    - **Access Control**: Users can only schedule callbacks for assigned leads
    - **Auto-logging**: Logs callback creation to lead timeline
    """
    try:
        user_role = current_user.get("role")
        current_user_id = str(current_user.get("user_id") or current_user.get("_id", ""))
        
        logger.info(f"User {current_user['email']} scheduling callback for lead: {callback_request.lead_id} - Role: {user_role}")
        
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
        
        # Schedule callback through service with role-based access control
        result = await call_log_service.schedule_callback(
            callback_request=callback_request,
            created_by=current_user_id,
            user_role=user_role
        )
        
        if not result["success"]:
            if "access denied" in result["message"].lower():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=result["message"]
                )
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
            user_role=user_role,
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
    user_filter: Optional[str] = Query(None, description="Filter by user ID (Admin only)"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get upcoming callbacks with role-based filtering
    
    - **Role-based Access**: Users see only their callbacks, Admins can see all or filter by user
    - **Time Range**: Configurable time range (default 24 hours)
    - **Reminders**: Shows callbacks needing attention
    """
    try:
        user_role = current_user.get("role")
        current_user_id = str(current_user.get("user_id") or current_user.get("_id", ""))
        
        # Apply role-based filtering
        target_user_id = apply_role_based_filter(current_user, user_filter)
        
        if user_role != "admin" and user_filter and user_filter != current_user_id:
            logger.warning(f"Non-admin user {current_user.get('email')} attempted to filter callbacks by user {user_filter}")
        
        logger.info(f"User {current_user['email']} fetching upcoming callbacks - Role: {user_role}, Target User: {target_user_id}")
        
        # Get upcoming callbacks through service
        callbacks = await call_log_service.get_upcoming_callbacks(
            user_id=target_user_id,
            hours_ahead=hours_ahead,
            limit=limit,
            requesting_user_role=user_role
        )
        
        # Convert ObjectIds
        converted_callbacks = convert_objectid_to_str(callbacks)
        
        return {
            "success": True,
            "callbacks": converted_callbacks,
            "total_count": len(converted_callbacks),
            "hours_ahead": hours_ahead,
            "user_role": user_role,
            "data_scope": "all_users" if user_role == "admin" and not user_filter else "filtered_user",
            "filtered_user_id": target_user_id if user_role != "admin" or user_filter else None,
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
    Update an existing callback with role-based access control
    
    - **Access Control**: Users can only update their own callbacks
    - **Flexible Updates**: Update time, notes, priority
    - **Auto-logging**: Logs callback updates to lead timeline
    """
    try:
        user_role = current_user.get("role")
        current_user_id = str(current_user.get("user_id") or current_user.get("_id", ""))
        
        logger.info(f"User {current_user['email']} updating callback: {callback_id} - Role: {user_role}")
        
        # Update callback through service with role-based access control
        result = await call_log_service.update_callback(
            callback_id=callback_id,
            callback_update=callback_update,
            updated_by=current_user_id,
            user_role=user_role
        )
        
        if not result["success"]:
            if "access denied" in result["message"].lower() or "not authorized" in result["message"].lower():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=result["message"]
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        logger.info(f"Callback updated successfully: {callback_id}")
        
        return {
            "success": True,
            "message": "Callback updated successfully",
            "callback_id": callback_id,
            "user_role": user_role,
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
# ANALYTICS ENDPOINTS - ENHANCED WITH ROLE-BASED ACCESS
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
    Get comprehensive call analytics and statistics with enhanced role-based access
    
    - **Role-based Data**: Users see their analytics, Admins see team analytics
    - **Time Range**: Flexible date range selection
    - **Performance Metrics**: Success rates, call duration, productivity
    - **Trend Analysis**: Call volume trends and patterns
    """
    try:
        user_role = current_user.get("role")
        current_user_id = str(current_user.get("user_id") or current_user.get("_id", ""))
        
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)  # Default 30 days
        
        # Enhanced role-based filtering
# Enhanced role-based filtering
        if user_role != "admin":
            # Non-admin users can only see their own data
            user_id = current_user_id
            team_id = None
            logger.info(f"Non-admin user {current_user.get('email')} restricted to own analytics data")
            
            # 🔥 CRITICAL SECURITY FIX: Check if user has TATA mapping
            has_tata_mapping = False
            for mapping in await get_user_tata_mappings():  # You'll need to implement this
                if mapping.get("crm_user_id") == current_user_id:
                    has_tata_mapping = True
                    break
            
            if not has_tata_mapping:
                logger.info(f"Non-TATA user {current_user.get('email')} has no call analytics access")
                return CallAnalytics(
                    total_calls=0,
                    successful_calls=0,
                    failed_calls=0,
                    success_rate=0.0,
                    average_call_duration=0.0,
                    total_call_time=0,
                    calls_by_outcome={},
                    calls_by_status={},
                    daily_call_trends=[],
                    hourly_call_patterns={},
                    user_performance=[],
                    productivity_score=0,
                    user_role=user_role,
                    data_scope="no_call_access",
                    filtered_user_id=current_user_id,
                    access_level="non_tata_user",
                    message="Call analytics require TATA integration"
                )
        else:
            # Apply admin filters or default to requesting user if no filters specified
            user_id = apply_role_based_filter(current_user, user_id)
            logger.info(f"Admin {current_user.get('email')} fetching analytics - User: {user_id or 'all'}, Team: {team_id or 'all'}")
        
        # Get analytics through service
        analytics = await call_log_service.get_call_analytics(
            user_id=user_id,
            team_id=team_id,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by,
            requesting_user_role=user_role,
            requesting_user_id=current_user_id
        )
        
        # Build response with role information
        analytics_response = CallAnalytics(
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
            # Enhanced metadata
            user_role=user_role,
            data_scope="all_users" if user_role == "admin" and not user_id else "filtered_user",
            filtered_user_id=user_id if user_role != "admin" or user_id else None,
            date_range={
                "start_date": start_date,
                "end_date": end_date
            },
            generated_at=datetime.utcnow()
        )
        
        return analytics_response
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error fetching call analytics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching call analytics: {str(e)}"
        )

# ============================================================================
# EXPORT ENDPOINTS - ENHANCED WITH ROLE-BASED ACCESS
# ============================================================================

@router.post("/export", response_model=CallExportResponse)
async def export_call_data(
    export_request: CallExportRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Export call data to various formats with role-based access control
    
    - **Multiple Formats**: CSV, Excel, PDF export options
    - **Filtered Export**: Export based on filters and date ranges
    - **Role-based Access**: Users export their data, Admins export team data
    - **Background Processing**: Large exports processed in background
    """
    try:
        user_role = current_user.get("role")
        current_user_id = str(current_user.get("user_id") or current_user.get("_id", ""))
        
        logger.info(f"User {current_user['email']} requesting call data export: {export_request.export_format} - Role: {user_role}")
        
        # Validate export request
        if not export_request.export_format:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Export format is required"
            )
        
        # Apply role-based restrictions to export request
        if user_role != "admin":
            # Non-admin users can only export their own data
            export_request.user_filter = current_user_id
            export_request.team_filter = None
            logger.info(f"Non-admin user {current_user.get('email')} export restricted to own data")
        
        # Process export through service with role-based access control
        result = await call_log_service.export_call_data(
            export_request=export_request,
            requesting_user_id=current_user_id,
            user_role=user_role
        )
        
        if not result["success"]:
            if "access denied" in result["message"].lower():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=result["message"]
                )
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
            user_role=user_role,
            data_scope="all_users" if user_role == "admin" else "current_user_only",
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
    Get status of an export job with role-based access control
    
    - **Export Tracking**: Track export progress and completion
    - **Access Control**: Users can only check their own export status
    - **Download Links**: Get download URL when export is complete
    - **Error Handling**: Get error details if export failed
    """
    try:
        user_role = current_user.get("role")
        current_user_id = str(current_user.get("user_id") or current_user.get("_id", ""))
        
        logger.info(f"User {current_user['email']} checking export status: {export_id} - Role: {user_role}")
        
        # Get export status through service with role-based access control
        status_result = await call_log_service.get_export_status(
            export_id=export_id,
            requesting_user_id=current_user_id,
            user_role=user_role
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
            "user_role": user_role,
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
# ADDITIONAL ROLE-BASED ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/my-performance")
async def get_my_call_performance(
    days_back: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    include_comparisons: bool = Query(True, description="Include period comparisons"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get current user's call performance analytics - Always user-specific
    
    - **Personal Analytics**: Always shows current user's performance
    - **Performance Trends**: Success rates, call volumes, efficiency metrics
    - **Comparisons**: Compare with previous periods
    """
    try:
        user_role = current_user.get("role")
        current_user_id = str(current_user.get("user_id") or current_user.get("_id", ""))
        
        logger.info(f"User {current_user['email']} fetching personal performance - Role: {user_role}")
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        
        # Get personal analytics (always for current user regardless of role)
        performance = await call_log_service.get_user_performance_analytics(
            user_id=current_user_id,
            start_date=start_date,
            end_date=end_date,
            include_comparisons=include_comparisons
        )
        
        return {
            "success": True,
            "user_id": current_user_id,
            "user_email": current_user.get("email"),
            "user_role": user_role,
            "analysis_period": f"{days_back} days",
            "date_range": {
                "start_date": start_date,
                "end_date": end_date
            },
            "performance_metrics": performance,
            "generated_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching personal performance: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching personal performance: {str(e)}"
        )

@router.get("/team-performance")
async def get_team_call_performance(
    days_back: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    team_id: Optional[str] = Query(None, description="Specific team ID"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get team call performance analytics - Admin only
    
    - **Admin Only**: Only administrators can view team performance
    - **Team Analytics**: Success rates, call volumes, team efficiency
    - **Comparisons**: Team performance trends and rankings
    """
    try:
        user_role = current_user.get("role")
        
        # Only admins can view team performance
        if user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can view team performance analytics"
            )
        
        logger.info(f"Admin {current_user['email']} fetching team performance - Team: {team_id or 'all teams'}")
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        
        # Get team analytics
        team_performance = await call_log_service.get_team_performance_analytics(
            team_id=team_id,
            start_date=start_date,
            end_date=end_date,
            requesting_admin_id=str(current_user.get("user_id") or current_user.get("_id", ""))
        )
        
        return {
            "success": True,
            "user_role": user_role,
            "team_id": team_id or "all_teams",
            "analysis_period": f"{days_back} days",
            "date_range": {
                "start_date": start_date,
                "end_date": end_date
            },
            "team_metrics": team_performance,
            "generated_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching team performance: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching team performance: {str(e)}"
        )

# ============================================================================
# USER ACTIVITY ENDPOINTS - ROLE-BASED ACCESS
# ============================================================================

@router.get("/activity/recent")
async def get_recent_call_activity(
    limit: int = Query(20, ge=1, le=100, description="Number of recent activities"),
    user_filter: Optional[str] = Query(None, description="Filter by user ID (Admin only)"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get recent call activity with role-based filtering
    
    - **Role-based Access**: Users see own activity, Admins can filter by user
    - **Activity Timeline**: Recent calls, callbacks, and call outcomes
    - **Real-time Updates**: Latest call activity and status changes
    """
    try:
        user_role = current_user.get("role")
        current_user_id = str(current_user.get("user_id") or current_user.get("_id", ""))
        
        # Apply role-based filtering
        target_user_id = apply_role_based_filter(current_user, user_filter)
        
        logger.info(f"User {current_user['email']} fetching recent activity - Role: {user_role}, Target: {target_user_id}")
        
        # Get recent activity
        activity = await call_log_service.get_recent_call_activity(
            user_id=target_user_id,
            limit=limit,
            requesting_user_role=user_role
        )
        
        # Convert ObjectIds
        converted_activity = convert_objectid_to_str(activity)
        
        return {
            "success": True,
            "activities": converted_activity,
            "user_role": user_role,
            "data_scope": "all_users" if user_role == "admin" and not user_filter else "filtered_user",
            "filtered_user_id": target_user_id if user_role != "admin" or user_filter else None,
            "limit": limit,
            "retrieved_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching recent activity: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching recent activity: {str(e)}"
        )

# ============================================================================
# CALL QUALITY ENDPOINTS - ROLE-BASED ACCESS
# ============================================================================

@router.get("/quality-metrics")
async def get_call_quality_metrics(
    start_date: Optional[datetime] = Query(None, description="Start date for quality analysis"),
    end_date: Optional[datetime] = Query(None, description="End date for quality analysis"),
    user_filter: Optional[str] = Query(None, description="Filter by user ID (Admin only)"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get call quality metrics with role-based access
    
    - **Role-based Data**: Users see own metrics, Admins can filter by user
    - **Quality Analysis**: Call duration, success rates, conversion metrics
    - **Performance Indicators**: Key quality indicators and trends
    """
    try:
        user_role = current_user.get("role")
        current_user_id = str(current_user.get("user_id") or current_user.get("_id", ""))
        
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # Apply role-based filtering
        target_user_id = apply_role_based_filter(current_user, user_filter)
        
        logger.info(f"User {current_user['email']} fetching quality metrics - Role: {user_role}, Target: {target_user_id}")
        
        # Get quality metrics
        quality_metrics = await call_log_service.get_call_quality_metrics(
            user_id=target_user_id,
            start_date=start_date,
            end_date=end_date,
            requesting_user_role=user_role
        )
        
        return {
            "success": True,
            "quality_metrics": quality_metrics,
            "user_role": user_role,
            "data_scope": "all_users" if user_role == "admin" and not user_filter else "filtered_user",
            "filtered_user_id": target_user_id if user_role != "admin" or user_filter else None,
            "date_range": {
                "start_date": start_date,
                "end_date": end_date
            },
            "generated_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching quality metrics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error fetching quality metrics: {str(e)}"
        )

# ============================================================================
# BATCH OPERATIONS - ROLE-BASED ACCESS
# ============================================================================

@router.post("/batch/mark-completed")
async def batch_mark_calls_completed(
    call_ids: List[str],
    outcome: str = Query(..., description="Call outcome to set"),
    notes: Optional[str] = Query(None, description="Additional notes"),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Batch mark multiple calls as completed with role-based access control
    
    - **Access Control**: Users can only mark their own calls, Admins can mark any calls
    - **Batch Operations**: Efficient bulk updates for multiple calls
    - **Audit Trail**: Logs all batch operations for compliance
    """
    try:
        user_role = current_user.get("role")
        current_user_id = str(current_user.get("user_id") or current_user.get("_id", ""))
        
        if not call_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Call IDs are required"
            )
        
        logger.info(f"User {current_user['email']} batch marking {len(call_ids)} calls - Role: {user_role}")
        
        # Process batch operation with role-based access control
        result = await call_log_service.batch_mark_calls_completed(
            call_ids=call_ids,
            outcome=outcome,
            notes=notes,
            updated_by=current_user_id,
            user_role=user_role
        )
        
        if not result["success"]:
            if "access denied" in result["message"].lower():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=result["message"]
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        logger.info(f"Batch operation completed: {result['updated_count']} calls updated")
        
        return {
            "success": True,
            "message": f"Successfully updated {result['updated_count']} calls",
            "updated_count": result["updated_count"],
            "failed_count": result.get("failed_count", 0),
            "user_role": user_role,
            "failed_ids": result.get("failed_ids", []),
            "updated_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch call update: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error in batch operation: {str(e)}"
        )

# ============================================================================
# ROUTER METADATA AND CONFIGURATION
# ============================================================================

# Router tags and metadata for API documentation
router.tags = ["Call Logs & Analytics - Role-based Access"]

# Additional router configuration
def configure_call_logs_router():
    """Configure additional router settings and middleware if needed"""
    pass

# Initialize router configuration
configure_call_logs_router()