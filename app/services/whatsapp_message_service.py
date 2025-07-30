# app/services/whatsapp_message_service.py - WhatsApp Message Business Logic Service

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from bson import ObjectId
import httpx

from ..config.database import get_database
from ..config.settings import settings
from ..models.whatsapp_message import (
    WhatsAppMessage, WhatsAppMessageCreate, WebhookIncomingMessage,
    WebhookStatusUpdate, ChatHistoryResponse, ActiveChatsResponse,
    ActiveChatResponse, WhatsAppMessageResponse, SendMessageResponse,
    MessageDirection, MessageType, MessageStatus, WhatsAppStatistics
)

logger = logging.getLogger(__name__)

class WhatsAppMessageService:
    """Service class for WhatsApp message operations following LeadG CRM patterns"""
    
    def __init__(self):
        self.whatsapp_config = {
            "base_url": settings.whatsapp_base_url,
            "license_number": settings.whatsapp_license_number,
            "api_key": settings.whatsapp_api_key
        }
    
    # ============================================================================
    # 🆕 BULK MESSAGING METHODS (Missing methods that bulk processor needs)
    # ============================================================================
    
    async def _make_whatsapp_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make authenticated request to WhatsApp API - INTERNAL METHOD"""
        # Add authentication parameters
        params.update({
            "LicenseNumber": self.whatsapp_config["license_number"],
            "APIKey": self.whatsapp_config["api_key"]
        })
        
        url = f"{self.whatsapp_config['base_url']}/{endpoint}"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                # Parse response - handle both JSON and text responses
                try:
                    return response.json()
                except:
                    return {"status": "success", "message": response.text}
                    
        except Exception as e:
            logger.error(f"WhatsApp API request failed: {str(e)}")
            raise
    
    async def send_template_message(
        self, 
        contact: str, 
        template_name: str, 
        lead_name: str = ""
    ) -> Dict[str, Any]:
        """
        Send template message - PUBLIC METHOD for bulk processor
        
        Args:
            contact: Phone number to send to
            template_name: Template name to use
            lead_name: Lead name for personalization
            
        Returns:
            Result dictionary with success status
        """
        try:
            logger.debug(f"Sending template {template_name} to {contact}")
            
            # Use the same pattern as your WhatsApp router
            whatsapp_params = {
                "Contact": contact,
                "Template": template_name,
                "Param": lead_name  # Single parameter (lead name)
            }
            
            # Make API request using internal method
            result = await self._make_whatsapp_request("sendtemplate.php", whatsapp_params)
            
            if result:
                return {
                    "success": True,
                    "message_id": result.get("message_id", f"template_{int(datetime.utcnow().timestamp())}"),
                    "data": result
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send template message"
                }
                
        except Exception as e:
            logger.error(f"Error sending template message: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def send_text_message(
        self, 
        contact: str, 
        message: str
    ) -> Dict[str, Any]:
        """
        Send text message - PUBLIC METHOD for bulk processor
        
        Args:
            contact: Phone number to send to
            message: Message content to send
            
        Returns:
            Result dictionary with success status
        """
        try:
            logger.debug(f"Sending text message to {contact}")
            
            # Use the same pattern as your WhatsApp router
            whatsapp_params = {
                "Contact": contact,
                "Message": message
            }
            
            # Make API request using internal method
            result = await self._make_whatsapp_request("sendtextmessage.php", whatsapp_params)
            
            if result:
                return {
                    "success": True,
                    "message_id": result.get("message_id", f"text_{int(datetime.utcnow().timestamp())}"),
                    "data": result
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send text message"
                }
                
        except Exception as e:
            logger.error(f"Error sending text message: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    # ============================================================================
    # WEBHOOK PROCESSING (Core Functionality) - EXISTING CODE
    # ============================================================================
    
    async def process_incoming_webhook(self, webhook_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming webhook from mydreamstechnology
        This is the core function that handles incoming messages and status updates
        """
        try:
            logger.info(f"Processing WhatsApp webhook: {webhook_payload}")
            
            processed_messages = []
            processed_statuses = []
            errors = []
            
            # Extract messages and statuses from webhook payload
            # Note: Adjust this parsing based on actual mydreamstechnology webhook format
            messages = self._extract_messages_from_webhook(webhook_payload)
            statuses = self._extract_statuses_from_webhook(webhook_payload)
            
            # Process incoming messages
            for message_data in messages:
                try:
                    result = await self._process_single_incoming_message(message_data, webhook_payload)
                    if result["success"]:
                        processed_messages.append(result)
                    else:
                        errors.append(result)
                except Exception as e:
                    logger.error(f"Error processing message {message_data}: {str(e)}")
                    errors.append({"error": str(e), "message_data": message_data})
            
            # Process status updates
            for status_data in statuses:
                try:
                    result = await self._process_message_status_update(status_data)
                    if result["success"]:
                        processed_statuses.append(result)
                    else:
                        errors.append(result)
                except Exception as e:
                    logger.error(f"Error processing status {status_data}: {str(e)}")
                    errors.append({"error": str(e), "status_data": status_data})
            
            return {
                "success": True,
                "processed_messages": len(processed_messages),
                "processed_statuses": len(processed_statuses),
                "errors": len(errors),
                "details": {
                    "messages": processed_messages,
                    "statuses": processed_statuses,
                    "errors": errors
                }
            }
            
        except Exception as e:
            logger.error(f"Webhook processing failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "webhook_payload": webhook_payload
            }
    
    async def _process_single_incoming_message(self, message_data: Dict[str, Any], raw_webhook: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single incoming message and store in database"""
        try:
            db = get_database()
            
            # Extract message details from webhook format
            message_id = message_data.get("id")
            from_number = self._normalize_phone_number(message_data.get("from", ""))
            message_type = message_data.get("type", "text")
            timestamp_str = message_data.get("timestamp")
            
            # Convert timestamp
            timestamp = self._parse_webhook_timestamp(timestamp_str)
            
            # Extract content based on message type
            content = self._extract_message_content(message_data, message_type)
            
            # Find lead by phone number
            lead = await self._find_lead_by_phone_number(from_number)
            
            if not lead:
                logger.warning(f"No lead found for phone number: {from_number}")
                return {
                    "success": False,
                    "error": "Lead not found",
                    "phone_number": from_number,
                    "message_id": message_id
                }
            
            # Check if message already exists (prevent duplicates)
            existing_message = await db.whatsapp_messages.find_one({"message_id": message_id})
            if existing_message:
                logger.info(f"Message {message_id} already exists, skipping")
                return {
                    "success": True,
                    "action": "skipped",
                    "reason": "duplicate",
                    "message_id": message_id
                }
            
            # Create message document
            message_doc = {
                "message_id": message_id,
                "lead_id": lead["lead_id"],
                "phone_number": from_number,
                "direction": MessageDirection.INCOMING,
                "message_type": self._normalize_message_type(message_type),
                "content": content,
                "timestamp": timestamp,
                "status": MessageStatus.DELIVERED,
                "is_read": False,
                "sent_by_user_id": None,
                "sent_by_name": None,
                "media_url": message_data.get("media_url"),
                "media_filename": message_data.get("filename"),
                "raw_webhook_data": raw_webhook,
                "created_at": datetime.utcnow()
            }
            
            # Store message in database
            result = await db.whatsapp_messages.insert_one(message_doc)
            
            # Update lead's WhatsApp activity
            await self._update_lead_whatsapp_activity(
                lead["lead_id"],
                content,
                increment_total=True,
                increment_unread=True
            )
            
            # Log activity in lead timeline
            await self._log_whatsapp_activity(
                lead["lead_id"],
                f"Received WhatsApp message: {content[:100]}"
            )
            
            logger.info(f"Processed incoming message for lead {lead['lead_id']}")
            
            return {
                "success": True,
                "action": "created",
                "message_id": message_id,
                "lead_id": lead["lead_id"],
                "internal_id": str(result.inserted_id)
            }
            
        except Exception as e:
            logger.error(f"Error processing incoming message: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message_data": message_data
            }
    
    async def _process_message_status_update(self, status_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process message status update from webhook"""
        try:
            db = get_database()
            
            message_id = status_data.get("id")
            status = status_data.get("status")
            timestamp_str = status_data.get("timestamp")
            
            # Update message status
            update_result = await db.whatsapp_messages.update_one(
                {"message_id": message_id},
                {
                    "$set": {
                        "status": self._normalize_message_status(status),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if update_result.modified_count > 0:
                logger.info(f"Updated status for message {message_id} to {status}")
                return {
                    "success": True,
                    "message_id": message_id,
                    "new_status": status
                }
            else:
                logger.warning(f"Message {message_id} not found for status update")
                return {
                    "success": False,
                    "error": "Message not found",
                    "message_id": message_id
                }
                
        except Exception as e:
            logger.error(f"Error processing status update: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "status_data": status_data
            }
    
    # ============================================================================
    # CHAT MANAGEMENT (User-Facing Functions) - EXISTING CODE
    # ============================================================================
    
    async def get_chat_history(
        self, 
        lead_id: str, 
        limit: int = 50, 
        offset: int = 0,
        current_user: Dict[str, Any] = None
    ) -> ChatHistoryResponse:
        """Get chat history for a specific lead with permission checking"""
        try:
            db = get_database()
            
            # Check lead access permissions (following LeadG CRM pattern)
            lead = await self._check_lead_access(lead_id, current_user)
            
            # Get messages for this lead, ordered by timestamp
            messages_cursor = db.whatsapp_messages.find(
                {"lead_id": lead_id}
            ).sort("timestamp", 1).skip(offset).limit(limit)
            
            messages = await messages_cursor.to_list(length=limit)
            
            # Convert to response format
            formatted_messages = []
            for msg in messages:
                formatted_messages.append(WhatsAppMessageResponse(
                    id=str(msg["_id"]),
                    message_id=msg["message_id"],
                    lead_id=msg["lead_id"],
                    direction=msg["direction"],
                    message_type=msg["message_type"],
                    content=msg["content"],
                    timestamp=msg["timestamp"],
                    status=msg["status"],
                    is_read=msg.get("is_read", False),
                    sent_by_name=msg.get("sent_by_name")
                ))
            
            # Get total counts
            total_messages = await db.whatsapp_messages.count_documents({"lead_id": lead_id})
            unread_count = await db.whatsapp_messages.count_documents({
                "lead_id": lead_id,
                "direction": MessageDirection.INCOMING,
                "is_read": False
            })
            
            # Get last activity
            last_activity = None
            if messages:
                last_msg = messages[-1]
                last_activity = last_msg["timestamp"]
            
            return ChatHistoryResponse(
                success=True,  
                lead_id=lead_id,
                lead_name=lead["name"],
                phone_number=lead.get("contact_number", ""),
                messages=formatted_messages,
                total_messages=total_messages,
                unread_count=unread_count,
                last_activity=last_activity,
                pagination={                    # ADD THIS LINE
                    "total": total_messages,    # ADD THIS LINE
                    "page": 1,                  # ADD THIS LINE
                    "limit": 50,               # ADD THIS LINE
                    "has_next": False,         # ADD THIS LINE
                    "has_prev": False          # ADD THIS LINE
                }      
            )
            
        except Exception as e:
            logger.error(f"Error fetching chat history for lead {lead_id}: {str(e)}")
            raise Exception(f"Failed to fetch chat history: {str(e)}")
    
    
    async def send_and_store_message(
        self, 
        lead_id: str, 
        message_content: str, 
        current_user: Dict[str, Any]
    ) -> SendMessageResponse:
        """Send message via WhatsApp API and store in database"""
        try:
            db = get_database()
            
            # Check lead access permissions
            lead = await self._check_lead_access(lead_id, current_user)
            
            # Get lead's phone number
            phone_number = lead.get("contact_number") or lead.get("phone_number")
            if not phone_number:
                raise Exception("Lead has no phone number")
            
            # Send message via WhatsApp API
            whatsapp_result = await self._send_whatsapp_text_message(phone_number, message_content)
            
            if not whatsapp_result.get("success"):
                raise Exception(f"WhatsApp API error: {whatsapp_result.get('error')}")
            
            # Store sent message in database
            message_doc = {
                "message_id": whatsapp_result.get("message_id", f"out_{int(datetime.utcnow().timestamp())}"),
                "lead_id": lead_id,
                "phone_number": self._normalize_phone_number(phone_number),
                "direction": MessageDirection.OUTGOING,
                "message_type": MessageType.TEXT,
                "content": message_content,
                "timestamp": datetime.utcnow(),
                "status": MessageStatus.SENT,
                "is_read": True,  # Outgoing messages are always "read"
                "sent_by_user_id": str(current_user.get("_id") or current_user.get("id")),
                "sent_by_name": current_user.get("name", "Unknown User"),
                "created_at": datetime.utcnow()
            }
            
            result = await db.whatsapp_messages.insert_one(message_doc)
            
            # Update lead's WhatsApp activity
            await self._update_lead_whatsapp_activity(
                lead_id,
                message_content,
                increment_total=True,
                increment_unread=False  # Don't increment unread for outgoing
            )
            
            # Log activity
            await self._log_whatsapp_activity(
                lead_id,
                f"Sent WhatsApp message: {message_content[:100]}"
            )
            
            return SendMessageResponse(
                success=True,
                message_id=message_doc["message_id"],
                lead_id=lead_id,
                content=message_content,
                timestamp=message_doc["timestamp"],
                status=MessageStatus.SENT
            )
            
        except Exception as e:
            logger.error(f"Error sending message to lead {lead_id}: {str(e)}")
            raise Exception(f"Failed to send message: {str(e)}")
    
    async def get_active_chats(
        self, 
        current_user: Dict[str, Any], 
        limit: int = 50
    ) -> ActiveChatsResponse:
        """Get list of leads with recent WhatsApp activity"""
        try:
            db = get_database()
            
            # Build permission filter (following LeadG CRM pattern)
            user_role = current_user.get("role", "user")
            user_email = current_user.get("email", "")
            
            if user_role == "admin":
                # Admin sees all leads with WhatsApp activity
                lead_filter = {"whatsapp_message_count": {"$gt": 0}}
            else:
                # Regular users see only their assigned leads with WhatsApp activity
                lead_filter = {
                    "$or": [
                        {"assigned_to": user_email},
                        {"co_assignees": user_email}
                    ],
                    "whatsapp_message_count": {"$gt": 0}
                }
            
            # Get leads with WhatsApp activity, sorted by last activity
            leads_cursor = db.leads.find(lead_filter).sort("last_whatsapp_activity", -1).limit(limit)
            leads = await leads_cursor.to_list(length=limit)
            
            active_chats = []
            total_unread = 0
            
            for lead in leads:
                # Get last message for this lead
                last_message_doc = await db.whatsapp_messages.find_one(
                    {"lead_id": lead["lead_id"]},
                    sort=[("timestamp", -1)]
                )
                
                last_message = None
                if last_message_doc:
                    last_message = WhatsAppMessageResponse(
                        id=str(last_message_doc["_id"]),
                        message_id=last_message_doc["message_id"],
                        lead_id=last_message_doc["lead_id"],
                        direction=last_message_doc["direction"],
                        message_type=last_message_doc["message_type"],
                        content=last_message_doc["content"],
                        timestamp=last_message_doc["timestamp"],
                        status=last_message_doc["status"],
                        is_read=last_message_doc.get("is_read", False),
                        sent_by_name=last_message_doc.get("sent_by_name")
                    )
                
                unread_count = lead.get("unread_whatsapp_count", 0)
                total_unread += unread_count
                
                active_chats.append(ActiveChatResponse(
                    lead_id=lead["lead_id"],
                    lead_name=lead["name"],
                    phone_number=lead.get("contact_number", ""),
                    assigned_to=lead.get("assigned_to"),
                    assigned_to_name=lead.get("assigned_to_name"),
                    last_message=last_message,
                    unread_count=unread_count,
                    total_messages=lead.get("whatsapp_message_count", 0),
                    last_activity=lead.get("last_whatsapp_activity")
                ))
            
            return ActiveChatsResponse(
                chats=active_chats,
                total_chats=len(active_chats),
                total_unread=total_unread
            )
            
        except Exception as e:
            logger.error(f"Error fetching active chats: {str(e)}")
            raise Exception(f"Failed to fetch active chats: {str(e)}")
    
    async def mark_messages_as_read(
        self, 
        lead_id: str, 
        message_ids: List[str], 
        current_user: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Mark messages as read and update lead unread count"""
        try:
            db = get_database()
            
            # Check lead access
            await self._check_lead_access(lead_id, current_user)
            
            # Mark messages as read
            update_result = await db.whatsapp_messages.update_many(
                {
                    "lead_id": lead_id,
                    "message_id": {"$in": message_ids},
                    "direction": MessageDirection.INCOMING,
                    "is_read": False
                },
                {
                    "$set": {
                        "is_read": True,
                        "read_at": datetime.utcnow(),
                        "read_by_user_id": str(current_user.get("_id") or current_user.get("id"))
                    }
                }
            )
            
            # Update lead's unread count
            if update_result.modified_count > 0:
                new_unread_count = await db.whatsapp_messages.count_documents({
                    "lead_id": lead_id,
                    "direction": MessageDirection.INCOMING,
                    "is_read": False
                })
                
                await db.leads.update_one(
                    {"lead_id": lead_id},
                    {"$set": {"unread_whatsapp_count": new_unread_count}}
                )
            
            return {
                "success": True,
                "marked_as_read": update_result.modified_count,
                "message_ids": message_ids
            }
            
        except Exception as e:
            logger.error(f"Error marking messages as read: {str(e)}")
            raise Exception(f"Failed to mark messages as read: {str(e)}")
    
    # ============================================================================
    # UTILITY & HELPER FUNCTIONS - EXISTING CODE
    # ============================================================================
    
    async def _find_lead_by_phone_number(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Find lead by phone number with multiple format matching"""
        db = get_database()
        
        # Try multiple phone number formats
        search_numbers = [
            phone_number,
            f"+{phone_number}",
            phone_number.lstrip('+'),
            phone_number[-10:] if len(phone_number) > 10 else phone_number  # Last 10 digits
        ]
        
        for search_num in search_numbers:
            lead = await db.leads.find_one({
                "$or": [
                    {"contact_number": search_num},
                    {"phone_number": search_num},
                    {"contact_number": {"$regex": search_num.replace("+", "\\+"), "$options": "i"}},
                    {"phone_number": {"$regex": search_num.replace("+", "\\+"), "$options": "i"}}
                ]
            })
            if lead:
                return lead
        
        return None
    
    async def _check_lead_access(self, lead_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Check if user has access to lead (following LeadG CRM permission pattern)"""
        db = get_database()
        
        user_role = current_user.get("role", "user")
        user_email = current_user.get("email", "")
        
        if user_role == "admin":
            # Admin can access any lead
            lead = await db.leads.find_one({"lead_id": lead_id})
        else:
            # Regular user can only access assigned leads
            lead = await db.leads.find_one({
                "lead_id": lead_id,
                "$or": [
                    {"assigned_to": user_email},
                    {"co_assignees": user_email}
                ]
            })
        
        if not lead:
            raise Exception("Lead not found or access denied")
        
        return lead
    
    async def _update_lead_whatsapp_activity(
        self, 
        lead_id: str, 
        message_content: str, 
        increment_total: bool = False,
        increment_unread: bool = False
    ):
        """Update lead's WhatsApp activity fields"""
        try:
            db = get_database()
            
            update_fields = {
                "last_whatsapp_activity": datetime.utcnow(),
                "last_whatsapp_message": message_content[:200]  # Preview
            }
            
            if increment_total:
                update_fields["$inc"] = update_fields.get("$inc", {})
                update_fields["$inc"]["whatsapp_message_count"] = 1
            
            if increment_unread:
                update_fields["$inc"] = update_fields.get("$inc", {})
                update_fields["$inc"]["unread_whatsapp_count"] = 1
            
            # Separate $set and $inc operations
            set_fields = {k: v for k, v in update_fields.items() if k != "$inc"}
            inc_fields = update_fields.get("$inc", {})
            
            update_query = {"$set": set_fields}
            if inc_fields:
                update_query["$inc"] = inc_fields
            
            await db.leads.update_one({"lead_id": lead_id}, update_query)
            
        except Exception as e:
            logger.error(f"Error updating lead WhatsApp activity: {str(e)}")
    
    async def _log_whatsapp_activity(self, lead_id: str, description: str):
        """Log WhatsApp activity in lead timeline (following LeadG CRM pattern)"""
        try:
            db = get_database()
            
            # Get lead object ID for activity logging
            lead = await db.leads.find_one({"lead_id": lead_id})
            if not lead:
                return
            
            activity_doc = {
                "lead_id": lead_id,
                "lead_object_id": lead["_id"],
                "activity_type": "whatsapp_message",
                "description": description,
                "is_system_generated": True,
                "created_by": "system",
                "created_at": datetime.utcnow()
            }
            
            await db.lead_activities.insert_one(activity_doc)
            
        except Exception as e:
            logger.error(f"Error logging WhatsApp activity: {str(e)}")
    
    async def _send_whatsapp_text_message(self, phone_number: str, message: str) -> Dict[str, Any]:
        """Send text message via WhatsApp API - PRIVATE METHOD (existing)"""
        try:
            url = f"{self.whatsapp_config['base_url']}/sendtextmessage.php"
            params = {
                "LicenseNumber": self.whatsapp_config["license_number"],
                "APIKey": self.whatsapp_config["api_key"],
                "Contact": phone_number,
                "Message": message
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                # Parse response (adjust based on actual API response format)
                try:
                    result = response.json()
                except:
                    result = {"status": "success", "message": response.text}
                
                return {
                    "success": True,
                    "message_id": result.get("message_id", f"msg_{int(datetime.utcnow().timestamp())}"),
                    "data": result
                }
                
        except Exception as e:
            logger.error(f"WhatsApp API error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    # Webhook parsing helpers - EXISTING CODE
    def _extract_messages_from_webhook(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract messages from webhook payload - adjust based on actual format"""
        messages = []
        
        # This needs to be adjusted based on actual mydreamstechnology webhook format
        entry_list = payload.get("entry", [])
        for entry in entry_list:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                webhook_messages = value.get("messages", [])
                messages.extend(webhook_messages)
        
        return messages
    
    def _extract_statuses_from_webhook(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract status updates from webhook payload"""
        statuses = []
        
        entry_list = payload.get("entry", [])
        for entry in entry_list:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                webhook_statuses = value.get("statuses", [])
                statuses.extend(webhook_statuses)
        
        return statuses
    
    def _extract_message_content(self, message_data: Dict[str, Any], message_type: str) -> str:
        """Extract content from message based on type"""
        if message_type == "text":
            return message_data.get("text", {}).get("body", "")
        elif message_type == "image":
            caption = message_data.get("image", {}).get("caption", "")
            return f"📷 Image: {caption}" if caption else "📷 Image"
        elif message_type == "document":
            filename = message_data.get("document", {}).get("filename", "Unknown file")
            return f"📄 Document: {filename}"
        elif message_type == "audio":
            return "🎵 Audio message"
        elif message_type == "video":
            return "🎥 Video message"
        else:
            return f"📎 {message_type.title()} message"
    
    def _normalize_phone_number(self, phone: str) -> str:
        """Normalize phone number format"""
        if not phone:
            return ""
        digits_only = ''.join(filter(str.isdigit, phone))
        if len(digits_only) == 10:
            return f"91{digits_only}"  # Add India country code
        return digits_only
    
    def _normalize_message_type(self, msg_type: str) -> str:
        """Normalize message type"""
        type_mapping = {
            "text": MessageType.TEXT,
            "image": MessageType.IMAGE,
            "document": MessageType.DOCUMENT,
            "audio": MessageType.AUDIO,
            "video": MessageType.VIDEO,
            "location": MessageType.LOCATION,
            "contact": MessageType.CONTACT
        }
        return type_mapping.get(msg_type.lower(), MessageType.TEXT)
    
    def _normalize_message_status(self, status: str) -> str:
        """Normalize message status"""
        status_mapping = {
            "sent": MessageStatus.SENT,
            "delivered": MessageStatus.DELIVERED,
            "read": MessageStatus.READ,
            "failed": MessageStatus.FAILED
        }
        return status_mapping.get(status.lower(), MessageStatus.SENT)
    
    def _parse_webhook_timestamp(self, timestamp_str: str) -> datetime:
        """Parse timestamp from webhook"""
        try:
            # Assume Unix timestamp
            timestamp = int(timestamp_str)
            return datetime.fromtimestamp(timestamp)
        except:
            # Fallback to current time
            return datetime.utcnow()

# Create singleton instance
whatsapp_message_service = WhatsAppMessageService()