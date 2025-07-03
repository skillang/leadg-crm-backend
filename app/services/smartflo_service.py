# app/services/smartflo_simple_service.py - Simple Bearer Token Authentication
import aiohttp
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from bson import ObjectId

from ..config.database import get_database
from ..config.settings import settings
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class SmartfloSimpleService:
    """Simple Smartflo API integration using Bearer Token authentication"""
    
    def __init__(self):
        self.base_url = settings.smartflo_api_base_url
        self.timeout = aiohttp.ClientTimeout(total=settings.smartflo_timeout)
        
    async def get_auth_token(self) -> Optional[str]:
        """
        Get Bearer token for Smartflo API authentication
        Uses email/password to get token from /v1/auth/login
        """
        try:
            # Check if we have credentials configured
            if not hasattr(settings, 'smartflo_email') or not hasattr(settings, 'smartflo_password'):
                logger.error("Smartflo email/password not configured")
                return None
            
            login_url = f"{self.base_url}/auth/login"
            login_payload = {
                "email": settings.smartflo_email,
                "password": settings.smartflo_password
            }
            
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(login_url, json=login_payload, headers=headers) as response:
                    if response.status == 200:
                        auth_data = await response.json()
                        access_token = auth_data.get("access_token")
                        
                        if access_token:
                            logger.info("✅ Smartflo authentication successful")
                            return access_token
                        else:
                            logger.error("❌ No access token in Smartflo response")
                            return None
                    else:
                        response_text = await response.text()
                        logger.error(f"❌ Smartflo authentication failed: {response.status} - {response_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ Error getting Smartflo auth token: {str(e)}")
            return None
    
    async def create_agent(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create Smartflo agent using the simple Create User API
        """
        try:
            logger.info(f"Creating Smartflo agent for user: {user_data.get('email')}")
            
            # Get authentication token
            auth_token = await self.get_auth_token()
            if not auth_token:
                return {
                    "success": False,
                    "error": "Failed to authenticate with Smartflo",
                    "retry_possible": True
                }
            
            # Prepare agent creation payload for /v1/user endpoint
            agent_payload = {
                "create_agent": True,  # ✅ This creates an agent!
                "status": True,        # Enable the user
                "name": f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
                "number": user_data.get('phone', ''),
                "email": user_data.get('email'),
                "login_id": user_data.get('email'),  # Use email as login ID
                "password": "TempPass123!",  # Temporary password - user should change
                "user_role": 1,  # Default role - adjust based on your setup
                "caller_id": [],  # Empty for now - can be configured later
                "assign_extension": True,  # ✅ This should create extension!
                "route_call_through": 2,  # BOTH agent and extension
                "block_web_login": False,
                "login_based_calling": True
            }
            
            headers = {
                "Authorization": f"Bearer {auth_token}",  # ✅ Simple Bearer token!
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            # Make API call to create user/agent
            create_url = f"{self.base_url}/user"
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(create_url, json=agent_payload, headers=headers) as response:
                    response_text = await response.text()
                    
                    if response.status in [200, 201]:
                        try:
                            response_data = await response.json()
                            
                            logger.info(f"✅ Smartflo agent created successfully")
                            
                            # Extract agent/extension info from response
                            return {
                                "success": True,
                                "agent_id": response_data.get("id") or response_data.get("agent_id"),
                                "extension_number": response_data.get("extension") or response_data.get("ext") or "Check admin panel",
                                "smartflo_user_id": response_data.get("user_id") or response_data.get("id"),
                                "status": "active",
                                "created_at": datetime.utcnow(),
                                "response_data": response_data,  # Full response for debugging
                                "temp_password": "TempPass123!"  # Share with admin for user setup
                            }
                            
                        except Exception as json_error:
                            logger.error(f"❌ JSON parsing error: {json_error}")
                            # Even if JSON parsing fails, 200/201 means success
                            return {
                                "success": True,
                                "agent_id": "check_response",
                                "extension_number": "check_admin_panel",
                                "status": "active",
                                "created_at": datetime.utcnow(),
                                "raw_response": response_text,
                                "note": "Agent created but response parsing failed - check Smartflo admin panel"
                            }
                    else:
                        logger.error(f"❌ Smartflo agent creation failed: {response.status} - {response_text}")
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}: {response_text}",
                            "retry_possible": True
                        }
                        
        except Exception as e:
            logger.error(f"❌ Unexpected error in create_agent: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "retry_possible": True
            }
    
    async def update_user_calling_status(
        self, 
        user_id: str, 
        smartflo_result: Dict[str, Any],
        attempt_number: int = 1
    ) -> bool:
        """Update user with Smartflo agent details"""
        try:
            db = get_database()
            
            if smartflo_result["success"]:
                # Successful setup
                update_data = {
                    "extension_number": smartflo_result.get("extension_number"),
                    "smartflo_agent_id": smartflo_result.get("agent_id"),
                    "smartflo_user_id": smartflo_result.get("smartflo_user_id"),
                    "calling_status": "active",
                    "can_make_calls": True,
                    "smartflo_setup_attempts": attempt_number,
                    "smartflo_setup_at": smartflo_result.get("created_at"),
                    "smartflo_temp_password": smartflo_result.get("temp_password"),  # Store temp password
                    "updated_at": datetime.utcnow()
                }
                logger.info(f"✅ Updating user {user_id} with active calling status")
            else:
                # Failed setup
                update_data = {
                    "calling_status": "failed",
                    "can_make_calls": False,
                    "smartflo_setup_attempts": attempt_number,
                    "smartflo_last_error": smartflo_result.get("error", "Unknown error"),
                    "updated_at": datetime.utcnow()
                }
                logger.warning(f"⚠️ Updating user {user_id} with failed calling status")
            
            result = await db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": update_data}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error updating user calling status: {str(e)}")
            return False
    
    async def test_authentication(self) -> Dict[str, Any]:
        """Test Smartflo authentication"""
        try:
            auth_token = await self.get_auth_token()
            
            if auth_token:
                return {
                    "success": True,
                    "message": "Authentication successful",
                    "token_preview": auth_token[:20] + "..." if len(auth_token) > 20 else auth_token
                }
            else:
                return {
                    "success": False,
                    "message": "Authentication failed"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

# Global service instance
smartflo_simple_service = SmartfloSimpleService()