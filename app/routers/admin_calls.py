# app/routers/admin_calls.py
# OPTIMIZED Admin Call Dashboard API Endpoints
# Uses TATA API server-side filtering - REMOVED Python filtering and debug endpoints

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime, timedelta
import calendar
from collections import defaultdict

from ..services.tata_admin_service import tata_admin_service
from ..services.tata_auth_service import tata_auth_service
from ..utils.performance_calculator import performance_calculator
from ..models.admin_dashboard import (
    AdminDashboardResponse, UserPerformanceResponse, PerformanceRankingResponse,
    RecordingPlayResponse, FilterOptionsResponse, DashboardFilters,
    UserPerformanceRequest, PlayRecordingRequest, PerformancePeriod,
    CallStatusFilter, CallDirectionFilter, DashboardError,
    ComprehensivePeakHoursResponse, PeakAnsweredHoursResponse, PeakMissedHoursResponse
)
from ..utils.dependencies import get_admin_user, get_current_active_user

logger = logging.getLogger(__name__)
router = APIRouter()

# =============================================================================
# MAIN DASHBOARD ENDPOINT - OPTIMIZED WITH TATA API FILTERING
# =============================================================================

@router.get("/call-dashboard")
async def get_admin_call_dashboard(
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    period: str = Query("daily", description="Performance period"),
    
    # TATA API Filter Parameters
    agents: Optional[str] = Query(None, description="Comma-separated agent numbers or user IDs"),
    call_type: Optional[str] = Query(None, description="Call type filter: c=answered, m=missed"),
    direction: Optional[str] = Query(None, description="Call direction: inbound/outbound"),
    department: Optional[str] = Query(None, description="Comma-separated department IDs"),
    duration: Optional[str] = Query(None, description="Duration value for filtering"),
    operator: Optional[str] = Query(None, description="Duration operator: >, <, >=, <=, !="),
    callerid: Optional[str] = Query(None, description="Filter by caller ID"),
    destination: Optional[str] = Query(None, description="Filter by destination number"),
    services: Optional[str] = Query(None, description="Comma-separated services"),
    did_number: Optional[str] = Query(None, description="Filter by DID number"),
    broadcast: Optional[str] = Query(None, description="Filter broadcast calls"),
    ivr: Optional[str] = Query(None, description="Comma-separated IVR IDs"),
    
    # Legacy parameters (converted to TATA format)
    user_ids: Optional[str] = Query(None, description="Comma-separated user IDs (converted to agents)"),
    call_status: str = Query("all", description="Call status: all/answered/missed (converted to call_type)"),
    call_direction: str = Query("all", description="Call direction: all/inbound/outbound (converted to direction)"),
    
    # Pagination
    limit: int = Query(50, ge=1, le=500, description="Records per page"),
    page: int = Query(1, ge=1, description="Page number"),
    current_user: Dict = Depends(get_admin_user)
):
    """
    OPTIMIZED Admin dashboard using TATA API server-side filtering
    Removed Python filtering - uses TATA query parameters directly
    """
    try:
        logger.info(f"Admin {current_user.get('email')} requesting optimized call dashboard")
        
        # Initialize agent mapping
        await tata_admin_service.initialize_agent_mapping()
        
        # Set default date range
        if not date_from or not date_to:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            date_from = start_date.strftime("%Y-%m-%d")
            date_to = end_date.strftime("%Y-%m-%d")
        
        # Format dates for TATA API
        from_date = f"{date_from} 00:00:00"
        to_date = f"{date_to} 23:59:59"
        
        # Build TATA API query parameters
        tata_params = {
            'from_date': from_date,
            'to_date': to_date,
            'page': str(page),
            'limit': str(limit)
        }
        
        # Convert legacy user_ids to agents parameter
        if user_ids and not agents:
            user_list = [uid.strip() for uid in user_ids.split(",")]
            agent_numbers = []
            
            for user_id in user_list:
                for agent_number, mapping in tata_admin_service.agent_user_mapping.items():
                    if mapping.get("user_id") == user_id:
                        agent_numbers.append(agent_number)
                        break
            
            if agent_numbers:
                agents = ",".join(agent_numbers)
                logger.info(f"Converted user_ids {user_ids} to agents {agents}")
        
        # Convert legacy call_status to call_type
        if call_status != "all" and not call_type:
            call_type = "c" if call_status == "answered" else "m"
        
        # Convert legacy call_direction to direction
        if call_direction != "all" and not direction:
            direction = call_direction
        
        # Apply TATA API filters
        if agents:
            tata_params['agents'] = agents
            
        if call_type:
            tata_params['call_type'] = call_type
            
        if direction:
            tata_params['direction'] = direction
            
        if department:
            tata_params['department'] = department
            
        if duration and operator:
            tata_params['duration'] = duration
            tata_params['operator'] = operator
            
        if callerid:
            tata_params['callerid'] = callerid
            
        if destination:
            tata_params['destination'] = destination
            
        if services:
            tata_params['services'] = services
            
        if did_number:
            tata_params['did_number'] = did_number
            
        if broadcast:
            tata_params['broadcast'] = broadcast
            
        if ivr:
            tata_params['ivr'] = ivr
        
        logger.info(f"TATA API call with params: {tata_params}")
        
        # Make single optimized TATA API call
        tata_response = await tata_admin_service.fetch_call_records_with_filters(
            params=tata_params
        )
        
        if not tata_response.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"TATA API call failed: {tata_response.get('error')}"
            )
        
        # Extract data from TATA response
        tata_data = tata_response.get("data", {})
        call_records = tata_data.get("results", [])
        total_count = tata_data.get("count", 0)
        
        logger.info(f"TATA API returned {len(call_records)} records out of {total_count} total")
        
        # Calculate statistics directly from TATA filtered data
        user_stats_dict = {}
        if call_records:
            if period == "daily":
                user_stats_dict = tata_admin_service.calculate_daily_stats(call_records, date_from)
            elif period == "weekly":
                week_start = datetime.strptime(date_from, "%Y-%m-%d")
                week_key = f"{week_start.year}-W{week_start.isocalendar()[1]:02d}"
                user_stats_dict = tata_admin_service.calculate_period_stats(call_records, "weekly", week_key)
            elif period == "monthly":
                month_key = date_from[:7]
                user_stats_dict = tata_admin_service.calculate_period_stats(call_records, "monthly", month_key)
        
        # Process recent calls
        recent_calls = []
        for record in call_records:
            try:
                parsed_record = tata_admin_service.parse_call_record(record)
                recent_calls.append(parsed_record)
            except Exception as e:
                logger.warning(f"Error parsing call record: {e}")
                continue
        
        # Calculate top performers
        top_performers = []
        if user_stats_dict:
            try:
                top_performers = performance_calculator.rank_performers(
                    user_stats=user_stats_dict,
                    period=period,
                    top_n=10
                )
            except Exception as e:
                logger.warning(f"Error calculating top performers: {e}")
        
        # Calculate summary statistics
        total_calls = len(call_records)
        total_answered = sum(1 for r in call_records if r.get("status") == "answered")
        total_recordings = sum(1 for r in call_records if r.get("recording_url"))
        overall_success_rate = (total_answered / total_calls * 100) if total_calls > 0 else 0.0
        
        # Build optimized response
        response_data = {
            "success": True,
            "total_calls": total_calls,
            "total_count_all_pages": total_count,
            "total_users": len(user_stats_dict),
            "total_recordings": total_recordings,
            "overall_success_rate": round(overall_success_rate, 2),
            "user_stats": list(user_stats_dict.values()),
            "recent_calls": recent_calls,
            "top_performers": top_performers,
            "date_range": f"{date_from} to {date_to}",
            "data_fetched_at": datetime.utcnow(),
            "pagination": {
                "current_page": page,
                "limit": limit,
                "total_pages": (total_count + limit - 1) // limit if total_count > 0 else 1,
                "has_more": page * limit < total_count
            },
            "filters_applied": {
                "date_from": date_from,
                "date_to": date_to,
                "period": period,
                "tata_filters": {k: v for k, v in tata_params.items() if k not in ['from_date', 'to_date', 'page', 'limit']}
            },
            "optimization_info": {
                "filtering_method": "tata_api_server_side",
                "python_filtering_removed": True,
                "api_calls_made": 1,
                "records_processed": len(call_records)
            }
        }
        
        # Log admin activity
        try:
            await tata_admin_service.log_admin_activity(
                admin_user_id=str(current_user.get("user_id") or current_user.get("_id", "unknown")),
                admin_email=current_user.get("email", "unknown"),
                action="viewed_call_dashboard_optimized",
                details={
                    "date_range": f"{date_from} to {date_to}",
                    "period": period,
                    "total_records": total_calls,
                    "filtering_method": "tata_api_server_side",
                    "filters_used": len([k for k, v in tata_params.items() if k not in ['from_date', 'to_date', 'page', 'limit']])
                }
            )
        except Exception as e:
            logger.warning(f"Error logging admin activity: {e}")
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in optimized admin call dashboard: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": str(e),
                "message": "Failed to fetch optimized dashboard data"
            }
        )

