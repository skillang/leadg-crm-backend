# app/services/call_routing_service.py - Final Updated Version
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
        self.base_url = os.getenv("TATA_CLOUDPHONE_BASE_URL", "https://cloudphone.tatateleservices.com")
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
        """Get available TATA agents for call routing"""
        
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
            return mock_agents
        
        try:
            headers = {
                "Authorization": f"Bearer {self.jwt_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/v1/agents",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    if response.status == 200:
                        agents = await response.json()
                        
                        # Filter for active agents
                        active_agents = [
                            agent for agent in agents 
                            if agent.get("eid")  # Has extension
                        ]
                        
                        self._agent_pool = active_agents
                        self._last_pool_update = datetime.now()
                        
                        logger.info(f"📞 TATA agent pool updated: {len(active_agents)} agents")
                        return active_agents
                    else:
                        logger.error(f"Failed to get TATA agents: {response.status}")
                        return []
        
        except Exception as e:
            logger.error(f"Error getting TATA agent pool: {str(e)}")
            return []
    
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
    
    async def _initiate_routed_call(self, from_extension: str, to_number: str, agent_id: str, user_id: str) -> Dict[str, Any]:
        """Initiate call through TATA API"""
        
        if self.mock_mode:
            # Mock call result
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
            
            call_payload = {
                "fromExtension": from_extension,
                "toNumber": to_number,
                "agentId": agent_id,
                "callType": "Outbound",
                "priority": "Normal",
                "originatingUser": user_id
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/v1/calls/initiate",
                    headers=headers,
                    json=call_payload,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    
                    if response.status in [200, 201]:
                        response_data = await response.json()
                        return {
                            "success": True,
                            "call_id": response_data.get("callId"),
                            "status": response_data.get("status"),
                            "provider": "TATA Cloud Phone"
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"TATA call failed: {error_text}",
                            "status_code": response.status
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

# Create singleton instance
call_routing_service = CallRoutingService()