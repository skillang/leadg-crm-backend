# app/services/tata_admin_service.py
# Admin Service for fetching call data directly from TATA API
# FIXED: Now uses dynamic token generation and agent mapping from database

import aiohttp
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
from bson import ObjectId
import calendar

from ..config.database import get_database
from ..services.tata_auth_service import tata_auth_service  # ✅ Use existing auth service
from ..models.admin_dashboard import (
    CallRecord, UserCallStats, DashboardFilters, 
    CallStatusFilter, CallDirectionFilter, AdminActivityLog
)

logger = logging.getLogger(__name__)

class TataAdminService:
    """
    Admin Service for Call Analytics Dashboard
    - Fetches call data directly from TATA API using dynamic tokens
    - Uses existing tata_auth_service for authentication
    - Maps TATA agents to LeadG CRM users from database
    - No local database storage of call data
    """
    
    def __init__(self):
        self.base_url = "https://api-smartflo.tatateleservices.com/v1"
        # ✅ REMOVED: Hardcoded auth token - now using tata_auth_service
        
        # ✅ REMOVED: Hardcoded agent mapping - now loaded from database
        self.agent_user_mapping = {}
        
        self.db = None
    
    def _get_db(self):
        """🔧 FIXED: Lazy database initialization with proper None checking"""
        if self.db is None:  # ✅ Use 'is None' instead of 'if not'
            try:
                self.db = get_database()
            except RuntimeError:
                return None
        return self.db
    
    async def _get_valid_auth_token(self) -> Optional[str]:
        """
        🔧 FIXED: Get valid authentication token from tata_auth_service
        Based on your working example - TATA API expects raw token without "Bearer"
        """
        try:
            # First try to get token from auth service
            token = await tata_auth_service.get_valid_token()
            
            # Check if token looks encrypted (starts with gAAAAAB)
            if token and token.startswith('gAAAAAB'):
                logger.warning("Token appears encrypted - attempting fresh login")
                token = None
            
            if not token:
                logger.warning("No valid TATA token available - attempting fresh login")
                # Try to get a fresh token
                login_result = await tata_auth_service.login()
                if login_result.get("success"):
                    token = login_result.get("access_token")
                    logger.info("✅ Got fresh TATA token")
                else:
                    logger.error(f"Failed to get fresh token: {login_result.get('message')}")
                    return None
            
            # ✅ FIXED: TATA API expects raw token without "Bearer" prefix
            # Remove "Bearer " if it exists
            if token and token.startswith('Bearer '):
                token = token[7:]  # Remove "Bearer " prefix
            
            # Validate token format (JWT should start with eyJ)
            if token and not token.startswith('eyJ'):
                logger.error(f"Invalid token format: {token[:20]}...")
                # Try fresh login one more time
                login_result = await tata_auth_service.login()
                if login_result.get("success"):
                    token = login_result.get("access_token")
                    if token and token.startswith('Bearer '):
                        token = token[7:]
                else:
                    return None
            
            logger.debug(f"Using TATA token: {token[:20]}...")
            return token
            
        except Exception as e:
            logger.error(f"Error getting TATA auth token: {e}")
            return None
    
    async def initialize_agent_mapping(self):
        """
        🔧 IMPROVED: Initialize agent-to-user mapping from database
        This runs once to populate the mapping from tata_user_mappings collection
        """
        try:
            db = self._get_db()
            if db is None:  # ✅ Use 'is None' instead of 'if not'
                logger.warning("Database not available for agent mapping")
                return
            
            # Get all TATA user mappings
            mappings = await db.tata_user_mappings.find({}).to_list(None)
            
            # Clear existing mapping
            self.agent_user_mapping = {}
            
            for mapping in mappings:
                agent_phone = mapping.get("tata_phone")
                user_id = mapping.get("crm_user_id")
                
                if agent_phone and user_id:
                    # Get user details
                    user = await db.users.find_one({"_id": ObjectId(user_id)})
                    if user:
                        # Try multiple name fields
                        user_name = (
                            user.get('full_name') or 
                            f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or
                            user.get('username') or 
                            user.get('email', '').split('@')[0] or
                            'Unknown'
                        )
                        
                        self.agent_user_mapping[agent_phone] = {
                            "user_id": str(user_id),
                            "user_name": user_name,
                            "user_email": user.get('email', ''),
                            "tata_agent_id": mapping.get("tata_agent_id"),
                            "tata_extension": mapping.get("tata_extension") or mapping.get("tata_caller_id")
                        }
            
            logger.info(f"✅ Initialized agent mapping for {len(self.agent_user_mapping)} agents")
            
        except Exception as e:
            logger.error(f"Error initializing agent mapping: {e}")
    
    async def fetch_call_records(
        self, 
        from_date: str, 
        to_date: str,
        page: int = 1,
        limit: int = 100,
        filters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        🔧 IMPROVED: Fetch call records directly from TATA API using dynamic auth
        
        Args:
            from_date: Start date (Y-m-d H:i:s format)
            to_date: End date (Y-m-d H:i:s format)
            page: Page number
            limit: Records per page
            filters: Optional filters (agents, call_type, direction, etc.)
        
        Returns:
            Dict containing call records and metadata
        """
        try:
            # Get valid authentication token
            auth_token = await self._get_valid_auth_token()
            if not auth_token:
                logger.error("No valid TATA authentication token available")
                return {"results": [], "count": 0, "error": "Authentication failed"}
            
            headers = {
                "accept": "application/json",
                "Authorization": auth_token  # ✅ Raw token without "Bearer" prefix
            }
            
            params = {
                "from_date": from_date,
                "to_date": to_date,
                "page": page,
                "limit": limit
            }
            
            # Add optional filters based on TATA API documentation
            if filters:
                # Map our filters to TATA API format
                if filters.get("agents"):
                    params["agents"] = filters["agents"]
                
                if filters.get("call_type"):
                    # Convert our format to TATA format: answered="c", missed="m"
                    if filters["call_type"] == "answered":
                        params["call_type"] = "c"
                    elif filters["call_type"] == "missed":
                        params["call_type"] = "m"
                
                if filters.get("direction"):
                    params["direction"] = filters["direction"]
                
                if filters.get("duration"):
                    params["duration"] = filters["duration"]
                
                if filters.get("operator"):
                    params["operator"] = filters["operator"]
            
            logger.info(f"Fetching TATA call records: {from_date} to {to_date}, page {page}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/call/records",
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Fetched {len(data.get('results', []))} call records from TATA API")
                        return data
                    elif response.status == 401:
                        logger.warning("TATA API authentication failed - token may be expired")
                        # Try to refresh token
                        await tata_auth_service.refresh_token()
                        return {"results": [], "count": 0, "error": "Authentication failed - please retry"}
                    else:
                        error_text = await response.text()
                        logger.error(f"TATA API error: {response.status} - {error_text}")
                        return {"results": [], "count": 0, "error": f"API Error: {response.status}"}
                        
        except asyncio.TimeoutError:
            logger.error("TATA API request timeout")
            return {"results": [], "count": 0, "error": "Request timeout"}
        except Exception as e:
            logger.error(f"Error fetching TATA call records: {e}")
            return {"results": [], "count": 0, "error": str(e)}
    
    async def fetch_all_call_records(
        self, 
        from_date: str, 
        to_date: str,
        filters: Optional[Dict] = None,
        max_records: int = 10000
    ) -> List[Dict]:
        """
        Fetch ALL call records for the date range (handles pagination)
        """
        all_records = []
        page = 1
        limit = 100
        
        while len(all_records) < max_records:
            batch = await self.fetch_call_records(
                from_date=from_date,
                to_date=to_date,
                page=page,
                limit=limit,
                filters=filters
            )
            
            records = batch.get("results", [])
            if not records:
                break
                
            all_records.extend(records)
            
            # Check if there are more pages
            total_count = batch.get("count", 0)
            if len(all_records) >= total_count:
                break
                
            page += 1
            
            # Safety limit to prevent infinite loops
            if page > 100:  # Max 10,000 records (100 pages * 100 per page)
                logger.warning("Reached pagination safety limit (100 pages)")
                break
            
            # Small delay to be API-friendly
            await asyncio.sleep(0.1)
        
        logger.info(f"Fetched total {len(all_records)} call records")
        return all_records
    
    def map_agent_to_user(self, agent_number: str) -> Dict[str, str]:
        """
        🔧 IMPROVED: Map TATA agent number to LeadG CRM user using database data
        
        Args:
            agent_number: Agent phone number from TATA
            
        Returns:
            Dict with user_id, user_name, and additional info
        """
        if not agent_number:
            return {
                "user_id": "unknown",
                "user_name": "Unknown Agent",
                "user_email": "",
                "tata_agent_id": None,
                "tata_extension": None
            }
        
        # Clean agent number for mapping
        clean_number = agent_number
        if clean_number.startswith('+'):
            clean_number = clean_number[1:]
        
        # Try multiple formats for mapping
        for search_format in [agent_number, f"+{clean_number}", clean_number]:
            mapping = self.agent_user_mapping.get(search_format)
            if mapping:
                return mapping
        
        # Return unknown user with cleaned number
        return {
            "user_id": f"unknown_{clean_number}",
            "user_name": f"Unknown ({agent_number})",
            "user_email": "",
            "tata_agent_id": None,
            "tata_extension": None
        }
    
   


    async def get_day_to_day_comparison(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get day-to-day call comparison for a specific user
        """
        try:
            # Format dates for TATA API
            from_date = start_date.strftime("%Y-%m-%d 00:00:00")
            to_date = end_date.strftime("%Y-%m-%d 23:59:59")
            
            # Get user's agent number for filtering
            user_agent = None
            for agent, mapping in self.agent_user_mapping.items():
                if mapping.get("user_id") == user_id:
                    user_agent = agent
                    break
            
            # Fetch call records with user filter if possible
            filters = {"agents": [f"agent|{user_agent}"]} if user_agent else None
            call_records = await self.fetch_all_call_records(from_date, to_date, filters)
            
            # Group by date
            daily_stats = defaultdict(lambda: {
                "total_calls": 0,
                "answered_calls": 0,
                "missed_calls": 0,
                "total_duration": 0,
                "recordings_count": 0
            })
            
            for record in call_records:
                # Filter by user if we couldn't filter at API level
                if user_agent:
                    if record.get("agent_number") != user_agent:
                        continue
                else:
                    # Fallback: check if this record belongs to our user
                    agent_number = record.get("agent_number", "")
                    user_mapping = self.map_agent_to_user(agent_number)
                    if user_mapping.get("user_id") != user_id:
                        continue
                
                record_date = record.get("date", "")
                if not record_date:
                    continue
                
                stats = daily_stats[record_date]
                stats["total_calls"] += 1
                
                if record.get("status") == "answered":
                    stats["answered_calls"] += 1
                    stats["total_duration"] += record.get("call_duration", 0)
                else:
                    stats["missed_calls"] += 1
                
                if record.get("recording_url"):
                    stats["recordings_count"] += 1
            
            # Convert to list with day-to-day comparison
            result = []
            sorted_dates = sorted(daily_stats.keys())
            
            for i, date in enumerate(sorted_dates):
                stats = daily_stats[date]
                
                # Calculate success rate
                success_rate = (
                    (stats["answered_calls"] / stats["total_calls"]) * 100
                    if stats["total_calls"] > 0 else 0.0
                )
                
                # Calculate change from previous day
                calls_change = 0
                calls_change_percent = 0.0
                trend = "stable"
                
                if i > 0:
                    prev_date = sorted_dates[i - 1]
                    prev_stats = daily_stats[prev_date]
                    
                    calls_change = stats["total_calls"] - prev_stats["total_calls"]
                    
                    if prev_stats["total_calls"] > 0:
                        calls_change_percent = (calls_change / prev_stats["total_calls"]) * 100
                    
                    if calls_change > 0:
                        trend = "up"
                    elif calls_change < 0:
                        trend = "down"
                
                result.append({
                    "date": date,
                    "total_calls": stats["total_calls"],
                    "answered_calls": stats["answered_calls"],
                    "missed_calls": stats["missed_calls"],
                    "total_duration": stats["total_duration"],
                    "success_rate": round(success_rate, 2),
                    "recordings_count": stats["recordings_count"],
                    "calls_change": calls_change,
                    "calls_change_percent": round(calls_change_percent, 2),
                    "trend": trend
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating day-to-day comparison: {e}")
            return []
    
    async def log_admin_activity(
        self,
        admin_user_id: str,
        admin_email: str,
        action: str,
        target_user_id: Optional[str] = None,
        target_user_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """
        Log admin activity for compliance and auditing
        """
        try:
            db = self._get_db()
            if db is None:  # ✅ Use 'is None' instead of 'if not'
                logger.warning("Database not available for admin logging")
                return
            
            log_entry = AdminActivityLog(
                admin_user_id=admin_user_id,
                admin_email=admin_email,
                action=action,
                target_user_id=target_user_id,
                target_user_name=target_user_name,
                details=details or {},
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            # Insert into admin_activity_logs collection
            await db.admin_activity_logs.insert_one(log_entry.dict())
            
            logger.info(f"Logged admin activity: {action} by {admin_email}")
            
        except Exception as e:
            logger.error(f"Error logging admin activity: {e}")
    
    async def get_recording_url(self, call_id: str) -> Optional[str]:
        """
        Get recording URL for a specific call
        """
        try:
            # For now, we'll need to fetch the call record to get the recording URL
            # In a production system, you might want to store this mapping or
            # use a more direct TATA API endpoint if available
            
            # This is a simplified approach - you might need to adjust based on
            # TATA API capabilities for direct recording access
            logger.info(f"Getting recording URL for call {call_id}")
            
            # The recording URL should be available in the call record from TATA API
            # We'll implement this based on TATA API documentation
            
            return None  # Placeholder - implement based on TATA API
            
        except Exception as e:
            logger.error(f"Error getting recording URL: {e}")
            return None

    async def ensure_authentication(self) -> bool:
        """
        🆕 NEW: Ensure we have valid authentication before making API calls
        """
        try:
            token = await self._get_valid_auth_token()
            if not token:
                logger.warning("No valid TATA token - attempting to refresh")
                # Try to refresh token
                refresh_result = await tata_auth_service.refresh_token()
                if refresh_result.get("success"):
                    return True
                else:
                    logger.error("Failed to refresh TATA token")
                    return False
            return True
        except Exception as e:
            logger.error(f"Error ensuring authentication: {e}")
            return False

    async def health_check(self) -> Dict[str, Any]:
        """
        🆕 NEW: Health check for TATA integration
        """
        try:
            # Check authentication
            auth_status = await self.ensure_authentication()
            
            # Check agent mapping
            mapping_count = len(self.agent_user_mapping)
            
            # Check database connectivity
            db = self._get_db()
            db_status = db is not None
            
            return {
                "success": True,
                "auth_status": auth_status,
                "agent_mappings": mapping_count,
                "database_status": db_status,
                "service_status": "operational" if auth_status and db_status else "degraded",
                "checked_at": datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "service_status": "error",
                "checked_at": datetime.utcnow()
            }


# Create singleton instance
tata_admin_service = TataAdminService()# app/services/tata_admin_service.py
# UPDATED Admin Service with optimized TATA API filtering
# Added fetch_call_records_with_filters() method for direct TATA parameter support

import aiohttp
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
from bson import ObjectId
import calendar

from ..config.database import get_database
from ..services.tata_auth_service import tata_auth_service
from ..models.admin_dashboard import (
    CallRecord, UserCallStats, DashboardFilters, 
    CallStatusFilter, CallDirectionFilter, AdminActivityLog
)

logger = logging.getLogger(__name__)

class TataAdminService:
    """
    UPDATED Admin Service for Call Analytics Dashboard
    - Added fetch_call_records_with_filters() for direct TATA API parameter support
    - Supports all TATA API filters: agents, call_type, direction, department, etc.
    - Uses existing tata_auth_service for authentication
    - Maps TATA agents to LeadG CRM users from database
    """
    
    def __init__(self):
        self.base_url = "https://api-smartflo.tatateleservices.com/v1"
        self.agent_user_mapping = {}
        self.db = None
    
    def _get_db(self):
        """Lazy database initialization with proper None checking"""
        if self.db is None:
            try:
                self.db = get_database()
            except RuntimeError:
                return None
        return self.db
    
    async def _get_valid_auth_token(self) -> Optional[str]:
        """
        Get valid authentication token from tata_auth_service
        TATA API expects raw token without "Bearer" prefix
        """
        try:
            token = await tata_auth_service.get_valid_token()
            
            if token and token.startswith('gAAAAAB'):
                logger.warning("Token appears encrypted - attempting fresh login")
                token = None
            
            if not token:
                logger.warning("No valid TATA token available - attempting fresh login")
                login_result = await tata_auth_service.login()
                if login_result.get("success"):
                    token = login_result.get("access_token")
                    logger.info("Got fresh TATA token")
                else:
                    logger.error(f"Failed to get fresh token: {login_result.get('message')}")
                    return None
            
            # Remove "Bearer " prefix if it exists
            if token and token.startswith('Bearer '):
                token = token[7:]
            
            # Validate token format (JWT should start with eyJ)
            if token and not token.startswith('eyJ'):
                logger.error(f"Invalid token format: {token[:20]}...")
                login_result = await tata_auth_service.login()
                if login_result.get("success"):
                    token = login_result.get("access_token")
                    if token and token.startswith('Bearer '):
                        token = token[7:]
                else:
                    return None
            
            logger.debug(f"Using TATA token: {token[:20]}...")
            return token
            
        except Exception as e:
            logger.error(f"Error getting TATA auth token: {e}")
            return None
    
    async def initialize_agent_mapping(self):
        """
        Initialize agent-to-user mapping from database
        """
        try:
            db = self._get_db()
            if db is None:
                logger.warning("Database not available for agent mapping")
                return
            
            mappings = await db.tata_user_mappings.find({}).to_list(None)
            self.agent_user_mapping = {}
            
            for mapping in mappings:
                agent_phone = mapping.get("tata_phone")
                user_id = mapping.get("crm_user_id")
                
                if agent_phone and user_id:
                    user = await db.users.find_one({"_id": ObjectId(user_id)})
                    if user:
                        user_name = (
                            user.get('full_name') or 
                            f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or
                            user.get('username') or 
                            user.get('email', '').split('@')[0] or
                            'Unknown'
                        )
                        
                        self.agent_user_mapping[agent_phone] = {
                            "user_id": str(user_id),
                            "user_name": user_name,
                            "user_email": user.get('email', ''),
                            "tata_agent_id": mapping.get("tata_agent_id"),
                            "tata_extension": mapping.get("tata_extension") or mapping.get("tata_caller_id")
                        }
            
            logger.info(f"Initialized agent mapping for {len(self.agent_user_mapping)} agents")
            
        except Exception as e:
            logger.error(f"Error initializing agent mapping: {e}")
    
    async def fetch_call_records_with_filters(
        self, 
        params: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        NEW: Fetch call records using TATA API with direct parameter support
        FIXED: Handles agent parameter formatting for TATA API compatibility
        
        Args:
            params: Dictionary of TATA API parameters
                - from_date, to_date (required)
                - page, limit (pagination)
                - agents, call_type, direction, etc. (filters)
        
        Returns:
            Dict containing success status, data from TATA API, and error info
        """
        try:
            # Get valid authentication token
            auth_token = await self._get_valid_auth_token()
            if not auth_token:
                logger.error("No valid TATA authentication token available")
                return {
                    "success": False,
                    "error": "Authentication failed - no valid token",
                    "data": {"results": [], "count": 0}
                }
            
            headers = {
                "accept": "application/json",
                "Authorization": auth_token  # Raw token without "Bearer" prefix
            }
            
            # FIXED: Handle agent parameter formatting before API call
            if 'agents' in params and params['agents']:
                original_agent = params['agents']
                
                # Remove + prefix if present - TATA API doesn't expect it
                if original_agent.startswith('+'):
                    params['agents'] = original_agent[1:]  # +916380480960 -> 916380480960
                    logger.info(f"🔧 Fixed agent parameter: {original_agent} -> {params['agents']}")
                
                # Handle multiple agents (comma-separated)
                elif ',' in original_agent:
                    # Clean each agent number in comma-separated list
                    agent_list = [agent.strip() for agent in original_agent.split(',')]
                    cleaned_agents = []
                    for agent in agent_list:
                        if agent.startswith('+'):
                            cleaned_agents.append(agent[1:])
                        else:
                            cleaned_agents.append(agent)
                    params['agents'] = ','.join(cleaned_agents)
                    logger.info(f"🔧 Fixed multiple agents: {original_agent} -> {params['agents']}")
            
            logger.info(f"TATA API call with parameters: {params}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/call/records",
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=60)  # Increased timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        results_count = len(data.get('results', []))
                        total_count = data.get('count', 0)
                        
                        logger.info(f"TATA API success: {results_count} records returned, {total_count} total available")
                        
                        return {
                            "success": True,
                            "data": data,
                            "filters_applied": params,
                            "records_returned": results_count,
                            "total_available": total_count
                        }
                        
                    elif response.status == 401:
                        logger.warning("TATA API authentication failed - token expired")
                        # Try to refresh token
                        refresh_result = await tata_auth_service.refresh_token()
                        if refresh_result.get("success"):
                            logger.info("Token refreshed, retry the request")
                        
                        return {
                            "success": False,
                            "error": "Authentication failed - token expired",
                            "data": {"results": [], "count": 0},
                            "retry_suggested": True
                        }
                        
                    elif response.status == 400:
                        error_text = await response.text()
                        logger.error(f"TATA API bad request: {error_text}")
                        return {
                            "success": False,
                            "error": f"Bad request - invalid parameters: {error_text}",
                            "data": {"results": [], "count": 0},
                            "invalid_params": params
                        }
                        
                    else:
                        error_text = await response.text()
                        logger.error(f"TATA API error: {response.status} - {error_text}")
                        return {
                            "success": False,
                            "error": f"API Error {response.status}: {error_text}",
                            "data": {"results": [], "count": 0}
                        }
                        
        except asyncio.TimeoutError:
            logger.error("TATA API request timeout")
            return {
                "success": False,
                "error": "Request timeout - TATA API took too long to respond",
                "data": {"results": [], "count": 0}
            }
        except Exception as e:
            logger.error(f"Error in TATA API call: {e}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "data": {"results": [], "count": 0}
        }

    async def fetch_call_records(
        self, 
        from_date: str, 
        to_date: str,
        page: int = 1,
        limit: int = 100,
        filters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        LEGACY: Fetch call records with legacy filter format (for backward compatibility)
        """
        # Build TATA API parameters
        params = {
            "from_date": from_date,
            "to_date": to_date,
            "page": str(page),
            "limit": str(limit)
        }
        
        # Convert legacy filters to TATA format
        if filters:
            if filters.get("agents"):
                if isinstance(filters["agents"], list):
                    params["agents"] = ",".join(filters["agents"])
                else:
                    params["agents"] = filters["agents"]
            
            if filters.get("call_type"):
                if filters["call_type"] == "answered":
                    params["call_type"] = "c"
                elif filters["call_type"] == "missed":
                    params["call_type"] = "m"
            
            if filters.get("direction"):
                params["direction"] = filters["direction"]
            
            if filters.get("duration"):
                params["duration"] = filters["duration"]
            
            if filters.get("operator"):
                params["operator"] = filters["operator"]
        
        # Use the new optimized method
        result = await self.fetch_call_records_with_filters(params)
        
        # Return in legacy format for backward compatibility
        if result.get("success"):
            return result.get("data", {"results": [], "count": 0})
        else:
            return {"results": [], "count": 0, "error": result.get("error")}
    
    async def fetch_all_call_records(
        self, 
        from_date: str, 
        to_date: str,
        filters: Optional[Dict] = None,
        max_records: int = 10000
    ) -> List[Dict]:
        """
        Fetch ALL call records for the date range (handles pagination)
        Uses the optimized filtering method
        """
        all_records = []
        page = 1
        limit = 200  # Increased page size for efficiency
        
        while len(all_records) < max_records:
            # Build parameters
            params = {
                "from_date": from_date,
                "to_date": to_date,
                "page": str(page),
                "limit": str(limit)
            }
            
            # Add filters if provided
            if filters:
                if filters.get("agents"):
                    if isinstance(filters["agents"], list):
                        params["agents"] = ",".join(filters["agents"])
                    else:
                        params["agents"] = filters["agents"]
                
                if filters.get("call_type"):
                    if filters["call_type"] == "answered":
                        params["call_type"] = "c"
                    elif filters["call_type"] == "missed":
                        params["call_type"] = "m"
                
                if filters.get("direction"):
                    params["direction"] = filters["direction"]
                
                # Add other TATA filters
                for filter_key in ["department", "duration", "operator", "callerid", 
                                 "destination", "services", "did_number", "broadcast", "ivr"]:
                    if filters.get(filter_key):
                        params[filter_key] = filters[filter_key]
            
            # Fetch batch using optimized method
            batch_result = await self.fetch_call_records_with_filters(params)
            
            if not batch_result.get("success"):
                logger.error(f"Failed to fetch batch on page {page}: {batch_result.get('error')}")
                break
            
            batch_data = batch_result.get("data", {})
            records = batch_data.get("results", [])
            
            if not records:
                logger.info("No more records available")
                break
                
            all_records.extend(records)
            
            # Check if we've got all available records
            total_count = batch_data.get("count", 0)
            if len(all_records) >= total_count:
                logger.info(f"Retrieved all {total_count} available records")
                break
                
            page += 1
            
            # Safety limit
            if page > 50:  # Max 10,000 records (50 pages * 200 per page)
                logger.warning("Reached pagination safety limit (50 pages)")
                break
            
            # API-friendly delay
            await asyncio.sleep(0.1)
        
        logger.info(f"Fetched total {len(all_records)} call records using optimized method")
        return all_records
    
  
    async def fetch_all_user_call_records(
        self, 
        user_agent_number: str,
        from_date: str, 
        to_date: str
    ) -> List[Dict]:
        """
        Fetch ALL call records for a specific user within date range
        """
        all_records = []
        page = 1
        limit = 200
        
        while True:
            params = {
                "from_date": from_date,
                "to_date": to_date,
                "agents": user_agent_number,
                "page": str(page),
                "limit": str(limit)
            }
            
            batch_result = await self.fetch_call_records_with_filters(params)
            
            if not batch_result.get("success"):
                break
                
            batch_data = batch_result.get("data", {})
            records = batch_data.get("results", [])
            
            if not records:
                break
                
            all_records.extend(records)
            
            total_count = batch_data.get("count", 0)
            if len(all_records) >= total_count:
                break
                
            page += 1
            if page > 50:
                logger.warning("Reached pagination limit")
                break
        
        return all_records

    def calculate_user_performance_from_records(
        self,
        user_id: str,
        user_name: str,
        call_records: List[Dict],
        date_from: str,
        date_to: str
    ) -> Dict:
        """
        Simple performance calculation from call records
        """
        total_calls = len(call_records)
        answered_calls = sum(1 for r in call_records if r.get("status") == "answered")
        missed_calls = total_calls - answered_calls
        
        total_duration = sum(
            r.get("call_duration", 0) 
            for r in call_records 
            if r.get("status") == "answered"
        )
        
        recordings_count = sum(1 for r in call_records if r.get("recording_url"))
        
        success_rate = (answered_calls / total_calls * 100) if total_calls > 0 else 0.0
        avg_duration = (total_duration / answered_calls) if answered_calls > 0 else 0.0
        
        return {
            "user_id": user_id,
            "user_name": user_name,
            "total_calls": total_calls,
            "answered_calls": answered_calls,
            "missed_calls": missed_calls,
            "success_rate": round(success_rate, 2),
            "total_duration": total_duration,
            "avg_call_duration": round(avg_duration, 2),
            "recordings_count": recordings_count,
            "date_range": f"{date_from} to {date_to}"
        }

    def map_agent_to_user(self, agent_number: str) -> Dict[str, str]:
        """
        Map TATA agent number to LeadG CRM user using database data
        """
        if not agent_number:
            return {
                "user_id": "unknown",
                "user_name": "Unknown Agent",
                "user_email": "",
                "tata_agent_id": None,
                "tata_extension": None
            }
        
        # Clean agent number for mapping
        clean_number = agent_number
        if clean_number.startswith('+'):
            clean_number = clean_number[1:]
        
        # Try multiple formats for mapping
        for search_format in [agent_number, f"+{clean_number}", clean_number]:
            mapping = self.agent_user_mapping.get(search_format)
            if mapping:
                return mapping
        
        # Return unknown user with cleaned number
        return {
            "user_id": f"unknown_{clean_number}",
            "user_name": f"Unknown ({agent_number})",
            "user_email": "",
            "tata_agent_id": None,
            "tata_extension": None
        }
    
    def parse_call_record(self, record: Dict) -> CallRecord:
        """
        Parse TATA API call record into our CallRecord model
        """
        # DEBUG: Log what TATA actually returns
      
        
        agent_number = record.get("agent_number", "")
        user_mapping = self.map_agent_to_user(agent_number)
        
        return CallRecord(
            call_id=record.get("id", ""),           # Main ID for frontend use
            tata_call_id=record.get("call_id", ""), # Secondary TATA call_id
            uuid=record.get("uuid"),                # UUID
            id=record.get("id", ""),                # Also store in id field
            direction=record.get("direction", "unknown"),
            status=record.get("status", "unknown"),
            service=record.get("service", ""),
            date=record.get("date", ""),
            time=record.get("time", ""),
            end_stamp=record.get("end_stamp"),
            call_duration=record.get("call_duration", 0),
            answered_seconds=record.get("answered_seconds", 0),
            agent_number=agent_number,
            agent_name=record.get("agent_name", ""),
            client_number=record.get("client_number", ""),
            did_number=record.get("did_number"),
            recording_url=record.get("recording_url"),
            hangup_cause=record.get("hangup_cause"),
            circle=record.get("circle"),
            user_id=user_mapping.get("user_id"),
            user_name=user_mapping.get("user_name"),
            lead_id=record.get("lead_id")
        )


    def calculate_daily_stats(
        self, 
        call_records: List[Dict], 
        target_date: str
    ) -> Dict[str, UserCallStats]:
        """
        Calculate daily call statistics for all users
        """
        daily_stats = defaultdict(lambda: {
            "user_name": "Unknown",
            "agent_number": "",
            "daily_calls": 0,
            "daily_answered": 0,
            "daily_missed": 0,
            "daily_duration": 0,
            "daily_recordings": 0
        })
        
        for record in call_records:
            # Filter by date
            record_date = record.get("date", "")
            if record_date != target_date:
                continue
            
            agent_number = record.get("agent_number", "")
            if not agent_number:
                continue
            
            # Map agent to user
            user_mapping = self.map_agent_to_user(agent_number)
            user_id = user_mapping.get("user_id", agent_number)
            
            # Update stats
            stats = daily_stats[user_id]
            stats["user_name"] = user_mapping.get("user_name", agent_number)
            stats["agent_number"] = agent_number
            stats["daily_calls"] += 1
            
            # Call status
            call_status = record.get("status", "")
            if call_status == "answered":
                stats["daily_answered"] += 1
                stats["daily_duration"] += record.get("call_duration", 0)
            else:
                stats["daily_missed"] += 1
            
            # Recording check
            if record.get("recording_url"):
                stats["daily_recordings"] += 1
        
        # Convert to UserCallStats objects
        result = {}
        for user_id, stats in daily_stats.items():
            result[user_id] = UserCallStats(
                user_id=user_id,
                user_name=stats["user_name"],
                agent_number=stats["agent_number"],
                daily_calls=stats["daily_calls"],
                daily_answered=stats["daily_answered"],
                daily_missed=stats["daily_missed"],
                daily_duration=stats["daily_duration"],
                daily_recordings=stats["daily_recordings"],
                success_rate=round(
                    (stats["daily_answered"] / stats["daily_calls"]) * 100, 2
                ) if stats["daily_calls"] > 0 else 0.0,
                avg_call_duration=round(
                    stats["daily_duration"] / stats["daily_answered"], 2
                ) if stats["daily_answered"] > 0 else 0.0
            )
        
        return result
    
    def calculate_period_stats(
        self,
        call_records: List[Dict],
        period_type: str,
        period_value: str
    ) -> Dict[str, UserCallStats]:
        """
        Calculate call statistics for a specific period
        """
        period_stats = defaultdict(lambda: {
            "user_name": "Unknown",
            "agent_number": "",
            "total_calls": 0,
            "answered_calls": 0,
            "missed_calls": 0,
            "total_duration": 0,
            "recordings_count": 0
        })
        
        for record in call_records:
            # Filter by period
            record_date = record.get("date", "")
            if not self._is_record_in_period(record_date, period_type, period_value):
                continue
            
            agent_number = record.get("agent_number", "")
            if not agent_number:
                continue
            
            # Map agent to user
            user_mapping = self.map_agent_to_user(agent_number)
            user_id = user_mapping.get("user_id", agent_number)
            
            # Update stats
            stats = period_stats[user_id]
            stats["user_name"] = user_mapping.get("user_name", agent_number)
            stats["agent_number"] = agent_number
            stats["total_calls"] += 1
            
            # Call status
            call_status = record.get("status", "")
            if call_status == "answered":
                stats["answered_calls"] += 1
                stats["total_duration"] += record.get("call_duration", 0)
            else:
                stats["missed_calls"] += 1
            
            # Recording check
            if record.get("recording_url"):
                stats["recordings_count"] += 1
        
        # Convert to UserCallStats objects
        result = {}
        for user_id, stats in period_stats.items():
            user_stats = UserCallStats(
                user_id=user_id,
                user_name=stats["user_name"],
                agent_number=stats["agent_number"],
                success_rate=round(
                    (stats["answered_calls"] / stats["total_calls"]) * 100, 2
                ) if stats["total_calls"] > 0 else 0.0,
                avg_call_duration=round(
                    stats["total_duration"] / stats["answered_calls"], 2
                ) if stats["answered_calls"] > 0 else 0.0
            )
            
            # Set period-specific stats
            if period_type == "daily":
                user_stats.daily_calls = stats["total_calls"]
                user_stats.daily_answered = stats["answered_calls"]
                user_stats.daily_missed = stats["missed_calls"]
                user_stats.daily_duration = stats["total_duration"]
                user_stats.daily_recordings = stats["recordings_count"]
            elif period_type == "weekly":
                user_stats.weekly_calls = stats["total_calls"]
                user_stats.weekly_answered = stats["answered_calls"]
                user_stats.weekly_missed = stats["missed_calls"]
                user_stats.weekly_duration = stats["total_duration"]
                user_stats.weekly_recordings = stats["recordings_count"]
            elif period_type == "monthly":
                user_stats.monthly_calls = stats["total_calls"]
                user_stats.monthly_answered = stats["answered_calls"]
                user_stats.monthly_missed = stats["missed_calls"]
                user_stats.monthly_duration = stats["total_duration"]
                user_stats.monthly_recordings = stats["recordings_count"]
            
            result[user_id] = user_stats
        
        return result
    
    def _is_record_in_period(self, record_date: str, period_type: str, period_value: str) -> bool:
        """
        Check if a record date falls within the specified period
        """
        try:
            if period_type == "daily":
                return record_date == period_value
            
            elif period_type == "weekly":
                date_obj = datetime.strptime(record_date, "%Y-%m-%d")
                week_num = date_obj.isocalendar()[1]
                year = date_obj.year
                expected_week = f"{year}-W{week_num:02d}"
                return expected_week == period_value
            
            elif period_type == "monthly":
                record_month = record_date[:7]  # YYYY-MM
                return record_month == period_value
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking period: {e}")
            return False
    
    async def get_weekly_performers(
        self, 
        week_start: datetime, 
        week_end: datetime,
        top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        LEGACY: Get top weekly performers (kept for backward compatibility)
        """
        return await self.get_weekly_performers_optimized(week_start, week_end, top_n)
    
    async def get_monthly_performers(
        self, 
        year: int, 
        month: int,
        top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        LEGACY: Get top monthly performers (kept for backward compatibility)
        """
        return await self.get_monthly_performers_optimized(year, month, top_n)
    
    async def get_day_to_day_comparison(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get day-to-day call comparison for a specific user using TATA filtering
        """
        try:
            # Format dates for TATA API
            from_date = start_date.strftime("%Y-%m-%d 00:00:00")
            to_date = end_date.strftime("%Y-%m-%d 23:59:59")
            
            # Get user's agent number for filtering
            user_agent = None
            for agent, mapping in self.agent_user_mapping.items():
                if mapping.get("user_id") == user_id:
                    user_agent = agent
                    break
            
            # Build TATA API params with user filter
            params = {
                "from_date": from_date,
                "to_date": to_date,
                "page": "1",
                "limit": "1000"
            }
            
            if user_agent:
                params["agents"] = user_agent
            
            # Use optimized TATA API call
            result = await self.fetch_call_records_with_filters(params)
            
            if not result.get("success"):
                logger.error(f"Failed to fetch comparison data: {result.get('error')}")
                return []
            
            call_records = result.get("data", {}).get("results", [])
            
            # Group by date
            daily_stats = defaultdict(lambda: {
                "total_calls": 0,
                "answered_calls": 0,
                "missed_calls": 0,
                "total_duration": 0,
                "recordings_count": 0
            })
            
            for record in call_records:
                # Additional user filter if TATA filtering didn't work
                if not user_agent:
                    agent_number = record.get("agent_number", "")
                    user_mapping = self.map_agent_to_user(agent_number)
                    if user_mapping.get("user_id") != user_id:
                        continue
                
                record_date = record.get("date", "")
                if not record_date:
                    continue
                
                stats = daily_stats[record_date]
                stats["total_calls"] += 1
                
                if record.get("status") == "answered":
                    stats["answered_calls"] += 1
                    stats["total_duration"] += record.get("call_duration", 0)
                else:
                    stats["missed_calls"] += 1
                
                if record.get("recording_url"):
                    stats["recordings_count"] += 1
            
            # Convert to list with day-to-day comparison
            result = []
            sorted_dates = sorted(daily_stats.keys())
            
            for i, date in enumerate(sorted_dates):
                stats = daily_stats[date]
                
                success_rate = (
                    (stats["answered_calls"] / stats["total_calls"]) * 100
                    if stats["total_calls"] > 0 else 0.0
                )
                
                # Calculate change from previous day
                calls_change = 0
                calls_change_percent = 0.0
                trend = "stable"
                
                if i > 0:
                    prev_date = sorted_dates[i - 1]
                    prev_stats = daily_stats[prev_date]
                    
                    calls_change = stats["total_calls"] - prev_stats["total_calls"]
                    
                    if prev_stats["total_calls"] > 0:
                        calls_change_percent = (calls_change / prev_stats["total_calls"]) * 100
                    
                    if calls_change > 0:
                        trend = "up"
                    elif calls_change < 0:
                        trend = "down"
                
                result.append({
                    "date": date,
                    "total_calls": stats["total_calls"],
                    "answered_calls": stats["answered_calls"],
                    "missed_calls": stats["missed_calls"],
                    "total_duration": stats["total_duration"],
                    "success_rate": round(success_rate, 2),
                    "recordings_count": stats["recordings_count"],
                    "calls_change": calls_change,
                    "calls_change_percent": round(calls_change_percent, 2),
                    "trend": trend
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating optimized day-to-day comparison: {e}")
            return []
    
    async def log_admin_activity(
        self,
        admin_user_id: str,
        admin_email: str,
        action: str,
        target_user_id: Optional[str] = None,
        target_user_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """
        Log admin activity for compliance and auditing
        """
        try:
            db = self._get_db()
            if db is None:
                logger.warning("Database not available for admin logging")
                return
            
            log_entry = AdminActivityLog(
                admin_user_id=admin_user_id,
                admin_email=admin_email,
                action=action,
                target_user_id=target_user_id,
                target_user_name=target_user_name,
                details=details or {},
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            # Insert into admin_activity_logs collection
            await db.admin_activity_logs.insert_one(log_entry.dict())
            
            logger.info(f"Logged admin activity: {action} by {admin_email}")
            
        except Exception as e:
            logger.error(f"Error logging admin activity: {e}")
    
    async def get_recording_url(self, call_id: str) -> Optional[str]:
        """
        Get recording URL for a specific call using TATA API
        """
        try:
            logger.info(f"Getting recording URL for call {call_id}")
            
            # Use TATA API to search for the specific call
            today = datetime.now()
            from_date = (today - timedelta(days=30)).strftime("%Y-%m-%d 00:00:00")
            to_date = today.strftime("%Y-%m-%d 23:59:59")
            
            params = {
                "from_date": from_date,
                "to_date": to_date,
                "call_id": call_id,
                "page": "1",
                "limit": "1"
            }
            
            result = await self.fetch_call_records_with_filters(params)
            
            if not result.get("success"):
                logger.error(f"Failed to search for call {call_id}: {result.get('error')}")
                return None
            
            records = result.get("data", {}).get("results", [])
            if not records:
                logger.warning(f"Call {call_id} not found in recent records")
                return None
            
            recording_url = records[0].get("recording_url")
            if recording_url:
                logger.info(f"Found recording URL for call {call_id}")
                return recording_url
            else:
                logger.info(f"No recording available for call {call_id}")
                return None
            
        except Exception as e:
            logger.error(f"Error getting recording URL: {e}")
            return None

    async def ensure_authentication(self) -> bool:
        """
        Ensure we have valid authentication before making API calls
        """
        try:
            token = await self._get_valid_auth_token()
            if not token:
                logger.warning("No valid TATA token - attempting to refresh")
                refresh_result = await tata_auth_service.refresh_token()
                if refresh_result.get("success"):
                    return True
                else:
                    logger.error("Failed to refresh TATA token")
                    return False
            return True
        except Exception as e:
            logger.error(f"Error ensuring authentication: {e}")
            return False


# Create singleton instance
tata_admin_service = TataAdminService()