# =============================================================================
# USER PERFORMANCE ENDPOINT - OPTIMIZED
# =============================================================================

@router.get("/user-performance/{user_id}")
async def get_user_call_performance(
    user_id: str,
    period: str = Query("weekly", description="Analysis period"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    include_day_comparison: bool = Query(True, description="Include day-to-day comparison"),
    current_user: Dict = Depends(get_admin_user)
):
    """
    OPTIMIZED User performance using TATA API filtering by agent
    """
    try:
        logger.info(f"Admin {current_user.get('email')} requesting optimized performance for user {user_id}")
        
        # Initialize agent mapping
        await tata_admin_service.initialize_agent_mapping()
        
        # Find user's agent number
        user_agent_number = None
        user_name = "Unknown"
        for agent_number, mapping in tata_admin_service.agent_user_mapping.items():
            if mapping.get("user_id") == user_id:
                user_agent_number = agent_number
                user_name = mapping.get("user_name", "Unknown")
                break
        
        if not user_agent_number:
            available_users = [
                {"user_id": m["user_id"], "user_name": m["user_name"]}
                for m in tata_admin_service.agent_user_mapping.values()
                if m.get("user_id") and m.get("user_name")
            ]
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "user_not_found",
                    "message": f"User {user_id} not found in agent mapping",
                    "available_users": available_users[:10]
                }
            )
        
        # Set date range
        if not date_from or not date_to:
            end_date = datetime.now()
            if period == "daily":
                start_date = end_date
            elif period == "weekly":
                start_date = end_date - timedelta(days=7)
            else:  # monthly
                start_date = end_date - timedelta(days=30)
            
            date_from = start_date.strftime("%Y-%m-%d")
            date_to = end_date.strftime("%Y-%m-%d")
        
        # Format dates for TATA API
        from_date = f"{date_from} 00:00:00"
        to_date = f"{date_to} 23:59:59"
        
        logger.info(f"Fetching optimized user performance for {user_name} ({user_agent_number})")
        
        # Use TATA API filtering by agent
        tata_params = {
            'from_date': from_date,
            'to_date': to_date,
            'agents': user_agent_number,  # Filter by specific agent
            'page': '1',
            'limit': '1000'  # Get enough records for analysis
        }
        
        # Make TATA API call with agent filter
        tata_response = await tata_admin_service.fetch_call_records_with_filters(
            params=tata_params
        )
        
        if not tata_response.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"TATA API call failed: {tata_response.get('error')}"
            )
        
        # Extract filtered user call records
        tata_data = tata_response.get("data", {})
        user_call_records = tata_data.get("results", [])
        
        logger.info(f"TATA API returned {len(user_call_records)} records for user {user_name}")
        
        # Calculate stats from TATA filtered data
        if user_call_records:
            total_calls = len(user_call_records)
            answered_calls = sum(1 for r in user_call_records if r.get("status") == "answered")
            missed_calls = total_calls - answered_calls
            total_duration = sum(r.get("call_duration", 0) for r in user_call_records if r.get("status") == "answered")
            recordings_count = sum(1 for r in user_call_records if r.get("recording_url"))
            
            success_rate = (answered_calls / total_calls * 100) if total_calls > 0 else 0.0
            avg_duration = (total_duration / answered_calls) if answered_calls > 0 else 0.0
            
            # Build period-specific stats
            user_stats_data = {
                "user_id": user_id,
                "user_name": user_name,
                "agent_number": user_agent_number,
                "success_rate": round(success_rate, 2),
                "avg_call_duration": round(avg_duration, 2)
            }
            
            # Set period-specific fields
            if period == "daily":
                user_stats_data.update({
                    "daily_calls": total_calls,
                    "daily_answered": answered_calls,
                    "daily_missed": missed_calls,
                    "daily_duration": total_duration,
                    "daily_recordings": recordings_count
                })
            elif period == "weekly":
                user_stats_data.update({
                    "weekly_calls": total_calls,
                    "weekly_answered": answered_calls,
                    "weekly_missed": missed_calls,
                    "weekly_duration": total_duration,
                    "weekly_recordings": recordings_count
                })
            else:  # monthly
                user_stats_data.update({
                    "monthly_calls": total_calls,
                    "monthly_answered": answered_calls,
                    "monthly_missed": missed_calls,
                    "monthly_duration": total_duration,
                    "monthly_recordings": recordings_count
                })
        else:
            # No records found
            user_stats_data = {
                "user_id": user_id,
                "user_name": user_name,
                "agent_number": user_agent_number,
                "daily_calls": 0,
                "daily_answered": 0,
                "daily_missed": 0,
                "success_rate": 0.0,
                "avg_call_duration": 0.0
            }
        
        # Calculate day-to-day comparison if requested
        day_comparison = []
        if include_day_comparison and user_call_records:
            daily_breakdown = defaultdict(lambda: {
                "total_calls": 0, "answered_calls": 0, "missed_calls": 0, 
                "total_duration": 0, "recordings_count": 0
            })
            
            for record in user_call_records:
                record_date = record.get("date", "")
                if record_date:
                    daily_breakdown[record_date]["total_calls"] += 1
                    if record.get("status") == "answered":
                        daily_breakdown[record_date]["answered_calls"] += 1
                        daily_breakdown[record_date]["total_duration"] += record.get("call_duration", 0)
                    else:
                        daily_breakdown[record_date]["missed_calls"] += 1
                    
                    if record.get("recording_url"):
                        daily_breakdown[record_date]["recordings_count"] += 1
            
            # Convert to comparison format
            sorted_dates = sorted(daily_breakdown.keys())
            for i, date in enumerate(sorted_dates):
                stats = daily_breakdown[date]
                success_rate = (stats["answered_calls"] / stats["total_calls"] * 100) if stats["total_calls"] > 0 else 0.0
                
                calls_change = 0
                calls_change_percent = 0.0
                trend = "stable"
                
                if i > 0:
                    prev_date = sorted_dates[i - 1]
                    prev_stats = daily_breakdown[prev_date]
                    calls_change = stats["total_calls"] - prev_stats["total_calls"]
                    if prev_stats["total_calls"] > 0:
                        calls_change_percent = (calls_change / prev_stats["total_calls"]) * 100
                    
                    if calls_change > 0:
                        trend = "up"
                    elif calls_change < 0:
                        trend = "down"
                
                day_comparison.append({
                    "date": date,
                    "total_calls": stats["total_calls"],
                    "answered_calls": stats["answered_calls"],
                    "missed_calls": stats["missed_calls"],
                    "total_duration": stats["total_duration"],
                    "success_rate": round(success_rate, 2),
                    "recordings_count": stats["recordings_count"],
                    "calls_change": calls_change,
                    "calls_change_percent": round(calls_change_percent, 2),
                    "trend": trend
                })
        
        # Parse recent call records
        call_records_parsed = []
        for record in user_call_records[:50]:
            try:
                parsed_record = tata_admin_service.parse_call_record(record)
                call_records_parsed.append({
                    "call_id": parsed_record.call_id,
                    "direction": parsed_record.direction,
                    "status": parsed_record.status,
                    "date": parsed_record.date,
                    "time": parsed_record.time,
                    "agent_number": parsed_record.agent_number,
                    "client_number": parsed_record.client_number,
                    "call_duration": parsed_record.call_duration,
                    "recording_url": parsed_record.recording_url
                })
            except Exception as e:
                logger.warning(f"Error parsing call record: {e}")
                continue
        
        # Calculate ranking
        ranking = None
        if user_stats_data["success_rate"] > 0:
            period_calls = user_stats_data.get(f"{period}_calls", user_stats_data.get("daily_calls", 0))
            ranking = {
                "rank": 1,
                "user_id": user_id,
                "user_name": user_name,
                "score": user_stats_data["success_rate"],
                "total_calls": period_calls
            }
        
        # Log admin activity
        try:
            await tata_admin_service.log_admin_activity(
                admin_user_id=str(current_user.get("user_id") or current_user.get("_id", "unknown")),
                admin_email=current_user.get("email", "unknown"),
                action="viewed_user_performance_optimized",
                target_user_id=user_id,
                target_user_name=user_name,
                details={
                    "period": period,
                    "date_range": f"{date_from} to {date_to}",
                    "records_analyzed": len(user_call_records),
                    "filtering_method": "tata_api_agent_filter"
                }
            )
        except Exception as e:
            logger.warning(f"Error logging admin activity: {e}")
        
        # Build response
        response = {
            "success": True,
            "user_id": user_id,
            "user_name": user_name,
            "agent_number": user_agent_number,
            "stats": user_stats_data,
            "day_comparison": day_comparison,
            "call_records": call_records_parsed,
            "ranking": ranking,
            "period_analyzed": f"{period.title()} ({date_from} to {date_to})",
            "analysis_date": datetime.utcnow(),
            "optimization_info": {
                "filtering_method": "tata_api_agent_filter",
                "user_records_found": len(user_call_records),
                "agent_number_used": user_agent_number
            }
        }
        
        logger.info(f"Optimized user performance analysis complete: {len(user_call_records)} records for {user_name}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting optimized user performance: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": f"Failed to fetch optimized user performance: {str(e)}",
                "user_id": user_id
            }
        )

