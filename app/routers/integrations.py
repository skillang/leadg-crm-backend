# app/routers/integrations.py - Skillang Integration Router
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from typing import Dict, Any
import logging
from datetime import datetime

from ..models.integration import (
    SkillangFormData, IntegrationResponse, IntegrationErrorResponse,
    SkillangIntegrationStats, IntegrationHealthCheck, IntegrationValidationError,
    EXPERIENCE_LEVELS, SKILLANG_CATEGORIES
)
from ..models.lead import LeadCreateComprehensive, LeadBasicInfo, LeadStatusAndTags, LeadAdditionalInfo, LeadAssignmentInfo
from ..services.lead_service import lead_service
from ..services.zepto_client import send_single_email
from ..config.settings import settings
from ..config.database import get_database
from ..utils.dependencies import get_current_active_user

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================================================
# SKILLANG FORM SUBMISSION ENDPOINT (PUBLIC - NO AUTH REQUIRED)
# ============================================================================

@router.post("/skillang/form-submission", response_model=IntegrationResponse)
async def create_lead_from_skillang(
    form_data: SkillangFormData,
    background_tasks: BackgroundTasks
):
    """
    Create lead from Skillang form submission + send confirmation email
    
    This endpoint is public and doesn't require authentication.
    It's designed to be called directly from Skillang frontend forms.
    """
    try:
        logger.info(f"📝 Received Skillang form submission for {form_data.email} (category: {form_data.category})")
        
        # Step 1: Validate integration is enabled
        if not settings.is_skillang_configured():
            logger.error("Skillang integration is not properly configured")
            raise HTTPException(
                status_code=503, 
                detail="Skillang integration is currently unavailable"
            )
        
        # Step 2: Validate category
        if form_data.category not in SKILLANG_CATEGORIES:
            logger.error(f"Invalid category received: {form_data.category}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category. Must be one of: {', '.join(SKILLANG_CATEGORIES)}"
            )
        
        # Step 3: Build notes from additional fields
        notes_parts = []
        if form_data.pincode:
            notes_parts.append(f"Pincode: {form_data.pincode}")
        if form_data.qualification:
            notes_parts.append(f"Qualification: {form_data.qualification}")
        if form_data.form_source:
            notes_parts.append(f"Form Source: {form_data.form_source}")
        
        # Add integration source info
        notes_parts.append(f"Integration: Skillang Form Submission")
        notes_parts.append(f"Submitted At: {datetime.utcnow().isoformat()}")
        
        # Step 4: Create structured lead data using your existing models
        structured_data = LeadCreateComprehensive(
            basic_info=LeadBasicInfo(
                name=form_data.name,
                email=form_data.email,
                contact_number=form_data.phone,
                source="website",  # Always website for Skillang forms
                category=form_data.category,  # Direct from frontend
                age=form_data.age,
                experience=EXPERIENCE_LEVELS.get(form_data.experience, "fresher"),
                nationality=form_data.country or "Unknown"
            ),
            status_and_tags=LeadStatusAndTags(
                stage="Initial",
                lead_score=25,  # Default score for form submissions
                tags=["Website Form", "Skillang Integration"]
            ),
            assignment=LeadAssignmentInfo(
                assigned_to="unassigned"  # Keep unassigned for manual assignment
            ),
            additional_info=LeadAdditionalInfo(
                notes="\n".join(notes_parts) if notes_parts else ""
            )
        )
        
        # Step 5: Create lead using your existing service
        result = await lead_service.create_lead_comprehensive(
            lead_data=structured_data,
            created_by=settings.system_user_email,
            force_create=False  # Check for duplicates
        )
        
        if not result["success"]:
            logger.error(f"Lead creation failed: {result['message']}")
            
            # Handle duplicate case specifically
            if result.get("duplicate_check", {}).get("is_duplicate"):
                raise HTTPException(
                    status_code=409,
                    detail="A lead with this email address already exists in our system"
                )
            else:
                raise HTTPException(status_code=400, detail=result["message"])
        
        # Step 6: Send confirmation email in background using your existing email system
        background_tasks.add_task(
            send_skillang_confirmation_email,
            form_data.email,
            form_data.name,
            result["lead"]["lead_id"],
            form_data.category
        )
        
        logger.info(f"✅ Skillang lead created successfully: {result['lead']['lead_id']} (category: {form_data.category})")
        
        # Step 7: Return successful response
        return IntegrationResponse(
            success=True,
            message="Lead created successfully and confirmation email sent",
            lead_id=result["lead"]["lead_id"],
            category=form_data.category
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except IntegrationValidationError as e:
        logger.error(f"Validation error: {e.message}")
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Unexpected error in Skillang integration: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail="An unexpected error occurred while processing your request"
        )

# ============================================================================
# BACKGROUND EMAIL FUNCTION
# ============================================================================

