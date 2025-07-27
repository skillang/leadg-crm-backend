# app/services/tata_call_service.py
# Tata Tele Call Service
# Handles click-to-call, support calls, and call management operations

import httpx
import logging
import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List
from bson import ObjectId

from ..config.database import get_database
from ..config.settings import get_settings
from ..models.call_log import (
    ClickToCallRequest, SupportCallRequest, TataCallResponse, TataSupportCallResponse,
    CallLogCreate, CallLogUpdate, CallLogResponse, CallStatus, CallType, CallOutcome,
    CallDirection, BulkCallRequest, BulkCallResponse, CallSystemHealth
)
from ..models.tata_integration import TataIntegrationLog
from .tata_auth_service import tata_auth_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TataCallService:
    """
    Comprehensive Tata Tele Call Service
    Handles all call operations including click-to-call, support calls, and call management
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
            "user_detail": f"{self.base_url}/v1/user"
        }
        
        self.default_timeout = getattr(self.settings, 'default_call_timeout', 300)
        self.max_concurrent_calls = getattr(self.settings, 'max_concurrent_calls', 50)

    async def _make_authenticated_request(
        self, 
        method: str, 
        url: str, 
        data: Optional[Dict] = None,
        user_id: str = "system"
    ) -> Tuple[bool, Dict[str, Any]]:
        """Make authenticated request to Tata API using stored tokens"""
        try:
            # Get valid token
            token = await self.auth_service.get_valid_token(user_id)
            if not token:
                logger.error(f"No valid token available for user: {user_id}")
                return False, {"error": "Authentication failed", "message": "No valid token available"}
            
            # Prepare headers
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
            # Make request
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"Making authenticated {method} request to {url}")
                
                if method.upper() == "POST":
                    response = await client.post(url, json=data, headers=headers)
                elif method.upper() == "GET":
                    response = await client.get(url, headers=headers)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Parse response
                try:
                    response_data = response.json()
                except:
                    response_data = {"message": response.text}
                
                logger.info(f"Response status: {response.status_code}")
                
                if response.status_code == 200:
                    return True, response_data
                else:
                    logger.warning(f"Request failed with status {response.status_code}: {response_data}")
                    return False, response_data
                    
        except httpx.TimeoutException:
            logger.error("Request timeout")
            return False, {"error": "Timeout", "message": "Request timed out"}
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            return False, {"error": "Request failed", "message": str(e)}

    async def _log_call_event(
        self, 
        event_type: str, 
        status: str, 
        message: str,
        call_id: Optional[str] = None,
        lead_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log call events for auditing and monitoring"""
        try:
            log_entry = TataIntegrationLog(
                event_type=event_type,
                user_id=user_id,
                tata_user_id=call_id,
                status=status,
                message=message,
                metadata=metadata or {}
            )
            
            await self.db.tata_integration_logs.insert_one(log_entry.dict())
            logger.info(f"Call event logged: {event_type} - {status}")
        except Exception as e:
            logger.error(f"Failed to log call event: {str(e)}")

    async def _get_user_agent_number(self, crm_user_id: str) -> Optional[str]:
        """Get Tata agent number for CRM user"""
        try:
            # Get user mapping
            user_mapping = await self.db.tata_user_mappings.find_one({"crm_user_id": crm_user_id})
            if not user_mapping:
                logger.warning(f"No Tata mapping found for CRM user: {crm_user_id}")
                return None
            
            agent_phone = user_mapping.get("tata_phone")
            if not agent_phone:
                logger.warning(f"No agent phone found for user: {crm_user_id}")
                return None
                
            return agent_phone
            
        except Exception as e:
            logger.error(f"Error getting agent number for user {crm_user_id}: {str(e)}")
            return None

    async def _create_call_log(self, call_data: CallLogCreate, current_user: Dict[str, Any]) -> str:
        """Create call log entry in database"""
        try:
            # Enrich call data with user information
            call_doc = call_data.dict()
            call_doc.update({
                "_id": ObjectId(),
                "created_at": datetime.utcnow(),
                "call_status": CallStatus.INITIATED,
                "call_direction": CallDirection.OUTBOUND,
                "metadata": {
                    "created_by_name": current_user.get("full_name", "Unknown"),
                    "created_by_email": current_user.get("email")
                }
            })
            
            # Insert call log
            result = await self.db.call_logs.insert_one(call_doc)
            call_log_id = str(result.inserted_id)
            
            logger.info(f"Created call log: {call_log_id}")
            return call_log_id
            
        except Exception as e:
            logger.error(f"Error creating call log: {str(e)}")
            raise

    async def _update_call_log(self, call_log_id: str, updates: CallLogUpdate):
        """Update call log with new information"""
        try:
            update_data = updates.dict(exclude_none=True)
            update_data["updated_at"] = datetime.utcnow()
            
            await self.db.call_logs.update_one(
                {"_id": ObjectId(call_log_id)},
                {"$set": update_data}
            )
            
            logger.info(f"Updated call log: {call_log_id}")
            
        except Exception as e:
            logger.error(f"Error updating call log {call_log_id}: {str(e)}")

    async def _log_activity_to_lead(
        self, 
        lead_id: str, 
        activity_type: str, 
        description: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log call activity to lead timeline"""
        try:
            activity = {
                "_id": ObjectId(),
                "lead_id": lead_id,
                "activity_type": activity_type,
                "description": description,
                "created_by": user_id,
                "created_at": datetime.utcnow(),
                "metadata": metadata or {}
            }
            
            await self.db.lead_activities.insert_one(activity)
            logger.info(f"Logged activity to lead {lead_id}: {activity_type}")
            
        except Exception as e:
            logger.error(f"Error logging activity to lead {lead_id}: {str(e)}")

    async def initiate_click_to_call(
        self, 
        lead_id: str,
        destination_number: str,
        current_user: Dict[str, Any],
        caller_id: Optional[str] = None,
        notes: Optional[str] = None,
        call_timeout: Optional[int] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Initiate click-to-call to a lead"""
        call_log_id = None
        try:
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            # Get agent number for current user
            agent_number = await self._get_user_agent_number(user_id)
            if not agent_number:
                return False, {
                    "error": "Agent not found", 
                    "message": "No Tata agent mapping found for current user"
                }
            
            # Create call log entry
            call_data = CallLogCreate(
                lead_id=lead_id,
                caller_user_id=user_id,
                destination_number=destination_number,
                caller_id=caller_id,
                call_type=CallType.CLICK_TO_CALL,
                notes=notes,
                custom_identifier=f"crm_call_{lead_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            )
            
            call_log_id = await self._create_call_log(call_data, current_user)
            
            # Prepare Tata API request
            tata_request = ClickToCallRequest(
                agent_number=agent_number,
                destination_number=destination_number,
                caller_id=caller_id,
                async_call=1,
                call_timeout=call_timeout or self.default_timeout,
                get_call_id=1,
                custom_identifier=call_data.custom_identifier
            )
            
            # Make call request to Tata API
            success, response_data = await self._make_authenticated_request(
                method="POST",
                url=self.endpoints["click_to_call"],
                data=tata_request.dict(),
                user_id="system"
            )
            
            if success and response_data.get("success"):
                # Parse successful response
                tata_response = TataCallResponse(**response_data)
                
                # Update call log with Tata call ID
                updates = CallLogUpdate(
                    call_status=CallStatus.RINGING,
                    tata_call_id=tata_response.call_id,
                    initiated_at=datetime.utcnow(),
                    metadata={"tata_response": response_data}
                )
                await self._update_call_log(call_log_id, updates)
                
                # Log activity to lead timeline
                await self._log_activity_to_lead(
                    lead_id=lead_id,
                    activity_type="call_initiated",
                    description=f"Call initiated to {destination_number}",
                    user_id=user_id,
                    metadata={
                        "call_type": "click_to_call",
                        "destination_number": destination_number,
                        "tata_call_id": tata_response.call_id,
                        "call_log_id": call_log_id
                    }
                )
                
                logger.info(f"Successfully initiated click-to-call for lead {lead_id}")
                
                return True, {
                    "success": True,
                    "message": "Call initiated successfully",
                    "call_log_id": call_log_id,
                    "tata_call_id": tata_response.call_id,
                    "status": "ringing"
                }
                
            else:
                # Handle failed call
                error_msg = response_data.get("message", "Call initiation failed")
                
                # Update call log with failure
                updates = CallLogUpdate(
                    call_status=CallStatus.FAILED,
                    call_outcome=CallOutcome.NO_RESPONSE,
                    metadata={"error_response": response_data}
                )
                await self._update_call_log(call_log_id, updates)
                
                return False, {
                    "error": "Call failed",
                    "message": error_msg,
                    "call_log_id": call_log_id
                }
                
        except Exception as e:
            error_msg = f"Click-to-call error: {str(e)}"
            logger.error(error_msg)
            
            # Update call log with error if it was created
            if call_log_id:
                try:
                    updates = CallLogUpdate(
                        call_status=CallStatus.FAILED,
                        metadata={"exception": str(e)}
                    )
                    await self._update_call_log(call_log_id, updates)
                except:
                    pass
            
            return False, {"error": "System error", "message": error_msg}

    async def initiate_support_call(
        self,
        customer_number: str,
        current_user: Dict[str, Any],
        caller_id: Optional[str] = None,
        lead_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Initiate support call using Tata support API"""
        call_log_id = None
        try:
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            # Create call log entry
            call_data = CallLogCreate(
                lead_id=lead_id or f"SUPPORT_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                caller_user_id=user_id,
                destination_number=customer_number,
                caller_id=caller_id,
                call_type=CallType.SUPPORT_CALL,
                notes=notes
            )
            
            call_log_id = await self._create_call_log(call_data, current_user)
            
            # Get API key for support calls (should be configured)
            api_key = getattr(self.settings, 'TATA_SUPPORT_API_KEY', None)
            if not api_key:
                return False, {
                    "error": "Configuration error",
                    "message": "Support call API key not configured"
                }
            
            # Prepare support call request
            support_request = SupportCallRequest(
                customer_number=customer_number,
                api_key=api_key,
                get_call_id=1,
                caller_id=caller_id
            )
            
            # Make support call request
            success, response_data = await self._make_authenticated_request(
                method="POST",
                url=self.endpoints["support_call"],
                data=support_request.dict(),
                user_id="system"
            )
            
            if success and response_data.get("success"):
                # Parse successful response
                support_response = TataSupportCallResponse(**response_data)
                
                # Update call log
                updates = CallLogUpdate(
                    call_status=CallStatus.RINGING,
                    tata_call_id=support_response.call_id,
                    initiated_at=datetime.utcnow(),
                    metadata={"support_response": response_data}
                )
                await self._update_call_log(call_log_id, updates)
                
                logger.info(f"Successfully initiated support call to {customer_number}")
                
                return True, {
                    "success": True,
                    "message": "Support call initiated successfully",
                    "call_log_id": call_log_id,
                    "tata_call_id": support_response.call_id,
                    "status": "ringing"
                }
                
            else:
                error_msg = response_data.get("message", "Support call failed")
                
                # Update call log with failure
                updates = CallLogUpdate(
                    call_status=CallStatus.FAILED,
                    metadata={"error_response": response_data}
                )
                await self._update_call_log(call_log_id, updates)
                
                return False, {
                    "error": "Support call failed",
                    "message": error_msg,
                    "call_log_id": call_log_id
                }
                
        except Exception as e:
            error_msg = f"Support call error: {str(e)}"
            logger.error(error_msg)
            
            if call_log_id:
                try:
                    updates = CallLogUpdate(
                        call_status=CallStatus.FAILED,
                        metadata={"exception": str(e)}
                    )
                    await self._update_call_log(call_log_id, updates)
                except:
                    pass
            
            return False, {"error": "System error", "message": error_msg}

    async def validate_phone_number(self, phone_number: str) -> Dict[str, Any]:
        """Validate phone number format and provide cleaning suggestions"""
        try:
            original = phone_number
            
            # Clean phone number
            cleaned = re.sub(r'[^\d+]', '', phone_number)
            
            # Validation results
            result = {
                "original_number": original,
                "cleaned_number": cleaned,
                "is_valid": False,
                "validation_errors": [],
                "suggestions": []
            }
            
            # Basic validation
            if not cleaned:
                result["validation_errors"].append("Phone number cannot be empty")
                return result
            
            # Check length
            if len(cleaned) < 10:
                result["validation_errors"].append("Phone number too short (minimum 10 digits)")
            elif len(cleaned) > 15:
                result["validation_errors"].append("Phone number too long (maximum 15 digits)")
            
            # Check format
            if not re.match(r'^\+?[1-9]\d{1,14}$', cleaned):
                result["validation_errors"].append("Invalid phone number format")
            
            # Add + if missing for international numbers
            if not cleaned.startswith('+') and len(cleaned) > 10:
                result["suggestions"].append(f"Consider international format: +{cleaned}")
            
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
            
            # General international validation
            elif cleaned.startswith('+') and len(cleaned) >= 11:
                result["is_valid"] = True
                result["international_format"] = cleaned
            
            # If no specific country detected but looks valid
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

    async def get_call_system_health(self) -> CallSystemHealth:
        """Get call system health status"""
        try:
            # Check integration health
            integration_health = await self.auth_service.get_integration_health()
            
            # Count active calls
            active_calls = await self.db.call_logs.count_documents({
                "call_status": {"$in": [CallStatus.INITIATED, CallStatus.RINGING, CallStatus.IN_PROGRESS]}
            })
            
            # Count calls in last hour
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            calls_last_hour = await self.db.call_logs.count_documents({
                "created_at": {"$gte": one_hour_ago}
            })
            
            # Calculate 24h success rate
            twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
            total_calls_24h = await self.db.call_logs.count_documents({
                "created_at": {"$gte": twenty_four_hours_ago}
            })
            
            successful_calls_24h = await self.db.call_logs.count_documents({
                "created_at": {"$gte": twenty_four_hours_ago},
                "call_status": CallStatus.COMPLETED,
                "call_outcome": {"$in": [CallOutcome.SUCCESSFUL, CallOutcome.INTERESTED]}
            })
            
            success_rate_24h = (successful_calls_24h / total_calls_24h * 100) if total_calls_24h > 0 else 0
            
            # Determine overall status
            if integration_health.tata_api_status == "healthy" and integration_health.token_valid:
                if active_calls < self.max_concurrent_calls and success_rate_24h > 80:
                    overall_status = "healthy"
                else:
                    overall_status = "degraded"
            else:
                overall_status = "unhealthy"
            
            return CallSystemHealth(
                overall_status=overall_status,
                tata_api_status=integration_health.tata_api_status,
                call_service_status="healthy" if overall_status != "unhealthy" else "unhealthy",
                database_status="healthy",
                active_calls=active_calls,
                calls_last_hour=calls_last_hour,
                success_rate_24h=success_rate_24h,
                average_response_time=100.0,
                recent_errors=[],
                system_alerts=[]
            )
            
        except Exception as e:
            logger.error(f"Error getting call system health: {str(e)}")
            return CallSystemHealth(
                overall_status="unhealthy",
                tata_api_status="unknown",
                call_service_status="unhealthy", 
                database_status="unknown",
                recent_errors=[f"Health check failed: {str(e)}"]
            )

# Create singleton instance
tata_call_service = TataCallService()