# =============================================================================
# PERFORMANCE RANKING ENDPOINTS - OPTIMIZED
# =============================================================================

@router.get("/weekly-performers", response_model=PerformanceRankingResponse)
async def get_weekly_performers(
    week_offset: int = Query(0, description="Weeks back from current week (0=current, 1=last week)"),
    top_n: int = Query(10, description="Number of top performers to return"),
    current_user: Dict = Depends(get_admin_user)
):
    """Get weekly top performers using TATA API filtering"""
    try:
        # Calculate week dates
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday()) - timedelta(weeks=week_offset)
        week_end = week_start + timedelta(days=6)
        
        # Get weekly performers using optimized TATA filtering
        performers = await tata_admin_service.get_weekly_performers_optimized(
            week_start=week_start,
            week_end=week_end,
            top_n=top_n
        )
        
        # Convert to PerformerRanking objects
        from ..models.admin_dashboard import PerformerRanking
        rankings = [
            PerformerRanking(**performer) for performer in performers
        ]
        
        return PerformanceRankingResponse(
            success=True,
            period=f"Week {week_start.strftime('%Y-W%U')}",
            rankings=rankings,
            total_users=len(rankings),
            date_range=f"{week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}"
        )
        
    except Exception as e:
        logger.error(f"Error getting weekly performers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch weekly performers: {str(e)}"
        )

