# app/decorators/timezone_decorator.py
from functools import wraps
from typing import Any, Callable, List, Optional
import logging
from datetime import datetime
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from app.utils.response_formatters import convert_response_dates

logger = logging.getLogger(__name__)

def convert_dates_to_ist(custom_date_fields: Optional[List[str]] = None):
    """
    Decorator to automatically convert UTC dates to IST in GET endpoint responses
    Uses your existing TimezoneHandler.utc_to_ist() function internally
    
    Args:
        custom_date_fields: Additional date fields to convert (optional)
        
    Usage:
        @router.get("/leads/")
        @convert_dates_to_ist()
        async def get_leads():
            # Your existing code - returns UTC dates
            return leads_data
            # Decorator automatically converts to IST
        
        # With custom date fields:
        @router.get("/leads/")
        @convert_dates_to_ist(['custom_date', 'special_timestamp'])
        async def get_leads():
            return leads_data
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                # print(f"🔍 DECORATOR: Processing {func.__name__}")
                # logger.info(f"🔍 DECORATOR: Processing {func.__name__}")
                
                # Call your original endpoint function
                response = await func(*args, **kwargs)
                
                # print(f"🔍 DECORATOR: Response type: {type(response)}")
                # logger.info(f"🔍 DECORATOR: Response type: {type(response)}")
                
                # Debug: Check sample data before conversion
                if isinstance(response, dict) and 'leads' in response:
                    leads_data = response.get('leads', [])
                    if leads_data:
                        sample_lead = leads_data[0]
                        # print(f"🔍 DECORATOR: Sample lead before conversion:")
                        print(f"   created_at: {sample_lead.get('created_at')} (type: {type(sample_lead.get('created_at'))})")
                        print(f"   last_contacted: {sample_lead.get('last_contacted')} (type: {type(sample_lead.get('last_contacted'))})")
                        # logger.info(f"🔍 DECORATOR: Sample lead - created_at: {sample_lead.get('created_at')} (type: {type(sample_lead.get('created_at'))})")
                
                # Handle different FastAPI response types
                if isinstance(response, JSONResponse):
                    # Extract data from JSONResponse
                    response_data = response.body
                    # print(f"🔍 DECORATOR: Converting JSONResponse data")
                    converted_data = convert_response_dates(response_data, custom_date_fields)
                    return JSONResponse(content=converted_data, status_code=response.status_code)
                
                elif isinstance(response, dict):
                    # Standard dictionary response
                    # print(f"🔍 DECORATOR: Converting dict response")
                    # logger.info(f"🔍 DECORATOR: Converting dict response")
                    
                    converted_data = convert_response_dates(response, custom_date_fields)
                    
                    # Debug: Check sample data after conversion
                    if 'leads' in converted_data:
                        leads_data = converted_data.get('leads', [])
                        if leads_data:
                            sample_lead = leads_data[0]
                            # print(f"🔍 DECORATOR: Sample lead after conversion:")
                            # print(f"   created_at: {sample_lead.get('created_at')} (type: {type(sample_lead.get('created_at'))})")
                            # print(f"   last_contacted: {sample_lead.get('last_contacted')} (type: {type(sample_lead.get('last_contacted'))})")
                            # logger.info(f"🔍 DECORATOR: Sample lead after - created_at: {sample_lead.get('created_at')} (type: {type(sample_lead.get('created_at'))})")
                    
                    # print(f"🔍 DECORATOR: Conversion complete for {func.__name__}")
                    # logger.info(f"🔍 DECORATOR: Conversion complete for {func.__name__}")
                    return converted_data
                
                elif isinstance(response, list):
                    # List response (like get all leads)
                    # print(f"🔍 DECORATOR: Converting list response with {len(response)} items")
                    # logger.info(f"🔍 DECORATOR: Converting list response with {len(response)} items")
                    
                    converted_data = convert_response_dates(response, custom_date_fields)
                    
                    # print(f"🔍 DECORATOR: List conversion complete for {func.__name__}")
                    # logger.info(f"🔍 DECORATOR: List conversion complete for {func.__name__}")
                    return converted_data
                
                elif hasattr(response, 'dict'):
                    # Pydantic model response
                    # print(f"🔍 DECORATOR: Converting Pydantic model response: {type(response)}")
                    # logger.info(f"🔍 DECORATOR: Converting Pydantic model response: {type(response)}")
                    
                    # Convert Pydantic model to dict
                    response_dict = response.dict()
                    
                    # Debug: Check sample data before conversion
                    if 'leads' in response_dict:
                        leads_data = response_dict.get('leads', [])
                        if leads_data:
                            sample_lead = leads_data[0]
                            # print(f"🔍 DECORATOR: Pydantic sample lead before conversion:")
                            # print(f"   created_at: {sample_lead.get('created_at')} (type: {type(sample_lead.get('created_at'))})")
                            # print(f"   last_contacted: {sample_lead.get('last_contacted')} (type: {type(sample_lead.get('last_contacted'))})")
                    
                    # Convert dates
                    converted_dict = convert_response_dates(response_dict, custom_date_fields)
                    
                    # Debug: Check sample data after conversion
                    if 'leads' in converted_dict:
                        leads_data = converted_dict.get('leads', [])
                        if leads_data:
                            sample_lead = leads_data[0]
                            # print(f"🔍 DECORATOR: Pydantic sample lead after conversion:")
                            # print(f"   created_at: {sample_lead.get('created_at')} (type: {type(sample_lead.get('created_at'))})")
                            # print(f"   last_contacted: {sample_lead.get('last_contacted')} (type: {type(sample_lead.get('last_contacted'))})")
                    
                    # print(f"🔍 DECORATOR: Pydantic conversion complete for {func.__name__}")
                    # logger.info(f"🔍 DECORATOR: Pydantic conversion complete for {func.__name__}")
                    
                    # Return as dict (FastAPI will serialize it)
                    return converted_dict
                
                else:
                    # Other response types - return as-is
                    # print(f"🔍 DECORATOR: No conversion needed for response type: {type(response)}")
                    # logger.info(f"🔍 DECORATOR: No conversion needed for response type: {type(response)}")
                    return response
                    
            except HTTPException:
                # Re-raise HTTP exceptions without modification
                # print(f"🔍 DECORATOR: HTTPException in {func.__name__}")
                raise
            except Exception as e:
                print(f"❌ DECORATOR ERROR in {func.__name__}: {e}")
                logger.error(f"❌ DECORATOR ERROR in {func.__name__}: {e}")
                # Return original response if decorator fails
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator

# ================================
# SPECIALIZED DECORATORS
# ================================

def convert_lead_dates():
    """
    Specialized decorator for lead endpoints
    Includes lead-specific date fields
    """
    lead_date_fields = [
        'last_contacted', 'last_contacted_at', 'follow_up_date', 
        'next_contact_date', 'assigned_at', 'last_whatsapp_activity'
    ]
    return convert_dates_to_ist(lead_date_fields)

def convert_task_dates():
    """
    Specialized decorator for task endpoints  
    Includes task-specific date fields
    """
    task_date_fields = ['due_date', 'completed_at', 'reminder_date', 'started_at']
    return convert_dates_to_ist(task_date_fields)

def convert_user_dates():
    """
    Specialized decorator for user/auth endpoints
    Includes user-specific date fields
    """
    user_date_fields = ['last_login', 'password_changed_at', 'account_created']
    return convert_dates_to_ist(user_date_fields)

def convert_activity_dates():
    """
    Specialized decorator for activity endpoints (for future use)
    Includes activity-specific date fields
    """
    activity_date_fields = ['timestamp', 'logged_at', 'action_time']
    return convert_dates_to_ist(activity_date_fields)

# ================================
# NEW DECORATORS FOR TIMEZONE FIX
# ================================

def convert_whatsapp_dates():
    """
    🆕 Specialized decorator for WhatsApp endpoints
    Includes WhatsApp-specific date fields for proper timing display
    """
    whatsapp_date_fields = [
        'timestamp', 'sent_at', 'delivered_at', 'read_at', 
        'webhook_received_at', 'last_message_time', 'last_activity',
        'last_whatsapp_activity', 'message_timestamp'
    ]
    return convert_dates_to_ist(whatsapp_date_fields)

def convert_notification_dates():
    """
    🆕 Specialized decorator for notification endpoints
    Includes notification-specific date fields for proper timing display
    """
    notification_date_fields = [
        'created_at', 'sent_at', 'read_at', 'scheduled_at', 
        'delivered_at', 'expires_at', 'notification_time',
        'timestamp', 'updated_at'
    ]
    return convert_dates_to_ist(notification_date_fields)

# ================================
# USAGE EXAMPLES
# ================================

"""
Usage Examples in your routers:

