# app/utils/email_service.py
# Email Service Utility for LeadG CRM - ZeptoMail Only Version
# Simplified to use ZeptoMail exclusively with your existing template

from typing import Dict, List, Any, Optional, Union
import logging
from datetime import datetime

from ..config.settings import settings
from ..services.zepto_client import zepto_client

logger = logging.getLogger(__name__)

class EmailService:
    """
    Simplified Email Service for LeadG CRM - ZeptoMail Only
    
    Features:
    - ZeptoMail integration only (SMTP removed)
    - Uses your existing template ID
    - Password reset email functionality
    - Admin notification support
    - Professional sender identity
    """
    
    def __init__(self):
        self.zepto_configured = zepto_client.is_configured()
        self.template_id = "2518b.3027c48fe4ab851b.m4.2bcde980-859d-11f0-a8ed-8e9a6c33ddc2.198faf59018"
        self.sender_email = "noreply@skillang.com"
        self.sender_name = "LeadG CRM"
        
        logger.info(f"Email service initialized - ZeptoMail: {self.zepto_configured}")
        logger.info(f"Using template ID: {self.template_id}")
        logger.info(f"Sender: {self.sender_name} <{self.sender_email}>")
    
    def validate_email(self, email: str) -> bool:
        """Basic email validation"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    async def send_password_reset_email(
        self,
        user_email: str,
        user_name: str,
        reset_token: str,
        reset_type: str = "user_initiated",
        admin_name: str = None,
        notification_message: str = None,
        expires_in_minutes: int = 30
    ) -> Dict[str, Any]:
        """
        Send password reset email using ZeptoMail template
        
        Args:
            user_email: Recipient email address
            user_name: Recipient name
            reset_token: Password reset token
            reset_type: "user_initiated" or "admin_initiated"
            admin_name: Admin name (for admin-initiated resets)
            notification_message: Custom message (for admin-initiated resets)
            expires_in_minutes: Token expiration time
            
        Returns:
            Dict with success status and details
        """
        try:
            # Validate email
            if not self.validate_email(user_email):
                return {
                    "success": False,
                    "error": "Invalid email address format"
                }
            
            if not self.zepto_configured:
                logger.error("ZeptoMail is not configured")
                return {
                    "success": False,
                    "error": "Email service is not configured"
                }
            
            # Build reset link
            reset_link = f"https://leadg.in/reset-password?token={reset_token}"
            
            # Prepare merge data based on reset type
            if reset_type == "admin_initiated":
                # Admin-initiated reset
                subject = f"Password Reset by Administrator - {settings.app_name}"
                email_type = "Admin Password Reset"
                message_content = f"""
                <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; margin: 20px 0; border-radius: 4px;">
                    <h3 style="margin-top: 0; color: #856404;">Administrator Message:</h3>
                    <p style="margin-bottom: 0; color: #856404; font-style: italic;">"{notification_message or 'Your password has been reset by an administrator.'}"</p>
                    <p style="color: #856404; font-size: 14px; margin-bottom: 0;">Reset initiated by: <strong>{admin_name or 'Administrator'}</strong></p>
                </div>
                
                <p>An administrator has initiated a password reset for your {settings.app_name} account.</p>
                <p><strong>Important:</strong> You will be required to change your password again after logging in for security reasons.</p>
                """
            else:
                # User-initiated reset
                subject = f"Password Reset Request - {settings.app_name}"
                email_type = "Password Reset"
                message_content = f"""
                <p>We received a request to reset your password for your {settings.app_name} account.</p>
                <p>If you didn't request this password reset, please ignore this email or contact our support team.</p>
                
                <div style="background: #e8f5e8; border-left: 4px solid #4caf50; padding: 15px 20px; margin: 20px 0; border-radius: 4px;">
                    <h4 style="margin-top: 0; color: #2e7d32;">🛡️ Security Tips:</h4>
                    <ul style="margin: 10px 0; padding-left: 20px; color: #2e7d32;">
                        <li>Never share your password with anyone</li>
                        <li>Use a strong, unique password</li>
                        <li>Consider using a password manager</li>
                    </ul>
                </div>
                """
            
            # Prepare template merge data
            merge_data = {
                "username": user_name,
                "app_name": settings.app_name,
                "email_type": email_type,
                "message_content": message_content,
                "reset_link": reset_link,
                "expires_in": str(expires_in_minutes),
                "support_email": settings.smtp_from_email or "support@skillang.com",
                "current_year": str(datetime.now().year),
                "button_text": "Reset My Password" if reset_type == "user_initiated" else "Set New Password"
            }
            
            # Send email using ZeptoMail
            result = await zepto_client.send_template_email(
                template_key="2518b.3027c48fe4ab851b.k1.44ad7230-859e-11f0-a35a-cabf48e1bf81.198fafcc0d3",
                sender_email=self.sender_email,
                recipient_email=user_email,
                recipient_name=user_name,
                merge_data=merge_data
            )
            
            if result.get("success"):
                logger.info(f"Password reset email sent to {user_email} (type: {reset_type})")
                return {
                    "success": True,
                    "message": "Password reset email sent successfully",
                    "email_type": reset_type,
                    "recipient": user_email
                }
            else:
                logger.error(f"Failed to send password reset email to {user_email}: {result}")
                return {
                    "success": False,
                    "error": f"Failed to send email: {result.get('error', 'Unknown error')}"
                }
                
        except Exception as e:
            logger.error(f"Error sending password reset email to {user_email}: {e}")
            return {
                "success": False,
                "error": f"Failed to send email: {str(e)}"
            }
    
    async def send_password_reset_success_email(
        self,
        user_email: str,
        user_name: str,
        reset_date: str,
        ip_address: str = "Unknown",
        user_agent: str = "Unknown"
    ) -> Dict[str, Any]:
        """Send password reset success confirmation email"""
        try:
            if not self.validate_email(user_email):
                return {
                    "success": False,
                    "error": "Invalid email address format"
                }
            
            if not self.zepto_configured:
                return {
                    "success": False,
                    "error": "Email service is not configured"
                }
            
            # Truncate long user agents
            display_user_agent = user_agent[:100] + "..." if len(user_agent) > 100 else user_agent
            
            # Success message content
            message_content = f"""
            <div style="background: #d4edda; border: 1px solid #c3e6cb; padding: 20px; margin: 25px 0; border-radius: 6px; text-align: center;">
                <h3 style="margin-top: 0; color: #155724; font-size: 18px;">✓ Password Reset Complete</h3>
                <p style="margin-bottom: 0; color: #155724;">Your account is now secure with your new password.</p>
            </div>
            
            <div style="background: #f8f9fa; border: 1px solid #dee2e6; padding: 20px; margin: 25px 0; border-radius: 6px;">
                <h4 style="margin-top: 0;">🔍 Reset Details:</h4>
                <ul style="margin: 10px 0; padding-left: 20px;">
                    <li><strong>Date:</strong> {reset_date}</li>
                    <li><strong>IP Address:</strong> {ip_address}</li>
                    <li><strong>Browser:</strong> {display_user_agent}</li>
                </ul>
            </div>
            
            <p><strong>⚠️ Security Alert:</strong> If you did not make this change, please contact our support team immediately.</p>
            """
            
            # Prepare template merge data
            merge_data = {
                "username": user_name,
                "app_name": settings.app_name,
                "email_type": "Password Reset Successful",
                "message_content": message_content,
                "reset_link": f"{settings.skillang_frontend_domain}/login",
                "support_email": settings.smtp_from_email or "support@skillang.com",
                "current_year": str(datetime.now().year),
                "button_text": f"Login to {settings.app_name}"
            }
            
            # Send email
            result = await zepto_client.send_template_email(
                template_key=self.template_id,
                sender_email=self.sender_email,
                recipient_email=user_email,
                recipient_name=user_name,
                merge_data=merge_data
            )
            
            if result.get("success"):
                logger.info(f"Password reset success email sent to {user_email}")
                return {
                    "success": True,
                    "message": "Password reset success confirmation sent"
                }
            else:
                logger.error(f"Failed to send success email to {user_email}: {result}")
                return {
                    "success": False,
                    "error": f"Failed to send confirmation email: {result.get('error', 'Unknown error')}"
                }
                
        except Exception as e:
            logger.error(f"Error sending password reset success email to {user_email}: {e}")
            return {
                "success": False,
                "error": f"Failed to send email: {str(e)}"
            }
    
    async def send_admin_notification(
        self,
        user_email: str,
        user_name: str,
        reset_type: str,
        initiated_by: str,
        reset_date: str,
        ip_address: str = "Unknown",
        status: str = "Success",
        reset_method: str = "email_link"
    ) -> Dict[str, Any]:
        """Send admin notification about password reset activity"""
        try:
            if not self.zepto_configured:
                return {
                    "success": False,
                    "error": "Email service is not configured"
                }
            
            # Get all admin users
            from ..config.database import get_database
            db = get_database()
            
            admin_users = await db.users.find(
                {"role": "admin", "is_active": True},
                {"email": 1, "first_name": 1, "last_name": 1}
            ).to_list(None)
            
            if not admin_users:
                logger.warning("No admin users found to notify")
                return {
                    "success": True,
                    "message": "No admin users to notify"
                }
            
            # Admin notification content
            message_content = f"""
            <div style="background: #f8f9fa; border-left: 4px solid #007bff; padding: 15px; margin: 20px 0;">
                <h3 style="margin-top: 0;">Password Reset Activity Report</h3>
                <p><strong>User:</strong> {user_email} ({user_name})</p>
                <p><strong>Reset Type:</strong> {reset_type}</p>
                <p><strong>Initiated By:</strong> {initiated_by}</p>
                <p><strong>Date/Time:</strong> {reset_date}</p>
                <p><strong>IP Address:</strong> {ip_address}</p>
                <p><strong>Status:</strong> {status}</p>
                <p><strong>Method:</strong> {reset_method}</p>
            </div>
            
            <p>This notification is sent to all administrators for security monitoring purposes.</p>
            """
            
            # Send to all admins
            results = []
            for admin in admin_users:
                admin_name = f"{admin.get('first_name', '')} {admin.get('last_name', '')}".strip() or admin["email"]
                
                merge_data = {
                    "username": admin_name,
                    "app_name": settings.app_name,
                    "email_type": "Security Alert - Password Reset Activity",
                    "message_content": message_content,
                    "reset_link": f"{settings.skillang_frontend_domain}/admin/security",
                    "support_email": settings.smtp_from_email or "support@skillang.com",
                    "current_year": str(datetime.now().year),
                    "button_text": "View Admin Dashboard"
                }
                
                result = await zepto_client.send_template_email(
                    template_key=self.template_id,
                    sender_email=self.sender_email,
                    recipient_email=admin["email"],
                    recipient_name=admin_name,
                    merge_data=merge_data
                )
                
                results.append({
                    "admin_email": admin["email"],
                    "success": result.get("success", False),
                    "error": result.get("error") if not result.get("success") else None
                })
            
            # Check overall success
            successful_sends = sum(1 for r in results if r["success"])
            total_sends = len(results)
            
            logger.info(f"Admin notifications sent: {successful_sends}/{total_sends}")
            
            return {
                "success": successful_sends > 0,
                "message": f"Admin notifications sent: {successful_sends}/{total_sends}",
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error sending admin notifications: {e}")
            return {
                "success": False,
                "error": f"Failed to send admin notifications: {str(e)}"
            }
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get email service configuration status"""
        return {
            "service_type": "ZeptoMail Only",
            "zepto_configured": self.zepto_configured,
            "template_id": self.template_id,
            "sender_email": self.sender_email,
            "sender_name": self.sender_name,
            "frontend_domain": settings.skillang_frontend_domain,
            "features": {
                "password_reset": True,
                "admin_notifications": True,
                "success_confirmations": True,
                "template_based": True
            }
        }
    
    async def test_email_service(self, test_email: str) -> Dict[str, Any]:
        """Test email service with a simple test email"""
        try:
            if not self.validate_email(test_email):
                return {
                    "success": False,
                    "error": "Invalid test email address"
                }
            
            if not self.zepto_configured:
                return {
                    "success": False,
                    "error": "ZeptoMail is not configured"
                }
            
            # Test message content
            message_content = f"""
            <div style="text-align: center; padding: 20px;">
                <h2>✅ Email Service Test</h2>
                <p>This is a test email from {settings.app_name} email service.</p>
                <p><strong>Service:</strong> ZeptoMail</p>
                <p><strong>Template ID:</strong> {self.template_id}</p>
                <p><strong>Sender:</strong> {self.sender_name} &lt;{self.sender_email}&gt;</p>
                <p><strong>Test Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            """
            
            merge_data = {
                "username": "Test User",
                "app_name": settings.app_name,
                "email_type": "Service Test",
                "message_content": message_content,
                "reset_link": settings.skillang_frontend_domain,
                "support_email": settings.smtp_from_email or "support@skillang.com",
                "current_year": str(datetime.now().year),
                "button_text": f"Visit {settings.app_name}"
            }
            
            result = await zepto_client.send_template_email(
                template_key=self.template_id,
                sender_email=self.sender_email,
                recipient_email=test_email,
                recipient_name="Test User",
                merge_data=merge_data
            )
            
            if result.get("success"):
                logger.info(f"Test email sent successfully to {test_email}")
                return {
                    "success": True,
                    "message": f"Test email sent successfully to {test_email}",
                    "template_used": self.template_id,
                    "sender": f"{self.sender_name} <{self.sender_email}>"
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to send test email: {result.get('error', 'Unknown error')}"
                }
                
        except Exception as e:
            logger.error(f"Error testing email service: {e}")
            return {
                "success": False,
                "error": f"Email service test failed: {str(e)}"
            }