@router.get("/monthly-performers", response_model=PerformanceRankingResponse)
async def get_monthly_performers(
    year: Optional[int] = Query(None, description="Year (defaults to current year)"),
    month: Optional[int] = Query(None, description="Month 1-12 (defaults to current month)"),
    top_n: int = Query(10, description="Number of top performers to return"),
    current_user: Dict = Depends(get_admin_user)
):
    """Get monthly top performers using TATA API filtering"""
    try:
        # Use current month if not specified
        now = datetime.now()
        year = year or now.year
        month = month or now.month
        
        # Validate month
        if not (1 <= month <= 12):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Month must be between 1 and 12"
            )
        
        # Get monthly performers using optimized TATA filtering
        performers = await tata_admin_service.get_monthly_performers_optimized(
            year=year,
            month=month,
            top_n=top_n
        )
        
        # Convert to PerformerRanking objects
        from ..models.admin_dashboard import PerformerRanking
        rankings = [
            PerformerRanking(**performer) for performer in performers
        ]
        
        month_name = calendar.month_name[month]
        
        return PerformanceRankingResponse(
            success=True,
            period=f"{month_name} {year}",
            rankings=rankings,
            total_users=len(rankings),
            date_range=f"{year}-{month:02d}-01 to {year}-{month:02d}-{calendar.monthrange(year, month)[1]}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting monthly performers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch monthly performers: {str(e)}"
        )

# =============================================================================
# RECORDING MANAGEMENT ENDPOINTS - OPTIMIZED
# =============================================================================

@router.post("/play-recording")
async def play_user_recording(
    recording_request: PlayRecordingRequest,
    request: Request,
    current_user: Dict = Depends(get_admin_user)
):
    """
    Admin endpoint to play user recordings using TATA API call filtering
    """
    try:
        logger.info(f"Admin {current_user.get('email')} requesting recording {recording_request.call_id}")
        
        # Initialize agent mapping
        await tata_admin_service.initialize_agent_mapping()
        
        # Find user details
        user_name = "Unknown"
        user_agent_number = None
        for agent_number, mapping in tata_admin_service.agent_user_mapping.items():
            if mapping.get("user_id") == recording_request.user_id:
                user_name = mapping.get("user_name", "Unknown")
                user_agent_number = agent_number
                break
        
        # Use TATA API to find the specific call record
        today = datetime.now()
        from_date = (today - timedelta(days=30)).strftime("%Y-%m-%d 00:00:00")
        to_date = today.strftime("%Y-%m-%d 23:59:59")
        
        # Search by call_id using TATA API
        tata_params = {
            'from_date': from_date,
            'to_date': to_date,
            'call_id': recording_request.call_id,
            'page': '1',
            'limit': '1'
        }
        
        tata_response = await tata_admin_service.fetch_call_records_with_filters(
            params=tata_params
        )
        
        if not tata_response.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"TATA API search failed: {tata_response.get('error')}"
            )
        
        # Extract call record
        tata_data = tata_response.get("data", {})
        call_records = tata_data.get("results", [])
        
        if not call_records:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "call_not_found",
                    "message": f"Call {recording_request.call_id} not found",
                    "suggestion": "Call might be older than 30 days or call ID is incorrect"
                }
            )
        
        target_call = call_records[0]
        recording_url = target_call.get("recording_url")
        
        if not recording_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "no_recording",
                    "message": f"No recording available for call {recording_request.call_id}",
                    "call_info": {
                        "call_id": target_call.get("id"),
                        "date": target_call.get("date"),
                        "time": target_call.get("time"),
                        "status": target_call.get("status"),
                        "agent": target_call.get("agent_name")
                    }
                }
            )
        
        # Log admin activity
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        await tata_admin_service.log_admin_activity(
            admin_user_id=str(current_user.get("user_id") or current_user.get("_id")),
            admin_email=current_user.get("email"),
            action="played_recording",
            target_user_id=recording_request.user_id,
            target_user_name=user_name,
            details={
                "call_id": recording_request.call_id,
                "reason": recording_request.reason,
                "recording_url": recording_url,
                "call_date": target_call.get("date"),
                "call_time": target_call.get("time"),
                "call_duration": target_call.get("call_duration", 0),
                "agent_name": target_call.get("agent_name")
            },
            ip_address=client_ip,
            user_agent=user_agent
        )
        
        return {
            "success": True,
            "message": "Recording access granted",
            "recording_url": recording_url,
            "call_id": recording_request.call_id,
            "call_info": {
                "date": target_call.get("date"),
                "time": target_call.get("time"),
                "duration": target_call.get("call_duration", 0),
                "status": target_call.get("status"),
                "agent_name": target_call.get("agent_name"),
                "client_number": target_call.get("client_number")
            },
            "access_logged": True,
            "expires_at": datetime.utcnow() + timedelta(hours=1),
            "accessed_by": current_user.get("email"),
            "access_reason": recording_request.reason
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error playing recording: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to access recording: {str(e)}"
        )

