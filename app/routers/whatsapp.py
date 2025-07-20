# app/routers/whatsapp.py - Simple WhatsApp Integration

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
import httpx
import logging
from datetime import datetime
from ..utils.dependencies import get_current_user
from ..config.settings import settings
import os


logger = logging.getLogger(__name__)
# In app/routers/whatsapp.py - Change this line:
router = APIRouter(tags=["WhatsApp Integration"])  # Remove prefix="/api/v1/whatsapp"

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
# PYDANTIC MODELS
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
# UTILITY FUNCTIONS
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
# API ENDPOINTS
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
                "description": template["description"],
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
    """Send WhatsApp template message (simplified - no lead validation)"""
    try:
        # Send template via WhatsApp API directly
        whatsapp_params = {
            "Contact": request.contact,
            "Template": request.template_name,
            "Param": request.lead_name  # Single parameter (lead name)
        }
        
        result = await make_whatsapp_request("sendtemplate.php", whatsapp_params)
        
        return {
            "success": True,
            "data": result,
            "template_name": request.template_name,
            "contact": request.contact,
            "lead_name": request.lead_name,
            "message": "Template message sent successfully"
        }
        
    except Exception as e:
        logger.error(f"Error sending template: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to send template: {str(e)}")

@router.post("/send-text")
async def send_text_message(
    request: SendTextRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Send WhatsApp text message (simplified - no lead validation)"""
    try:
        # Send text message via WhatsApp API directly
        whatsapp_params = {
            "Contact": request.contact,
            "Message": request.message
        }
        
        result = await make_whatsapp_request("sendtextmessage.php", whatsapp_params)
        
        return {
            "success": True,
            "data": result,
            "contact": request.contact,
            "message": "Text message sent successfully"
        }
        
    except Exception as e:
        logger.error(f"Error sending text message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to send text message: {str(e)}")

@router.get("/lead-messages/{lead_id}")
async def get_lead_whatsapp_history(
    lead_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get WhatsApp message history for a lead (optional - requires database)"""
    try:
        # Simplified response without database dependency
        return {
            "success": True,
            "lead_id": lead_id,
            "message": "Message history endpoint available (requires database connection)",
            "note": "Database connection needed for full functionality"
        }
        
    except Exception as e:
        logger.error(f"Error fetching WhatsApp history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch message history: {str(e)}")
