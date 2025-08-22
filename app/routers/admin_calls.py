# app/routers/admin_calls.py
# Admin Call Dashboard API Endpoints
# Fetch and display call analytics from TATA API

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
    CallStatusFilter, CallDirectionFilter, DashboardError,ComprehensivePeakHoursResponse, PeakAnsweredHoursResponse, PeakMissedHoursResponse
)
from ..utils.dependencies import get_admin_user, get_current_active_user

logger = logging.getLogger(__name__)

router = APIRouter()

# =============================================================================
# MAIN DASHBOARD ENDPOINT
# =============================================================================
# Fix for TATA API filtering issue in app/routers/admin_calls.py

# PROBLEM: TATA API agent filtering returns 0 records even when agent exists
# SOLUTION: Use Python filtering as primary method, with better error handling

# ============================================================================
# FIXED DASHBOARD ENDPOINT WITH PYTHON FILTERING
# ============================================================================

@router.get("/call-dashboard")
async def get_admin_call_dashboard(
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    period: str = Query("daily", description="Performance period"),
    user_ids: Optional[str] = Query(None, description="Comma-separated user IDs to filter"),
    call_status: str = Query("all", description="Call status filter"),
    call_direction: str = Query("all", description="Call direction filter"),
    limit: int = Query(50, description="Maximum records to return"),
    page: int = Query(1, description="Page number"),
    current_user: Dict = Depends(get_admin_user)
):
    """🔧 FIXED: Admin dashboard with reliable Python-based user filtering"""
    try:
        logger.info(f"Admin {current_user.get('email')} requesting call dashboard")
        
        # Initialize agent mapping
        await tata_admin_service.initialize_agent_mapping()
        
        # Set date range
        if not date_from or not date_to:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            date_from = start_date.strftime("%Y-%m-%d")
            date_to = end_date.strftime("%Y-%m-%d")
        
        # Format dates for TATA API
        from_date = f"{date_from} 00:00:00"
        to_date = f"{date_to} 23:59:59"
        
        # 🔧 STEP 1: Always fetch ALL records first (TATA API filtering is unreliable)
        logger.info(f"Fetching all call records from {from_date} to {to_date}")
        
        # Only apply non-user filters to TATA API (these seem to work better)
        tata_filters = {}
        if call_status != "all":
            tata_filters["call_type"] = "c" if call_status == "answered" else "m"
        if call_direction != "all":
            tata_filters["direction"] = call_direction
        
        # Fetch all records with basic filters only
        all_call_records = await tata_admin_service.fetch_all_call_records(
            from_date=from_date,
            to_date=to_date,
            filters=tata_filters,  # Don't include user filters here
            max_records=10000  # Get more records for filtering
        )
        
        logger.info(f"📊 Fetched {len(all_call_records)} total call records")
        
        # 🔧 STEP 2: Apply user filtering in Python (RELIABLE)
        filtered_call_records = all_call_records
        filtered_agent_numbers = []
        
        if user_ids:
            logger.info(f"🎯 Applying Python user filter for: {user_ids}")
            user_list = [uid.strip() for uid in user_ids.split(",")]
            
            # Build list of target agent numbers
            target_agent_numbers = []
            for user_id in user_list:
                for agent_number, mapping in tata_admin_service.agent_user_mapping.items():
                    if mapping.get("user_id") == user_id:
                        target_agent_numbers.append(agent_number)
                        filtered_agent_numbers.append(agent_number)
                        logger.info(f"✅ User {user_id} -> Agent {agent_number}")
                        break
                else:
                    logger.warning(f"❌ User {user_id} not found in agent mapping")
            
            # Filter records by agent numbers
            if target_agent_numbers:
                original_count = len(filtered_call_records)
                filtered_call_records = [
                    record for record in all_call_records
                    if record.get("agent_number") in target_agent_numbers
                ]
                logger.info(f"🔍 Python filtering: {original_count} -> {len(filtered_call_records)} records")
                logger.info(f"📋 Target agents: {target_agent_numbers}")
                
                # Debug: Show sample of what we're filtering
                if len(filtered_call_records) > 0:
                    sample_agents = [r.get("agent_number") for r in filtered_call_records[:5]]
                    logger.info(f"✅ Sample filtered agent numbers: {sample_agents}")
                else:
                    # Debug: Show what agent numbers exist in data
                    all_agents = list(set(r.get("agent_number") for r in all_call_records if r.get("agent_number")))
                    logger.warning(f"❌ No records found. Available agents in data: {all_agents[:10]}")
            else:
                logger.warning("No valid target agent numbers found - returning empty results")
                filtered_call_records = []
        
        # 🔧 STEP 3: Calculate statistics on filtered data
        user_stats_dict = {}
        if filtered_call_records:
            if period == "daily":
                user_stats_dict = tata_admin_service.calculate_daily_stats(filtered_call_records, date_from)
            elif period == "weekly":
                week_start = datetime.strptime(date_from, "%Y-%m-%d")
                week_key = f"{week_start.year}-W{week_start.isocalendar()[1]:02d}"
                user_stats_dict = tata_admin_service.calculate_period_stats(filtered_call_records, "weekly", week_key)
            elif period == "monthly":
                month_key = date_from[:7]
                user_stats_dict = tata_admin_service.calculate_period_stats(filtered_call_records, "monthly", month_key)
            
            logger.info(f"📈 Calculated stats for {len(user_stats_dict)} users")
        
        # 🔧 STEP 4: Process recent calls (from filtered data)
        recent_calls = []
        for i, record in enumerate(filtered_call_records[:limit]):
            try:
                parsed_record = tata_admin_service.parse_call_record(record)
                recent_calls.append(parsed_record)
            except Exception as e:
                logger.warning(f"Error parsing call record {i}: {e}")
                continue
        
        # 🔧 STEP 5: Calculate top performers
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
        
        # 🔧 STEP 6: Summary statistics
        total_calls = len(filtered_call_records)
        total_answered = sum(1 for r in filtered_call_records if r.get("status") == "answered")
        total_recordings = sum(1 for r in filtered_call_records if r.get("recording_url"))
        overall_success_rate = (total_answered / total_calls * 100) if total_calls > 0 else 0.0
        
        # 🔧 STEP 7: Enhanced debug info
        debug_info = {
            "filtering_method": "python_based",  # We're using Python filtering
            "total_records_fetched": len(all_call_records),
            "records_after_user_filter": len(filtered_call_records),
            "tata_api_filters": tata_filters,
            "filtering_successful": len(filtered_call_records) > 0 if user_ids else True
        }
        
        if user_ids:
            debug_info.update({
                "requested_user_ids": user_ids.split(","),
                "found_agent_numbers": filtered_agent_numbers,
                "filter_working": len(filtered_call_records) > 0
            })
        
        # Build response
        response_data = {
            "success": True,
            "total_calls": total_calls,
            "total_users": len(user_stats_dict),
            "total_recordings": total_recordings,
            "overall_success_rate": round(overall_success_rate, 2),
            "user_stats": list(user_stats_dict.values()),
            "recent_calls": recent_calls,
            "top_performers": top_performers,
            "date_range": f"{date_from} to {date_to}",
            "data_fetched_at": datetime.utcnow(),
            "total_pages": 1,
            "current_page": page,
            "filters_applied": {
                "date_from": date_from,
                "date_to": date_to,
                "period": period,
                "call_status": call_status,
                "call_direction": call_direction,
                "user_ids": user_ids.split(",") if user_ids else None
            },
            "debug_info": debug_info  # Always include debug info
        }
        
        # Log admin activity
        try:
            await tata_admin_service.log_admin_activity(
                admin_user_id=str(current_user.get("user_id") or current_user.get("_id", "unknown")),
                admin_email=current_user.get("email", "unknown"),
                action="viewed_call_dashboard",
                details={
                    "date_range": f"{date_from} to {date_to}",
                    "period": period,
                    "total_records": total_calls,
                    "user_filter_applied": bool(user_ids),
                    "filtering_method": "python_based"
                }
            )
        except Exception as e:
            logger.warning(f"Error logging admin activity: {e}")
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error in admin call dashboard: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": str(e),
                "message": "Failed to fetch dashboard data"
            }
        )

