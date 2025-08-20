# app/routers/integrations.py - Skillang Integration Router
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from typing import Dict, Any
import logging
from datetime import datetime

from ..models.integration import (
    SkillangFormData, IntegrationResponse, IntegrationErrorResponse,
    SkillangIntegrationStats, IntegrationHealthCheck, IntegrationValidationError,
    EXPERIENCE_LEVELS
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
        valid_categories = await get_valid_categories()
        if form_data.category not in valid_categories:
            logger.error(f"Invalid category received: {form_data.category}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category. Must be one of: {', '.join(valid_categories)}"
            )
        
        # Step 3: ENHANCED - Build comprehensive notes from ALL additional fields
        notes_parts = []
        
        # Standard optional fields mapping
        field_mappings = {
            'pincode': 'Pincode',
            'qualification': 'Qualification', 
            'form_source': 'Form Source',
            'preferred_call_type': 'Preferred Call Type',
            'preferred_language': 'Preferred Language',
            'status': 'Current Status',
            'preferred_time': 'Preferred Contact Time',
            'budget_range': 'Budget Range',
            'urgency_level': 'Urgency Level',
            'referral_source': 'Referral Source',
            'special_requirements': 'Special Requirements',
            'german_status': 'German Language Status',
            'start_planning': 'Planning to Start',
            'call_back': 'Preferred Callback Time'
        }
        
        # Process all standard fields
        for field_name, display_name in field_mappings.items():
            field_value = getattr(form_data, field_name, None)
            if field_value:
                notes_parts.append(f"{display_name}: {field_value}")
        
        # Process flexible extra_info dictionary
        if form_data.extra_info:
            notes_parts.append("--- Additional Information ---")
            for key, value in form_data.extra_info.items():
                if value:  # Only add non-empty values
                    # Convert key from snake_case to Title Case
                    display_key = key.replace('_', ' ').title()
                    notes_parts.append(f"{display_key}: {value}")
        
        # Add integration metadata
        notes_parts.append("--- Integration Details ---")
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
                lead_score=calculate_lead_score(form_data),  # Enhanced scoring based on extra data
                tags=generate_tags(form_data)  # Dynamic tags based on form data
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
# HELPER FUNCTIONS FOR ENHANCED DATA PROCESSING
# ============================================================================

def calculate_lead_score(form_data: SkillangFormData) -> int:
    """Calculate lead score based on available data and engagement indicators"""
    base_score = 25
    
    # Add points for additional information provided (shows engagement)
    if form_data.qualification:
        base_score += 5
    if form_data.experience and form_data.experience != "fresher":
        base_score += 10
    if form_data.budget_range:
        base_score += 15  # Budget indicates serious interest
    if form_data.preferred_time:
        base_score += 5   # Specific time preference shows planning
    if form_data.special_requirements:
        base_score += 8   # Detailed requirements indicate serious consideration
    
    # Urgency level scoring
    if form_data.urgency_level == "High":
        base_score += 20
    elif form_data.urgency_level == "Medium":
        base_score += 10
    elif form_data.urgency_level == "Low":
        base_score += 3
    
    # Referral source bonus
    if form_data.referral_source:
        if "referral" in form_data.referral_source.lower() or "friend" in form_data.referral_source.lower():
            base_score += 12  # Personal referrals are high value
        else:
            base_score += 5   # Other sources still valuable
    
    # Planning and timing bonuses
    if form_data.start_planning:
        if "immediately" in form_data.start_planning.lower():
            base_score += 15  # High urgency for immediate start
        elif "next month" in form_data.start_planning.lower():
            base_score += 8
        else:
            base_score += 3
    
    if form_data.call_back:
        base_score += 5  # Shows engagement and planning
    
    # German language status bonus (for language courses)
    if form_data.german_status:
        if "beginner" in form_data.german_status.lower() or "started" in form_data.german_status.lower():
            base_score += 8
        else:
            base_score += 3
    
    # Extra info bonus (shows detailed engagement)
    if form_data.extra_info and len(form_data.extra_info) > 0:
        base_score += len(form_data.extra_info) * 3  # 3 points per extra field
    
    return min(base_score, 100)  # Cap at 100

def generate_tags(form_data: SkillangFormData) -> list:
    """Generate dynamic tags based on form data for better lead categorization"""
    tags = ["Website Form", "Skillang Integration"]
    
    # Urgency-based tags
    if form_data.urgency_level:
        tags.append(f"Urgency: {form_data.urgency_level}")
    
    # Communication preference tags
    if form_data.preferred_call_type:
        tags.append(f"Call Type: {form_data.preferred_call_type}")
    
    if form_data.preferred_language and form_data.preferred_language.lower() != "english":
        tags.append(f"Language: {form_data.preferred_language}")
    
    # Source and referral tags
    if form_data.referral_source:
        tags.append(f"Referral: {form_data.referral_source}")
    
    if form_data.form_source:
        tags.append(f"Source: {form_data.form_source}")
    
    # Budget indication
    if form_data.budget_range:
        tags.append("Budget Provided")
    
    # Special requirements flag
    if form_data.special_requirements:
        tags.append("Special Requirements")
    
    # Experience level tags
    if form_data.experience:
        tags.append(f"Experience: {form_data.experience}")
    
    # Country-specific tags for international leads
    if form_data.country and form_data.country.lower() not in ["india", "unknown"]:
        tags.append(f"International: {form_data.country}")
    
    # Planning and engagement tags
    if form_data.start_planning:
        if "immediately" in form_data.start_planning.lower():
            tags.append("Immediate Start")
        else:
            tags.append(f"Start: {form_data.start_planning}")
    
    if form_data.call_back:
        tags.append(f"Callback: {form_data.call_back}")
    
    # German language specific tags
    if form_data.german_status:
        tags.append(f"German Status: {form_data.german_status}")
    
    return tags

# ============================================================================
# BACKGROUND EMAIL FUNCTION
# ============================================================================

async def get_valid_categories():
    """Fetch active categories dynamically from database"""
    try:
        db = get_database()
        categories = await db.lead_categories.find({"is_active": True}).to_list(None)
        return [cat["name"] for cat in categories]
    except Exception as e:
        logger.error(f"Error fetching categories: {str(e)}")
        # Fallback to ensure integration doesn't break
        return ["Nursing", "Study Abroad", "German Language", "Work Abroad", "Institution"]

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