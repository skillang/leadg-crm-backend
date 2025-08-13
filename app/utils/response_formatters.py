# app/utils/response_formatters.py
from datetime import datetime
from typing import Any, Dict, List, Union, Optional
import logging
from app.utils.timezone_helper import TimezoneHandler

logger = logging.getLogger(__name__)

class ResponseFormatter:
    """
    Response formatter that uses your existing TimezoneHandler.utc_to_ist() function
    to convert UTC dates to IST in API responses.
    
    This class handles:
    - Single objects with date fields
    - Lists of objects
    - Nested objects
    - Automatic date field detection
    """
    
    # Common date field names in your LeadG CRM
    DEFAULT_DATE_FIELDS = {
        'created_at', 'updated_at', 'last_contacted', 
        'due_date', 'completed_at', 'timestamp', 'last_login',
        'sent_at', 'cancelled_at', 'scheduled_time'
    }
    
    @classmethod
    def convert_response_dates(cls, data: Any, custom_date_fields: Optional[List[str]] = None) -> Any:
        """
        Convert UTC dates to IST in response data using your existing utc_to_ist() function
        
        Args:
            data: Response data (dict, list, or any other type)
            custom_date_fields: Additional date fields to convert (optional)
            
        Returns:
            Same data structure with UTC dates converted to IST
        """
        if data is None:
            return None
            
        # Combine default and custom date fields
        date_fields = cls.DEFAULT_DATE_FIELDS.copy()
        if custom_date_fields:
            date_fields.update(custom_date_fields)
            
        try:
            return cls._convert_data_recursive(data, date_fields)
        except Exception as e:
            logger.error(f"Error converting response dates: {e}")
            # Return original data if conversion fails
            return data
    
    @classmethod
    def _convert_data_recursive(cls, data: Any, date_fields: set) -> Any:
        """
        Recursively convert dates in nested data structures
        
        Args:
            data: Data to process
            date_fields: Set of field names that contain dates
            
        Returns:
            Data with converted dates
        """
        if isinstance(data, dict):
            return cls._convert_dict(data, date_fields)
        elif isinstance(data, list):
            return cls._convert_list(data, date_fields)
        else:
            return data
    
    @classmethod
    def _convert_dict(cls, data_dict: Dict, date_fields: set) -> Dict:
        """
        Convert dates in a dictionary object
        
        Args:
            data_dict: Dictionary to process
            date_fields: Set of field names that contain dates
            
        Returns:
            Dictionary with converted dates
        """
        result = {}
        
        for key, value in data_dict.items():
            if key in date_fields and isinstance(value, datetime):
                # Use your existing utc_to_ist() function
                converted_date = TimezoneHandler.utc_to_ist(value)
                result[key] = converted_date
                logger.debug(f"Converted {key}: {value} UTC -> {converted_date} IST")
            elif isinstance(value, (dict, list)):
                # Recursively handle nested objects
                result[key] = cls._convert_data_recursive(value, date_fields)
            else:
                # Keep non-date fields as-is
                result[key] = value
                
        return result
    
    @classmethod
    def _convert_list(cls, data_list: List, date_fields: set) -> List:
        """
        Convert dates in a list of objects
        
        Args:
            data_list: List to process
            date_fields: Set of field names that contain dates
            
        Returns:
            List with converted dates
        """
        return [cls._convert_data_recursive(item, date_fields) for item in data_list]

# ================================
# CONVENIENCE FUNCTIONS
# ================================

def convert_response_dates(data: Any, custom_date_fields: Optional[List[str]] = None) -> Any:
    """
    Quick function to convert response dates using your existing utc_to_ist()
    
    Usage:
        # Single object
        lead_data = convert_response_dates(lead_dict)
        
        # List of objects  
        leads_list = convert_response_dates(leads_list)
        
        # With custom date fields
        data = convert_response_dates(response, ['custom_date', 'another_date'])
    
    Args:
        data: Response data to convert
        custom_date_fields: Additional date fields to convert
        
    Returns:
        Data with UTC dates converted to IST
    """
    return ResponseFormatter.convert_response_dates(data, custom_date_fields)

def convert_lead_response(lead_data: Union[Dict, List[Dict]]) -> Union[Dict, List[Dict]]:
    """
    Convert dates specifically for lead responses
    Includes lead-specific date fields
    
    Args:
        lead_data: Single lead dict or list of lead dicts
        
    Returns:
        Lead data with converted dates
    """
    lead_date_fields = ['last_contacted_at', 'follow_up_date']
    return convert_response_dates(lead_data, lead_date_fields)

def convert_task_response(task_data: Union[Dict, List[Dict]]) -> Union[Dict, List[Dict]]:
    """
    Convert dates specifically for task responses
    Includes task-specific date fields
    
    Args:
        task_data: Single task dict or list of task dicts
        
    Returns:
        Task data with converted dates
    """
    task_date_fields = ['due_date', 'completed_at', 'reminder_date']
    return convert_response_dates(task_data, task_date_fields)

def convert_user_response(user_data: Union[Dict, List[Dict]]) -> Union[Dict, List[Dict]]:
    """
    Convert dates specifically for user responses
    Includes user-specific date fields
    
    Args:
        user_data: Single user dict or list of user dicts
        
    Returns:
        User data with converted dates
    """
    user_date_fields = ['last_login', 'password_changed_at']
    return convert_response_dates(user_data, user_date_fields)

# ================================
# USAGE EXAMPLES
# ================================

"""
Usage Examples:

1. Basic usage with any response data:
   converted_data = convert_response_dates(response_data)

2. With custom date fields:
   converted_data = convert_response_dates(response_data, ['custom_date'])

3. Lead-specific conversion:
   converted_leads = convert_lead_response(leads_data)

4. Task-specific conversion:
   converted_tasks = convert_task_response(tasks_data)

5. In your existing endpoints (before decorator):
   @router.get("/leads/")
   async def get_leads():
       leads = await fetch_leads_from_db()  # Returns UTC dates
       return convert_lead_response(leads)   # Returns IST dates
"""