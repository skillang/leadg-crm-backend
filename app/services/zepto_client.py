# app/services/zepto_client.py
import aiohttp
import asyncio
from typing import Dict, List, Any, Optional
import logging
import json
from datetime import datetime

from ..config.settings import settings

logger = logging.getLogger(__name__)

class ZeptoMailClient:
    """ZeptoMail API client for sending template-based emails"""
    
    def __init__(self):
        # Use your exact ZeptoMail configuration
        self.base_url = f"https://{settings.zeptomail_url.rstrip('/')}"
        self.api_token = settings.zeptomail_token
        
        # Standard headers for ZeptoMail API
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self.api_token  # Your token already includes "Zoho-enczapikey"
        }
        
        logger.info(f"ZeptoMail client initialized with URL: {self.base_url}")
    
    async def send_template_email(
        self, 
        template_key: str,
        sender_email: str,
        recipient_email: str,
        recipient_name: str,
        merge_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send single email using ZeptoMail template API
        Following your existing mailer logic pattern
        """
        try:
            # Prepare recipient (following your existing format)
            recipient = {
                "email_address": {
                    "address": recipient_email,
                    "name": recipient_name
                }
            }
            
            # Prepare payload (following your exact mailer structure)
            payload = {
                "mail_template_key": template_key,
                "from": {
                    "address": sender_email,
                    "name": "Skillang"  # Use your brand name
                },
                "to": [recipient]
            }
            
            # Add merge_info for personalization (like username)
            if merge_data:
                payload["merge_info"] = merge_data
            else:
                # Default merge info with recipient name
                payload["merge_info"] = {
                    "username": recipient_name
                }
            
            logger.info(f"Sending email to {recipient_email} with template {template_key}")
            logger.debug(f"ZeptoMail payload: {json.dumps(payload, indent=2)}")
            
            # Send request to ZeptoMail API
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/v1.1/email/template"
                
                async with session.post(url, json=payload, headers=self.headers) as response:
                    response_data = await response.json()
                    
                    # ZeptoMail returns 200/201 for success, not just 200
                    if response.status in [200, 201]:
                        logger.info(f"Email sent successfully to {recipient_email}")
                        return {
                            "success": True,
                            "data": response_data,
                            "recipient": recipient_email,
                            "template": template_key,
                            "status_code": response.status
                        }
                    else:
                        error_msg = f"ZeptoMail API error: {response.status} - {response_data}"
                        logger.error(error_msg)
                        return {
                            "success": False,
                            "error": response_data,
                            "recipient": recipient_email,
                            "template": template_key,
                            "status_code": response.status
                        }
                        
        except aiohttp.ClientError as e:
            error_msg = f"Network error sending email to {recipient_email}: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "recipient": recipient_email,
                "template": template_key
            }
        except Exception as e:
            error_msg = f"Unexpected error sending email to {recipient_email}: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "recipient": recipient_email,
                "template": template_key
            }
    
    async def send_bulk_template_email(
        self,
        template_key: str,
        sender_email: str,
        recipients: List[Dict[str, Any]]  # List of {email, name, merge_data}
    ) -> Dict[str, Any]:
        """
        Send bulk emails using ZeptoMail template API
        Process each recipient individually for better error handling
        """
        results = []
        successful_count = 0
        failed_count = 0
        
        logger.info(f"Starting bulk email send to {len(recipients)} recipients")
        
        # Process each recipient individually (like your existing mailer)
        for recipient_data in recipients:
            try:
                email = recipient_data.get("email")
                name = recipient_data.get("name", email.split('@')[0])
                merge_data = recipient_data.get("merge_data", {})
                
                # Send individual email
                result = await self.send_template_email(
                    template_key=template_key,
                    sender_email=sender_email,
                    recipient_email=email,
                    recipient_name=name,
                    merge_data=merge_data
                )
                
                if result["success"]:
                    successful_count += 1
                    results.append({
                        "recipient": email,
                        "status": "sent",
                        "sent_at": datetime.utcnow()
                    })
                else:
                    failed_count += 1
                    results.append({
                        "recipient": email,
                        "status": "failed",
                        "error": result.get("error", "Unknown error"),
                        "failed_at": datetime.utcnow()
                    })
                
                # Small delay between emails to avoid rate limiting
                await asyncio.sleep(0.1)
                
            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing recipient {recipient_data}: {e}")
                results.append({
                    "recipient": recipient_data.get("email", "unknown"),
                    "status": "failed",
                    "error": str(e),
                    "failed_at": datetime.utcnow()
                })
        
        logger.info(f"Bulk email completed: {successful_count} sent, {failed_count} failed")
        
        return {
            "success": successful_count > 0,
            "total_recipients": len(recipients),
            "successful_count": successful_count,
            "failed_count": failed_count,
            "results": results,
            "message": f"Bulk email completed: {successful_count} sent, {failed_count} failed"
        }
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test ZeptoMail API connection and authentication"""
        try:
            logger.info("Testing ZeptoMail API connection...")
            
            # Use a simple API call to test connection
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/v1.1/email/template"  # This will fail but shows auth works
                
                # Send empty request to test auth
                async with session.post(url, json={}, headers=self.headers) as response:
                    response_data = await response.json()
                    
                    if response.status == 400:
                        # 400 Bad Request means auth worked but request is invalid (expected)
                        logger.info("ZeptoMail API connection successful (auth working)")
                        return {
                            "success": True,
                            "message": "ZeptoMail API connection successful",
                            "authenticated": True
                        }
                    elif response.status == 401:
                        # 401 Unauthorized means auth failed
                        logger.error("ZeptoMail API authentication failed")
                        return {
                            "success": False,
                            "message": "ZeptoMail API authentication failed",
                            "authenticated": False,
                            "error": response_data
                        }
                    else:
                        logger.warning(f"Unexpected response from ZeptoMail API: {response.status}")
                        return {
                            "success": True,
                            "message": f"ZeptoMail API responded with status {response.status}",
                            "authenticated": True,
                            "response": response_data
                        }
                        
        except Exception as e:
            error_msg = f"Failed to test ZeptoMail connection: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "authenticated": False
            }
    
    def format_sender_email(self, prefix: str) -> str:
        """Format sender email with domain (following your pattern)"""
        # Use your domain from existing configuration
        domain = "@skillang.com"  # Your existing domain
        
        # Clean the prefix
        clean_prefix = prefix.strip().lower()
        
        return f"{clean_prefix}{domain}"
    
    def is_configured(self) -> bool:
        """Check if ZeptoMail is properly configured"""
        return bool(self.api_token) and bool(self.base_url)

# Global ZeptoMail client instance
zepto_client = ZeptoMailClient()

# Helper functions for easy import
async def send_single_email(
    template_key: str,
    sender_prefix: str,
    recipient_email: str,
    recipient_name: str,
    merge_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Helper function to send single email"""
    sender_email = zepto_client.format_sender_email(sender_prefix)
    
    return await zepto_client.send_template_email(
        template_key=template_key,
        sender_email=sender_email,
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        merge_data=merge_data
    )

async def send_bulk_emails(
    template_key: str,
    sender_prefix: str,
    recipients: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Helper function to send bulk emails"""
    sender_email = zepto_client.format_sender_email(sender_prefix)
    
    return await zepto_client.send_bulk_template_email(
        template_key=template_key,
        sender_email=sender_email,
        recipients=recipients
    )

async def test_zepto_connection() -> Dict[str, Any]:
    """Helper function to test ZeptoMail connection"""
    return await zepto_client.test_connection()