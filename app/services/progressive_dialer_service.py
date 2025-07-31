# app/services/progressive_dialer_service.py
# Progressive Dialer Service - Multi-lead Sequential Calling
# Handles Tata Progressive Dialer campaigns, session management, and real-time monitoring

import logging
import asyncio
import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from bson import ObjectId
import json
import re
import random

# 🔧 FIX: Setup logging FIRST before using logger anywhere
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from ..config.database import get_database
from ..config.settings import get_settings

# Import Tata auth service for API access (NOW logger is available)
try:
    from .tata_auth_service import tata_auth_service
    TATA_AUTH_AVAILABLE = True
    logger.info("✅ Tata Auth service imported successfully")
except ImportError as e:
    TATA_AUTH_AVAILABLE = False
    logger.warning(f"⚠️ Tata Auth service not available: {e}")

class ProgressiveDialerService:
    """
    Progressive Dialer Service - Multi-lead Sequential Calling System
    
    Features:
    - Multi-lead campaign creation
    - Agent session management (agent stays on call)
    - Real-time session monitoring and control
    - Lead validation and permission checking
    - Session statistics and performance tracking
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.db = None
        
        # Tata integration settings
        self.tata_auth_service = tata_auth_service if TATA_AUTH_AVAILABLE else None
        self.tata_base_url = getattr(self.settings, 'tata_api_base_url', '')
        self.mock_mode = getattr(self.settings, 'smartflo_mock_mode', False)
        
        # Progressive dialer configuration
        self.max_leads_per_session = 50
        self.default_call_timeout = 30  # seconds
        self.time_between_calls = 3  # seconds
        self.session_timeout = 3600  # 1 hour max session time
        self.max_concurrent_sessions_per_user = 3
        
        logger.info("Progressive Dialer Service initialized")

    def _get_db(self):
        """Lazy database initialization"""
        if self.db is None:
            try:
                self.db = get_database()
            except RuntimeError:
                return None
        return self.db

    # =============================================================================
    # MAIN PROGRESSIVE DIALER METHODS
    # =============================================================================

    async def start_progressive_dialer_session(
        self,
        lead_ids: List[str],
        current_user: Dict[str, Any],
        session_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Start Progressive Dialer Session - Agent stays connected, leads dial sequentially
        
        Args:
            lead_ids: List of lead IDs to call
            current_user: Current user making the request
            session_name: Optional session name
            
        Returns:
            Dict with session details and success status
        """
        try:
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            user_email = current_user.get("email", "unknown")
            
            logger.info(f"🎯 Starting progressive dialer session for user {user_email} with {len(lead_ids)} leads")
            
            # 1. Validate prerequisites
            validation_result = await self._validate_session_prerequisites(lead_ids, current_user)
            if not validation_result["success"]:
                return validation_result
            
            # 2. Get and validate leads
            leads_data = await self._get_and_validate_leads(lead_ids, user_id)
            if not leads_data["success"]:
                return leads_data
            
            valid_leads = leads_data["valid_leads"]
            
            # 3. Create Tata Progressive Campaign
            campaign_result = await self._create_tata_progressive_campaign(
                leads=valid_leads,
                current_user=current_user,
                session_name=session_name or f"Progressive Session - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
            
            if not campaign_result["success"]:
                return campaign_result
            
            # 4. Start Agent Session
            session_result = await self._start_agent_session(
                campaign_id=campaign_result["campaign_id"],
                current_user=current_user
            )
            
            if not session_result["success"]:
                # Cleanup campaign if session start failed
                await self._cleanup_failed_campaign(campaign_result["campaign_id"])
                return session_result
            
            # 5. Store session in database
            session_doc = await self._create_session_database_record(
                campaign_id=campaign_result["campaign_id"],
                session_id=session_result["session_id"],
                leads=valid_leads,
                current_user=current_user,
                session_name=session_name
            )
            
            # 6. Log session start activity
            await self._log_session_activity(
                session_id=session_result["session_id"],
                event_type="session_started",
                user_id=user_id,
                data={
                    "total_leads": len(valid_leads),
                    "campaign_id": campaign_result["campaign_id"]
                }
            )
            
            logger.info(f"✅ Progressive dialer session started successfully: {session_result['session_id']}")
            
            return {
                "success": True,
                "message": f"Progressive dialer started! You'll receive a call to join the session. {len(valid_leads)} leads will be called automatically.",
                "session_id": session_result["session_id"],
                "campaign_id": campaign_result["campaign_id"],
                "total_leads": len(valid_leads),
                "leads_preview": [
                    {
                        "lead_id": lead["lead_id"],
                        "name": lead.get("name", "Unknown"),
                        "phone": lead["phone"]
                    }
                    for lead in valid_leads[:5]  # Show first 5 leads
                ],
                "session_config": {
                    "call_timeout": self.default_call_timeout,
                    "time_between_calls": self.time_between_calls,
                    "session_timeout": self.session_timeout
                },
                "started_at": datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"Error starting progressive dialer session: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to start progressive dialer: {str(e)}"
            }

    async def get_session_status(
        self,
        session_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get real-time progressive dialer session status
        
        Args:
            session_id: Session ID to check
            user_id: User ID requesting status
            
        Returns:
            Dict with session status and progress
        """
        try:
            logger.info(f"📊 Getting session status for {session_id}")
            
            # 1. Get session from database
            db = self._get_db()
            if not db:
                return {"success": False, "message": "Database not available"}
            
            session = await db.dialer_campaigns.find_one({"session_id": session_id})
            if not session:
                return {"success": False, "message": "Session not found"}
            
            # 2. Check permissions
            if str(session.get("user_id")) != user_id:
                return {"success": False, "message": "Not authorized to access this session"}
            
            # 3. Get live status from Tata API
            tata_status = await self._get_tata_session_status(session_id)
            
            # 4. Calculate progress metrics
            progress_metrics = await self._calculate_session_progress(session, tata_status)
            
            # 5. Get recent session logs
            recent_logs = await self._get_recent_session_logs(session_id, limit=5)
            
            return {
                "success": True,
                "session_id": session_id,
                "status": tata_status.get("status", "unknown"),
                "agent_status": tata_status.get("agent_status", "unknown"),
                "current_call": tata_status.get("current_call", {}),
                "progress": progress_metrics,
                "session_duration": self._calculate_session_duration(session),
                "recent_activity": recent_logs,
                "last_updated": datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"Error getting session status: {str(e)}")
            return {"success": False, "message": f"Failed to get session status: {str(e)}"}

    async def control_session(
        self,
        session_id: str,
        action: str,  # pause, resume, end
        user_id: str,
        session_summary: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Control progressive dialer session (pause, resume, end)
        
        Args:
            session_id: Session ID to control
            action: Control action (pause, resume, end)
            user_id: User ID requesting control
            session_summary: Optional session summary for end action
            
        Returns:
            Dict with control result
        """
        try:
            logger.info(f"🎮 Session control: {action} for session {session_id}")
            
            # 1. Validate session and permissions
            validation_result = await self._validate_session_control(session_id, user_id, action)
            if not validation_result["success"]:
                return validation_result
            
            session = validation_result["session"]
            
            # 2. Execute control action
            if action == "pause":
                result = await self._pause_session(session_id, session)
            elif action == "resume":
                result = await self._resume_session(session_id, session)
            elif action == "end":
                result = await self._end_session(session_id, session, session_summary)
            else:
                return {"success": False, "message": f"Invalid action: {action}"}
            
            # 3. Log control action
            await self._log_session_activity(
                session_id=session_id,
                event_type=f"session_{action}",
                user_id=user_id,
                data={"action": action, "result": result.get("success", False)}
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error controlling session {session_id}: {str(e)}")
            return {"success": False, "message": f"Failed to {action} session: {str(e)}"}

    async def get_user_sessions(
        self,
        user_id: str,
        status_filter: Optional[str] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Get user's progressive dialer sessions
        
        Args:
            user_id: User ID
            status_filter: Optional status filter
            limit: Maximum number of sessions to return
            
        Returns:
            Dict with user sessions
        """
        try:
            logger.info(f"📋 Getting sessions for user {user_id}")
            
            db = self._get_db()
            if not db:
                return {"success": False, "message": "Database not available"}
            
            # Build query
            query = {"user_id": ObjectId(user_id)}
            if status_filter:
                query["status"] = status_filter
            
            # Get sessions with pagination
            sessions_cursor = db.dialer_campaigns.find(query).sort("created_at", -1).limit(limit)
            sessions = await sessions_cursor.to_list(length=limit)
            
            # Enrich sessions with statistics
            enriched_sessions = []
            for session in sessions:
                enriched_session = await self._enrich_session_data(session)
                enriched_sessions.append(enriched_session)
            
            # Count active sessions
            active_count = await db.dialer_campaigns.count_documents({
                "user_id": ObjectId(user_id),
                "status": {"$in": ["active", "paused"]}
            })
            
            return {
                "success": True,
                "sessions": enriched_sessions,
                "total_count": len(enriched_sessions),
                "active_count": active_count
            }
            
        except Exception as e:
            logger.error(f"Error getting user sessions: {str(e)}")
            return {"success": False, "message": f"Failed to get sessions: {str(e)}"}

    # =============================================================================
    # VALIDATION AND PREPROCESSING METHODS
    # =============================================================================

    async def _validate_session_prerequisites(
        self,
        lead_ids: List[str],
        current_user: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate prerequisites for starting a progressive dialer session"""
        try:
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            # Check if user has calling enabled
            if not current_user.get("calling_enabled"):
                return {
                    "success": False,
                    "message": "Calling not enabled for your account. Please contact admin to set up Tata integration."
                }
            
            # Check if user has Tata extension
            tata_extension = current_user.get("tata_extension")
            if not tata_extension:
                return {
                    "success": False,
                    "message": "Tata extension not configured. Please contact admin to complete setup."
                }
            
            # Check lead count limits
            if len(lead_ids) == 0:
                return {"success": False, "message": "At least one lead is required"}
            
            if len(lead_ids) > self.max_leads_per_session:
                return {
                    "success": False,
                    "message": f"Maximum {self.max_leads_per_session} leads allowed per session"
                }
            
            # Check concurrent session limit
            db = self._get_db()
            if db:
                active_sessions = await db.dialer_campaigns.count_documents({
                    "user_id": ObjectId(user_id),
                    "status": {"$in": ["active", "paused"]}
                })
                
                if active_sessions >= self.max_concurrent_sessions_per_user:
                    return {
                        "success": False,
                        "message": f"Maximum {self.max_concurrent_sessions_per_user} concurrent sessions allowed. Please end existing sessions first."
                    }
            
            # Check Tata API availability
            if not TATA_AUTH_AVAILABLE and not self.mock_mode:
                return {
                    "success": False,
                    "message": "Tata integration not available. Contact system administrator."
                }
            
            return {"success": True}
            
        except Exception as e:
            logger.error(f"Error validating session prerequisites: {str(e)}")
            return {"success": False, "message": f"Validation failed: {str(e)}"}

    async def _get_and_validate_leads(
        self,
        lead_ids: List[str],
        user_id: str
    ) -> Dict[str, Any]:
        """Get leads from database and validate them for calling"""
        try:
            db = self._get_db()
            if not db:
                return {"success": False, "message": "Database not available"}
            
            # Get leads from database
            leads_cursor = db.leads.find({"lead_id": {"$in": lead_ids}})
            leads = await leads_cursor.to_list(length=len(lead_ids))
            
            if not leads:
                return {"success": False, "message": "No valid leads found"}
            
            valid_leads = []
            invalid_leads = []
            
            for lead in leads:
                # Check lead permission (non-admin users can only call assigned leads)
                assigned_to = str(lead.get("assigned_to", ""))
                if assigned_to != user_id:
                    # Note: Admin permission check should be done at endpoint level
                    invalid_leads.append({
                        "lead_id": lead.get("lead_id"),
                        "reason": "Not assigned to you"
                    })
                    continue
                
                # Check if lead has phone number
                phone = lead.get("phone", "").strip()
                if not phone:
                    invalid_leads.append({
                        "lead_id": lead.get("lead_id"),
                        "reason": "No phone number"
                    })
                    continue
                
                # Validate phone number format
                if not self._is_valid_phone_number(phone):
                    invalid_leads.append({
                        "lead_id": lead.get("lead_id"),
                        "reason": "Invalid phone number format"
                    })
                    continue
                
                # Lead is valid
                valid_leads.append({
                    "lead_id": lead.get("lead_id"),
                    "name": lead.get("name") or lead.get("full_name", "Unknown"),
                    "phone": phone,
                    "email": lead.get("email"),
                    "company_name": lead.get("company_name"),
                    "status": lead.get("status")
                })
            
            if not valid_leads:
                return {
                    "success": False,
                    "message": "No valid leads found for calling",
                    "invalid_leads": invalid_leads
                }
            
            logger.info(f"✅ Validated {len(valid_leads)} leads for progressive dialer")
            
            return {
                "success": True,
                "valid_leads": valid_leads,
                "invalid_leads": invalid_leads,
                "total_valid": len(valid_leads),
                "total_invalid": len(invalid_leads)
            }
            
        except Exception as e:
            logger.error(f"Error validating leads: {str(e)}")
            return {"success": False, "message": f"Lead validation failed: {str(e)}"}

    def _is_valid_phone_number(self, phone: str) -> bool:
        """Basic phone number validation"""
        if not phone:
            return False
        
        # Remove common phone number characters
        cleaned = re.sub(r'[^\d]', '', phone)
        
        # Check if it's a reasonable length (assuming Indian numbers)
        if len(cleaned) < 10 or len(cleaned) > 13:
            return False
        
        return True

    # =============================================================================
    # TATA API INTEGRATION METHODS
    # =============================================================================

    async def _create_tata_progressive_campaign(
        self,
        leads: List[Dict[str, Any]],
        current_user: Dict[str, Any],
        session_name: str
    ) -> Dict[str, Any]:
        """Create progressive dialer campaign in Tata system"""
        try:
            if self.mock_mode:
                return await self._create_mock_tata_campaign(leads, current_user, session_name)
            
            logger.info(f"Creating Tata progressive campaign with {len(leads)} leads")
            
            # Prepare campaign data
            campaign_data = {
                "campaign_name": session_name,
                "dial_method": "progressive",
                "agent_connection_method": "dial_out_session",  # Agent receives call to join
                "agents": [current_user.get("tata_agent_id")],
                "caller_id": current_user.get("tata_extension"),
                "leads": [
                    {
                        "phone_number": lead["phone"],
                        "lead_id": lead["lead_id"],
                        "name": lead.get("name", "Unknown"),
                        "custom_data": {
                            "crm_lead_id": lead["lead_id"],
                            "lead_email": lead.get("email"),
                            "company_name": lead.get("company_name")
                        }
                    }
                    for lead in leads
                ],
                "campaign_settings": {
                    "call_timeout": self.default_call_timeout,
                    "retry_attempts": 1,
                    "time_between_calls": self.time_between_calls,
                    "session_timeout": self.session_timeout,
                    "auto_start": False  # We'll start session separately
                }
            }
            
            # Make API call to create campaign
            success, response = await self._make_tata_api_request(
                "POST",
                "/v1/dialer/campaigns",
                data=campaign_data
            )
            
            if success and response.get("campaign_id"):
                campaign_id = response["campaign_id"]
                logger.info(f"✅ Tata campaign created successfully: {campaign_id}")
                
                return {
                    "success": True,
                    "campaign_id": campaign_id,
                    "tata_response": response
                }
            else:
                logger.error(f"Tata campaign creation failed: {response}")
                return {
                    "success": False,
                    "message": f"Failed to create Tata campaign: {response.get('message', 'Unknown error')}"
                }
                
        except Exception as e:
            logger.error(f"Error creating Tata campaign: {str(e)}")
            return {"success": False, "message": f"Campaign creation failed: {str(e)}"}

    async def _start_agent_session(
        self,
        campaign_id: str,
        current_user: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Start agent session for progressive dialer campaign"""
        try:
            if self.mock_mode:
                return await self._start_mock_agent_session(campaign_id, current_user)
            
            logger.info(f"Starting agent session for campaign {campaign_id}")
            
            # Prepare session start data
            session_data = {
                "agent_id": current_user.get("tata_agent_id"),
                "session_type": "progressive_dialer",
                "auto_connect_agent": True
            }
            
            # Make API call to start session
            success, response = await self._make_tata_api_request(
                "POST",
                f"/v1/dialer/campaigns/{campaign_id}/start-session",
                data=session_data
            )
            
            if success and response.get("session_id"):
                session_id = response["session_id"]
                logger.info(f"✅ Agent session started successfully: {session_id}")
                
                return {
                    "success": True,
                    "session_id": session_id,
                    "tata_response": response
                }
            else:
                logger.error(f"Agent session start failed: {response}")
                return {
                    "success": False,
                    "message": f"Failed to start agent session: {response.get('message', 'Unknown error')}"
                }
                
        except Exception as e:
            logger.error(f"Error starting agent session: {str(e)}")
            return {"success": False, "message": f"Session start failed: {str(e)}"}

    async def _get_tata_session_status(self, session_id: str) -> Dict[str, Any]:
        """Get session status from Tata API"""
        try:
            if self.mock_mode:
                return self._get_mock_session_status(session_id)
            
            success, response = await self._make_tata_api_request(
                "GET",
                f"/v1/dialer/sessions/{session_id}/status"
            )
            
            if success:
                return response
            else:
                logger.warning(f"Failed to get Tata session status: {response}")
                return {"status": "unknown", "error": response}
                
        except Exception as e:
            logger.error(f"Error getting Tata session status: {str(e)}")
            return {"status": "error", "error": str(e)}

    async def _make_tata_api_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Make authenticated request to Tata API"""
        try:
            if not TATA_AUTH_AVAILABLE:
                return False, {"error": "Tata auth service not available"}
            
            # Get valid token
            token = await self.tata_auth_service.get_valid_token()
            if not token:
                return False, {"error": "No valid Tata token available"}
            
            # Prepare request
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            url = f"{self.tata_base_url}{endpoint}"
            
            async with httpx.AsyncClient(timeout=60) as client:
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method.upper() == "POST":
                    response = await client.post(url, headers=headers, json=data)
                elif method.upper() == "PUT":
                    response = await client.put(url, headers=headers, json=data)
                else:
                    return False, {"error": "Unsupported HTTP method"}
                
                if response.status_code in [200, 201]:
                    return True, response.json()
                else:
                    logger.error(f"Tata API request failed: {response.status_code} - {response.text}")
                    return False, {
                        "error": f"API request failed with status {response.status_code}",
                        "details": response.text
                    }
                    
        except Exception as e:
            logger.error(f"Tata API request error: {str(e)}")
            return False, {"error": str(e)}

    # =============================================================================
    # DATABASE OPERATIONS
    # =============================================================================

    async def _create_session_database_record(
        self,
        campaign_id: str,
        session_id: str,
        leads: List[Dict[str, Any]],
        current_user: Dict[str, Any],
        session_name: Optional[str]
    ) -> Dict[str, Any]:
        """Create session record in database"""
        try:
            db = self._get_db()
            if not db:
                raise Exception("Database not available")
            
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            session_doc = {
                "_id": ObjectId(),
                "campaign_id": campaign_id,
                "session_id": session_id,
                "user_id": ObjectId(user_id),
                "agent_id": current_user.get("tata_agent_id"),
                "agent_extension": current_user.get("tata_extension"),
                "session_name": session_name or f"Progressive Session - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "total_leads": len(leads),
                "leads": [
                    {
                        "lead_id": lead["lead_id"],
                        "phone": lead["phone"],
                        "name": lead.get("name", "Unknown"),
                        "status": "pending"  # pending, called, connected, failed
                    }
                    for lead in leads
                ],
                "status": "active",  # active, paused, completed, failed
                "created_at": datetime.utcnow(),
                "started_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "completed_at": None,
                "session_statistics": {
                    "leads_called": 0,
                    "leads_connected": 0,
                    "leads_failed": 0,
                    "total_call_duration": 0,
                    "average_call_duration": 0
                }
            }
            
            # Insert session document
            await db.dialer_campaigns.insert_one(session_doc)
            
            logger.info(f"✅ Session database record created: {session_id}")
            return session_doc
            
        except Exception as e:
            logger.error(f"Error creating session database record: {str(e)}")
            raise

    async def _log_session_activity(
        self,
        session_id: str,
        event_type: str,
        user_id: str,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log session activity to database"""
        try:
            db = self._get_db()
            if not db:
                return
            
            activity_doc = {
                "_id": ObjectId(),
                "session_id": session_id,
                "event_type": event_type,
                "user_id": user_id,
                "timestamp": datetime.utcnow(),
                "data": data or {}
            }
            
            await db.dialer_session_logs.insert_one(activity_doc)
            logger.debug(f"Logged session activity: {event_type} for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error logging session activity: {str(e)}")

    # =============================================================================
    # SESSION CONTROL METHODS
    # =============================================================================

    async def _validate_session_control(
        self,
        session_id: str,
        user_id: str,
        action: str
    ) -> Dict[str, Any]:
        """Validate session control request"""
        try:
            db = self._get_db()
            if not db:
                return {"success": False, "message": "Database not available"}
            
            # Get session
            session = await db.dialer_campaigns.find_one({"session_id": session_id})
            if not session:
                return {"success": False, "message": "Session not found"}
            
            # Check permissions
            if str(session.get("user_id")) != user_id:
                return {"success": False, "message": "Not authorized to control this session"}
            
            # Check if action is valid for current status
            current_status = session.get("status")
            if action == "pause" and current_status != "active":
                return {"success": False, "message": "Can only pause active sessions"}
            elif action == "resume" and current_status != "paused":
                return {"success": False, "message": "Can only resume paused sessions"}
            elif action == "end" and current_status in ["completed", "failed"]:
                return {"success": False, "message": "Session is already ended"}
            
            return {"success": True, "session": session}
            
        except Exception as e:
            logger.error(f"Error validating session control: {str(e)}")
            return {"success": False, "message": f"Validation failed: {str(e)}"}

    async def _pause_session(self, session_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
        """Pause progressive dialer session"""
        try:
            # Pause in Tata system
            if not self.mock_mode:
                success, response = await self._make_tata_api_request(
                    "POST",
                    f"/v1/dialer/sessions/{session_id}/pause"
                )
                
                if not success:
                    return {"success": False, "message": f"Failed to pause Tata session: {response}"}
            
            # Update database
            db = self._get_db()
            if db:
                await db.dialer_campaigns.update_one(
                    {"session_id": session_id},
                    {
                        "$set": {
                            "status": "paused",
                            "updated_at": datetime.utcnow(),
                            "paused_at": datetime.utcnow()
                        }
                    }
                )
            
            logger.info(f"✅ Session paused successfully: {session_id}")
            return {"success": True, "message": "Session paused successfully"}
            
        except Exception as e:
            logger.error(f"Error pausing session: {str(e)}")
            return {"success": False, "message": f"Failed to pause session: {str(e)}"}

    async def _resume_session(self, session_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
        """Resume progressive dialer session"""
        try:
            # Resume in Tata system
            if not self.mock_mode:
                success, response = await self._make_tata_api_request(
                    "POST",
                    f"/v1/dialer/sessions/{session_id}/resume"
                )
                
                if not success:
                    return {"success": False, "message": f"Failed to resume Tata session: {response}"}
            
            # Update database
            db = self._get_db()
            if db:
                await db.dialer_campaigns.update_one(
                    {"session_id": session_id},
                    {
                        "$set": {
                            "status": "active",
                            "updated_at": datetime.utcnow()
                        },
                        "$unset": {"paused_at": ""}
                    }
                )
            
            logger.info(f"✅ Session resumed successfully: {session_id}")
            return {"success": True, "message": "Session resumed successfully"}
            
        except Exception as e:
            logger.error(f"Error resuming session: {str(e)}")
            return {"success": False, "message": f"Failed to resume session: {str(e)}"}

    async def _end_session(
        self,
        session_id: str,
        session: Dict[str, Any],
        session_summary: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """End progressive dialer session"""
        try:
            # End in Tata system
            if not self.mock_mode:
                success, response = await self._make_tata_api_request(
                    "POST",
                    f"/v1/dialer/sessions/{session_id}/end"
                )
                
                if not success:
                    logger.warning(f"Failed to end Tata session (continuing anyway): {response}")
            
            # Calculate final statistics
            final_stats = await self._calculate_final_session_statistics(session_id)
            
            # Update database
            db = self._get_db()
            if db:
                await db.dialer_campaigns.update_one(
                    {"session_id": session_id},
                    {
                        "$set": {
                            "status": "completed",
                            "updated_at": datetime.utcnow(),
                            "completed_at": datetime.utcnow(),
                            "session_statistics": final_stats,
                            "session_summary": session_summary or {}
                        }
                    }
                )
            
            logger.info(f"✅ Session ended successfully: {session_id}")
            return {
                "success": True,
                "message": "Session ended successfully",
                "final_summary": final_stats,
                "session_statistics": final_stats
            }
            
        except Exception as e:
            logger.error(f"Error ending session: {str(e)}")
            return {"success": False, "message": f"Failed to end session: {str(e)}"}

    # =============================================================================
    # HELPER METHODS
    # =============================================================================

    async def _calculate_session_progress(
        self,
        session: Dict[str, Any],
        tata_status: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate session progress metrics"""
        try:
            total_leads = session.get("total_leads", 0)
            leads_called = tata_status.get("leads_processed", 0)
            leads_connected = tata_status.get("successful_connections", 0)
            leads_remaining = total_leads - leads_called
            
            return {
                "total_leads": total_leads,
                "leads_called": leads_called,
                "leads_connected": leads_connected,
                "leads_remaining": max(0, leads_remaining),
                "success_rate": round((leads_connected / max(leads_called, 1)) * 100, 2) if leads_called > 0 else 0,
                "completion_percentage": round((leads_called / max(total_leads, 1)) * 100, 2) if total_leads > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error calculating session progress: {str(e)}")
            return {"error": str(e)}

    def _calculate_session_duration(self, session: Dict[str, Any]) -> int:
        """Calculate session duration in seconds"""
        try:
            started_at = session.get("started_at")
            if not started_at:
                return 0
            
            if session.get("status") == "completed":
                completed_at = session.get("completed_at")
                if completed_at:
                    return int((completed_at - started_at).total_seconds())
            
            # Session is still active
            return int((datetime.utcnow() - started_at).total_seconds())
            
        except Exception as e:
            logger.error(f"Error calculating session duration: {str(e)}")
            return 0

    async def _get_recent_session_logs(self, session_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent session activity logs"""
        try:
            db = self._get_db()
            if not db:
                return []
            
            logs_cursor = db.dialer_session_logs.find(
                {"session_id": session_id}
            ).sort("timestamp", -1).limit(limit)
            
            logs = await logs_cursor.to_list(length=limit)
            
            return [
                {
                    "event_type": log.get("event_type"),
                    "timestamp": log.get("timestamp"),
                    "data": log.get("data", {})
                }
                for log in logs
            ]
            
        except Exception as e:
            logger.error(f"Error getting recent session logs: {str(e)}")
            return []

    async def _enrich_session_data(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich session data with additional information"""
        try:
            # Convert ObjectIds to strings
            enriched = {
                "session_id": session.get("session_id"),
                "campaign_id": session.get("campaign_id"),
                "session_name": session.get("session_name"),
                "status": session.get("status"),
                "total_leads": session.get("total_leads", 0),
                "created_at": session.get("created_at"),
                "started_at": session.get("started_at"),
                "completed_at": session.get("completed_at"),
                "session_duration": self._calculate_session_duration(session),
                "session_statistics": session.get("session_statistics", {}),
                "leads_preview": session.get("leads", [])[:3]  # First 3 leads
            }
            
            return enriched
            
        except Exception as e:
            logger.error(f"Error enriching session data: {str(e)}")
            return session

    async def _calculate_final_session_statistics(self, session_id: str) -> Dict[str, Any]:
        """Calculate final session statistics"""
        try:
            # This would typically fetch final statistics from Tata API
            # For now, return basic statistics
            return {
                "leads_called": 0,
                "leads_connected": 0,
                "leads_failed": 0,  
                "total_call_duration": 0,
                "average_call_duration": 0,
                "success_rate": 0.0,
                "calculated_at": datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"Error calculating final statistics: {str(e)}")
            return {}

    async def _cleanup_failed_campaign(self, campaign_id: str) -> None:
        """Cleanup failed campaign"""
        try:
            logger.info(f"Cleaning up failed campaign: {campaign_id}")
            
            # Try to delete campaign from Tata system
            if not self.mock_mode:
                await self._make_tata_api_request(
                    "DELETE",
                    f"/v1/dialer/campaigns/{campaign_id}"
                )
            
            # Mark as failed in database
            db = self._get_db()
            if db:
                await db.dialer_campaigns.update_one(
                    {"campaign_id": campaign_id},
                    {
                        "$set": {
                            "status": "failed",
                            "updated_at": datetime.utcnow(),
                            "error_message": "Campaign creation failed"
                        }
                    }
                )
                
        except Exception as e:
            logger.error(f"Error cleaning up failed campaign: {str(e)}")

    # =============================================================================
    # MOCK METHODS FOR TESTING
    # =============================================================================

    async def _create_mock_tata_campaign(
        self,
        leads: List[Dict[str, Any]],
        current_user: Dict[str, Any],
        session_name: str
    ) -> Dict[str, Any]:
        """Create mock Tata campaign for testing"""
        mock_campaign_id = f"MOCK_CAMPAIGN_{random.randint(100000, 999999)}"
        logger.info(f"🧪 Created mock Tata campaign: {mock_campaign_id}")
        
        await asyncio.sleep(0.5)  # Simulate API delay
        
        return {
            "success": True,
            "campaign_id": mock_campaign_id,
            "tata_response": {
                "campaign_id": mock_campaign_id,
                "status": "created",
                "leads_count": len(leads),
                "mock_mode": True
            }
        }

    async def _start_mock_agent_session(
        self,
        campaign_id: str,
        current_user: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Start mock agent session for testing"""
        mock_session_id = f"MOCK_SESSION_{random.randint(100000, 999999)}"
        logger.info(f"🧪 Started mock agent session: {mock_session_id}")
        
        await asyncio.sleep(0.3)  # Simulate API delay
        
        return {
            "success": True,
            "session_id": mock_session_id,
            "tata_response": {
                "session_id": mock_session_id,
                "status": "active",
                "campaign_id": campaign_id,
                "mock_mode": True
            }
        }

    def _get_mock_session_status(self, session_id: str) -> Dict[str, Any]:
        """Get mock session status for testing"""
        return {
            "status": "active",
            "agent_status": "connected",
            "current_call": {
                "lead_id": "LD-1001",
                "lead_phone": "+919876543210",
                "call_duration": 45,
                "call_status": "connected"
            },
            "leads_processed": 2,
            "successful_connections": 1,
            "mock_mode": True
        }

# Create singleton instance
progressive_dialer_service = ProgressiveDialerService()