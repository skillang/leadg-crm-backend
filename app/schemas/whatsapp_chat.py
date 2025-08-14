# app/schemas/whatsapp_chat.py - Enhanced with Real-time Notification Schemas

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum

# ============================================================================
# API REQUEST SCHEMAS
# ============================================================================

class SendChatMessageRequest(BaseModel):
    """Request schema for sending a message in chat conversation"""
    message: str = Field(..., min_length=1, max_length=4096, description="Message text to send")
    
    @validator('message')
    def validate_message_content(cls, v):
        """Validate message content"""
        if not v or not v.strip():
            raise ValueError("Message cannot be empty")
        return v.strip()
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Thanks for your interest! Let me share more details about our programs."
            }
        }

class MarkMessagesReadRequest(BaseModel):
    """Request schema for marking messages as read"""
    message_ids: List[str] = Field(..., min_items=1, description="List of message IDs to mark as read")
    
    @validator('message_ids')
    def validate_message_ids(cls, v):
        """Validate message IDs list"""
        if not v:
            raise ValueError("At least one message ID must be provided")
        # Remove duplicates while preserving order
        seen = set()
        unique_ids = []
        for msg_id in v:
            if msg_id not in seen:
                seen.add(msg_id)
                unique_ids.append(msg_id)
        return unique_ids
    
    class Config:
        json_schema_extra = {
            "example": {
                "message_ids": ["wa_msg_12345", "wa_msg_12346", "wa_msg_12347"]
            }
        }

# ============================================================================
# 🆕 NEW: REAL-TIME NOTIFICATION REQUEST SCHEMAS
# ============================================================================

class MarkLeadAsReadRequest(BaseModel):
    """🆕 Request schema for marking entire lead conversation as read"""
    lead_id: str = Field(..., description="Lead ID to mark as read")
    force_update: bool = Field(default=False, description="Force update even if no unread messages")
    
    class Config:
        json_schema_extra = {
            "example": {
                "lead_id": "LD-1001",
                "force_update": False
            }
        }

class UnreadStatusRequest(BaseModel):
    """🆕 Request schema for checking unread status"""
    lead_ids: Optional[List[str]] = Field(None, description="Specific lead IDs to check (if None, check all)")
    include_details: bool = Field(default=False, description="Include detailed unread message information")
    
    @validator('lead_ids')
    def validate_lead_ids(cls, v):
        """Remove duplicates from lead IDs if provided"""
        if v:
            return list(set(v))  # Remove duplicates
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "lead_ids": ["LD-1001", "LD-1002", "LD-1003"],
                "include_details": True
            }
        }

class RealtimeConnectionRequest(BaseModel):
    """🆕 Request schema for establishing real-time connection"""
    user_agent: Optional[str] = Field(None, description="User agent for connection tracking")
    timezone: Optional[str] = Field(None, description="User timezone for timestamp display")
    connection_id: Optional[str] = Field(None, description="Client-generated connection ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_agent": "Mozilla/5.0 Chrome/120.0.0.0",
                "timezone": "Asia/Kolkata",
                "connection_id": "conn_abc123"
            }
        }

# ============================================================================
# EXISTING SCHEMAS (KEEP AS-IS)
# ============================================================================

class ChatHistoryRequest(BaseModel):
    """Request schema for fetching chat history with pagination"""
    limit: int = Field(default=50, ge=1, le=100, description="Number of messages to fetch (1-100)")
    offset: int = Field(default=0, ge=0, description="Number of messages to skip for pagination")
    include_media: bool = Field(default=True, description="Whether to include media message details")
    
    class Config:
        json_schema_extra = {
            "example": {
                "limit": 50,
                "offset": 0,
                "include_media": True
            }
        }

class ActiveChatsRequest(BaseModel):
    """Request schema for fetching active chats list"""
    limit: int = Field(default=50, ge=1, le=100, description="Number of chats to fetch")
    include_unread_only: bool = Field(default=False, description="Only show chats with unread messages")
    sort_by: str = Field(default="last_activity", description="Sort criteria")
    
    @validator('sort_by')
    def validate_sort_criteria(cls, v):
        """Validate sort criteria"""
        allowed_sorts = ["last_activity", "unread_count", "total_messages", "lead_name"]
        if v not in allowed_sorts:
            raise ValueError(f"sort_by must be one of: {', '.join(allowed_sorts)}")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "limit": 25,
                "include_unread_only": False,
                "sort_by": "last_activity"
            }
        }

