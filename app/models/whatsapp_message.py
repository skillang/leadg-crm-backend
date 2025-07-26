# app/models/whatsapp_message.py - WhatsApp Message Models for Chat Functionality

from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum

# ============================================================================
# ENUMERATIONS
# ============================================================================

class MessageDirection(str, Enum):
    """Message direction enumeration"""
    INCOMING = "incoming"  # From customer to CRM
    OUTGOING = "outgoing"  # From CRM to customer

class MessageType(str, Enum):
    """WhatsApp message type enumeration"""
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    LOCATION = "location"
    CONTACT = "contact"
    TEMPLATE = "template"
    BUTTON = "button"
    LIST = "list"

class MessageStatus(str, Enum):
    """Message delivery status enumeration"""
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    PENDING = "pending"

# ============================================================================
# CORE WHATSAPP MESSAGE MODELS
# ============================================================================

class WhatsAppMessage(BaseModel):
    """Core WhatsApp message model for database storage"""
    message_id: str = Field(..., description="Unique WhatsApp message ID from mydreamstechnology")
    lead_id: str = Field(..., description="Lead ID this message belongs to")
    phone_number: str = Field(..., description="Phone number (normalized format)")
    direction: MessageDirection = Field(..., description="Message direction (incoming/outgoing)")
    message_type: MessageType = Field(default=MessageType.TEXT, description="Type of message")
    content: str = Field(..., description="Message content/text")
    timestamp: datetime = Field(..., description="When message was sent/received")
    status: MessageStatus = Field(default=MessageStatus.SENT, description="Message delivery status")
    
    # User tracking (for outgoing messages)
    sent_by_user_id: Optional[str] = Field(None, description="User ID who sent the message (outgoing only)")
    sent_by_name: Optional[str] = Field(None, description="User name who sent the message")
    
    # Read tracking
    is_read: bool = Field(default=False, description="Whether message has been read (incoming only)")
    read_at: Optional[datetime] = Field(None, description="When message was marked as read")
    read_by_user_id: Optional[str] = Field(None, description="User who marked as read")
    
    # Media/File information (for non-text messages)
    media_url: Optional[str] = Field(None, description="URL to media file if applicable")
    media_filename: Optional[str] = Field(None, description="Original filename for documents")
    media_mime_type: Optional[str] = Field(None, description="MIME type of media")
    media_size: Optional[int] = Field(None, description="File size in bytes")
    
    # Raw webhook data for debugging
    raw_webhook_data: Optional[Dict[str, Any]] = Field(None, description="Original webhook payload")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When record was created in CRM")
    updated_at: Optional[datetime] = Field(None, description="When record was last updated")
    
    @validator('phone_number')
    def normalize_phone_number(cls, v):
        """Normalize phone number format"""
        if not v:
            return v
        # Remove all non-digits and normalize
        digits_only = ''.join(filter(str.isdigit, v))
        # Ensure it starts with country code (assume +91 for India if not present)
        if len(digits_only) == 10:
            return f"91{digits_only}"
        return digits_only
    
    @validator('content')
    def validate_content(cls, v):
        """Validate message content"""
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        return v.strip()
    
    class Config:
        json_schema_extra = {
            "example": {
                "message_id": "wa_msg_12345",
                "lead_id": "LD-1001",
                "phone_number": "919876543210",
                "direction": "incoming",
                "message_type": "text",
                "content": "Hi, I'm interested in your courses",
                "timestamp": "2024-01-15T10:30:00Z",
                "status": "delivered",
                "is_read": False
            }
        }

# ============================================================================
# REQUEST MODELS
# ============================================================================

class WhatsAppMessageCreate(BaseModel):
    """Model for creating new WhatsApp messages"""
    lead_id: str = Field(..., description="Lead ID to associate message with")
    phone_number: str = Field(..., description="Phone number to send to")
    content: str = Field(..., description="Message content")
    message_type: MessageType = Field(default=MessageType.TEXT, description="Type of message")
    
    # Optional user context (for outgoing messages)
    sent_by_user_id: Optional[str] = Field(None, description="User sending the message")
    sent_by_name: Optional[str] = Field(None, description="Name of user sending message")
    
    @validator('content')
    def validate_message_content(cls, v):
        """Validate message content"""
        if not v or not v.strip():
            raise ValueError("Message content is required")
        if len(v.strip()) > 4096:  # WhatsApp text limit
            raise ValueError("Message content too long (max 4096 characters)")
        return v.strip()
    
    @validator('phone_number')
    def validate_phone_number(cls, v):
        """Validate phone number format"""
        if not v:
            raise ValueError("Phone number is required")
        # Basic validation - detailed normalization happens in service
        digits_only = ''.join(filter(str.isdigit, v))
        if len(digits_only) < 10:
            raise ValueError("Invalid phone number format")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "lead_id": "LD-1001",
                "phone_number": "+91-9876543210",
                "content": "Hi! Thanks for your interest. Let me share more details.",
                "message_type": "text",
                "sent_by_user_id": "user123",
                "sent_by_name": "John Doe"
            }
        }

