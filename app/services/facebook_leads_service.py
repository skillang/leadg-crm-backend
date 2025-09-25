# app/services/facebook_leads_service.py
# Facebook Leads Center Integration for LeadG CRM
# Handles lead retrieval, webhooks, and sync with CRM

import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
from fastapi import HTTPException
from ..models.lead import (
    LeadCreateComprehensive, 
    LeadBasicInfo, 
    LeadStatusAndTags, 
    LeadAdditionalInfo,
    LeadAssignmentInfo,  # Add this
    ExperienceLevel      # Add this
)

from ..config.database import get_database
from ..config.settings import settings
from .lead_service import lead_service

logger = logging.getLogger(__name__)

class FacebookLeadsService:
    """Service for Facebook Leads Center integration"""
    
    def __init__(self):
        self.base_url = f"https://graph.facebook.com/{settings.facebook_api_version}"
        self.access_token = settings.facebook_page_access_token
        self.page_id = settings.facebook_page_id
        self.app_id = settings.facebook_app_id
        self.app_secret = settings.facebook_app_secret
        
    async def initialize_facebook_config(self):
        """Initialize Facebook configuration from database/settings"""
        db = get_database()
        config = await db.facebook_config.find_one({"active": True})
        
        if config:
            self.access_token = config.get("access_token")
            self.page_id = config.get("page_id")
            self.app_id = config.get("app_id")
            self.app_secret = config.get("app_secret")
            logger.info("✅ Facebook configuration loaded")
        else:
            logger.warning("⚠️ No active Facebook configuration found")

    async def save_facebook_config(self, config_data: Dict[str, Any], user_email: str):
        """Save Facebook API configuration"""
        db = get_database()
        
        # Deactivate existing configs
        await db.facebook_config.update_many(
            {"active": True},
            {"$set": {"active": False, "updated_at": datetime.utcnow()}}
        )
        
        # Save new config
        config_doc = {
            "app_id": config_data["app_id"],
            "app_secret": config_data["app_secret"],
            "access_token": config_data["access_token"],
            "page_id": config_data["page_id"],
            "webhook_verify_token": config_data.get("webhook_verify_token"),
            "active": True,
            "created_by": user_email,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = await db.facebook_config.insert_one(config_doc)
        
        # Update instance variables
        await self.initialize_facebook_config()
        
        return {
            "success": True,
            "message": "Facebook configuration saved successfully",
            "config_id": str(result.inserted_id)
        }

    async def verify_facebook_access(self) -> Dict[str, Any]:
        """Verify Facebook API access and permissions"""
        if not self.access_token:
            await self.initialize_facebook_config()
            
        if not self.access_token:
            return {"success": False, "error": "No access token configured"}
        
        try:
            async with aiohttp.ClientSession() as session:
                # Test API access
                url = f"{self.base_url}/me"
                params = {"access_token": self.access_token}
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "user_info": data,
                            "message": "Facebook API access verified"
                        }
                    else:
                        error_data = await response.json()
                        return {
                            "success": False,
                            "error": error_data.get("error", {}).get("message", "Unknown error")
                        }
                        
        except Exception as e:
            logger.error(f"Facebook API verification failed: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_lead_forms(self, page_id: Optional[str] = None) -> Dict[str, Any]:
        """Get all lead forms for a Facebook page"""
        target_page_id = page_id or self.page_id
        
        if not target_page_id or not self.access_token:
            return {"success": False, "error": "Page ID or access token not configured"}
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/{target_page_id}/leadgen_forms"
                params = {
                    "access_token": self.access_token,
                    "fields": "id,name,status,created_time,leads_count,page_id,context_card"
                }
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "forms": data.get("data", []),
                            "total_forms": len(data.get("data", []))
                        }
                    else:
                        error_data = await response.json()
                        return {
                            "success": False,
                            "error": error_data.get("error", {}).get("message", "Unknown error")
                        }
                        
        except Exception as e:
            logger.error(f"Failed to get lead forms: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_leads_from_form(self, form_id: str, limit: int = 100) -> Dict[str, Any]:
        """Get leads from a specific lead form"""
        if not self.access_token:
            await self.initialize_facebook_config()
            
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/{form_id}/leads"
                params = {
                    "access_token": self.access_token,
                    "limit": limit,
                    "fields": "id,created_time,field_data,platform,ad_id,adset_id,campaign_id"
                }
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        leads = data.get("data", [])
                        
                        # Process leads for CRM format
                        processed_leads = []
                        for lead in leads:
                            processed_lead = await self._process_facebook_lead(lead, form_id)
                            processed_leads.append(processed_lead)
                        
                        return {
                            "success": True,
                            "leads": processed_leads,
                            "total_leads": len(processed_leads),
                            "form_id": form_id
                        }
                    else:
                        error_data = await response.json()
                        return {
                            "success": False,
                            "error": error_data.get("error", {}).get("message", "Unknown error")
                        }
                        
        except Exception as e:
            logger.error(f"Failed to get leads from form {form_id}: {str(e)}")
            return {"success": False, "error": str(e)}

    async def _process_facebook_lead(self, fb_lead: Dict[str, Any], form_id: str) -> Dict[str, Any]:
        """Process Facebook lead data into CRM format"""
        field_data = {item["name"]: item["values"][0] if item["values"] else "" 
                     for item in fb_lead.get("field_data", [])}
        
        # Map Facebook fields to CRM fields
        processed_lead = {
            "facebook_lead_id": fb_lead["id"],
            "form_id": form_id,
            "platform": fb_lead.get("platform", "facebook"),
            "created_time": fb_lead["created_time"],
            "ad_id": fb_lead.get("ad_id"),
            "campaign_id": fb_lead.get("campaign_id"),
            "adset_id": fb_lead.get("adset_id"),
            
            # CRM mapped fields
            "name": field_data.get("full_name", field_data.get("first_name", "")),
            "email": field_data.get("email", ""),
            "phone": field_data.get("phone_number", field_data.get("mobile", "")),
            "course_interest": field_data.get("course_interest", field_data.get("program", "")),
            "city": field_data.get("city", ""),
            "experience": field_data.get("experience", ""),
            "education": field_data.get("education", ""),
            "age": field_data.get("age", ""),
            "nationality": field_data.get("nationality", ""),
            
            # Additional fields
            "source": "Facebook Leads",
            "raw_field_data": field_data
        }
        
        return processed_lead

    async def import_leads_to_crm(self, form_id: str, user_email: str, 
                                category: str = "Digital Marketing", limit: int = 100) -> Dict[str, Any]:
        """Import Facebook leads to LeadG CRM with proper duplicate detection"""
        try:
            # Get leads from Facebook with limit
            fb_result = await self.get_leads_from_form(form_id, limit)
            
            if not fb_result["success"]:
                return fb_result
            
            fb_leads = fb_result["leads"]
            imported_count = 0
            failed_count = 0
            skipped_count = 0  # Now captures ALL duplicates
            errors = []
            
            db = get_database()
            
            # Import lead service
            from .lead_service import lead_service
            
            for fb_lead in fb_leads:
                try:
                    # STEP 1: Check Facebook ID duplicate (existing logic)
                    existing_lead = await db.leads.find_one({
                        "facebook_integration.facebook_lead_id": fb_lead["facebook_lead_id"]
                    })
                    
                    if existing_lead:
                        skipped_count += 1
                        logger.info(f"⏭️ Skipped Facebook duplicate: {fb_lead['facebook_lead_id']} (already imported)")
                        continue
                    
                    # STEP 2: Extract lead data for CRM duplicate check
                    raw_data = fb_lead.get("raw_field_data", {})
                    name = self._extract_name(fb_lead, raw_data)
                    phone = self._extract_phone(fb_lead, raw_data)
                    email = self._extract_email(fb_lead, raw_data)
                    
                    # STEP 3: Check CRM duplicates BEFORE creating lead
                    duplicate_check = await lead_service.check_duplicate_lead(
                        email=email,
                        contact_number=phone
                    )
                    
                    if duplicate_check["is_duplicate"]:
                        skipped_count += 1
                        logger.info(f"⏭️ Skipped CRM duplicate: {fb_lead['facebook_lead_id']} - {duplicate_check['message']}")
                        continue
                    
                    # STEP 4: Extract all other fields for lead creation
                    age = self._extract_age(raw_data)
                    experience = self._extract_experience(raw_data)
                    qualification = self._extract_qualification(raw_data)
                    german_status = self._extract_german_status(raw_data)
                    
                    # Build extra_info for unmapped fields
                    extra_info = self._build_extra_info(raw_data)
                    
                    # Build notes from structured fields
                    notes = self._build_notes_from_facebook_data(
                        qualification, german_status, raw_data
                    )
                    
                    # STEP 5: Create comprehensive lead data structure
                    from ..models.lead import LeadCreateComprehensive, LeadBasicInfo, LeadStatusAndTags, LeadAdditionalInfo
                    
                    lead_data = LeadCreateComprehensive(
                        basic_info=LeadBasicInfo(
                            name=name or "Facebook Lead",
                            email=email or f"facebook_{fb_lead['facebook_lead_id']}@placeholder.com",
                            contact_number=phone,
                            source="facebook-leads",
                            category=category,
                            course_level="undergraduate",
                            age=age,
                            experience=experience or ExperienceLevel.FRESHER,
                            nationality="",
                            current_location="Not mentioned"
                        ),
                        status_and_tags=LeadStatusAndTags(
                            stage="Pending",
                            status="New", 
                            lead_score=0,
                            tags=["Facebook Import", category]
                        ),
                        additional_info=LeadAdditionalInfo(
                            notes=notes,
                            extra_info=extra_info
                        ),
                        assignment=LeadAssignmentInfo(
                            assigned_to="unassigned"
                        )
                    )
                    
                    # STEP 6: Create lead using comprehensive method with force_create=True
                    result = await lead_service.create_lead_comprehensive(
                        lead_data=lead_data,
                        created_by=user_email,
                        force_create=True  # Skip internal duplicate check since we already did it
                    )
                    
                    if result["success"]:
                        # Add Facebook integration metadata to the created lead
                        lead_id = result.get("lead_id")
                        await self._add_facebook_metadata(db, lead_id, fb_lead, form_id)
                        
                        imported_count += 1
                        logger.info(f"✅ Imported Facebook lead: {fb_lead['facebook_lead_id']} → {lead_id}")
                    else:
                        failed_count += 1
                        error_msg = f"Failed to import {fb_lead['facebook_lead_id']}: {result.get('message', 'Unknown error')}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                        
                except Exception as e:
                    failed_count += 1
                    error_msg = f"Error importing {fb_lead.get('facebook_lead_id', 'unknown')}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
            
            # Return the stats structure your frontend team expects
            return {
                "success": True,
                "summary": {
                    "total_facebook_leads": len(fb_leads),
                    "imported_count": imported_count,
                    "failed_count": failed_count,
                    "skipped_count": skipped_count
                },
                "message": f"Successfully processed {len(fb_leads)} Facebook leads: {imported_count} imported, {failed_count} failed, {skipped_count} duplicates skipped",
                "import_details": {
                    "form_id": form_id,
                    "category": category,
                    "user_email": user_email,
                    "processing_time": datetime.utcnow().isoformat()
                },
                "errors": errors[:10] if errors else []  # Limit errors to first 10 for response size
            }
                
        except Exception as e:
            logger.error(f"Failed to import leads from form {form_id}: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to import leads: {str(e)}",
                "summary": {
                    "total_facebook_leads": 0,
                    "imported_count": 0,
                    "failed_count": 0,
                    "skipped_count": 0
                }
            }
    def _extract_name(self, fb_lead: Dict[str, Any], raw_data: Dict[str, Any]) -> str:
        """Extract name from various possible field names"""
        return (
            fb_lead.get("name") or 
            raw_data.get("full name") or 
            raw_data.get("full_name") or
            raw_data.get("name") or
            ""
        ).strip()

    def _extract_phone(self, fb_lead: Dict[str, Any], raw_data: Dict[str, Any]) -> str:
        """Extract phone from various possible field names"""
        # Your actual data uses 'phone' as the key, so prioritize that
        phone = (
            raw_data.get("phone") or           # This is your actual field name
            fb_lead.get("phone") or 
            raw_data.get("phone_number") or
            raw_data.get("phone number") or
            raw_data.get("mobile") or
            ""
        ).strip()
        
        # Remove '+' prefix if present and ensure 10+ digits
        if phone:
            # Handle Indian phone numbers: +918331917701 -> 8331917701
            clean_phone = phone.replace("+91", "").replace("+", "").strip()
            if len(clean_phone) >= 10:
                return clean_phone
            else:
                # If phone is too short, use a default to pass validation
                return "0000000000"
    
        return "0000000000"  # Default fallback to pass validation

    def _extract_email(self, fb_lead: Dict[str, Any], raw_data: Dict[str, Any]) -> str:
        """Extract email from various possible field names"""
        return (
            fb_lead.get("email") or 
            raw_data.get("email") or
            ""
        ).strip()

    def _extract_age(self, raw_data: Dict[str, Any]) -> str:
        """Extract age information"""
        return (
            raw_data.get("age information") or
            raw_data.get("age_information") or
            raw_data.get("age") or
            ""
        ).strip()

    def _extract_experience(self, raw_data: Dict[str, Any]) -> str:
        """Extract experience information"""
        return (
            raw_data.get("years of experience ?") or
            raw_data.get("years_of_experience") or
            raw_data.get("experience") or
            ""
        ).strip()

    def _extract_qualification(self, raw_data: Dict[str, Any]) -> str:
        """Extract qualification/education information"""
        return (
            raw_data.get("what is your current qualification?") or
            raw_data.get("current_qualification") or
            raw_data.get("qualification") or
            raw_data.get("education") or
            ""
        ).strip()

    def _extract_german_status(self, raw_data: Dict[str, Any]) -> str:
        """Extract German language status"""
        return (
            raw_data.get("german language status") or
            raw_data.get("german_language_status") or
            raw_data.get("german_status") or
            ""
        ).strip()

    def _build_extra_info(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build extra_info dict from unmapped fields"""
        # Fields that are already mapped to CRM fields
        mapped_fields = {
            "full name", "full_name", "name",
            "phone_number", "phone number", "mobile", "phone",
            "email",
            "age information", "age_information", "age",
            "years of experience ?", "years_of_experience", "experience",
            "what is your current qualification?", "current_qualification", "qualification", "education",
            "german language status", "german_language_status", "german_status"
        }
        
        extra_info = {}
        for key, value in raw_data.items():
            if key.lower() not in mapped_fields and value:
                # Clean up key name for display
                clean_key = key.replace("_", " ").title()
                extra_info[clean_key] = value
        
        return extra_info

    def _build_notes_from_facebook_data(self, qualification: str, german_status: str, raw_data: Dict[str, Any]) -> str:
        """Build notes section from structured Facebook data"""
        notes_parts = []
        
        if qualification:
            notes_parts.append(f"Qualification: {qualification}")
        
        if german_status:
            notes_parts.append(f"German Status: {german_status}")
        
        # Add any study abroad specific information
        country_interest = raw_data.get("which_country_are_you_interested_in_studying_abroad?")
        if country_interest:
            notes_parts.append(f"Country Interest: {country_interest}")
        
        study_level = raw_data.get("what_level_of_study_are_you_planning_to_pursue?")
        if study_level:
            notes_parts.append(f"Study Level: {study_level}")
        
        intake = raw_data.get("which_intake_are_you_planning_to_join?")
        if intake:
            notes_parts.append(f"Preferred Intake: {intake}")
        
        # Add source information
        notes_parts.append("--- Import Details ---")
        notes_parts.append("Source: Facebook Lead Form")
        notes_parts.append(f"Imported: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return "\n".join(notes_parts)

    async def _add_facebook_metadata(self, db, lead_id: str, fb_lead: Dict[str, Any], form_id: str):
        """Add Facebook integration metadata to the created lead"""
        try:
            facebook_metadata = {
                "facebook_integration": {
                    "facebook_lead_id": fb_lead["facebook_lead_id"],
                    "form_id": form_id,
                    "platform": fb_lead.get("platform", "facebook"),
                    "ad_id": fb_lead.get("ad_id"),
                    "campaign_id": fb_lead.get("campaign_id"),
                    "adset_id": fb_lead.get("adset_id"),
                    "created_time": fb_lead.get("created_time"),
                    "raw_data": fb_lead.get("raw_field_data", {}),
                    "imported_at": datetime.utcnow()
                }
            }
            
            await db.leads.update_one(
                {"lead_id": lead_id},
                {"$set": facebook_metadata}
            )
            
        except Exception as e:
            logger.error(f"Failed to add Facebook metadata to lead {lead_id}: {str(e)}")
            # Don't fail the import for metadata errors
    async def setup_webhook(self, webhook_url: str, verify_token: str) -> Dict[str, Any]:
        """Set up Facebook webhook for real-time lead notifications"""
        if not self.access_token or not self.page_id:
            return {"success": False, "error": "Facebook configuration not complete"}
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/{self.page_id}/subscribed_apps"
                data = {
                    "access_token": self.access_token,
                    "subscribed_fields": "leadgen"
                }
                
                async with session.post(url, data=data) as response:
                    if response.status == 200:
                        # Save webhook config to database
                        db = get_database()
                        webhook_config = {
                            "webhook_url": webhook_url,
                            "verify_token": verify_token,
                            "page_id": self.page_id,
                            "subscribed_fields": ["leadgen"],
                            "active": True,
                            "created_at": datetime.utcnow()
                        }
                        
                        await db.facebook_webhooks.replace_one(
                            {"page_id": self.page_id},
                            webhook_config,
                            upsert=True
                        )
                        
                        return {
                            "success": True,
                            "message": "Webhook subscription created successfully",
                            "webhook_url": webhook_url
                        }
                    else:
                        error_data = await response.json()
                        return {
                            "success": False,
                            "error": error_data.get("error", {}).get("message", "Unknown error")
                        }
                        
        except Exception as e:
            logger.error(f"Failed to setup webhook: {str(e)}")
            return {"success": False, "error": str(e)}

    async def process_webhook_lead(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming webhook lead data"""
        try:
            entry = webhook_data.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            
            if changes.get("field") != "leadgen":
                return {"success": False, "error": "Not a leadgen webhook"}
            
            lead_id = changes.get("value", {}).get("leadgen_id")
            form_id = changes.get("value", {}).get("form_id")
            
            if not lead_id or not form_id:
                return {"success": False, "error": "Missing lead_id or form_id"}
            
            # Get lead details from Facebook
            lead_details = await self._get_single_lead(lead_id)
            
            if lead_details["success"]:
                processed_lead = await self._process_facebook_lead(
                    lead_details["lead"], form_id
                )
                
                # Import to CRM automatically
                import_result = await self._import_single_lead_to_crm(
                    processed_lead, "system@leadg.com"
                )
                
                return {
                    "success": True,
                    "message": "Webhook lead processed successfully",
                    "lead_id": lead_id,
                    "import_result": import_result
                }
            else:
                return lead_details
                
        except Exception as e:
            logger.error(f"Failed to process webhook lead: {str(e)}")
            return {"success": False, "error": str(e)}

    async def _get_single_lead(self, lead_id: str) -> Dict[str, Any]:
        """Get single lead details from Facebook"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/{lead_id}"
                params = {
                    "access_token": self.access_token,
                    "fields": "id,created_time,field_data,platform,ad_id,adset_id,campaign_id"
                }
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        lead_data = await response.json()
                        return {"success": True, "lead": lead_data}
                    else:
                        error_data = await response.json()
                        return {
                            "success": False,
                            "error": error_data.get("error", {}).get("message", "Unknown error")
                        }
                        
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _import_single_lead_to_crm(self, processed_lead: Dict[str, Any], 
                                       user_email: str) -> Dict[str, Any]:
        """Import single processed lead to CRM"""
        try:
            # Check if lead already exists
            db = get_database()
            existing_lead = await db.leads.find_one({
                "facebook_lead_id": processed_lead["facebook_lead_id"]
            })
            
            if existing_lead:
                return {"success": False, "error": "Lead already exists", "skipped": True}
            
            # Prepare lead data for CRM
            lead_data = {
                "name": processed_lead["name"],
                "email": processed_lead["email"],
                "contact_number": processed_lead["phone"],
                "category": "Digital Marketing",  # Default category
                "course_level": "Beginner",
                "course_interest": processed_lead["course_interest"],
                "city": processed_lead["city"],
                "experience": processed_lead["experience"],
                "education": processed_lead["education"],
                "age": processed_lead["age"],
                "nationality": processed_lead["nationality"],
                "source": "Facebook Leads",
                "facebook_integration": {
                    "facebook_lead_id": processed_lead["facebook_lead_id"],
                    "form_id": processed_lead["form_id"],
                    "platform": processed_lead["platform"],
                    "ad_id": processed_lead["ad_id"],
                    "campaign_id": processed_lead["campaign_id"],
                    "adset_id": processed_lead["adset_id"],
                    "created_time": processed_lead["created_time"],
                    "raw_data": processed_lead["raw_field_data"]
                }
            }
            
            # Create lead in CRM
            result = await lead_service.create_lead(lead_data, user_email)
            return result
            
        except Exception as e:
            logger.error(f"Failed to import single lead: {str(e)}")
            return {"success": False, "error": str(e)}



    async def auto_refresh_token_if_needed(self):
        """Auto-refresh Facebook page access token if needed"""
        try:
            if not self.access_token:
                await self.initialize_facebook_config()
                
            # Check token info
            async with aiohttp.ClientSession() as session:
                debug_url = f"https://graph.facebook.com/debug_token"
                params = {
                    "input_token": self.access_token,
                    "access_token": f"{self.app_id}|{self.app_secret}"
                }
                
                async with session.get(debug_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        token_data = data.get("data", {})
                        expires_at = token_data.get("expires_at")
                        
                        if expires_at:
                            expires_date = datetime.fromtimestamp(expires_at)
                            days_left = (expires_date - datetime.utcnow()).days
                            
                            logger.info(f"Facebook token expires in {days_left} days ({expires_date})")
                            
                            # Refresh if expires within 10 days
                            if days_left <= 10:
                                logger.info("Token expires soon, attempting refresh...")
                                
                                refresh_url = f"https://graph.facebook.com/oauth/access_token"
                                refresh_params = {
                                    "grant_type": "fb_exchange_token",
                                    "client_id": self.app_id,
                                    "client_secret": self.app_secret,
                                    "fb_exchange_token": self.access_token
                                }
                                
                                async with session.get(refresh_url, params=refresh_params) as refresh_response:
                                    if refresh_response.status == 200:
                                        refresh_data = await refresh_response.json()
                                        new_token = refresh_data.get("access_token")
                                        
                                        # Update database config
                                        db = get_database()
                                        await db.facebook_config.update_one(
                                            {"active": True},
                                            {"$set": {
                                                "access_token": new_token,
                                                "last_refreshed": datetime.utcnow(),
                                                "updated_at": datetime.utcnow()
                                            }}
                                        )
                                        
                                        # Update instance variable
                                        self.access_token = new_token
                                        
                                        logger.info("Facebook token refreshed successfully!")
                                        return {"success": True, "refreshed": True, "new_token": new_token}
                                    else:
                                        error_data = await refresh_response.json()
                                        error_msg = error_data.get("error", {}).get("message", "Refresh failed")
                                        logger.error(f"Token refresh failed: {error_msg}")
                                        return {"success": False, "error": error_msg}
                            else:
                                return {"success": True, "valid": True, "days_left": days_left}
                        else:
                            return {"success": True, "no_expiry": True}
                    else:
                        error_data = await response.json()
                        return {"success": False, "error": error_data.get("error", {}).get("message", "Token validation failed")}
                        
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            return {"success": False, "error": str(e)}
# Create service instance
facebook_leads_service = FacebookLeadsService()