@router.get("/user-recordings/{user_id}")
async def get_user_recordings(
    user_id: str,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(20, ge=1, le=100, description="Records per page"),
    page: int = Query(1, ge=1, description="Page number"),
    current_user: Dict = Depends(get_admin_user)
):
    """
    Get user recordings using TATA API agent filtering
    """
    try:
        logger.info(f"Admin {current_user.get('email')} requesting recordings for user {user_id}")
        
        # Initialize agent mapping
        await tata_admin_service.initialize_agent_mapping()
        
        # Find user's agent number
        user_agent_number = None
        user_name = "Unknown"
        for agent_number, mapping in tata_admin_service.agent_user_mapping.items():
            if mapping.get("user_id") == user_id:
                user_agent_number = agent_number
                user_name = mapping.get("user_name", "Unknown")
                break
        
        if not user_agent_number:
            available_users = [
                {"user_id": m["user_id"], "user_name": m["user_name"]}
                for m in tata_admin_service.agent_user_mapping.values()
                if m.get("user_id") and m.get("user_name")
            ]
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "user_not_found",
                    "message": f"User {user_id} not found in agent mapping",
                    "available_users": available_users[:10]
                }
            )
        
        # Set default date range
        if not date_from or not date_to:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            date_from = start_date.strftime("%Y-%m-%d")
            date_to = end_date.strftime("%Y-%m-%d")
        
        # Format dates
        from_date = f"{date_from} 00:00:00"
        to_date = f"{date_to} 23:59:59"
        
        logger.info(f"Fetching recordings for {user_name} ({user_agent_number})")
        
        # Use TATA API with agent filter
        tata_params = {
            'from_date': from_date,
            'to_date': to_date,
            'agents': user_agent_number,
            'page': str(page),
            'limit': str(limit * 2)  # Get more records since not all have recordings
        }
        
        tata_response = await tata_admin_service.fetch_call_records_with_filters(
            params=tata_params
        )
        
        if not tata_response.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"TATA API call failed: {tata_response.get('error')}"
            )
        
        # Extract and filter for recordings only
        tata_data = tata_response.get("data", {})
        all_records = tata_data.get("results", [])
        
        # Filter only records with recordings
        recordings_only = [
            record for record in all_records 
            if record.get("recording_url")
        ]
        
        # Apply pagination to recordings
        start_index = (page - 1) * limit
        end_index = start_index + limit
        paginated_recordings = recordings_only[start_index:end_index]
        
        # Process recordings
        formatted_recordings = []
        for record in paginated_recordings:
            try:
                recording_info = {
                    "call_id": record.get("id") or record.get("call_id"),
                    "uuid": record.get("uuid"),
                    "recording_url": record.get("recording_url"),
                    "date": record.get("date"),
                    "time": record.get("time"),
                    "call_duration": record.get("call_duration", 0),
                    "answered_seconds": record.get("answered_seconds", 0),
                    "direction": record.get("direction"),
                    "status": record.get("status"),
                    "client_number": record.get("client_number"),
                    "agent_name": record.get("agent_name"),
                    "service": record.get("service"),
                    "hangup_cause": record.get("hangup_cause"),
                    "description": record.get("description"),
                    "call_quality": "good" if record.get("call_duration", 0) > 30 else "short",
                    "has_recording": True,
                    "created_at": f"{record.get('date')} {record.get('time')}",
                    "circle": record.get("circle", {})
                }
                formatted_recordings.append(recording_info)
            except Exception as e:
                logger.warning(f"Error formatting recording: {e}")
                continue
        
        # Calculate statistics
        total_recordings = len(recordings_only)
        total_duration = sum(r["call_duration"] for r in formatted_recordings)
        avg_duration = total_duration / len(formatted_recordings) if formatted_recordings else 0
        answered_recordings = [r for r in formatted_recordings if r["status"] == "answered"]
        
        # Build response
        response = {
            "success": True,
            "user_id": user_id,
            "user_name": user_name,
            "agent_number": user_agent_number,
            "recordings": formatted_recordings,
            "pagination": {
                "current_page": page,
                "limit": limit,
                "total_recordings": total_recordings,
                "total_pages": (total_recordings + limit - 1) // limit if total_recordings > 0 else 1,
                "has_more": end_index < total_recordings,
                "has_previous": page > 1
            },
            "statistics": {
                "recordings_on_this_page": len(formatted_recordings),
                "total_recordings_found": total_recordings,
                "total_duration_minutes": round(total_duration / 60, 2),
                "average_duration_seconds": round(avg_duration, 2),
                "answered_recordings": len(answered_recordings)
            },
            "query_info": {
                "date_range": f"{date_from} to {date_to}",
                "filtering_method": "tata_api_agent_filter",
                "user_agent_number": user_agent_number
            },
            "retrieved_at": datetime.utcnow()
        }
        
        # Log activity
        await tata_admin_service.log_admin_activity(
            admin_user_id=str(current_user.get("user_id") or current_user.get("_id")),
            admin_email=current_user.get("email"),
            action="viewed_user_recordings",
            target_user_id=user_id,
            target_user_name=user_name,
            details={
                "date_range": f"{date_from} to {date_to}",
                "page": page,
                "recordings_returned": len(formatted_recordings),
                "filtering_method": "tata_api_agent_filter"
            }
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user recordings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch user recordings: {str(e)}"
        )

