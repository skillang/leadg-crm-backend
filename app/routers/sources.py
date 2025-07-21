# app/routers/sources.py - FIXED FILE FOR SOURCE API ENDPOINTS

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Dict, Any
import logging
from ..config.database import get_database
from bson import ObjectId
from datetime import datetime
from ..models.source import SourceCreate, SourceUpdate, SourceResponse, SourceListResponse
from ..services.source_service import source_service
from ..utils.dependencies import get_current_active_user, get_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sources"])

# ============================================================================
# PUBLIC ENDPOINTS (All authenticated users can view sources)
# ============================================================================

@router.get("/", response_model=SourceListResponse)
async def get_all_sources(
    include_lead_count: bool = Query(False, description="Include lead count for each source"),
    active_only: bool = Query(True, description="Only return active sources"),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get all sources (visible to all authenticated users)
    Used for dropdowns in lead creation/editing
    """
    try:
        logger.info(f"Getting sources for user: {current_user.get('email')}")
        
        sources = await source_service.get_all_sources(
            include_lead_count=include_lead_count,
            active_only=active_only
        )
        
        # Count totals
        total = len(sources)
        active_count = sum(1 for s in sources if s.get("is_active", True))
        inactive_count = total - active_count
        
        return SourceListResponse(
            sources=sources,
            total=total,
            active_count=active_count,
            inactive_count=inactive_count
        )
        
    except Exception as e:
        logger.error(f"Error getting sources: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sources: {str(e)}"
        )

@router.get("/inactive", response_model=SourceListResponse)
async def get_inactive_sources(
    include_lead_count: bool = Query(False, description="Include lead count for each source"),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Get all inactive sources (Admin view)"""
    try:
        logger.info(f"Getting inactive sources for user: {current_user.get('email')}")
        
        # Get ALL sources first
        all_sources = await source_service.get_all_sources(
            include_lead_count=include_lead_count,
            active_only=False
        )
        
        # Filter to only inactive sources
        inactive_sources = [s for s in all_sources if not s.get("is_active", True)]
        
        # Count totals from ALL sources
        total_sources = len(all_sources)
        active_count = sum(1 for s in all_sources if s.get("is_active", True))
        inactive_count = total_sources - active_count
        
        return SourceListResponse(
            sources=inactive_sources,
            total=len(inactive_sources),
            active_count=active_count,
            inactive_count=inactive_count
        )
        
    except Exception as e:
        logger.error(f"Error getting inactive sources: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get inactive sources: {str(e)}"
        )

@router.get("/active", response_model=SourceListResponse)
async def get_active_sources(
    include_lead_count: bool = Query(False, description="Include lead count for each source"),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get all active sources (explicitly active only)
    Useful for lead creation dropdowns
    """
    try:
        logger.info(f"Getting active sources for user: {current_user.get('email')}")
        
        # Get ALL sources first to get accurate counts
        all_sources = await source_service.get_all_sources(
            include_lead_count=include_lead_count,
            active_only=False
        )
        
        # Filter to only active sources
        active_sources = [s for s in all_sources if s.get("is_active", True)]
        
        # Count totals from ALL sources
        total_sources = len(all_sources)
        active_count = len(active_sources)
        inactive_count = total_sources - active_count
        
        return SourceListResponse(
            sources=active_sources,
            total=len(active_sources),
            active_count=active_count,
            inactive_count=inactive_count
        )
        
    except Exception as e:
        logger.error(f"Error getting active sources: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get active sources: {str(e)}"
        )

@router.get("/{source_id}", response_model=SourceResponse)
async def get_source_by_id(
    source_id: str,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Get a specific source by ID"""
    try:
        source = await source_service.get_source_by_id(source_id)
        return SourceResponse(**source)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting source {source_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get source: {str(e)}"
        )

# ============================================================================
# ADMIN-ONLY ENDPOINTS (Source management)
# ============================================================================

@router.post("/", response_model=Dict[str, Any])
async def create_source(
    source_data: SourceCreate,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """Create a new source (Admin only)"""
    try:
        user_email = current_user.get("email", "unknown")
        logger.info(f"Creating source '{source_data.name}' by admin: {user_email}")
        
        result = await source_service.create_source(source_data, user_email)
        
        return {
            "success": True,
            "message": result["message"],
            "source": result["source"]
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating source: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create source: {str(e)}"
        )

@router.put("/{source_id}", response_model=Dict[str, Any])
async def update_source(
    source_id: str,
    source_data: SourceUpdate,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """Update an existing source (Admin only)"""
    try:
        user_email = current_user.get("email", "unknown")
        logger.info(f"Updating source {source_id} by admin: {user_email}")
        
        result = await source_service.update_source(source_id, source_data, user_email)
        
        return {
            "success": True,
            "message": result["message"],
            "source": result["source"]
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating source {source_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update source: {str(e)}"
        )

@router.patch("/{source_id}/activate", response_model=Dict[str, Any])
async def activate_source(
    source_id: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """Activate a deactivated source (Admin only)"""
    try:
        user_email = current_user.get("email", "unknown")
        logger.info(f"Activating source {source_id} by admin: {user_email}")
        
        db = get_database()
        
        # Check if source exists
        source = await db.sources.find_one({"_id": ObjectId(source_id)})
        if not source:
            raise ValueError(f"Source with ID {source_id} not found")
        
        # Update source to active
        result = await db.sources.update_one(
            {"_id": ObjectId(source_id)},
            {
                "$set": {
                    "is_active": True,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count == 0:
            return {
                "success": True,
                "message": f"Source '{source['name']}' was already active",
                "action": "no_change"
            }
        
        logger.info(f"Source '{source['name']}' activated by {user_email}")
        
        return {
            "success": True,
            "message": f"Source '{source['name']}' activated successfully",
            "action": "activated"
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error activating source {source_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate source: {str(e)}"
        )

@router.patch("/{source_id}/deactivate", response_model=Dict[str, Any])
async def deactivate_source(
    source_id: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """Deactivate a source without deleting it (Admin only)"""
    try:
        user_email = current_user.get("email", "unknown")
        logger.info(f"Deactivating source {source_id} by admin: {user_email}")
        
        db = get_database()
        
        # Check if source exists
        source = await db.sources.find_one({"_id": ObjectId(source_id)})
        if not source:
            raise ValueError(f"Source with ID {source_id} not found")
        
        # Check if this is the only active source
        active_count = await db.sources.count_documents({"is_active": True})
        if active_count <= 1 and source.get("is_active", True):
            raise ValueError("Cannot deactivate the last active source")
        
        # Update source to inactive
        result = await db.sources.update_one(
            {"_id": ObjectId(source_id)},
            {
                "$set": {
                    "is_active": False,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count == 0:
            return {
                "success": True,
                "message": f"Source '{source['name']}' was already inactive",
                "action": "no_change"
            }
        
        logger.info(f"Source '{source['name']}' deactivated by {user_email}")
        
        return {
            "success": True,
            "message": f"Source '{source['name']}' deactivated successfully",
            "action": "deactivated"
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error deactivating source {source_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deactivate source: {str(e)}"
        )

@router.delete("/{source_id}", response_model=Dict[str, Any])
async def delete_source(
    source_id: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """Delete a source (Admin only - only if no leads are using it)"""
    try:
        user_email = current_user.get("email", "unknown")
        logger.info(f"Deleting source {source_id} by admin: {user_email}")
        
        result = await source_service.delete_source(source_id, user_email)
        
        return {
            "success": True,
            "message": result["message"]
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error deleting source {source_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete source: {str(e)}"
        )