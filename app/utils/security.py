from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from passlib.context import CryptContext
from ..config.settings import settings
from ..config.database import get_database
import uuid
import logging
from bson import ObjectId

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class SecurityManager:
    def __init__(self):
        self.secret_key = settings.secret_key
        self.algorithm = settings.algorithm
        self.access_token_expire_minutes = settings.access_token_expire_minutes
        self.refresh_token_expire_days = settings.refresh_token_expire_days

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False

    def get_password_hash(self, password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)

    def create_access_token(self, data: Dict[str, Any]) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        
        # Add standard JWT claims
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": str(uuid.uuid4()),  # Unique token ID for blacklisting
            "type": "access"
        })
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def create_refresh_token(self, data: Dict[str, Any], expire_days: int = None) -> str:
        """Create JWT refresh token with optional custom expiry"""
        to_encode = data.copy()
        
        # Use custom expiry or default
        days = expire_days or self.refresh_token_expire_days
        expire = datetime.utcnow() + timedelta(days=days)
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": str(uuid.uuid4()),
            "type": "refresh"
        })
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.InvalidTokenError as e:
            logger.error(f"Token verification failed: {e}")
            return None

    async def is_token_blacklisted(self, token_jti: str) -> bool:
        """Check if token is blacklisted"""
        try:
            db = get_database()
            result = await db.token_blacklist.find_one({"token_jti": token_jti})
            return result is not None
        except Exception as e:
            logger.error(f"Error checking token blacklist: {e}")
            return True  # Fail safe - treat as blacklisted

    async def blacklist_token(self, token_jti: str, expires_at: datetime = None):
        """Add token to blacklist"""
        try:
            db = get_database()
            
            # If expires_at not provided, set a default (7 days from now)
            if expires_at is None:
                expires_at = datetime.utcnow() + timedelta(days=7)
            
            await db.token_blacklist.insert_one({
                "token_jti": token_jti,
                "expires_at": expires_at,
                "blacklisted_at": datetime.utcnow()
            })
            logger.info(f"Token {token_jti} blacklisted successfully")
        except Exception as e:
            logger.error(f"Failed to blacklist token: {e}")




    # 🆕 NEW: Enhanced user fetching with permissions
    async def get_user_with_permissions(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user from database with permissions included
        Ensures backward compatibility by adding default permissions if missing
        """
        try:
            db = get_database()
            user_data = await db.users.find_one({"_id": ObjectId(user_id)})
            
            if user_data is None:
                return None
            
            # 🆕 NEW: Ensure permissions field exists for backward compatibility
            if "permissions" not in user_data:
                # Add default permissions
                default_permissions = {
                    "can_create_single_lead": False,
                    "can_create_bulk_leads": False,
                    "granted_by": None,
                    "granted_at": None,
                    "last_modified_by": None,
                    "last_modified_at": None
                }
                
                # Update user in database with default permissions
                await db.users.update_one(
                    {"_id": ObjectId(user_id)},
                    {"$set": {"permissions": default_permissions}}
                )
                
                # Add to current user data
                user_data["permissions"] = default_permissions
                
                logger.info(f"Added default permissions for user {user_data.get('email')}")
            
            # Convert ObjectId to string for JSON serialization
            user_data["_id"] = str(user_data["_id"])
            
            return user_data
            
        except Exception as e:
            logger.error(f"Error fetching user with permissions: {e}")
            return None

    # 🆕 NEW: Update user permissions
    async def update_user_permissions(
        self, 
        user_email: str, 
        permissions: Dict[str, Any], 
        admin_email: str
    ) -> bool:
        """
        Update user permissions in database
        Used by permission management service
        """
        try:
            db = get_database()
            
            update_data = {
                "permissions.can_create_single_lead": permissions.get("can_create_single_lead", False),
                "permissions.can_create_bulk_leads": permissions.get("can_create_bulk_leads", False),
                "permissions.last_modified_by": admin_email,
                "permissions.last_modified_at": datetime.utcnow()
            }
            
            # Set granted_by and granted_at only if granting new permissions
            if permissions.get("can_create_single_lead") or permissions.get("can_create_bulk_leads"):
                # Check if user already has granted_by set
                user = await db.users.find_one({"email": user_email})
                if user and not user.get("permissions", {}).get("granted_by"):
                    update_data["permissions.granted_by"] = admin_email
                    update_data["permissions.granted_at"] = datetime.utcnow()
            
            result = await db.users.update_one(
                {"email": user_email},
                {"$set": update_data}
            )
            
            success = result.modified_count > 0
            if success:
                logger.info(f"Updated permissions for {user_email} by {admin_email}")
            else:
                logger.warning(f"No user found or no changes made for {user_email}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error updating user permissions: {e}")
            return False

    # 🆕 NEW: Get users with permissions for admin interface
    async def get_all_users_with_permissions(self) -> list:
        """
        Get all active users with their permissions for admin management interface
        """
        try:
            db = get_database()
            
            cursor = db.users.find(
                {"is_active": True},
                {
                    "email": 1,
                    "first_name": 1,
                    "last_name": 1,
                    "role": 1,
                    "permissions": 1,
                    "created_at": 1,
                    "last_login": 1
                }
            )
            
            users = await cursor.to_list(None)
            
            # Ensure all users have permissions field
            for user in users:
                if "permissions" not in user:
                    user["permissions"] = {
                        "can_create_single_lead": False,
                        "can_create_bulk_leads": False,
                        "granted_by": None,
                        "granted_at": None,
                        "last_modified_by": None,
                        "last_modified_at": None
                    }
                
                # Convert ObjectId to string
                user["_id"] = str(user["_id"])
            
            return users
            
        except Exception as e:
            logger.error(f"Error fetching users with permissions: {e}")
            return []

# Global security manager instance
security = SecurityManager()

# Utility functions (keeping existing + adding new)
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return security.verify_password(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return security.get_password_hash(password)

def create_access_token(data: Dict[str, Any]) -> str:
    return security.create_access_token(data)

def create_refresh_token(data: Dict[str, Any]) -> str:
    return security.create_refresh_token(data)

# 🆕 NEW: Permission-related utility functions
async def get_user_with_permissions(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user with permissions included"""
    return await security.get_user_with_permissions(user_id)

async def update_user_permissions(user_email: str, permissions: Dict[str, Any], admin_email: str) -> bool:
    """Update user permissions"""
    return await security.update_user_permissions(user_email, permissions, admin_email)

async def get_all_users_with_permissions() -> list:
    """Get all users with permissions for admin interface"""
    return await security.get_all_users_with_permissions()

# 🆕 NEW: Permission checking utilities
def check_user_has_permission(user_data: Dict[str, Any], permission_name: str) -> bool:
    """
    Check if user has specific permission
    
    Args:
        user_data: User data from database
        permission_name: Permission to check (e.g., 'can_create_single_lead')
    
    Returns:
        bool: True if user has permission
    """
    # Admins always have all permissions
    if user_data.get("role") == "admin":
        return True
    
    # Check user permissions
    permissions = user_data.get("permissions", {})
    return permissions.get(permission_name, False)

def get_user_permission_summary(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get summary of user's permissions for UI display
    
    Args:
        user_data: User data from database
        
    Returns:
        dict: Permission summary
    """
    role = user_data.get("role")
    permissions = user_data.get("permissions", {})
    
    if role == "admin":
        return {
            "is_admin": True,
            "can_create_single_lead": True,
            "can_create_bulk_leads": True,
            "can_manage_permissions": True,
            "permission_source": "admin_role"
        }
    
    return {
        "is_admin": False,
        "can_create_single_lead": permissions.get("can_create_single_lead", False),
        "can_create_bulk_leads": permissions.get("can_create_bulk_leads", False),
        "can_manage_permissions": False,
        "permission_source": "user_permissions",
        "granted_by": permissions.get("granted_by"),
        "granted_at": permissions.get("granted_at")
    }