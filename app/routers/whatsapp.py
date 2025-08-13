# app/routers/whatsapp.py - Enhanced WhatsApp Integration with Chat Functionality

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
import httpx
import logging
from datetime import datetime
from app.services.communication_service import CommunicationService
from ..utils.dependencies import get_current_user
from ..config.settings import settings
from ..config.database import get_database
from ..services.whatsapp_message_service import whatsapp_message_service
from ..schemas.whatsapp_chat import (
    SendChatMessageRequest, MarkMessagesReadRequest, ChatHistoryRequest,
    ActiveChatsRequest, WebhookPayloadRequest, WebhookProcessingResponse,
    ChatHistoryResponse, ActiveChatsResponse, SendMessageResponse,
    MarkReadResponse, WhatsAppErrorResponse
)
import os
import time

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WhatsApp Integration"])

# ================================
# CONFIGURATION
# ================================

WHATSAPP_CONFIG = {
    "base_url": os.getenv("WHATSAPP_BASE_URL", "https://wa.mydreamstechnology.in/api"),
    "license_number": os.getenv("WHATSAPP_LICENSE_NUMBER", ""),
    "api_key": os.getenv("WHATSAPP_API_KEY", "")
}

CMS_CONFIG = {
    "base_url": os.getenv("CMS_BASE_URL", "https://cms.skillang.com/api"),
    "templates_endpoint": os.getenv("CMS_TEMPLATES_ENDPOINT", "whatsapp-templates")
}

# ================================
# EXISTING PYDANTIC MODELS (Keep for backward compatibility)
# ================================

class SendTemplateRequest(BaseModel):
    template_name: str
    contact: str
    lead_name: str

class SendTextRequest(BaseModel):
    contact: str
    message: str

class ValidateContactRequest(BaseModel):
    contact: str

# ================================
# EXISTING UTILITY FUNCTIONS (Keep as-is)
# ================================

async def make_whatsapp_request(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Make authenticated request to WhatsApp API"""
    # Add authentication parameters
    params.update({
        "LicenseNumber": WHATSAPP_CONFIG["license_number"],
        "APIKey": WHATSAPP_CONFIG["api_key"]
    })
    
    url = f"{WHATSAPP_CONFIG['base_url']}/{endpoint}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            # Try to parse JSON response
            try:
                return response.json()
            except:
                return {"status": "success", "message": response.text}
                
    except httpx.HTTPError as e:
        logger.error(f"WhatsApp API error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"WhatsApp API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

async def fetch_templates_from_cms() -> List[Dict[str, Any]]:
    """Fetch WhatsApp templates from Strapi CMS"""
    url = f"{CMS_CONFIG['base_url']}/{CMS_CONFIG['templates_endpoint']}"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            # Extract templates from Strapi response format
            templates = data.get('data', [])
            
            # Filter only active templates
            active_templates = [
                template for template in templates 
                if template.get('Is_Active', False)
            ]
            
            return active_templates
            
    except Exception as e:
        logger.error(f"Failed to fetch templates from CMS: {str(e)}")
        # Return fallback templates if CMS is unavailable
        return [
            {
                "id": 1,
                "template_name": "nursing_promo_form_wa",
                "display_name": "Nursing Promo",
                "description": "form for nursing",
                "Is_Active": True
            },
            {
                "id": 2,
                "template_name": "lead_new",
                "display_name": "New lead",
                "description": "new lead welcome message",
                "Is_Active": True
            }
        ]

# ================================
# NEW: Helper function to store outgoing messages
# ================================
# ================================
# 🆕 NEW: WEBHOOK ENDPOINTS (Core Chat Functionality)
# ================================

@router.post("/webhook", response_model=WebhookProcessingResponse)
async def handle_whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Handle incoming WhatsApp webhook notifications from mydreamstechnology
    This endpoint receives real-time updates when customers send messages
    """
    try:
        # Get raw request body
        webhook_payload = await request.json()
        
        logger.info(f"Received WhatsApp webhook: {webhook_payload}")
        
        # Process webhook asynchronously for better performance
        background_tasks.add_task(
            whatsapp_message_service.process_incoming_webhook,
            webhook_payload
        )
        
        # Return immediate success response for webhook
        return WebhookProcessingResponse(
            success=True,
            processed_messages=0,  # Will be updated in background
            processed_statuses=0,
            errors=0,
            details={"status": "processing_in_background"}
        )
        
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Webhook processing failed: {str(e)}"
        )

