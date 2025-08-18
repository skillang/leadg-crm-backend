# app/services/tata_call_service.py
# CLEANED VERSION: Tata Tele Call Service - NO CALL LOGGING
# Handles click-to-call and support calls without local database storage
# Direct TATA API calls only - no logging, no call tracking

import httpx
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List
from bson import ObjectId
from ..config.database import get_database
from ..config.settings import get_settings
from ..models.tata_integration import TataIntegrationLog
from .tata_auth_service import tata_auth_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TataCallService:
    """
    CLEANED: Tata Tele Call Service - NO CALL LOGGING
    - Proper user sync validation
    - Exact Tata API format compliance
    - Auto lead phone extraction
    - Enhanced error handling and logging
    - NO DATABASE STORAGE OF CALLS
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.db = None
        self.auth_service = tata_auth_service
        self.base_url = self.settings.tata_api_base_url
        self.timeout = self.settings.tata_api_timeout or 30
        
        # API endpoints
        self.endpoints = {
            "click_to_call": f"{self.base_url}/v1/click_to_call",
            "support_call": f"{self.base_url}/v1/click_to_call_support",
            "users": f"{self.base_url}/v1/users",
            "user_detail": f"{self.base_url}/v1/user",
            "my_numbers": f"{self.base_url}/v1/my_number"
        }
        
        self.default_timeout = getattr(self.settings, 'default_call_timeout', 300)
        self.max_concurrent_calls = getattr(self.settings, 'max_concurrent_calls', 50)

    def _get_db(self):
        """Lazy database initialization - only for lead/user lookups"""
        if self.db is None:
            try:
                self.db = get_database()
            except RuntimeError:
                return None
        return self.db

    def _format_phone_for_tata(self, phone: str) -> str:
        """
        Format phone number for Tata API (Indian format)
        Based on actual working patterns from Tata API
        """
        if not phone:
            return phone
            
        # Remove all non-digits
        cleaned = re.sub(r'[^\d]', '', phone)
        
        # Handle Indian numbers (most common case)
        if len(cleaned) == 10 and cleaned.startswith(('6', '7', '8', '9')):
            # Indian 10-digit mobile: 9087924334 → +919087924334
            formatted = f"+91{cleaned}"
            logger.info(f"Formatted Indian number: {phone} → {formatted}")
            return formatted
        elif len(cleaned) == 12 and cleaned.startswith('91'):
            # Already has country code: 919087924334 → +919087924334
            return f"+{cleaned}"
        elif phone.startswith('+'):
            # Already international format
            return phone
        else:
            # Return as-is for other formats
            logger.warning(f"Using phone as-is (unknown format): {phone}")
            return phone

    async def _validate_user_tata_sync(self, user_id: str, user_email: str) -> Tuple[bool, Dict]:
        """
        Validate that user is properly synced with Tata system
        This is the key fix for the 422 errors - ensuring correct agent_id
        """
        try:
            logger.info(f"🔍 Validating Tata sync for user: {user_email}")
            
            db = self._get_db()
            if db is None:
                return False, {"error": "Database unavailable", "message": "Cannot access database"}
            
            # 1. Get user from users collection (for basic validation)
            user = await db.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return False, {"error": "User not found", "message": f"User {user_email} not found"}
            
            # 2. Get Tata mapping from tata_user_mappings collection (this has the correct data)
            tata_mapping = await db.tata_user_mappings.find_one({"crm_user_id": user_id})
            if not tata_mapping:
                return False, {
                    "error": "No Tata mapping", 
                    "message": f"No Tata mapping found for user {user_email}. Please sync with Tata system."
                }
            
            # 3. Get current Tata sync data from the mapping
            tata_agent_id = tata_mapping.get("tata_agent_id")  # Old field for logging
            tata_phone = tata_mapping.get("tata_phone")        # This is the actual agent number
            tata_caller_id = tata_mapping.get("tata_caller_id") or tata_mapping.get("tata_did_number")  # Extension/DID
            sync_status = tata_mapping.get("sync_status")
            calling_enabled = tata_mapping.get("can_make_calls", False)
            
            logger.info(f"📊 Current sync data - Agent ID: {tata_agent_id}, Agent Phone: {tata_phone}, Caller ID: {tata_caller_id}, Status: {sync_status}, Enabled: {calling_enabled}")
            
            # 4. Validate sync quality - use tata_phone as the actual agent number
            if (tata_phone and 
                tata_caller_id and 
                sync_status in ["synced", "already_synced"] and 
                calling_enabled):
                
                # Clean tata_phone to get agent number (remove +91 prefix)
                agent_number = tata_phone
                if agent_number.startswith('+91'):
                    agent_number = agent_number[3:]  # Remove +91 prefix
                elif agent_number.startswith('91'):
                    agent_number = agent_number[2:]  # Remove 91 prefix
                
                logger.info(f"✅ User {user_email} has valid Tata sync - Agent: {agent_number} (from {tata_phone})")
                return True, {
                    "tata_agent_id": agent_number,    # Clean agent number for Tata API
                    "tata_extension": tata_caller_id, # Use caller_id as extension
                    "sync_status": sync_status,
                    "can_make_calls": True
                }
            
            # 5. If sync is invalid/missing, return detailed error
            issues = []
            if not tata_phone:
                issues.append("No Tata phone/agent number")
            if not tata_caller_id:
                issues.append("No Tata caller ID/extension")
            if sync_status not in ["synced", "already_synced"]:
                issues.append(f"Invalid sync status: {sync_status}")
            if not calling_enabled:
                issues.append("Calling not enabled")
            
            logger.warning(f"❌ Invalid sync for {user_email}: {', '.join(issues)}")
            
            return False, {
                "error": "User sync invalid",
                "message": f"User not properly synced with Tata: {', '.join(issues)}",
                "details": {
                    "tata_agent_id": tata_agent_id,
                    "tata_phone": tata_phone,
                    "tata_caller_id": tata_caller_id,
                    "sync_status": sync_status,
                    "calling_enabled": calling_enabled,
                    "issues": issues
                },
                "solution": "Please log out and log back in to re-sync with Tata system"
            }
            
        except Exception as e:
            logger.error(f"Error validating Tata sync: {str(e)}")
            return False, {"error": "Sync validation failed", "message": str(e)}

    async def _get_lead_phone_number(self, lead_id: str) -> Optional[str]:
        """
        Auto-fetch lead's phone number with multiple strategies
        """
        try:
            db = self._get_db()
            if db is None:
                logger.error("Database not available")
                return None
                
            # Strategy 1: Direct lead_id match
            lead = await db.leads.find_one({"lead_id": lead_id})
            
            # Strategy 2: Try _id field if first strategy fails
            if not lead:
                try:
                    if ObjectId.is_valid(lead_id):
                        lead = await db.leads.find_one({"_id": ObjectId(lead_id)})
                        logger.info(f"Found lead by _id: {lead_id}")
                except:
                    pass
            
            # Strategy 3: Case-insensitive search on lead_id
            if not lead:
                lead = await db.leads.find_one({
                    "lead_id": {"$regex": f"^{lead_id}$", "$options": "i"}
                })
                if lead:
                    logger.info(f"Found lead by case-insensitive search: {lead_id}")
            
            # Strategy 4: Try other potential ID fields
            if not lead:
                for field in ['id', 'leadId', 'lead_identifier']:
                    lead = await db.leads.find_one({field: lead_id})
                    if lead:
                        logger.info(f"Found lead by {field}: {lead_id}")
                        break
            
            if not lead:
                logger.warning(f"❌ Lead not found with any strategy: {lead_id}")
                return None
            
            # Extract phone number (try multiple field names)
            phone = (lead.get("contact_number") or 
                    lead.get("phone_number") or 
                    lead.get("phone") or
                    lead.get("mobile"))
            
            if not phone:
                logger.warning(f"❌ No phone number found for lead: {lead_id}")
                return None
            
            # Format phone for Tata API
            formatted_phone = self._format_phone_for_tata(str(phone))
            logger.info(f"✅ Found phone for lead {lead_id}: {phone} → {formatted_phone}")
            return formatted_phone
            
        except Exception as e:
            logger.error(f"Error getting lead phone for {lead_id}: {str(e)}")
            return None

    async def _make_authenticated_request(
        self, 
        method: str, 
        url: str, 
        data: Optional[Dict] = None,
        content_type: str = "application/json",
        user_id: str = "system"
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Make authenticated request to Tata API with detailed logging
        """
        try:
            # Get valid token
            token = await self.auth_service.get_valid_token()
            if not token:
                logger.error("❌ No valid token available")
                return False, {"error": "Authentication failed", "message": "No valid token available"}
            
            # Prepare headers exactly as per Tata API docs
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": content_type,
                "Accept": "application/json"
            }
            
            logger.info(f"🔗 Making {method} request to: {url}")
            logger.info(f"📋 Request headers: {headers}")
            logger.info(f"📦 Request data: {data}")
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers)
                elif method.upper() == "POST":
                    if content_type == "application/x-www-form-urlencoded":
                        response = await client.post(url, headers=headers, data=data)
                    else:
                        response = await client.post(url, headers=headers, json=data)
                elif method.upper() == "PUT":
                    response = await client.put(url, headers=headers, json=data)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, headers=headers)
                else:
                    return False, {"error": f"Unsupported HTTP method: {method}"}
                
                logger.info(f"📡 Response status: {response.status_code}")
                
                if response.status_code == 200:
                    response_data = response.json()
                    logger.info(f"✅ Tata API success response: {response_data}")
                    return True, response_data
                else:
                    # Enhanced error logging for debugging
                    try:
                        error_response = response.json()
                    except:
                        error_response = response.text
                    
                    logger.error(f"❌ Tata API error {response.status_code}: {error_response}")
                    
                    # Special handling for 422 errors (our main issue)
                    if response.status_code == 422:
                        logger.error(f"🔍 422 Debug - Request URL: {url}")
                        logger.error(f"🔍 422 Debug - Request Headers: {headers}")
                        logger.error(f"🔍 422 Debug - Request Data: {data}")
                        logger.error(f"🔍 422 Debug - Response: {error_response}")
                    
                    return False, {
                        "error": f"API request failed with status {response.status_code}",
                        "message": error_response.get("message", "Unknown error") if isinstance(error_response, dict) else str(error_response),
                        "status_code": response.status_code,
                        "response_body": error_response
                    }
                    
        except Exception as e:
            logger.error(f"❌ Request error: {str(e)}")
            return False, {"error": "Request failed", "message": str(e)}

    async def _make_tata_click_to_call_request(
        self, 
        agent_number: str, 
        destination_number: str,
        custom_identifier: str,
        caller_id: Optional[str] = None,
        call_purpose: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Tuple[bool, Dict]:
        """
        Make Tata click-to-call request with EXACT format from documentation
        This is the critical method that was causing 422 errors
        """
        try:
            # ACTUAL FORMAT that Tata expects
            request_data = {
                "destination_number": destination_number,  # Required: Customer phone with +
                "agent_number": agent_number,              # Required: Agent number (clean, no +)
                "call_purpose": call_purpose or "CRM Call", # Required: Purpose of call  
                "priority": "normal",                      # Required: Call priority
                "notes": notes or "Click-to-call from CRM" # Required: Call notes
            }
            
            # Add caller_id if provided (without + prefix)
            if caller_id:
                clean_caller_id = caller_id
                if clean_caller_id.startswith('+91'):
                    clean_caller_id = clean_caller_id[3:]  # Remove +91
                elif clean_caller_id.startswith('+'):
                    clean_caller_id = clean_caller_id[1:]  # Remove +
                elif clean_caller_id.startswith('91'):
                    clean_caller_id = clean_caller_id[2:]  # Remove 91
                
                request_data["caller_id"] = clean_caller_id
            
            logger.info(f"🚀 Making Tata click-to-call request:")
            logger.info(f"   Agent Number: {agent_number}")
            logger.info(f"   Destination: {destination_number}")
            logger.info(f"   Caller ID: {request_data.get('caller_id', 'Not set')}")
            logger.info(f"   Request Data: {request_data}")
            
            # Make the API call
            success, response = await self._make_authenticated_request(
                method="POST",
                url=self.endpoints["click_to_call"],
                data=request_data,
                user_id="system"
            )
            
            if success and response.get("success"):
                logger.info(f"✅ Tata API call successful: {response}")
                return True, {
                    "success": True,
                    "call_id": response.get("call_id"),
                    "message": response.get("message", "Call initiated successfully"),
                    "tata_response": response
                }
            else:
                logger.error(f"❌ Tata API call failed: {response}")
                return False, {
                    "error": response.get("error", "Tata API call failed"),
                    "message": response.get("message", "Unknown error"),
                    "tata_response": response
                }
                
        except Exception as e:
            logger.error(f"❌ Tata API call exception: {str(e)}")
            return False, {"error": "API call failed", "message": str(e)}

    # ==========================================================================
    # MAIN CALLING METHODS - NO LOGGING
    # ==========================================================================

    async def initiate_click_to_call_simple(
        self,
        lead_id: str,
        current_user: Dict[str, Any],
        notes: Optional[str] = None,
        call_purpose: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        CLEANED: Simplified click-to-call - NO LOGGING
        
        This method:
        1. Validates user Tata sync (fixes wrong agent_id)
        2. Auto-fetches lead phone number
        3. Uses exact Tata API format (fixes 422 errors)
        4. NO DATABASE STORAGE - Direct API call only
        
        Usage: Only requires lead_id, everything else is auto-handled
        """
        try:
            user_email = current_user.get("email", "unknown")
            logger.info(f"🎯 User {user_email} initiating simplified click-to-call for lead {lead_id} (NO LOGGING)")
            
            # 1. Extract and validate user ID
            user_id = (current_user.get("user_id") or 
                      current_user.get("_id") or 
                      current_user.get("id"))
            
            if not user_id:
                return False, {"error": "User ID not found", "message": "Unable to identify user"}
            
            user_id = str(user_id)
            
            # 2. Validate user Tata sync
            sync_valid, sync_data = await self._validate_user_tata_sync(user_id, user_email)
            if not sync_valid:
                logger.error(f"❌ User {user_email} has invalid Tata sync: {sync_data.get('message')}")
                return False, sync_data
            
            agent_number = sync_data.get("tata_agent_id")
            if not agent_number:
                return False, {
                    "error": "Agent ID missing",
                    "message": "No Tata agent ID found in sync data"
                }
            
            logger.info(f"✅ Using validated agent number: {agent_number}")
            
            # 3. Auto-fetch lead phone number
            destination_number = await self._get_lead_phone_number(lead_id)
            if not destination_number:
                return False, {
                    "error": "Lead phone not found",
                    "message": f"No phone number found for lead {lead_id}"
                }
            
            logger.info(f"✅ Auto-fetched lead phone: {destination_number}")
            
            # 4. Generate tracking identifier (for TATA API only)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            custom_identifier = f"crm_call_{lead_id}_{timestamp}"
            
            # 5. Make Tata API call directly (NO DATABASE LOGGING)
            call_success, call_result = await self._make_tata_click_to_call_request(
                agent_number=agent_number,
                destination_number=destination_number,
                custom_identifier=custom_identifier,
                caller_id=sync_data.get("tata_extension"),
                call_purpose=call_purpose or "CRM Call",
                notes=notes
            )
            
            # 6. Return result (NO DATABASE OPERATIONS)
            if call_success:
                logger.info(f"✅ Click-to-call successful for lead {lead_id} (NO LOGGING)")
                
                return True, {
                    "success": True,
                    "message": "Call initiated successfully",
                    "tata_call_id": call_result.get("call_id"),
                    "agent_number": agent_number,
                    "destination_number": destination_number,
                    "status": "ringing",
                    "note": "Call initiated via TATA API - no local logging"
                }
            else:
                logger.error(f"❌ Click-to-call failed for lead {lead_id}: {call_result.get('message')}")
                
                return False, {
                    "error": call_result.get("error", "Call failed"),
                    "message": call_result.get("message", "Unable to initiate call"),
                    "tata_response": call_result.get("tata_response")
                }
                
        except Exception as e:
            logger.error(f"❌ Click-to-call system error: {str(e)}")
            return False, {"error": "System error", "message": str(e)}

    async def initiate_click_to_call(
        self, 
        lead_id: str,
        destination_number: Optional[str] = None,
        current_user: Dict[str, Any] = None,
        caller_id: Optional[str] = None,
        notes: Optional[str] = None,
        call_timeout: Optional[int] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Legacy click-to-call method - NO LOGGING
        Kept for backward compatibility with existing code
        """
        try:
            logger.info(f"Legacy click-to-call called for lead {lead_id} (NO LOGGING)")
            
            # If destination_number is provided, validate it matches lead
            if destination_number:
                auto_phone = await self._get_lead_phone_number(lead_id)
                if auto_phone and auto_phone != destination_number:
                    logger.warning(f"⚠️ Provided phone {destination_number} doesn't match lead phone {auto_phone}")
            
            # Use the simplified method which has all the fixes
            return await self.initiate_click_to_call_simple(
                lead_id=lead_id,
                current_user=current_user,
                notes=notes,
                call_purpose=None  # Legacy method doesn't have call_purpose
            )
            
        except Exception as e:
            logger.error(f"Legacy click-to-call error: {str(e)}")
            return False, {"error": "System error", "message": str(e)}

    async def initiate_support_call(
        self,
        customer_number: str,
        current_user: Dict[str, Any],
        caller_id: Optional[str] = None,
        lead_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Initiate support call using Tata support API - NO LOGGING"""
        try:
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            user_email = current_user.get("email", "unknown")
            
            logger.info(f"Initiating support call for {user_email} to {customer_number} (NO LOGGING)")
            
            # Validate user sync for support calls too
            sync_valid, sync_data = await self._validate_user_tata_sync(user_id, user_email)
            if not sync_valid:
                return False, sync_data
            
            # Get API key for support calls
            api_key = getattr(self.settings, 'TATA_SUPPORT_API_KEY', None)
            if not api_key:
                return False, {
                    "error": "Configuration error",
                    "message": "Support call API key not configured"
                }
            
            # Prepare support call request
            support_request_data = {
                "customer_number": customer_number,
                "api_key": api_key,
                "get_call_id": 1
            }
            
            if caller_id:
                support_request_data["caller_id"] = caller_id
            
            # Make support call request (NO DATABASE LOGGING)
            success, response_data = await self._make_authenticated_request(
                method="POST",
                url=self.endpoints["support_call"],
                data=support_request_data,
                user_id="system"
            )
            
            if success and response_data.get("success"):
                logger.info(f"✅ Support call initiated successfully (NO LOGGING)")
                
                return True, {
                    "success": True,
                    "message": "Support call initiated successfully",
                    "tata_call_id": response_data.get("call_id"),
                    "status": "ringing",
                    "note": "Support call initiated via TATA API - no local logging"
                }
            else:
                return False, {
                    "error": "Support call failed",
                    "message": response_data.get("message", "Unknown error")
                }
                
        except Exception as e:
            logger.error(f"Support call error: {str(e)}")
            return False, {"error": "System error", "message": str(e)}

    # ==========================================================================
    # UTILITY METHODS - PRESERVED
    # ==========================================================================

    async def validate_phone_number(self, phone_number: str) -> Dict[str, Any]:
        """Validate phone number format and provide cleaning suggestions"""
        try:
            original = phone_number
            cleaned = re.sub(r'[^\d+]', '', phone_number)
            
            result = {
                "original_number": original,
                "cleaned_number": cleaned,
                "is_valid": False,
                "validation_errors": [],
                "suggestions": []
            }
            
            if not cleaned:
                result["validation_errors"].append("Phone number cannot be empty")
                return result
            
            if len(cleaned) < 10:
                result["validation_errors"].append("Phone number too short (minimum 10 digits)")
            elif len(cleaned) > 15:
                result["validation_errors"].append("Phone number too long (maximum 15 digits)")
            
            if not re.match(r'^\+?[1-9]\d{1,14}$', cleaned):
                result["validation_errors"].append("Invalid phone number format")
            
            # Indian number specific validation
            if cleaned.startswith('+91') or (len(cleaned) == 10 and cleaned[0] in '6789'):
                if cleaned.startswith('+91'):
                    indian_number = cleaned[3:]
                else:
                    indian_number = cleaned
                
                if len(indian_number) == 10 and indian_number[0] in '6789':
                    result["is_valid"] = True
                    result["country_code"] = "+91"
                    result["national_format"] = indian_number
                    result["international_format"] = f"+91{indian_number}"
                else:
                    result["validation_errors"].append("Invalid Indian mobile number format")
            elif cleaned.startswith('+') and len(cleaned) >= 11:
                result["is_valid"] = True
                result["international_format"] = cleaned
            elif len(cleaned) >= 10 and len(cleaned) <= 15:
                result["is_valid"] = True
                result["suggestions"].append("Add country code for international calling")
            
            return result
            
        except Exception as e:
            logger.error(f"Phone validation error: {str(e)}")
            return {
                "original_number": phone_number,
                "cleaned_number": phone_number,
                "is_valid": False,
                "validation_errors": [f"Validation failed: {str(e)}"],
                "suggestions": []
            }

    # ==========================================================================
    # SIMPLIFIED METHODS (NO LOGGING OPERATIONS)
    # ==========================================================================

    async def check_user_call_permissions(self, user_id: str) -> Dict[str, Any]:
        """Check user call permissions - NO LOGGING"""
        try:
            db = self._get_db()
            if not db:
                return {
                    "can_make_calls": False,
                    "has_tata_mapping": False,
                    "permission_errors": ["Database unavailable"]
                }
            
            # Get user mapping
            user_mapping = await db.tata_user_mappings.find_one({"crm_user_id": user_id})
            
            if user_mapping:
                return {
                    "can_make_calls": user_mapping.get("can_make_calls", False),
                    "has_tata_mapping": True,
                    "tata_agent_id": user_mapping.get("tata_agent_id"),
                    "permission_errors": []
                }
            else:
                return {
                    "can_make_calls": False,
                    "has_tata_mapping": False,
                    "permission_errors": ["No TATA mapping found"]
                }
                
        except Exception as e:
            logger.error(f"Error checking user permissions: {str(e)}")
            return {
                "can_make_calls": False,
                "has_tata_mapping": False,
                "permission_errors": [f"Permission check failed: {str(e)}"]
            }

    async def get_call_status(self, call_id: str, requesting_user_id: str) -> Dict[str, Any]:
        """Get call status - SIMPLIFIED (NO LOGGING)"""
        return {
            "success": False,
            "message": "Call status not tracked (no logging enabled)",
            "note": "Use TATA dashboard for call status tracking"
        }

    async def end_call(self, call_id: str, user_id: str, call_outcome: Optional[str] = None, notes: Optional[str] = None) -> Dict[str, Any]:
        """End call - SIMPLIFIED (NO LOGGING)"""
        return {
            "success": True,
            "message": "Call end acknowledged (no logging enabled)",
            "final_status": "acknowledged",
            "note": "Use TATA dashboard for call management"
        }

    async def get_user_active_calls(self, user_id: str) -> List[Dict]:
        """Get user active calls - SIMPLIFIED (NO LOGGING)"""
        return []  # No local call tracking

    async def get_all_active_calls(self) -> List[Dict]:
        """Get all active calls - SIMPLIFIED (NO LOGGING)"""
        return []  # No local call tracking

    async def process_webhook(self, webhook_payload: Any, raw_body: bytes, headers: Dict) -> Dict[str, Any]:
        """Process TATA webhook - SIMPLIFIED (NO LOGGING)"""
        try:
            logger.info(f"Webhook received but not processed (no logging enabled)")
            return {
                "success": True,
                "message": "Webhook acknowledged but not processed (no logging enabled)",
                "note": "Webhook data not stored locally"
            }
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}")
            return {
                "success": False,
                "message": f"Webhook processing failed: {str(e)}"
            }


# Create singleton instance
tata_call_service = TataCallService()