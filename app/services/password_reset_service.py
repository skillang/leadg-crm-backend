# app/services/password_reset_service.py
# Password Reset Service for LeadG CRM - FIXED VERSION
# Handles both user self-service and admin-initiated password resets

import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import logging
from bson import ObjectId

from ..config.database import get_database
from ..config.settings import settings
from ..utils.security import SecurityManager, get_password_hash, verify_password
from ..services.zepto_client import zepto_client
from ..models.password_reset import (
    ResetTokenType, ResetTokenStatus, ResetMethod,
    PasswordResetToken, ForgotPasswordResponse, ResetPasswordResponse,
    AdminResetPasswordResponse, ValidateResetTokenResponse, PasswordResetStats
)

logger = logging.getLogger(__name__)

class PasswordResetService:
    """Password Reset Service with comprehensive security and email integration"""
    
    def __init__(self):
        self.security = SecurityManager()
        self.db = None
        
        # 🔧 FIXED: Use your actual ZeptoMail template ID
        self.template_id = "2518b.3027c48fe4ab851b.k1.44ad7230-859e-11f0-a35a-cabf48e1bf81.198fafcc0d3"
        self.sender_email = "noreply@skillang.com"
        
        # Password reset configuration
        self.reset_token_expire_minutes = 30  # 30 minutes for user tokens
        self.admin_token_expire_hours = 24    # 24 hours for admin tokens
        self.max_attempts_per_day = 5         # Max reset attempts per user per day
        self.cleanup_expired_hours = 48       # Clean up expired tokens after 48 hours
        
        logger.info(f"Password Reset Service initialized with template ID: {self.template_id}")
        
    def _get_db(self):
        """Lazy database initialization"""
        if self.db is None:
            self.db = get_database()
        return self.db
    
    def _generate_secure_token(self) -> str:
        """Generate cryptographically secure token"""
        return secrets.token_urlsafe(32)
    
    def _hash_token(self, token: str) -> str:
        """Hash token for secure storage"""
        return hashlib.sha256(token.encode()).hexdigest()
    
    async def _get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email address"""
        try:
            db = self._get_db()
            user = await db.users.find_one({
                "email": email.lower(),
                "is_active": True
            })
            return user
        except Exception as e:
            logger.error(f"Error fetching user by email {email}: {e}")
            return None
    
    async def _check_rate_limit(self, user_id: str, ip_address: str = None) -> bool:
        """Check if user has exceeded reset rate limit"""
        try:
            db = self._get_db()
            
            # Check attempts in last 24 hours
            since = datetime.utcnow() - timedelta(hours=24)
            
            query = {
                "user_id": user_id,
                "created_at": {"$gte": since}
            }
            
            # Also check by IP if provided
            if ip_address:
                ip_query = {
                    "ip_address": ip_address,
                    "created_at": {"$gte": since}
                }
                ip_count = await db.password_reset_tokens.count_documents(ip_query)
                if ip_count >= self.max_attempts_per_day * 2:  # More lenient for IP
                    logger.warning(f"Rate limit exceeded for IP {ip_address}")
                    return False
            
            attempts = await db.password_reset_tokens.count_documents(query)
            
            if attempts >= self.max_attempts_per_day:
                logger.warning(f"Rate limit exceeded for user {user_id}: {attempts} attempts")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return True  # Allow on error to avoid blocking users
    
    async def _store_reset_token(
        self, 
        token: str, 
        user_id: str, 
        user_email: str,
        token_type: ResetTokenType,
        expires_in_minutes: int,
        created_by: str = None,
        reset_method: ResetMethod = None,
        force_change: bool = False,
        notification_message: str = None,
        ip_address: str = None,
        user_agent: str = None
    ) -> bool:
        """Store password reset token in database"""
        try:
            db = self._get_db()
            
            # Hash the token for storage
            hashed_token = self._hash_token(token)
            
            # Create token document
            token_doc = {
                "token": hashed_token,
                "user_id": user_id,
                "user_email": user_email.lower(),
                "token_type": token_type,
                "status": ResetTokenStatus.ACTIVE,
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(minutes=expires_in_minutes),
                "created_by": created_by,
                "ip_address": ip_address,
                "user_agent": user_agent
            }
            
            # Add admin-specific fields
            if token_type == ResetTokenType.ADMIN_INITIATED:
                token_doc.update({
                    "reset_method": reset_method,
                    "force_change_on_login": force_change,
                    "notification_message": notification_message
                })
            
            # Insert token
            result = await db.password_reset_tokens.insert_one(token_doc)
            
            logger.info(f"Reset token stored for user {user_email} (type: {token_type})")
            return bool(result.inserted_id)
            
        except Exception as e:
            logger.error(f"Error storing reset token: {e}")
            return False
    
    async def _send_reset_email(
            self, 
            user_email: str, 
            user_name: str, 
            reset_token: str,
            token_type: ResetTokenType,
            created_by: str = None,
            notification_message: str = None
        ) -> bool:
            """Send password reset email using ZeptoMail - SIMPLIFIED VERSION"""
            try:
                # Build reset link
                reset_link = f"https://leadg.in/reset-password?token={reset_token}"
                
                # Calculate expiration time based on token type
                if token_type == ResetTokenType.USER_INITIATED:
                    expires_in = self.reset_token_expire_minutes
                else:  # ADMIN_INITIATED
                    expires_in = self.admin_token_expire_hours * 60  # Convert hours to minutes
                
                # 🔧 SIMPLIFIED: Only send variables that template expects
                merge_data = {
                    "username": user_name,
                    "reset_link": reset_link,
                    "expires_in": str(expires_in)
                }
                
                logger.debug(f"Sending email with merge data: {merge_data}")
                
                # Send email using ZeptoMail with CORRECT template ID
                result = await zepto_client.send_template_email(
                    template_key=self.template_id,
                    sender_email=self.sender_email,
                    recipient_email=user_email,
                    recipient_name=user_name,
                    merge_data=merge_data
                )
                
                if result.get("success"):
                    logger.info(f"Password reset email sent to {user_email} (type: {token_type})")
                    return True
                else:
                    logger.error(f"Failed to send password reset email to {user_email}: {result}")
                    return False
                    
            except Exception as e:
                logger.error(f"Error sending password reset email to {user_email}: {e}")
                return False


    async def forgot_password(
        self, 
        email: str, 
        ip_address: str = None, 
        user_agent: str = None
    ) -> ForgotPasswordResponse:
        """Handle user-initiated forgot password request"""
        try:
            # Normalize email
            email = email.lower().strip()
            
            # Get user by email
            user = await self._get_user_by_email(email)
            
            # Always return success message to prevent email enumeration
            success_message = "If your email is registered, you will receive a password reset link shortly."
            
            if not user:
                logger.info(f"Password reset requested for non-existent email: {email}")
                return ForgotPasswordResponse(
                    success=True,
                    message=success_message,
                    email_sent=False
                )
            
            user_id = str(user["_id"])
            user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get("username", email)
            
            # Check rate limiting
            if not await self._check_rate_limit(user_id, ip_address):
                return ForgotPasswordResponse(
                    success=False,
                    message="Too many password reset attempts. Please try again later.",
                    email_sent=False
                )
            
            # Revoke any existing active tokens for this user
            await self._revoke_user_tokens(user_id)
            
            # Generate secure token
            reset_token = self._generate_secure_token()
            
            # Store token in database
            token_stored = await self._store_reset_token(
                token=reset_token,
                user_id=user_id,
                user_email=email,
                token_type=ResetTokenType.USER_INITIATED,
                expires_in_minutes=self.reset_token_expire_minutes,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            if not token_stored:
                logger.error(f"Failed to store reset token for user {email}")
                return ForgotPasswordResponse(
                    success=False,
                    message="An error occurred while processing your request. Please try again.",
                    email_sent=False
                )
            
            # Send email
            email_sent = await self._send_reset_email(
                user_email=email,
                user_name=user_name,
                reset_token=reset_token,
                token_type=ResetTokenType.USER_INITIATED
            )
            
            # Log the attempt
            logger.info(f"Password reset initiated by user {email} from IP {ip_address}")
            
            return ForgotPasswordResponse(
                success=True,
                message=success_message,
                email_sent=email_sent,
                token_expires_in=self.reset_token_expire_minutes
            )
            
        except Exception as e:
            logger.error(f"Error in forgot password for {email}: {e}")
            return ForgotPasswordResponse(
                success=False,
                message="An unexpected error occurred. Please try again later.",
                email_sent=False
            )
    
    async def _revoke_user_tokens(self, user_id: str):
        """Revoke all active tokens for a user"""
        try:
            db = self._get_db()
            await db.password_reset_tokens.update_many(
                {
                    "user_id": user_id,
                    "status": ResetTokenStatus.ACTIVE
                },
                {
                    "$set": {
                        "status": ResetTokenStatus.REVOKED,
                        "revoked_at": datetime.utcnow()
                    }
                }
            )
            logger.debug(f"Revoked existing tokens for user {user_id}")
        except Exception as e:
            logger.error(f"Error revoking user tokens: {e}")
    
    async def validate_reset_token(self, token: str) -> ValidateResetTokenResponse:
        """Validate a password reset token"""
        try:
            if not token:
                return ValidateResetTokenResponse(
                    valid=False,
                    message="Reset token is required"
                )
            
            # Hash the token to match stored version
            hashed_token = self._hash_token(token)
            
            db = self._get_db()
            token_doc = await db.password_reset_tokens.find_one({
                "token": hashed_token,
                "status": ResetTokenStatus.ACTIVE
            })
            
            if not token_doc:
                return ValidateResetTokenResponse(
                    valid=False,
                    message="Invalid or expired reset token"
                )
            
            # Check expiration
            if datetime.utcnow() > token_doc["expires_at"]:
                # Mark as expired
                await db.password_reset_tokens.update_one(
                    {"_id": token_doc["_id"]},
                    {"$set": {"status": ResetTokenStatus.EXPIRED}}
                )
                return ValidateResetTokenResponse(
                    valid=False,
                    message="Reset token has expired"
                )
            
            # Calculate remaining time
            expires_at = token_doc["expires_at"]
            remaining_time = expires_at - datetime.utcnow()
            minutes_remaining = int(remaining_time.total_seconds() / 60)
            
            return ValidateResetTokenResponse(
                valid=True,
                token_type=token_doc["token_type"],
                user_email=token_doc["user_email"],
                expires_at=expires_at,
                expires_in_minutes=minutes_remaining,
                message="Token is valid"
            )
            
        except Exception as e:
            logger.error(f"Error validating reset token: {e}")
            return ValidateResetTokenResponse(
                valid=False,
                message="An error occurred while validating the token"
            )
    
    async def reset_password(
        self, 
        token: str, 
        new_password: str,
        ip_address: str = None
    ) -> ResetPasswordResponse:
        """Reset password using valid token"""
        try:
            # Validate token first
            validation = await self.validate_reset_token(token)
            if not validation.valid:
                return ResetPasswordResponse(
                    success=False,
                    message=validation.message,
                    requires_login=False
                )
            
            # Get token document and user
            hashed_token = self._hash_token(token)
            db = self._get_db()
            
            token_doc = await db.password_reset_tokens.find_one({
                "token": hashed_token,
                "status": ResetTokenStatus.ACTIVE
            })
            
            if not token_doc:
                return ResetPasswordResponse(
                    success=False,
                    message="Invalid reset token",
                    requires_login=False
                )
            
            user_id = token_doc["user_id"]
            user_email = token_doc["user_email"]
            
            # Get user document
            user = await db.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return ResetPasswordResponse(
                    success=False,
                    message="User not found",
                    requires_login=False
                )
            
            # Hash new password
            new_password_hash = get_password_hash(new_password)
            
            # Update user password
            update_data = {
                "hashed_password": new_password_hash,
                "password_changed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            # If admin-initiated, set force change flag
            if (token_doc["token_type"] == ResetTokenType.ADMIN_INITIATED and 
                token_doc.get("force_change_on_login")):
                update_data["must_change_password"] = True
            
            user_update = await db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": update_data}
            )
            
            if user_update.modified_count == 0:
                return ResetPasswordResponse(
                    success=False,
                    message="Failed to update password",
                    requires_login=False
                )
            
            # Mark token as used
            await db.password_reset_tokens.update_one(
                {"_id": token_doc["_id"]},
                {
                    "$set": {
                        "status": ResetTokenStatus.USED,
                        "used_at": datetime.utcnow(),
                        "used_from_ip": ip_address
                    }
                }
            )
            
            # Revoke any other active tokens for this user
            await self._revoke_user_tokens(user_id)
            
            # Log successful reset
            reset_type = "admin-initiated" if token_doc["token_type"] == ResetTokenType.ADMIN_INITIATED else "user-initiated"
            logger.info(f"Password successfully reset for {user_email} ({reset_type}) from IP {ip_address}")
            
            return ResetPasswordResponse(
                success=True,
                message="Password reset successfully. Please login with your new password.",
                user_email=user_email,
                requires_login=True
            )
            
        except Exception as e:
            logger.error(f"Error resetting password: {e}")
            return ResetPasswordResponse(
                success=False,
                message="An unexpected error occurred. Please try again.",
                requires_login=False
            )
    
    async def admin_reset_password(
        self,
        admin_email: str,
        target_user_email: str,
        reset_method: ResetMethod,
        temporary_password: str = None,
        force_change_on_login: bool = True,
        notification_message: str = None
    ) -> AdminResetPasswordResponse:
        """Admin-initiated password reset"""
        try:
            # Get target user
            target_user = await self._get_user_by_email(target_user_email)
            if not target_user:
                return AdminResetPasswordResponse(
                    success=False,
                    message="Target user not found",
                    user_email=target_user_email,
                    reset_method=reset_method,
                    force_change_on_login=force_change_on_login,
                    reset_by=admin_email,
                    reset_at=datetime.utcnow()
                )
            
            target_user_id = str(target_user["_id"])
            target_user_name = f"{target_user.get('first_name', '')} {target_user.get('last_name', '')}".strip() or target_user.get("username", target_user_email)
            
            db = self._get_db()
            
            if reset_method == ResetMethod.ADMIN_TEMPORARY:
                # Direct password reset with temporary password
                if not temporary_password:
                    return AdminResetPasswordResponse(
                        success=False,
                        message="Temporary password is required for this reset method",
                        user_email=target_user_email,
                        reset_method=reset_method,
                        force_change_on_login=force_change_on_login,
                        reset_by=admin_email,
                        reset_at=datetime.utcnow()
                    )
                
                # Update user password directly
                temp_password_hash = get_password_hash(temporary_password)
                update_data = {
                    "hashed_password": temp_password_hash,
                    "password_changed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "password_reset_by": admin_email,
                    "must_change_password": force_change_on_login
                }
                
                await db.users.update_one(
                    {"_id": ObjectId(target_user_id)},
                    {"$set": update_data}
                )
                
                logger.info(f"Admin {admin_email} set temporary password for {target_user_email}")
                
                return AdminResetPasswordResponse(
                    success=True,
                    message="Temporary password set successfully",
                    user_email=target_user_email,
                    reset_method=reset_method,
                    temporary_password=temporary_password,
                    force_change_on_login=force_change_on_login,
                    reset_by=admin_email,
                    reset_at=datetime.utcnow()
                )
                
            else:  # EMAIL_LINK method
                # Revoke existing tokens
                await self._revoke_user_tokens(target_user_id)
                
                # Generate reset token
                reset_token = self._generate_secure_token()
                
                # Store token
                token_stored = await self._store_reset_token(
                    token=reset_token,
                    user_id=target_user_id,
                    user_email=target_user_email,
                    token_type=ResetTokenType.ADMIN_INITIATED,
                    expires_in_minutes=self.admin_token_expire_hours * 60,
                    created_by=admin_email,
                    reset_method=reset_method,
                    force_change=force_change_on_login,
                    notification_message=notification_message
                )
                
                if not token_stored:
                    return AdminResetPasswordResponse(
                        success=False,
                        message="Failed to create reset token",
                        user_email=target_user_email,
                        reset_method=reset_method,
                        force_change_on_login=force_change_on_login,
                        reset_by=admin_email,
                        reset_at=datetime.utcnow()
                    )
                
                # Send email
                email_sent = await self._send_reset_email(
                    user_email=target_user_email,
                    user_name=target_user_name,
                    reset_token=reset_token,
                    token_type=ResetTokenType.ADMIN_INITIATED,
                    created_by=admin_email,
                    notification_message=notification_message
                )
                
                logger.info(f"Admin {admin_email} initiated password reset for {target_user_email}")
                
                return AdminResetPasswordResponse(
                    success=True,
                    message="Password reset email sent successfully",
                    user_email=target_user_email,
                    reset_method=reset_method,
                    email_sent=email_sent,
                    force_change_on_login=force_change_on_login,
                    reset_by=admin_email,
                    reset_at=datetime.utcnow()
                )
            
        except Exception as e:
            logger.error(f"Error in admin password reset: {e}")
            return AdminResetPasswordResponse(
                success=False,
                message=f"An unexpected error occurred: {str(e)}",
                user_email=target_user_email,
                reset_method=reset_method,
                force_change_on_login=force_change_on_login,
                reset_by=admin_email,
                reset_at=datetime.utcnow()
            )
    
    async def get_reset_statistics(self) -> PasswordResetStats:
        """Get password reset statistics for admin dashboard"""
        try:
            db = self._get_db()
            now = datetime.utcnow()
            
            # Date ranges
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=7)
            month_start = today_start - timedelta(days=30)
            
            # Aggregate stats
            stats = PasswordResetStats()
            
            # Today's requests
            stats.total_requests_today = await db.password_reset_tokens.count_documents({
                "created_at": {"$gte": today_start}
            })
            
            # This week
            stats.total_requests_this_week = await db.password_reset_tokens.count_documents({
                "created_at": {"$gte": week_start}
            })
            
            # This month
            stats.total_requests_this_month = await db.password_reset_tokens.count_documents({
                "created_at": {"$gte": month_start}
            })
            
            # Successful resets today
            stats.successful_resets_today = await db.password_reset_tokens.count_documents({
                "created_at": {"$gte": today_start},
                "status": ResetTokenStatus.USED
            })
            
            # Token status counts
            stats.pending_tokens = await db.password_reset_tokens.count_documents({
                "status": ResetTokenStatus.ACTIVE,
                "expires_at": {"$gt": now}
            })
            
            stats.expired_tokens = await db.password_reset_tokens.count_documents({
                "status": ResetTokenStatus.EXPIRED
            })
            
            # By type
            stats.admin_initiated_resets = await db.password_reset_tokens.count_documents({
                "token_type": ResetTokenType.ADMIN_INITIATED,
                "created_at": {"$gte": month_start}
            })
            
            stats.user_initiated_resets = await db.password_reset_tokens.count_documents({
                "token_type": ResetTokenType.USER_INITIATED,
                "created_at": {"$gte": month_start}
            })
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting reset statistics: {e}")
            return PasswordResetStats()
    
    async def cleanup_expired_tokens(self):
        """Clean up expired tokens (run periodically)"""
        try:
            db = self._get_db()
            cleanup_before = datetime.utcnow() - timedelta(hours=self.cleanup_expired_hours)
            
            # Mark expired tokens
            await db.password_reset_tokens.update_many(
                {
                    "status": ResetTokenStatus.ACTIVE,
                    "expires_at": {"$lt": datetime.utcnow()}
                },
                {
                    "$set": {"status": ResetTokenStatus.EXPIRED}
                }
            )
            
            # Delete very old tokens
            result = await db.password_reset_tokens.delete_many({
                "created_at": {"$lt": cleanup_before}
            })
            
            if result.deleted_count > 0:
                logger.info(f"Cleaned up {result.deleted_count} old password reset tokens")
            
        except Exception as e:
            logger.error(f"Error cleaning up expired tokens: {e}")

# Global password reset service instance
password_reset_service = PasswordResetService()