# ============================================================================
# WEBHOOK REQUEST SCHEMAS (KEEP AS-IS)
# ============================================================================

class WebhookVerificationRequest(BaseModel):
    """Schema for webhook verification (if needed by mydreamstechnology)"""
    hub_mode: str = Field(..., alias="hub.mode")
    hub_challenge: str = Field(..., alias="hub.challenge") 
    hub_verify_token: str = Field(..., alias="hub.verify_token")
    
    class Config:
        allow_population_by_field_name = True
        json_schema_extra = {
            "example": {
                "hub.mode": "subscribe",
                "hub.challenge": "1234567890",
                "hub.verify_token": "your_verify_token"
            }
        }

class WebhookMessageData(BaseModel):
    """Schema for individual message in webhook payload"""
    id: str = Field(..., description="WhatsApp message ID")
    type: str = Field(..., description="Message type (text, image, document, etc.)")
    timestamp: str = Field(..., description="Message timestamp")
    from_: str = Field(..., alias="from", description="Sender phone number")
    to: Optional[str] = Field(None, description="Recipient phone number")
    
    # Message content based on type
    text: Optional[Dict[str, str]] = Field(None, description="Text message content")
    image: Optional[Dict[str, Any]] = Field(None, description="Image message content")
    document: Optional[Dict[str, Any]] = Field(None, description="Document message content")
    audio: Optional[Dict[str, Any]] = Field(None, description="Audio message content")
    video: Optional[Dict[str, Any]] = Field(None, description="Video message content")
    location: Optional[Dict[str, Any]] = Field(None, description="Location message content")
    contact: Optional[Dict[str, Any]] = Field(None, description="Contact message content")
    
    class Config:
        allow_population_by_field_name = True
        json_schema_extra = {
            "example": {
                "id": "wa_msg_12345",
                "type": "text",
                "timestamp": "1642234200",
                "from": "919876543210",
                "text": {
                    "body": "Hi, I'm interested in your courses"
                }
            }
        }

class WebhookStatusData(BaseModel):
    """Schema for message status update in webhook"""
    id: str = Field(..., description="WhatsApp message ID")
    status: str = Field(..., description="New message status")
    timestamp: str = Field(..., description="Status update timestamp")
    recipient_id: str = Field(..., description="Recipient phone number")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "wa_msg_12345",
                "status": "delivered",
                "timestamp": "1642234260",
                "recipient_id": "919876543210"
            }
        }

class WebhookChangeData(BaseModel):
    """Schema for webhook change data"""
    field: str = Field(..., description="Changed field")
    value: Dict[str, Any] = Field(..., description="Change value data")
    
    class Config:
        json_schema_extra = {
            "example": {
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "919876543210"},
                    "messages": [
                        {
                            "id": "wa_msg_12345",
                            "type": "text",
                            "from": "919876543210",
                            "text": {"body": "Hello"}
                        }
                    ]
                }
            }
        }

class WebhookEntryData(BaseModel):
    """Schema for webhook entry"""
    id: str = Field(..., description="Business account ID")
    changes: List[WebhookChangeData] = Field(..., description="List of changes")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "business_account_id_123",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messages": [{"id": "wa_msg_12345", "type": "text"}]
                        }
                    }
                ]
            }
        }

class WebhookPayloadRequest(BaseModel):
    """Complete webhook payload request schema"""
    object: str = Field(..., description="Webhook object type")
    entry: List[WebhookEntryData] = Field(..., description="Webhook entries")
    
    class Config:
        json_schema_extra = {
            "example": {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "id": "business_account_id",
                        "changes": [
                            {
                                "field": "messages",
                                "value": {
                                    "messaging_product": "whatsapp",
                                    "messages": [
                                        {
                                            "id": "wa_msg_12345",
                                            "type": "text",
                                            "from": "919876543210",
                                            "text": {"body": "Hello"}
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
        }

# ============================================================================
# API RESPONSE SCHEMAS
# ============================================================================

class MessageResponse(BaseModel):
    """Response schema for individual message"""
    id: str = Field(..., description="Internal message ID")
    message_id: str = Field(..., description="WhatsApp message ID")
    direction: str = Field(..., description="Message direction (incoming/outgoing)")
    message_type: str = Field(..., description="Message type")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(..., description="Message timestamp")
    status: str = Field(..., description="Message status")
    is_read: bool = Field(..., description="Whether message is read")
    sent_by_name: Optional[str] = Field(None, description="Name of sender (for outgoing messages)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "msg_internal_123",
                "message_id": "wa_msg_12345",
                "direction": "incoming",
                "message_type": "text",
                "content": "Hi, I'm interested in your courses",
                "timestamp": "2024-01-15T10:30:00Z",
                "status": "delivered",
                "is_read": False,
                "sent_by_name": None
            }
        }

class ChatHistoryResponse(BaseModel):
    """Response schema for chat history"""
    success: bool = Field(default=True, description="Response success status")
    lead_id: str = Field(..., description="Lead ID")
    lead_name: str = Field(..., description="Lead name")
    phone_number: str = Field(..., description="Lead phone number")
    messages: List[MessageResponse] = Field(..., description="List of messages")
    total_messages: int = Field(..., description="Total message count")
    unread_count: int = Field(..., description="Unread message count")
    last_activity: Optional[datetime] = Field(None, description="Last message timestamp")
    pagination: Optional[Dict[str, Any]] = Field(None, description="Pagination information")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "lead_id": "LD-1001",
                "lead_name": "John Smith",
                "phone_number": "919876543210",
                "messages": [
                    {
                        "id": "msg_1",
                        "direction": "outgoing",
                        "content": "Hi! Thanks for your interest.",
                        "timestamp": "2024-01-15T10:00:00Z",
                        "sent_by_name": "Sales Agent"
                    }
                ],
                "total_messages": 5,
                "unread_count": 2,
                "last_activity": "2024-01-15T10:30:00Z",
                "pagination": {
                    "current_page": 1,
                    "has_next": True,
                    "has_prev": False
                }
            }
        }

class ActiveChatItem(BaseModel):
    """Schema for individual active chat item"""
    lead_id: str = Field(..., description="Lead ID")
    lead_name: str = Field(..., description="Lead name")
    phone_number: str = Field(..., description="Phone number")
    assigned_to: Optional[str] = Field(None, description="Assigned user email")
    assigned_to_name: Optional[str] = Field(None, description="Assigned user name")
    last_message: Optional[MessageResponse] = Field(None, description="Last message preview")
    unread_count: int = Field(default=0, description="Unread message count")
    total_messages: int = Field(default=0, description="Total message count")
    last_activity: Optional[datetime] = Field(None, description="Last activity timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "lead_id": "LD-1001",
                "lead_name": "John Smith",
                "phone_number": "919876543210",
                "assigned_to": "john.doe@leadg.com",
                "assigned_to_name": "John Doe",
                "last_message": {
                    "content": "Thanks for the information!",
                    "direction": "incoming",
                    "timestamp": "2024-01-15T10:30:00Z"
                },
                "unread_count": 2,
                "total_messages": 5,
                "last_activity": "2024-01-15T10:30:00Z"
            }
        }

class ActiveChatsResponse(BaseModel):
    """Response schema for active chats list"""
    success: bool = Field(default=True, description="Response success status")
    chats: List[ActiveChatItem] = Field(..., description="List of active chats")
    total_chats: int = Field(..., description="Total number of active chats")
    total_unread: int = Field(default=0, description="Total unread messages across all chats")
    user_permissions: Dict[str, Any] = Field(..., description="User permission context")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "chats": [
                    {
                        "lead_id": "LD-1001",
                        "lead_name": "John Smith",
                        "unread_count": 2,
                        "last_activity": "2024-01-15T10:30:00Z"
                    }
                ],
                "total_chats": 15,
                "total_unread": 8,
                "user_permissions": {
                    "role": "user",
                    "can_see_all_chats": False
                }
            }
        }

class SendMessageResponse(BaseModel):
    """Response schema for sending messages"""
    success: bool = Field(..., description="Whether message was sent successfully")
    message_id: str = Field(..., description="WhatsApp message ID")
    lead_id: str = Field(..., description="Lead ID")
    content: str = Field(..., description="Message content sent")
    timestamp: datetime = Field(..., description="When message was sent")
    status: str = Field(..., description="Initial message status")
    sent_by: str = Field(..., description="User who sent the message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message_id": "wa_msg_12345",
                "lead_id": "LD-1001",
                "content": "Thanks for your interest! Let me share more details.",
                "timestamp": "2024-01-15T10:30:00Z",
                "status": "sent",
                "sent_by": "john.doe@leadg.com"
            }
        }

class MarkReadResponse(BaseModel):
    """Response schema for marking messages as read"""
    success: bool = Field(..., description="Operation success status")
    marked_count: int = Field(..., description="Number of messages marked as read")
    lead_id: str = Field(..., description="Lead ID")
    new_unread_count: int = Field(..., description="Updated unread count for lead")
    message_ids: List[str] = Field(..., description="List of message IDs that were marked")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "marked_count": 3,
                "lead_id": "LD-1001",
                "new_unread_count": 0,
                "message_ids": ["wa_msg_12345", "wa_msg_12346", "wa_msg_12347"]
            }
        }

# ============================================================================
# 🆕 NEW: REAL-TIME NOTIFICATION RESPONSE SCHEMAS
# ============================================================================

class RealtimeNotification(BaseModel):
    """🆕 Base schema for real-time notifications"""
    type: str = Field(..., description="Notification type")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Notification timestamp")
    user_id: Optional[str] = Field(None, description="Target user ID (if user-specific)")
    data: Dict[str, Any] = Field(..., description="Notification payload data")
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "new_whatsapp_message",
                "timestamp": "2024-01-15T10:30:00Z",
                "user_id": "user_123",
                "data": {
                    "lead_id": "LD-1001",
                    "lead_name": "John Smith",
                    "message_preview": "Hi, I'm interested in..."
                }
            }
        }

class NewMessageNotification(BaseModel):
    """🆕 Schema for new WhatsApp message notifications"""
    type: str = Field(default="new_whatsapp_message", description="Always 'new_whatsapp_message'")
    lead_id: str = Field(..., description="Lead ID that received message")
    lead_name: str = Field(..., description="Lead name")
    message_preview: str = Field(..., description="Preview of message content (first 50 chars)")
    timestamp: str = Field(..., description="Message timestamp (ISO format)")
    direction: str = Field(..., description="Message direction (incoming/outgoing)")
    message_id: str = Field(..., description="WhatsApp message ID")
    unread_count: int = Field(default=1, description="New unread count for this lead")
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "new_whatsapp_message",
                "lead_id": "LD-1001",
                "lead_name": "John Smith",
                "message_preview": "Hi, I'm interested in your courses...",
                "timestamp": "2024-01-15T10:30:00Z",
                "direction": "incoming",
                "message_id": "wa_msg_12345",
                "unread_count": 3
            }
        }

class LeadMarkedReadNotification(BaseModel):
    """🆕 Schema for lead marked as read notifications"""
    type: str = Field(default="lead_marked_read", description="Always 'lead_marked_read'")
    lead_id: str = Field(..., description="Lead ID that was marked as read")
    lead_name: Optional[str] = Field(None, description="Lead name")
    marked_by_user: str = Field(..., description="User email who marked as read")
    unread_leads: List[str] = Field(..., description="Updated list of leads with unread messages")
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "lead_marked_read",
                "lead_id": "LD-1001",
                "lead_name": "John Smith", 
                "marked_by_user": "john.doe@leadg.com",
                "unread_leads": ["LD-1002", "LD-1003"]
            }
        }