@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = None,
    hub_challenge: str = None,
    hub_verify_token: str = None
):
    """
    Webhook verification endpoint (if required by mydreamstechnology)
    This is used during webhook setup to verify the endpoint
    """
    try:
        # Add your verification logic here if mydreamstechnology requires it
        # For now, just return the challenge
        if hub_mode == "subscribe" and hub_challenge:
            logger.info("Webhook verification successful")
            return {"hub_challenge": hub_challenge}
        
        raise HTTPException(status_code=400, detail="Invalid webhook verification")
        
    except Exception as e:
        logger.error(f"Webhook verification error: {str(e)}")
        raise HTTPException(status_code=400, detail="Webhook verification failed")

# ================================
# 🆕 NEW: CHAT MANAGEMENT ENDPOINTS
# ================================

@router.get("/active-chats", response_model=ActiveChatsResponse)
async def get_active_chats(
    limit: int = 50,
    include_unread_only: bool = False,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get list of leads with recent WhatsApp activity
    Users see only their assigned leads, admins see all leads with WhatsApp activity
    """
    try:
        result = await whatsapp_message_service.get_active_chats(
            current_user=current_user,
            limit=limit
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching active chats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch active chats: {str(e)}"
        )

@router.get("/lead-messages/{lead_id}", response_model=ChatHistoryResponse)
async def get_lead_whatsapp_history(
    lead_id: str,
    limit: int = 50,
    offset: int = 0,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get WhatsApp message history for a specific lead (UPDATED - Now fully functional)
    Includes complete chat history with pagination and permission checking
    """
    try:
        result = await whatsapp_message_service.get_chat_history(
            lead_id=lead_id,
            limit=limit,
            offset=offset,
            current_user=current_user
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching chat history for lead {lead_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch chat history: {str(e)}"
        )

@router.post("/leads/{lead_id}/send", response_model=SendMessageResponse)
async def send_message_in_chat(
    lead_id: str,
    request: SendChatMessageRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Send a message in an existing WhatsApp conversation
    Message is sent via WhatsApp API and stored in database for chat history
    """
    try:
        result = await whatsapp_message_service.send_and_store_message(
            lead_id=lead_id,
            message_content=request.message,
            current_user=current_user
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error sending message to lead {lead_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send message: {str(e)}"
        )

@router.patch("/messages/read", response_model=MarkReadResponse)
async def mark_messages_as_read(
    request: MarkMessagesReadRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Mark WhatsApp messages as read and update unread counts
    This updates the lead's unread message counter
    """
    try:
        # Extract lead_id from first message (assuming all messages are from same lead)
        # In a real implementation, you might want to group by lead_id
        from ..config.database import get_database
        db = get_database()
        
        # Get lead_id from first message
        first_message = await db.whatsapp_messages.find_one(
            {"message_id": request.message_ids[0]}
        )
        
        if not first_message:
            raise HTTPException(status_code=404, detail="Message not found")
        
        lead_id = first_message["lead_id"]
        
        result = await whatsapp_message_service.mark_messages_as_read(
            lead_id=lead_id,
            message_ids=request.message_ids,
            current_user=current_user
        )
        
        return MarkReadResponse(
            success=result["success"],
            marked_count=result["marked_as_read"],
            lead_id=lead_id,
            new_unread_count=0,  # Will be calculated in service
            message_ids=result["message_ids"]
        )
        
    except Exception as e:
        logger.error(f"Error marking messages as read: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mark messages as read: {str(e)}"
        )

# ================================
# 🆕 NEW: WHATSAPP STATISTICS & MONITORING
# ================================

@router.get("/stats")
async def get_whatsapp_statistics(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get WhatsApp usage statistics for dashboard"""
    try:
        from ..config.database import get_database
        db = get_database()
        
        user_role = current_user.get("role", "user")
        user_email = current_user.get("email", "")
        
        # Base stats
        stats = {}
        
        if user_role == "admin":
            # Admin sees all statistics
            stats["total_messages"] = await db.whatsapp_messages.count_documents({})
            stats["incoming_messages"] = await db.whatsapp_messages.count_documents({"direction": "incoming"})
            stats["outgoing_messages"] = await db.whatsapp_messages.count_documents({"direction": "outgoing"})
            stats["total_unread"] = await db.whatsapp_messages.count_documents({
                "direction": "incoming", 
                "is_read": False
            })
            stats["active_conversations"] = await db.leads.count_documents({
                "whatsapp_message_count": {"$gt": 0}
            })
        else:
            # Regular user sees only their assigned leads' stats
            user_leads = await db.leads.find({
                "$or": [
                    {"assigned_to": user_email},
                    {"co_assignees": user_email}
                ]
            }).to_list(length=None)
            
            user_lead_ids = [lead["lead_id"] for lead in user_leads]
            
            stats["total_messages"] = await db.whatsapp_messages.count_documents({
                "lead_id": {"$in": user_lead_ids}
            })
            stats["incoming_messages"] = await db.whatsapp_messages.count_documents({
                "lead_id": {"$in": user_lead_ids},
                "direction": "incoming"
            })
            stats["outgoing_messages"] = await db.whatsapp_messages.count_documents({
                "lead_id": {"$in": user_lead_ids},
                "direction": "outgoing"
            })
            stats["total_unread"] = await db.whatsapp_messages.count_documents({
                "lead_id": {"$in": user_lead_ids},
                "direction": "incoming",
                "is_read": False
            })
            stats["active_conversations"] = len([
                lead for lead in user_leads 
                if lead.get("whatsapp_message_count", 0) > 0
            ])
        
        # Messages today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        stats["messages_today"] = await db.whatsapp_messages.count_documents({
            "timestamp": {"$gte": today_start}
        })
        
        return {
            "success": True,
            **stats
        }
        
    except Exception as e:
        logger.error(f"Error fetching WhatsApp statistics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch statistics: {str(e)}"
        )

# ================================
# EXISTING ENDPOINTS (Keep for backward compatibility)
# ================================

@router.get("/account/status")
async def check_account_status(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Check WhatsApp account validity"""
    try:
        result = await make_whatsapp_request("accountvalidity.php", {})
        return {
            "success": True,
            "data": result,
            "message": "Account status checked successfully"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@router.post("/validate-contact")
async def validate_contact(
    request: ValidateContactRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Check if contact number is valid for WhatsApp"""
    try:
        result = await make_whatsapp_request("conversationvalidity.php", {
            "Contact": request.contact
        })
        return {
            "success": True,
            "data": result,
            "contact": request.contact,
            "message": "Contact validation completed"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "contact": request.contact
        }

@router.get("/templates")
async def get_available_templates(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get available WhatsApp templates from CMS"""
    try:
        templates = await fetch_templates_from_cms()
        
        # Format for frontend consumption
        formatted_templates = [
            {
                "id": template["id"],
                "template_name": template["template_name"],
                "display_name": template["display_name"],
                "body": template["body"],
                "is_active": template["Is_Active"]
            }
            for template in templates
        ]
        
        return {
            "success": True,
            "templates": formatted_templates,
            "total": len(formatted_templates),
            "message": "Templates fetched successfully"
        }
        
    except Exception as e:
        logger.error(f"Error fetching templates: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch templates: {str(e)}")

@router.post("/send-template")
async def send_template_to_lead(
    request: SendTemplateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Send WhatsApp template message and store in database for chat history"""
    try:
        # 1. Send template via WhatsApp API (existing code)
        whatsapp_params = {
            "Contact": request.contact,
            "Template": request.template_name,
            "Param": request.lead_name  # Single parameter (lead name)
        }
        
        result = await make_whatsapp_request("sendtemplate.php", whatsapp_params)
        
        # 2. 🔥 FIXED: Check for API errors before proceeding
        api_response = result.get("ApiResponse", "")
        api_message = result.get("ApiMessage", {})
        
        # Check if the WhatsApp API returned an error
        if api_response == "Fail" or api_message.get("Status") == "Error":
            error_details = api_message.get("ErrorMessage", {})
            error_message = "WhatsApp API error"
            
            # Extract specific error message
            if isinstance(error_details, dict) and "error" in error_details:
                error_info = error_details["error"]
                error_message = error_info.get("message", error_message)
                error_code = error_info.get("code", "")
                if error_code:
                    error_message = f"Error {error_code}: {error_message}"
            
            logger.error(f"WhatsApp API error for template {request.template_name}: {error_message}")
            
            # Return error response - DON'T store message in database
            return {
                "success": False,  # 🔥 KEY CHANGE: success = False for errors
                "error": error_message,
                "data": result,
                "template_name": request.template_name,
                "contact": request.contact,
                "lead_name": request.lead_name,
                "message": f"Failed to send template: {error_message}"  # 🔥 Clear error message
            }
        
        # 3. Only store message if WhatsApp API was successful
        if result and api_response != "Fail":  # 🔥 Additional check
            # Create readable message content for storage
            template_content = f"Template: {request.template_name} (Lead: {request.lead_name})"
            
            await store_outgoing_message(
                contact=request.contact,
                message_content=template_content,
                message_type="template",
                current_user=current_user,
                api_result=result,
                template_name=request.template_name
            )
        
        # 4. Return success response
        return {
            "success": True,  # 🔥 Only True when actually successful
            "data": result,
            "template_name": request.template_name,
            "contact": request.contact,
            "lead_name": request.lead_name,
            "message": "Template message sent successfully"  # 🔥 Success message
        }
        
    except Exception as e:
        logger.error(f"Error sending template: {str(e)}")
        # 🔥 Return proper error response for exceptions too
        return {
            "success": False,
            "error": str(e),
            "template_name": request.template_name,
            "contact": request.contact,
            "lead_name": request.lead_name,
            "message": f"Failed to send template: {str(e)}"
        }

@router.post("/send-text")
async def send_text_message(
    request: SendTextRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Send WhatsApp text message and store in database for chat history"""
    try:
        # 1. Send text message via WhatsApp API (existing code)
        whatsapp_params = {
            "Contact": request.contact,
            "Message": request.message
        }
        
        result = await make_whatsapp_request("sendtextmessage.php", whatsapp_params)
        
        # 2. NEW: Store the outgoing message in database
        if result:  # If message sent successfully
            await store_outgoing_message(
                contact=request.contact,
                message_content=request.message,
                message_type="text",
                current_user=current_user,
                api_result=result
            )
        
        return {
            "success": True,
            "data": result,
            "contact": request.contact,
            "message": "Text message sent and stored successfully"
        }
        
    except Exception as e:
        logger.error(f"Error sending text message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to send text message: {str(e)}")
    
async def store_outgoing_message(
    contact: str,
    message_content: str,
    message_type: str,
    current_user: Dict[str, Any],
    api_result: Dict[str, Any],
    template_name: Optional[str] = None
):
    """Store outgoing WhatsApp message in database"""
    try:
        print(f"🔍 DEBUG: store_outgoing_message called for contact: {contact}")
        db = get_database()
        
        # Clean the contact number
        clean_contact = contact.strip().replace(" ", "").replace("-", "")
        
        # Extract the 10-digit number (the actual phone number)
        if clean_contact.startswith("+91"):
            phone_10_digit = clean_contact[3:]  # Remove +91
        elif clean_contact.startswith("91") and len(clean_contact) == 12:
            phone_10_digit = clean_contact[2:]  # Remove 91
        else:
            phone_10_digit = clean_contact  # Already 10 digits
        
        print(f"🔍 DEBUG: Extracted 10-digit number: {phone_10_digit}")
        
        # Create all possible formats to search for
        possible_formats = [
            phone_10_digit,                    # 8531864229
            f"91{phone_10_digit}",             # 918531864229
            f"+91{phone_10_digit}",            # +918531864229
            f"+91 {phone_10_digit}",           # +91 8531864229
            contact.strip()                     # Original format
        ]
        
        print(f"🔍 DEBUG: Searching for formats: {possible_formats}")
        
        # Find lead by any of these phone number formats
        lead = await db.leads.find_one({
            "$or": [
                {"phoneNumber": {"$in": possible_formats}},
                {"contact_number": {"$in": possible_formats}},
                # Also try exact matches with field variations
                {"phoneNumber": phone_10_digit},
                {"contact_number": phone_10_digit},
                {"phoneNumber": f"91{phone_10_digit}"},
                {"contact_number": f"91{phone_10_digit}"},
                {"phoneNumber": f"+91{phone_10_digit}"},
                {"contact_number": f"+91{phone_10_digit}"}
            ]
        })
        
        print(f"🔍 DEBUG: Lead found: {lead is not None}")
        if lead:
            print(f"🔍 DEBUG: Lead ID: {lead.get('lead_id')}")
            print(f"🔍 DEBUG: Lead phone in DB: {lead.get('phoneNumber')} / {lead.get('contact_number')}")
        
        if not lead:
            logger.warning(f"No lead found for contact {contact}")
            return
        
        # Get user name for display
        user_name = f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip()
        if not user_name:
            user_name = current_user.get('email', 'Unknown User')
        
        # Use the original contact format for storage (keeps consistency with how message was sent)
        storage_phone = f"+91{phone_10_digit}" if not contact.startswith("+") else contact
        
        # Create message document
        message_doc = {
            "message_id": f"out_{int(time.time())}_{phone_10_digit}",  # Use 10-digit for unique ID
            "lead_id": lead.get("lead_id"),
            "phone_number": storage_phone,
            "direction": "outgoing",
            "message_type": message_type,
            "content": message_content,
            "timestamp": datetime.utcnow(),
            "status": "sent",
            "is_read": True,
            "sent_by_user_id": str(current_user.get("_id", "")),
            "sent_by_name": user_name,
            "media_url": None,
            "media_filename": None,
            "raw_webhook_data": {
                "api_response": api_result,
                "template_name": template_name,
                "sent_via": "crm_api",
                "original_contact_format": contact
            },
            "created_at": datetime.utcnow()
        }
        
        print(f"🔍 DEBUG: About to insert message: {message_doc['message_id']}")
        
        # Insert message
        result = await db.whatsapp_messages.insert_one(message_doc)
        
        print(f"🔍 DEBUG: Insert result: {result.inserted_id}")
        
        # Update lead's WhatsApp activity fields
        await db.leads.update_one(
            {"lead_id": lead.get("lead_id")},
            {
                "$set": {
                    "last_whatsapp_activity": datetime.utcnow(),
                    "last_whatsapp_message": message_content[:100],
                    "last_contacted": datetime.utcnow()  # Add this line
                },
                "$inc": {
                    "whatsapp_message_count": 1
                }
            }
        )
        await CommunicationService.log_whatsapp_communication(lead.get("lead_id"))
        
        logger.info(f"✅ Stored outgoing message for lead {lead.get('lead_id')}")
        
    except Exception as e:
        print(f"🔍 DEBUG: Error in store_outgoing_message: {str(e)}")
        logger.error(f"Error storing outgoing message: {str(e)}")
        import traceback
        print(f"🔍 DEBUG: Full traceback: {traceback.format_exc()}")