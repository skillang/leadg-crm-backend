# app/routers/automation_campaigns.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime

from app.utils.dependencies import get_current_active_user, get_admin_user
from app.config.database import get_database
from app.models.automation_campaign import (
    CampaignCreateRequest,
    CampaignResponse,
    CampaignListItem,
    CampaignStatsResponse
)
from app.services.campaign_service import campaign_service
from app.services.campaign_executor import campaign_executor

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# CAMPAIGN CRUD ENDPOINTS
# ============================================================================

@router.post("/create", response_model=CampaignResponse)
async def create_campaign(
    campaign_data: CampaignCreateRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Create new automation campaign (Admin only)
    
    - Creates campaign configuration
    - Enrolls matching leads immediately
    - Returns schedule preview
    """
    try:
        admin_email = current_user.get("email")
        logger.info(f"Campaign creation requested by {admin_email}")
        
        # Create campaign
        result = await campaign_service.create_campaign(
            campaign_data=campaign_data,
            created_by=admin_email
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        
        campaign_id = result["campaign_id"]
        
        # Enroll leads immediately
        enrollment_result = await campaign_executor.enroll_leads_in_campaign(campaign_id)
        
        return CampaignResponse(
            success=True,
            message=result["message"],
            campaign_id=campaign_id,
            campaign_name=result["campaign_name"],
            total_leads_enrolled=enrollment_result.get("enrolled_count", 0),
            schedule_preview=result.get("schedule_preview")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating campaign: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create campaign: {str(e)}"
        )


@router.get("/list")
async def list_campaigns(
    campaign_type: Optional[str] = Query(None, description="Filter by type (whatsapp/email)"),
    status: Optional[str] = Query(None, description="Filter by status (active/paused)"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    List all campaigns with filtering (Admin only)
    
    - Supports filtering by type and status
    - Paginated results
    - Includes enrollment counts
    """
    try:
        skip = (page - 1) * limit
        
        # Get campaigns from service
        result = await campaign_service.list_campaigns(
            campaign_type=campaign_type,
            status=status,
            skip=skip,
            limit=limit
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to list campaigns"
            )
        
        # Enrich with enrollment stats
        db = get_database()
        campaigns = result["campaigns"]
        
        for campaign in campaigns:
            # Get enrollment count
            enrolled = await db.campaign_tracking.count_documents({
                "campaign_id": campaign["campaign_id"],
                "job_type": "enrollment"
            })
            
            # Get messages sent count
            messages_sent = await db.campaign_tracking.count_documents({
                "campaign_id": campaign["campaign_id"],
                "job_type": "message_job",
                "status": "completed"
            })
            
            # Get pending messages count
            messages_pending = await db.campaign_tracking.count_documents({
                "campaign_id": campaign["campaign_id"],
                "job_type": "message_job",
                "status": "pending"
            })
            
            campaign["enrolled_leads"] = enrolled
            campaign["messages_sent"] = messages_sent
            campaign["messages_pending"] = messages_pending
        
        return {
            "success": True,
            "campaigns": campaigns,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": result["total"],
                "pages": (result["total"] + limit - 1) // limit
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing campaigns: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list campaigns: {str(e)}"
        )


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """Get campaign details by ID (Admin only)"""
    try:
        campaign = await campaign_service.get_campaign(campaign_id)
        
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found"
            )
        
        return {
            "success": True,
            "campaign": campaign
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting campaign {campaign_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get campaign: {str(e)}"
        )


# ============================================================================
# CAMPAIGN CONTROL ENDPOINTS
# ============================================================================

@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Pause campaign (Admin only)
    
    - Stops new enrollments
    - Pending jobs remain but won't execute
    """
    try:
        success = await campaign_service.pause_campaign(campaign_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found or already paused"
            )
        
        return {
            "success": True,
            "message": "Campaign paused successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing campaign: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause campaign: {str(e)}"
        )


@router.post("/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Resume paused campaign (Admin only)
    
    - Resumes enrollments
    - Pending jobs will execute
    """
    try:
        success = await campaign_service.resume_campaign(campaign_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found or not paused"
            )
        
        return {
            "success": True,
            "message": "Campaign resumed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming campaign: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume campaign: {str(e)}"
        )


@router.delete("/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Delete campaign (Admin only)
    
    - Soft delete (marks as deleted)
    - Cancels all pending jobs
    """
    try:
        db = get_database()
        
        # Soft delete campaign
        success = await campaign_service.delete_campaign(campaign_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found"
            )
        
        # Cancel all pending jobs
        await db.campaign_tracking.update_many(
            {
                "campaign_id": campaign_id,
                "job_type": "message_job",
                "status": "pending"
            },
            {
                "$set": {
                    "status": "cancelled",
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return {
            "success": True,
            "message": "Campaign deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting campaign: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete campaign: {str(e)}"
        )


# ============================================================================
# CAMPAIGN STATISTICS ENDPOINTS
# ============================================================================

@router.get("/{campaign_id}/stats")
async def get_campaign_stats(
    campaign_id: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Get detailed campaign statistics (Admin only)
    
    - Enrollment counts by status
    - Message delivery statistics
    - Next scheduled messages
    """
    try:
        db = get_database()
        
        # Get campaign
        campaign = await campaign_service.get_campaign(campaign_id)
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found"
            )
        
        # Enrollment statistics
        total_enrolled = await db.campaign_tracking.count_documents({
            "campaign_id": campaign_id,
            "job_type": "enrollment"
        })
        
        active_enrollments = await db.campaign_tracking.count_documents({
            "campaign_id": campaign_id,
            "job_type": "enrollment",
            "status": "active"
        })
        
        completed_enrollments = await db.campaign_tracking.count_documents({
            "campaign_id": campaign_id,
            "job_type": "enrollment",
            "status": "completed"
        })
        
        criteria_not_matched = await db.campaign_tracking.count_documents({
            "campaign_id": campaign_id,
            "job_type": "enrollment",
            "status": "criteria_not_matched"
        })
        
        # Message statistics
        total_sent = await db.campaign_tracking.count_documents({
            "campaign_id": campaign_id,
            "job_type": "message_job",
            "status": "completed"
        })
        
        total_pending = await db.campaign_tracking.count_documents({
            "campaign_id": campaign_id,
            "job_type": "message_job",
            "status": "pending"
        })
        
        total_failed = await db.campaign_tracking.count_documents({
            "campaign_id": campaign_id,
            "job_type": "message_job",
            "status": "failed"
        })
        
        return {
            "success": True,
            "campaign_id": campaign_id,
            "campaign_name": campaign["campaign_name"],
            "status": campaign["status"],
            "enrollments": {
                "total": total_enrolled,
                "active": active_enrollments,
                "completed": completed_enrollments,
                "criteria_not_matched": criteria_not_matched
            },
            "messages": {
                "sent": total_sent,
                "pending": total_pending,
                "failed": total_failed
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting campaign stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get campaign stats: {str(e)}"
        )


@router.get("/{campaign_id}/enrolled-leads")
async def get_enrolled_leads(
    campaign_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Get list of enrolled leads for campaign (Admin only)
    
    - Shows enrollment status
    - Messages sent/pending count
    - Lead details
    """
    try:
        db = get_database()
        skip = (page - 1) * limit
        
        # Get total count
        total = await db.campaign_tracking.count_documents({
            "campaign_id": campaign_id,
            "job_type": "enrollment"
        })
        
        # Get enrollments
        enrollments = await db.campaign_tracking.find({
            "campaign_id": campaign_id,
            "job_type": "enrollment"
        }).sort("enrolled_at", -1).skip(skip).limit(limit).to_list(length=limit)
        
        # Enrich with lead data
        enriched_enrollments = []
        for enrollment in enrollments:
            lead = await db.leads.find_one({"lead_id": enrollment["lead_id"]})
            
            if lead:
                enriched_enrollments.append({
                    "lead_id": enrollment["lead_id"],
                    "lead_name": lead.get("name", "Unknown"),
                    "email": lead.get("email", ""),
                    "enrolled_at": enrollment["enrolled_at"],
                    "enrollment_status": enrollment["status"],
                    "messages_sent": enrollment.get("messages_sent", 0),
                    "current_sequence": enrollment.get("current_sequence", 0)
                })
        
        return {
            "success": True,
            "enrollments": enriched_enrollments,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting enrolled leads: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get enrolled leads: {str(e)}"
        )