# ============================================================================
# DEBUG ENDPOINT (GET method, not POST)
# ============================================================================

@router.get("/debug/test-user-filter/{user_id}")
async def debug_test_user_filter(
    user_id: str,
    date_from: str = Query("2025-08-18", description="Start date"),
    date_to: str = Query("2025-08-18", description="End date"),
    current_user: Dict = Depends(get_admin_user)
):
    """🔍 DEBUG: Test user filtering mechanisms"""
    try:
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
            return {
                "success": False,
                "error": f"User {user_id} not found in agent mapping",
                "available_users": [
                    {
                        "user_id": m["user_id"], 
                        "user_name": m["user_name"], 
                        "agent_number": k
                    }
                    for k, m in tata_admin_service.agent_user_mapping.items()
                ][:10]  # Show first 10 users
            }
        
        # Test different filtering approaches
        from_date = f"{date_from} 00:00:00"
        to_date = f"{date_to} 23:59:59"
        
        # Method 1: Fetch all records
        logger.info("Testing Method 1: Fetch all records")
        all_records = await tata_admin_service.fetch_all_call_records(
            from_date=from_date,
            to_date=to_date,
            max_records=1000
        )
        
        # Method 2: Python filtering
        logger.info("Testing Method 2: Python filtering")
        user_records_python = [
            r for r in all_records 
            if r.get("agent_number") == user_agent_number
        ]
        
        # Method 3: TATA API filtering (test different formats)
        logger.info("Testing Method 3: TATA API filtering")
        
        # Test format 1: agent|+number
        tata_filters_1 = {"agents": [f"agent|{user_agent_number}"]}
        filtered_records_1 = await tata_admin_service.fetch_all_call_records(
            from_date=from_date,
            to_date=to_date,
            filters=tata_filters_1,
            max_records=1000
        )
        
        # Test format 2: just the number
        tata_filters_2 = {"agents": [user_agent_number]}
        filtered_records_2 = await tata_admin_service.fetch_all_call_records(
            from_date=from_date,
            to_date=to_date,
            filters=tata_filters_2,
            max_records=1000
        )
        
        # Get sample of agent numbers in data
        sample_agents = list(set(
            r.get("agent_number") for r in all_records[:50] 
            if r.get("agent_number")
        ))
        
        return {
            "success": True,
            "user_info": {
                "user_id": user_id,
                "user_name": user_name,
                "agent_number": user_agent_number
            },
            "date_range": f"{date_from} to {date_to}",
            "test_results": {
                "total_records_all_users": len(all_records),
                "python_filtered_records": len(user_records_python),
                "tata_filter_format_1": len(filtered_records_1),
                "tata_filter_format_2": len(filtered_records_2)
            },
            "filter_formats_tested": {
                "format_1": tata_filters_1,
                "format_2": tata_filters_2
            },
            "recommendations": {
                "python_filtering_works": len(user_records_python) > 0,
                "tata_api_filtering_works": len(filtered_records_1) > 0 or len(filtered_records_2) > 0,
                "recommended_method": "python" if len(user_records_python) > 0 else "investigate_further"
            },
            "debug_data": {
                "sample_agents_in_data": sample_agents[:10],
                "target_agent_found_in_sample": user_agent_number in sample_agents,
                "sample_user_records": user_records_python[:2] if user_records_python else []
            }
        }
        
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "user_id": user_id
        }

