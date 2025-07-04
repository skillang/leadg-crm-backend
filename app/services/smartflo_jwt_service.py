# app/services/smartflo_jwt_service.py - FIXED for TATA Cloud Phone Service
import aiohttp
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from bson import ObjectId
import os

from ..config.database import get_database

logger = logging.getLogger(__name__)

class SmartfloJWTService:
    def __init__(self):
        # ✅ FIXED: Use correct TATA Cloud Phone API
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
        
    async def test_connection(self) -> Dict[str, Any]:
        """Test JWT Bearer token authentication with TATA Cloud Phone"""
        
        if self.mock_mode:
            return {
                "success": True,
                "status_code": 200,
                "auth_method": "Bearer JWT (MOCK)",
                "response_data": "Mock connection successful",
                "error": None
            }
        
        try:
            headers = {
                "Authorization": f"Bearer {self.jwt_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/v1/profile",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    if response.status == 200:
                        response_data = await response.json()
                        return {
                            "success": True,
                            "status_code": response.status,
                            "auth_method": "Bearer JWT (TATA Cloud Phone)",
                            "response_data": f"Connected as: {response_data.get('name', 'Unknown')}",
                            "user_email": response_data.get('email'),
                            "error": None
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "status_code": response.status,
                            "auth_method": "Bearer JWT (TATA)",
                            "error": error_text
                        }
                    
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Connection timeout to TATA Cloud Phone API",
                "auth_method": "Bearer JWT (TATA)"
            }
        except Exception as e:
            logger.error(f"TATA Cloud Phone connection test failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "auth_method": "Bearer JWT (TATA)"
            }

    async def create_agent(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Setup user with call routing capability (no fixed extension assignment)"""
        try:
            from .call_routing_service import call_routing_service
            
            routing_result = await call_routing_service.setup_user_calling(user_data)
            
            if routing_result.get("success"):
                calling_setup = routing_result["calling_setup"]
                
                logger.info(f"✅ Call routing setup successful: {routing_result['available_agents']} agents available")
                
                return {
                    "success": True,
                    "assignment_type": "call_routing",
                    "calling_enabled": True,
                    "routing_method": "next_available_agent",
                    "available_agents": routing_result["available_agents"],
                    "agent_pool": calling_setup["tata_agent_pool"],
                    "note": routing_result["note"],
                    "setup_date": calling_setup["setup_date"].isoformat(),
                    "agent_id": "ROUTING_POOL",
                    "extension_number": "DYNAMIC_ROUTING",
                    "temp_password": "NotApplicable",
                    "status": "active"
                }
            else:
                return {
                    "success": False,
                    "error": routing_result.get("error", "Call routing setup failed")
                }
                
        except Exception as e:
            logger.error(f"Call routing setup failed: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def update_user_calling_info(self, user_id: str, routing_info: Dict[str, Any]) -> bool:
        """Update user record with call routing information"""
        try:
            if routing_info.get("success"):
                update_data = {
                    "calling_enabled": True,
                    "routing_method": "next_available_agent",
                    "tata_agent_pool": routing_info.get("agent_pool", []),
                    "available_agents": routing_info.get("available_agents", 0),
                    "calling_status": "active",
                    "calling_provider": "TATA Cloud Phone",
                    "calling_setup_date": datetime.utcnow(),
                    "assignment_type": "call_routing",
                    "updated_at": datetime.utcnow(),
                    "extension_number": "DYNAMIC_ROUTING",
                    "agent_id": "ROUTING_POOL"
                }
            else:
                update_data = {
                    "calling_enabled": False,
                    "calling_status": "failed",
                    "calling_error": routing_info.get("error"),
                    "updated_at": datetime.utcnow()
                }
            
            result = await self.db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": update_data}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Failed to update user calling info: {str(e)}")
            return False

    async def make_test_call(self, from_extension: str, to_number: str, agent_id: str) -> Dict[str, Any]:
        """Make a test call using TATA Cloud Phone API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.jwt_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            call_payload = {
                "fromExtension": from_extension,
                "toNumber": to_number,
                "agentId": agent_id,
                "callType": "Outbound",
                "priority": "Normal"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/v1/calls/initiate",
                    headers=headers,
                    json=call_payload,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    
                    if response.status == 200 or response.status == 201:
                        response_data = await response.json()
                        return {
                            "success": True,
                            "call_id": response_data.get("callId") or response_data.get("id"),
                            "status": response_data.get("status"),
                            "from_extension": from_extension,
                            "to_number": to_number,
                            "provider": "TATA Cloud Phone"
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"TATA Call failed: {error_text}",
                            "status_code": response.status
                        }
                        
        except Exception as e:
            logger.error(f"TATA test call failed: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

# Create singleton instance
smartflo_jwt_service = SmartfloJWTService()
