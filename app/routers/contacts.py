# app/routers/contacts.py - Fixed Router with All Existing Services
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, List
import logging
from datetime import datetime

# Fixed imports - only import what exists
from app.decorators.timezone_decorator import convert_dates_to_ist
from app.models.contact import (
    ContactCreate, 
    ContactUpdate, 
    ContactResponse, 
    ContactListResponse, 
    SetPrimaryContactRequest  # Now exists in models
)
from app.services.contact_service import contact_service  # Import the service instance
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)

# Create router without tags (tags will be added in main.py)
router = APIRouter()

# =====================================================================
# CONTACT CRUD OPERATIONS (All Existing Services Preserved)
# =====================================================================

@router.post("/leads/{lead_id}/contacts", status_code=status.HTTP_201_CREATED)
async def create_contact(
    lead_id: str,
    contact_data: ContactCreate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Create a new contact for a specific lead.
    Auto-logs activity to lead_activities collection.
    Handles permissions and duplicate prevention.
    """
    try:
        result = await contact_service.create_contact(lead_id, contact_data, current_user)
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in create_contact: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

@router.get("/leads/{lead_id}/contacts")
@convert_dates_to_ist()
async def get_lead_contacts(
    lead_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get all contacts for a specific lead.
    Returns contacts with summary statistics and lead info.
    """
    try:
        result = await contact_service.get_lead_contacts(lead_id, current_user)
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_lead_contacts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

# 🔧 FIXED: Put specific routes BEFORE general routes to avoid conflicts
@router.patch("/{contact_id}/primary")
async def set_primary_contact(
    contact_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Set a contact as the primary contact for their lead.
    Removes primary status from other contacts for the same lead.
    """
    try:
        result = await contact_service.set_primary_contact(contact_id, current_user)
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in set_primary_contact: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

@router.get("/{contact_id}")
@convert_dates_to_ist()
async def get_contact(
    contact_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get a specific contact by ID.
    Includes all contact details and linked leads.
    """
    try:
        result = await contact_service.get_contact_by_id(contact_id, current_user)
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_contact: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

@router.put("/{contact_id}")
async def update_contact(
    contact_id: str,
    contact_data: ContactUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Update a contact's information.
    Handles duplicate prevention and permission checking.
    Auto-logs activity to lead_activities collection.
    """
    try:
        result = await contact_service.update_contact(contact_id, contact_data, current_user)
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in update_contact: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

@router.delete("/{contact_id}")
async def delete_contact(
    contact_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Delete a contact.
    Auto-logs activity to lead_activities collection.
    Returns confirmation with deleted contact info.
    """
    try:
        result = await contact_service.delete_contact(contact_id, current_user)
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in delete_contact: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

# =====================================================================
# DEBUG & TESTING ENDPOINTS (All Existing Debug Services Preserved)
# =====================================================================

@router.get("/debug/test")
@convert_dates_to_ist()
async def debug_test():
    """
    Debug endpoint to test contact service availability and database connectivity.
    Tests the health of the contact service.
    """
    try:
        result = await contact_service.test_service()
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Service test failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@router.get("/debug/test-method")
@convert_dates_to_ist()
async def test_contact_method():
    """
    Debug endpoint to test method existence.
    Verifies all required contact service methods are available.
    """
    try:
        result = await contact_service.test_method_existence()
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Method test failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# =====================================================================
# HEALTH CHECK ENDPOINT
# =====================================================================

@router.get("/health")
@convert_dates_to_ist()
async def health_check():
    """
    Simple health check endpoint for monitoring.
    Returns basic service status and version info.
    """
    return {
        "status": "healthy",
        "service": "contact_service",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "endpoints": {
            "create_contact": "POST /leads/{lead_id}/contacts",
            "get_lead_contacts": "GET /leads/{lead_id}/contacts", 
            "get_contact": "GET /{contact_id}",
            "update_contact": "PUT /{contact_id}",
            "delete_contact": "DELETE /{contact_id}",
            "set_primary_contact": "PATCH /{contact_id}/primary",
            "debug_test": "GET /debug/test",
            "test_methods": "GET /debug/test-method",
            "health_check": "GET /health"
        }
    }

# =====================================================================
# ADDITIONAL UTILITY ENDPOINTS (Enhanced Functionality)
# =====================================================================

@router.get("/stats")
@convert_dates_to_ist()
async def get_contact_statistics(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get contact statistics for the current user.
    Shows contact counts by role, relationship, etc.
    """
    try:
        # This would need to be implemented in the service if needed
        # For now, return a placeholder
        return {
            "success": True,
            "data": {
                "message": "Contact statistics endpoint - implement in service if needed",
                "user": current_user.get("email", "unknown")
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting contact statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get statistics: {str(e)}"
        )