# app/utils/timezone_helper.py
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class TimezoneHandler:
    """
    Timezone conversion utility - SAME PATTERN as your email implementation
    Handles IST (frontend) to UTC (MongoDB) conversion for consistent storage
    
    Problem Solved:
    - Frontend sends datetime in IST (Indian Standard Time)
    - MongoDB should store all datetimes in UTC for consistency
    - Need reliable conversion between IST ↔ UTC
    """
    
    # IST is UTC + 5:30 (5 hours 30 minutes ahead of UTC)
    IST_OFFSET = timedelta(hours=5, minutes=30)
    
    @classmethod
    def ist_to_utc(cls, ist_datetime: datetime) -> Optional[datetime]:
        """
        Convert IST datetime to UTC for MongoDB storage
        SAME LOGIC as your email service implementation
        
        Args:
            ist_datetime: Datetime in IST timezone from frontend
            
        Returns:
            Datetime in UTC for MongoDB storage
        """
        if not ist_datetime:
            return None
            
        # Convert IST to UTC by subtracting IST offset (5 hours 30 minutes)
        utc_datetime = ist_datetime - cls.IST_OFFSET
        
        logger.info(f"Timezone conversion: IST {ist_datetime.strftime('%Y-%m-%d %H:%M:%S')} → UTC {utc_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        return utc_datetime
    
    @classmethod
    def utc_to_ist(cls, utc_datetime: datetime) -> Optional[datetime]:
        """
        Convert UTC datetime to IST for frontend display
        
        Args:
            utc_datetime: Datetime in UTC from MongoDB
            
        Returns:
            Datetime in IST for frontend display
        """
        if not utc_datetime:
            return None
        
        # Handle timezone-aware datetime objects from MongoDB
        if utc_datetime.tzinfo is not None:
            # Convert to naive UTC datetime first
            utc_datetime = utc_datetime.replace(tzinfo=None)
        
        # Convert UTC to IST by adding IST offset (5 hours 30 minutes)
        ist_datetime = utc_datetime + cls.IST_OFFSET
        
        logger.debug(f"Timezone conversion: UTC {utc_datetime.strftime('%Y-%m-%d %H:%M:%S')} → IST {ist_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        return ist_datetime
    @classmethod
    def validate_future_time_ist(cls, ist_datetime: datetime) -> Tuple[bool, str]:
        """
        Validate that the IST time is in the future
        SAME VALIDATION LOGIC as your email service
        
        Args:
            ist_datetime: Scheduled time in IST from frontend
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not ist_datetime:
            return False, "Scheduled time is required"
        
        # Convert to UTC for accurate comparison with current UTC time
        scheduled_utc = cls.ist_to_utc(ist_datetime)
        now_utc = datetime.utcnow()
        
        if scheduled_utc <= now_utc:
            # Detailed error message showing both timezones (same as your email)
            error_msg = (
                f"Scheduled time must be in the future. "
                f"IST: {ist_datetime.strftime('%Y-%m-%d %H:%M:%S')}, "
                f"UTC: {scheduled_utc.strftime('%Y-%m-%d %H:%M:%S')}, "
                f"Current UTC: {now_utc.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return False, error_msg
        
        return True, ""
    
    @classmethod
    def get_current_ist(cls) -> datetime:
        """
        Get current time in IST
        
        Returns:
            Current datetime in IST
        """
        utc_now = datetime.utcnow()
        return cls.utc_to_ist(utc_now)
    
    @classmethod
    def get_current_utc(cls) -> datetime:
        """
        Get current time in UTC
        
        Returns:
            Current datetime in UTC
        """
        return datetime.utcnow()
    
    @classmethod
    def format_scheduled_time_response(cls, scheduled_utc: datetime) -> Dict[str, Any]:
        """
        Format scheduled time for API response (both IST and UTC)
        Used in bulk job creation responses
        
        Args:
            scheduled_utc: Scheduled time in UTC (from MongoDB)
            
        Returns:
            Dict with both IST and UTC formatted times
        """
        if not scheduled_utc:
            return {
                "scheduled_time_utc": None,
                "scheduled_time_ist": None,
                "scheduled_time_ist_display": None
            }
        
        scheduled_ist = cls.utc_to_ist(scheduled_utc)
        
        return {
            "scheduled_time_utc": scheduled_utc,
            "scheduled_time_ist": scheduled_ist,
            "scheduled_time_ist_display": scheduled_ist.strftime('%Y-%m-%d %H:%M:%S IST')
        }
    
    @classmethod
    def is_time_due(cls, scheduled_utc: datetime) -> bool:
        """
        Check if scheduled time has arrived (for scheduler processing)
        
        Args:
            scheduled_utc: Scheduled time in UTC from MongoDB
            
        Returns:
            True if time is due for processing
        """
        if not scheduled_utc:
            return False
            
        now_utc = datetime.utcnow()
        return scheduled_utc <= now_utc
    
    @classmethod
    def calculate_delay_seconds(cls, scheduled_utc: datetime) -> int:
        """
        Calculate seconds until scheduled time (for background job delay)
        
        Args:
            scheduled_utc: Scheduled time in UTC from MongoDB
            
        Returns:
            Seconds until scheduled time (0 if already due)
        """
        if not scheduled_utc:
            return 0
            
        now_utc = datetime.utcnow()
        if scheduled_utc <= now_utc:
            return 0
            
        delta = scheduled_utc - now_utc
        return int(delta.total_seconds())

# ================================
# CONVENIENCE FUNCTIONS
# ================================

def convert_frontend_time_to_db(ist_datetime: datetime) -> datetime:
    """
    Quick helper function for converting frontend time to database time
    
    Args:
        ist_datetime: Time from frontend (IST)
        
    Returns:
        Time for database storage (UTC)
    """
    return TimezoneHandler.ist_to_utc(ist_datetime)

def convert_db_time_to_frontend(utc_datetime: datetime) -> datetime:
    """
    Quick helper function for converting database time to frontend time
    
    Args:
        utc_datetime: Time from database (UTC)
        
    Returns:
        Time for frontend display (IST)
    """
    return TimezoneHandler.utc_to_ist(utc_datetime)

def validate_scheduled_time(ist_datetime: datetime) -> Tuple[bool, str]:
    """
    Quick helper function for validating scheduled time
    
    Args:
        ist_datetime: Scheduled time from frontend (IST)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    return TimezoneHandler.validate_future_time_ist(ist_datetime)

# ================================
# CONSTANTS FOR REFERENCE
# ================================

class TimezoneConstants:
    """Constants for timezone handling"""
    
    # Timezone info
    IST_TIMEZONE_NAME = "Asia/Kolkata"
    UTC_TIMEZONE_NAME = "UTC"
    IST_OFFSET_HOURS = 5.5
    
    # Common format strings
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
    DATETIME_FORMAT_WITH_TZ = "%Y-%m-%d %H:%M:%S %Z"
    API_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
    
    # Validation constants
    MIN_SCHEDULE_MINUTES_AHEAD = 1  # Minimum 1 minute in future
    MAX_SCHEDULE_DAYS_AHEAD = 30   # Maximum 30 days in future

# ================================
# USAGE EXAMPLES (for documentation)
# ================================

"""
Usage Examples:

1. Converting frontend time to database time:
   frontend_time = datetime(2024, 12, 25, 15, 30)  # 3:30 PM IST from frontend
   db_time = TimezoneHandler.ist_to_utc(frontend_time)  # 10:00 AM UTC for MongoDB

2. Validating scheduled time:
   is_valid, error = TimezoneHandler.validate_future_time_ist(frontend_time)
   if not is_valid:
       raise ValueError(error)

3. Formatting response with both timezones:
   response_data = TimezoneHandler.format_scheduled_time_response(db_time)
   # Returns: {"scheduled_time_utc": ..., "scheduled_time_ist": ..., "scheduled_time_ist_display": "..."}

4. Quick conversion functions:
   db_time = convert_frontend_time_to_db(frontend_time)
   frontend_time = convert_db_time_to_frontend(db_time)
"""