@router.get("/recording/{call_id}")
async def get_recording_details(
    call_id: str,
    current_user: Dict = Depends(get_admin_user)
):
    """
    Get recording details using TATA API call_id filter
    """
    try:
        logger.info(f"Admin {current_user.get('email')} requesting recording details for {call_id}")
        
        # Use TATA API to search by call_id
        today = datetime.now()
        from_date = (today - timedelta(days=30)).strftime("%Y-%m-%d 00:00:00")
        to_date = today.strftime("%Y-%m-%d 23:59:59")
        
        tata_params = {
            'from_date': from_date,
            'to_date': to_date,
            'call_id': call_id,
            'page': '1',
            'limit': '1'
        }
        
        tata_response = await tata_admin_service.fetch_call_records_with_filters(
            params=tata_params
        )
        
        if not tata_response.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"TATA API search failed: {tata_response.get('error')}"
            )
        
        # Extract call record
        tata_data = tata_response.get("data", {})
        call_records = tata_data.get("results", [])
        
        if not call_records:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "call_not_found",
                    "message": f"Call {call_id} not found",
                    "suggestion": "Call might be older than 30 days or call ID is incorrect"
                }
            )
        
        target_call = call_records[0]
        recording_url = target_call.get("recording_url")
        
        if not recording_url:
            return {
                "success": True,
                "has_recording": False,
                "message": "Call found but no recording available",
                "call_info": {
                    "call_id": target_call.get("id"),
                    "date": target_call.get("date"),
                    "time": target_call.get("time"),
                    "status": target_call.get("status"),
                    "duration": target_call.get("call_duration", 0)
                }
            }
        
        # Find associated user
        agent_number = target_call.get("agent_number")
        user_info = {"user_id": "unknown", "user_name": "Unknown"}
        
        await tata_admin_service.initialize_agent_mapping()
        for agent, mapping in tata_admin_service.agent_user_mapping.items():
            if agent == agent_number:
                user_info = {
                    "user_id": mapping.get("user_id", "unknown"),
                    "user_name": mapping.get("user_name", "Unknown")
                }
                break
        
        return {
            "success": True,
            "has_recording": True,
            "recording_url": recording_url,
            "call_details": {
                "call_id": target_call.get("id"),
                "uuid": target_call.get("uuid"),
                "date": target_call.get("date"),
                "time": target_call.get("time"),
                "duration": target_call.get("call_duration", 0),
                "answered_seconds": target_call.get("answered_seconds", 0),
                "direction": target_call.get("direction"),
                "status": target_call.get("status"),
                "service": target_call.get("service"),
                "agent_name": target_call.get("agent_name"),
                "agent_number": agent_number,
                "client_number": target_call.get("client_number"),
                "did_number": target_call.get("did_number"),
                "hangup_cause": target_call.get("hangup_cause"),
                "description": target_call.get("description"),
                "circle": target_call.get("circle")
            },
            "user_info": user_info,
            "recording_info": {
                "recording_url": recording_url,
                "estimated_duration": target_call.get("call_duration", 0),
                "recording_quality": "good" if target_call.get("call_duration", 0) > 30 else "short",
                "file_format": "audio/wav",
                "can_download": True
            },
            "retrieved_at": datetime.utcnow()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting recording details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recording details: {str(e)}"
        )

# =============================================================================
# FILTER OPTIONS ENDPOINT
# =============================================================================

@router.get("/filter-options", response_model=FilterOptionsResponse)
async def get_filter_options(
    current_user: Dict = Depends(get_admin_user)
):
    """Get available filter options for the admin dashboard"""
    try:
        # Initialize agent mapping
        await tata_admin_service.initialize_agent_mapping()
        
        # Get available users from agent mapping
        available_users = [
            {"user_id": mapping["user_id"], "user_name": mapping["user_name"]}
            for mapping in tata_admin_service.agent_user_mapping.values()
        ]
        
        # Set date ranges
        today = datetime.now()
        min_date = (today - timedelta(days=90)).strftime("%Y-%m-%d")
        max_date = today.strftime("%Y-%m-%d")
        
        return FilterOptionsResponse(
            success=True,
            available_users=available_users,
            min_date=min_date,
            max_date=max_date,
            call_statuses=["all", "answered", "missed"],
            call_directions=["all", "inbound", "outbound"],
            performance_periods=["daily", "weekly", "monthly"]
        )
        
    except Exception as e:
        logger.error(f"Error getting filter options: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch filter options: {str(e)}"
        )

# =============================================================================
# SUMMARY STATISTICS ENDPOINT - OPTIMIZED
# =============================================================================

