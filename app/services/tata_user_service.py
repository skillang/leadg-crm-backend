# app/services/tata_user_service.py
# 🔧 FIXED: Enhanced Tata User Service with Auto-Sync on Login
# Handles user synchronization between LeadG CRM and Tata Tele system

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from bson import ObjectId
import re
import httpx

from ..config.database import get_database
from ..config.settings import get_settings
from ..models.tata_user import (
    TataUserMapping, TataUserMappingCreate, TataUserMappingUpdate, TataUserMappingResponse,
    SyncStatus, TataUserType, UserStatus, BulkUserSyncRequest, BulkUserSyncResponse,
    UserSyncResult, UserSyncStatistics, UserMappingListResponse, UserMappingFilter,
    UserValidationResult, TataUserSyncConfig, UserSyncAuditLog
)
from ..models.tata_integration import TataUserData, TataUsersListResponse, TataIntegrationLog
from .tata_auth_service import tata_auth_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TataUserService:
    """
    Enhanced Tata User Service with Auto-Sync Functionality
    Handles user synchronization, mapping, and management between CRM and Tata Tele
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.db = None  # Lazy initialization
        self.auth_service = tata_auth_service
        self.base_url = self.settings.tata_api_base_url
        
        # API endpoints
        self.endpoints = {
            "users": f"{self.base_url}/v1/users",
            "user_detail": f"{self.base_url}/v1/user",
            "create_user": f"{self.base_url}/v1/user",
            "update_user": f"{self.base_url}/v1/user",
            "my_numbers": f"{self.base_url}/v1/my_number"
        }
        
        # Sync configuration
        self.max_sync_batch_size = getattr(self.settings, 'max_sync_batch_size', 10)

    def _get_db(self):
        """Lazy database initialization"""
        if self.db is None:
            try:
                self.db = get_database()
            except RuntimeError:
                return None
        return self.db

    # =============================================================================
    # 🆕 NEW: AUTO-SYNC ON LOGIN METHODS
    # =============================================================================

    async def auto_sync_on_login(self, user: Dict) -> Dict:
        """
        Auto-sync user with Tata agents during CRM login
        This is the main method called from auth.py during login
        """
        try:
            user_id = str(user.get("_id") or user.get("user_id"))
            user_phone = user.get("phone") or user.get("phone_number")
            user_email = user.get("email", "")
            
            logger.info(f"Starting Tata auto-sync for user: {user_email} with phone: {user_phone}")
            
            # 1. Check if user has phone number
            if not user_phone:
                logger.warning(f"User {user_email} has no phone number - cannot auto-sync")
                return {
                    "enabled": False,
                    "sync_status": "no_phone",
                    "message": "No phone number in user profile. Please add phone number to enable calling."
                }
            
            # 2. Check existing mapping (maybe already synced)
            existing_mapping = await self.get_user_mapping(user_id)
            if existing_mapping and existing_mapping.get("can_make_calls"):
                logger.info(f"User {user_email} already has valid Tata mapping")
                return {
                    "enabled": True,
                    "extension": existing_mapping.get("tata_extension") or existing_mapping.get("tata_caller_id"),
                    "agent_id": existing_mapping.get("tata_agent_id"),
                    "sync_status": "already_synced",
                    "message": "Already synced with Tata agent"
                }
            
            # 3. Fetch all Tata agents
            agents_result = await self.fetch_all_tata_users()
            if not agents_result.get("success"):
                logger.error(f"Failed to fetch Tata agents: {agents_result.get('message')}")
                return {
                    "enabled": False,
                    "sync_status": "api_error",
                    "message": "Failed to fetch Tata agents. Please try again later."
                }
            
            tata_agents = agents_result.get("users", [])
            logger.info(f"Fetched {len(tata_agents)} Tata agents for matching")
            
            # 4. Smart phone matching
            matched_agent = self._smart_phone_match(user_phone, tata_agents)
            if not matched_agent:
                logger.warning(f"No Tata agent found with phone {user_phone}")
                return {
                    "enabled": False,
                    "sync_status": "no_match",
                    "message": f"No Tata agent found with phone {user_phone}. Please contact admin to set up calling."
                }
            
            logger.info(f"Matched user to Tata agent: {matched_agent.get('agent_name')} (ID: {matched_agent.get('tata_agent_id')})")
            
            # 5. Get agent's extension/DID
            extension_data = await self._get_agent_extension(matched_agent["tata_agent_id"])
            if not extension_data.get("did"):
                logger.warning(f"Agent {matched_agent.get('tata_agent_id')} has no extension/DID")
                return {
                    "enabled": False,
                    "sync_status": "no_extension",
                    "message": "Agent found but no extension/DID available. Please contact admin."
                }
            
            # 6. Create/update mapping
            mapping_success = await self._create_or_update_user_mapping(
                user_id=user_id,
                matched_agent=matched_agent,
                extension_data=extension_data,
                user_phone=user_phone
            )
            
            if not mapping_success:
                return {
                    "enabled": False,
                    "sync_status": "mapping_failed",
                    "message": "Failed to create user mapping. Please contact admin."
                }
            
            # 7. Update user record with calling status
            await self._update_user_calling_status(
                user_id=user_id,
                calling_enabled=True,
                extension=extension_data["did"],
                agent_id=matched_agent["tata_agent_id"]
            )
            
            logger.info(f"✅ Auto-sync completed successfully for {user_email} - Extension: {extension_data['did']}")
            
            return {
                "enabled": True,
                "extension": extension_data["did"],
                "agent_id": matched_agent["tata_agent_id"],
                "sync_status": "synced",
                "message": f"Successfully synced! Calling enabled with extension {extension_data['did']}"
            }
            
        except Exception as e:
            logger.error(f"Auto-sync failed for user {user.get('email', 'unknown')}: {str(e)}")
            return {
                "enabled": False,
                "sync_status": "error",
                "message": f"Auto-sync failed: {str(e)}"
            }

    async def fetch_all_tata_users(self) -> Dict[str, Any]:
        """
        Fetch all Tata agents with pagination support
        Returns all agents available for phone matching
        """
        try:
            all_agents = []
            has_more = True
            last_seen_id = 0
            page_count = 0
            max_pages = 10  # Safety limit
            
            while has_more and page_count < max_pages:
                # Make API call with pagination
                success, response = await self._make_authenticated_request(
                    method="GET",
                    url=f"{self.endpoints['users']}?last_seen_id={last_seen_id}&count=50"
                )
                
                if not success:
                    logger.error(f"Failed to fetch Tata users: {response}")
                    return {
                        "success": False,
                        "message": f"API error: {response.get('message', 'Unknown error')}",
                        "users": []
                    }
                
                # Extract user data
                batch_agents = response.get("data", [])
                if not batch_agents:
                    break
                
                all_agents.extend(batch_agents)
                
                # Check pagination
                has_more = response.get("has_more", False)
                last_seen_id = response.get("last_seen_id", 0)
                page_count += 1
                
                logger.debug(f"Fetched page {page_count}: {len(batch_agents)} agents")
            
            logger.info(f"✅ Fetched total {len(all_agents)} Tata agents across {page_count} pages")
            
            return {
                "success": True,
                "users": all_agents,
                "total_count": len(all_agents),
                "pages_fetched": page_count
            }
            
        except Exception as e:
            logger.error(f"Error fetching all Tata users: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to fetch Tata users: {str(e)}",
                "users": []
            }

    def _smart_phone_match(self, user_phone: str, tata_agents: List[Dict]) -> Optional[Dict]:
        """
        Smart phone number matching between CRM user and Tata agents
        Handles different phone formats and finds best match
        """
        def clean_phone(phone: str) -> str:
            """Clean and normalize phone number for matching"""
            if not phone:
                return ""
            # Remove all non-digit characters
            cleaned = re.sub(r'[^\d]', '', phone)
            # Remove country code if present (assuming +91 for India)
            if cleaned.startswith('91') and len(cleaned) > 10:
                cleaned = cleaned[2:]
            elif cleaned.startswith('0') and len(cleaned) == 11:
                cleaned = cleaned[1:]  # Remove leading 0
            return cleaned
        
        cleaned_user_phone = clean_phone(user_phone)
        if len(cleaned_user_phone) < 10:
            logger.warning(f"User phone number too short after cleaning: {cleaned_user_phone}")
            return None
        
        logger.debug(f"Looking for match for cleaned phone: {cleaned_user_phone}")
        
        for agent in tata_agents:
            try:
                agent_data = agent.get("agent", {})
                
                # Check multiple phone fields in Tata agent data
                phone_fields = [
                    agent_data.get("number"),
                    agent_data.get("follow_me_number"),
                    agent.get("phone"),
                    agent.get("mobile"),
                    agent.get("contact_number")
                ]
                
                for agent_phone in phone_fields:
                    if agent_phone:
                        cleaned_agent_phone = clean_phone(agent_phone)
                        if cleaned_agent_phone == cleaned_user_phone:
                            logger.info(f"📞 Phone match found: {user_phone} ↔ {agent_phone}")
                            return {
                                "tata_user_id": agent.get("id"),
                                "tata_agent_id": agent_data.get("id"),
                                "agent_name": agent.get("name", "Unknown"),
                                "phone": agent_phone,
                                "login_id": agent.get("team_member", {}).get("login_id"),
                                "agent_status": agent_data.get("status"),
                                "follow_me_number": agent_data.get("follow_me_number")
                            }
            
            except Exception as e:
                logger.debug(f"Error processing agent {agent.get('id', 'unknown')}: {str(e)}")
                continue
        
        logger.warning(f"No phone match found for {user_phone} (cleaned: {cleaned_user_phone})")
        return None

    async def _get_agent_extension(self, agent_id: str) -> Dict:
        """
        Get agent's DID from Tata /v1/my_number API
        This provides the extension/caller ID for making calls
        """
        try:
            logger.debug(f"Fetching extension for agent: {agent_id}")
            
            # Use existing auth service to make API call
            success, response = await self._make_authenticated_request("GET", "/v1/my_number")
            
            if not success:
                logger.error(f"Failed to fetch My Numbers: {response}")
                return {}
            
            numbers_data = response if isinstance(response, list) else response.get("data", [])
            
            # Find matching DID for agent
            for number_entry in numbers_data:
                destination = number_entry.get("destination", "")
                # Tata format: "agent||{agent_id}"
                if destination == f"agent||{agent_id}":
                    extension_info = {
                        "did": number_entry.get("did"),
                        "alias": number_entry.get("alias"),
                        "extension_id": number_entry.get("id"),
                        "name": number_entry.get("name"),
                        "destination_name": number_entry.get("destination_name")
                    }
                    logger.info(f"✅ Found extension for agent {agent_id}: {extension_info['did']}")
                    return extension_info
            
            logger.warning(f"No extension found for agent: {agent_id}")
            return {}
            
        except Exception as e:
            logger.error(f"Failed to get extension for agent {agent_id}: {str(e)}")
            return {}

    async def _create_or_update_user_mapping(
        self, 
        user_id: str, 
        matched_agent: Dict, 
        extension_data: Dict,
        user_phone: str
    ) -> bool:
        """
        🔧 FIXED: Create or update user mapping with matched Tata agent data
        """
        try:
            db = self._get_db()
            if db is None:  # 🔧 FIXED: Use 'is None'
                logger.warning("Database not available for mapping creation")
                return False
            
            mapping_data = {
                "crm_user_id": user_id,
                "tata_user_id": matched_agent["tata_user_id"],
                "tata_agent_id": matched_agent["tata_agent_id"],
                "tata_extension": extension_data.get("did"),
                "tata_caller_id": extension_data.get("did"),
                "tata_did_number": extension_data.get("did"),
                "phone_matched": user_phone,
                "sync_method": "auto_login",
                "can_make_calls": True,
                "sync_status": "synced",
                "last_synced": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            # Check if mapping exists
            existing_mapping = await db.tata_user_mappings.find_one({"crm_user_id": user_id})
            
            if existing_mapping:
                # Update existing mapping
                await db.tata_user_mappings.update_one(
                    {"crm_user_id": user_id},
                    {"$set": mapping_data}
                )
                logger.info(f"Updated existing mapping for user {user_id}")
            else:
                # Create new mapping
                mapping_data.update({
                    "created_at": datetime.utcnow(),
                    "created_by": "auto_sync_system",
                    "sync_attempts": 1,
                    "is_active": True,
                    "auto_sync_enabled": True
                })
                
                await db.tata_user_mappings.insert_one(mapping_data)
                logger.info(f"Created new mapping for user {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create/update user mapping: {str(e)}")
            return False

    async def _update_user_calling_status(
        self, 
        user_id: str, 
        calling_enabled: bool, 
        extension: str = None,
        agent_id: str = None
    ) -> bool:
        """
        🔧 FIXED: Update user record with calling status and Tata information
        """
        try:
            db = self._get_db()
            if db is None:  # 🔧 FIXED: Use 'is None'
                logger.warning("Database not available for user status update")
                return False
            
            update_data = {
                "calling_enabled": calling_enabled,
                "tata_sync_status": "synced" if calling_enabled else "failed",
                "last_tata_sync": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            if extension:
                update_data["tata_extension"] = extension
            
            if agent_id:
                update_data["tata_agent_id"] = agent_id
            
            result = await db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                logger.info(f"Updated calling status for user {user_id}: enabled={calling_enabled}")
                return True
            else:
                logger.warning(f"No user updated for ID {user_id}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to update user calling status: {str(e)}")
            return False

    async def get_user_mapping(self, user_id: str) -> Optional[Dict]:
        """
        Get existing user mapping by CRM user ID
        """
        try:
            db = self._get_db()
            if db is None:
                logger.warning("Database not available for user mapping lookup")
                return None
            
            mapping = await db.tata_user_mappings.find_one({"crm_user_id": user_id})
            return mapping
            
        except Exception as e:
            logger.error(f"Error getting user mapping for {user_id}: {str(e)}")
            return None

    # =============================================================================
    # EXISTING METHODS - PRESERVED
    # =============================================================================

    async def _make_authenticated_request(
        self, 
        method: str, 
        url: str, 
        data: Optional[Dict] = None,
        user_id: str = "system"
    ) -> Tuple[bool, Dict[str, Any]]:
        """Make authenticated request to Tata API"""
        try:
            # Get valid token (no parameters needed)
            token = await self.auth_service.get_valid_token()
            if not token:
                logger.error("No valid token available")
                return False, {"error": "Authentication failed", "message": "No valid token available"}
            
            # Make actual HTTP request
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers)
                elif method.upper() == "POST":
                    response = await client.post(url, headers=headers, json=data)
                elif method.upper() == "PUT":
                    response = await client.put(url, headers=headers, json=data)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, headers=headers)
                else:
                    return False, {"error": "Unsupported HTTP method"}
                
                if response.status_code == 200:
                    return True, response.json()
                else:
                    logger.error(f"API request failed: {response.status_code} - {response.text}")
                    return False, {
                        "error": f"API request failed with status {response.status_code}",
                        "message": response.text
                    }
                    
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            return False, {"error": "Request failed", "message": str(e)}
        
    async def _log_sync_event(
        self, 
        event_type: str, 
        status: str, 
        message: str,
        crm_user_id: Optional[str] = None,
        tata_user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log synchronization events for auditing"""
        try:
            db = self._get_db()
            if db is None:  # 🔧 FIXED: Use 'is None'
                logger.warning("Database not available for sync event logging")
                return None
                
            log_entry = TataIntegrationLog(
                event_type=event_type,
                user_id=crm_user_id,
                tata_user_id=tata_user_id,
                status=status,
                message=message,
                metadata=metadata or {}
            )
            
            await db.tata_integration_logs.insert_one(log_entry.dict())
            logger.info(f"Sync event logged: {event_type} - {status}")
        except Exception as e:
            logger.error(f"Failed to log sync event: {str(e)}")

    async def _log_audit_event(
        self,
        operation_type: str,
        crm_user_id: str,
        tata_user_id: Optional[str],
        operation_status: str,
        initiated_by: str,
        changes_made: Optional[Dict[str, Any]] = None,
        error_details: Optional[str] = None
    ):
        """Log detailed audit events"""
        try:
            db = self._get_db()
            if db is None:  # 🔧 FIXED: Use 'is None'
                logger.warning("Database not available for audit event logging")
                return None
                
            audit_log = UserSyncAuditLog(
                operation_type=operation_type,
                crm_user_id=crm_user_id,
                tata_user_id=tata_user_id,
                operation_status=operation_status,
                initiated_by=initiated_by,
                changes_made=changes_made,
                error_details=error_details,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow()
            )
            
            await db.user_sync_audit_logs.insert_one(audit_log.dict())
        except Exception as e:
            logger.error(f"Failed to log audit event: {str(e)}")

    async def validate_user_for_sync(self, crm_user_id: str) -> UserValidationResult:
        """Validate if CRM user can be synced to Tata"""
        try:
            db = self._get_db()
            if db is None:  # 🔧 FIXED: Use 'is None'
                return UserValidationResult(
                    is_valid=False,
                    crm_user_id=crm_user_id,
                    validation_errors=["Database not available"]
                )
                
            # Get CRM user
            user = await db.users.find_one({"_id": ObjectId(crm_user_id)})
            if not user:
                return UserValidationResult(
                    is_valid=False,
                    crm_user_id=crm_user_id,
                    validation_errors=["User not found in CRM"],
                    required_fields=["user_exists"]
                )
            
            validation_errors = []
            validation_warnings = []
            required_fields = []
            suggested_values = {}
            
            # Check required fields
            if not user.get("email"):
                validation_errors.append("Email is required")
                required_fields.append("email")
            
            if not user.get("full_name") and not user.get("name"):
                validation_errors.append("Full name is required")
                required_fields.append("full_name")
            
            # Validate email format
            email = user.get("email")
            if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                validation_errors.append("Invalid email format")
            
            # Check phone number
            phone = user.get("phone") or user.get("phone_number")
            if not phone:
                validation_warnings.append("Phone number is recommended for calling features")
                suggested_values["phone"] = "+91XXXXXXXXXX"
            elif phone:
                # Validate phone format
                cleaned_phone = re.sub(r'[^\d+]', '', phone)
                if len(cleaned_phone) < 10:
                    validation_warnings.append("Phone number seems too short")
            
            # Check if user already has mapping
            existing_mapping = await db.tata_user_mappings.find_one({"crm_user_id": crm_user_id})
            if existing_mapping:
                validation_warnings.append("User already has Tata mapping")
            
            # Check user status
            if not user.get("is_active", True):
                validation_warnings.append("User is inactive in CRM")
            
            is_valid = len(validation_errors) == 0
            can_auto_fix = len(required_fields) == 0 and is_valid
            
            return UserValidationResult(
                is_valid=is_valid,
                crm_user_id=crm_user_id,
                validation_errors=validation_errors,
                validation_warnings=validation_warnings,
                required_fields=required_fields,
                suggested_values=suggested_values,
                can_auto_fix=can_auto_fix
            )
            
        except Exception as e:
            logger.error(f"Error validating user {crm_user_id}: {str(e)}")
            return UserValidationResult(
                is_valid=False,
                crm_user_id=crm_user_id,
                validation_errors=[f"Validation failed: {str(e)}"]
            )
    
    async def _fetch_tata_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Fetch user data from Tata API by email/login_id
        """
        try:
            # Make request to Tata Users API
            success, response = await self._make_authenticated_request(
                method="GET",
                url=self.endpoints["users"],
                user_id="system"
            )
            
            if not success:
                logger.error(f"Failed to fetch Tata users: {response}")
                return None
            
            # Search for user by email/login_id in the response
            users_data = response.get("data", [])
            for user in users_data:
                if (user.get("login_id") == email or 
                    user.get("name", "").lower() == email.split("@")[0].lower()):
                    logger.info(f"Found Tata user: {user.get('id')} - {user.get('name')}")
                    return user
            
            logger.warning(f"User not found in Tata system: {email}")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching Tata user by email {email}: {str(e)}")
            return None
    
    async def _fetch_user_extension(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch user's extension/caller_id from My Numbers API
        """
        try:
            # Make request to My Numbers API
            success, response = await self._make_authenticated_request(
                method="GET",
                url=f"{self.base_url}/v1/my_number",
                user_id="system"
            )
            
            if not success:
                logger.error(f"Failed to fetch My Numbers: {response}")
                return None
            
            # Search for entry where destination matches agent_id
            numbers_data = response if isinstance(response, list) else response.get("data", [])
            
            for number_entry in numbers_data:
                destination = number_entry.get("destination", "")
                # Match pattern: "agent||0506197500004"
                if destination == f"agent||{agent_id}":
                    logger.info(f"Found extension for agent {agent_id}: {number_entry.get('did')}")
                    return {
                        "did": number_entry.get("did"),           # Caller ID number
                        "alias": number_entry.get("alias"),       # Alias
                        "id": number_entry.get("id"),             # Number ID
                        "name": number_entry.get("name"),         # Name
                        "destination_name": number_entry.get("destination_name")
                    }
            
            logger.warning(f"No extension found for agent: {agent_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching extension for agent {agent_id}: {str(e)}")
            return None

    async def create_user_mapping(
        self, 
        mapping_data: Dict[str, Any],
        created_by: str
    ) -> Dict[str, Any]:
        """
        Create a new user mapping between CRM and Tata systems
        NOW WITH AUTO-SYNC TO GET REAL TATA DATA
        """
        try:
            # Use lazy database initialization
            db = self._get_db()
            if db is None:  # 🔧 FIXED: Use 'is None'
                return {"success": False, "message": "Database not available"}

            crm_user_id = mapping_data["crm_user_id"]
            
            # Check if mapping already exists
            existing_mapping = await db.tata_user_mappings.find_one({
                "crm_user_id": crm_user_id
            })
            
            if existing_mapping:
                return {"success": False, "message": "User mapping already exists"}
            
            # Verify CRM user exists
            crm_user = await db.users.find_one({"_id": ObjectId(crm_user_id)})
            if not crm_user:
                return {"success": False, "message": "CRM user not found"}

            # AUTO-FETCH REAL TATA USER DATA
            tata_user_data = await self._fetch_tata_user_by_email(
                email=mapping_data.get("tata_email") or crm_user.get("email")
            )
            
            if not tata_user_data:
                return {
                    "success": False, 
                    "message": "User not found in Tata system. User must be created in Tata first."
                }
            
            # EXTRACT REAL IDS FROM TATA API RESPONSE
            real_tata_user_id = str(tata_user_data.get("id"))
            real_tata_agent_id = tata_user_data.get("agent", {}).get("id")
            
            if not real_tata_agent_id:
                return {
                    "success": False, 
                    "message": "User exists in Tata but has no agent ID assigned"
                }
                
            extension_data = await self._fetch_user_extension(real_tata_agent_id)
            caller_id = extension_data.get("did") if extension_data else None

            # Create mapping document WITH REAL DATA
            mapping_doc = {
                "crm_user_id": crm_user_id,
                "tata_user_id": real_tata_user_id,
                "tata_agent_id": real_tata_agent_id,
                "tata_login_id": tata_user_data.get("login_id"),
                "tata_email": mapping_data.get("tata_email"),
                "tata_phone": tata_user_data.get("agent", {}).get("follow_me_number"),
                "sync_status": "synced",
                "tata_caller_id": caller_id,
                "tata_did_number": caller_id,
                "sync_attempts": 1,
                "is_login_based_calling": tata_user_data.get("is_login_based_calling_enabled", True),
                "is_international_outbound": tata_user_data.get("is_international_outbound_enabled", False),
                "auto_sync_enabled": True,
                "can_make_calls": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "created_by": created_by,
                "last_synced": datetime.utcnow(),
                "is_active": True
            }
            
            # Insert mapping
            result = await db.tata_user_mappings.insert_one(mapping_doc)
            
            # Get the created mapping
            created_mapping = await db.tata_user_mappings.find_one({"_id": result.inserted_id})
            
            # Create response mapping
            response_mapping = {
                "id": str(created_mapping["_id"]),
                
                # CRM user data
                "crm_user_id": str(created_mapping["crm_user_id"]),
                "crm_user_name": crm_user.get("full_name", crm_user.get("email", "Unknown")),
                "crm_user_email": crm_user.get("email", ""),
                "crm_user_role": crm_user.get("role", "user"),
                
                # Tata user data
                "tata_user_id": created_mapping.get("tata_user_id"),
                "tata_agent_id": created_mapping.get("tata_agent_id"),
                "tata_login_id": created_mapping.get("tata_login_id"),
                "tata_email": created_mapping.get("tata_email"),
                "tata_phone": created_mapping.get("tata_phone"),
                "tata_extension": created_mapping.get("tata_extension"),
                
                # Status and configuration
                "sync_status": created_mapping.get("sync_status", "synced"),
                "last_synced": created_mapping.get("last_synced"),
                "sync_attempts": created_mapping.get("sync_attempts", 0),
                "last_sync_error": created_mapping.get("last_sync_error"),
                
                "tata_caller_id": created_mapping.get("tata_caller_id"),
                "tata_did_number": created_mapping.get("tata_did_number"),
                
                # Tata configuration
                "tata_user_type": created_mapping.get("tata_user_type"),
                "tata_role_name": created_mapping.get("tata_role_name"),
                "is_login_based_calling": created_mapping.get("is_login_based_calling", True),
                "is_international_outbound": created_mapping.get("is_international_outbound", False),
                "is_web_login_blocked": created_mapping.get("is_web_login_blocked", False),
                "agent_status": created_mapping.get("agent_status"),
                "agent_status_text": created_mapping.get("agent_status_text"),
                
                # Timestamps
                "created_at": created_mapping.get("created_at"),
                "updated_at": created_mapping.get("updated_at"),
                
                # Flags
                "is_active": created_mapping.get("is_active", True),
                "auto_sync_enabled": created_mapping.get("auto_sync_enabled", True),
                "can_make_calls": created_mapping.get("can_make_calls", True)
            }
            
            logger.info(f"User mapping created successfully for {crm_user_id} with real Tata data")

            return {
                "success": True,
                "message": "User mapping created successfully with real Tata data", 
                "mapping": response_mapping
            }
            
        except Exception as e:
            logger.error(f"Error creating user mapping: {str(e)}", exc_info=True)
            return {"success": False, "message": f"Failed to create mapping: {str(e)}"}

    def _generate_login_id(self, user: Dict[str, Any]) -> str:
        """Generate login ID from user data"""
        try:
            name = user.get("full_name", user.get("name", ""))
            email = user.get("email", "")
            
            # Try to use first part of email
            if email:
                login_id = email.split("@")[0]
            else:
                # Use name with underscores
                login_id = name.lower().replace(" ", "_")
            
            # Clean login ID
            login_id = re.sub(r'[^a-zA-Z0-9_]', '', login_id)
            
            # Ensure it's not too long
            if len(login_id) > 20:
                login_id = login_id[:20]
            
            # Ensure minimum length
            if len(login_id) < 3:
                login_id = f"user_{str(user.get('_id', ''))[:8]}"
            
            return login_id
            
        except Exception as e:
            logger.error(f"Error generating login ID: {str(e)}")
            return f"user_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    async def _create_tata_user(
        self,
        email: str,
        name: str,
        phone: Optional[str] = None,
        login_id: Optional[str] = None,
        designation: Optional[str] = None,
        role_id: Optional[int] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Create user in Tata Tele system"""
        try:
            # Prepare user data for Tata API
            user_data = {
                "create_agent": True,
                "status": True,
                "block_web_login": False,
                "login_based_calling": True,
                "name": name,
                "email": email,
                "login_id": login_id or email.split("@")[0],
                "password": self._generate_temp_password(),
                "user_role": role_id or 54742,  # Default role ID
                "caller_id": [],  # Will be configured later
                "assign_extension": True
            }
            
            if phone:
                user_data["number"] = phone
            
            if designation:
                user_data["designation"] = designation
            
            # Make request to create user
            success, response = await self._make_authenticated_request(
                method="POST",
                url=self.endpoints["create_user"],
                data=user_data
            )
            
            return success, response
            
        except Exception as e:
            logger.error(f"Error creating Tata user: {str(e)}")
            return False, {"error": str(e)}

    def _generate_temp_password(self) -> str:
        """Generate temporary password for new Tata users"""
        import secrets
        import string
        
        # Generate secure random password
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for _ in range(12))
        return password

    async def sync_user_to_tata(
        self, 
        crm_user_id: str,
        current_user: Dict[str, Any],
        force_sync: bool = False
    ) -> UserSyncResult:
        """Sync single user to Tata system"""
        try:
            db = self._get_db()
            if db is None:  # 🔧 FIXED: Use 'is None'
                return UserSyncResult(
                    crm_user_id=crm_user_id,
                    sync_status=SyncStatus.FAILED,
                    error_message="Database not available"
                )
                
            initiated_by = str(current_user.get("user_id") or current_user.get("_id"))
            start_time = datetime.utcnow()
            
            # Get CRM user
            crm_user = await db.users.find_one({"_id": ObjectId(crm_user_id)})
            if not crm_user:
                return UserSyncResult(
                    crm_user_id=crm_user_id,
                    sync_status=SyncStatus.FAILED,
                    error_message="CRM user not found"
                )
            
            user_name = crm_user.get("full_name", crm_user.get("name", "Unknown"))
            
            # Check existing mapping
            existing_mapping = await db.tata_user_mappings.find_one({"crm_user_id": crm_user_id})
            
            if existing_mapping and not force_sync:
                if existing_mapping.get("sync_status") == SyncStatus.SYNCED.value:
                    return UserSyncResult(
                        crm_user_id=crm_user_id,
                        user_name=user_name,
                        sync_status=SyncStatus.SYNCED,
                        tata_user_id=existing_mapping.get("tata_user_id"),
                        tata_agent_id=existing_mapping.get("tata_agent_id"),
                        error_message="User already synced (use force_sync to re-sync)",
                        actions_taken=["skipped_existing"]
                    )
            
            # Validate user
            validation = await self.validate_user_for_sync(crm_user_id)
            if not validation.is_valid:
                return UserSyncResult(
                    crm_user_id=crm_user_id,
                    user_name=user_name,
                    sync_status=SyncStatus.FAILED,
                    error_message=f"Validation failed: {', '.join(validation.validation_errors)}",
                    actions_taken=["validation_failed"]
                )
            
            actions_taken = []
            tata_user_id = None
            tata_agent_id = None
            
            try:
                if existing_mapping:
                    # Update existing mapping
                    tata_user_id = existing_mapping.get("tata_user_id")
                    tata_agent_id = existing_mapping.get("tata_agent_id")
                    
                    if tata_user_id:
                        # Update user in Tata
                        success, response = await self._update_tata_user(
                            tata_user_id,
                            crm_user
                        )
                        if success:
                            actions_taken.append("updated_tata_user")
                        else:
                            actions_taken.append("update_failed")
                    else:
                        # Create user in Tata
                        success, response = await self._create_tata_user(
                            email=crm_user.get("email"),
                            name=user_name,
                            phone=crm_user.get("phone", crm_user.get("phone_number")),
                            login_id=existing_mapping.get("tata_login_id")
                        )
                        if success:
                            tata_user_id = response.get("user_id")
                            tata_agent_id = f"agent_{tata_user_id}"
                            actions_taken.append("created_tata_user")
                    
                    # Update mapping
                    await db.tata_user_mappings.update_one(
                        {"crm_user_id": crm_user_id},
                        {
                            "$set": {
                                "tata_user_id": tata_user_id,
                                "tata_agent_id": tata_agent_id,
                                "sync_status": SyncStatus.SYNCED.value,
                                "last_synced": datetime.utcnow(),
                                "updated_at": datetime.utcnow(),
                                "sync_attempts": existing_mapping.get("sync_attempts", 0) + 1
                            }
                        }
                    )
                    actions_taken.append("updated_mapping")
                    
                else:
                    # Create new mapping and Tata user
                    success, response = await self._create_tata_user(
                        email=crm_user.get("email"),
                        name=user_name,
                        phone=crm_user.get("phone", crm_user.get("phone_number")),
                        login_id=self._generate_login_id(crm_user)
                    )
                    
                    if success:
                        tata_user_id = response.get("user_id")
                        tata_agent_id = f"agent_{tata_user_id}"
                        actions_taken.append("created_tata_user")
                        
                        # Create mapping
                        mapping = TataUserMapping(
                            crm_user_id=crm_user_id,
                            tata_user_id=tata_user_id,
                            tata_agent_id=tata_agent_id,
                            tata_login_id=self._generate_login_id(crm_user),
                            tata_email=crm_user.get("email"),
                            tata_phone=crm_user.get("phone", crm_user.get("phone_number")),
                            sync_status=SyncStatus.SYNCED,
                            last_synced=datetime.utcnow(),
                            sync_attempts=1
                        )
                        
                        await db.tata_user_mappings.insert_one(mapping.dict())
                        actions_taken.append("created_mapping")
                    else:
                        actions_taken.append("create_user_failed")
                        raise Exception(f"Failed to create Tata user: {response.get('message')}")
                
                # Log successful sync
                await self._log_sync_event(
                    event_type="user_sync_success",
                    status="success",
                    message=f"User {user_name} synced successfully",
                    crm_user_id=crm_user_id,
                    tata_user_id=tata_user_id
                )
                
                end_time = datetime.utcnow()
                sync_duration = (end_time - start_time).total_seconds()
                
                return UserSyncResult(
                    crm_user_id=crm_user_id,
                    user_name=user_name,
                    sync_status=SyncStatus.SYNCED,
                    tata_user_id=tata_user_id,
                    tata_agent_id=tata_agent_id,
                    actions_taken=actions_taken,
                    sync_duration=sync_duration
                )
                
            except Exception as sync_error:
                # Update sync status to failed
                if existing_mapping:
                    await db.tata_user_mappings.update_one(
                        {"crm_user_id": crm_user_id},
                        {
                            "$set": {
                                "sync_status": SyncStatus.FAILED.value,
                                "last_sync_error": str(sync_error),
                                "updated_at": datetime.utcnow(),
                                "sync_attempts": existing_mapping.get("sync_attempts", 0) + 1
                            }
                        }
                    )
                
                await self._log_sync_event(
                    event_type="user_sync_failed",
                    status="failure",
                    message=f"User sync failed: {str(sync_error)}",
                    crm_user_id=crm_user_id
                )
                
                return UserSyncResult(
                    crm_user_id=crm_user_id,
                    user_name=user_name,
                    sync_status=SyncStatus.FAILED,
                    error_message=str(sync_error),
                    actions_taken=actions_taken
                )
                
        except Exception as e:
            logger.error(f"Error syncing user {crm_user_id}: {str(e)}")
            return UserSyncResult(
                crm_user_id=crm_user_id,
                sync_status=SyncStatus.FAILED,
                error_message=str(e)
            )

    async def _update_tata_user(
        self,
        tata_user_id: str,
        crm_user: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """Update existing user in Tata system"""
        try:
            # Prepare update data
            update_data = {
                "name": crm_user.get("full_name", crm_user.get("name")),
                "email": crm_user.get("email")
            }
            
            phone = crm_user.get("phone", crm_user.get("phone_number"))
            if phone:
                update_data["number"] = phone
            
            # Make update request
            success, response = await self._make_authenticated_request(
                method="PATCH",
                url=f"{self.endpoints['update_user']}/{tata_user_id}",
                data=update_data
            )
            
            return success, response
            
        except Exception as e:
            logger.error(f"Error updating Tata user {tata_user_id}: {str(e)}")
            return False, {"error": str(e)}

    async def bulk_sync_users(
        self,
        bulk_request: BulkUserSyncRequest,
        current_user: Dict[str, Any]
    ) -> BulkUserSyncResponse:
        """Sync multiple users in bulk"""
        try:
            db = self._get_db()
            if db is None:  # 🔧 FIXED: Use 'is None'
                return BulkUserSyncResponse(
                    total_requested=0,
                    successful=0,
                    failed=1,
                    skipped=0,
                    created_new=0,
                    updated_existing=0,
                    results=[],
                    summary_message="Database not available",
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    total_duration=0
                )
                
            started_at = datetime.utcnow()
            initiated_by = str(current_user.get("user_id") or current_user.get("_id"))
            
            # Get user IDs to sync
            if bulk_request.user_ids:
                user_ids = bulk_request.user_ids
            else:
                # Get all active CRM users
                users_cursor = db.users.find(
                    {"is_active": {"$ne": False}},
                    {"_id": 1}
                )
                user_docs = await users_cursor.to_list(length=None)
                user_ids = [str(doc["_id"]) for doc in user_docs]
            
            # Limit batch size
            if len(user_ids) > self.max_sync_batch_size:
                user_ids = user_ids[:self.max_sync_batch_size]
            
            # Track results
            results = []
            successful = 0
            failed = 0
            skipped = 0
            created_new = 0
            updated_existing = 0
            
            # Process users in batches
            for user_id in user_ids:
                try:
                    sync_result = await self.sync_user_to_tata(
                        crm_user_id=user_id,
                        current_user=current_user,
                        force_sync=bulk_request.force_sync
                    )
                    
                    results.append(sync_result)
                    
                    if sync_result.sync_status == SyncStatus.SYNCED:
                        successful += 1
                        if "created_tata_user" in sync_result.actions_taken:
                            created_new += 1
                        elif "updated_tata_user" in sync_result.actions_taken:
                            updated_existing += 1
                    elif sync_result.sync_status == SyncStatus.FAILED:
                        failed += 1
                    else:
                        skipped += 1
                        
                    # Add small delay to avoid overwhelming the API
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    failed += 1
                    results.append(UserSyncResult(
                        crm_user_id=user_id,
                        sync_status=SyncStatus.FAILED,
                        error_message=str(e)
                    ))
            
            completed_at = datetime.utcnow()
            total_duration = (completed_at - started_at).total_seconds()
            
            # Log bulk operation
            await self._log_sync_event(
                event_type="bulk_user_sync",
                status="completed",
                message=f"Bulk sync completed: {successful} successful, {failed} failed, {skipped} skipped",
                metadata={
                    "total_requested": len(user_ids),
                    "successful": successful,
                    "failed": failed,
                    "skipped": skipped,
                    "duration": total_duration
                }
            )
            
            return BulkUserSyncResponse(
                total_requested=len(user_ids),
                successful=successful,
                failed=failed,
                skipped=skipped,
                created_new=created_new,
                updated_existing=updated_existing,
                results=results,
                summary_message=f"Bulk sync completed: {successful}/{len(user_ids)} successful",
                started_at=started_at,
                completed_at=completed_at,
                total_duration=total_duration
            )
            
        except Exception as e:
            error_msg = f"Bulk sync error: {str(e)}"
            logger.error(error_msg)
            await self._log_sync_event(
                    event_type="bulk_user_sync_error",
                    status="error",
                    message=error_msg
                )
            return BulkUserSyncResponse(
                total_requested=0,
                successful=0,
                failed=1,
                skipped=0,
                created_new=0,
                updated_existing=0,
                results=[],
                summary_message=f"Bulk sync failed: {str(e)}",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                total_duration=0
            )

    async def sync_single_user(
        self, 
        crm_user_id: str, 
        initiated_by: str
    ) -> Dict[str, Any]:
        """
        Synchronize a single user with Tata system
        """
        try:
            # Use lazy database initialization
            db = self._get_db()
            if db is None:  # 🔧 FIXED: Use 'is None'
                return {"success": False, "message": "Database not available"}
            
            # Check if CRM user exists
            crm_user = await db.users.find_one({"_id": ObjectId(crm_user_id)})
            if not crm_user:
                return {"success": False, "message": "CRM user not found"}
            
            # Check if mapping already exists
            existing_mapping = await db.tata_user_mappings.find_one({
                "crm_user_id": crm_user_id
            })
            
            if existing_mapping:
                # Update existing mapping
                result = await db.tata_user_mappings.update_one(
                    {"_id": existing_mapping["_id"]},
                    {
                        "$set": {
                            "last_synced": datetime.utcnow(),
                            "updated_at": datetime.utcnow(),
                            "sync_attempts": existing_mapping.get("sync_attempts", 0) + 1,
                            "sync_status": "synced"
                        }
                    }
                )
                
                return {
                    "success": True,
                    "message": "User mapping updated successfully",
                    "sync_status": "updated",
                    "tata_user_id": existing_mapping.get("tata_user_id"),
                    "mapping_id": existing_mapping["_id"]
                }
            else:
                # Create new mapping using existing method
                mapping_data = {
                    "crm_user_id": crm_user_id,
                    "tata_login_id": crm_user.get("email"),
                    "tata_email": crm_user.get("email"),
                    "tata_phone": crm_user.get("phone", ""),
                    "auto_create_agent": True
                }
                
                result = await self.create_user_mapping(
                    mapping_data=mapping_data,
                    created_by=initiated_by
                )
                
                if result["success"]:
                    return {
                        "success": True,
                        "message": "User synced and mapping created",
                        "sync_status": "created",
                        "mapping_id": result["mapping"]["id"]
                    }
                else:
                    return result
            
        except Exception as e:
            logger.error(f"Error syncing user {crm_user_id}: {str(e)}", exc_info=True)
            return {"success": False, "message": f"Failed to sync user: {str(e)}"}
    
    async def get_user_mappings(
        self, 
        limit: int = 50, 
        offset: int = 0, 
        sync_status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get user mappings with pagination and filtering
        """
        try:
            db = self._get_db()
            if db is None:  # 🔧 FIXED: Use 'is None'
                logger.warning("Database not available for user mappings")
                return []
            
            # Build query
            query = {}
            if sync_status:
                query["sync_status"] = sync_status
            
            # Get mappings from database
            cursor = db.tata_user_mappings.find(query).skip(offset).limit(limit)
            mappings = []
            
            async for mapping in cursor:
                # Convert to response format matching TataUserMappingResponse model
                response_mapping = {
                    "id": str(mapping["_id"]),  # Change _id to id
                    "crm_user_id": str(mapping["crm_user_id"]),
                    "tata_user_id": mapping.get("tata_user_id"),
                    "tata_agent_id": mapping.get("tata_agent_id"),
                    "tata_login_id": mapping.get("tata_login_id"),
                    "tata_email": mapping.get("tata_email"),
                    "tata_phone": mapping.get("tata_phone"),
                    "tata_extension": mapping.get("tata_extension"),
                    "tata_caller_id": mapping.get("tata_caller_id"),
                    "tata_did_number": mapping.get("tata_did_number"),
                    "sync_status": mapping.get("sync_status", "pending"),
                    "last_synced": mapping.get("last_synced"),
                    "sync_attempts": mapping.get("sync_attempts", 0),
                    "last_sync_error": mapping.get("last_sync_error"),
                    "tata_user_type": mapping.get("tata_user_type"),
                    "tata_role_id": mapping.get("tata_role_id"),
                    "tata_role_name": mapping.get("tata_role_name"),
                    "is_login_based_calling": mapping.get("is_login_based_calling", True),
                    "is_international_outbound": mapping.get("is_international_outbound", False),
                    "is_web_login_blocked": mapping.get("is_web_login_blocked", False),
                    "agent_intercom": mapping.get("agent_intercom"),
                    "agent_status": mapping.get("agent_status"),
                    "agent_status_text": mapping.get("agent_status_text"),
                    "created_at": mapping.get("created_at"),
                    "updated_at": mapping.get("updated_at"),
                    "is_active": mapping.get("is_active", True),
                    "auto_sync_enabled": mapping.get("auto_sync_enabled", True),
                    "can_make_calls": mapping.get("can_make_calls", True)
                }
                
                # Get CRM user details
                if "crm_user_id" in mapping:
                    try:
                        crm_user = await db.users.find_one({"_id": ObjectId(mapping["crm_user_id"])})
                        if crm_user:
                            response_mapping["crm_user_name"] = crm_user.get("full_name", crm_user.get("email", "Unknown"))
                            response_mapping["crm_user_email"] = crm_user.get("email", "")
                            response_mapping["crm_user_role"] = crm_user.get("role", "user")
                        else:
                            response_mapping["crm_user_name"] = "Unknown"
                            response_mapping["crm_user_email"] = ""
                            response_mapping["crm_user_role"] = "user"
                    except:
                        response_mapping["crm_user_name"] = "Unknown"
                        response_mapping["crm_user_email"] = ""
                        response_mapping["crm_user_role"] = "user"
                
                mappings.append(response_mapping)
            
            logger.info(f"Retrieved {len(mappings)} user mappings")
            return mappings
            
        except Exception as e:
            logger.error(f"Error fetching user mappings: {str(e)}", exc_info=True)
            raise Exception(f"Failed to fetch user mappings: {str(e)}")

# Create singleton instance
tata_user_service = TataUserService()