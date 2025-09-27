# app/routers/tata_calls.py
# MINIMAL CLEANED VERSION - Only Actually Used Endpoints

from fastapi import APIRouter, HTTPException, status, Depends
from typing import Optional
import logging
from datetime import datetime
from pydantic import BaseModel, Field
import json
import re
from ..config.database import get_database
from fastapi import APIRouter, HTTPException, status, Depends, Request  # Add Request
from typing import Optional, Dict, Any  

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import existing services
from ..services.tata_user_service import tata_user_service
from ..services.tata_call_service import tata_call_service
from ..utils.dependencies import get_current_active_user

# =============================================================================
# MINIMAL MODELS - Only for endpoints actually used by frontend
# =============================================================================

class ClickToCallRequestSimple(BaseModel):
    lead_id: str = Field(..., description="Lead ID to call")
    notes: Optional[str] = Field(None, description="Call notes")
    call_purpose: Optional[str] = Field(None, description="Purpose of call")

class ClickToCallResponse(BaseModel):
    success: bool = Field(..., description="Call success status")
    message: str = Field(..., description="Response message")
    call_id: Optional[str] = Field(None, description="Call ID")
    tata_call_id: Optional[str] = Field(None, description="TATA API call ID")
    call_status: str = Field("initiated", description="Call status")
    estimated_connection_time: int = Field(30, description="Estimated connection time")
    initiated_at: datetime = Field(default_factory=datetime.utcnow, description="Call initiation time")
    caller_number: Optional[str] = Field(None, description="Caller number")
    destination_number: Optional[str] = Field(None, description="Destination number")

class CallValidationRequest(BaseModel):
    lead_id: str = Field(..., description="Lead ID to validate")

class CallValidationResponse(BaseModel):
    can_call: bool = Field(..., description="Can make call")
    validation_errors: list = Field(default_factory=list, description="Validation errors")
    lead_found: bool = Field(False, description="Lead found")
    lead_phone: Optional[str] = Field(None, description="Lead phone number")
    user_can_call: bool = Field(False, description="User can make calls")
    user_agent_id: Optional[str] = Field(None, description="User agent ID")
    estimated_setup_time: int = Field(0, description="Setup time estimate")
    recommendations: list = Field(default_factory=list, description="Recommendations")

# =============================================================================
# CREATE ROUTER
# =============================================================================

router = APIRouter()

# =============================================================================
# MAIN CALLING ENDPOINT - USED BY FRONTEND
# =============================================================================