@router.get("/summary-stats")
async def get_summary_statistics(
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: Dict = Depends(get_admin_user)
):
    """Get summary statistics using TATA API filtering"""
    try:
        # Set default date range
        if not date_from or not date_to:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            date_from = start_date.strftime("%Y-%m-%d")
            date_to = end_date.strftime("%Y-%m-%d")
        
        # Format for TATA API
        from_date = f"{date_from} 00:00:00"
        to_date = f"{date_to} 23:59:59"
        
        # Use TATA API to fetch summary data
        tata_params = {
            'from_date': from_date,
            'to_date': to_date,
            'page': '1',
            'limit': '1000'  # Get enough for statistics
        }
        
        tata_response = await tata_admin_service.fetch_call_records_with_filters(
            params=tata_params
        )
        
        if not tata_response.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"TATA API call failed: {tata_response.get('error')}"
            )
        
        # Extract call records
        tata_data = tata_response.get("data", {})
        call_records = tata_data.get("results", [])
        total_count = tata_data.get("count", 0)
        
        # Calculate statistics
        total_calls = len(call_records)
        total_answered = sum(1 for r in call_records if r.get("status") == "answered")
        total_missed = total_calls - total_answered
        total_duration = sum(r.get("call_duration", 0) for r in call_records if r.get("status") == "answered")
        total_recordings = sum(1 for r in call_records if r.get("recording_url"))
        
        # Get unique users
        unique_agents = set(r.get("agent_number") for r in call_records if r.get("agent_number"))
        unique_users = len(unique_agents)
        
        # Calculate averages
        avg_calls_per_day = total_calls / 7 if total_calls > 0 else 0
        avg_duration = total_duration / total_answered if total_answered > 0 else 0
        success_rate = (total_answered / total_calls * 100) if total_calls > 0 else 0
        
        # Calculate trends and peak hours
        trend_data = performance_calculator.calculate_trend_analysis(call_records, 7)
        peak_hours_data = performance_calculator.calculate_peak_hours(call_records)
        
        return {
            "success": True,
            "date_range": f"{date_from} to {date_to}",
            "summary": {
                "total_calls": total_calls,
                "total_calls_all_pages": total_count,
                "total_answered": total_answered,
                "total_missed": total_missed,
                "total_duration_minutes": round(total_duration / 60, 2),
                "total_recordings": total_recordings,
                "unique_users": unique_users,
                "success_rate": round(success_rate, 2),
                "avg_calls_per_day": round(avg_calls_per_day, 2),
                "avg_call_duration_seconds": round(avg_duration, 2)
            },
            "trends": trend_data,
            "peak_hours": peak_hours_data,
            "optimization_info": {
                "filtering_method": "tata_api_server_side",
                "records_analyzed": total_calls,
                "total_available": total_count
            },
            "calculated_at": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Error getting summary statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch summary statistics: {str(e)}"
        )

# =============================================================================
# COMPREHENSIVE PEAK HOURS ENDPOINT - OPTIMIZED
# =============================================================================

@router.get("/analytics/comprehensive-peak-hours")
async def get_comprehensive_peak_hours_analysis(
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    include_total: bool = Query(True, description="Include peak calling hours"),
    include_answered: bool = Query(True, description="Include peak answered hours"),
    include_missed: bool = Query(True, description="Include peak missed hours"),
    user_ids: Optional[str] = Query(None, description="Comma-separated user IDs to filter"),
    current_user: Dict = Depends(get_admin_user)
):
    """
    Comprehensive peak hours analysis using TATA API filtering
    """
    try:
        logger.info(f"Admin {current_user.get('email')} requesting comprehensive peak hours analysis")
        
        # Initialize agent mapping
        await tata_admin_service.initialize_agent_mapping()
        
        # Set default date range
        if not date_from or not date_to:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            date_from = start_date.strftime("%Y-%m-%d")
            date_to = end_date.strftime("%Y-%m-%d")
        
        # Format dates
        from_date = f"{date_from} 00:00:00"
        to_date = f"{date_to} 23:59:59"
        
        # Build TATA params
        tata_params = {
            'from_date': from_date,
            'to_date': to_date,
            'page': '1',
            'limit': '2000'
        }
        
        # Apply user filtering if specified
        filter_info = {"applied": False}
        if user_ids:
            user_list = [uid.strip() for uid in user_ids.split(",")]
            agent_numbers = []
            
            for user_id in user_list:
                for agent_number, mapping in tata_admin_service.agent_user_mapping.items():
                    if mapping.get("user_id") == user_id:
                        agent_numbers.append(agent_number)
                        break
            
            if agent_numbers:
                tata_params['agents'] = ",".join(agent_numbers)
                filter_info = {
                    "applied": True,
                    "user_count": len(user_list),
                    "agent_numbers": agent_numbers
                }
        
        # Fetch data using TATA API
        tata_response = await tata_admin_service.fetch_call_records_with_filters(
            params=tata_params
        )
        
        if not tata_response.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"TATA API call failed: {tata_response.get('error')}"
            )
        
        # Extract filtered records
        tata_data = tata_response.get("data", {})
        filtered_call_records = tata_data.get("results", [])
        
        logger.info(f"Analyzing {len(filtered_call_records)} filtered call records")
        
        # Calculate comprehensive peak hours
        peak_hours_analysis = performance_calculator.calculate_comprehensive_peak_hours(
            call_records=filtered_call_records
        )
        
        # Build response based on include flags
        response_data = {
            "success": True,
            "date_range": f"{date_from} to {date_to}",
            "analysis_type": "comprehensive_peak_hours_optimized",
            "filter_info": filter_info
        }
        
        if include_total:
            response_data["peak_calling_hours"] = peak_hours_analysis["peak_calling_hours"]
        
        if include_answered:
            response_data["peak_answered_hours"] = peak_hours_analysis["peak_answered_hours"]
        
        if include_missed:
            response_data["peak_missed_hours"] = peak_hours_analysis["peak_missed_hours"]
        
        response_data.update({
            "summary": peak_hours_analysis["summary"],
            "analysis_metadata": peak_hours_analysis["analysis_metadata"],
            "optimization_info": {
                "filtering_method": "tata_api_server_side",
                "records_analyzed": len(filtered_call_records)
            },
            "generated_at": datetime.utcnow(),
            "requested_by": current_user.get("email", "unknown")
        })
        
        # Add insights
        summary = peak_hours_analysis["summary"]
        if summary["total_calls"] > 0:
            response_data["insights"] = {
                "best_calling_time": peak_hours_analysis["analysis_metadata"].get("most_active_hour"),
                "best_answer_time": peak_hours_analysis["analysis_metadata"].get("best_answer_hour"), 
                "worst_miss_time": peak_hours_analysis["analysis_metadata"].get("worst_miss_hour"),
                "overall_answer_rate": summary["answer_rate"]
            }
        
        # Log activity
        await tata_admin_service.log_admin_activity(
            admin_user_id=str(current_user.get("user_id") or current_user.get("_id", "unknown")),
            admin_email=current_user.get("email", "unknown"),
            action="viewed_comprehensive_peak_hours_optimized",
            details={
                "date_range": f"{date_from} to {date_to}",
                "total_calls_analyzed": summary["total_calls"],
                "user_filter_applied": bool(user_ids),
                "filtering_method": "tata_api_server_side"
            }
        )
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in comprehensive peak hours analysis: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze peak hours: {str(e)}"
        )