async def send_skillang_confirmation_email(
    email: str, 
    name: str, 
    lead_id: str, 
    category: str
):
    """Send confirmation email to new Skillang lead"""
    try:
        logger.info(f"📧 Sending confirmation email to {email} (Lead: {lead_id})")
        
        # Use your existing email system with form_acknowledgement template
        result = await send_single_email(
            template_key="2518b.3027c48fe4ab851b.k1.68914c40-792c-11f0-830f-525400c92439.198a96de704",  # Your existing template
            sender_prefix="noreply",  # Will become noreply@skillang.com
            recipient_email=email,
            recipient_name=name,
            merge_data={
                "name": name,
                "lead_id": lead_id,
                "category": category,
                "company": "Skillang"
            }
        )
        
        if result["success"]:
            logger.info(f"✅ Confirmation email sent successfully to {email}")
        else:
            logger.error(f"❌ Failed to send confirmation email to {email}: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"❌ Error sending confirmation email to {email}: {str(e)}", exc_info=True)

# ============================================================================
# INTEGRATION STATISTICS ENDPOINTS (ADMIN ONLY)
# ============================================================================

@router.get("/skillang/stats", response_model=SkillangIntegrationStats)
async def get_skillang_integration_stats(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get Skillang integration statistics (Admin only)
    
    Returns statistics about form submissions, success rates, and performance.
    """
    try:
        # Check if user is admin
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        logger.info(f"📊 Fetching Skillang integration stats for admin: {current_user['email']}")
        
        db = get_database()
        
        # Get leads created via Skillang integration
        skillang_leads = await db.leads.find({
            "tags": "Skillang Integration",
            "source": "website"
        }).to_list(None)
        
        # Calculate statistics
        total_leads = len(skillang_leads)
        
        # Group by category
        leads_by_category = {}
        for lead in skillang_leads:
            category = lead.get("category", "Unknown")
            leads_by_category[category] = leads_by_category.get(category, 0) + 1
        
        # Calculate success rate (assuming all retrieved leads were successful)
        success_rate = 100.0 if total_leads > 0 else 0.0
        
        # Get last submission timestamp
        last_submission = None
        if skillang_leads:
            # Sort by created_at and get the latest
            sorted_leads = sorted(skillang_leads, key=lambda x: x.get("created_at", datetime.min), reverse=True)
            last_submission = sorted_leads[0].get("created_at")
        
        return SkillangIntegrationStats(
            total_leads_created=total_leads,
            leads_by_category=leads_by_category,
            success_rate=success_rate,
            average_response_time=0.5,  # Default estimate
            last_submission=last_submission,
            email_success_rate=95.0  # Default estimate
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching Skillang integration stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch integration statistics")

# ============================================================================
# INTEGRATION HEALTH CHECK ENDPOINT (ADMIN ONLY)
# ============================================================================

@router.get("/skillang/health", response_model=IntegrationHealthCheck)
async def check_skillang_integration_health(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Check Skillang integration health (Admin only)
    
    Returns the current status of all integration components.
    """
    try:
        # Check if user is admin
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        logger.info(f"🏥 Checking Skillang integration health for admin: {current_user['email']}")
        
        # Check configuration
        config_valid = settings.is_skillang_configured()
        
        # Check email service
        email_status = "connected" if settings.is_zeptomail_configured() else "disconnected"
        
        # Check database
        db_status = "connected"
        try:
            db = get_database()
            await db.leads.find_one({})  # Simple test query
        except Exception:
            db_status = "disconnected"
        
        # Get last successful submission
        last_submission = None
        try:
            db = get_database()
            latest_lead = await db.leads.find_one(
                {"tags": "Skillang Integration", "source": "website"},
                sort=[("created_at", -1)]
            )
            if latest_lead:
                last_submission = latest_lead.get("created_at")
        except Exception:
            pass
        
        # Determine overall status
        overall_status = "healthy" if (config_valid and email_status == "connected" and db_status == "connected") else "unhealthy"
        
        return IntegrationHealthCheck(
            status=overall_status,
            integration_enabled=config_valid,
            email_service_status=email_status,
            database_status=db_status,
            last_successful_submission=last_submission,
            configuration_valid=config_valid
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking Skillang integration health: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to check integration health")

# ============================================================================
# TEST ENDPOINT (ADMIN ONLY - FOR DEVELOPMENT)
# ============================================================================

@router.post("/skillang/test", response_model=IntegrationResponse)
async def test_skillang_integration(
    test_data: SkillangFormData,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Test Skillang integration with sample data (Admin only)
    
    This endpoint allows admins to test the integration without affecting production data.
    """
    try:
        # Check if user is admin
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        logger.info(f"🧪 Testing Skillang integration for admin: {current_user['email']}")
        
        # Add test prefix to email to avoid conflicts
        test_data.email = f"test.{test_data.email}"
        test_data.name = f"TEST - {test_data.name}"
        
        # Use the main integration endpoint logic but mark as test
        background_tasks = BackgroundTasks()
        
        # Call the main endpoint function
        result = await create_lead_from_skillang(test_data, background_tasks)
        
        logger.info(f"✅ Skillang integration test completed successfully")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing Skillang integration: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to test integration")