class UnreadLeadsSyncNotification(BaseModel):
    """🆕 Schema for initial unread leads synchronization"""
    type: str = Field(default="unread_leads_sync", description="Always 'unread_leads_sync'")
    unread_leads: List[str] = Field(..., description="List of lead IDs with unread messages")
    total_unread_count: int = Field(..., description="Total unread messages count")
    sync_timestamp: str = Field(..., description="Sync timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "unread_leads_sync",
                "unread_leads": ["LD-1001", "LD-1002", "LD-1005"],
                "total_unread_count": 8,
                "sync_timestamp": "2024-01-15T10:30:00Z"
            }
        }

class ConnectionEstablishedNotification(BaseModel):
    """🆕 Schema for real-time connection established notification"""
    type: str = Field(default="connection_established", description="Always 'connection_established'")
    user_email: str = Field(..., description="Connected user email")
    connection_id: str = Field(..., description="Unique connection ID")
    timestamp: str = Field(..., description="Connection timestamp")
    initial_unread_leads: List[str] = Field(..., description="Initial unread leads for this user")
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "connection_established",
                "user_email": "john.doe@leadg.com",
                "connection_id": "conn_abc123",
                "timestamp": "2024-01-15T10:30:00Z",
                "initial_unread_leads": ["LD-1001", "LD-1003"]
            }
        }

class HeartbeatNotification(BaseModel):
    """🆕 Schema for connection heartbeat notifications"""
    type: str = Field(default="heartbeat", description="Always 'heartbeat'")
    timestamp: str = Field(..., description="Heartbeat timestamp")
    active_connections: int = Field(..., description="Number of active connections")
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "heartbeat",
                "timestamp": "2024-01-15T10:30:00Z",
                "active_connections": 5
            }
        }

class MarkLeadAsReadResponse(BaseModel):
    """🆕 Response schema for marking lead as read"""
    success: bool = Field(..., description="Operation success status")
    lead_id: str = Field(..., description="Lead ID that was marked as read")
    marked_messages: int = Field(..., description="Number of messages marked as read")
    icon_state: str = Field(..., description="New icon state (grey/green)")
    message: str = Field(..., description="Success message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "lead_id": "LD-1001",
                "marked_messages": 3,
                "icon_state": "grey",
                "message": "Lead marked as read successfully"
            }
        }

class LeadUnreadStatusResponse(BaseModel):
    """🆕 Response schema for individual lead unread status"""
    success: bool = Field(default=True, description="Response success status")
    lead_id: str = Field(..., description="Lead ID")
    lead_name: Optional[str] = Field(None, description="Lead name")
    has_unread: bool = Field(..., description="Whether lead has unread messages")
    unread_count: int = Field(..., description="Number of unread messages")
    icon_state: str = Field(..., description="Icon state (green/grey)")
    last_activity: Optional[datetime] = Field(None, description="Last WhatsApp activity")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "lead_id": "LD-1001",
                "lead_name": "John Smith",
                "has_unread": True,
                "unread_count": 3,
                "icon_state": "green",
                "last_activity": "2024-01-15T10:30:00Z"
            }
        }

class UnreadStatusSummary(BaseModel):
    """🆕 Individual unread status item for bulk response"""
    lead_id: str = Field(..., description="Lead ID")
    lead_name: Optional[str] = Field(None, description="Lead name")
    unread_count: int = Field(..., description="Number of unread messages")
    last_activity: Optional[datetime] = Field(None, description="Last WhatsApp activity")
    
    class Config:
        json_schema_extra = {
            "example": {
                "lead_id": "LD-1001",
                "lead_name": "John Smith",
                "unread_count": 3,
                "last_activity": "2024-01-15T10:30:00Z"
            }
        }

