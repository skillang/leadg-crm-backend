# app/utils/performance_calculator.py
# Performance calculation utilities for admin dashboard
# Calculates various metrics from TATA call data

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import calendar

from ..models.admin_dashboard import (
    UserCallStats, DayComparisonStats, 
)

logger = logging.getLogger(__name__)

class PerformanceCalculator:
    """
    Performance calculation utilities for call analytics
    - Calculates various performance metrics
    - Handles ranking algorithms
    - Provides statistical analysis
    """
    
    def __init__(self):
        # Performance scoring weights
        self.scoring_weights = {
            "call_volume": 0.4,      # 40% weight for total calls
            "success_rate": 0.3,     # 30% weight for answer rate
            "call_duration": 0.2,    # 20% weight for talk time
            "recordings": 0.1        # 10% weight for recordings
        }
    
    # def calculate_performance_score(
    #     self,
    #     total_calls: int,
    #     success_rate: float,
    #     total_duration: int,
    #     recordings_count: int,
    #     max_calls: int = 100,
    #     max_duration: int = 3600  # 1 hour
    # ) -> float:
    #     """
    #     Calculate weighted performance score
        
    #     Args:
    #         total_calls: Total number of calls
    #         success_rate: Success rate percentage (0-100)
    #         total_duration: Total call duration in seconds
    #         recordings_count: Number of recordings
    #         max_calls: Maximum calls for normalization
    #         max_duration: Maximum duration for normalization
            
    #     Returns:
    #         Performance score (0-100)
    #     """
    #     try:
    #         # Normalize metrics to 0-1 scale
    #         normalized_calls = min(total_calls / max_calls, 1.0) if max_calls > 0 else 0
    #         normalized_success = success_rate / 100.0 if success_rate <= 100 else 1.0
    #         normalized_duration = min(total_duration / max_duration, 1.0) if max_duration > 0 else 0
    #         normalized_recordings = min(recordings_count / max_calls, 1.0) if max_calls > 0 else 0
            
    #         # Calculate weighted score
    #         score = (
    #             normalized_calls * self.scoring_weights["call_volume"] +
    #             normalized_success * self.scoring_weights["success_rate"] +
    #             normalized_duration * self.scoring_weights["call_duration"] +
    #             normalized_recordings * self.scoring_weights["recordings"]
    #         ) * 100
            
    #         return round(score, 2)
            
    #     except Exception as e:
    #         logger.error(f"Error calculating performance score: {e}")
    #         return 0.0
    
    def rank_performers(
    self,
    user_stats: List[Dict],  # Changed from Dict[str, UserCallStats]
    top_n: Optional[int] = None
) -> List[Dict]:
        """
        Simple ranking based on user performance data
        
        Args:
            user_stats: List of user performance dictionaries
            top_n: Number of top performers to return
            
        Returns:
            List of ranked performers
        """
        try:
            if not user_stats:
                return []
            
            # Sort by success rate, then by total calls
            sorted_performers = sorted(
                user_stats, 
                key=lambda x: (x.get("success_rate", 0), x.get("total_calls", 0)), 
                reverse=True
            )
            
            # Add rank
            for i, performer in enumerate(sorted_performers):
                performer["rank"] = i + 1
            
            return sorted_performers[:top_n] if top_n else sorted_performers
            
        except Exception as e:
            logger.error(f"Error ranking performers: {e}")
            return []


    def calculate_day_comparison(
        self,
        call_records: List[Dict],
        user_id: str,
        date_range: Tuple[datetime, datetime]
    ) -> List[DayComparisonStats]:
        """
        Calculate day-to-day comparison for a user
        
        Args:
            call_records: List of call records
            user_id: User ID to analyze
            date_range: Tuple of (start_date, end_date)
            
        Returns:
            List of daily comparison statistics
        """
        try:
            start_date, end_date = date_range
            
            # Group records by date
            daily_data = defaultdict(lambda: {
                "total_calls": 0,
                "answered_calls": 0,
                "missed_calls": 0,
                "total_duration": 0,
                "recordings_count": 0
            })
            
            # Process call records
            for record in call_records:
                # Filter by user (assuming user_id is mapped to agent_number)
                # This filtering logic depends on how user_id relates to call records
                record_date = record.get("date", "")
                if not record_date:
                    continue
                
                # Parse date and check if in range
                try:
                    record_dt = datetime.strptime(record_date, "%Y-%m-%d")
                    if not (start_date <= record_dt <= end_date):
                        continue
                except ValueError:
                    continue
                
                # Update daily stats
                stats = daily_data[record_date]
                stats["total_calls"] += 1
                
                if record.get("status") == "answered":
                    stats["answered_calls"] += 1
                    stats["total_duration"] += record.get("call_duration", 0)
                else:
                    stats["missed_calls"] += 1
                
                if record.get("recording_url"):
                    stats["recordings_count"] += 1
            
            # Convert to DayComparisonStats objects
            result = []
            sorted_dates = sorted(daily_data.keys())
            
            for i, date in enumerate(sorted_dates):
                stats = daily_data[date]
                
                # Calculate success rate
                success_rate = (
                    (stats["answered_calls"] / stats["total_calls"]) * 100
                    if stats["total_calls"] > 0 else 0.0
                )
                
                # Calculate change from previous day
                calls_change = 0
                calls_change_percent = 0.0
                trend = "stable"
                
                if i > 0:
                    prev_date = sorted_dates[i - 1]
                    prev_stats = daily_data[prev_date]
                    
                    calls_change = stats["total_calls"] - prev_stats["total_calls"]
                    
                    if prev_stats["total_calls"] > 0:
                        calls_change_percent = (calls_change / prev_stats["total_calls"]) * 100
                    
                    if calls_change > 0:
                        trend = "up"
                    elif calls_change < 0:
                        trend = "down"
                
                result.append(DayComparisonStats(
                    date=date,
                    total_calls=stats["total_calls"],
                    answered_calls=stats["answered_calls"],
                    missed_calls=stats["missed_calls"],
                    total_duration=stats["total_duration"],
                    success_rate=round(success_rate, 2),
                    recordings_count=stats["recordings_count"],
                    calls_change=calls_change,
                    calls_change_percent=round(calls_change_percent, 2),
                    trend=trend
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating day comparison: {e}")
            return []
    
    def calculate_weekly_stats(
        self,
        call_records: List[Dict],
        week_start: datetime
    ) -> Dict[str, Any]:
        """
        Calculate weekly statistics for all users
        
        Args:
            call_records: List of call records
            week_start: Start of the week
            
        Returns:
            Dictionary with weekly statistics
        """
        try:
            week_end = week_start + timedelta(days=6)
            week_start_str = week_start.strftime("%Y-%m-%d")
            week_end_str = week_end.strftime("%Y-%m-%d")
            
            # Group by user
            user_stats = defaultdict(lambda: {
                "total_calls": 0,
                "answered_calls": 0,
                "missed_calls": 0,
                "total_duration": 0,
                "recordings_count": 0,
                "daily_breakdown": defaultdict(int)
            })
            
            for record in call_records:
                record_date = record.get("date", "")
                if not (week_start_str <= record_date <= week_end_str):
                    continue
                
                # Map to user (this logic depends on your user mapping)
                agent_number = record.get("agent_number", "")
                user_id = f"user_{agent_number}"  # Simplified mapping
                
                stats = user_stats[user_id]
                stats["total_calls"] += 1
                stats["daily_breakdown"][record_date] += 1
                
                if record.get("status") == "answered":
                    stats["answered_calls"] += 1
                    stats["total_duration"] += record.get("call_duration", 0)
                else:
                    stats["missed_calls"] += 1
                
                if record.get("recording_url"):
                    stats["recordings_count"] += 1
            
            # Calculate summary statistics
            total_users = len(user_stats)
            total_calls = sum(stats["total_calls"] for stats in user_stats.values())
            total_answered = sum(stats["answered_calls"] for stats in user_stats.values())
            total_duration = sum(stats["total_duration"] for stats in user_stats.values())
            total_recordings = sum(stats["recordings_count"] for stats in user_stats.values())
            
            overall_success_rate = (
                (total_answered / total_calls) * 100 
                if total_calls > 0 else 0.0
            )
            
            return {
                "week_start": week_start_str,
                "week_end": week_end_str,
                "total_users": total_users,
                "total_calls": total_calls,
                "total_answered": total_answered,
                "total_missed": total_calls - total_answered,
                "total_duration": total_duration,
                "total_recordings": total_recordings,
                "overall_success_rate": round(overall_success_rate, 2),
                "avg_calls_per_user": round(total_calls / total_users, 2) if total_users > 0 else 0,
                "avg_duration_per_call": round(total_duration / total_answered, 2) if total_answered > 0 else 0,
                "user_stats": dict(user_stats)
            }
            
        except Exception as e:
            logger.error(f"Error calculating weekly stats: {e}")
            return {}
    
    def calculate_monthly_stats(
        self,
        call_records: List[Dict],
        year: int,
        month: int
    ) -> Dict[str, Any]:
        """
        Calculate monthly statistics for all users
        
        Args:
            call_records: List of call records
            year: Year
            month: Month (1-12)
            
        Returns:
            Dictionary with monthly statistics
        """
        try:
            # Get month boundaries
            month_start = datetime(year, month, 1)
            last_day = calendar.monthrange(year, month)[1]
            month_end = datetime(year, month, last_day)
            
            month_start_str = month_start.strftime("%Y-%m-%d")
            month_end_str = month_end.strftime("%Y-%m-%d")
            
            # Similar logic to weekly stats but for the entire month
            user_stats = defaultdict(lambda: {
                "total_calls": 0,
                "answered_calls": 0,
                "missed_calls": 0,
                "total_duration": 0,
                "recordings_count": 0,
                "weekly_breakdown": defaultdict(int)
            })
            
            for record in call_records:
                record_date = record.get("date", "")
                if not (month_start_str <= record_date <= month_end_str):
                    continue
                
                # Get week number for weekly breakdown
                try:
                    record_dt = datetime.strptime(record_date, "%Y-%m-%d")
                    week_num = record_dt.isocalendar()[1]
                except ValueError:
                    week_num = 0
                
                agent_number = record.get("agent_number", "")
                user_id = f"user_{agent_number}"
                
                stats = user_stats[user_id]
                stats["total_calls"] += 1
                stats["weekly_breakdown"][week_num] += 1
                
                if record.get("status") == "answered":
                    stats["answered_calls"] += 1
                    stats["total_duration"] += record.get("call_duration", 0)
                else:
                    stats["missed_calls"] += 1
                
                if record.get("recording_url"):
                    stats["recordings_count"] += 1
            
            # Calculate summary
            total_users = len(user_stats)
            total_calls = sum(stats["total_calls"] for stats in user_stats.values())
            total_answered = sum(stats["answered_calls"] for stats in user_stats.values())
            total_duration = sum(stats["total_duration"] for stats in user_stats.values())
            total_recordings = sum(stats["recordings_count"] for stats in user_stats.values())
            
            overall_success_rate = (
                (total_answered / total_calls) * 100 
                if total_calls > 0 else 0.0
            )
            
            return {
                "year": year,
                "month": month,
                "month_name": calendar.month_name[month],
                "month_start": month_start_str,
                "month_end": month_end_str,
                "total_users": total_users,
                "total_calls": total_calls,
                "total_answered": total_answered,
                "total_missed": total_calls - total_answered,
                "total_duration": total_duration,
                "total_recordings": total_recordings,
                "overall_success_rate": round(overall_success_rate, 2),
                "avg_calls_per_user": round(total_calls / total_users, 2) if total_users > 0 else 0,
                "avg_duration_per_call": round(total_duration / total_answered, 2) if total_answered > 0 else 0,
                "user_stats": dict(user_stats)
            }
            
        except Exception as e:
            logger.error(f"Error calculating monthly stats: {e}")
            return {}

    def calculate_trend_analysis(
        self,
        call_records: List[Dict],
        period_days: int = 7
    ) -> Dict[str, Any]:
        """
        Calculate trend analysis for the specified period
        
        Args:
            call_records: List of call records
            period_days: Number of days to analyze
            
        Returns:
            Trend analysis data
        """
        try:
            # Group by date
            daily_stats = defaultdict(lambda: {
                "total_calls": 0,
                "answered_calls": 0,
                "total_duration": 0
            })
            
            for record in call_records:
                record_date = record.get("date", "")
                if not record_date:
                    continue
                
                stats = daily_stats[record_date]
                stats["total_calls"] += 1
                
                if record.get("status") == "answered":
                    stats["answered_calls"] += 1
                    stats["total_duration"] += record.get("call_duration", 0)
            
            # Calculate trends
            sorted_dates = sorted(daily_stats.keys())
            if len(sorted_dates) < 2:
                return {"trend": "insufficient_data", "change_percent": 0.0}
            
            # Compare first half with second half
            mid_point = len(sorted_dates) // 2
            first_half = sorted_dates[:mid_point]
            second_half = sorted_dates[mid_point:]
            
            first_half_calls = sum(daily_stats[date]["total_calls"] for date in first_half)
            second_half_calls = sum(daily_stats[date]["total_calls"] for date in second_half)
            
            first_half_avg = first_half_calls / len(first_half) if first_half else 0
            second_half_avg = second_half_calls / len(second_half) if second_half else 0
            
            # Calculate trend
            if first_half_avg == 0:
                change_percent = 0.0
                trend = "stable"
            else:
                change_percent = ((second_half_avg - first_half_avg) / first_half_avg) * 100
                
                if change_percent > 5:
                    trend = "increasing"
                elif change_percent < -5:
                    trend = "decreasing"
                else:
                    trend = "stable"
            
            return {
                "trend": trend,
                "change_percent": round(change_percent, 2),
                "first_half_avg": round(first_half_avg, 2),
                "second_half_avg": round(second_half_avg, 2),
                "total_days_analyzed": len(sorted_dates)
            }
            
        except Exception as e:
            logger.error(f"Error calculating trend analysis: {e}")
            return {"trend": "error", "change_percent": 0.0}
    
    def calculate_peak_hours(
        self,
        call_records: List[Dict]
    ) -> Dict[str, Any]:
        """
        Calculate peak calling hours (existing method - unchanged)
        
        Args:
            call_records: List of call records
            
        Returns:
            Peak hours analysis
        """
        try:
            hourly_stats = defaultdict(int)
            
            for record in call_records:
                call_time = record.get("time", "")
                if not call_time:
                    continue
                
                try:
                    # Extract hour from time (HH:MM:SS format)
                    hour = int(call_time.split(":")[0])
                    hourly_stats[hour] += 1
                except (ValueError, IndexError):
                    continue
            
            if not hourly_stats:
                return {"peak_hours": [], "total_calls": 0}
            
            # Find peak hours (top 3)
            sorted_hours = sorted(hourly_stats.items(), key=lambda x: x[1], reverse=True)
            peak_hours = [
                {"hour": hour, "calls": calls, "percentage": round((calls / sum(hourly_stats.values())) * 100, 2)}
                for hour, calls in sorted_hours[:3]
            ]
            
            return {
                "peak_hours": peak_hours,
                "total_calls": sum(hourly_stats.values()),
                "hourly_distribution": dict(hourly_stats)
            }
            
        except Exception as e:
            logger.error(f"Error calculating peak hours: {e}")
            return {"peak_hours": [], "total_calls": 0}

    def calculate_comprehensive_peak_hours(
        self,
        call_records: List[Dict]
    ) -> Dict[str, Any]:
        """
        🆕 NEW: Calculate comprehensive peak hours analysis
        - Peak calling hours (all calls)
        - Peak answered hours (answered calls only)
        - Peak missed hours (missed calls only)
        
        Args:
            call_records: List of call records
            
        Returns:
            Comprehensive peak hours analysis
        """
        try:
            # Initialize hourly stats for all three categories
            hourly_total_stats = defaultdict(int)
            hourly_answered_stats = defaultdict(int)
            hourly_missed_stats = defaultdict(int)
            
            total_calls = 0
            total_answered = 0
            total_missed = 0
            
            # Process each call record
            for record in call_records:
                call_time = record.get("time", "")
                call_status = record.get("status", "")
                
                if not call_time:
                    continue
                
                try:
                    # Extract hour from time (HH:MM:SS format)
                    hour = int(call_time.split(":")[0])
                    
                    # Count total calls for this hour
                    hourly_total_stats[hour] += 1
                    total_calls += 1
                    
                    # Count by status
                    if call_status == "answered":
                        hourly_answered_stats[hour] += 1
                        total_answered += 1
                    else:
                        # Treat all non-answered as missed
                        hourly_missed_stats[hour] += 1
                        total_missed += 1
                        
                except (ValueError, IndexError):
                    continue
            
            # Helper function to format peak hours
            def format_peak_hours(hourly_stats: defaultdict, total_count: int, calls_type: str) -> List[Dict]:
                if not hourly_stats or total_count == 0:
                    return []
                
                sorted_hours = sorted(hourly_stats.items(), key=lambda x: x[1], reverse=True)
                
                return [
                    {
                        "hour": hour,
                        "calls": calls,
                        "percentage": round((calls / total_count) * 100, 2),
                        "hour_display": f"{hour:02d}:00-{hour:02d}:59",
                        "calls_type": calls_type
                    }
                    for hour, calls in sorted_hours[:3]
                ]
            
            # Calculate peak hours for each category
            peak_calling_hours = format_peak_hours(hourly_total_stats, total_calls, "total")
            peak_answered_hours = format_peak_hours(hourly_answered_stats, total_answered, "answered")
            peak_missed_hours = format_peak_hours(hourly_missed_stats, total_missed, "missed")
            
            return {
                "success": True,
                "peak_calling_hours": peak_calling_hours,
                "peak_answered_hours": peak_answered_hours,
                "peak_missed_hours": peak_missed_hours,
                "summary": {
                    "total_calls": total_calls,
                    "total_answered": total_answered,
                    "total_missed": total_missed,
                    "answer_rate": round((total_answered / total_calls) * 100, 2) if total_calls > 0 else 0.0,
                    "miss_rate": round((total_missed / total_calls) * 100, 2) if total_calls > 0 else 0.0
                },
                "hourly_distributions": {
                    "total_calls": dict(hourly_total_stats),
                    "answered_calls": dict(hourly_answered_stats),
                    "missed_calls": dict(hourly_missed_stats)
                },
                "analysis_metadata": {
                    "hours_with_calls": len(hourly_total_stats),
                    "hours_with_answered": len(hourly_answered_stats),
                    "hours_with_missed": len(hourly_missed_stats),
                    "most_active_hour": max(hourly_total_stats, key=hourly_total_stats.get) if hourly_total_stats else None,
                    "best_answer_hour": max(hourly_answered_stats, key=hourly_answered_stats.get) if hourly_answered_stats else None,
                    "worst_miss_hour": max(hourly_missed_stats, key=hourly_missed_stats.get) if hourly_missed_stats else None
                }
            }
            
        except Exception as e:
            logger.error(f"Error calculating comprehensive peak hours: {e}")
            return {
                "success": False,
                "error": str(e),
                "peak_calling_hours": [],
                "peak_answered_hours": [],
                "peak_missed_hours": [],
                "summary": {
                    "total_calls": 0,
                    "total_answered": 0,
                    "total_missed": 0,
                    "answer_rate": 0.0,
                    "miss_rate": 0.0
                }
            }
    
    def calculate_efficiency_metrics(
        self,
        user_stats: UserCallStats
    ) -> Dict[str, float]:
        """
        Calculate efficiency metrics for a user
        
        Args:
            user_stats: User call statistics
            
        Returns:
            Dictionary of efficiency metrics
        """
        try:
            metrics = {}
            
            # Call efficiency (answered calls per total calls)
            total_calls = user_stats.daily_calls + user_stats.weekly_calls + user_stats.monthly_calls
            answered_calls = user_stats.daily_answered + user_stats.weekly_answered + user_stats.monthly_answered
            
            metrics["call_efficiency"] = (
                (answered_calls / total_calls) * 100 
                if total_calls > 0 else 0.0
            )
            
            # Time efficiency (average call duration)
            total_duration = user_stats.daily_duration + user_stats.weekly_duration + user_stats.monthly_duration
            metrics["time_efficiency"] = (
                total_duration / answered_calls 
                if answered_calls > 0 else 0.0
            )
            
            # Recording efficiency (recordings per answered calls)
            total_recordings = user_stats.daily_recordings + user_stats.weekly_recordings + user_stats.monthly_recordings
            metrics["recording_efficiency"] = (
                (total_recordings / answered_calls) * 100 
                if answered_calls > 0 else 0.0
            )
            
            # Overall efficiency score (weighted average)
            metrics["overall_efficiency"] = (
                metrics["call_efficiency"] * 0.5 +
                min(metrics["time_efficiency"] / 60, 100) * 0.3 +  # Normalize duration to 0-100 scale
                metrics["recording_efficiency"] * 0.2
            )
            
            # Round all metrics
            for key in metrics:
                metrics[key] = round(metrics[key], 2)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating efficiency metrics: {e}")
            return {
                "call_efficiency": 0.0,
                "time_efficiency": 0.0,
                "recording_efficiency": 0.0,
                "overall_efficiency": 0.0
            }


# Create singleton instance
performance_calculator = PerformanceCalculator()