@router.post("/click-to-call-simple", response_model=ClickToCallResponse)
async def initiate_click_to_call_simple(
    call_request: ClickToCallRequestSimple,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Main Click-to-Call endpoint - USED BY FRONTEND
    
    Auto-fetch Features:
    - Lead phone number from database
    - User agent ID from Tata sync
    - Passes lead_id as custom_identifier for webhook correlation
    """
    try:
        logger.info(f"User {current_user['email']} initiating call for lead {call_request.lead_id}")
        
        if not call_request.lead_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lead ID is required"
            )
        
        # Use the simplified service method
        success, result = await tata_call_service.initiate_click_to_call_simple(
            lead_id=call_request.lead_id,
            current_user=current_user,
            notes=call_request.notes,
            call_purpose=call_request.call_purpose
        )
        
        if not success:
            error_detail = result.get("message", "Call initiation failed")
            
            # Provide specific error messages
            if "phone not found" in error_detail.lower():
                error_detail = f"No phone number found for lead {call_request.lead_id}. Please add a phone number to the lead."
            elif "not synchronized" in error_detail.lower():
                error_detail = "Your account is not synchronized with the calling system. Please contact admin to enable calling."
            elif "agent id not found" in error_detail.lower():
                error_detail = "Calling not configured for your account. Please contact admin for setup."
            
            logger.warning(f"Click-to-call failed for {call_request.lead_id}: {error_detail}")
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail
            )
        
        logger.info(f"Click-to-call initiated successfully for lead {call_request.lead_id}")
        
        return ClickToCallResponse(
            success=True,
            message="Call initiated successfully",
            call_id=result.get("call_id"),
            tata_call_id=result.get("tata_call_id"),
            call_status=result.get("status", "initiated"),
            estimated_connection_time=30,
            initiated_at=datetime.utcnow(),
            caller_number=result.get("caller_number"),
            destination_number=result.get("destination_number")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in click-to-call: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error initiating call: {str(e)}"
        )

# =============================================================================
# CALL VALIDATION ENDPOINT - USED BY FRONTEND
# =============================================================================

@router.post("/validate-call", response_model=CallValidationResponse)
async def validate_call_parameters(
    validation_request: CallValidationRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Pre-call validation endpoint - USED BY FRONTEND
    
    Validates:
    - Lead exists and has phone number
    - User has calling permissions
    - User is synchronized with Tata system
    """
    try:
        logger.info(f"User {current_user['email']} validating call for lead {validation_request.lead_id}")
        
        user_id = str(current_user.get("user_id") or current_user.get("_id"))
        validation_errors = []
        recommendations = []
        
        # Check if lead exists and has phone
        lead_phone = await tata_call_service._get_lead_phone_number(validation_request.lead_id)
        lead_found = lead_phone is not None
        
        if not lead_found:
            validation_errors.append(f"Lead {validation_request.lead_id} not found")
        elif not lead_phone:
            validation_errors.append(f"Lead {validation_request.lead_id} has no phone number")
            recommendations.append("Add a phone number to the lead before calling")
        
        # Check user calling permissions
        user_mapping = await tata_user_service.get_user_mapping(user_id)
        
        user_can_call = False
        user_agent_id = None
        
        if user_mapping:
            user_can_call = user_mapping.get("can_make_calls", False)
            user_agent_id = user_mapping.get("tata_agent_id")
            
            # Check for caller ID
            caller_id = user_mapping.get("tata_caller_id") or user_mapping.get("tata_did_number")
            if not caller_id and user_can_call:
                validation_errors.append("User has no caller ID configured")
                recommendations.append("Contact admin to configure caller ID/DID")
                user_can_call = False
        else:
            validation_errors.append("User is not synchronized with calling system")
            recommendations.append("Contact admin to set up calling permissions")
        
        if not user_agent_id:
            validation_errors.append("No Tata agent ID found for user")
            recommendations.append("Complete Tata system synchronization")
        
        # Overall validation result
        can_call = len(validation_errors) == 0
        
        if can_call:
            recommendations.append("All validations passed - ready to make call")
        
        logger.info(f"Call validation for {validation_request.lead_id}: {'PASS' if can_call else 'FAIL'}")
        
        return CallValidationResponse(
            can_call=can_call,
            validation_errors=validation_errors,
            lead_found=lead_found,
            lead_phone=lead_phone,
            user_can_call=user_can_call,
            user_agent_id=user_agent_id,
            estimated_setup_time=0 if can_call else 10,
            recommendations=recommendations
        )
        
    except Exception as e:
        logger.error(f"Error validating call: {str(e)}")
        return CallValidationResponse(
            can_call=False,
            validation_errors=[f"Validation failed: {str(e)}"],
            lead_found=False,
            user_can_call=False,
            recommendations=["Contact support for assistance"]
        )


@router.post("/webhook")
async def handle_tata_webhook(request: Request):
    """
    Handle Smartflo/TATA webhooks - ENHANCED with real timeline logging
    
    Processes webhook events and logs to lead timeline:
    - Call initiated, answered, missed
    - Real-time updates to lead activity
    - Automatic duration and agent tracking
    """
    try:
        # Get raw body for logging
        body = await request.body()
        logger.info(f"Smartflo webhook received: {body.decode('utf-8')}")
        
        # Parse JSON payload
        try:
            payload = await request.json()
        except Exception as json_error:
            logger.error(f"Failed to parse webhook JSON: {json_error}")
            return {"success": False, "error": "Invalid JSON"}
        
        # Log parsed payload
        logger.info(f"Parsed webhook: {json.dumps(payload, indent=2, default=str)}")
        
        # Process webhook and log to timeline
        await process_webhook_to_timeline(payload)
        
        return {
            "success": True,
            "message": "Webhook processed and logged to timeline",
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}", exc_info=True)
        return {
            "success": True,  # Return success to avoid Smartflo retries
            "message": "Webhook acknowledged (error logged)",
            "timestamp": datetime.utcnow()
        }

async def process_webhook_to_timeline(payload: Dict[str, Any]):
    """Enhanced outgoing call processing with better agent identification"""
    try:
        call_id = payload.get("call_id") or payload.get("uuid")
        call_status = payload.get("call_status", "unknown")
        customer_number = payload.get("call_to_number")
        
        # Get call timing
        duration = payload.get("duration", 0) or payload.get("billsec", 0)
        if isinstance(duration, str):
            duration = int(duration) if duration.isdigit() else 0
        
        # Better agent identification for outgoing calls
        answered_agent = payload.get("answered_agent", {})
        missed_agent = payload.get("missed_agent", [])
        
        agent_name = "Unknown Agent"
        
        if isinstance(answered_agent, dict) and answered_agent.get("name"):
            agent_name = answered_agent.get("name")
        elif missed_agent and len(missed_agent) > 0:
            agent_name = missed_agent[0].get("name", "Unknown Agent")
        elif payload.get("answered_agent_name") and payload.get("answered_agent_name") != "_name":
            agent_name = payload.get("answered_agent_name")
        
        # Find lead by customer phone number
        lead_id = await find_lead_by_phone_number(customer_number)
        
        if not lead_id:
            logger.warning(f"No lead found for outgoing call to: {customer_number}")
            return
        
        # Create timeline description
        if call_status == "answered" and duration > 0:
            minutes = duration // 60
            seconds = duration % 60
            duration_text = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
            description = f"Call initiated and answered by customer (Duration: {duration_text}) - Handled by {agent_name}"
        elif call_status == "missed":
            if answered_agent:
                description = f"Call initiated and missed by customer - Agent {agent_name} was ready"
            elif missed_agent:
                description = f"Call initiated and missed by agent - {agent_name} didn't answer"
            else:
                description = f"Call initiated and missed by customer"
        else:
            description = f"Call initiated - Status: {call_status}"
        
        # Log to enhanced timeline
        await log_to_timeline_updated(lead_id, call_id, description, payload)
        
        logger.info(f"Outgoing call logged: {description}")
        
    except Exception as e:
        logger.error(f"Error processing outgoing call: {str(e)}", exc_info=True)

async def find_lead_by_phone_number(phone_number: str) -> Optional[str]:
    """Find lead by phone number - updated for actual database schema"""
    try:
        if not phone_number:
            return None
            
        db = get_database()
        
        # Clean phone number
        clean_phone = re.sub(r'[^\d]', '', phone_number)
        
        # Remove country code if present
        if clean_phone.startswith('91') and len(clean_phone) > 10:
            ten_digit = clean_phone[2:]  # Remove 91 prefix
        else:
            ten_digit = clean_phone
        
        # Create search patterns
        patterns = [
            phone_number,          # 918531864229
            clean_phone,           # 918531864229
            ten_digit,             # 8531864229 (this should match!)
            f"+{clean_phone}",     # +918531864229
            f"+91{ten_digit}"      # +918531864229
        ]
        
        logger.info(f"Searching for lead with phone patterns: {patterns}")
        
        for pattern in patterns:
            # Search in the correct field names from your database
            lead = await db.leads.find_one({
                "$or": [
                    {"contact_number": pattern},     # Your actual field
                    {"phone_number": pattern},       # Your actual field  
                    {"phone": pattern},              # Legacy field (if exists)
                    {"mobile": pattern},             # Legacy field (if exists)
                    # Regex patterns for partial matching
                    {"contact_number": {"$regex": f".*{ten_digit}.*"}},
                    {"phone_number": {"$regex": f".*{ten_digit}.*"}}
                ]
            })
            
            if lead:
                lead_id = lead.get("lead_id")
                logger.info(f"✅ Found lead {lead_id} for phone pattern: {pattern}")
                return lead_id
        
        logger.error(f"❌ No lead found for any phone pattern: {patterns}")
        logger.error(f"Webhook phone: {phone_number}, Clean: {clean_phone}, Ten-digit: {ten_digit}")
        return None
        
    except Exception as e:
        logger.error(f"Error finding lead by phone: {str(e)}")
        return None


@router.post("/webhook-incoming")
async def handle_incoming_calls_webhook(
    request: Request
):
    """Handle incoming calls webhook - Customer called Agent"""
    try:
        # Get raw body and parse payload
        raw_body = await request.body()
        payload = await request.json()
        
        logger.info(f"Incoming call webhook received: {json.dumps(payload, indent=2)}")
        
        # Process incoming call specifically
        await process_incoming_call_to_timeline(payload)
        
        return {
            "success": True,
            "message": "Incoming call webhook processed successfully",
            "call_id": payload.get("call_id"),
            "direction": "incoming",
            "processed_at": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Incoming call webhook error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process incoming call webhook: {str(e)}"
        )

async def process_incoming_call_to_timeline(payload: Dict[str, Any]):
    """Enhanced incoming call processing with lead attribution"""
    try:
        call_id = payload.get("call_id") or payload.get("uuid")
        call_status = payload.get("call_status", "unknown")
        
        # For incoming calls, the caller is the customer (lead)
        customer_number = payload.get("caller_id_number") or payload.get("call_from_number")
        
        if customer_number:
            customer_number = customer_number.replace("+", "")
        
        # Get call duration
        duration = payload.get("duration", 0) or payload.get("billsec", 0)
        if isinstance(duration, str):
            duration = int(duration) if duration.isdigit() else 0
        
        # Enhanced agent detection
        agent_name = "Unknown Agent"
        
        answered_agent = payload.get("answered_agent")
        if answered_agent:
            if isinstance(answered_agent, dict) and answered_agent.get("name"):
                agent_name = answered_agent.get("name")
            elif isinstance(answered_agent, str) and answered_agent.strip():
                agent_name = answered_agent
        
        if agent_name == "Unknown Agent":
            answered_agent_name = payload.get("answered_agent_name")
            if answered_agent_name and answered_agent_name != "_name" and answered_agent_name.strip():
                agent_name = answered_agent_name
        
        if agent_name == "Unknown Agent":
            missed_agents = payload.get("missed_agent", [])
            if missed_agents and len(missed_agents) > 0:
                first_missed = missed_agents[0]
                if isinstance(first_missed, dict) and first_missed.get("name"):
                    agent_name = first_missed.get("name")
        
        # Find lead by customer phone number
        lead_id = await find_lead_by_phone_number(customer_number)
        
        if not lead_id:
            logger.warning(f"No lead found for incoming call from: {customer_number}")
            return
        
        # Create timeline description
        if call_status == "answered" and duration > 0:
            minutes = duration // 60
            seconds = duration % 60
            duration_text = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
            description = f"Call dialed by lead and answered by agent - {agent_name} (Duration: {duration_text})"
        elif call_status == "missed" or call_status == "noanswer":
            if agent_name != "Unknown Agent":
                description = f"Call dialed by lead and missed by agent - {agent_name} didn't answer"
            else:
                description = f"Call dialed by lead and missed by agent - No agent available"
        elif call_status == "answered" and duration == 0:
            description = f"Call dialed by lead and answered by agent - {agent_name} (immediate hangup)"
        else:
            description = f"Call dialed by lead - Status: {call_status}"
        
        # Log to enhanced timeline (will be attributed to the lead)
        await log_to_timeline_updated(lead_id, call_id, description, payload)
        
        logger.info(f"Incoming call timeline logged for lead {lead_id}: {description}")
        
    except Exception as e:
        logger.error(f"Error processing incoming call to timeline: {str(e)}", exc_info=True)

def clean_phone_number(phone: str) -> str:
    """Clean phone number for matching"""
    if not phone:
        return ""
    
    # Remove all non-digits
    import re
    cleaned = re.sub(r'[^\d]', '', phone)
    
    # Remove country code if present
    if cleaned.startswith('91') and len(cleaned) > 10:
        cleaned = cleaned[2:]
    elif cleaned.startswith('+91'):
        cleaned = cleaned[3:]
    
    return cleaned

async def log_to_timeline_updated(lead_id: str, call_id: str, description: str, payload: Dict[str, Any]):
    """Enhanced timeline logging with proper attribution and recording URL - FIXED"""
    try:
        db = get_database()
        
        # Check if this call_id already exists to prevent duplicates
        existing_entry = await db.lead_activities.find_one({
            "metadata.call_id": call_id,
            "lead_id": lead_id
        })
        
        if existing_entry:
            logger.info(f"Call {call_id} already logged for lead {lead_id}")
            return True
        
        # Determine call direction and set appropriate attribution
        direction = payload.get("direction", "unknown")
        call_direction = "incoming" if direction in ["inbound", "incoming"] else "outgoing"
        
        # Initialize defaults
        created_by = None
        created_by_name = "System Generated"  # Default fallback
        is_system_generated = True
        
        # Set created_by and created_by_name based on call direction
        if call_direction == "incoming":
            # For incoming calls, attribute to the lead who called
            lead = await db.leads.find_one({"lead_id": lead_id})
            created_by = lead_id  # Use lead_id as identifier
            created_by_name = lead.get("name", "Unknown Lead") if lead else "Unknown Lead"
            is_system_generated = False  # Lead initiated this call
        else:
            # For outgoing calls, find the agent who made the call
            agent_name = "System Generated"
            
            # Try to identify the agent from webhook data
            answered_agent = payload.get("answered_agent", {})
            if isinstance(answered_agent, dict) and answered_agent.get("name"):
                agent_name = answered_agent.get("name")
            elif payload.get("answered_agent_name") and payload.get("answered_agent_name") not in ["_name", ""]:
                agent_name = payload.get("answered_agent_name")
            else:
                # FIXED: Check missed_agent array when agent didn't answer
                missed_agent = payload.get("missed_agent", [])
                if missed_agent and len(missed_agent) > 0:
                    first_missed = missed_agent[0]
                    if isinstance(first_missed, dict) and first_missed.get("name"):
                        agent_name = first_missed.get("name")
            
            # Set created_by_name to agent_name
            created_by_name = agent_name
            
            # Try to find the actual user in database
            if agent_name != "System Generated":
                user = await db.users.find_one({"$or": [
                    {"first_name": {"$regex": f".*{agent_name}.*", "$options": "i"}},
                    {"last_name": {"$regex": f".*{agent_name}.*", "$options": "i"}},
                    {"email": {"$regex": f".*{agent_name.lower()}.*", "$options": "i"}}
                ]})
                
                if user:
                    created_by = str(user["_id"])
                    created_by_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get('email')
                    is_system_generated = False
        
        # Get recording URL if available
        recording_url = payload.get("recording_url")
        has_recording = bool(recording_url and recording_url.strip())
        
        # Create enhanced timeline entry
        timeline_entry = {
            "lead_id": lead_id,
            "activity_type": "call",
            "description": description,
            "created_by": created_by,
            "created_by_name": created_by_name,  # Now guaranteed to be set
            "created_at": datetime.utcnow(),
            "is_system_generated": is_system_generated,
            "metadata": {
                "source": "smartflo_webhook",
                "call_id": call_id,
                "call_direction": call_direction,
                "call_status": payload.get("call_status"),
                "duration": payload.get("billsec", 0) or payload.get("duration", 0),
                "customer_number": payload.get("call_to_number") if call_direction == "outgoing" else payload.get("caller_id_number"),
                "agent_name": payload.get("answered_agent", {}).get("name") if isinstance(payload.get("answered_agent"), dict) else payload.get("answered_agent_name"),
                "hangup_cause": payload.get("hangup_cause"),
                "start_stamp": payload.get("start_stamp"),
                "end_stamp": payload.get("end_stamp"),
                "answer_stamp": payload.get("answer_stamp"),
                # Recording information
                "has_recording": has_recording,
                "recording_url": recording_url if has_recording else None,
                "aws_recording_id": payload.get("aws_call_recording_identifier"),
                # Full webhook payload for debugging
                "full_webhook_payload": payload
            }
        }
        
        # Insert into lead_activities collection
        result = await db.lead_activities.insert_one(timeline_entry)
        
        if result.inserted_id:
            logger.info(f"✅ Timeline entry created for lead {lead_id}: {description}")
            logger.info(f"✅ Inserted with ID: {result.inserted_id}")
            logger.info(f"✅ Attribution: {created_by_name} ({'Lead' if call_direction == 'incoming' else 'Agent'})")
            if has_recording:
                logger.info(f"✅ Recording available: {recording_url}")
            return True
        else:
            logger.error(f"❌ Failed to insert timeline entry for lead {lead_id}")
            return False
        
    except Exception as e:
        logger.error(f"❌ Error logging to timeline: {str(e)}", exc_info=True)
        return False
    
def create_call_description(call_status: str, agent_name: str, duration: Any, customer_number: str) -> str:
    """Create human-readable timeline description - UPDATED"""
    try:
        duration_sec = int(duration) if duration else 0
    except (ValueError, TypeError):
        duration_sec = 0
    
    # Format duration
    if duration_sec > 0:
        minutes = duration_sec // 60
        seconds = duration_sec % 60
        duration_text = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
        description = f"Call answered by customer (Duration: {duration_text})"
    else:
        if call_status and call_status.lower() == "answered":
            description = "Call answered by customer"
        else:
            description = "Call missed by customer"
    
    # Add agent name if available
    if agent_name:
        description += f" - Handled by {agent_name}"
    
    # Add masked customer number for privacy
    if customer_number:
        masked = customer_number[-4:] if len(customer_number) > 4 else customer_number
        description += f" (***{masked})"
    
    return description


async def log_to_timeline(lead_id: str, call_id: str, description: str, payload: Dict[str, Any]):
    """Log call event to lead timeline"""
    try:
        db = get_database()
        
        timeline_entry = {
            "lead_id": lead_id,
            "activity_type": "call",
            "description": description,
            "activity_date": datetime.utcnow(),
            "created_by": "system",
            "metadata": {
                "call_id": call_id,
                "call_status": payload.get("$call_status") or payload.get("call_status"),
                "agent_name": payload.get("$answered_agent_name") or payload.get("answered_agent_name"),
                "duration_seconds": int(payload.get("$duration", 0)) if payload.get("$duration") else 0,
                "source": "smartflo_webhook",
                "webhook_received_at": datetime.utcnow()
            }
        }
        
        result = await db.timeline.insert_one(timeline_entry)
        
        if result.inserted_id:
            logger.info(f"Timeline entry created for lead {lead_id}")
        else:
            logger.error(f"Failed to create timeline entry for lead {lead_id}")
            
    except Exception as e:
        logger.error(f"Error logging to timeline: {str(e)}", exc_info=True)

# =============================================================================
# ROUTER METADATA
# =============================================================================

router.tags = ["Tata Calls"]