class BulkUnreadStatusResponse(BaseModel):
    """🆕 Response schema for bulk unread status check"""
    success: bool = Field(default=True, description="Response success status")
    unread_leads: List[str] = Field(..., description="List of lead IDs with unread messages")
    unread_details: List[UnreadStatusSummary] = Field(..., description="Detailed unread information")
    total_unread_leads: int = Field(..., description="Total number of leads with unread messages")
    total_unread_messages: int = Field(..., description="Total unread messages across all leads")
    user_role: str = Field(..., description="User role for context")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "unread_leads": ["LD-1001", "LD-1002", "LD-1005"],
                "unread_details": [
                    {
                        "lead_id": "LD-1001",
                        "lead_name": "John Smith",
                        "unread_count": 3,
                        "last_activity": "2024-01-15T10:30:00Z"
                    }
                ],
                "total_unread_leads": 3,
                "total_unread_messages": 8,
                "user_role": "user"
            }
        }

# ============================================================================
# WEBHOOK RESPONSE SCHEMAS (KEEP AS-IS)
# ============================================================================

class WebhookProcessingResponse(BaseModel):
    """Response schema for webhook processing"""
    success: bool = Field(..., description="Webhook processing success")
    processed_messages: int = Field(default=0, description="Number of messages processed")
    processed_statuses: int = Field(default=0, description="Number of status updates processed")
    errors: int = Field(default=0, description="Number of processing errors")
    details: Optional[Dict[str, Any]] = Field(None, description="Detailed processing results")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "processed_messages": 2,
                "processed_statuses": 1,
                "errors": 0,
                "details": {
                    "new_leads_contacted": 1,
                    "existing_conversations_updated": 1
                }
            }
        }

class WebhookVerificationResponse(BaseModel):
    """Response schema for webhook verification"""
    hub_challenge: str = Field(..., description="Challenge token to return")
    
    class Config:
        json_schema_extra = {
            "example": {
                "hub_challenge": "1234567890"
            }
        }

# ============================================================================
# ERROR RESPONSE SCHEMAS (KEEP AS-IS)
# ============================================================================

class WhatsAppErrorResponse(BaseModel):
    """Standard error response schema for WhatsApp endpoints"""
    success: bool = Field(default=False, description="Always false for error responses")
    error: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Specific error code")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "Lead not found or access denied",
                "error_code": "LEAD_ACCESS_DENIED",
                "details": {
                    "lead_id": "LD-1001",
                    "user_email": "user@example.com"
                },
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }

class ValidationErrorResponse(BaseModel):
    """Schema for validation error responses"""
    success: bool = Field(default=False)
    error: str = Field(default="Validation error")
    validation_errors: List[Dict[str, str]] = Field(..., description="List of validation errors")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "Validation error",
                "validation_errors": [
                    {
                        "field": "message",
                        "error": "Message cannot be empty"
                    },
                    {
                        "field": "lead_id",
                        "error": "Invalid lead ID format"
                    }
                ]
            }
        }

# ============================================================================
# STATISTICS & ANALYTICS SCHEMAS (KEEP AS-IS)
# ============================================================================

class WhatsAppStatsResponse(BaseModel):
    """Response schema for WhatsApp statistics"""
    success: bool = Field(default=True)
    total_messages: int = Field(..., description="Total messages in system")
    incoming_messages: int = Field(..., description="Total incoming messages")
    outgoing_messages: int = Field(..., description="Total outgoing messages")
    total_unread: int = Field(..., description="Total unread messages")
    active_conversations: int = Field(..., description="Leads with WhatsApp activity")
    messages_today: int = Field(..., description="Messages sent/received today")
    top_active_leads: List[Dict[str, Any]] = Field(..., description="Most active leads by message count")
    user_stats: Optional[Dict[str, Any]] = Field(None, description="User-specific statistics")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "total_messages": 150,
                "incoming_messages": 85,
                "outgoing_messages": 65,
                "total_unread": 12,
                "active_conversations": 25,
                "messages_today": 8,
                "top_active_leads": [
                    {"lead_id": "LD-1001", "lead_name": "John Smith", "message_count": 12},
                    {"lead_id": "LD-1002", "lead_name": "Jane Doe", "message_count": 8}
                ],
                "user_stats": {
                    "user_messages_sent": 15,
                    "user_conversations": 8
                }
            }
        }

# ============================================================================
# 🆕 NEW: REAL-TIME CONNECTION SCHEMAS
# ============================================================================

