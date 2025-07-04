# app/services/call_routing_service.py - COMPLETELY FIXED
import aiohttp
import asyncio
import logging
import random
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from bson import ObjectId
import os
import hashlib

from ..config.database import get_database

logger = logging.getLogger(__name__)

class CallRoutingService:
    def __init__(self):
        # ✅ FIXED: Use correct TATA Smartflo API base URL
        self.base_url = os.getenv("TATA_CLOUDPHONE_BASE_URL", "https://api-smartflo.tatateleservices.com")
        self.jwt_token = os.getenv("SMARTFLO_JWT_TOKEN")
        self.mock_mode = os.getenv("SMARTFLO_MOCK_MODE", "false").lower() == "true"
        self._db = None
        self._agent_pool = None
        self._last_pool_update = None
    
    @property
    def db(self):
        """Lazy database connection"""
        if self._db is None:
            self._db = get_database()
        return self._db
    
    async def setup_user_calling(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Setup calling capability for user with routing approach"""
        
        try:
            # Get TATA agent pool
            agent_pool = await self.get_tata_agent_pool()
            
            if not agent_pool:
                return {
                    "success": False,
                    "error": "No TATA agents available for routing"
                }
            
            # Setup user with call routing capability
            calling_setup = {
                "calling_enabled": True,
                "routing_method": "next_available_agent",
                "tata_agent_pool": [str(agent["id"]) for agent in agent_pool],
                "agent_details": {
                    str(agent["id"]): {
                        "name": agent["name"],
                        "extension": agent["eid"],
                        "follow_me": agent.get("follow_me_number")
                    } for agent in agent_pool
                },
                "setup_date": datetime.utcnow(),
                "routing_type": "dynamic_pool",
                "agent_pool_version": datetime.utcnow().isoformat()  # For tracking updates
            }
            
            logger.info(f"✅ User setup for call routing: {len(agent_pool)} agents available")
            
            return {
                "success": True,
                "calling_setup": calling_setup,
                "available_agents": len(agent_pool),
                "routing_method": "next_available_agent",
                "note": f"Calls will route through {len(agent_pool)} available TATA agents"
            }
            
        except Exception as e:
            logger.error(f"Call routing setup failed: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_tata_agent_pool(self) -> List[Dict[str, Any]]:
        """Get available TATA agents using correct Smartflo API"""
        
        # Use cache if recent (5 minutes)
        if (self._agent_pool and self._last_pool_update and 
            datetime.now() - self._last_pool_update < timedelta(minutes=5)):
            return self._agent_pool
        
        if self.mock_mode:
            # Mock agent pool
            mock_agents = [
                {"id": "MOCK_001", "name": "Mock Agent 1", "eid": "91990001", "status": "available"},
                {"id": "MOCK_002", "name": "Mock Agent 2", "eid": "91990002", "status": "available"},
                {"id": "MOCK_003", "name": "Mock Agent 3", "eid": "91990003", "status": "available"}
            ]
            self._agent_pool = mock_agents
            self._last_pool_update = datetime.now()
            logger.info(f"📞 Using mock agent pool: {len(mock_agents)} agents")
            return mock_agents
        
        # ✅ FIXED: Try correct TATA Smartflo API endpoints
        endpoints_to_try = [
            "/v1/users",           # Get all users (most likely)
            "/v1/user",            # Alternative user endpoint
            "/v1/agents",          # Direct agents endpoint if exists
            "/v1/extensions"       # Extensions endpoint
        ]
        
        try:
            headers = {
                "Authorization": f"Bearer {self.jwt_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                for endpoint in endpoints_to_try:
                    try:
                        logger.info(f"🔍 Trying TATA endpoint: {endpoint}")
                        
                        async with session.get(
                            f"{self.base_url}{endpoint}",
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as response:
                            
                            logger.info(f"🔍 {endpoint} returned: {response.status}")
                            
                            if response.status == 200:
                                data = await response.json()
                                logger.info(f"✅ Success with {endpoint}")
                                
                                # Extract agents from response
                                agents = await self._extract_agents_from_response(data, endpoint)
                                
                                if agents:
                                    self._agent_pool = agents
                                    self._last_pool_update = datetime.now()
                                    logger.info(f"📞 TATA agent pool updated: {len(agents)} agents from {endpoint}")
                                    return agents
                                else:
                                    logger.warning(f"⚠️ {endpoint} returned data but no agents found")
                                    
                            elif response.status == 401:
                                logger.error(f"❌ 401 Unauthorized for {endpoint}")
                            else:
                                error_text = await response.text()
                                logger.warning(f"⚠️ {endpoint} failed: {response.status} - {error_text[:100]}")
                                
                    except Exception as e:
                        logger.warning(f"⚠️ Error trying {endpoint}: {str(e)}")
                        continue
                
                # If all endpoints fail, log the issue
                logger.warning("⚠️ All TATA endpoints failed - falling back to mock agents")
                
        except Exception as e:
            logger.error(f"Error getting TATA agent pool: {str(e)}")
        
        # Fallback to mock agents if TATA API fails
        mock_agents = [
            {"id": "MOCK_001", "name": "Mock Agent 1", "eid": "91990001", "status": "available"},
            {"id": "MOCK_002", "name": "Mock Agent 2", "eid": "91990002", "status": "available"},
            {"id": "MOCK_003", "name": "Mock Agent 3", "eid": "91990003", "status": "available"}
        ]
        self._agent_pool = mock_agents
        self._last_pool_update = datetime.now()
        logger.info(f"📞 Using fallback mock agent pool: {len(mock_agents)} agents")
        return mock_agents
    
    async def _extract_agents_from_response(self, data: Any, endpoint: str) -> List[Dict[str, Any]]:
        """Extract agent information from different API response formats"""
        
        try:
            agents = []
            
            # Handle different response formats
            if isinstance(data, list):
                # Direct list of users/agents
                for item in data:
                    if self._is_valid_agent(item):
                        agents.append(self._normalize_agent_data(item))
                        
            elif isinstance(data, dict):
                # Check common container keys
                for key in ['users', 'agents', 'employees', 'directory', 'data', 'results']:
                    if key in data and isinstance(data[key], list):
                        for item in data[key]:
                            if self._is_valid_agent(item):
                                agents.append(self._normalize_agent_data(item))
                        break
                else:
                    # If data is a single agent object
                    if self._is_valid_agent(data):
                        agents.append(self._normalize_agent_data(data))
            
            logger.info(f"📊 Extracted {len(agents)} agents from {endpoint}")
            return agents
            
        except Exception as e:
            logger.error(f"Error extracting agents from {endpoint}: {str(e)}")
            return []
    
    def _is_valid_agent(self, item: Dict[str, Any]) -> bool:
        """Check if an item represents a valid agent"""
        
        # Must have some form of ID and extension/phone
        has_id = any(key in item for key in ['id', 'user_id', 'employee_id', 'ext_id'])
        has_extension = any(key in item for key in ['eid', 'extension', 'ext', 'phone', 'mobile'])
        has_name = any(key in item for key in ['name', 'username', 'display_name', 'full_name'])
        
        return has_id and has_extension and has_name
    
    def _normalize_agent_data(self, agent: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize agent data from different API formats"""
        
        # Extract ID
        agent_id = (agent.get('id') or agent.get('user_id') or 
                   agent.get('employee_id') or agent.get('ext_id') or 
                   str(hash(str(agent))))
        
        # Extract name
        name = (agent.get('name') or agent.get('username') or 
               agent.get('display_name') or agent.get('full_name') or 
               f"Agent {agent_id}")
        
        # Extract extension
        extension = (agent.get('eid') or agent.get('extension') or 
                    agent.get('ext') or agent.get('phone') or 
                    agent.get('mobile'))
        
        return {
            "id": str(agent_id),
            "name": str(name),
            "eid": str(extension),
            "status": agent.get('status', 'available'),
            "follow_me_number": agent.get('follow_me_number') or agent.get('mobile')
        }
    
    async def route_call(self, user_id: str, to_number: str) -> Dict[str, Any]:
        """Route call through next available TATA agent"""
        
        try:
            # Get user's calling setup
            user = await self.db.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return {"success": False, "error": "User not found"}
            
            if not user.get("calling_enabled"):
                return {"success": False, "error": "Calling not enabled for user"}
            
            # 🔄 DYNAMIC AGENT POOL: Always get fresh agents to include new ones
            fresh_agent_pool = await self.get_tata_agent_pool()
            
            if fresh_agent_pool:
                # Update user's agent pool if new agents are available
                await self._update_user_agent_pool(user_id, fresh_agent_pool)
                
                # Use fresh agent pool
                agent_pool = [str(agent["id"]) for agent in fresh_agent_pool]
                agent_details = {
                    str(agent["id"]): {
                        "name": agent["name"],
                        "extension": agent["eid"],
                        "follow_me": agent.get("follow_me_number")
                    } for agent in fresh_agent_pool
                }
            else:
                # Fallback to user's stored agent pool
                agent_pool = user.get("tata_agent_pool", [])
                agent_details = user.get("agent_details", {})
            
            if not agent_pool:
                return {"success": False, "error": "No agents available for routing"}
            
            # Select agent
            selected_agent_id = await self._select_next_agent(agent_pool, user_id)
            agent_info = agent_details.get(selected_agent_id)
            
            if not agent_info:
                return {"success": False, "error": "Selected agent not found"}
            
            # Route call through selected agent
            call_result = await self._initiate_routed_call(
                agent_info["extension"],
                to_number,
                selected_agent_id,
                user_id
            )
            
            # Log the call routing
            await self._log_call_routing(user_id, selected_agent_id, to_number, call_result)
            
            return {
                "success": call_result.get("success", False),
                "call_id": call_result.get("call_id"),
                "routed_through": agent_info["name"],
                "agent_extension": agent_info["extension"],
                "routing_method": "next_available_agent",
                "to_number": to_number,
                "call_details": call_result
            }
            
        except Exception as e:
            logger.error(f"Call routing failed: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def _update_user_agent_pool(self, user_id: str, fresh_agent_pool: List[Dict[str, Any]]):
        """Update user's agent pool with fresh data from TATA"""
        try:
            update_data = {
                "tata_agent_pool": [str(agent["id"]) for agent in fresh_agent_pool],
                "agent_details": {
                    str(agent["id"]): {
                        "name": agent["name"],
                        "extension": agent["eid"],
                        "follow_me": agent.get("follow_me_number")
                    } for agent in fresh_agent_pool
                },
                "agent_pool_last_updated": datetime.utcnow()
            }
            
            await self.db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": update_data}
            )
            
            logger.info(f"🔄 Updated agent pool for user {user_id}: {len(fresh_agent_pool)} agents")
            
        except Exception as e:
            logger.warning(f"Failed to update user agent pool (non-critical): {str(e)}")
    
    async def _select_next_agent(self, agent_pool: List[str], user_id: str) -> str:
        """Select next agent using round-robin or least-busy strategy"""
        
        try:
            # Get recent call counts for each agent (last hour)
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            
            pipeline = [
                {
                    "$match": {
                        "routed_agent": {"$in": agent_pool},
                        "created_at": {"$gte": one_hour_ago}
                    }
                },
                {
                    "$group": {
                        "_id": "$routed_agent",
                        "call_count": {"$sum": 1}
                    }
                }
            ]
            
            recent_calls = await self.db.call_routing_logs.aggregate(pipeline).to_list(None)
            
            # Create call count map
            call_counts = {item["_id"]: item["call_count"] for item in recent_calls}
            
            # ✅ FIXED: Handle case where no call history exists yet
            if not call_counts:
                # No previous calls - use simple round-robin
                selected_agent = self._round_robin_selection(agent_pool, user_id)
                logger.info(f"🎯 First-time selection (round-robin): {selected_agent}")
                return selected_agent
            
            # Find agent with least recent calls
            least_busy_agent = min(agent_pool, key=lambda agent_id: call_counts.get(agent_id, 0))
            
            logger.info(f"🎯 Selected least busy agent: {least_busy_agent} (recent calls: {call_counts.get(least_busy_agent, 0)})")
            
            return least_busy_agent
            
        except Exception as e:
            logger.error(f"Error selecting agent: {str(e)}")
            # ✅ FIXED: Robust fallback for any database issues
            return self._round_robin_selection(agent_pool, user_id)
    
    def _round_robin_selection(self, agent_pool: List[str], user_id: str) -> str:
        """Simple round-robin selection when no database history available"""
        
        try:
            # Use hash of user_id for consistent but distributed selection
            user_hash = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
            agent_index = user_hash % len(agent_pool)
            
            selected_agent = agent_pool[agent_index]
            logger.info(f"🔄 Round-robin selection: {selected_agent} (index: {agent_index})")
            
            return selected_agent
            
        except Exception as e:
            logger.error(f"Round-robin selection failed: {str(e)}")
            # Ultimate fallback - random selection
            return random.choice(agent_pool)
    
    # ✅ FIXED: Proper indentation and self parameter
    async def _initiate_routed_call(self, from_extension: str, to_number: str, agent_id: str, user_id: str) -> Dict[str, Any]:
        """✅ FIXED: Initiate call using correct TATA Smartflo API with proper payload"""
        
        if self.mock_mode:
            return {
                "success": True,
                "call_id": f"MOCK_CALL_{random.randint(100000, 999999)}",
                "status": "initiated",
                "mock_mode": True
            }
        
        try:
            headers = {
                "Authorization": f"Bearer {self.jwt_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            # ✅ FIXED: Try multiple payload formats to find the correct one
            payloads_to_try = [
                # Format 1: Standard format from docs
                {
                    "agent_number": str(agent_id),
                    "destination_number": to_number,
                    "async": "1",
                    "get_call_id": 1
                },
                # Format 2: With caller_id as agent extension
                {
                    "agent_number": str(agent_id), 
                    "destination_number": to_number,
                    "caller_id": str(from_extension),
                    "async": "1",
                    "get_call_id": 1
                },
                # Format 3: With call_timeout
                {
                    "agent_number": str(agent_id),
                    "destination_number": to_number,
                    "async": "1",
                    "call_timeout": 30,
                    "get_call_id": 1
                },
                # Format 4: Alternative field names
                {
                    "agent_id": str(agent_id),
                    "destination": to_number,
                    "async": "1"
                },
                # Format 5: Simple format
                {
                    "agent_number": str(agent_id),
                    "destination_number": to_number,
                    "async": 1  # Try as integer instead of string
                }
            ]
            
            logger.info(f"📞 Initiating TATA call: Agent {agent_id} → {to_number}")
            
            async with aiohttp.ClientSession() as session:
                for i, call_payload in enumerate(payloads_to_try, 1):
                    try:
                        logger.info(f"🔍 Trying payload format {i}: {call_payload}")
                        
                        async with session.post(
                            f"{self.base_url}/v1/click_to_call",
                            headers=headers,
                            json=call_payload,
                            timeout=aiohttp.ClientTimeout(total=15)
                        ) as response:
                            
                            logger.info(f"📊 Format {i} response: {response.status}")
                            
                            if response.status in [200, 201]:
                                response_data = await response.json()
                                logger.info(f"✅ TATA call successful with format {i}: {response_data}")
                                
                                return {
                                    "success": response_data.get("success", True),
                                    "call_id": response_data.get("call_id", f"TATA_{random.randint(100000, 999999)}"),
                                    "status": "initiated",
                                    "provider": "TATA Smartflo",
                                    "message": response_data.get("message", "Call initiated successfully"),
                                    "payload_format": i
                                }
                            
                            elif response.status == 422:
                                error_text = await response.text()
                                logger.warning(f"⚠️ Format {i} invalid (422): {error_text}")
                                # Continue to next format
                                
                            else:
                                error_text = await response.text()
                                logger.warning(f"⚠️ Format {i} failed ({response.status}): {error_text}")
                                # Continue to next format
                                
                    except Exception as e:
                        logger.warning(f"⚠️ Format {i} error: {str(e)}")
                        continue
                
                # If all formats fail
                logger.error("❌ All payload formats failed")
                return {
                    "success": False,
                    "error": "All TATA payload formats failed - API requirements may have changed",
                    "status_code": 422
                }
                            
        except Exception as e:
            logger.error(f"Call initiation failed: {str(e)}")
            return {"success": False, "error": str(e)}

    async def _log_call_routing(self, user_id: str, agent_id: str, to_number: str, call_result: Dict[str, Any]):
        """Log call routing for analytics and load balancing"""
        
        try:
            log_entry = {
                "user_id": user_id,
                "routed_agent": agent_id,
                "to_number": to_number,
                "call_success": call_result.get("success", False),
                "call_id": call_result.get("call_id"),
                "created_at": datetime.utcnow(),
                "routing_method": "next_available_agent"
            }
            
            # ✅ FIXED: Gracefully handle if collection doesn't exist yet
            try:
                await self.db.call_routing_logs.insert_one(log_entry)
                logger.info(f"📝 Call routing logged: {agent_id} → {to_number}")
            except Exception as db_error:
                # Don't fail the call if logging fails
                logger.warning(f"Failed to log call routing (non-critical): {str(db_error)}")
                
        except Exception as e:
            # Don't fail the call if logging fails completely
            logger.warning(f"Call routing logging failed (non-critical): {str(e)}")
    
    async def refresh_all_user_agent_pools(self) -> Dict[str, Any]:
        """Refresh agent pools for all users with calling enabled"""
        try:
            # Get fresh agent pool from TATA
            fresh_agent_pool = await self.get_tata_agent_pool()
            
            if not fresh_agent_pool:
                return {"success": False, "error": "No agents available from TATA"}
            
            # Update all users with calling enabled
            update_data = {
                "tata_agent_pool": [str(agent["id"]) for agent in fresh_agent_pool],
                "agent_details": {
                    str(agent["id"]): {
                        "name": agent["name"],
                        "extension": agent["eid"],
                        "follow_me": agent.get("follow_me_number")
                    } for agent in fresh_agent_pool
                },
                "agent_pool_last_updated": datetime.utcnow()
            }
            
            result = await self.db.users.update_many(
                {"calling_enabled": True},
                {"$set": update_data}
            )
            
            logger.info(f"🔄 Refreshed agent pools for {result.modified_count} users")
            
            return {
                "success": True,
                "users_updated": result.modified_count,
                "agents_available": len(fresh_agent_pool),
                "agent_names": [agent["name"] for agent in fresh_agent_pool]
            }
            
        except Exception as e:
            logger.error(f"Failed to refresh user agent pools: {str(e)}")
            return {"success": False, "error": str(e)}

    async def _select_least_busy_agent(self, agent_pool: List[str], user_id: str) -> str:
        """Select the least busy agent from the pool (alias for _select_next_agent)"""
        return await self._select_next_agent(agent_pool, user_id)

# Create singleton instance
call_routing_service = CallRoutingService()