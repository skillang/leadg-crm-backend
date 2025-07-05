# app/services/direct_calling_service.py - NEW FILE

import aiohttp
import logging
import random
from typing import Dict, Any
from datetime import datetime
import os

from ..config.database import get_database

logger = logging.getLogger(__name__)

class DirectCallingService:
    def __init__(self):
        self.base_url = os.getenv("TATA_CLOUDPHONE_BASE_URL", "https://cloudphone.tatateleservices.com")
        self.jwt_token = os.getenv("SMARTFLO_JWT_TOKEN")
        self.mock_mode = os.getenv("SMARTFLO_MOCK_MODE", "false").lower() == "true"
        self._db = None
    
    @property
    def db(self):
        """Lazy database connection"""
        if self._db is None:
            self._db = get_database()
        return self._db
    
    async def make_user_call(self, user_phone: str, customer_phone: str, user_id: str, 
                           lead_id: str, user_email: str, lead_name: str) -> Dict[str, Any]:
        """
        Direct calling: User's phone rings first, then customer's phone
        """
        try:
            logger.info(f"📞 Direct call: {user_phone} → {customer_phone} (Lead: {lead_id})")
            
            if self.mock_mode:
                # Mock call for testing
                mock_call_id = f"DIRECT_MOCK_{random.randint(100000, 999999)}"
                
                # Log mock call
                await self._log_call(
                    call_id=mock_call_id,
                    user_phone=user_phone,
                    customer_phone=customer_phone,
                    user_id=user_id,
                    lead_id=lead_id,
                    user_email=user_email,
                    lead_name=lead_name,
                    status="mock_initiated",
                    provider="Mock TATA"
                )
                
                return {
                    "success": True,
                    "call_id": mock_call_id,
                    "status": "initiated",
                    "message": "Mock call initiated - your phone will ring first",
                    "mock_mode": True,
                    "user_phone": user_phone,
                    "customer_phone": customer_phone
                }
            
            # Real TATA API call
            call_result = await self._initiate_tata_bridge_call(
                user_phone=user_phone,
                customer_phone=customer_phone,
                user_id=user_id,
                lead_id=lead_id
            )
            
            if call_result.get("success"):
                # Log successful call
                await self._log_call(
                    call_id=call_result.get("call_id"),
                    user_phone=user_phone,
                    customer_phone=customer_phone,
                    user_id=user_id,
                    lead_id=lead_id,
                    user_email=user_email,
                    lead_name=lead_name,
                    status="initiated",
                    provider="TATA Cloud Phone"
                )
                
                logger.info(f"✅ TATA call initiated: {call_result.get('call_id')}")
                
            return call_result
            
        except Exception as e:
            logger.error(f"Direct call failed: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _initiate_tata_bridge_call(self, user_phone: str, customer_phone: str, 
                                       user_id: str, lead_id: str) -> Dict[str, Any]:
        """
        Make direct call via TATA using the WORKING format from before
        """
        try:
            # Try TATA's expected key=value format
            headers = {
                "Authorization": f"token={self.jwt_token}",  # 🎯 Try key=value format
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            # REVERT TO WORKING TATA API PAYLOAD FORMAT
            call_payload = {
                "fromExtension": user_phone,        # Use working format
                "toNumber": customer_phone,         # Customer number
                "agentId": user_id,                 # User as agent ID
                "callType": "Outbound",
                "priority": "Normal",
                "originatingUser": user_id
            }
            
            logger.info(f"📡 TATA Direct Call (working format): {user_phone} → {customer_phone}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/v1/calls/initiate",  # REVERT to working endpoint
                    headers=headers,
                    json=call_payload,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    
                    if response.status in [200, 201]:
                        response_data = await response.json()
                        
                        return {
                            "success": True,
                            "call_id": response_data.get("callId") or response_data.get("id"),
                            "status": response_data.get("status", "initiated"),
                            "provider": "TATA Cloud Phone",
                            "message": "Call initiated - your phone will ring first"
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ TATA bridge call failed: {response.status} - {error_text}")
                        
                        return {
                            "success": False,
                            "error": f"TATA call failed: {error_text}",
                            "status_code": response.status
                        }
                        
        except Exception as e:
            logger.error(f"TATA bridge call exception: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _log_call(self, call_id: str, user_phone: str, customer_phone: str,
                       user_id: str, lead_id: str, user_email: str, lead_name: str,
                       status: str, provider: str):
        """Log call details for tracking and analytics"""
        try:
            call_log = {
                "call_id": call_id,
                "call_type": "direct_user_call",
                "user_id": user_id,
                "user_email": user_email,
                "user_phone": user_phone,
                "customer_phone": customer_phone,
                "lead_id": lead_id,
                "lead_name": lead_name,
                "status": status,
                "provider": provider,
                "created_at": datetime.utcnow(),
                "call_direction": "outbound",
                "call_method": "bridge_call"
            }
            
            await self.db.call_logs.insert_one(call_log)
            logger.info(f"📝 Call logged: {call_id} ({user_email} → {customer_phone})")
            
        except Exception as e:
            # Don't fail the call if logging fails
            logger.warning(f"Call logging failed (non-critical): {str(e)}")
    
    async def get_call_history(self, user_id: str = None, limit: int = 50) -> list:
        """Get call history for user or all users"""
        try:
            query = {"call_type": "direct_user_call"}
            if user_id:
                query["user_id"] = user_id
            
            calls = await self.db.call_logs.find(query) \
                                         .sort("created_at", -1) \
                                         .limit(limit) \
                                         .to_list(None)
            
            # Convert ObjectId to string for JSON serialization
            for call in calls:
                call["_id"] = str(call["_id"])
            
            return calls
            
        except Exception as e:
            logger.error(f"Failed to get call history: {str(e)}")
            return []

# Create singleton instance
direct_calling_service = DirectCallingService()