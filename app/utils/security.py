
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from passlib.context import CryptContext
from ..config.settings import settings
from ..config.database import get_database
import uuid
import logging

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

    async def blacklist_token(self, token_jti: str, expires_at: datetime):
        """Add token to blacklist"""
        try:
            db = get_database()
            await db.token_blacklist.insert_one({
                "token_jti": token_jti,
                "expires_at": expires_at,
                "blacklisted_at": datetime.utcnow()
            })
            logger.info(f"Token {token_jti} blacklisted successfully")
        except Exception as e:
            logger.error(f"Failed to blacklist token: {e}")

# Global security manager instance
security = SecurityManager()

# Utility functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return security.verify_password(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return security.get_password_hash(password)

def create_access_token(data: Dict[str, Any]) -> str:
    return security.create_access_token(data)

def create_refresh_token(data: Dict[str, Any]) -> str:
    return security.create_refresh_token(data)