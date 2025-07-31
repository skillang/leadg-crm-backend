# app/services/call_log_service.py
# Enhanced Call Log Service with Tata CDR Integration
# Handles call history management, analytics, reporting, and Tata call record synchronization

import logging
import asyncio
import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from bson import ObjectId
import json
import re
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


from ..config.database import get_database
from ..config.settings import get_settings
from ..models.call_log import (
    CallLogResponse, CallHistoryFilter, CallHistoryResponse, CallAnalytics,
    CallSummaryReport, CallStatus, CallOutcome, CallType, CallPriority,
    CallbackRequest, CallbackResponse, UpcomingCallbacksResponse,
    CallExportRequest, CallExportResponse, BulkCallResponse
)
from ..utils.dependencies import get_current_user

# 🆕 NEW: Import Tata auth service for CDR API access
try:
    from .tata_auth_service import tata_auth_service
    TATA_CDR_AVAILABLE = True
    logger.info("✅ Tata CDR integration available")
except ImportError as e:
    TATA_CDR_AVAILABLE = False
    logger.warning(f"⚠️ Tata CDR integration not available: {e}")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CallLogService:
    """
    Enhanced Call Log Service with Tata CDR Integration
    Handles call history, analytics, callbacks, reporting, and Tata call record synchronization
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.db = None
        
        # 🆕 NEW: Tata CDR integration settings
        self.tata_auth_service = tata_auth_service if TATA_CDR_AVAILABLE else None
        self.tata_base_url = getattr(self.settings, 'tata_api_base_url', '')
        self.cdr_sync_batch_size = 100
        self.cdr_max_date_range = 30  # Max days per API call
        
        # Configuration
        self.default_page_size = 20
        self.max_page_size = 100
        self.retention_days = getattr(self.settings, 'CALL_LOG_RETENTION_DAYS', 365)

    # 🔧 FIX: Add lazy database initialization
    def _get_db(self):
        """Lazy database initialization"""
        if self.db is None:
            try:
                self.db = get_database()
            except RuntimeError:
                return None
        return self.db

    # =============================================================================
    # 🆕 NEW: TATA CDR INTEGRATION METHODS
    # =============================================================================

    async def fetch_tata_call_records(
        self, 
        date_from: datetime, 
        date_to: datetime,
        call_type: str = "all",
        sync_to_database: bool = True
    ) -> Dict[str, Any]:
        """
        Fetch call records from Tata CDR API and optionally sync to database
        
        Args:
            date_from: Start date for CDR fetch
            date_to: End date for CDR fetch  
            call_type: Type of calls to fetch (all, click_to_call, dialer, incoming)
            sync_to_database: Whether to sync fetched records to database
            
        Returns:
            Dict with success status and fetched records
        """
        if not TATA_CDR_AVAILABLE:
            return {
                "success": False,
                "message": "Tata CDR integration not available",
                "records": []
            }
        
        try:
            logger.info(f"Fetching Tata CDR records from {date_from} to {date_to}")
            
            # Validate date range (Tata API limitation)
            date_diff = (date_to - date_from).days
            if date_diff > self.cdr_max_date_range:
                return {
                    "success": False,
                    "message": f"Date range too large. Maximum {self.cdr_max_date_range} days per request.",
                    "records": []
                }
            
            # Prepare API parameters
            params = {
                "from_date": date_from.strftime('%Y-%m-%d'),
                "to_date": date_to.strftime('%Y-%m-%d'),
                "page": 1,
                "limit": self.cdr_sync_batch_size
            }
            
            if call_type != "all":
                params["call_type"] = call_type
            
            all_records = []
            has_more = True
            page = 1
            
            # Fetch all pages
            while has_more and page <= 50:  # Safety limit
                params["page"] = page
                
                success, response = await self._make_tata_cdr_request("GET", "/v1/call/records", params)
                
                if not success:
                    logger.error(f"CDR API request failed: {response}")
                    break
                
                batch_records = response.get("data", [])
                if not batch_records:
                    break
                
                all_records.extend(batch_records)
                
                # Check pagination
                has_more = response.get("has_more", False)
                total_pages = response.get("total_pages", 1)
                has_more = has_more and page < total_pages
                page += 1
                
                logger.debug(f"Fetched page {page-1}: {len(batch_records)} records")
                
                # Small delay to be API-friendly
                await asyncio.sleep(0.1)
            
            logger.info(f"✅ Fetched {len(all_records)} total CDR records from Tata API")
            
            # Enrich records with CRM data
            enriched_records = await self._enrich_tata_call_records(all_records)
            
            # Sync to database if requested
            if sync_to_database and enriched_records:
                sync_count = await self._sync_cdr_records_to_database(enriched_records)
                logger.info(f"✅ Synced {sync_count} CDR records to database")
            
            return {
                "success": True,
                "records": enriched_records,
                "total_fetched": len(all_records),
                "total_enriched": len(enriched_records),
                "date_range": f"{date_from.strftime('%Y-%m-%d')} to {date_to.strftime('%Y-%m-%d')}",
                "synced_to_db": sync_to_database
            }
            
        except Exception as e:
            logger.error(f"Error fetching Tata CDR records: {str(e)}")
            return {
                "success": False,
                "message": f"CDR fetch failed: {str(e)}",
                "records": []
            }

    async def _make_tata_cdr_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Dict = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Make authenticated request to Tata CDR API"""
        try:
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
            
            async with httpx.AsyncClient(timeout=60) as client:  # Longer timeout for CDR
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method.upper() == "POST":
                    response = await client.post(url, headers=headers, json=params)
                else:
                    return False, {"error": "Unsupported HTTP method"}
                
                if response.status_code == 200:
                    return True, response.json()
                else:
                    logger.error(f"CDR API request failed: {response.status_code} - {response.text}")
                    return False, {
                        "error": f"API request failed with status {response.status_code}",
                        "details": response.text
                    }
                    
        except Exception as e:
            logger.error(f"CDR API request error: {str(e)}")
            return False, {"error": str(e)}

    async def _enrich_tata_call_records(self, tata_records: List[Dict]) -> List[Dict]:
        """
        Enrich Tata CDR records with CRM lead and agent information
        
        Args:
            tata_records: Raw CDR records from Tata API
            
        Returns:
            List of enriched call records
        """
        try:
            db = self._get_db()
            if not db:
                return tata_records
            
            enriched_records = []
            
            for record in tata_records:
                try:
                    enriched_record = {
                        # Tata call data
                        "tata_call_id": record.get("call_id") or record.get("unique_id"),
                        "tata_session_id": record.get("session_id"),
                        "call_type": record.get("call_type", "unknown"),
                        "call_direction": record.get("direction", "outbound"),
                        "call_status": record.get("status", "unknown"),
                        "call_outcome": record.get("disposition", "unknown"),
                        "call_duration": record.get("duration", 0),  # in seconds
                        "call_start_time": self._parse_tata_datetime(record.get("start_time")),
                        "call_end_time": self._parse_tata_datetime(record.get("end_time")),
                        "caller_number": record.get("caller_id") or record.get("from_number"),
                        "destination_number": record.get("destination_number") or record.get("to_number"),
                        "recording_url": record.get("recording_url"),
                        "call_cost": record.get("cost", 0),
                        "wait_time": record.get("wait_time", 0),
                        "talk_time": record.get("talk_time", 0),
                        "campaign_id": record.get("campaign_id"),
                        
                        # Metadata
                        "fetched_from_tata": True,
                        "tata_fetch_time": datetime.utcnow(),
                        "raw_tata_data": record
                    }
                    
                    # Enrich with CRM lead information
                    destination_number = enriched_record["destination_number"]
                    if destination_number:
                        lead_info = await self._find_lead_by_phone(destination_number)
                        if lead_info:
                            enriched_record.update({
                                "lead_id": lead_info.get("lead_id"),
                                "lead_name": lead_info.get("name") or lead_info.get("full_name"),
                                "lead_email": lead_info.get("email"),
                                "lead_status": lead_info.get("status"),
                                "lead_company": lead_info.get("company_name"),
                                "lead_assigned_to": lead_info.get("assigned_to")
                            })
                    
                    # Enrich with CRM agent information
                    caller_number = enriched_record["caller_number"]
                    if caller_number:
                        agent_info = await self._find_agent_by_phone_or_extension(caller_number)
                        if agent_info:
                            enriched_record.update({
                                "caller_user_id": str(agent_info.get("_id")),
                                "caller_name": agent_info.get("full_name"),
                                "caller_email": agent_info.get("email"),
                                "caller_role": agent_info.get("role"),
                                "tata_agent_id": agent_info.get("tata_agent_id"),
                                "tata_extension": agent_info.get("tata_extension")
                            })
                    
                    enriched_records.append(enriched_record)
                    
                except Exception as e:
                    logger.warning(f"Error enriching CDR record: {str(e)}")
                    # Still include the record but without enrichment
                    enriched_records.append({
                        **record,
                        "fetched_from_tata": True,
                        "enrichment_error": str(e)
                    })
            
            logger.info(f"✅ Enriched {len(enriched_records)} CDR records with CRM data")
            return enriched_records
            
        except Exception as e:
            logger.error(f"Error enriching Tata records: {str(e)}")
            return tata_records

    async def _find_lead_by_phone(self, phone_number: str) -> Optional[Dict]:
        """Find CRM lead by phone number with fuzzy matching"""
        try:
            db = self._get_db()
            if not db or not phone_number:
                return None
            
            # Clean phone number
            cleaned_phone = self._clean_phone_number(phone_number)
            
            # Try exact match first
            lead = await db.leads.find_one({"phone": phone_number})
            if lead:
                return lead
            
            # Try cleaned phone match
            if cleaned_phone != phone_number:
                # Search for partial matches
                regex_pattern = cleaned_phone[-10:] if len(cleaned_phone) > 10 else cleaned_phone
                lead = await db.leads.find_one({
                    "phone": {"$regex": regex_pattern, "$options": "i"}
                })
                if lead:
                    return lead
            
            return None
            
        except Exception as e:
            logger.debug(f"Error finding lead by phone {phone_number}: {str(e)}")
            return None

    async def _find_agent_by_phone_or_extension(self, identifier: str) -> Optional[Dict]:
        """Find CRM user/agent by phone number or Tata extension"""
        try:
            db = self._get_db()
            if not db or not identifier:
                return None
            
            # Try finding by Tata extension first
            user = await db.users.find_one({"tata_extension": identifier})
            if user:
                return user
            
            # Try finding by phone number
            user = await db.users.find_one({"phone": identifier})
            if user:
                return user
            
            # Try finding via Tata mapping
            mapping = await db.tata_user_mappings.find_one({
                "$or": [
                    {"tata_caller_id": identifier},
                    {"tata_did_number": identifier},
                    {"tata_extension": identifier}
                ]
            })
            
            if mapping:
                user = await db.users.find_one({"_id": ObjectId(mapping["crm_user_id"])})
                return user
            
            return None
            
        except Exception as e:
            logger.debug(f"Error finding agent by identifier {identifier}: {str(e)}")
            return None

    def _clean_phone_number(self, phone: str) -> str:
        """Clean and normalize phone number"""
        if not phone:
            return ""
        # Remove all non-digit characters
        cleaned = re.sub(r'[^\d]', '', phone)
        # Remove country code if present (assuming +91 for India)
        if cleaned.startswith('91') and len(cleaned) > 10:
            cleaned = cleaned[2:]
        elif cleaned.startswith('0') and len(cleaned) == 11:
            cleaned = cleaned[1:]
        return cleaned

    def _parse_tata_datetime(self, dt_string: str) -> Optional[datetime]:
        """Parse Tata datetime string to Python datetime"""
        if not dt_string:
            return None
        try:
            # Try common datetime formats
            for fmt in [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S.%f"
            ]:
                try:
                    return datetime.strptime(dt_string, fmt)
                except ValueError:
                    continue
            return None
        except Exception:
            return None

    async def _sync_cdr_records_to_database(self, enriched_records: List[Dict]) -> int:
        """Sync enriched CDR records to call_logs collection"""
        try:
            db = self._get_db()
            if not db:
                return 0
            
            synced_count = 0
            
            for record in enriched_records:
                try:
                    # Check if record already exists
                    tata_call_id = record.get("tata_call_id")
                    if tata_call_id:
                        existing = await db.call_logs.find_one({"tata_call_id": tata_call_id})
                        if existing:
                            logger.debug(f"CDR record {tata_call_id} already exists, skipping")
                            continue
                    
                    # Prepare call log document
                    call_log_doc = {
                        "_id": ObjectId(),
                        "call_id": f"CDR_{tata_call_id}_{int(datetime.utcnow().timestamp())}",
                        "tata_call_id": tata_call_id,
                        "lead_id": record.get("lead_id"),
                        "caller_user_id": record.get("caller_user_id"),
                        "destination_number": record.get("destination_number"),
                        "caller_number": record.get("caller_number"),
                        "call_type": self._map_tata_call_type(record.get("call_type")),
                        "call_status": self._map_tata_call_status(record.get("call_status")),
                        "call_outcome": self._map_tata_call_outcome(record.get("call_outcome")),
                        "call_duration": record.get("call_duration", 0),
                        "call_priority": "normal",
                        "notes": f"Synced from Tata CDR - {record.get('call_type', 'unknown')} call",
                        "created_at": record.get("call_start_time") or datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                        "synced_from_tata": True,
                        "tata_metadata": {
                            "session_id": record.get("tata_session_id"),
                            "direction": record.get("call_direction"),
                            "recording_url": record.get("recording_url"),
                            "cost": record.get("call_cost"),
                            "wait_time": record.get("wait_time"),
                            "talk_time": record.get("talk_time"),
                            "campaign_id": record.get("campaign_id"),
                            "raw_data": record.get("raw_tata_data", {})
                        }
                    }
                    
                    # Insert record
                    await db.call_logs.insert_one(call_log_doc)
                    synced_count += 1
                    
                except Exception as e:
                    logger.warning(f"Error syncing CDR record: {str(e)}")
                    continue
            
            logger.info(f"✅ Successfully synced {synced_count} CDR records to database")
            return synced_count
            
        except Exception as e:
            logger.error(f"Error syncing CDR records to database: {str(e)}")
            return 0

    def _map_tata_call_type(self, tata_type: str) -> str:
        """Map Tata call type to CRM call type"""
        mapping = {
            "click_to_call": "click_to_call",
            "dialer": "progressive_dialer",
            "incoming": "incoming",
            "outbound": "click_to_call",
            "support": "support_call"
        }
        return mapping.get(tata_type, "unknown")

    def _map_tata_call_status(self, tata_status: str) -> str:
        """Map Tata call status to CRM call status"""
        mapping = {
            "answered": "answered",
            "completed": "completed",
            "failed": "failed",
            "busy": "busy",
            "no_answer": "no_answer",
            "timeout": "timeout",
            "cancelled": "cancelled"
        }
        return mapping.get(tata_status, "unknown")

    def _map_tata_call_outcome(self, tata_outcome: str) -> str:
        """Map Tata call outcome to CRM call outcome"""
        mapping = {
            "successful": "successful",
            "interested": "interested",
            "not_interested": "not_interested",
            "no_response": "no_response",
            "callback_requested": "callback_requested",
            "meeting_scheduled": "meeting_scheduled"
        }
        return mapping.get(tata_outcome, "unknown")

    async def sync_call_records_realtime(
        self, 
        hours_back: int = 24,
        auto_sync: bool = True
    ) -> Dict[str, Any]:
        """
        Background job to sync recent call records from Tata CDR API
        
        Args:
            hours_back: How many hours back to sync
            auto_sync: Whether this is an automatic sync
            
        Returns:
            Sync results summary
        """
        if not TATA_CDR_AVAILABLE:
            return {
                "success": False,
                "message": "Tata CDR integration not available"
            }
        
        try:
            logger.info(f"Starting real-time CDR sync for last {hours_back} hours")
            
            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(hours=hours_back)
            
            # Fetch and sync records
            result = await self.fetch_tata_call_records(
                date_from=start_date,
                date_to=end_date,
                sync_to_database=True
            )
            
            if result.get("success"):
                return {
                    "success": True,
                    "sync_type": "realtime" if auto_sync else "manual",
                    "records_fetched": result.get("total_fetched", 0),
                    "records_synced": result.get("total_enriched", 0),
                    "date_range": result.get("date_range"),
                    "sync_timestamp": datetime.utcnow().isoformat(),
                    "message": f"Successfully synced {result.get('total_enriched', 0)} call records"
                }
            else:
                return {
                    "success": False,
                    "message": result.get("message", "Sync failed"),
                    "sync_timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Real-time CDR sync failed: {str(e)}")
            return {
                "success": False,
                "message": f"Sync failed: {str(e)}",
                "sync_timestamp": datetime.utcnow().isoformat()
            }

    async def get_enhanced_call_analytics(
        self,
        current_user: Dict[str, Any],
        date_from: datetime,
        date_to: datetime,
        include_tata_data: bool = True
    ) -> Dict[str, Any]:
        """
        Get enhanced call analytics including Tata CDR data
        
        Returns comprehensive analytics with Tata call integration
        """
        try:
            db = self._get_db()
            if not db:
                return {"error": "Database not available"}
            
            user_role = current_user.get("role", "user")
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            # Build base query
            query = {
                "created_at": {"$gte": date_from, "$lte": date_to}
            }
            
            if user_role != "admin":
                query["caller_user_id"] = user_id
            
            # Get regular analytics
            regular_analytics = await self._generate_call_analytics(query)
            
            # Get Tata-specific analytics if available
            tata_analytics = {}
            if include_tata_data and TATA_CDR_AVAILABLE:
                tata_query = {**query, "synced_from_tata": True}
                tata_analytics = await self._generate_tata_specific_analytics(tata_query)
            
            # Combine analytics
            enhanced_analytics = {
                "date_range": {
                    "from": date_from.isoformat(),
                    "to": date_to.isoformat()
                },
                "regular_calls": regular_analytics.dict() if hasattr(regular_analytics, 'dict') else regular_analytics,
                "tata_cdr_data": tata_analytics,
                "combined_metrics": {
                    "total_calls_all_sources": regular_analytics.total_calls,
                    "success_rate_combined": regular_analytics.success_rate,
                    "average_duration_combined": regular_analytics.average_duration,
                    "data_sources": ["crm_native", "tata_cdr"] if tata_analytics else ["crm_native"]
                },
                "data_quality": {
                    "tata_integration_active": TATA_CDR_AVAILABLE,
                    "last_tata_sync": await self._get_last_tata_sync_time(),
                    "enrichment_rate": await self._calculate_enrichment_rate(query)
                }
            }
            
            return enhanced_analytics
            
        except Exception as e:
            logger.error(f"Error generating enhanced analytics: {str(e)}")
            return {"error": str(e)}

    async def _generate_tata_specific_analytics(self, query: Dict) -> Dict[str, Any]:
        """Generate analytics specific to Tata CDR data"""
        try:
            db = self._get_db()
            if not db:
                return {}
            
            # Tata-specific metrics pipeline
            pipeline = [
                {"$match": query},
                {
                    "$group": {
                        "_id": None,
                        "total_tata_calls": {"$sum": 1},
                        "total_call_cost": {"$sum": {"$toDouble": "$tata_metadata.cost"}},
                        "avg_wait_time": {"$avg": {"$toDouble": "$tata_metadata.wait_time"}},
                        "avg_talk_time": {"$avg": {"$toDouble": "$tata_metadata.talk_time"}},
                        "calls_with_recordings": {
                            "$sum": {"$cond": [{"$ne": ["$tata_metadata.recording_url", None]}, 1, 0]}
                        },
                        "campaign_calls": {
                            "$sum": {"$cond": [{"$ne": ["$tata_metadata.campaign_id", None]}, 1, 0]}
                        },
                        "call_directions": {"$push": "$tata_metadata.direction"}
                    }
                }
            ]
            
            result = await db.call_logs.aggregate(pipeline).to_list(length=1)
            
            if result:
                stats = result[0]
                return {
                    "total_tata_calls": stats.get("total_tata_calls", 0),
                    "total_call_cost": round(stats.get("total_call_cost", 0), 2),
                    "average_wait_time": round(stats.get("avg_wait_time", 0), 2),
                    "average_talk_time": round(stats.get("avg_talk_time", 0), 2),
                    "calls_with_recordings": stats.get("calls_with_recordings", 0),
                    "campaign_calls": stats.get("campaign_calls", 0),
                    "recording_rate": round(
                        (stats.get("calls_with_recordings", 0) / stats.get("total_tata_calls", 1)) * 100, 2
                    ) if stats.get("total_tata_calls", 0) > 0 else 0
                }
            else:
                return {}
                
        except Exception as e:
            logger.error(f"Error generating Tata analytics: {str(e)}")
            return {}

    async def _get_last_tata_sync_time(self) -> Optional[str]:
        """Get timestamp of last Tata CDR sync"""
        try:
            db = self._get_db()
            if not db:
                return None
            
            last_record = await db.call_logs.find_one(
                {"synced_from_tata": True},
                sort=[("tata_metadata.fetch_time", -1)]
            )
            
            if last_record and last_record.get("tata_metadata", {}).get("fetch_time"):
                return last_record["tata_metadata"]["fetch_time"].isoformat()
            
            return None
            
        except Exception as e:
            logger.debug(f"Error getting last sync time: {str(e)}")
            return None

    async def _calculate_enrichment_rate(self, query: Dict) -> float:
        """Calculate percentage of calls that have been enriched with CRM data"""
        try:
            db = self._get_db()
            if not db:
                return 0
            
            total_calls = await db.call_logs.count_documents(query)
            if total_calls == 0:
                return 0
            
            enriched_calls = await db.call_logs.count_documents({
                **query,
                "$or": [
                    {"lead_id": {"$ne": None}},
                    {"caller_name": {"$ne": None}}
                ]
            })
            
            return round((enriched_calls / total_calls) * 100, 2)
            
        except Exception as e:
            logger.debug(f"Error calculating enrichment rate: {str(e)}")
            return 0

    # =============================================================================
    # EXISTING METHODS - PRESERVED WITH MINOR ENHANCEMENTS
    # =============================================================================

    def _convert_objectid_to_str(self, obj):
        """Recursively convert ObjectId to string in any data structure"""
        if isinstance(obj, ObjectId):
            return str(obj)
        elif isinstance(obj, dict):
            return {key: self._convert_objectid_to_str(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_objectid_to_str(item) for item in obj]
        else:
            return obj

    async def _enrich_call_log(self, call_log: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich call log with user and lead information"""
        try:
            db = self._get_db()
            if not db:
                return self._convert_objectid_to_str(call_log)
                
            # Convert ObjectIds to strings
            enriched_log = self._convert_objectid_to_str(call_log)
            
            # Get caller user information
            caller_user_id = enriched_log.get("caller_user_id")
            if caller_user_id:
                user = await db.users.find_one({"_id": ObjectId(caller_user_id)})
                if user:
                    enriched_log["caller_name"] = user.get("full_name", user.get("name", "Unknown"))
                    enriched_log["caller_email"] = user.get("email")
            
            # Get lead information
            lead_id = enriched_log.get("lead_id")
            if lead_id and lead_id.startswith("LD-"):
                lead = await db.leads.find_one({"lead_id": lead_id})
                if lead:
                    enriched_log["lead_name"] = lead.get("name", lead.get("full_name"))
                    enriched_log["lead_email"] = lead.get("email")
                    enriched_log["lead_status"] = lead.get("status")
            
            # Calculate if callback is overdue
            scheduled_at = enriched_log.get("scheduled_at")
            if scheduled_at and isinstance(scheduled_at, datetime):
                enriched_log["is_overdue"] = scheduled_at < datetime.utcnow()
            
            # 🆕 NEW: Add Tata CDR indicators
            enriched_log["is_tata_synced"] = enriched_log.get("synced_from_tata", False)
            enriched_log["has_recording"] = bool(
                enriched_log.get("tata_metadata", {}).get("recording_url")
            )
            
            return enriched_log
            
        except Exception as e:
            logger.error(f"Error enriching call log: {str(e)}")
            return self._convert_objectid_to_str(call_log)

    async def get_call_history(
        self, 
        filters: CallHistoryFilter,
        current_user: Dict[str, Any]
    ) -> CallHistoryResponse:
        """
        Get call history with filtering, pagination, and analytics
        🆕 ENHANCED: Now includes Tata CDR data
        """
        try:
            db = self._get_db()
            if not db:
                raise Exception("Database not available")
            
            # Build MongoDB query based on filters
            query = {}
            
            # Permission-based filtering
            user_role = current_user.get("role", "user")
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            if user_role != "admin":
                # Regular users can only see their own calls
                query["caller_user_id"] = user_id
            
            # Apply filters
            if filters.lead_id:
                query["lead_id"] = filters.lead_id
            
            if filters.user_id and user_role == "admin":
                query["caller_user_id"] = filters.user_id
            
            if filters.call_type:
                query["call_type"] = filters.call_type.value
            
            if filters.call_status:
                query["call_status"] = filters.call_status.value
            
            if filters.call_outcome:
                query["call_outcome"] = filters.call_outcome.value
            
            if filters.phone_number:
                query["destination_number"] = {"$regex": filters.phone_number, "$options": "i"}
            
            # Date range filtering
            if filters.date_from or filters.date_to:
                date_query = {}
                if filters.date_from:
                    date_query["$gte"] = filters.date_from
                if filters.date_to:
                    date_query["$lte"] = filters.date_to
                query["created_at"] = date_query
            
            # Duration filtering
            if filters.min_duration is not None or filters.max_duration is not None:
                duration_query = {}
                if filters.min_duration is not None:
                    duration_query["$gte"] = filters.min_duration
                if filters.max_duration is not None:
                    duration_query["$lte"] = filters.max_duration
                query["call_duration"] = duration_query
            
            # Get total count
            total_count = await db.call_logs.count_documents(query)
            
            # Calculate pagination
            page = max(1, filters.page)
            limit = min(filters.limit, self.max_page_size)
            skip = (page - 1) * limit
            total_pages = (total_count + limit - 1) // limit
            has_more = page < total_pages
            
            # Build sort criteria
            sort_criteria = []
            if filters.sort_by and filters.sort_order:
                sort_direction = 1 if filters.sort_order.lower() == "asc" else -1
                sort_criteria.append((filters.sort_by, sort_direction))
            else:
                sort_criteria.append(("created_at", -1))  # Default: newest first
            
            # Execute query
            cursor = db.call_logs.find(query).sort(sort_criteria).skip(skip).limit(limit)
            call_logs = await cursor.to_list(length=limit)
            
            # Enrich call logs with user and lead information
            enriched_logs = []
            for log in call_logs:
                enriched_log = await self._enrich_call_log(log)
                enriched_logs.append(CallLogResponse(**enriched_log))
            
            # Generate analytics for filtered data
            analytics = await self._generate_call_analytics(query)
            
            logger.info(f"Retrieved {len(enriched_logs)} call logs for user {user_id}")
            
            return CallHistoryResponse(
                calls=enriched_logs,
                total_count=total_count,
                page=page,
                limit=limit,
                total_pages=total_pages,
                has_more=has_more,
                analytics=analytics
            )
            
        except Exception as e:
            logger.error(f"Error getting call history: {str(e)}")
            raise Exception(f"Failed to retrieve call history: {str(e)}")

    async def get_call_by_id(
        self, 
        call_log_id: str,
        current_user: Dict[str, Any]
    ) -> CallLogResponse:
        """Get single call log by ID with permission checking"""
        try:
            db = self._get_db()
            if not db:
                raise Exception("Database not available")
                
            # Get call log
            call_log = await db.call_logs.find_one({"_id": ObjectId(call_log_id)})
            if not call_log:
                raise Exception("Call log not found")
            
            # Check permissions
            user_role = current_user.get("role", "user")
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            if user_role != "admin":
                # Regular users can only access their own calls
                if str(call_log.get("caller_user_id")) != user_id:
                    raise Exception("Not authorized to access this call log")
            
            # Enrich and return
            enriched_log = await self._enrich_call_log(call_log)
            return CallLogResponse(**enriched_log)
            
        except Exception as e:
            logger.error(f"Error getting call log {call_log_id}: {str(e)}")
            raise

    async def _generate_call_analytics(self, query: Dict[str, Any]) -> CallAnalytics:
        """Generate analytics for calls matching the query"""
        try:
            db = self._get_db()
            if not db:
                return CallAnalytics()
                
            # Aggregate pipeline for analytics
            pipeline = [
                {"$match": query},
                {
                    "$group": {
                        "_id": None,
                        "total_calls": {"$sum": 1},
                        "successful_calls": {
                            "$sum": {
                                "$cond": [
                                    {"$in": ["$call_outcome", ["successful", "interested", "meeting_scheduled"]]},
                                    1, 0
                                ]
                            }
                        },
                        "failed_calls": {
                            "$sum": {
                                "$cond": [
                                    {"$in": ["$call_status", ["failed", "busy", "no_answer", "timeout"]]},
                                    1, 0
                                ]
                            }
                        },
                        "total_duration": {"$sum": {"$ifNull": ["$call_duration", 0]}},
                        "avg_duration": {"$avg": {"$ifNull": ["$call_duration", 0]}},
                        
                        # Call type breakdown
                        "click_to_call_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_type", "click_to_call"]}, 1, 0]}
                        },
                        "support_call_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_type", "support_call"]}, 1, 0]}
                        },
                        "callback_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_type", "callback"]}, 1, 0]}
                        },
                        "progressive_dialer_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_type", "progressive_dialer"]}, 1, 0]}
                        },
                        
                        # Outcome breakdown
                        "interested_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_outcome", "interested"]}, 1, 0]}
                        },
                        "not_interested_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_outcome", "not_interested"]}, 1, 0]}
                        },
                        "no_response_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_outcome", "no_response"]}, 1, 0]}
                        },
                        "callback_requested_count": {
                            "$sum": {"$cond": [{"$eq": ["$call_outcome", "callback_requested"]}, 1, 0]}
                        },
                        
                        # 🆕 NEW: Tata-specific metrics
                        "tata_synced_count": {
                            "$sum": {"$cond": [{"$eq": ["$synced_from_tata", True]}, 1, 0]}
                        }
                    }
                }
            ]
            
            result = await db.call_logs.aggregate(pipeline).to_list(length=1)
            
            if result:
                stats = result[0]
                total_calls = stats.get("total_calls", 0)
                successful_calls = stats.get("successful_calls", 0)
                
                return CallAnalytics(
                    total_calls=total_calls,
                    successful_calls=successful_calls,
                    failed_calls=stats.get("failed_calls", 0),
                    average_duration=stats.get("avg_duration", 0.0),
                    total_duration=stats.get("total_duration", 0),
                    success_rate=(successful_calls / total_calls * 100) if total_calls > 0 else 0.0,
                    
                    # Type breakdown
                    click_to_call_count=stats.get("click_to_call_count", 0),
                    support_call_count=stats.get("support_call_count", 0),
                    callback_count=stats.get("callback_count", 0),
                    
                    # Outcome breakdown
                    interested_count=stats.get("interested_count", 0),
                    not_interested_count=stats.get("not_interested_count", 0),
                    no_response_count=stats.get("no_response_count", 0),
                    callback_requested_count=stats.get("callback_requested_count", 0)
                )
            else:
                return CallAnalytics()
                
        except Exception as e:
            logger.error(f"Error generating call analytics: {str(e)}")
            return CallAnalytics()

    # =============================================================================
    # ALL OTHER EXISTING METHODS REMAIN UNCHANGED...
    # (Preserving all your existing functionality)
    # =============================================================================

    async def get_call_summary_report(
        self, 
        start_date: datetime,
        end_date: datetime,
        current_user: Dict[str, Any],
        report_type: str = "custom"
    ) -> CallSummaryReport:
        """Generate comprehensive call summary report"""
        try:
            db = self._get_db()
            if not db:
                raise Exception("Database not available")
                
            # Build base query
            query = {
                "created_at": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
            
            # Apply user permissions
            user_role = current_user.get("role", "user")
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            if user_role != "admin":
                query["caller_user_id"] = user_id
            
            # Get basic metrics
            total_calls = await db.call_logs.count_documents(query)
            
            # Calculate total duration in hours
            duration_pipeline = [
                {"$match": query},
                {"$group": {"_id": None, "total_duration": {"$sum": {"$ifNull": ["$call_duration", 0]}}}}
            ]
            duration_result = await db.call_logs.aggregate(duration_pipeline).to_list(length=1)
            total_duration_seconds = duration_result[0].get("total_duration", 0) if duration_result else 0
            total_duration_hours = total_duration_seconds / 3600
            
            # Count unique leads and callers
            unique_leads = len(await db.call_logs.distinct("lead_id", query))
            unique_callers = len(await db.call_logs.distinct("caller_user_id", query))
            
            # Calculate success and conversion rates
            successful_calls = await db.call_logs.count_documents({
                **query,
                "call_outcome": {"$in": ["successful", "interested", "meeting_scheduled"]}
            })
            
            success_rate = (successful_calls / total_calls * 100) if total_calls > 0 else 0
            avg_duration = total_duration_seconds / total_calls if total_calls > 0 else 0
            
            # Status breakdown
            status_pipeline = [
                {"$match": query},
                {"$group": {"_id": "$call_status", "count": {"$sum": 1}}}
            ]
            status_results = await db.call_logs.aggregate(status_pipeline).to_list(length=None)
            status_breakdown = {result["_id"]: result["count"] for result in status_results}
            
            # Outcome breakdown
            outcome_pipeline = [
                {"$match": query},
                {"$group": {"_id": "$call_outcome", "count": {"$sum": 1}}}
            ]
            outcome_results = await db.call_logs.aggregate(outcome_pipeline).to_list(length=None)
            outcome_breakdown = {result["_id"]: result["count"] for result in outcome_results}
            
            # Type breakdown
            type_pipeline = [
                {"$match": query},
                {"$group": {"_id": "$call_type", "count": {"$sum": 1}}}
            ]
            type_results = await db.call_logs.aggregate(type_pipeline).to_list(length=None)
            type_breakdown = {result["_id"]: result["count"] for result in type_results}
            
            # Top callers (admin only)
            top_callers = []
            if user_role == "admin":
                caller_pipeline = [
                    {"$match": query},
                    {"$group": {
                        "_id": "$caller_user_id",
                        "total_calls": {"$sum": 1},
                        "successful_calls": {
                            "$sum": {"$cond": [
                                {"$in": ["$call_outcome", ["successful", "interested"]]}, 1, 0
                            ]}
                        }
                    }},
                    {"$sort": {"total_calls": -1}},
                    {"$limit": 10}
                ]
                caller_results = await db.call_logs.aggregate(caller_pipeline).to_list(length=None)
                
                # Enrich with user names
                for caller in caller_results:
                    user = await db.users.find_one({"_id": ObjectId(caller["_id"])})
                    top_callers.append({
                        "user_id": caller["_id"],
                        "user_name": user.get("full_name", "Unknown") if user else "Unknown",
                        "total_calls": caller["total_calls"],
                        "successful_calls": caller["successful_calls"],
                        "success_rate": (caller["successful_calls"] / caller["total_calls"] * 100) if caller["total_calls"] > 0 else 0
                    })
            
            # Daily breakdown
            daily_pipeline = [
                {"$match": query},
                {
                    "$group": {
                        "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                        "calls": {"$sum": 1},
                        "successful": {
                            "$sum": {"$cond": [
                                {"$in": ["$call_outcome", ["successful", "interested"]]}, 1, 0
                            ]}
                        }
                    }
                },
                {"$sort": {"_id": 1}}
            ]
            daily_results = await db.call_logs.aggregate(daily_pipeline).to_list(length=None)
            daily_call_trend = [
                {
                    "date": result["_id"],
                    "calls": result["calls"],
                    "successful": result["successful"],
                    "success_rate": (result["successful"] / result["calls"] * 100) if result["calls"] > 0 else 0
                }
                for result in daily_results
            ]
            
            return CallSummaryReport(
                report_period=report_type,
                start_date=start_date,
                end_date=end_date,
                total_calls=total_calls,
                total_duration_hours=round(total_duration_hours, 2),
                unique_leads_contacted=unique_leads,
                unique_callers=unique_callers,
                success_rate=round(success_rate, 2),
                average_call_duration=round(avg_duration / 60, 2),  # in minutes
                conversion_rate=round(success_rate, 2),  # Same as success rate for now
                status_breakdown=status_breakdown,
                outcome_breakdown=outcome_breakdown,
                type_breakdown=type_breakdown,
                top_callers=top_callers,
                busiest_hours=[],  # Could be implemented
                daily_call_trend=daily_call_trend,
                success_trend=daily_call_trend  # Using same data for now
            )
            
        except Exception as e:
            logger.error(f"Error generating call summary report: {str(e)}")
            raise

    async def schedule_callback(
        self, 
        callback_request: CallbackRequest,
        current_user: Dict[str, Any]
    ) -> CallbackResponse:
        """Schedule a callback for a lead"""
        try:
            db = self._get_db()
            if not db:
                raise Exception("Database not available")
                
            user_id = str(current_user.get("user_id") or current_user.get("_id"))
            
            # Check if lead exists and user has access
            lead = await db.leads.find_one({"lead_id": callback_request.lead_id})
            if not lead:
                raise Exception("Lead not found")
            
            # Check permissions
            user_role = current_user.get("role", "user")
            if user_role != "admin":
                lead_assigned_to = str(lead.get("assigned_to", ""))
                if lead_assigned_to != user_id:
                    raise Exception("Not authorized to schedule callback for this lead")
            
            # Create callback entry
            callback_data = {
                "_id": ObjectId(),
                "lead_id": callback_request.lead_id,
                "scheduled_at": callback_request.scheduled_at,
                "priority": callback_request.priority.value,
                "notes": callback_request.notes,
                "assigned_to": callback_request.assigned_to or user_id,
                "created_at": datetime.utcnow(),
                "created_by": user_id,
                "status": CallStatus.INITIATED.value,
                "is_overdue": False
            }
            
            # Insert callback
            result = await db.call_logs.insert_one({
                **callback_data,
                "caller_user_id": callback_request.assigned_to or user_id,
                "destination_number": lead.get("phone", ""),
                "call_type": CallType.CALLBACK.value,
                "call_priority": callback_request.priority.value,
                "call_status": CallStatus.INITIATED.value
            })
            
            callback_id = str(result.inserted_id)
            
            # Log activity to lead
            await db.lead_activities.insert_one({
                "_id": ObjectId(),
                "lead_id": callback_request.lead_id,
                "activity_type": "callback_scheduled",
                "description": f"Callback scheduled for {callback_request.scheduled_at.strftime('%Y-%m-%d %H:%M')}",
                "created_by": user_id,
                "created_at": datetime.utcnow(),
                "metadata": {
                    "callback_id": callback_id,
                    "scheduled_at": callback_request.scheduled_at.isoformat(),
                    "priority": callback_request.priority.value
                }
            })
            
            # Get user names for response
            created_by_user = await db.users.find_one({"_id": ObjectId(user_id)})
            assigned_to_user = None
            if callback_request.assigned_to:
                assigned_to_user = await db.users.find_one({"_id": ObjectId(callback_request.assigned_to)})
            
            logger.info(f"Scheduled callback {callback_id} for lead {callback_request.lead_id}")
            
            return CallbackResponse(
                id=callback_id,
                lead_id=callback_request.lead_id,
                lead_name=lead.get("name", lead.get("full_name")),
                scheduled_at=callback_request.scheduled_at,
                priority=callback_request.priority,
                notes=callback_request.notes,
                assigned_to=callback_request.assigned_to or user_id,
                assigned_to_name=assigned_to_user.get("full_name") if assigned_to_user else created_by_user.get("full_name"),
                status=CallStatus.INITIATED,
                created_at=datetime.utcnow(),
                created_by=user_id,
                created_by_name=created_by_user.get("full_name", "Unknown"),
                is_overdue=False
            )
            
        except Exception as e:
            logger.error(f"Error scheduling callback: {str(e)}")
            raise

    # ... (All other existing methods remain unchanged)
    # Including: get_upcoming_callbacks, export_call_data, cleanup_old_calls,
    # get_user_call_statistics, get_lead_call_history, update_callback_status,
    # search_calls, get_call_trends, get_performance_metrics, etc.

# Create singleton instance
call_log_service = CallLogService()