class SSEConnectionInfo(BaseModel):
    """🆕 Schema for SSE connection information"""
    user_email: str = Field(..., description="Connected user email")
    connection_id: str = Field(..., description="Unique connection identifier")
    connected_at: datetime = Field(..., description="Connection establishment time")
    user_agent: Optional[str] = Field(None, description="User agent string")
    ip_address: Optional[str] = Field(None, description="User IP address")
    timezone: Optional[str] = Field(None, description="User timezone")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_email": "john.doe@leadg.com",
                "connection_id": "conn_abc123_456",
                "connected_at": "2024-01-15T10:30:00Z",
                "user_agent": "Mozilla/5.0 Chrome/120.0.0.0",
                "ip_address": "192.168.1.100",
                "timezone": "Asia/Kolkata"
            }
        }

class RealtimeConnectionStatus(BaseModel):
    """🆕 Schema for real-time connection status"""
    is_connected: bool = Field(..., description="Whether user has active real-time connection")
    connection_count: int = Field(..., description="Number of active connections for user")
    last_connected: Optional[datetime] = Field(None, description="Last connection time")
    last_activity: Optional[datetime] = Field(None, description="Last activity time")
    connection_quality: str = Field(..., description="Connection quality (good/fair/poor)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "is_connected": True,
                "connection_count": 2,
                "last_connected": "2024-01-15T10:30:00Z",
                "last_activity": "2024-01-15T10:35:00Z",
                "connection_quality": "good"
            }
        }

# ============================================================================
# 🆕 NEW: BULK OPERATIONS SCHEMAS  
# ============================================================================

class BulkMarkReadRequest(BaseModel):
    """🆕 Request schema for bulk marking leads as read"""
    lead_ids: List[str] = Field(..., min_items=1, max_items=50, description="Lead IDs to mark as read")
    mark_all_messages: bool = Field(default=True, description="Mark all messages as read vs just latest")
    
    @validator('lead_ids')
    def validate_lead_ids(cls, v):
        """Remove duplicates and validate lead IDs"""
        if not v:
            raise ValueError("At least one lead ID must be provided")
        return list(set(v))  # Remove duplicates
    
    class Config:
        json_schema_extra = {
            "example": {
                "lead_ids": ["LD-1001", "LD-1002", "LD-1003"],
                "mark_all_messages": True
            }
        }

class BulkMarkReadResponse(BaseModel):
    """🆕 Response schema for bulk mark as read operation"""
    success: bool = Field(..., description="Overall operation success")
    processed_leads: int = Field(..., description="Number of leads successfully processed")
    failed_leads: int = Field(..., description="Number of leads that failed to process")
    results: List[Dict[str, Any]] = Field(..., description="Detailed results per lead")
    total_messages_marked: int = Field(..., description="Total messages marked as read")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "processed_leads": 2,
                "failed_leads": 1,
                "results": [
                    {"lead_id": "LD-1001", "success": True, "messages_marked": 3},
                    {"lead_id": "LD-1002", "success": True, "messages_marked": 1},
                    {"lead_id": "LD-1003", "success": False, "error": "Access denied"}
                ],
                "total_messages_marked": 4
            }
        }

# ============================================================================
# UTILITY SCHEMAS (KEEP AS-IS)
# ============================================================================

class HealthCheckResponse(BaseModel):
    """Response schema for WhatsApp service health check"""
    success: bool = Field(default=True)
    service: str = Field(default="whatsapp_chat")
    status: str = Field(..., description="Service status")
    database_connected: bool = Field(..., description="Database connection status")
    whatsapp_api_accessible: bool = Field(..., description="WhatsApp API accessibility")
    total_active_chats: int = Field(..., description="Current active chat count")
    last_webhook_received: Optional[datetime] = Field(None, description="Last webhook timestamp")
    realtime_connections: int = Field(default=0, description="Active real-time connections")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "service": "whatsapp_chat",
                "status": "healthy",
                "database_connected": True,
                "whatsapp_api_accessible": True,
                "total_active_chats": 25,
                "last_webhook_received": "2024-01-15T10:30:00Z",
                "realtime_connections": 8
            }
        }