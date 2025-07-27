# app/services/tata_auth_service.py
# Tata Tele Authentication Service
# Handles all authentication operations with Tata Tele API

import httpx
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from cryptography.fernet import Fernet
import base64
import json

from ..config.database import get_database
from ..config.settings import get_settings
from ..models.tata_integration import (
    TataLoginRequest, TataLoginResponse, TataLoginFailedResponse,
    TataRefreshTokenResponse, TataLogoutResponse, TataTokenStorage,
    TataIntegrationHealth, TataIntegrationLog, IntegrationStatus
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TataAuthService:
    """
    Comprehensive Tata Tele Authentication Service
    Handles login, token management, refresh, logout, and health monitoring
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.db = get_database()
        self.base_url = self.settings.TATA_API_BASE_URL
        self.timeout = self.settings.TATA_API_TIMEOUT or 30
        self.retry_attempts = self.settings.TATA_API_RETRIES or 3
        
        # Initialize encryption for token storage
        self._init_encryption()
        
        # API endpoints
        self.endpoints = {
            "login": f"{self.base_url}/v1/auth/login",
            "refresh": f"{self.base_url}/v1/auth/refresh", 
            "logout": f"{self.base_url}/v1/auth/logout"
        }

    def _init_encryption(self):
        """Initialize encryption for secure token storage"""
        try:
            # Use a key from settings or generate one (in production, use a secure key)
            encryption_key = getattr(self.settings, 'TATA_ENCRYPTION_KEY', None)
            if not encryption_key:
                # Generate a key (in production, store this securely)
                encryption_key = Fernet.generate_key()
                logger.warning("Generated new encryption key. In production, use a secure stored key.")
            
            if isinstance(encryption_key, str):
                encryption_key = encryption_key.encode()
            
            self.cipher = Fernet(encryption_key)
            logger.info("Encryption initialized for token storage")
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {str(e)}")
            # Fallback to no encryption (not recommended for production)
            self.cipher = None

    def _encrypt_token(self, token: str) -> str:
        """Encrypt token for secure storage"""
        if not self.cipher:
            return token
        try:
            encrypted = self.cipher.encrypt(token.encode())
            return base64.b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Token encryption failed: {str(e)}")
            return token

    def _decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt token from storage"""
        if not self.cipher:
            return encrypted_token
        try:
            decoded = base64.b64decode(encrypted_token.encode())
            decrypted = self.cipher.decrypt(decoded)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Token decryption failed: {str(e)}")
            return encrypted_token

    async def _make_request(
        self, 
        method: str, 
        url: str, 
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        auth_token: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Make HTTP request to Tata API with retry logic and error handling
        """
        if headers is None:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
        
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        for attempt in range(self.retry_attempts):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    logger.info(f"Making {method} request to {url} (attempt {attempt + 1})")
                    
                    if method.upper() == "POST":
                        response = await client.post(url, json=data, headers=headers)
                    elif method.upper() == "GET":
                        response = await client.get(url, headers=headers)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")
                    
                    # Log response details
                    logger.info(f"Response status: {response.status_code}")
                    
                    # Parse response
                    try:
                        response_data = response.json()
                    except json.JSONDecodeError:
                        response_data = {"message": response.text}
                    
                    # Check if request was successful
                    if response.status_code == 200:
                        return True, response_data
                    else:
                        logger.warning(f"Request failed with status {response.status_code}: {response_data}")
                        return False, response_data
                        
            except httpx.TimeoutException:
                logger.warning(f"Request timeout (attempt {attempt + 1})")
                if attempt == self.retry_attempts - 1:
                    return False, {"error": "Request timeout", "message": "API request timed out"}
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
            except httpx.RequestError as e:
                logger.error(f"Request error (attempt {attempt + 1}): {str(e)}")
                if attempt == self.retry_attempts - 1:
                    return False, {"error": "Connection error", "message": str(e)}
                await asyncio.sleep(2 ** attempt)
                
            except Exception as e:
                logger.error(f"Unexpected error (attempt {attempt + 1}): {str(e)}")
                if attempt == self.retry_attempts - 1:
                    return False, {"error": "Unexpected error", "message": str(e)}
                await asyncio.sleep(2 ** attempt)

        return False, {"error": "Max retries exceeded", "message": "Failed after all retry attempts"}

    async def _log_integration_event(
        self, 
        event_type: str, 
        status: str, 
        message: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log integration events for auditing and monitoring"""
        try:
            log_entry = TataIntegrationLog(
                event_type=event_type,
                user_id=user_id,
                status=status,
                message=message,
                metadata=metadata or {}
            )
            
            await self.db.tata_integration_logs.insert_one(log_entry.dict())
            logger.info(f"Integration event logged: {event_type} - {status}")
        except Exception as e:
            logger.error(f"Failed to log integration event: {str(e)}")

    async def login_to_tata(self, email: str, password: str, user_id: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Login to Tata Tele API and store encrypted tokens
        
        Args:
            email: Tata Tele login email
            password: Tata Tele password  
            user_id: Optional CRM user ID for token association
            
        Returns:
            Tuple of (success: bool, response_data: dict)
        """
        try:
            # Prepare login request
            login_request = TataLoginRequest(email=email, password=password)
            
            # Make login request
            success, response_data = await self._make_request(
                method="POST",
                url=self.endpoints["login"],
                data=login_request.dict()
            )
            
            if not success:
                await self._log_integration_event(
                    event_type="tata_login",
                    status="failure",
                    message=f"Login failed: {response_data.get('message', 'Unknown error')}",
                    user_id=user_id,
                    metadata={"email": email, "error": response_data}
                )
                return False, response_data
            
            # Validate response structure
            if not response_data.get("success"):
                # Handle failed login response
                failed_response = TataLoginFailedResponse(**response_data)
                await self._log_integration_event(
                    event_type="tata_login",
                    status="failure", 
                    message=failed_response.message,
                    user_id=user_id,
                    metadata={"email": email, "login_failed_count": failed_response.login_failed_count}
                )
                return False, failed_response.dict()
            
            # Parse successful login response
            login_response = TataLoginResponse(**response_data)
            
            # Store encrypted token in database
            token_storage = TataTokenStorage(
                user_id=user_id or "system",
                access_token=self._encrypt_token(login_response.access_token),
                token_type=login_response.token_type,
                expires_in=login_response.expires_in,
                expires_at=datetime.utcnow() + timedelta(seconds=login_response.expires_in),
                created_at=datetime.utcnow()
            )
            
            # Upsert token (update if exists, insert if new)
            await self.db.tata_tokens.update_one(
                {"user_id": token_storage.user_id},
                {"$set": token_storage.dict()},
                upsert=True
            )
            
            # Log successful login
            await self._log_integration_event(
                event_type="tata_login",
                status="success",
                message="Successfully logged in to Tata Tele",
                user_id=user_id,
                metadata={
                    "email": email,
                    "expires_in": login_response.expires_in,
                    "days_left": login_response.number_of_days_left
                }
            )
            
            logger.info(f"Successfully logged in to Tata Tele for user: {user_id or 'system'}")
            
            # Return response without sensitive token
            safe_response = login_response.dict()
            safe_response["access_token"] = "***STORED_SECURELY***"
            
            return True, safe_response
            
        except Exception as e:
            error_msg = f"Login error: {str(e)}"
            logger.error(error_msg)
            
            await self._log_integration_event(
                event_type="tata_login",
                status="error",
                message=error_msg,
                user_id=user_id,
                metadata={"email": email, "exception": str(e)}
            )
            
            return False, {"error": "Login failed", "message": error_msg}

    async def refresh_tata_token(self, user_id: str = "system") -> Tuple[bool, Dict[str, Any]]:
        """
        Refresh Tata Tele access token
        
        Args:
            user_id: CRM user ID (defaults to "system")
            
        Returns:
            Tuple of (success: bool, response_data: dict)
        """
        try:
            # Get current token from database
            token_doc = await self.db.tata_tokens.find_one({"user_id": user_id})
            if not token_doc:
                return False, {"error": "No token found", "message": "No stored token found for user"}
            
            # Decrypt token
            current_token = self._decrypt_token(token_doc["access_token"])
            
            # Make refresh request
            success, response_data = await self._make_request(
                method="POST",
                url=self.endpoints["refresh"],
                auth_token=current_token
            )
            
            if not success:
                await self._log_integration_event(
                    event_type="tata_token_refresh",
                    status="failure",
                    message=f"Token refresh failed: {response_data.get('message', 'Unknown error')}",
                    user_id=user_id,
                    metadata={"error": response_data}
                )
                return False, response_data
            
            # Validate response
            if not response_data.get("success"):
                return False, response_data
            
            # Parse refresh response
            refresh_response = TataRefreshTokenResponse(**response_data)
            
            # Update stored token
            updated_token = TataTokenStorage(
                user_id=user_id,
                access_token=self._encrypt_token(refresh_response.access_token),
                token_type=refresh_response.token_type,
                expires_in=refresh_response.expires_in,
                expires_at=datetime.utcnow() + timedelta(seconds=refresh_response.expires_in),
                created_at=token_doc.get("created_at", datetime.utcnow()),
                last_refreshed=datetime.utcnow()
            )
            
            await self.db.tata_tokens.update_one(
                {"user_id": user_id},
                {"$set": updated_token.dict()}
            )
            
            # Log successful refresh
            await self._log_integration_event(
                event_type="tata_token_refresh", 
                status="success",
                message="Token successfully refreshed",
                user_id=user_id,
                metadata={"expires_in": refresh_response.expires_in}
            )
            
            logger.info(f"Successfully refreshed Tata token for user: {user_id}")
            
            # Return safe response
            safe_response = refresh_response.dict()
            safe_response["access_token"] = "***REFRESHED_AND_STORED***"
            
            return True, safe_response
            
        except Exception as e:
            error_msg = f"Token refresh error: {str(e)}"
            logger.error(error_msg)
            
            await self._log_integration_event(
                event_type="tata_token_refresh",
                status="error", 
                message=error_msg,
                user_id=user_id,
                metadata={"exception": str(e)}
            )
            
            return False, {"error": "Refresh failed", "message": error_msg}

    async def logout_from_tata(self, user_id: str = "system") -> Tuple[bool, Dict[str, Any]]:
        """
        Logout from Tata Tele API and clean up stored tokens
        
        Args:
            user_id: CRM user ID (defaults to "system")
            
        Returns:
            Tuple of (success: bool, response_data: dict)
        """
        try:
            # Get current token
            token_doc = await self.db.tata_tokens.find_one({"user_id": user_id})
            if not token_doc:
                return True, {"success": True, "message": "No token to logout"}
            
            # Decrypt token
            current_token = self._decrypt_token(token_doc["access_token"])
            
            # Make logout request
            success, response_data = await self._make_request(
                method="POST",
                url=self.endpoints["logout"],
                auth_token=current_token
            )
            
            # Clean up stored token regardless of API response
            await self.db.tata_tokens.delete_one({"user_id": user_id})
            
            if success and response_data.get("success"):
                logout_response = TataLogoutResponse(**response_data)
                
                await self._log_integration_event(
                    event_type="tata_logout",
                    status="success",
                    message="Successfully logged out from Tata Tele",
                    user_id=user_id
                )
                
                logger.info(f"Successfully logged out from Tata Tele for user: {user_id}")
                return True, logout_response.dict()
            else:
                # Even if API logout failed, we cleaned up local token
                await self._log_integration_event(
                    event_type="tata_logout",
                    status="partial",
                    message="Local token cleaned up, API logout may have failed",
                    user_id=user_id,
                    metadata={"api_response": response_data}
                )
                
                return True, {"success": True, "message": "Token cleaned up locally"}
                
        except Exception as e:
            error_msg = f"Logout error: {str(e)}"
            logger.error(error_msg)
            
            # Still try to clean up local token
            try:
                await self.db.tata_tokens.delete_one({"user_id": user_id})
            except:
                pass
            
            await self._log_integration_event(
                event_type="tata_logout",
                status="error",
                message=error_msg,
                user_id=user_id,
                metadata={"exception": str(e)}
            )
            
            return False, {"error": "Logout error", "message": error_msg}

    async def get_valid_token(self, user_id: str = "system") -> Optional[str]:
        """
        Get a valid Tata token, refreshing if necessary
        
        Args:
            user_id: CRM user ID (defaults to "system")
            
        Returns:
            Valid access token or None if unable to get/refresh
        """
        try:
            # Get stored token
            token_doc = await self.db.tata_tokens.find_one({"user_id": user_id})
            if not token_doc:
                logger.warning(f"No stored token found for user: {user_id}")
                return None
            
            # Check if token is still valid (with 5 minute buffer)
            expires_at = token_doc.get("expires_at")
            if expires_at and expires_at > datetime.utcnow() + timedelta(minutes=5):
                # Token is still valid
                return self._decrypt_token(token_doc["access_token"])
            
            # Token is expired or expiring soon, try to refresh
            logger.info(f"Token expiring soon for user {user_id}, attempting refresh")
            success, _ = await self.refresh_tata_token(user_id)
            
            if success:
                # Get the refreshed token
                refreshed_token_doc = await self.db.tata_tokens.find_one({"user_id": user_id})
                if refreshed_token_doc:
                    return self._decrypt_token(refreshed_token_doc["access_token"])
            
            logger.error(f"Failed to refresh token for user: {user_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting valid token for user {user_id}: {str(e)}")
            return None

    async def validate_token(self, user_id: str = "system") -> bool:
        """
        Validate if stored token is still valid
        
        Args:
            user_id: CRM user ID (defaults to "system")
            
        Returns:
            True if token is valid, False otherwise
        """
        token = await self.get_valid_token(user_id)
        return token is not None

    async def get_integration_health(self) -> TataIntegrationHealth:
        """
        Get comprehensive health status of Tata integration
        
        Returns:
            TataIntegrationHealth object with current status
        """
        try:
            # Check API connectivity
            api_status = "healthy"
            token_valid = False
            last_sync = None
            users_synced = 0
            error_message = None
            
            # Test API connectivity with a simple request
            try:
                success, _ = await self._make_request("GET", f"{self.base_url}/health", timeout=10)
                if not success:
                    api_status = "degraded"
            except:
                api_status = "unhealthy"
            
            # Check if we have a valid token
            token_valid = await self.validate_token()
            
            # Get last sync timestamp from logs
            try:
                last_log = await self.db.tata_integration_logs.find_one(
                    {"event_type": "tata_login", "status": "success"},
                    sort=[("timestamp", -1)]
                )
                if last_log:
                    last_sync = last_log.get("timestamp")
            except:
                pass
            
            # Count synced users (this will be implemented when user service is ready)
            try:
                users_synced = await self.db.tata_user_mappings.count_documents({"sync_status": "synced"})
            except:
                users_synced = 0
            
            # Determine overall integration status
            if api_status == "healthy" and token_valid:
                integration_status = IntegrationStatus.SYNCED
            elif api_status == "degraded" or not token_valid:
                integration_status = IntegrationStatus.PARTIAL
                error_message = "API connectivity issues or invalid token"
            else:
                integration_status = IntegrationStatus.FAILED
                error_message = "API unhealthy and no valid token"
            
            return TataIntegrationHealth(
                tata_api_status=api_status,
                token_valid=token_valid,
                last_sync=last_sync,
                users_synced=users_synced,
                integration_status=integration_status,
                error_message=error_message
            )
            
        except Exception as e:
            logger.error(f"Error checking integration health: {str(e)}")
            return TataIntegrationHealth(
                tata_api_status="unknown",
                token_valid=False,
                integration_status=IntegrationStatus.FAILED,
                error_message=f"Health check failed: {str(e)}"
            )

    async def cleanup_expired_tokens(self):
        """Clean up expired tokens from database"""
        try:
            result = await self.db.tata_tokens.delete_many({
                "expires_at": {"$lt": datetime.utcnow()}
            })
            
            if result.deleted_count > 0:
                logger.info(f"Cleaned up {result.deleted_count} expired tokens")
                
                await self._log_integration_event(
                    event_type="token_cleanup",
                    status="success",
                    message=f"Cleaned up {result.deleted_count} expired tokens"
                )
                
        except Exception as e:
            logger.error(f"Error cleaning up expired tokens: {str(e)}")

# Create singleton instance
tata_auth_service = TataAuthService()