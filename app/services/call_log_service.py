# app/services/call_log_service.py
# Call Log Service
# Handles call history management, analytics, and reporting

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from bson import ObjectId
import json

from ..config.database import get_database
from ..config.settings import get_settings
from ..models.call_log import (
    CallLogResponse, CallHistoryFilter, CallHistoryResponse, CallAnalytics,
    CallSummaryReport, CallStatus, CallOutcome, CallType, CallPriority,
    CallbackRequest, CallbackResponse, UpcomingCallbacksResponse,
    CallExportRequest, CallExportResponse, BulkCallResponse
)
from ..utils.dependencies import get_current_user

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CallLogService:
    """
    Comprehensive Call Log Service
    Handles call history, analytics, callbacks, and reporting
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.db = None
    
        
        # Configuration
        self.default_page_size = 20
        self.max_page_size = 100
        self.retention_days = getattr(self.settings, 'CALL_LOG_RETENTION_DAYS', 365)

    def _convert_objectid_to_str(self, obj):
        """Recursively convert ObjectId to string in any data structure"""
        if isinstance(obj, ObjectId):
            return str(obj)
        elif isinstance(obj, dict):
            return {key: self._convert_objectid_to_str(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_objectid_to_str(item) for item in obj]
        else:
            return obj

    async def _enrich_call_log(self, call_log: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich call log with user and lead information"""
        try:
            # Convert ObjectIds to strings
            enriched_log = self._convert_objectid_to_str(call_log)
            
            # Get caller user information
            caller_user_id = enriched_log.get("caller_user_id")
            if caller_user_id:
                user = await self.db.users.find_one({"_id": ObjectId(caller_user_id)})
                if user:
                    enriched_log["caller_name"] = user.get("full_name", user.get("name", "Unknown"))
                    enriched_log["caller_email"] = user.get("email")
            
            # Get lead information
            lead_id = enriched_log.get("lead_id")
            if lead_id and lead_id.startswith("LD-"):
                lead = await self.db.leads.find_one({"lead_id": lead_id})
                if lead:
                    enriched_log["lead_name"] = lead.get("name", lead.get("full_name"))
                    enriched_log["lead_email"] = lead.get("email")
                    enriched_log["lead_status"] = lead.get("status")
            
            # Calculate if callback is overdue
            scheduled_at = enriched_log.get("scheduled_at")
            if scheduled_at and isinstance(scheduled_at, datetime):
                enriched_log["is_overdue"] = scheduled_at < datetime.utcnow()
            
            return enriched_log
            
        except Exception as e:
            logger.error(f"Error enriching call log: {str(e)}")
            return self._convert_objectid_to_str(call_log)

    async def get_call_history(
        self, 
        filters: CallHistoryFilter,
        current_user: Dict[str, Any]
    ) -> CallHistoryResponse:
        """
        Get call history with filtering, pagination, and analytics
        
        Args:
            filters: Filter parameters
            current_user: Current user for permission checking
            
        Returns:
            CallHistoryResponse with paginated results
        """
        try:
            # Build MongoDB query based on filters
            query = {}
            
            # Permission-based filtering
            user_role = current_user.get("role", "user")
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            if user_role != "admin":
                # Regular users can only see their own calls
                query["caller_user_id"] = user_id
            
            # Apply filters
            if filters.lead_id:
                query["lead_id"] = filters.lead_id
            
            if filters.user_id and user_role == "admin":
                query["caller_user_id"] = filters.user_id
            
            if filters.call_type:
                query["call_type"] = filters.call_type.value
            
            if filters.call_status:
                query["call_status"] = filters.call_status.value
            
            if filters.call_outcome:
                query["call_outcome"] = filters.call_outcome.value
            
            if filters.phone_number:
                query["destination_number"] = {"$regex": filters.phone_number, "$options": "i"}
            
            # Date range filtering
            if filters.date_from or filters.date_to:
                date_query = {}
                if filters.date_from:
                    date_query["$gte"] = filters.date_from
                if filters.date_to:
                    date_query["$lte"] = filters.date_to
                query["created_at"] = date_query
            
            # Duration filtering
            if filters.min_duration is not None or filters.max_duration is not None:
                duration_query = {}
                if filters.min_duration is not None:
                    duration_query["$gte"] = filters.min_duration
                if filters.max_duration is not None:
                    duration_query["$lte"] = filters.max_duration
                query["call_duration"] = duration_query
            
            # Get total count
            total_count = await self.db.call_logs.count_documents(query)
            
            # Calculate pagination
            page = max(1, filters.page)
            limit = min(filters.limit, self.max_page_size)
            skip = (page - 1) * limit
            total_pages = (total_count + limit - 1) // limit
            has_more = page < total_pages
            
            # Build sort criteria
            sort_criteria = []
            if filters.sort_by and filters.sort_order:
                sort_direction = 1 if filters.sort_order.lower() == "asc" else -1
                sort_criteria.append((filters.sort_by, sort_direction))
            else:
                sort_criteria.append(("created_at", -1))  # Default: newest first
            
            # Execute query
            cursor = self.db.call_logs.find(query).sort(sort_criteria).skip(skip).limit(limit)
            call_logs = await cursor.to_list(length=limit)
            
            # Enrich call logs with user and lead information
            enriched_logs = []
            for log in call_logs:
                enriched_log = await self._enrich_call_log(log)
                enriched_logs.append(CallLogResponse(**enriched_log))
            
            # Generate analytics for filtered data
            analytics = await self._generate_call_analytics(query)
            
            logger.info(f"Retrieved {len(enriched_logs)} call logs for user {user_id}")
            
            return CallHistoryResponse(
                calls=enriched_logs,
                total_count=total_count,
                page=page,
                limit=limit,
                total_pages=total_pages,
                has_more=has_more,
                analytics=analytics
            )
            
        except Exception as e:
            logger.error(f"Error getting call history: {str(e)}")
            raise Exception(f"Failed to retrieve call history: {str(e)}")

    async def get_call_by_id(
        self, 
        call_log_id: str,
        current_user: Dict[str, Any]
    ) -> CallLogResponse:
        """
        Get single call log by ID with permission checking
        
        Args:
            call_log_id: Call log ID
            current_user: Current user for permission checking
            
        Returns:
            CallLogResponse object
        """
        try:
            # Get call log
            call_log = await self.db.call_logs.find_one({"_id": ObjectId(call_log_id)})
            if not call_log:
                raise Exception("Call log not found")
            
            # Check permissions
            user_role = current_user.get("role", "user")
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            if user_role != "admin":
                # Regular users can only access their own calls
                if str(call_log.get("caller_user_id")) != user_id:
                    raise Exception("Not authorized to access this call log")
            
            # Enrich and return
            enriched_log = await self._enrich_call_log(call_log)
            return CallLogResponse(**enriched_log)
            
        except Exception as e:
            logger.error(f"Error getting call log {call_log_id}: {str(e)}")
            raise

    async def _generate_call_analytics(self, query: Dict[str, Any]) -> CallAnalytics:
        """Generate analytics for calls matching the query"""
        try:
            # Aggregate pipeline for analytics
            pipeline = [
                {"$match": query},
                {
                    "$group": {
                        "_id": None,
                        "total_calls": {"$sum": 1},
                        "successful_calls": {
                            "$sum": {
                                "$cond": [
                                    {"$in": ["$call_outcome", ["successful", "interested", "meeting_scheduled"]]},
                                    1, 0
                                ]
                            }
                        },
                        "failed_calls": {
                            "$sum": {
                                "$cond": [
                                    {"$in": ["$call_status", ["failed", "busy", "no_answer", "timeout"]]},
                                    1, 0
                                ]
                            }
                        },
                        "total_duration": {"$sum": {"$ifNull": ["$call_duration", 0]}},
                        "avg_duration": {"$avg": {"$ifNull": ["$call_duration", 0]}},
                        
                        # Call type breakdown
                        "click_to_call_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_type", "click_to_call"]}, 1, 0]}
                        },
                        "support_call_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_type", "support_call"]}, 1, 0]}
                        },
                        "callback_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_type", "callback"]}, 1, 0]}
                        },
                        
                        # Outcome breakdown
                        "interested_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_outcome", "interested"]}, 1, 0]}
                        },
                        "not_interested_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_outcome", "not_interested"]}, 1, 0]}
                        },
                        "no_response_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_outcome", "no_response"]}, 1, 0]}
                        },
                        "callback_requested_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_outcome", "callback_requested"]}, 1, 0]}
                        }
                    }
                }
            ]
            
            result = await self.db.call_logs.aggregate(pipeline).to_list(length=1)
            
            if result:
                stats = result[0]
                total_calls = stats.get("total_calls", 0)
                successful_calls = stats.get("successful_calls", 0)
                
                return CallAnalytics(
                    total_calls=total_calls,
                    successful_calls=successful_calls,
                    failed_calls=stats.get("failed_calls", 0),
                    average_duration=stats.get("avg_duration", 0.0),
                    total_duration=stats.get("total_duration", 0),
                    success_rate=(successful_calls / total_calls * 100) if total_calls > 0 else 0.0,
                    
                    # Type breakdown
                    click_to_call_count=stats.get("click_to_call_count", 0),
                    support_call_count=stats.get("support_call_count", 0),
                    callback_count=stats.get("callback_count", 0),
                    
                    # Outcome breakdown
                    interested_count=stats.get("interested_count", 0),
                    not_interested_count=stats.get("not_interested_count", 0),
                    no_response_count=stats.get("no_response_count", 0),
                    callback_requested_count=stats.get("callback_requested_count", 0)
                )
            else:
                return CallAnalytics()
                
        except Exception as e:
            logger.error(f"Error generating call analytics: {str(e)}")
            return CallAnalytics()

    async def get_call_summary_report(
        self, 
        start_date: datetime,
        end_date: datetime,
        current_user: Dict[str, Any],
        report_type: str = "custom"
    ) -> CallSummaryReport:
        """
        Generate comprehensive call summary report
        
        Args:
            start_date: Report start date
            end_date: Report end date
            current_user: Current user
            report_type: Type of report (daily, weekly, monthly, custom)
            
        Returns:
            CallSummaryReport with comprehensive statistics
        """
        try:
            # Build base query
            query = {
                "created_at": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
            
            # Apply user permissions
            user_role = current_user.get("role", "user")
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            if user_role != "admin":
                query["caller_user_id"] = user_id
            
            # Get basic metrics
            total_calls = await self.db.call_logs.count_documents(query)
            
            # Calculate total duration in hours
            duration_pipeline = [
                {"$match": query},
                {"$group": {"_id": None, "total_duration": {"$sum": {"$ifNull": ["$call_duration", 0]}}}}
            ]
            duration_result = await self.db.call_logs.aggregate(duration_pipeline).to_list(length=1)
            total_duration_seconds = duration_result[0].get("total_duration", 0) if duration_result else 0
            total_duration_hours = total_duration_seconds / 3600
            
            # Count unique leads and callers
            unique_leads = len(await self.db.call_logs.distinct("lead_id", query))
            unique_callers = len(await self.db.call_logs.distinct("caller_user_id", query))
            
            # Calculate success and conversion rates
            successful_calls = await self.db.call_logs.count_documents({
                **query,
                "call_outcome": {"$in": ["successful", "interested", "meeting_scheduled"]}
            })
            
            success_rate = (successful_calls / total_calls * 100) if total_calls > 0 else 0
            avg_duration = total_duration_seconds / total_calls if total_calls > 0 else 0
            
            # Status breakdown
            status_pipeline = [
                {"$match": query},
                {"$group": {"_id": "$call_status", "count": {"$sum": 1}}}
            ]
            status_results = await self.db.call_logs.aggregate(status_pipeline).to_list(length=None)
            status_breakdown = {result["_id"]: result["count"] for result in status_results}
            
            # Outcome breakdown
            outcome_pipeline = [
                {"$match": query},
                {"$group": {"_id": "$call_outcome", "count": {"$sum": 1}}}
            ]
            outcome_results = await self.db.call_logs.aggregate(outcome_pipeline).to_list(length=None)
            outcome_breakdown = {result["_id"]: result["count"] for result in outcome_results}
            
            # Type breakdown
            type_pipeline = [
                {"$match": query},
                {"$group": {"_id": "$call_type", "count": {"$sum": 1}}}
            ]
            type_results = await self.db.call_logs.aggregate(type_pipeline).to_list(length=None)
            type_breakdown = {result["_id"]: result["count"] for result in type_results}
            
            # Top callers (admin only)
            top_callers = []
            if user_role == "admin":
                caller_pipeline = [
                    {"$match": query},
                    {"$group": {
                        "_id": "$caller_user_id",
                        "total_calls": {"$sum": 1},
                        "successful_calls": {
                            "$sum": {"$cond": [
                                {"$in": ["$call_outcome", ["successful", "interested"]]}, 1, 0
                            ]}
                        }
                    }},
                    {"$sort": {"total_calls": -1}},
                    {"$limit": 10}
                ]
                caller_results = await self.db.call_logs.aggregate(caller_pipeline).to_list(length=None)
                
                # Enrich with user names
                for caller in caller_results:
                    user = await self.db.users.find_one({"_id": ObjectId(caller["_id"])})
                    top_callers.append({
                        "user_id": caller["_id"],
                        "user_name": user.get("full_name", "Unknown") if user else "Unknown",
                        "total_calls": caller["total_calls"],
                        "successful_calls": caller["successful_calls"],
                        "success_rate": (caller["successful_calls"] / caller["total_calls"] * 100) if caller["total_calls"] > 0 else 0
                    })
            
            # Daily breakdown
            daily_pipeline = [
                {"$match": query},
                {
                    "$group": {
                        "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                        "calls": {"$sum": 1},
                        "successful": {
                            "$sum": {"$cond": [
                                {"$in": ["$call_outcome", ["successful", "interested"]]}, 1, 0
                            ]}
                        }
                    }
                },
                {"$sort": {"_id": 1}}
            ]
            daily_results = await self.db.call_logs.aggregate(daily_pipeline).to_list(length=None)
            daily_call_trend = [
                {
                    "date": result["_id"],
                    "calls": result["calls"],
                    "successful": result["successful"],
                    "success_rate": (result["successful"] / result["calls"] * 100) if result["calls"] > 0 else 0
                }
                for result in daily_results
            ]
            
            return CallSummaryReport(
                report_period=report_type,
                start_date=start_date,
                end_date=end_date,
                total_calls=total_calls,
                total_duration_hours=round(total_duration_hours, 2),
                unique_leads_contacted=unique_leads,
                unique_callers=unique_callers,
                success_rate=round(success_rate, 2),
                average_call_duration=round(avg_duration / 60, 2),  # in minutes
                conversion_rate=round(success_rate, 2),  # Same as success rate for now
                status_breakdown=status_breakdown,
                outcome_breakdown=outcome_breakdown,
                type_breakdown=type_breakdown,
                top_callers=top_callers,
                busiest_hours=[],  # Could be implemented
                daily_call_trend=daily_call_trend,
                success_trend=daily_call_trend  # Using same data for now
            )
            
        except Exception as e:
            logger.error(f"Error generating call summary report: {str(e)}")
            raise

    async def schedule_callback(
        self, 
        callback_request: CallbackRequest,
        current_user: Dict[str, Any]
    ) -> CallbackResponse:
        """
        Schedule a callback for a lead
        
        Args:
            callback_request: Callback request details
            current_user: Current user scheduling the callback
            
        Returns:
            CallbackResponse with scheduled callback details
        """
        try:
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            # Check if lead exists and user has access
            lead = await self.db.leads.find_one({"lead_id": callback_request.lead_id})
            if not lead:
                raise Exception("Lead not found")
            
            # Check permissions
            user_role = current_user.get("role", "user")
            if user_role != "admin":
                lead_assigned_to = str(lead.get("assigned_to", ""))
                if lead_assigned_to != user_id:
                    raise Exception("Not authorized to schedule callback for this lead")
            
            # Create callback entry
            callback_data = {
                "_id": ObjectId(),
                "lead_id": callback_request.lead_id,
                "scheduled_at": callback_request.scheduled_at,
                "priority": callback_request.priority.value,
                "notes": callback_request.notes,
                "assigned_to": callback_request.assigned_to or user_id,
                "created_at": datetime.utcnow(),
                "created_by": user_id,
                "status": CallStatus.INITIATED.value,
                "is_overdue": False
            }
            
            # Insert callback
            result = await self.db.call_logs.insert_one({
                **callback_data,
                "caller_user_id": callback_request.assigned_to or user_id,
                "destination_number": lead.get("phone", ""),
                "call_type": CallType.CALLBACK.value,
                "call_priority": callback_request.priority.value,
                "call_status": CallStatus.INITIATED.value
            })
            
            callback_id = str(result.inserted_id)
            
            # Log activity to lead
            await self.db.lead_activities.insert_one({
                "_id": ObjectId(),
                "lead_id": callback_request.lead_id,
                "activity_type": "callback_scheduled",
                "description": f"Callback scheduled for {callback_request.scheduled_at.strftime('%Y-%m-%d %H:%M')}",
                "created_by": user_id,
                "created_at": datetime.utcnow(),
                "metadata": {
                    "callback_id": callback_id,
                    "scheduled_at": callback_request.scheduled_at.isoformat(),
                    "priority": callback_request.priority.value
                }
            })
            
            # Get user names for response
            created_by_user = await self.db.users.find_one({"_id": ObjectId(user_id)})
            assigned_to_user = None
            if callback_request.assigned_to:
                assigned_to_user = await self.db.users.find_one({"_id": ObjectId(callback_request.assigned_to)})
            
            logger.info(f"Scheduled callback {callback_id} for lead {callback_request.lead_id}")
            
            return CallbackResponse(
                id=callback_id,
                lead_id=callback_request.lead_id,
                lead_name=lead.get("name", lead.get("full_name")),
                scheduled_at=callback_request.scheduled_at,
                priority=callback_request.priority,
                notes=callback_request.notes,
                assigned_to=callback_request.assigned_to or user_id,
                assigned_to_name=assigned_to_user.get("full_name") if assigned_to_user else created_by_user.get("full_name"),
                status=CallStatus.INITIATED,
                created_at=datetime.utcnow(),
                created_by=user_id,
                created_by_name=created_by_user.get("full_name", "Unknown"),
                is_overdue=False
            )
            
        except Exception as e:
            logger.error(f"Error scheduling callback: {str(e)}")
            raise

    async def get_upcoming_callbacks(
        self,
        current_user: Dict[str, Any],
        days_ahead: int = 7
    ) -> UpcomingCallbacksResponse:
        """
        Get upcoming callbacks for current user or all users (admin)
        
        Args:
            current_user: Current user
            days_ahead: Number of days to look ahead
            
        Returns:
            UpcomingCallbacksResponse with callback lists
        """
        try:
            user_role = current_user.get("role", "user")
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            # Build query
            end_date = datetime.utcnow() + timedelta(days=days_ahead)
            query = {
                "call_type": CallType.CALLBACK.value,
                "call_status": {"$in": [CallStatus.INITIATED.value, CallStatus.RINGING.value]},
                "scheduled_at": {"$lte": end_date}
            }
            
            if user_role != "admin":
                # Regular users see only their assigned callbacks
                query["$or"] = [
                    {"assigned_to": user_id},
                    {"caller_user_id": user_id}
                ]
            
            # Get callbacks
            callbacks_cursor = self.db.call_logs.find(query).sort("scheduled_at", 1)
            callbacks = await callbacks_cursor.to_list(length=None)
            
            # Enrich and categorize callbacks
            now = datetime.utcnow()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            week_end = today_start + timedelta(days=7)
            
            callback_responses = []
            overdue_count = 0
            today_count = 0
            this_week_count = 0
            
            for callback in callbacks:
                enriched = await self._enrich_call_log(callback)
                callback_response = CallbackResponse(**enriched)
                callback_responses.append(callback_response)
                
                scheduled_at = callback.get("scheduled_at")
                if scheduled_at:
                    if scheduled_at < now:
                        overdue_count += 1
                    elif today_start <= scheduled_at < today_end:
                        today_count += 1
                    elif scheduled_at < week_end:
                        this_week_count += 1
            
            return UpcomingCallbacksResponse(
                callbacks=callback_responses,
                overdue_count=overdue_count,
                today_count=today_count,
                this_week_count=this_week_count,
                total_count=len(callback_responses)
            )
            
        except Exception as e:
            logger.error(f"Error getting upcoming callbacks: {str(e)}")
            raise

    async def export_call_data(
        self,
        export_request: CallExportRequest,
        current_user: Dict[str, Any]
    ) -> CallExportResponse:
        """
        Export call data in specified format
        
        Args:
            export_request: Export configuration
            current_user: Current user
            
        Returns:
            CallExportResponse with download information
        """
        try:
            # This is a simplified implementation
            # In production, you'd generate actual files and store them
            
            # Get call history based on filters
            if export_request.filter_params:
                history_response = await self.get_call_history(export_request.filter_params, current_user)
                calls = history_response.calls
            else:
                # Default filter for recent calls
                default_filter = CallHistoryFilter(
                    date_from=datetime.utcnow() - timedelta(days=30),
                    limit=1000
                )
                history_response = await self.get_call_history(default_filter, current_user)
                calls = history_response.calls
            
            # Generate filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"call_export_{timestamp}.{export_request.format}"
            
            # In a real implementation, you would:
            # 1. Generate the actual file (CSV, Excel, PDF)
            # 2. Store it in a temporary location or cloud storage
            # 3. Return a download URL
            
            # For now, return a mock response
            download_url = f"/api/v1/downloads/{filename}"
            expires_at = datetime.utcnow() + timedelta(hours=24)
            
            logger.info(f"Generated export for {len(calls)} calls in {export_request.format} format")
            
            return CallExportResponse(
                success=True,
                download_url=download_url,
                file_name=filename,
                record_count=len(calls),
                file_size="2.5 MB",  # Mock size
                expires_at=expires_at,
                message=f"Successfully exported {len(calls)} call records"
            )
            
        except Exception as e:
            logger.error(f"Error exporting call data: {str(e)}")
            return CallExportResponse(
                success=False,
                file_name="",
                record_count=0,
                expires_at=datetime.utcnow(),
                message=f"Export failed: {str(e)}"
            )

    async def cleanup_old_calls(self):
        """Clean up old call logs based on retention policy"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)
            
            result = await self.db.call_logs.delete_many({
                "created_at": {"$lt": cutoff_date}
            })
            
            if result.deleted_count > 0:
                logger.info(f"Cleaned up {result.deleted_count} old call logs")
            
            return result.deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old calls: {str(e)}")
            return 0

    async def get_user_call_statistics(
        self,
        user_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get call statistics for a specific user"""
        try:
            start_date = datetime.utcnow() - timedelta(days=days)
            
            query = {
                "caller_user_id": user_id,
                "created_at": {"$gte": start_date}
            }
            
            # Aggregate user statistics
            pipeline = [
                {"$match": query},
                {
                    "$group": {
                        "_id": None,
                        "total_calls": {"$sum": 1},
                        "completed_calls": {
                            "$sum": {"$cond": [{"$eq": ["$call_status", "completed"]}, 1, 0]}
                        },
                        "successful_calls": {
                            "$sum": {"$cond": [
                                {"$in": ["$call_outcome", ["successful", "interested", "meeting_scheduled"]]}, 
                                1, 0
                            ]}
                        },
                        "total_duration": {"$sum": {"$ifNull": ["$call_duration", 0]}},
                        "avg_duration": {"$avg": {"$ifNull": ["$call_duration", 0]}},
                        "leads_contacted": {"$addToSet": "$lead_id"}
                    }
                }
            ]
            
            result = await self.db.call_logs.aggregate(pipeline).to_list(length=1)
            
            if result:
                stats = result[0]
                total_calls = stats.get("total_calls", 0)
                successful_calls = stats.get("successful_calls", 0)
                
                return {
                    "user_id": user_id,
                    "period_days": days,
                    "total_calls": total_calls,
                    "completed_calls": stats.get("completed_calls", 0),
                    "successful_calls": successful_calls,
                    "success_rate": (successful_calls / total_calls * 100) if total_calls > 0 else 0,
                    "total_duration_minutes": round(stats.get("total_duration", 0) / 60, 2),
                    "average_duration_minutes": round(stats.get("avg_duration", 0) / 60, 2),
                    "unique_leads_contacted": len(stats.get("leads_contacted", [])),
                    "calls_per_day": round(total_calls / days, 2)
                }
            else:
                return {
                    "user_id": user_id,
                    "period_days": days,
                    "total_calls": 0,
                    "completed_calls": 0,
                    "successful_calls": 0,
                    "success_rate": 0,
                    "total_duration_minutes": 0,
                    "average_duration_minutes": 0,
                    "unique_leads_contacted": 0,
                    "calls_per_day": 0
                }
                
        except Exception as e:
            logger.error(f"Error getting user call statistics: {str(e)}")
            return {"error": str(e)}

    async def get_lead_call_history(
        self,
        lead_id: str,
        current_user: Dict[str, Any]
    ) -> List[CallLogResponse]:
        """Get all calls for a specific lead"""
        try:
            # Check lead access permission
            lead = await self.db.leads.find_one({"lead_id": lead_id})
            if not lead:
                raise Exception("Lead not found")
            
            user_role = current_user.get("role", "user")
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            if user_role != "admin":
                lead_assigned_to = str(lead.get("assigned_to", ""))
                if lead_assigned_to != user_id:
                    raise Exception("Not authorized to access this lead's call history")
            
            # Get call history for lead
            query = {"lead_id": lead_id}
            calls_cursor = self.db.call_logs.find(query).sort("created_at", -1)
            calls = await calls_cursor.to_list(length=None)
            
            # Enrich calls
            enriched_calls = []
            for call in calls:
                enriched_call = await self._enrich_call_log(call)
                enriched_calls.append(CallLogResponse(**enriched_call))
            
            return enriched_calls
            
        except Exception as e:
            logger.error(f"Error getting lead call history: {str(e)}")
            raise

    async def update_callback_status(
        self,
        callback_id: str,
        status: CallStatus,
        current_user: Dict[str, Any]
    ) -> bool:
        """Update callback status"""
        try:
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            user_role = current_user.get("role", "user")
            
            # Get callback
            callback = await self.db.call_logs.find_one({"_id": ObjectId(callback_id)})
            if not callback:
                raise Exception("Callback not found")
            
            # Check permissions
            if user_role != "admin":
                if str(callback.get("assigned_to")) != user_id and str(callback.get("caller_user_id")) != user_id:
                    raise Exception("Not authorized to update this callback")
            
            # Update status
            update_data = {
                "call_status": status.value,
                "updated_at": datetime.utcnow()
            }
            
            if status in [CallStatus.COMPLETED, CallStatus.FAILED, CallStatus.CANCELLED]:
                update_data["ended_at"] = datetime.utcnow()
            
            await self.db.call_logs.update_one(
                {"_id": ObjectId(callback_id)},
                {"$set": update_data}
            )
            
            # Log activity
            lead_id = callback.get("lead_id")
            if lead_id and lead_id.startswith("LD-"):
                await self.db.lead_activities.insert_one({
                    "_id": ObjectId(),
                    "lead_id": lead_id,
                    "activity_type": "callback_status_updated",
                    "description": f"Callback status updated to {status.value}",
                    "created_by": user_id,
                    "created_at": datetime.utcnow(),
                    "metadata": {"callback_id": callback_id, "new_status": status.value}
                })
            
            logger.info(f"Updated callback {callback_id} status to {status.value}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating callback status: {str(e)}")
            return False

    async def search_calls(
        self,
        search_query: str,
        current_user: Dict[str, Any],
        limit: int = 20
    ) -> List[CallLogResponse]:
        """Search calls by notes, lead name, phone number, etc."""
        try:
            user_role = current_user.get("role", "user")
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            # Build search query
            search_conditions = [
                {"notes": {"$regex": search_query, "$options": "i"}},
                {"destination_number": {"$regex": search_query, "$options": "i"}},
                {"custom_identifier": {"$regex": search_query, "$options": "i"}}
            ]
            
            query = {"$or": search_conditions}
            
            # Apply user permissions
            if user_role != "admin":
                query["caller_user_id"] = user_id
            
            # Execute search
            calls_cursor = self.db.call_logs.find(query).sort("created_at", -1).limit(limit)
            calls = await calls_cursor.to_list(length=limit)
            
            # Enrich results
            enriched_calls = []
            for call in calls:
                enriched_call = await self._enrich_call_log(call)
                enriched_calls.append(CallLogResponse(**enriched_call))
            
            logger.info(f"Search for '{search_query}' returned {len(enriched_calls)} results")
            return enriched_calls
            
        except Exception as e:
            logger.error(f"Error searching calls: {str(e)}")
            return []

    async def get_call_trends(
        self,
        current_user: Dict[str, Any],
        days: int = 30
    ) -> Dict[str, Any]:
        """Get call trends and patterns"""
        try:
            user_role = current_user.get("role", "user")
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # Build base query
            query = {"created_at": {"$gte": start_date}}
            if user_role != "admin":
                query["caller_user_id"] = user_id
            
            # Daily trend
            daily_pipeline = [
                {"$match": query},
                {
                    "$group": {
                        "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                        "total_calls": {"$sum": 1},
                        "successful_calls": {
                            "$sum": {"$cond": [
                                {"$in": ["$call_outcome", ["successful", "interested"]]}, 1, 0
                            ]}
                        }
                    }
                },
                {"$sort": {"_id": 1}}
            ]
            
            daily_results = await self.db.call_logs.aggregate(daily_pipeline).to_list(length=None)
            
            # Hourly pattern
            hourly_pipeline = [
                {"$match": query},
                {
                    "$group": {
                        "_id": {"$hour": "$created_at"},
                        "call_count": {"$sum": 1}
                    }
                },
                {"$sort": {"_id": 1}}
            ]
            
            hourly_results = await self.db.call_logs.aggregate(hourly_pipeline).to_list(length=None)
            
            # Outcome trends
            outcome_pipeline = [
                {"$match": query},
                {
                    "$group": {
                        "_id": {
                            "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                            "outcome": "$call_outcome"
                        },
                        "count": {"$sum": 1}
                    }
                }
            ]
            
            outcome_results = await self.db.call_logs.aggregate(outcome_pipeline).to_list(length=None)
            
            return {
                "period_days": days,
                "daily_trend": [
                    {
                        "date": result["_id"],
                        "total_calls": result["total_calls"],
                        "successful_calls": result["successful_calls"],
                        "success_rate": (result["successful_calls"] / result["total_calls"] * 100) if result["total_calls"] > 0 else 0
                    }
                    for result in daily_results
                ],
                "hourly_pattern": [
                    {
                        "hour": result["_id"],
                        "call_count": result["call_count"]
                    }
                    for result in hourly_results
                ],
                "outcome_trends": outcome_results
            }
            
        except Exception as e:
            logger.error(f"Error getting call trends: {str(e)}")
            return {"error": str(e)}

    async def get_performance_metrics(
        self,
        current_user: Dict[str, Any],
        period_days: int = 30
    ) -> Dict[str, Any]:
        """Get comprehensive performance metrics"""
        try:
            user_role = current_user.get("role", "user")
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            start_date = datetime.utcnow() - timedelta(days=period_days)
            
            # Base query
            query = {"created_at": {"$gte": start_date}}
            if user_role != "admin":
                query["caller_user_id"] = user_id
            
            # Performance metrics pipeline
            pipeline = [
                {"$match": query},
                {
                    "$group": {
                        "_id": None,
                        "total_calls": {"$sum": 1},
                        "answered_calls": {
                            "$sum": {"$cond": [
                                {"$in": ["$call_status", ["answered", "completed"]]}, 1, 0
                            ]}
                        },
                        "completed_calls": {
                            "$sum": {"$cond": [{"$eq": ["$call_status", "completed"]}, 1, 0]}
                        },
                        "successful_calls": {
                            "$sum": {"$cond": [
                                {"$in": ["$call_outcome", ["successful", "interested", "meeting_scheduled"]]}, 1, 0
                            ]}
                        },
                        "avg_duration": {"$avg": {"$ifNull": ["$call_duration", 0]}},
                        "total_talk_time": {"$sum": {"$ifNull": ["$call_duration", 0]}},
                        "unique_leads": {"$addToSet": "$lead_id"}
                    }
                }
            ]
            
            result = await self.db.call_logs.aggregate(pipeline).to_list(length=1)
            
            if result:
                stats = result[0]
                total_calls = stats.get("total_calls", 0)
                answered_calls = stats.get("answered_calls", 0)
                completed_calls = stats.get("completed_calls", 0)
                successful_calls = stats.get("successful_calls", 0)
                
                return {
                    "period_days": period_days,
                    "total_calls": total_calls,
                    "answer_rate": (answered_calls / total_calls * 100) if total_calls > 0 else 0,
                    "completion_rate": (completed_calls / total_calls * 100) if total_calls > 0 else 0,
                    "success_rate": (successful_calls / total_calls * 100) if total_calls > 0 else 0,
                    "conversion_rate": (successful_calls / answered_calls * 100) if answered_calls > 0 else 0,
                    "average_call_duration": round(stats.get("avg_duration", 0) / 60, 2),  # minutes
                    "total_talk_time_hours": round(stats.get("total_talk_time", 0) / 3600, 2),
                    "unique_leads_contacted": len(stats.get("unique_leads", [])),
                    "calls_per_day": round(total_calls / period_days, 2),
                    "productivity_score": self._calculate_productivity_score(stats, total_calls)
                }
            else:
                return {
                    "period_days": period_days,
                    "total_calls": 0,
                    "answer_rate": 0,
                    "completion_rate": 0,
                    "success_rate": 0,
                    "conversion_rate": 0,
                    "average_call_duration": 0,
                    "total_talk_time_hours": 0,
                    "unique_leads_contacted": 0,
                    "calls_per_day": 0,
                    "productivity_score": 0
                }
                
        except Exception as e:
            logger.error(f"Error getting performance metrics: {str(e)}")
            return {"error": str(e)}

    def _calculate_productivity_score(self, stats: Dict[str, Any], total_calls: int) -> float:
        """Calculate a productivity score based on multiple factors"""
        try:
            if total_calls == 0:
                return 0
            
            # Factors for productivity score (0-100)
            success_rate = (stats.get("successful_calls", 0) / total_calls) * 100
            completion_rate = (stats.get("completed_calls", 0) / total_calls) * 100
            avg_duration = stats.get("avg_duration", 0)
            
            # Weights for different factors
            success_weight = 0.4
            completion_weight = 0.3
            duration_weight = 0.2
            volume_weight = 0.1
            
            # Duration score (optimal range: 2-10 minutes)
            optimal_duration = 300  # 5 minutes
            if avg_duration > 0:
                duration_score = max(0, 100 - abs(avg_duration - optimal_duration) / optimal_duration * 100)
            else:
                duration_score = 0
            
            # Volume score (calls per day, normalized to 0-100)
            volume_score = min(100, (total_calls / 30) * 10)  # Assume 10 calls/day is good
            
            # Calculate weighted score
            productivity_score = (
                success_rate * success_weight +
                completion_rate * completion_weight +
                duration_score * duration_weight +
                volume_score * volume_weight
            )
            
            return round(productivity_score, 2)
            
        except Exception as e:
            logger.error(f"Error calculating productivity score: {str(e)}")
            return 0

# Create singleton instance
call_log_service = CallLogService()