# app/services/analytics_service.py
# Advanced Analytics Service for Call Dashboard Visualizations
# Generates chart-ready data for comprehensive performance analysis

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
import statistics
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ChartThresholds:
    """Configuration thresholds for chart calculations"""
    target_success_rate: float = 60.0
    volume_threshold: int = 30
    efficiency_threshold: float = 5.0
    quality_duration_threshold: int = 60  # seconds
    peak_hour_minimum_calls: int = 5

class AnalyticsService:
    """
    Advanced analytics service for generating chart-ready data
    Processes call records into visualization-friendly formats
    """
    
    def __init__(self, thresholds: Optional[ChartThresholds] = None):
        self.thresholds = thresholds or ChartThresholds()
    
    def calculate_performance_gauge(
        self, 
        current_success_rate: float,
        previous_period_rate: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Generate data for success rate gauge chart
        
        Args:
            current_success_rate: Current period success rate
            previous_period_rate: Previous period rate for comparison
            
        Returns:
            Gauge chart data with status, color zones, and targets
        """
        try:
            target_rate = self.thresholds.target_success_rate
            
            # Determine status and color zone
            if current_success_rate >= target_rate:
                status = "above_target"
                color_zone = "green"
            elif current_success_rate >= (target_rate * 0.8):
                status = "on_target"
                color_zone = "yellow"
            else:
                status = "below_target"
                color_zone = "red"
            
            return {
                "current_rate": round(current_success_rate, 1),
                "target_rate": target_rate,
                "status": status,
                "color_zone": color_zone,
                "previous_period": round(previous_period_rate, 1) if previous_period_rate else None,
                "improvement": round(current_success_rate - previous_period_rate, 1) if previous_period_rate else None,
                "progress_to_target": min(100, round((current_success_rate / target_rate) * 100, 1))
            }
            
        except Exception as e:
            logger.error(f"Error calculating performance gauge: {e}")
            return {
                "current_rate": current_success_rate,
                "target_rate": self.thresholds.target_success_rate,
                "status": "unknown",
                "color_zone": "gray",
                "previous_period": None,
                "improvement": None,
                "progress_to_target": 0
            }
    
    def generate_scatter_plot_data(
        self, 
        user_stats: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate call volume vs success rate scatter plot data
        
        Args:
            user_stats: List of user performance statistics
            
        Returns:
            Scatter plot data with efficiency scores
        """
        try:
            scatter_data = []
            
            for user in user_stats:
                # Calculate efficiency score (composite metric)
                efficiency_score = self._calculate_efficiency_score(
                    success_rate=user.get("success_rate", 0),
                    avg_duration=user.get("avg_call_duration", 0),
                    total_calls=user.get("total_calls", 0)
                )
                
                scatter_data.append({
                    "user_id": user.get("user_id"),
                    "user_name": user.get("user_name"),
                    "total_calls": user.get("total_calls", 0),
                    "success_rate": round(user.get("success_rate", 0), 1),
                    "avg_duration": round(user.get("avg_call_duration", 0), 1),
                    "efficiency_score": round(efficiency_score, 1),
                    "recordings_count": user.get("recordings_count", 0),
                    "bubble_size": min(max(user.get("total_calls", 0) / 2, 5), 25)  # For bubble chart variation
                })
            
            return sorted(scatter_data, key=lambda x: x["efficiency_score"], reverse=True)
            
        except Exception as e:
            logger.error(f"Error generating scatter plot data: {e}")
            return []
    
    def calculate_temporal_trends(
        self, 
        call_records: List[Dict[str, Any]],
        date_from: str,
        date_to: str
    ) -> Dict[str, Any]:
        """
        Calculate daily and hourly trends for line charts
        
        Args:
            call_records: Raw call records
            date_from: Start date string
            date_to: End date string
            
        Returns:
            Temporal trend data for charts
        """
        try:
            # Group records by date and hour
            daily_stats = defaultdict(lambda: {
                "total_calls": 0, "answered_calls": 0, "total_duration": 0, "active_agents": set()
            })
            
            hourly_stats = defaultdict(lambda: {
                "calls": 0, "answered": 0, "total_duration": 0
            })
            
            for record in call_records:
                record_date = record.get("date", "")
                record_time = record.get("time", "")
                
                if not record_date or not record_time:
                    continue
                
                # Daily aggregation
                daily_stats[record_date]["total_calls"] += 1
                if record.get("status") == "answered":
                    daily_stats[record_date]["answered_calls"] += 1
                    daily_stats[record_date]["total_duration"] += record.get("call_duration", 0)
                
                # Track active agents per day
                agent_number = record.get("agent_number", "")
                if agent_number:
                    daily_stats[record_date]["active_agents"].add(agent_number)
                
                # Hourly aggregation
                try:
                    hour = int(record_time.split(":")[0])
                    hourly_stats[hour]["calls"] += 1
                    if record.get("status") == "answered":
                        hourly_stats[hour]["answered"] += 1
                        hourly_stats[hour]["total_duration"] += record.get("call_duration", 0)
                except (ValueError, IndexError):
                    continue
            
            # Format daily series
            daily_series = []
            for date in sorted(daily_stats.keys()):
                stats = daily_stats[date]
                success_rate = (stats["answered_calls"] / stats["total_calls"] * 100) if stats["total_calls"] > 0 else 0
                avg_duration = (stats["total_duration"] / stats["answered_calls"]) if stats["answered_calls"] > 0 else 0
                
                daily_series.append({
                    "date": date,
                    "total_calls": stats["total_calls"],
                    "answered_calls": stats["answered_calls"],
                    "success_rate": round(success_rate, 1),
                    "avg_duration": round(avg_duration, 1),
                    "active_agents": len(stats["active_agents"])
                })
            
            # Format hourly series
            hourly_series = []
            for hour in sorted(hourly_stats.keys()):
                stats = hourly_stats[hour]
                success_rate = (stats["answered"] / stats["calls"] * 100) if stats["calls"] > 0 else 0
                avg_duration = (stats["total_duration"] / stats["answered"]) if stats["answered"] > 0 else 0
                
                hourly_series.append({
                    "hour": hour,
                    "display": f"{hour:02d}:00",
                    "calls": stats["calls"],
                    "answered": stats["answered"],
                    "success_rate": round(success_rate, 1),
                    "avg_duration": round(avg_duration, 1)
                })
            
            return {
                "daily_series": daily_series,
                "hourly_series": hourly_series,
                "date_range": f"{date_from} to {date_to}",
                "total_days": len(daily_series),
                "active_hours": len(hourly_series)
            }
            
        except Exception as e:
            logger.error(f"Error calculating temporal trends: {e}")
            return {"daily_series": [], "hourly_series": [], "date_range": "", "total_days": 0, "active_hours": 0}
    
    def generate_hourly_heatmap(
        self, 
        call_records: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate hour-by-hour activity heatmap data
        
        Args:
            call_records: Raw call records
            
        Returns:
            Heatmap data with intensity calculations
        """
        try:
            hourly_data = defaultdict(lambda: {"calls": 0, "answered": 0})
            
            # Process records by hour
            for record in call_records:
                record_time = record.get("time", "")
                if not record_time:
                    continue
                
                try:
                    hour = int(record_time.split(":")[0])
                    hourly_data[hour]["calls"] += 1
                    if record.get("status") == "answered":
                        hourly_data[hour]["answered"] += 1
                except (ValueError, IndexError):
                    continue
            
            # Calculate max calls for normalization
            max_calls = max([data["calls"] for data in hourly_data.values()], default=1)
            
            # Format heatmap data
            heatmap_data = []
            best_hour = {"hour": 0, "success_rate": 0}
            
            for hour in range(24):  # Include all 24 hours
                data = hourly_data.get(hour, {"calls": 0, "answered": 0})
                success_rate = (data["answered"] / data["calls"] * 100) if data["calls"] > 0 else 0
                intensity = data["calls"] / max_calls if max_calls > 0 else 0
                
                # Track best performing hour
                if success_rate > best_hour["success_rate"] and data["calls"] >= self.thresholds.peak_hour_minimum_calls:
                    best_hour = {"hour": hour, "success_rate": success_rate}
                
                heatmap_data.append({
                    "hour": hour,
                    "display": f"{hour:02d}:00",
                    "call_count": data["calls"],
                    "answered_count": data["answered"],
                    "success_rate": round(success_rate, 1),
                    "intensity": round(intensity, 2),
                    "is_active": data["calls"] > 0
                })
            
            return {
                "data": heatmap_data,
                "max_calls": max_calls,
                "best_hour": best_hour,
                "total_active_hours": len([d for d in heatmap_data if d["is_active"]])
            }
            
        except Exception as e:
            logger.error(f"Error generating hourly heatmap: {e}")
            return {"data": [], "max_calls": 0, "best_hour": {"hour": 0, "success_rate": 0}, "total_active_hours": 0}
    
    def calculate_duration_distribution(
        self, 
        call_records: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate call duration distribution for histogram
        
        Args:
            call_records: Raw call records (answered calls only)
            
        Returns:
            Duration distribution data
        """
        try:
            # Filter answered calls only
            answered_calls = [
                record for record in call_records 
                if record.get("status") == "answered" and record.get("call_duration", 0) > 0
            ]
            
            if not answered_calls:
                return {
                    "buckets": [],
                    "avg_duration": 0,
                    "quality_threshold": self.thresholds.quality_duration_threshold,
                    "total_analyzed": 0
                }
            
            durations = [record.get("call_duration", 0) for record in answered_calls]
            
            # Define duration buckets
            buckets = [
                {"range": "0-30s", "min": 0, "max": 30},
                {"range": "30-60s", "min": 30, "max": 60},
                {"range": "60-120s", "min": 60, "max": 120},
                {"range": "120-300s", "min": 120, "max": 300},
                {"range": "300s+", "min": 300, "max": float('inf')}
            ]
            
            # Count durations in each bucket
            total_calls = len(durations)
            bucket_data = []
            
            for bucket in buckets:
                count = sum(1 for d in durations if bucket["min"] <= d < bucket["max"])
                percentage = (count / total_calls * 100) if total_calls > 0 else 0
                
                bucket_data.append({
                    "range": bucket["range"],
                    "count": count,
                    "percentage": round(percentage, 1),
                    "is_quality": bucket["min"] >= self.thresholds.quality_duration_threshold
                })
            
            # Calculate statistics
            avg_duration = statistics.mean(durations)
            quality_calls = sum(1 for d in durations if d >= self.thresholds.quality_duration_threshold)
            quality_percentage = (quality_calls / total_calls * 100) if total_calls > 0 else 0
            
            return {
                "buckets": bucket_data,
                "avg_duration": round(avg_duration, 1),
                "quality_threshold": self.thresholds.quality_duration_threshold,
                "quality_calls": quality_calls,
                "quality_percentage": round(quality_percentage, 1),
                "total_analyzed": total_calls,
                "median_duration": round(statistics.median(durations), 1)
            }
            
        except Exception as e:
            logger.error(f"Error calculating duration distribution: {e}")
            return {
                "buckets": [],
                "avg_duration": 0,
                "quality_threshold": self.thresholds.quality_duration_threshold,
                "quality_calls": 0,
                "quality_percentage": 0,
                "total_analyzed": 0,
                "median_duration": 0
            }
    
    def analyze_peak_hours(
        self, 
        call_records: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze peak calling hours for column chart
        
        Args:
            call_records: Raw call records
            
        Returns:
            Peak hours analysis data
        """
        try:
            hourly_stats = defaultdict(lambda: {"total": 0, "answered": 0})
            
            # Process records by hour
            for record in call_records:
                record_time = record.get("time", "")
                if not record_time:
                    continue
                
                try:
                    hour = int(record_time.split(":")[0])
                    hourly_stats[hour]["total"] += 1
                    if record.get("status") == "answered":
                        hourly_stats[hour]["answered"] += 1
                except (ValueError, IndexError):
                    continue
            
            # Calculate hourly performance and ranking
            hourly_data = []
            for hour in range(24):
                stats = hourly_stats.get(hour, {"total": 0, "answered": 0})
                success_rate = (stats["answered"] / stats["total"] * 100) if stats["total"] > 0 else 0
                
                hourly_data.append({
                    "hour": hour,
                    "display": f"{hour:02d}:00",
                    "total_calls": stats["total"],
                    "answered_calls": stats["answered"],
                    "success_rate": round(success_rate, 1),
                    "is_active": stats["total"] >= self.thresholds.peak_hour_minimum_calls
                })
            
            # Filter active hours and rank them
            active_hours = [h for h in hourly_data if h["is_active"]]
            active_hours.sort(key=lambda x: (x["success_rate"], x["total_calls"]), reverse=True)
            
            # Assign ranks and identify peaks
            for i, hour_data in enumerate(active_hours):
                hour_data["rank"] = i + 1
                hour_data["is_peak"] = i < 3  # Top 3 hours are peaks
            
            # Identify best and worst hours
            best_hours = [h["hour"] for h in active_hours[:3]]
            worst_hours = [h["hour"] for h in active_hours[-3:]] if len(active_hours) >= 3 else []
            
            # Generate recommendations
            if best_hours:
                recommended_window = f"{min(best_hours):02d}:00-{max(best_hours)+1:02d}:00"
            else:
                recommended_window = "No clear pattern"
            
            return {
                "hourly_data": hourly_data,
                "active_hours": active_hours,
                "peak_summary": {
                    "best_hours": best_hours,
                    "worst_hours": worst_hours,
                    "recommended_calling_window": recommended_window,
                    "peak_success_rate": active_hours[0]["success_rate"] if active_hours else 0
                },
                "analysis_metadata": {
                    "total_active_hours": len(active_hours),
                    "peak_threshold": self.thresholds.peak_hour_minimum_calls
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing peak hours: {e}")
            return {
                "hourly_data": [],
                "active_hours": [],
                "peak_summary": {
                    "best_hours": [],
                    "worst_hours": [],
                    "recommended_calling_window": "Analysis failed"
                },
                "analysis_metadata": {"total_active_hours": 0}
            }
    
    def forecast_trends(
        self, 
        daily_series: List[Dict[str, Any]],
        forecast_days: int = 3
    ) -> Dict[str, Any]:
        """
        Generate performance trend forecast
        
        Args:
            daily_series: Historical daily performance data
            forecast_days: Number of days to forecast
            
        Returns:
            Trend forecast data
        """
        try:
            if len(daily_series) < 3:
                return {
                    "historical": daily_series,
                    "forecast": [],
                    "trend_direction": "insufficient_data",
                    "projected_monthly_rate": 0,
                    "confidence": 0
                }
            
            # Extract success rates for trend calculation
            success_rates = [day["success_rate"] for day in daily_series]
            
            # Simple linear regression for trend
            n = len(success_rates)
            x_values = list(range(n))
            
            # Calculate slope and intercept
            x_mean = statistics.mean(x_values)
            y_mean = statistics.mean(success_rates)
            
            numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, success_rates))
            denominator = sum((x - x_mean) ** 2 for x in x_values)
            
            if denominator == 0:
                slope = 0
            else:
                slope = numerator / denominator
            
            intercept = y_mean - slope * x_mean
            
            # Generate forecast
            forecast = []
            last_date = datetime.strptime(daily_series[-1]["date"], "%Y-%m-%d")
            
            for i in range(1, forecast_days + 1):
                forecast_date = last_date + timedelta(days=i)
                predicted_rate = slope * (n + i - 1) + intercept
                predicted_rate = max(0, min(100, predicted_rate))  # Clamp to 0-100%
                
                # Calculate confidence (decreases with distance)
                confidence = max(50, 95 - (i * 10))
                
                forecast.append({
                    "date": forecast_date.strftime("%Y-%m-%d"),
                    "predicted_rate": round(predicted_rate, 1),
                    "confidence": confidence
                })
            
            # Determine trend direction
            if slope > 1:
                trend_direction = "improving"
            elif slope < -1:
                trend_direction = "declining"
            else:
                trend_direction = "stable"
            
            # Project monthly rate (30 days out)
            projected_monthly_rate = slope * (n + 30 - 1) + intercept
            projected_monthly_rate = max(0, min(100, projected_monthly_rate))
            
            return {
                "historical": daily_series,
                "forecast": forecast,
                "trend_direction": trend_direction,
                "projected_monthly_rate": round(projected_monthly_rate, 1),
                "confidence": round(max(50, 95 - (forecast_days * 5)), 0),
                "slope": round(slope, 3)
            }
            
        except Exception as e:
            logger.error(f"Error forecasting trends: {e}")
            return {
                "historical": daily_series,
                "forecast": [],
                "trend_direction": "error",
                "projected_monthly_rate": 0,
                "confidence": 0
            }
    
    def calculate_efficiency_matrix(
        self, 
        user_stats: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate efficiency matrix for quadrant analysis
        
        Args:
            user_stats: List of user performance statistics
            
        Returns:
            Efficiency matrix data for quadrant chart
        """
        try:
            if not user_stats:
                return {
                    "quadrants": [],
                    "thresholds": {"volume": self.thresholds.volume_threshold, "efficiency": self.thresholds.efficiency_threshold}
                }
            
            # Calculate thresholds if not set (use medians)
            call_volumes = [user.get("total_calls", 0) for user in user_stats]
            efficiency_scores = [
                self._calculate_efficiency_score(
                    user.get("success_rate", 0),
                    user.get("avg_call_duration", 0),
                    user.get("total_calls", 0)
                ) for user in user_stats
            ]
            
            volume_threshold = self.thresholds.volume_threshold
            efficiency_threshold = self.thresholds.efficiency_threshold
            
            # If thresholds are default, use data-driven thresholds
            if volume_threshold == 30 and call_volumes:
                volume_threshold = statistics.median(call_volumes)
            if efficiency_threshold == 5.0 and efficiency_scores:
                efficiency_threshold = statistics.median(efficiency_scores)
            
            # Categorize users into quadrants
            quadrants = {
                "high_volume_high_efficiency": {"users": [], "color": "green"},
                "high_volume_low_efficiency": {"users": [], "color": "orange"},
                "low_volume_high_efficiency": {"users": [], "color": "blue"},
                "low_volume_low_efficiency": {"users": [], "color": "red"}
            }
            
            for user in user_stats:
                volume = user.get("total_calls", 0)
                efficiency = self._calculate_efficiency_score(
                    user.get("success_rate", 0),
                    user.get("avg_call_duration", 0),
                    user.get("total_calls", 0)
                )
                
                user_data = {
                    "user_id": user.get("user_id"),
                    "user_name": user.get("user_name"),
                    "calls": volume,
                    "efficiency": round(efficiency, 1),
                    "success_rate": user.get("success_rate", 0)
                }
                
                # Categorize into quadrant
                if volume >= volume_threshold and efficiency >= efficiency_threshold:
                    quadrants["high_volume_high_efficiency"]["users"].append(user_data)
                elif volume >= volume_threshold and efficiency < efficiency_threshold:
                    quadrants["high_volume_low_efficiency"]["users"].append(user_data)
                elif volume < volume_threshold and efficiency >= efficiency_threshold:
                    quadrants["low_volume_high_efficiency"]["users"].append(user_data)
                else:
                    quadrants["low_volume_low_efficiency"]["users"].append(user_data)
            
            # Convert to list format with categories
            quadrant_list = []
            for category, data in quadrants.items():
                if data["users"]:  # Only include non-empty quadrants
                    quadrant_list.append({
                        "category": category,
                        "users": data["users"],
                        "color": data["color"],
                        "count": len(data["users"])
                    })
            
            return {
                "quadrants": quadrant_list,
                "thresholds": {
                    "volume": round(volume_threshold, 1),
                    "efficiency": round(efficiency_threshold, 1)
                },
                "summary": {
                    "total_users": len(user_stats),
                    "high_performers": len(quadrants["high_volume_high_efficiency"]["users"]),
                    "need_coaching": len(quadrants["low_volume_low_efficiency"]["users"])
                }
            }
            
        except Exception as e:
            logger.error(f"Error calculating efficiency matrix: {e}")
            return {
                "quadrants": [],
                "thresholds": {"volume": self.thresholds.volume_threshold, "efficiency": self.thresholds.efficiency_threshold},
                "summary": {"total_users": 0, "high_performers": 0, "need_coaching": 0}
            }
    
    def _calculate_efficiency_score(
        self, 
        success_rate: float, 
        avg_duration: float, 
        total_calls: int
    ) -> float:
        """
        Calculate composite efficiency score
        
        Args:
            success_rate: Call success rate percentage
            avg_duration: Average call duration in seconds
            total_calls: Total number of calls
            
        Returns:
            Efficiency score (0-10 scale)
        """
        try:
            if total_calls == 0:
                return 0.0
            
            # Normalize success rate (0-100 to 0-4)
            success_component = (success_rate / 100) * 4
            
            # Duration quality component (optimal around 60-180 seconds)
            if avg_duration == 0:
                duration_component = 0
            elif 60 <= avg_duration <= 180:
                duration_component = 3  # Optimal range
            elif 30 <= avg_duration < 60:
                duration_component = 2  # Acceptable but short
            elif 180 < avg_duration <= 300:
                duration_component = 2  # Acceptable but long
            else:
                duration_component = 1  # Too short or too long
            
            # Volume consistency component (normalized to 0-3)
            volume_component = min(3, total_calls / 20)  # 20 calls = max component score
            
            # Weighted efficiency score
            efficiency_score = (success_component * 0.5) + (duration_component * 0.3) + (volume_component * 0.2)
            
            return min(10.0, efficiency_score)
            
        except Exception as e:
            logger.error(f"Error calculating efficiency score: {e}")
            return 0.0

# Create singleton instance
analytics_service = AnalyticsService()