class SendChatMessageRequest(BaseModel):
    """Request model for sending a message in chat conversation"""
    message: str = Field(..., description="Message text to send")
    
    @validator('message')
    def validate_message(cls, v):
        if not v or not v.strip():
            raise ValueError("Message cannot be empty")
        if len(v.strip()) > 4096:
            raise ValueError("Message too long (max 4096 characters)")
        return v.strip()
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Thanks for your interest! Let me share more details about our programs."
            }
        }

class MarkMessageReadRequest(BaseModel):
    """Request model for marking messages as read"""
    message_ids: List[str] = Field(..., description="List of message IDs to mark as read")
    
    @validator('message_ids')
    def validate_message_ids(cls, v):
        if not v:
            raise ValueError("At least one message ID must be provided")
        return list(set(v))  # Remove duplicates
    
    class Config:
        json_schema_extra = {
            "example": {
                "message_ids": ["wa_msg_12345", "wa_msg_12346"]
            }
        }

# ============================================================================
# WEBHOOK MODELS
# ============================================================================

class WebhookIncomingMessage(BaseModel):
    """Model for processing incoming webhook messages from mydreamstechnology"""
    id: str = Field(..., description="WhatsApp message ID")
    type: str = Field(..., description="Message type from webhook")
    timestamp: str = Field(..., description="Timestamp from webhook")
    from_: str = Field(..., alias="from", description="Sender phone number")
    to: Optional[str] = Field(None, description="Receiver phone number")
    
    # Message content (varies by type)
    text: Optional[Dict[str, str]] = Field(None, description="Text message content")
    image: Optional[Dict[str, Any]] = Field(None, description="Image message content")
    document: Optional[Dict[str, Any]] = Field(None, description="Document message content")
    audio: Optional[Dict[str, Any]] = Field(None, description="Audio message content")
    video: Optional[Dict[str, Any]] = Field(None, description="Video message content")
    
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

class WebhookStatusUpdate(BaseModel):
    """Model for processing message status updates from webhook"""
    id: str = Field(..., description="WhatsApp message ID")
    status: str = Field(..., description="New status (sent/delivered/read/failed)")
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

