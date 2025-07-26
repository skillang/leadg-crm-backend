# app/schemas/whatsapp_chat.py - WhatsApp Chat API Request/Response Schemas

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
# WEBHOOK REQUEST SCHEMAS
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
# WEBHOOK RESPONSE SCHEMAS
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
# ERROR RESPONSE SCHEMAS
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
# STATISTICS & ANALYTICS SCHEMAS
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
# UTILITY SCHEMAS
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
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "service": "whatsapp_chat",
                "status": "healthy",
                "database_connected": True,
                "whatsapp_api_accessible": True,
                "total_active_chats": 25,
                "last_webhook_received": "2024-01-15T10:30:00Z"
            }
        }