# Global email service instance
email_service = EmailService()

# Utility functions for easy import
async def send_password_reset_email(
    user_email: str,
    user_name: str,
    reset_token: str,
    reset_type: str = "user_initiated",
    **kwargs
) -> Dict[str, Any]:
    """Helper function to send password reset email"""
    return await email_service.send_password_reset_email(
        user_email=user_email,
        user_name=user_name,
        reset_token=reset_token,
        reset_type=reset_type,
        **kwargs
    )

async def send_password_reset_success_email(
    user_email: str,
    user_name: str,
    reset_date: str,
    **kwargs
) -> Dict[str, Any]:
    """Helper function to send password reset success confirmation"""
    return await email_service.send_password_reset_success_email(
        user_email=user_email,
        user_name=user_name,
        reset_date=reset_date,
        **kwargs
    )

async def notify_admins_of_password_reset(
    user_email: str,
    user_name: str,
    reset_type: str,
    initiated_by: str,
    **kwargs
) -> Dict[str, Any]:
    """Helper function to notify admins of password reset activity"""
    return await email_service.send_admin_notification(
        user_email=user_email,
        user_name=user_name,
        reset_type=reset_type,
        initiated_by=initiated_by,
        **kwargs
    )

def get_email_service_status() -> Dict[str, Any]:
    """Helper function to get email service status"""
    return email_service.get_service_status()

async def test_email_service(test_email: str) -> Dict[str, Any]:
    """Helper function to test email service"""
    return await email_service.test_email_service(test_email)