class WebhookPayload(BaseModel):
    """Complete webhook payload from mydreamstechnology"""
    object: str = Field(..., description="Webhook object type")
    entry: List[Dict[str, Any]] = Field(..., description="Webhook entry data")
    
    # Raw payload for processing
    messages: Optional[List[WebhookIncomingMessage]] = Field(None, description="Incoming messages")
    statuses: Optional[List[WebhookStatusUpdate]] = Field(None, description="Status updates")
    
    class Config:
        json_schema_extra = {
            "example": {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "id": "business_account_id",
                        "changes": [
                            {
                                "value": {
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
# RESPONSE MODELS
# ============================================================================

class WhatsAppMessageResponse(BaseModel):
    """Response model for individual WhatsApp messages"""
    id: str = Field(..., description="Message ID")
    message_id: str = Field(..., description="WhatsApp message ID")
    lead_id: str = Field(..., description="Associated lead ID")
    direction: MessageDirection = Field(..., description="Message direction")
    message_type: MessageType = Field(..., description="Message type")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(..., description="Message timestamp")
    status: MessageStatus = Field(..., description="Delivery status")
    is_read: bool = Field(..., description="Read status")
    sent_by_name: Optional[str] = Field(None, description="Sender name (outgoing messages)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "msg_internal_123",
                "message_id": "wa_msg_12345",
                "lead_id": "LD-1001",
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
    """Response model for chat history"""
    lead_id: str = Field(..., description="Lead ID")
    lead_name: str = Field(..., description="Lead name")
    phone_number: str = Field(..., description="Lead phone number")
    messages: List[WhatsAppMessageResponse] = Field(..., description="Chat messages")
    total_messages: int = Field(..., description="Total message count")
    unread_count: int = Field(..., description="Unread message count")
    last_activity: Optional[datetime] = Field(None, description="Last message timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
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
                    },
                    {
                        "id": "msg_2",
                        "direction": "incoming",
                        "content": "Yes, I want to know more",
                        "timestamp": "2024-01-15T10:05:00Z",
                        "is_read": False
                    }
                ],
                "total_messages": 2,
                "unread_count": 1,
                "last_activity": "2024-01-15T10:05:00Z"
            }
        }

class ActiveChatResponse(BaseModel):
    """Response model for active chat list item"""
    lead_id: str = Field(..., description="Lead ID")
    lead_name: str = Field(..., description="Lead name")
    phone_number: str = Field(..., description="Phone number")
    assigned_to: Optional[str] = Field(None, description="Assigned user email")
    assigned_to_name: Optional[str] = Field(None, description="Assigned user name")
    last_message: Optional[WhatsAppMessageResponse] = Field(None, description="Last message in conversation")
    unread_count: int = Field(default=0, description="Unread message count")
    total_messages: int = Field(default=0, description="Total message count")
    last_activity: Optional[datetime] = Field(None, description="Last WhatsApp activity")
    
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
                    "timestamp": "2024-01-15T10:30:00Z",
                    "is_read": False
                },
                "unread_count": 2,
                "total_messages": 5,
                "last_activity": "2024-01-15T10:30:00Z"
            }
        }

class ActiveChatsResponse(BaseModel):
    """Response model for active chats list"""
    chats: List[ActiveChatResponse] = Field(..., description="List of active chats")
    total_chats: int = Field(..., description="Total number of active chats")
    total_unread: int = Field(default=0, description="Total unread messages across all chats")
    
    class Config:
        json_schema_extra = {
            "example": {
                "chats": [
                    {
                        "lead_id": "LD-1001",
                        "lead_name": "John Smith",
                        "unread_count": 2,
                        "last_activity": "2024-01-15T10:30:00Z"
                    },
                    {
                        "lead_id": "LD-1002", 
                        "lead_name": "Jane Doe",
                        "unread_count": 0,
                        "last_activity": "2024-01-15T09:15:00Z"
                    }
                ],
                "total_chats": 2,
                "total_unread": 2
            }
        }

class SendMessageResponse(BaseModel):
    """Response model for sending messages"""
    success: bool = Field(..., description="Whether message was sent successfully")
    message_id: str = Field(..., description="WhatsApp message ID")
    lead_id: str = Field(..., description="Lead ID")
    content: str = Field(..., description="Message content sent")
    timestamp: datetime = Field(..., description="When message was sent")
    status: MessageStatus = Field(..., description="Initial message status")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message_id": "wa_msg_12345",
                "lead_id": "LD-1001",
                "content": "Thanks for your interest! Let me share more details.",
                "timestamp": "2024-01-15T10:30:00Z",
                "status": "sent"
            }
        }

# ============================================================================
# UTILITY MODELS
# ============================================================================

class UnreadMessagesSummary(BaseModel):
    """Summary of unread messages per user"""
    user_email: str = Field(..., description="User email")
    user_name: str = Field(..., description="User name")
    total_unread: int = Field(default=0, description="Total unread messages")
    leads_with_unread: int = Field(default=0, description="Number of leads with unread messages")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_email": "john.doe@leadg.com",
                "user_name": "John Doe", 
                "total_unread": 5,
                "leads_with_unread": 3
            }
        }

class WhatsAppStatistics(BaseModel):
    """WhatsApp usage statistics"""
    total_messages: int = Field(default=0, description="Total messages in system")
    incoming_messages: int = Field(default=0, description="Total incoming messages")
    outgoing_messages: int = Field(default=0, description="Total outgoing messages")
    total_unread: int = Field(default=0, description="Total unread messages")
    active_conversations: int = Field(default=0, description="Leads with WhatsApp activity")
    messages_today: int = Field(default=0, description="Messages sent/received today")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_messages": 150,
                "incoming_messages": 85,
                "outgoing_messages": 65,
                "total_unread": 12,
                "active_conversations": 25,
                "messages_today": 8
            }
        }