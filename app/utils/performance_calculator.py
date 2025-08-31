# app/utils/performance_calculator.py
# Enhanced Performance Calculator with Chart-Specific Analytics
# Extended to support advanced visualizations and mathematical computations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
import statistics
import math

logger = logging.getLogger(__name__)

class PerformanceCalculator:
    """
    Enhanced performance calculator for call analytics
    Provides mathematical computations for chart generation and trend analysis
    """
    
    def __init__(self):
        pass
    
    def rank_performers(
        self,
        user_stats: List[Dict],
        top_n: Optional[int] = None
    ) -> List[Dict]:
        """
        Simple ranking based on user performance data
        Enhanced with additional ranking metrics
        """
        try:
            if not user_stats:
                return []
            
            # Calculate composite scores for ranking
            for user in user_stats:
                # Composite score: weighted combination of success rate, volume, and efficiency
                success_rate = user.get("success_rate", 0)
                total_calls = user.get("total_calls", 0)
                avg_duration = user.get("avg_call_duration", 0)
                
                # Weighted scoring: 50% success rate, 30% volume, 20% call quality
                volume_score = min(100, (total_calls / 50) * 100)  # Normalize volume to 100
                quality_score = self._calculate_quality_score(avg_duration)
                
                composite_score = (
                    success_rate * 0.5 + 
                    volume_score * 0.3 + 
                    quality_score * 0.2
                )
                
                user["composite_score"] = round(composite_score, 1)
                user["volume_score"] = round(volume_score, 1)
                user["quality_score"] = round(quality_score, 1)
            
            # Sort by composite score, then by success rate
            sorted_performers = sorted(
                user_stats, 
                key=lambda x: (x.get("composite_score", 0), x.get("success_rate", 0)), 
                reverse=True
            )
            
            # Add rank and performance tier
            for i, performer in enumerate(sorted_performers):
                performer["rank"] = i + 1
                performer["performance_tier"] = self._get_performance_tier(i + 1, len(sorted_performers))
            
            return sorted_performers[:top_n] if top_n else sorted_performers
            
        except Exception as e:
            logger.error(f"Error ranking performers: {e}")
            return []
    
    def calculate_trend_analysis(
        self,
        call_records: List[Dict],
        period_days: int = 7
    ) -> Dict[str, Any]:
        """
        Enhanced trend analysis for the specified period
        """
        try:
            # Group by date
            daily_stats = defaultdict(lambda: {
                "total_calls": 0,
                "answered_calls": 0,
                "total_duration": 0,
                "unique_agents": set()
            })
            
            for record in call_records:
                record_date = record.get("date", "")
                if not record_date:
                    continue
                
                stats = daily_stats[record_date]
                stats["total_calls"] += 1
                
                # Track agent activity
                agent = record.get("agent_number", "")
                if agent:
                    stats["unique_agents"].add(agent)
                
                if record.get("status") == "answered":
                    stats["answered_calls"] += 1
                    stats["total_duration"] += record.get("call_duration", 0)
            
            # Convert sets to counts
            for date_stats in daily_stats.values():
                date_stats["unique_agents"] = len(date_stats["unique_agents"])
            
            # Calculate trends
            sorted_dates = sorted(daily_stats.keys())
            if len(sorted_dates) < 2:
                return {
                    "trend": "insufficient_data", 
                    "change_percent": 0.0,
                    "daily_averages": {},
                    "trend_strength": "none"
                }
            
            # Enhanced trend calculation
            mid_point = len(sorted_dates) // 2
            first_half = sorted_dates[:mid_point]
            second_half = sorted_dates[mid_point:]
            
            first_half_calls = sum(daily_stats[date]["total_calls"] for date in first_half)
            second_half_calls = sum(daily_stats[date]["total_calls"] for date in second_half)
            
            first_half_success = sum(daily_stats[date]["answered_calls"] for date in first_half)
            second_half_success = sum(daily_stats[date]["answered_calls"] for date in second_half)
            
            first_half_avg = first_half_calls / len(first_half) if first_half else 0
            second_half_avg = second_half_calls / len(second_half) if second_half else 0
            
            # Success rate trends
            first_half_success_rate = (first_half_success / first_half_calls * 100) if first_half_calls > 0 else 0
            second_half_success_rate = (second_half_success / second_half_calls * 100) if second_half_calls > 0 else 0
            
            # Calculate trend strength and direction
            if first_half_avg == 0:
                change_percent = 0.0
                trend = "stable"
                success_change = 0.0
            else:
                change_percent = ((second_half_avg - first_half_avg) / first_half_avg) * 100
                success_change = second_half_success_rate - first_half_success_rate
                
                if change_percent > 10:
                    trend = "strongly_increasing"
                elif change_percent > 5:
                    trend = "increasing"
                elif change_percent < -10:
                    trend = "strongly_decreasing"
                elif change_percent < -5:
                    trend = "decreasing"
                else:
                    trend = "stable"
            
            # Calculate trend strength
            trend_strength = self._calculate_trend_strength(change_percent)
            
            # Calculate daily averages for the period
            total_calls = sum(stats["total_calls"] for stats in daily_stats.values())
            total_answered = sum(stats["answered_calls"] for stats in daily_stats.values())
            total_agents = len(set().union(*[stats.get("unique_agents", set()) for stats in daily_stats.values()]))
            
            daily_averages = {
                "avg_calls_per_day": round(total_calls / len(sorted_dates), 1),
                "avg_answered_per_day": round(total_answered / len(sorted_dates), 1),
                "avg_success_rate": round((total_answered / total_calls * 100) if total_calls > 0 else 0, 1),
                "active_agents": total_agents,
                "days_analyzed": len(sorted_dates)
            }
            
            return {
                "trend": trend,
                "change_percent": round(change_percent, 2),
                "success_rate_change": round(success_change, 2),
                "first_half_avg": round(first_half_avg, 2),
                "second_half_avg": round(second_half_avg, 2),
                "trend_strength": trend_strength,
                "daily_averages": daily_averages,
                "total_days_analyzed": len(sorted_dates),
                "prediction_confidence": self._calculate_confidence(len(sorted_dates), abs(change_percent))
            }
            
        except Exception as e:
            logger.error(f"Error calculating trend analysis: {e}")
            return {"trend": "error", "change_percent": 0.0, "trend_strength": "none"}
    
    def calculate_peak_hours(
        self,
        call_records: List[Dict]
    ) -> Dict[str, Any]:
        """
        Enhanced peak calling hours calculation
        """
        try:
            hourly_stats = defaultdict(lambda: {
                "calls": 0,
                "answered": 0,
                "duration": 0,
                "agents": set()
            })
            
            for record in call_records:
                call_time = record.get("time", "")
                if not call_time:
                    continue
                
                try:
                    hour = int(call_time.split(":")[0])
                    stats = hourly_stats[hour]
                    stats["calls"] += 1
                    
                    # Track agents per hour
                    agent = record.get("agent_number", "")
                    if agent:
                        stats["agents"].add(agent)
                    
                    if record.get("status") == "answered":
                        stats["answered"] += 1
                        stats["duration"] += record.get("call_duration", 0)
                        
                except (ValueError, IndexError):
                    continue
            
            if not hourly_stats:
                return {"peak_hours": [], "total_calls": 0}
            
            # Calculate enhanced metrics per hour
            enhanced_hours = []
            for hour, stats in hourly_stats.items():
                success_rate = (stats["answered"] / stats["calls"] * 100) if stats["calls"] > 0 else 0
                avg_duration = (stats["duration"] / stats["answered"]) if stats["answered"] > 0 else 0
                agent_count = len(stats["agents"])
                
                # Calculate productivity score
                productivity_score = self._calculate_hourly_productivity(
                    stats["calls"], success_rate, avg_duration, agent_count
                )
                
                enhanced_hours.append({
                    "hour": hour,
                    "display": f"{hour:02d}:00",
                    "calls": stats["calls"],
                    "answered": stats["answered"],
                    "success_rate": round(success_rate, 1),
                    "avg_duration": round(avg_duration, 1),
                    "agent_count": agent_count,
                    "productivity_score": round(productivity_score, 2),
                    "percentage": round((stats["calls"] / sum(h["calls"] for h in hourly_stats.values())) * 100, 2)
                })
            
            # Sort by productivity score for better peak identification
            sorted_hours = sorted(enhanced_hours, key=lambda x: x["productivity_score"], reverse=True)
            
            # Identify peaks (top 3 productive hours with minimum activity)
            peak_hours = [
                hour for hour in sorted_hours[:5] 
                if hour["calls"] >= 5  # Minimum threshold for peak consideration
            ][:3]
            
            return {
                "peak_hours": peak_hours,
                "total_calls": sum(h["calls"] for h in enhanced_hours),
                "hourly_distribution": {h["hour"]: h["calls"] for h in enhanced_hours},
                "productivity_ranking": sorted_hours,
                "analysis_metadata": {
                    "hours_analyzed": len(enhanced_hours),
                    "peak_threshold": 5,
                    "best_productivity_hour": sorted_hours[0]["hour"] if sorted_hours else None
                }
            }
            
        except Exception as e:
            logger.error(f"Error calculating peak hours: {e}")
            return {"peak_hours": [], "total_calls": 0}
    
    def calculate_comprehensive_peak_hours(
        self,
        call_records: List[Dict]
    ) -> Dict[str, Any]:
        """
        Enhanced comprehensive peak hours analysis with advanced metrics
        """
        try:
            hourly_total_stats = defaultdict(int)
            hourly_answered_stats = defaultdict(int)
            hourly_missed_stats = defaultdict(int)
            hourly_duration_stats = defaultdict(list)
            hourly_agent_stats = defaultdict(set)
            
            total_calls = 0
            total_answered = 0
            total_missed = 0
            
            # Process each call record with enhanced tracking
            for record in call_records:
                call_time = record.get("time", "")
                call_status = record.get("status", "")
                
                if not call_time:
                    continue
                
                try:
                    hour = int(call_time.split(":")[0])
                    
                    # Track totals
                    hourly_total_stats[hour] += 1
                    total_calls += 1
                    
                    # Track agents
                    agent = record.get("agent_number", "")
                    if agent:
                        hourly_agent_stats[hour].add(agent)
                    
                    # Track by status with duration
                    if call_status == "answered":
                        hourly_answered_stats[hour] += 1
                        total_answered += 1
                        duration = record.get("call_duration", 0)
                        hourly_duration_stats[hour].append(duration)
                    else:
                        hourly_missed_stats[hour] += 1
                        total_missed += 1
                        
                except (ValueError, IndexError):
                    continue
            
            # Enhanced formatting function
            def format_comprehensive_peak_hours(hourly_stats: defaultdict, total_count: int, calls_type: str) -> List[Dict]:
                if not hourly_stats or total_count == 0:
                    return []
                
                formatted_hours = []
                for hour, calls in hourly_stats.items():
                    # Calculate additional metrics
                    success_rate = (calls / hourly_total_stats[hour] * 100) if hourly_total_stats[hour] > 0 else 0
                    agent_count = len(hourly_agent_stats.get(hour, set()))
                    
                    # Average duration for this hour
                    durations = hourly_duration_stats.get(hour, [])
                    avg_duration = statistics.mean(durations) if durations else 0
                    
                    # Efficiency score
                    efficiency = self._calculate_hourly_efficiency(calls, success_rate, avg_duration, agent_count)
                    
                    formatted_hours.append({
                        "hour": hour,
                        "calls": calls,
                        "percentage": round((calls / total_count) * 100, 2),
                        "hour_display": f"{hour:02d}:00-{hour:02d}:59",
                        "calls_type": calls_type,
                        "success_rate": round(success_rate, 1),
                        "agent_count": agent_count,
                        "avg_duration": round(avg_duration, 1),
                        "efficiency_score": round(efficiency, 2)
                    })
                
                # Sort by efficiency score, then by call count
                return sorted(formatted_hours, key=lambda x: (x["efficiency_score"], x["calls"]), reverse=True)[:3]
            
            # Calculate peak hours for each category
            peak_calling_hours = format_comprehensive_peak_hours(hourly_total_stats, total_calls, "total")
            peak_answered_hours = format_comprehensive_peak_hours(hourly_answered_stats, total_answered, "answered")
            peak_missed_hours = format_comprehensive_peak_hours(hourly_missed_stats, total_missed, "missed")
            
            # Enhanced analysis metadata
            analysis_metadata = {
                "hours_with_calls": len(hourly_total_stats),
                "hours_with_answered": len(hourly_answered_stats),
                "hours_with_missed": len(hourly_missed_stats),
                "most_active_hour": max(hourly_total_stats, key=hourly_total_stats.get) if hourly_total_stats else None,
                "best_answer_hour": max(hourly_answered_stats, key=hourly_answered_stats.get) if hourly_answered_stats else None,
                "worst_miss_hour": max(hourly_missed_stats, key=hourly_missed_stats.get) if hourly_missed_stats else None,
                "total_active_agents": len(set().union(*hourly_agent_stats.values())) if hourly_agent_stats else 0,
                "peak_agent_hour": max(hourly_agent_stats, key=lambda h: len(hourly_agent_stats[h])) if hourly_agent_stats else None
            }
            
            # Generate insights
            insights = self._generate_peak_hours_insights(
                peak_calling_hours, peak_answered_hours, peak_missed_hours, analysis_metadata
            )
            
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
                "analysis_metadata": analysis_metadata,
                "insights": insights
            }
            
        except Exception as e:
            logger.error(f"Error calculating comprehensive peak hours: {e}")
            return {
                "success": False,
                "error": str(e),
                "peak_calling_hours": [],
                "peak_answered_hours": [],
                "peak_missed_hours": [],
                "summary": {"total_calls": 0, "total_answered": 0, "total_missed": 0, "answer_rate": 0, "miss_rate": 0},
                "insights": {}
            }
    
    def calculate_statistical_metrics(
        self,
        values: List[float]
    ) -> Dict[str, float]:
        """
        Calculate comprehensive statistical metrics for datasets
        """
        try:
            if not values:
                return {"mean": 0, "median": 0, "std_dev": 0, "variance": 0, "min": 0, "max": 0}
            
            return {
                "mean": round(statistics.mean(values), 2),
                "median": round(statistics.median(values), 2),
                "std_dev": round(statistics.stdev(values) if len(values) > 1 else 0, 2),
                "variance": round(statistics.variance(values) if len(values) > 1 else 0, 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "range": round(max(values) - min(values), 2),
                "q1": round(statistics.quantiles(values, n=4)[0] if len(values) >= 4 else min(values), 2),
                "q3": round(statistics.quantiles(values, n=4)[2] if len(values) >= 4 else max(values), 2)
            }
            
        except Exception as e:
            logger.error(f"Error calculating statistical metrics: {e}")
            return {"mean": 0, "median": 0, "std_dev": 0, "variance": 0, "min": 0, "max": 0}
    
    def calculate_correlation(
        self,
        x_values: List[float],
        y_values: List[float]
    ) -> float:
        """
        Calculate Pearson correlation coefficient between two datasets
        """
        try:
            if len(x_values) != len(y_values) or len(x_values) < 2:
                return 0.0
            
            n = len(x_values)
            sum_x = sum(x_values)
            sum_y = sum(y_values)
            sum_xy = sum(x * y for x, y in zip(x_values, y_values))
            sum_x2 = sum(x * x for x in x_values)
            sum_y2 = sum(y * y for y in y_values)
            
            numerator = n * sum_xy - sum_x * sum_y
            denominator = math.sqrt((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y))
            
            return round(numerator / denominator if denominator != 0 else 0, 3)
            
        except Exception as e:
            logger.error(f"Error calculating correlation: {e}")
            return 0.0
    
    # Helper methods
    def _calculate_quality_score(self, avg_duration: float) -> float:
        """Calculate call quality score based on duration"""
        if avg_duration == 0:
            return 0
        elif 60 <= avg_duration <= 180:
            return 100  # Optimal range
        elif 30 <= avg_duration < 60:
            return 75   # Short but acceptable
        elif 180 < avg_duration <= 300:
            return 75   # Long but acceptable
        else:
            return 50   # Too short or too long
    
    def _get_performance_tier(self, rank: int, total_users: int) -> str:
        """Determine performance tier based on rank"""
        percentile = rank / total_users
        if percentile <= 0.2:
            return "top_performer"
        elif percentile <= 0.4:
            return "high_performer"
        elif percentile <= 0.6:
            return "average_performer"
        elif percentile <= 0.8:
            return "needs_improvement"
        else:
            return "requires_coaching"
    
    def _calculate_trend_strength(self, change_percent: float) -> str:
        """Calculate trend strength classification"""
        abs_change = abs(change_percent)
        if abs_change > 20:
            return "very_strong"
        elif abs_change > 10:
            return "strong"
        elif abs_change > 5:
            return "moderate"
        elif abs_change > 2:
            return "weak"
        else:
            return "minimal"
    
    def _calculate_confidence(self, data_points: int, change_magnitude: float) -> float:
        """Calculate prediction confidence based on data quality"""
        base_confidence = min(90, data_points * 10)  # More data = higher confidence
        volatility_penalty = min(20, change_magnitude / 2)  # High volatility = lower confidence
        return max(30, base_confidence - volatility_penalty)
    
    def _calculate_hourly_productivity(self, calls: int, success_rate: float, avg_duration: float, agent_count: int) -> float:
        """Calculate productivity score for an hour"""
        if calls == 0:
            return 0
        
        # Normalize components
        volume_score = min(calls / 10, 5)  # Max 5 points for volume
        success_score = (success_rate / 100) * 3  # Max 3 points for success
        duration_score = 2 if 60 <= avg_duration <= 180 else 1  # Quality duration bonus
        efficiency_score = (calls / max(agent_count, 1)) * 0.5  # Calls per agent
        
        return volume_score + success_score + duration_score + efficiency_score
    
    def _calculate_hourly_efficiency(self, calls: int, success_rate: float, avg_duration: float, agent_count: int) -> float:
        """Calculate efficiency score for comprehensive peak hours"""
        if calls == 0:
            return 0
        
        # Base efficiency: success rate weighted by volume
        base_efficiency = (success_rate / 100) * min(calls / 20, 2)  # Max 2 for volume component
        
        # Duration quality bonus
        if 60 <= avg_duration <= 180:
            duration_bonus = 1.0
        elif 30 <= avg_duration < 300:
            duration_bonus = 0.5
        else:
            duration_bonus = 0.2
        
        # Agent utilization factor
        utilization_factor = calls / max(agent_count, 1) / 10  # Normalize to reasonable scale
        
        return base_efficiency + duration_bonus + min(utilization_factor, 1)
    
    def _generate_peak_hours_insights(self, peak_calling: List, peak_answered: List, peak_missed: List, metadata: Dict) -> Dict:
        """Generate actionable insights from peak hours analysis"""
        insights = {}
        
        if peak_calling:
            insights["best_calling_time"] = f"{peak_calling[0]['hour']:02d}:00 - highest activity with {peak_calling[0]['calls']} calls"
        
        if peak_answered:
            insights["best_answer_time"] = f"{peak_answered[0]['hour']:02d}:00 - {peak_answered[0]['success_rate']:.1f}% success rate"
        
        if peak_missed:
            insights["worst_miss_time"] = f"{peak_missed[0]['hour']:02d}:00 - highest missed calls"
        
        # Strategic recommendations
        if peak_calling and peak_answered:
            if peak_calling[0]['hour'] == peak_answered[0]['hour']:
                insights["recommendation"] = "Peak calling time aligns with peak success - maintain current schedule"
            else:
                insights["recommendation"] = f"Consider shifting resources from {peak_calling[0]['hour']:02d}:00 to {peak_answered[0]['hour']:02d}:00 for better results"
        
        insights["agent_utilization"] = f"Peak agent activity at {metadata.get('peak_agent_hour', 'N/A'):02d}:00 with {metadata.get('total_active_agents', 0)} agents"
        
        return insights

# Create singleton instance
performance_calculator = PerformanceCalculator()