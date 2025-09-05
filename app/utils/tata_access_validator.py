# app/utils/tata_access_validator.py
from typing import Dict, List
import logging
from ..config.database import get_database

logger = logging.getLogger(__name__)

async def validate_user_tata_access(user_id: str, user_role: str) -> Dict:
    """
    Validate if user has access to TATA call data
    
    Returns:
        Dict with access information
    """
    try:
        db = get_database()
        
        # Admin always has access
        if user_role == "admin":
            return {
                "has_access": True,
                "access_level": "admin",
                "can_view_calls": True,
                "reason": "admin_privileges"
            }
        
        # Check for TATA mapping
        mapping = await db.tata_user_mappings.find_one({"crm_user_id": user_id})
        
        if mapping and mapping.get("tata_agent_id"):
            return {
                "has_access": True,
                "access_level": "tata_user", 
                "can_view_calls": True,
                "tata_agent_id": mapping.get("tata_agent_id"),
                "reason": "tata_integration_active"
            }
        else:
            return {
                "has_access": False,
                "access_level": "non_tata_user",
                "can_view_calls": False,
                "reason": "no_tata_integration",
                "available_features": ["leads", "tasks", "contacts", "notes"],
                "restricted_features": ["calls", "analytics", "recordings"]
            }
            
    except Exception as e:
        logger.error(f"Error validating TATA access for user {user_id}: {e}")
        return {
            "has_access": False,
            "access_level": "error",
            "can_view_calls": False,
            "reason": "validation_error"
        }

def get_empty_call_response(message: str = "Call data requires TATA integration") -> Dict:
    """Return empty call data response for non-TATA users"""
    return {
        "success": True,
        "message": message,
        "total_calls": 0,
        "user_stats": [],
        "call_records": [],
        "access_level": "non_tata_user"
    }