# =============================================================================
# EXPORT ENDPOINT - OPTIMIZED
# =============================================================================

@router.get("/export-call-data")
async def export_call_data(
    date_from: str = Query(..., description="Start date (YYYY-MM-DD)"),
    date_to: str = Query(..., description="End date (YYYY-MM-DD)"),
    format: str = Query("json", description="Export format (json, csv)"),
    user_ids: Optional[str] = Query(None, description="Comma-separated user IDs"),
    call_type: Optional[str] = Query(None, description="Call type filter"),
    direction: Optional[str] = Query(None, description="Direction filter"),
    current_user: Dict = Depends(get_admin_user)
):
    """Export call data using TATA API filtering"""
    try:
        logger.info(f"Admin {current_user['email']} exporting call data")
        
        # Format dates
        from_date = f"{date_from} 00:00:00"
        to_date = f"{date_to} 23:59:59"
        
        # Build TATA params for export
        tata_params = {
            'from_date': from_date,
            'to_date': to_date,
            'page': '1',
            'limit': '5000'  # Limit for exports
        }
        
        # Apply user filters
        if user_ids:
            await tata_admin_service.initialize_agent_mapping()
            user_list = [uid.strip() for uid in user_ids.split(",")]
            agent_numbers = []
            for user_id in user_list:
                for agent_number, mapping in tata_admin_service.agent_user_mapping.items():
                    if mapping.get("user_id") == user_id:
                        agent_numbers.append(agent_number)
            if agent_numbers:
                tata_params['agents'] = ",".join(agent_numbers)
        
        if call_type:
            tata_params['call_type'] = call_type
        
        if direction:
            tata_params['direction'] = direction
        
        # Fetch records using TATA API
        tata_response = await tata_admin_service.fetch_call_records_with_filters(
            params=tata_params
        )
        
        if not tata_response.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"TATA API call failed: {tata_response.get('error')}"
            )
        
        # Extract and parse records
        tata_data = tata_response.get("data", {})
        call_records = tata_data.get("results", [])
        
        parsed_records = []
        for record in call_records:
            try:
                parsed_record = tata_admin_service.parse_call_record(record)
                parsed_records.append(parsed_record.dict())
            except Exception as e:
                logger.warning(f"Error parsing record for export: {e}")
                continue
        
        # Log admin activity
        await tata_admin_service.log_admin_activity(
            admin_user_id=str(current_user.get("user_id") or current_user.get("_id")),
            admin_email=current_user["email"],
            action="exported_call_data_optimized",
            details={
                "date_range": f"{date_from} to {date_to}",
                "format": format,
                "record_count": len(parsed_records),
                "user_filter": user_ids,
                "filtering_method": "tata_api_server_side"
            }
        )
        
        if format.lower() == "csv":
            # Convert to CSV format
            import csv
            import io
            
            output = io.StringIO()
            if parsed_records:
                fieldnames = parsed_records[0].keys()
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(parsed_records)
            
            from fastapi.responses import Response
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=call_data_{date_from}_to_{date_to}.csv"}
            )
        else:
            # Return JSON
            return {
                "success": True,
                "export_format": format,
                "date_range": f"{date_from} to {date_to}",
                "record_count": len(parsed_records),
                "filtering_method": "tata_api_server_side",
                "data": parsed_records,
                "exported_at": datetime.utcnow()
            }
        
    except Exception as e:
        logger.error(f"Error exporting call data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export call data: {str(e)}"
        )

# =============================================================================
# ADMIN ACTIVITY LOGS ENDPOINT
# =============================================================================

@router.get("/admin-activity-logs")
async def get_admin_activity_logs(
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    limit: int = Query(50, description="Maximum records to return"),
    current_user: Dict = Depends(get_admin_user)
):
    """Get admin activity logs for auditing purposes"""
    try:
        # Set default date range
        if not date_from or not date_to:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            date_from = start_date.strftime("%Y-%m-%d")
            date_to = end_date.strftime("%Y-%m-%d")
        
        # Query admin activity logs from database
        db = tata_admin_service._get_db()
        if not db:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not available"
            )
        
        # Build query
        query = {
            "timestamp": {
                "$gte": datetime.strptime(f"{date_from} 00:00:00", "%Y-%m-%d %H:%M:%S"),
                "$lte": datetime.strptime(f"{date_to} 23:59:59", "%Y-%m-%d %H:%M:%S")
            }
        }
        
        if action_type:
            query["action"] = action_type
        
        # Fetch logs
        logs_cursor = db.admin_activity_logs.find(query).sort("timestamp", -1).limit(limit)
        logs = await logs_cursor.to_list(length=limit)
        
        # Convert ObjectId to string
        for log in logs:
            log["_id"] = str(log["_id"])
        
        return {
            "success": True,
            "date_range": f"{date_from} to {date_to}",
            "action_filter": action_type,
            "log_count": len(logs),
            "logs": logs,
            "retrieved_at": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Error fetching admin activity logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch activity logs: {str(e)}"
        )