# ============================================================================
# SIMPLE DEBUGGING ENDPOINT
# ============================================================================

@router.get("/debug/agent-mapping-check")
async def debug_agent_mapping_check(current_user: Dict = Depends(get_admin_user)):
    """🔍 DEBUG: Quick check of agent mapping"""
    try:
        await tata_admin_service.initialize_agent_mapping()
        
        mapping_summary = []
        for agent_number, mapping in tata_admin_service.agent_user_mapping.items():
            mapping_summary.append({
                "agent_number": agent_number,
                "user_id": mapping.get("user_id"),
                "user_name": mapping.get("user_name")
            })
        
        return {
            "success": True,
            "total_mappings": len(mapping_summary),
            "mappings": mapping_summary,
            "hariharan_mapping": next(
                (m for m in mapping_summary if "686f894b1ca17da22b3533e7" in str(m.get("user_id"))), 
                "Not found"
            )
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# =============================================================================
# USER PERFORMANCE ENDPOINT
# =============================================================================

# Replace the entire get_user_call_performance function with this corrected version

@router.get("/user-performance/{user_id}")
async def get_user_call_performance(
    user_id: str,
    period: str = Query("weekly", description="Analysis period"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    include_day_comparison: bool = Query(True, description="Include day-to-day comparison"),
    current_user: Dict = Depends(get_admin_user)
):
    """🔧 FIXED: Get detailed performance data for a specific user using Python filtering"""
    try:
        logger.info(f"Admin {current_user.get('email')} requesting performance for user {user_id}")
        
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
        
        # Determine date range
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
        
        logger.info(f"🔍 Fetching user performance for {user_name} ({user_agent_number}) from {from_date} to {to_date}")
        
        # Fetch ALL call records and filter in Python
        all_call_records = await tata_admin_service.fetch_all_call_records(
            from_date=from_date,
            to_date=to_date,
            max_records=10000
        )
        
        logger.info(f"📊 Fetched {len(all_call_records)} total records")
        
        # Filter by user's agent number in Python
        user_call_records = [
            record for record in all_call_records
            if record.get("agent_number") == user_agent_number
        ]
        
        logger.info(f"🎯 Filtered to {len(user_call_records)} records for user {user_name}")
        
        # Calculate stats manually (more reliable than using the service)
        if user_call_records:
            total_calls = len(user_call_records)
            answered_calls = sum(1 for r in user_call_records if r.get("status") == "answered")
            missed_calls = total_calls - answered_calls
            total_duration = sum(r.get("call_duration", 0) for r in user_call_records if r.get("status") == "answered")
            recordings_count = sum(1 for r in user_call_records if r.get("recording_url"))
            
            success_rate = (answered_calls / total_calls * 100) if total_calls > 0 else 0.0
            avg_duration = (total_duration / answered_calls) if answered_calls > 0 else 0.0
            
            # Create stats based on period
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
                    "daily_recordings": recordings_count,
                    "weekly_calls": None,
                    "weekly_answered": None,
                    "weekly_missed": None,
                    "weekly_duration": None,
                    "weekly_recordings": None,
                    "monthly_calls": None,
                    "monthly_answered": None,
                    "monthly_missed": None,
                    "monthly_duration": None,
                    "monthly_recordings": None
                })
            elif period == "weekly":
                user_stats_data.update({
                    "daily_calls": 0,
                    "daily_answered": 0,
                    "daily_missed": 0,
                    "daily_duration": 0,
                    "daily_recordings": 0,
                    "weekly_calls": total_calls,
                    "weekly_answered": answered_calls,
                    "weekly_missed": missed_calls,
                    "weekly_duration": total_duration,
                    "weekly_recordings": recordings_count,
                    "monthly_calls": None,
                    "monthly_answered": None,
                    "monthly_missed": None,
                    "monthly_duration": None,
                    "monthly_recordings": None
                })
            else:  # monthly
                user_stats_data.update({
                    "daily_calls": 0,
                    "daily_answered": 0,
                    "daily_missed": 0,
                    "daily_duration": 0,
                    "daily_recordings": 0,
                    "weekly_calls": None,
                    "weekly_answered": None,
                    "weekly_missed": None,
                    "weekly_duration": None,
                    "weekly_recordings": None,
                    "monthly_calls": total_calls,
                    "monthly_answered": answered_calls,
                    "monthly_missed": missed_calls,
                    "monthly_duration": total_duration,
                    "monthly_recordings": recordings_count
                })
        else:
            # No records found - create empty stats
            user_stats_data = {
                "user_id": user_id,
                "user_name": user_name,
                "agent_number": user_agent_number,
                "daily_calls": 0,
                "daily_answered": 0,
                "daily_missed": 0,
                "daily_duration": 0,
                "daily_recordings": 0,
                "weekly_calls": None,
                "weekly_answered": None,
                "weekly_missed": None,
                "weekly_duration": None,
                "weekly_recordings": None,
                "monthly_calls": None,
                "monthly_answered": None,
                "monthly_missed": None,
                "monthly_duration": None,
                "monthly_recordings": None,
                "success_rate": 0.0,
                "avg_call_duration": 0.0
            }
        
        # Day-to-day comparison
        day_comparison = []
        if include_day_comparison and user_call_records:
            try:
                from collections import defaultdict
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
                    
            except Exception as e:
                logger.warning(f"Error calculating day comparison: {e}")
                day_comparison = []
        
        # Convert recent call records
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
                action="viewed_user_performance",
                target_user_id=user_id,
                target_user_name=user_name,
                details={
                    "period": period,
                    "date_range": f"{date_from} to {date_to}",
                    "records_analyzed": len(user_call_records),
                    "filtering_method": "python_based"
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
            "debug_info": {
                "total_records_fetched": len(all_call_records),
                "user_records_found": len(user_call_records),
                "filtering_method": "python_based",
                "agent_number_used": user_agent_number
            }
        }
        
        logger.info(f"✅ User performance analysis complete: {len(user_call_records)} records found for {user_name}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user performance: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": f"Failed to fetch user performance: {str(e)}",
                "user_id": user_id
            }
        )


