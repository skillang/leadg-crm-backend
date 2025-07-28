# app/services/tata_auth_service.py - FIXED with lazy database initialization
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import httpx
from cryptography.fernet import Fernet
import json

from ..config.settings import get_settings
from ..config.database import get_database  # Import but don't call immediately

logger = logging.getLogger(__name__)

class TataAuthService:
    """
    Tata Tele Authentication Service
    Handles JWT token management, encryption, and API authentication
    """
    
    def __init__(self):
        """Initialize service without database connection"""
        self.settings = get_settings()
        self.db = None  # 🔧 FIX: Don't initialize database here
        self.cipher_suite = None
        self.base_url = self.settings.tata_api_base_url
        self.timeout = self.settings.tata_api_timeout or 30
        self.retries = self.settings.tata_api_retries
        
        # Initialize encryption if key is available
        if self.settings.tata_encryption_key:
            try:
                key = self.settings.tata_encryption_key.encode()
                if len(key) == 32:  # Fernet requires 32-byte key
                    self.cipher_suite = Fernet(Fernet.generate_key())
                else:
                    # Convert to proper Fernet key
                    from cryptography.hazmat.primitives import hashes
                    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
                    import base64
                    
                    kdf = PBKDF2HMAC(
                        algorithm=hashes.SHA256(),
                        length=32,
                        salt=b'leadg_tata_salt',
                        iterations=100000,
                    )
                    key = base64.urlsafe_b64encode(kdf.derive(key))
                    self.cipher_suite = Fernet(key)
                    
            except Exception as e:
                logger.warning(f"Failed to initialize encryption: {e}")
                self.cipher_suite = None
    
    def _get_db(self):
        """🔧 FIX: Lazy database initialization"""
        if self.db is None:
            try:
                self.db = get_database()
            except RuntimeError:
                # Database not initialized yet, return None
                return None
        return self.db
    
    def _encrypt_token(self, token: str) -> str:
        """Encrypt token for secure storage"""
        if not self.cipher_suite:
            return token  # Store unencrypted if no cipher
        
        try:
            return self.cipher_suite.encrypt(token.encode()).decode()
        except Exception as e:
            logger.warning(f"Failed to encrypt token: {e}")
            return token
    
    def _decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt token from storage"""
        if not self.cipher_suite:
            return encrypted_token  # Return as-is if no cipher
        
        try:
            return self.cipher_suite.decrypt(encrypted_token.encode()).decode()
        except Exception as e:
            logger.warning(f"Failed to decrypt token: {e}")
            return encrypted_token



    async def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Login to Tata Tele API and store encrypted tokens
        """
        try:
            logger.info(f"Attempting Tata login for email: {email}")
            
            # 🔧 FIX: Check database availability
            db = self._get_db()
            if db is None:
                return {
                    "success": False,
                    "message": "Database not available yet. Please try again."
                }
            
            login_payload = {
                "email": email,
                "password": password
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/auth/login",
                    json=login_payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    access_token = data.get("access_token")
                    
                    if access_token:
                        # Calculate expiry time
                        expires_at = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
                        
                        # Encrypt and store token
                        encrypted_token = self._encrypt_token(access_token)
                        
                        # Store in database
                        token_doc = {
                            "user_id": "system",  # System-wide token
                            "access_token": encrypted_token,
                            "expires_at": expires_at,
                            "created_at": datetime.utcnow()
                        }
                        
                        # Upsert token document
                        await db.tata_tokens.update_one(
                            {"user_id": "system"},
                            {"$set": token_doc},
                            upsert=True
                        )
                        
                        # Log successful login
                        await self._log_event("login", "success", "Tata login successful")
                        
                        logger.info("Tata login successful")
                        return {
                                "success": data.get("success", True),
                                "access_token": access_token,  # Return actual token
                                "token_type": data.get("token_type", "bearer"),
                                "expires_in": data.get("expires_in", 3600),  # ← CORRECT: Model expects this
                                "number_of_days_left": data.get("number_of_days_left")
                        }
                    else:
                        await self._log_event("login", "error", "No access token in response")
                        return {
                            "success": False,
                            "message": "No access token received"
                        }
                else:
                    error_msg = f"Login failed with status {response.status_code}"
                    await self._log_event("login", "error", error_msg)
                    logger.warning(error_msg)
                    return {
                        "success": False,
                        "message": error_msg
                    }
                    
        except httpx.TimeoutException:
            error_msg = "Tata API timeout during login"
            await self._log_event("login", "error", error_msg)
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
        except Exception as e:
            error_msg = f"Login error: {str(e)}"
            await self._log_event("login", "error", error_msg)
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "message": error_msg
            }



    async def get_valid_token(self) -> Optional[str]:
        """
        Get a valid access token, refreshing if necessary
        """
        try:
            # 🔧 FIX: Check database availability
            db = self._get_db()
            if db is None:
                logger.warning("Database not available for token retrieval")
                return None
            
            # Find stored token
            token_doc = await db.tata_tokens.find_one({"user_id": "system"})
            
            if not token_doc:
                logger.warning("No stored Tata token found")
                return None
            
            # Check if token is expired or expiring soon (5 minute buffer)
            expires_at = token_doc.get("expires_at")
            if expires_at and expires_at <= datetime.utcnow() + timedelta(minutes=5):
                logger.info("Token expired or expiring soon, refresh needed")
                refresh_result = await self.refresh_token()
                if not refresh_result["success"]:
                    return None
                # Get the refreshed token
                token_doc = await db.tata_tokens.find_one({"user_id": "system"})
                if not token_doc:
                    return None
            
            # Decrypt and return token
            encrypted_token = token_doc.get("access_token")
            if encrypted_token:
                return self._decrypt_token(encrypted_token)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting valid token: {e}")
            return None
    
    async def refresh_token(self) -> Dict[str, Any]:
        """
        Refresh the access token
        """
        try:
            # 🔧 FIX: Check database availability
            db = self._get_db()
            if db is None:
                return {
                    "success": False,
                    "message": "Database not available yet. Please try again."
                }
            
            # For now, we'll implement a simple re-login
            # In a real implementation, you'd use the refresh token endpoint
            logger.info("Token refresh requested - implementing re-login")
            
            # Get stored credentials (if available)
            # For security, we don't store passwords, so this would need to be handled differently
            # For now, return failure requiring manual login
            
            return {
                "success": False,
                "message": "Token refresh requires manual re-login"
            }
            
        except Exception as e:
            error_msg = f"Token refresh error: {str(e)}"
            await self._log_event("refresh", "error", error_msg)
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "message": error_msg
            }
    
    async def logout(self) -> Dict[str, Any]:
        """
        Logout from Tata API and clear stored tokens
        """
        try:
            # 🔧 FIX: Check database availability
            db = self._get_db()
            if db is None:
                return {
                    "success": False,
                    "message": "Database not available yet. Please try again."
                }
            
            # Get current token for API logout
            current_token = await self.get_valid_token()
            
            # Call API logout if we have a token
            if current_token:
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        await client.post(
                            f"{self.base_url}/auth/logout",
                            headers={
                                "Authorization": f"Bearer {current_token}",
                                "Content-Type": "application/json"
                            }
                        )
                except Exception as e:
                    logger.warning(f"API logout failed: {e}")
            
            # Clear stored token
            await db.tata_tokens.delete_many({"user_id": "system"})
            
            # Log logout
            await self._log_event("logout", "success", "Tata logout successful")
            
            logger.info("Tata logout successful")
            return {
                "success": True,
                "message": "Logout successful"
            }
            
        except Exception as e:
            error_msg = f"Logout error: {str(e)}"
            await self._log_event("logout", "error", error_msg)
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "message": error_msg
            }
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status of Tata integration"""
        try:
            db = self._get_db()
            if db is None:
                return {
                    "is_authenticated": False,
                    "token_valid": False,
                    "api_connectivity": False,
                    "tata_api_status": "disconnected",
                    "integration_status": "failed",
                    "health_score": 0,
                    "total_api_calls": 0,
                    "failed_calls_24h": 0
                }
            
            health_status = {
                "is_authenticated": False,
                "token_valid": False,
                "api_connectivity": False,
                "tata_api_status": "disconnected",
                "integration_status": "disconnected",
                "health_score": 0,
                "total_api_calls": 0,
                "failed_calls_24h": 0
            }
            
            # Check if we have a valid token
            token = await self.get_valid_token()
            if token:
                health_status["is_authenticated"] = True
                health_status["token_valid"] = True
                health_status["health_score"] += 40
                
                # Test API connectivity with actual token
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        response = await client.get(
                            f"{self.base_url}/users",
                            headers={"Authorization": f"Bearer {token}"}
                        )
                        if response.status_code == 200:
                            health_status["api_connectivity"] = True
                            health_status["tata_api_status"] = "connected"
                            health_status["health_score"] += 30
                        else:
                            health_status["tata_api_status"] = "error"
                except Exception as e:
                    health_status["tata_api_status"] = "timeout"
                    logger.warning(f"API connectivity test failed: {e}")
            
            # Get integration statistics
            try:
                logs_count = await db.tata_integration_logs.count_documents({})
                health_status["total_api_calls"] = logs_count
                
                # Count failed calls in last 24 hours
                yesterday = datetime.utcnow() - timedelta(days=1)
                failed_count = await db.tata_integration_logs.count_documents({
                    "status": "error",
                    "timestamp": {"$gte": yesterday}
                })
                health_status["failed_calls_24h"] = failed_count
                health_status["health_score"] += 30
            except Exception as e:
                logger.warning(f"Failed to get integration statistics: {e}")
            
            # Determine overall integration status using correct enum values
            if health_status["health_score"] >= 80:
                health_status["integration_status"] = "synced"
            elif health_status["health_score"] >= 50:
                health_status["integration_status"] = "pending"
            else:
                health_status["integration_status"] = "failed"
            
            return health_status
            
        except Exception as e:
            logger.error(f"Error checking health status: {e}")
            return {
                "is_authenticated": False,
                "token_valid": False,
                "api_connectivity": False,
                "tata_api_status": "error",
                "integration_status": "failed",
                "health_score": 0,
                "total_api_calls": 0,
                "failed_calls_24h": 0
            }


    async def check_token_status(self) -> Dict[str, Any]:
        """
        Check current token status for debugging
        """
        try:
            # 🔧 FIX: Check database availability
            db = self._get_db()
            if db is None:
                return {
                    "has_token": False,
                    "token_expired": True,
                    "needs_refresh": True,
                    "error": "Database not available"
                }
            
            token_doc = await db.tata_tokens.find_one({"user_id": "system"})
            
            if not token_doc:
                return {
                    "has_token": False,
                    "token_expired": True,
                    "needs_refresh": True
                }
            
            expires_at = token_doc.get("expires_at")
            now = datetime.utcnow()
            
            token_expired = expires_at <= now if expires_at else True
            needs_refresh = expires_at <= now + timedelta(minutes=5) if expires_at else True
            
            time_until_expiry = None
            if expires_at:
                time_until_expiry = max(0, (expires_at - now).total_seconds())
            
            return {
                "has_token": True,
                "token_expired": token_expired,
                "expires_at": expires_at,
                "time_until_expiry": time_until_expiry,
                "needs_refresh": needs_refresh
            }
            
        except Exception as e:
            logger.error(f"Error checking token status: {e}")
            return {
                "has_token": False,
                "token_expired": True,
                "needs_refresh": True,
                "error": str(e)
            }
    
    async def _log_event(self, event_type: str, status: str, message: str):
        """
        Log integration events
        """
        try:
            # 🔧 FIX: Check database availability
            db = self._get_db()
            if db is None:
                # If database not available, just log to console
                logger.info(f"Tata Event: {event_type} - {status} - {message}")
                return
            
            log_doc = {
                "event_type": event_type,
                "status": status,
                "message": message,
                "timestamp": datetime.utcnow()
            }
            
            await db.tata_integration_logs.insert_one(log_doc)
            
        except Exception as e:
            logger.warning(f"Failed to log event: {e}")

# 🔧 FIX: Create instance without immediate database connection
tata_auth_service = TataAuthService()