1. Basic usage (converts common date fields):
   @router.get("/leads/")
   @convert_dates_to_ist()
   async def get_leads():
       return leads_data

2. With custom date fields:
   @router.get("/leads/special")
   @convert_dates_to_ist(['custom_date', 'special_timestamp'])
   async def get_special_leads():
       return special_data

3. Using specialized decorators:
   @router.get("/leads/")
   @convert_lead_dates()
   async def get_leads():
       return leads_data
   
   @router.get("/tasks/")
   @convert_task_dates()
   async def get_tasks():
       return tasks_data

4. NEW - Using WhatsApp and notification decorators:
   @router.get("/notifications/history")
   @convert_notification_dates()
   async def get_notification_history():
       return notification_data
   
   @router.get("/whatsapp/chat/{lead_id}/history")
   @convert_whatsapp_dates()
   async def get_chat_history():
       return chat_data

5. Multiple endpoints with same decorator:
   @router.get("/leads/")
   @convert_lead_dates()
   async def get_all_leads():
       return leads_list
   
   @router.get("/leads/{lead_id}")
   @convert_lead_dates()
   async def get_single_lead(lead_id: str):
       return single_lead_dict

Note: 
- Your endpoint code stays exactly the same
- Just add the decorator line above your endpoint function
- Uses your existing TimezoneHandler.utc_to_ist() function
- Handles errors gracefully - returns original data if conversion fails
"""