# =============================================================================
# PERFORMANCE RANKING ENDPOINTS
# =============================================================================

@router.get("/weekly-performers", response_model=PerformanceRankingResponse)
async def get_weekly_performers(
    week_offset: int = Query(0, description="Weeks back from current week (0=current, 1=last week)"),
    top_n: int = Query(10, description="Number of top performers to return"),
    current_user: Dict = Depends(get_admin_user)
):
    """Get weekly top performers ranking"""
    try:
        # Calculate week dates
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday()) - timedelta(weeks=week_offset)
        week_end = week_start + timedelta(days=6)
        
        # Get weekly performers
        performers = await tata_admin_service.get_weekly_performers(
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
    """Get monthly top performers ranking"""
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
        
        # Get monthly performers
        performers = await tata_admin_service.get_monthly_performers(
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
# RECORDING MANAGEMENT ENDPOINT
# =============================================================================

# Replace and add these recording endpoints in your admin_calls.py

# =============================================================================
# ENHANCED RECORDING MANAGEMENT ENDPOINTS
# =============================================================================

@router.post("/play-recording")
async def play_user_recording(
    recording_request: PlayRecordingRequest,
    request: Request,
    current_user: Dict = Depends(get_admin_user)
):
    """
    🔧 FIXED: Admin endpoint to play user recordings with complete URL and activity logging
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
        
        # 🔧 STEP 1: Find the specific call record with recording URL
        # We need to search through recent calls to find the recording URL
        today = datetime.now()
        from_date = (today - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")  # Last 7 days
        to_date = today.strftime("%Y-%m-%d 23:59:59")
        
        # Fetch recent call records
        all_records = await tata_admin_service.fetch_all_call_records(
            from_date=from_date,
            to_date=to_date,
            max_records=5000  # Get enough records to find the call
        )
        
        # Find the specific call record
        target_call = None
        for record in all_records:
            if record.get("id") == recording_request.call_id or record.get("call_id") == recording_request.call_id:
                target_call = record
                break
        
        if not target_call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "call_not_found",
                    "message": f"Call {recording_request.call_id} not found in recent records",
                    "suggestion": "Call might be older than 7 days or call ID is incorrect"
                }
            )
        
        # 🔧 STEP 2: Get the complete recording URL from TATA record
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
        
        # 🔧 STEP 3: Enhance the recording URL with proper authentication if needed
        # The TATA API should provide a complete URL, but we can enhance it
        enhanced_recording_url = recording_url
        
        # Log admin activity with complete details
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
                "recording_url": enhanced_recording_url,
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
            "recording_url": enhanced_recording_url,
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
            "expires_at": datetime.utcnow() + timedelta(hours=1),  # URL expires in 1 hour
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

# =============================================================================
# NEW: GET ALL RECORDINGS FOR A USER
# =============================================================================
# Replace the get_user_recordings endpoint with this efficient version

@router.get("/user-recordings/{user_id}")
async def get_user_recordings(
    user_id: str,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(20, ge=1, le=100, description="Records per page (max 100)"),
    page: int = Query(1, ge=1, description="Page number"),
    current_user: Dict = Depends(get_admin_user)
):
    """
    🔧 EFFICIENT: Get user recordings with proper pagination (fetch only what's needed)
    """
    try:
        logger.info(f"Admin {current_user.get('email')} requesting recordings for user {user_id} (page {page}, limit {limit})")
        
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
        
        # Set default date range if not provided
        if not date_from or not date_to:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)  # Last 30 days default
            date_from = start_date.strftime("%Y-%m-%d")
            date_to = end_date.strftime("%Y-%m-%d")
        
        # Format dates for TATA API
        from_date = f"{date_from} 00:00:00"
        to_date = f"{date_to} 23:59:59"
        
        logger.info(f"🎵 Fetching recordings for {user_name} ({user_agent_number}) - Page {page}, Limit {limit}")
        
        # 🔧 STEP 1: Use paginated approach to fetch records efficiently
        # Calculate how many pages we might need to get enough recordings
        # Since not all calls have recordings, we fetch more records per API call
        records_per_api_call = min(limit * 3, 300)  # Fetch 3x more to account for calls without recordings
        
        all_user_recordings = []
        current_api_page = 1
        total_api_calls = 0
        max_api_calls = 5  # Safety limit to prevent infinite loops
        
        # We need to fetch enough records to have at least 'limit' recordings for the requested page
        target_recordings_needed = page * limit
        
        while len(all_user_recordings) < target_recordings_needed and total_api_calls < max_api_calls:
            logger.info(f"📡 API Call {total_api_calls + 1}: Fetching page {current_api_page} with {records_per_api_call} records")
            
            # Fetch records from TATA API
            batch_records = await tata_admin_service.fetch_call_records(
                from_date=from_date,
                to_date=to_date,
                page=current_api_page,
                limit=records_per_api_call
            )
            
            # Check if we got any records
            records = batch_records.get("results", [])
            if not records:
                logger.info("📭 No more records available from TATA API")
                break
            
            # Filter for this user's recordings only
            batch_user_recordings = []
            for record in records:
                if (record.get("agent_number") == user_agent_number and 
                    record.get("recording_url")):
                    
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
                            "recording_duration": record.get("call_duration", 0),
                            "created_at": f"{record.get('date')} {record.get('time')}",
                            "circle": record.get("circle", {})
                        }
                        batch_user_recordings.append(recording_info)
                    except Exception as e:
                        logger.warning(f"Error parsing recording: {e}")
                        continue
            
            all_user_recordings.extend(batch_user_recordings)
            
            logger.info(f"✅ Found {len(batch_user_recordings)} recordings in this batch. Total so far: {len(all_user_recordings)}")
            
            # If we got fewer records than requested, we've reached the end
            if len(records) < records_per_api_call:
                logger.info("📄 Reached end of available records")
                break
            
            current_api_page += 1
            total_api_calls += 1
        
        # 🔧 STEP 2: Sort recordings by date and time (newest first)
        all_user_recordings.sort(key=lambda x: f"{x['date']} {x['time']}", reverse=True)
        
        # 🔧 STEP 3: Apply client-side pagination to get the exact page requested
        total_recordings = len(all_user_recordings)
        start_index = (page - 1) * limit
        end_index = start_index + limit
        paginated_recordings = all_user_recordings[start_index:end_index]
        
        # 🔧 STEP 4: Calculate pagination info
        total_pages = (total_recordings + limit - 1) // limit if total_recordings > 0 else 1
        has_more = end_index < total_recordings
        
        # 🔧 STEP 5: Calculate statistics (only from what we have so far)
        total_duration = sum(r["call_duration"] for r in all_user_recordings)
        avg_duration = total_duration / len(all_user_recordings) if all_user_recordings else 0
        answered_recordings = [r for r in all_user_recordings if r["status"] == "answered"]
        
        # 🔧 STEP 6: Log admin activity
        await tata_admin_service.log_admin_activity(
            admin_user_id=str(current_user.get("user_id") or current_user.get("_id")),
            admin_email=current_user.get("email"),
            action="viewed_user_recordings",
            target_user_id=user_id,
            target_user_name=user_name,
            details={
                "date_range": f"{date_from} to {date_to}",
                "page": page,
                "limit": limit,
                "recordings_returned": len(paginated_recordings),
                "total_recordings_found": total_recordings,
                "api_calls_made": total_api_calls
            }
        )
        
        # 🔧 STEP 7: Build efficient response
        response = {
            "success": True,
            "user_id": user_id,
            "user_name": user_name,
            "agent_number": user_agent_number,
            "recordings": paginated_recordings,
            "pagination": {
                "current_page": page,
                "limit": limit,
                "total_recordings": total_recordings,
                "total_pages": total_pages,
                "has_more": has_more,
                "has_previous": page > 1,
                "next_page": page + 1 if has_more else None,
                "previous_page": page - 1 if page > 1 else None,
                "showing_records": f"{start_index + 1}-{min(end_index, total_recordings)} of {total_recordings}"
            },
            "statistics": {
                "recordings_on_this_page": len(paginated_recordings),
                "total_recordings_found": total_recordings,
                "total_duration_minutes": round(total_duration / 60, 2),
                "average_duration_seconds": round(avg_duration, 2),
                "answered_recordings": len(answered_recordings),
                "recording_success_rate": round(len(answered_recordings) / len(all_user_recordings) * 100, 2) if all_user_recordings else 0
            },
            "query_info": {
                "date_range": f"{date_from} to {date_to}",
                "api_calls_made": total_api_calls,
                "search_method": "paginated_efficient",
                "user_agent_number": user_agent_number
            },
            "retrieved_at": datetime.utcnow()
        }
        
        logger.info(f"✅ Successfully retrieved page {page} with {len(paginated_recordings)} recordings for {user_name}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user recordings: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": f"Failed to fetch user recordings: {str(e)}",
                "user_id": user_id
            }
        )

# =============================================================================
# ADDITIONAL ENDPOINT: GET RECORDING COUNT FOR USER (EFFICIENT)
# =============================================================================

@router.get("/user-recordings-count/{user_id}")
async def get_user_recordings_count(
    user_id: str,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: Dict = Depends(get_admin_user)
):
    """
    🆕 NEW: Get total recording count for a user (for pagination planning)
    """
    try:
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found in agent mapping"
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
        
        # Quick count: fetch first few pages to estimate
        total_recordings = 0
        page = 1
        max_pages = 3  # Limit for quick count
        
        while page <= max_pages:
            batch = await tata_admin_service.fetch_call_records(
                from_date=from_date,
                to_date=to_date,
                page=page,
                limit=100
            )
            
            records = batch.get("results", [])
            if not records:
                break
            
            # Count recordings for this user
            user_recordings_in_batch = sum(
                1 for r in records 
                if r.get("agent_number") == user_agent_number and r.get("recording_url")
            )
            
            total_recordings += user_recordings_in_batch
            
            if len(records) < 100:  # Last page
                break
                
            page += 1
        
        return {
            "success": True,
            "user_id": user_id,
            "user_name": user_name,
            "total_recordings": total_recordings,
            "date_range": f"{date_from} to {date_to}",
            "is_estimate": page >= max_pages,  # True if we stopped early
            "recommended_page_size": min(20, max(10, total_recordings // 10)) if total_recordings > 0 else 20
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to count recordings: {str(e)}"
        )

# =============================================================================
# NEW: GET RECORDING DETAILS BY CALL ID
# =============================================================================

@router.get("/recording/{call_id}")
async def get_recording_details(
    call_id: str,
    current_user: Dict = Depends(get_admin_user)
):
    """
    🆕 NEW: Get detailed information about a specific recording
    """
    try:
        logger.info(f"Admin {current_user.get('email')} requesting recording details for {call_id}")
        
        # Search for the call in recent records
        today = datetime.now()
        from_date = (today - timedelta(days=30)).strftime("%Y-%m-%d 00:00:00")
        to_date = today.strftime("%Y-%m-%d 23:59:59")
        
        all_records = await tata_admin_service.fetch_all_call_records(
            from_date=from_date,
            to_date=to_date,
            max_records=10000
        )
        
        # Find the specific call
        target_call = None
        for record in all_records:
            if (record.get("id") == call_id or 
                record.get("call_id") == call_id or 
                record.get("uuid") == call_id):
                target_call = record
                break
        
        if not target_call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "call_not_found",
                    "message": f"Call {call_id} not found in recent records",
                    "suggestion": "Call might be older than 30 days or call ID is incorrect"
                }
            )
        
        # Check if recording exists
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
        
        # Parse the call record for complete details
        parsed_record = tata_admin_service.parse_call_record(target_call)
        
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
                "file_format": "audio/wav",  # Assuming TATA uses WAV format
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
        
        # Set date ranges (you might want to make this configurable)
        today = datetime.now()
        min_date = (today - timedelta(days=90)).strftime("%Y-%m-%d")  # 90 days back
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
# SUMMARY STATISTICS ENDPOINTS
# =============================================================================

@router.get("/summary-stats")
async def get_summary_statistics(
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: Dict = Depends(get_admin_user)
):
    """Get high-level summary statistics for the admin dashboard"""
    try:
        # Use last 7 days if no dates provided
        if not date_from or not date_to:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            date_from = start_date.strftime("%Y-%m-%d")
            date_to = end_date.strftime("%Y-%m-%d")
        
        # Format for TATA API
        from_date = f"{date_from} 00:00:00"
        to_date = f"{date_to} 23:59:59"
        
        # Fetch call records
        call_records = await tata_admin_service.fetch_all_call_records(
            from_date=from_date,
            to_date=to_date
        )
        
        # Calculate summary statistics
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
        
        # Calculate trend analysis
        trend_data = performance_calculator.calculate_trend_analysis(call_records, 7)
        
        # Calculate peak hours
        peak_hours_data = performance_calculator.calculate_peak_hours(call_records)
        
        return {
            "success": True,
            "date_range": f"{date_from} to {date_to}",
            "summary": {
                "total_calls": total_calls,
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
            "calculated_at": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Error getting summary statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch summary statistics: {str(e)}"
        )




# =============================================================================
# NEW: COMPREHENSIVE PEAK HOURS ANALYTICS ENDPOINT
# =============================================================================

@router.get("/analytics/comprehensive-peak-hours")
async def get_comprehensive_peak_hours_analysis(
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    include_total: bool = Query(True, description="Include peak calling hours (all calls)"),
    include_answered: bool = Query(True, description="Include peak answered hours"),
    include_missed: bool = Query(True, description="Include peak missed hours"),
    user_ids: Optional[str] = Query(None, description="Comma-separated user IDs to filter"),
    current_user: Dict = Depends(get_admin_user)
):
    """
    🆕 NEW: Get comprehensive peak hours analysis
    - Peak calling hours (all calls)
    - Peak answered hours (when leads answer most)
    - Peak missed hours (when leads miss most)
    
    This endpoint provides all three peak hour analyses in a single efficient API call.
    """
    try:
        logger.info(f"Admin {current_user.get('email')} requesting comprehensive peak hours analysis")
        
        # Initialize agent mapping
        await tata_admin_service.initialize_agent_mapping()
        
        # Set default date range if not provided
        if not date_from or not date_to:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)  # Last 7 days default
            date_from = start_date.strftime("%Y-%m-%d")
            date_to = end_date.strftime("%Y-%m-%d")
        
        # Format dates for TATA API
        from_date = f"{date_from} 00:00:00"
        to_date = f"{date_to} 23:59:59"
        
        logger.info(f"📊 Fetching comprehensive peak hours analysis from {date_from} to {date_to}")
        
        # Fetch ALL call records first
        all_call_records = await tata_admin_service.fetch_all_call_records(
            from_date=from_date,
            to_date=to_date,
            max_records=10000
        )
        
        logger.info(f"📈 Fetched {len(all_call_records)} total call records")
        
        # Apply user filtering if specified
        filtered_call_records = all_call_records
        filter_info = {"applied": False, "user_count": 0, "agent_numbers": []}
        
        if user_ids:
            logger.info(f"🎯 Applying user filter for: {user_ids}")
            user_list = [uid.strip() for uid in user_ids.split(",")]
            
            # Build list of target agent numbers
            target_agent_numbers = []
            for user_id in user_list:
                for agent_number, mapping in tata_admin_service.agent_user_mapping.items():
                    if mapping.get("user_id") == user_id:
                        target_agent_numbers.append(agent_number)
                        logger.info(f"✅ User {user_id} -> Agent {agent_number}")
                        break
                else:
                    logger.warning(f"❌ User {user_id} not found in agent mapping")
            
            # Filter records by agent numbers
            if target_agent_numbers:
                original_count = len(filtered_call_records)
                filtered_call_records = [
                    record for record in all_call_records
                    if record.get("agent_number") in target_agent_numbers
                ]
                logger.info(f"🔍 User filtering: {original_count} -> {len(filtered_call_records)} records")
                
                filter_info = {
                    "applied": True,
                    "user_count": len(user_list),
                    "agent_numbers": target_agent_numbers,
                    "records_before_filter": original_count,
                    "records_after_filter": len(filtered_call_records)
                }
            else:
                logger.warning("No valid target agent numbers found")
                filtered_call_records = []
                filter_info = {
                    "applied": True,
                    "user_count": len(user_list),
                    "agent_numbers": [],
                    "error": "No valid agent numbers found for specified users"
                }
        
        # Calculate comprehensive peak hours using the performance calculator
        peak_hours_analysis = performance_calculator.calculate_comprehensive_peak_hours(
            call_records=filtered_call_records
        )
        
        # Validate the analysis was successful
        if not peak_hours_analysis.get("success", False):
            logger.error(f"Peak hours calculation failed: {peak_hours_analysis.get('error', 'Unknown error')}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "calculation_failed",
                    "message": "Failed to calculate peak hours",
                    "details": peak_hours_analysis.get("error", "Unknown error")
                }
            )
        
        # Filter results based on include flags
        response_data = {
            "success": True,
            "date_range": f"{date_from} to {date_to}",
            "analysis_type": "comprehensive_peak_hours",
            "filter_info": filter_info
        }
        
        if include_total:
            response_data["peak_calling_hours"] = peak_hours_analysis["peak_calling_hours"]
        
        if include_answered:
            response_data["peak_answered_hours"] = peak_hours_analysis["peak_answered_hours"]
        
        if include_missed:
            response_data["peak_missed_hours"] = peak_hours_analysis["peak_missed_hours"]
        
        # Always include summary and metadata
        response_data.update({
            "summary": peak_hours_analysis["summary"],
            "analysis_metadata": peak_hours_analysis["analysis_metadata"],
            "generated_at": datetime.utcnow(),
            "requested_by": current_user.get("email", "unknown"),
            "query_parameters": {
                "date_from": date_from,
                "date_to": date_to,
                "include_total": include_total,
                "include_answered": include_answered,
                "include_missed": include_missed,
                "user_filter_applied": bool(user_ids),
                "filtered_user_ids": user_ids.split(",") if user_ids else None
            }
        })
        
        # Add additional insights
        summary = peak_hours_analysis["summary"]
        if summary["total_calls"] > 0:
            response_data["insights"] = {
                "best_calling_time": peak_hours_analysis["analysis_metadata"].get("most_active_hour"),
                "best_answer_time": peak_hours_analysis["analysis_metadata"].get("best_answer_hour"), 
                "worst_miss_time": peak_hours_analysis["analysis_metadata"].get("worst_miss_hour"),
                "overall_answer_rate": summary["answer_rate"],
                "recommendation": _generate_peak_hours_recommendation(peak_hours_analysis)
            }
        
        # Log admin activity
        try:
            await tata_admin_service.log_admin_activity(
                admin_user_id=str(current_user.get("user_id") or current_user.get("_id", "unknown")),
                admin_email=current_user.get("email", "unknown"),
                action="viewed_comprehensive_peak_hours",
                details={
                    "date_range": f"{date_from} to {date_to}",
                    "total_calls_analyzed": summary["total_calls"],
                    "user_filter_applied": bool(user_ids),
                    "include_flags": {
                        "total": include_total,
                        "answered": include_answered, 
                        "missed": include_missed
                    }
                }
            )
        except Exception as e:
            logger.warning(f"Error logging admin activity: {e}")
        
        logger.info(f"✅ Comprehensive peak hours analysis complete: {summary['total_calls']} calls analyzed")
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in comprehensive peak hours analysis: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "internal_error",
                "message": f"Failed to analyze peak hours: {str(e)}",
                "date_range": f"{date_from} to {date_to}" if 'date_from' in locals() else "unknown"
            }
        )

def _generate_peak_hours_recommendation(analysis: Dict[str, Any]) -> str:
    """
    Generate actionable recommendation based on peak hours analysis
    """
    try:
        metadata = analysis.get("analysis_metadata", {})
        summary = analysis.get("summary", {})
        
        most_active = metadata.get("most_active_hour")
        best_answer = metadata.get("best_answer_hour") 
        worst_miss = metadata.get("worst_miss_hour")
        answer_rate = summary.get("answer_rate", 0)
        
        if answer_rate > 75:
            if best_answer == most_active:
                return f"Excellent performance! Peak activity hour ({most_active}:00) aligns with best answer rates. Continue focusing efforts during this time."
            else:
                return f"Good performance overall. Consider shifting some activity from hour {most_active}:00 to hour {best_answer}:00 for better answer rates."
        elif answer_rate > 50:
            return f"Moderate performance. Focus more calling efforts during hour {best_answer}:00 when leads are most responsive, and reduce activity during hour {worst_miss}:00."
        else:
            return f"Low answer rate detected. Strongly recommend concentrating calls during hour {best_answer}:00 and avoiding hour {worst_miss}:00. Consider lead quality review."
            
    except Exception:
        return "Unable to generate specific recommendation. Review peak hours data to optimize calling strategy."

# =============================================================================
# QUICK ENDPOINT: GET ONLY PEAK ANSWERED HOURS
# =============================================================================

@router.get("/analytics/peak-answered-hours")
async def get_peak_answered_hours_only(
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    user_ids: Optional[str] = Query(None, description="Comma-separated user IDs to filter"),
    current_user: Dict = Depends(get_admin_user)
):
    """
    🎯 QUICK: Get only peak answered hours (when leads answer most frequently)
    """
    try:
        # Call the comprehensive endpoint but return only answered hours
        comprehensive_result = await get_comprehensive_peak_hours_analysis(
            date_from=date_from,
            date_to=date_to,
            include_total=False,
            include_answered=True,
            include_missed=False,
            user_ids=user_ids,
            current_user=current_user
        )
        
        return {
            "success": True,
            "analysis_type": "peak_answered_hours_only",
            "date_range": comprehensive_result["date_range"],
            "peak_answered_hours": comprehensive_result["peak_answered_hours"],
            "summary": {
                "total_answered": comprehensive_result["summary"]["total_answered"],
                "answer_rate": comprehensive_result["summary"]["answer_rate"]
            },
            "best_answer_hour": comprehensive_result["analysis_metadata"]["best_answer_hour"],
            "generated_at": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Error getting peak answered hours: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get peak answered hours: {str(e)}"
        )

# =============================================================================
# QUICK ENDPOINT: GET ONLY PEAK MISSED HOURS  
# =============================================================================

@router.get("/analytics/peak-missed-hours")
async def get_peak_missed_hours_only(
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    user_ids: Optional[str] = Query(None, description="Comma-separated user IDs to filter"),
    current_user: Dict = Depends(get_admin_user)
):
    """
    ⚠️ QUICK: Get only peak missed hours (when leads miss calls most frequently)
    """
    try:
        # Call the comprehensive endpoint but return only missed hours
        comprehensive_result = await get_comprehensive_peak_hours_analysis(
            date_from=date_from,
            date_to=date_to,
            include_total=False,
            include_answered=False,
            include_missed=True,
            user_ids=user_ids,
            current_user=current_user
        )
        
        return {
            "success": True,
            "analysis_type": "peak_missed_hours_only",
            "date_range": comprehensive_result["date_range"],
            "peak_missed_hours": comprehensive_result["peak_missed_hours"],
            "summary": {
                "total_missed": comprehensive_result["summary"]["total_missed"],
                "miss_rate": comprehensive_result["summary"]["miss_rate"]
            },
            "worst_miss_hour": comprehensive_result["analysis_metadata"]["worst_miss_hour"],
            "generated_at": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Error getting peak missed hours: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get peak missed hours: {str(e)}"
        )
# =============================================================================
# EXPORT ENDPOINTS
# =============================================================================

@router.get("/export-call-data")
async def export_call_data(
    date_from: str = Query(..., description="Start date (YYYY-MM-DD)"),
    date_to: str = Query(..., description="End date (YYYY-MM-DD)"),
    format: str = Query("json", description="Export format (json, csv)"),
    user_ids: Optional[str] = Query(None, description="Comma-separated user IDs"),
    current_user: Dict = Depends(get_admin_user)
):
    """Export call data for analysis (Admin only)"""
    try:
        logger.info(f"Admin {current_user['email']} exporting call data")
        
        # Format dates for TATA API
        from_date = f"{date_from} 00:00:00"
        to_date = f"{date_to} 23:59:59"
        
        # Prepare filters
        tata_filters = {}
        if user_ids:
            user_list = [uid.strip() for uid in user_ids.split(",")]
            agent_filters = []
            for user_id in user_list:
                for agent_number, mapping in tata_admin_service.agent_user_mapping.items():
                    if mapping.get("user_id") == user_id:
                        agent_filters.append(f"agent|{agent_number}")
            if agent_filters:
                tata_filters["agents"] = agent_filters
        
        # Fetch call records
        call_records = await tata_admin_service.fetch_all_call_records(
            from_date=from_date,
            to_date=to_date,
            filters=tata_filters,
            max_records=10000  # Limit for exports
        )
        
        # Parse and enrich records
        parsed_records = []
        for record in call_records:
            parsed_record = tata_admin_service.parse_call_record(record)
            parsed_records.append(parsed_record.dict())
        
        # Log admin activity
        await tata_admin_service.log_admin_activity(
            admin_user_id=str(current_user.get("user_id") or current_user.get("_id")),
            admin_email=current_user["email"],
            action="exported_call_data",
            details={
                "date_range": f"{date_from} to {date_to}",
                "format": format,
                "record_count": len(parsed_records),
                "user_filter": user_ids
            }
        )
        
        if format.lower() == "csv":
            # Convert to CSV format (simplified)
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
# ADMIN ACTIVITY LOG ENDPOINTS
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
        # Only super admins or specific roles should see this
        # Add role checking here if needed
        
        # Use last 30 days if no dates provided
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
# Add these endpoints to your app/routers/admin_calls.py