# app/routers/calls.py - CREATE THIS FILE

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Dict, Any, List
import logging
from datetime import datetime

from app.services.call_routing_service import call_routing_service
from app.utils.dependencies import get_current_active_user
from app.models.call import (
    CallRequest, 
    CallResponse, 
    CallHistoryItem, 
    UserCallingStatus,
    CallEndRequest
)
from app.config.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/make-call", response_model=Dict[str, Any])
async def make_call(
    call_request: CallRequest,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    🚀 TRIGGER ACTUAL CALL through TATA routing system
    Uses your existing call_routing_service.py with load balancing
    """
    try:
        user_email = current_user.get('email')
        logger.info(f"📞 Call request: {user_email} → {call_request.phone_number} (Lead: {call_request.lead_id})")
        
        # Check if user has calling capability
        db = get_database()
        user = await db.users.find_one({"email": user_email})
        
        if not user or not user.get("calling_enabled", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Calling not enabled for your account. Please contact administrator."
            )
        
        # Get TATA agent pool for this user
        agent_pool = await call_routing_service.get_tata_agent_pool()
        
        if not agent_pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No TATA agents available for routing. Please try again later."
            )
        
        # Select best agent using load balancing
        selected_agent_id = await call_routing_service._select_least_busy_agent(
            [str(agent["id"]) for agent in agent_pool],
            user_email
        )
        
        # Find agent details
        selected_agent = next(
            (agent for agent in agent_pool if str(agent["id"]) == selected_agent_id),
            None
        )
        
        if not selected_agent:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to select TATA agent for routing"
            )
        
        # Initiate call through TATA API
        call_result = await call_routing_service._initiate_routed_call(
            from_extension=selected_agent["eid"],
            to_number=call_request.phone_number,
            agent_id=selected_agent_id,
            user_id=user_email
        )
        
        # Log the call routing decision
        await call_routing_service._log_call_routing(
            user_id=user_email,
            agent_id=selected_agent_id,
            to_number=call_request.phone_number,
            call_result=call_result
        )
        
        if call_result.get("success"):
            return {
                "success": True,
                "message": "Call initiated successfully through TATA agent",
                "data": {
                    "call_id": call_result.get("call_id"),
                    "routed_agent": selected_agent_id,
                    "agent_name": selected_agent.get("name"),
                    "agent_extension": selected_agent.get("eid"),
                    "status": call_result.get("status", "connecting"),
                    "lead_id": call_request.lead_id,
                    "phone_number": call_request.phone_number,
                    "lead_name": call_request.lead_name
                },
                "routing_info": {
                    "method": "least_busy_agent",
                    "available_agents": len(agent_pool),
                    "selected_from": [agent["name"] for agent in agent_pool]
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"TATA call initiation failed: {call_result.get('error', 'Unknown error')}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Call initiation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Call initiation failed: {str(e)}"
        )

@router.get("/history", response_model=Dict[str, Any])
async def get_call_history(
    limit: int = Query(20, description="Number of calls to return"),
    offset: int = Query(0, description="Number of calls to skip"),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Get user's call history with pagination"""
    try:
        db = get_database()
        user_email = current_user.get('email')
        
        # Get call history for this user
        query = {"user_id": user_email}
        
        # Get total count
        total_calls = await db.call_routing_logs.count_documents(query)
        
        # Get paginated results
        calls_cursor = db.call_routing_logs.find(query).sort("created_at", -1).skip(offset).limit(limit)
        calls = await calls_cursor.to_list(None)
        
        # Format call history
        call_history = []
        for call in calls:
            call_history.append({
                "call_id": call.get("call_id", "N/A"),
                "phone_number": call.get("to_number"),
                "routed_agent": call.get("routed_agent"),
                "status": "completed" if call.get("call_success") else "failed",
                "created_at": call.get("created_at").isoformat() if call.get("created_at") else None,
                "notes": call.get("notes", "")
            })
        
        return {
            "success": True,
            "data": {
                "calls": call_history,
                "pagination": {
                    "total": total_calls,
                    "limit": limit,
                    "offset": offset,
                    "has_more": total_calls > (offset + limit)
                }
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get call history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get call history: {str(e)}"
        )

@router.get("/status", response_model=Dict[str, Any])
async def get_calling_status(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Get user's calling capability status and agent availability"""
    try:
        db = get_database()
        user_email = current_user.get('email')
        
        # Get user's calling setup
        user = await db.users.find_one({"email": user_email})
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Get current TATA agent pool
        agent_pool = await call_routing_service.get_tata_agent_pool()
        
        return {
            "success": True,
            "data": {
                "calling_enabled": user.get("calling_enabled", False),
                "routing_method": user.get("routing_method"),
                "calling_status": user.get("calling_status", "unknown"),
                "available_agents": len(agent_pool),
                "tata_agent_pool": user.get("tata_agent_pool", []),
                "agent_details": [
                    {
                        "id": agent["id"],
                        "name": agent["name"],
                        "extension": agent["eid"],
                        "status": "available"
                    }
                    for agent in agent_pool
                ],
                "setup_date": user.get("calling_setup_date"),
                "last_updated": user.get("updated_at")
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get calling status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get calling status: {str(e)}"
        )

@router.get("/agents", response_model=Dict[str, Any])
async def get_available_agents(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Get list of available TATA agents with their current status"""
    try:
        # Get fresh agent pool from TATA
        agent_pool = await call_routing_service.get_tata_agent_pool()
        
        if not agent_pool:
            return {
                "success": False,
                "message": "No TATA agents available",
                "data": {
                    "agents": [],
                    "total_agents": 0
                }
            }
        
        # Get recent call distribution for load balancing info
        db = get_database()
        
        # Get call counts for each agent in the last hour
        from datetime import timedelta
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        pipeline = [
            {"$match": {"created_at": {"$gte": one_hour_ago}}},
            {"$group": {"_id": "$routed_agent", "recent_calls": {"$sum": 1}}}
        ]
        
        recent_call_stats = await db.call_routing_logs.aggregate(pipeline).to_list(None)
        call_counts = {item["_id"]: item["recent_calls"] for item in recent_call_stats}
        
        # Format agent information
        agents_info = []
        for agent in agent_pool:
            agent_id = str(agent["id"])
            recent_calls = call_counts.get(agent_id, 0)
            
            agents_info.append({
                "id": agent_id,
                "name": agent["name"],
                "extension": agent["eid"],
                "recent_calls_last_hour": recent_calls,
                "status": "available",
                "load_level": "low" if recent_calls < 5 else "medium" if recent_calls < 15 else "high"
            })
        
        # Sort by recent calls (least busy first)
        agents_info.sort(key=lambda x: x["recent_calls_last_hour"])
        
        return {
            "success": True,
            "data": {
                "agents": agents_info,
                "total_agents": len(agents_info),
                "routing_method": "least_busy_agent",
                "next_agent": agents_info[0]["name"] if agents_info else None
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get agent status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent status: {str(e)}"
        )

@router.get("/test-connection")
async def test_tata_connection(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Test TATA Cloud Phone API connection"""
    try:
        # Test connection using existing service
        from app.services.smartflo_jwt_service import smartflo_jwt_service
        
        connection_result = await smartflo_jwt_service.test_connection()
        
        return {
            "success": connection_result.get("success", False),
            "data": connection_result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"TATA connection test failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }