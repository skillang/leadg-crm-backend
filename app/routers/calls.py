# app/routers/calls.py - COMPLETE WORKING VERSION (Uses ONLY working call_routing_service)

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Dict, Any, List
import logging
import random
from datetime import datetime, timedelta
from ..utils.dependencies import get_current_active_user
from ..models.call import (
    CallRequest, 
    CallResponse, 
    CallHistoryItem, 
    UserCallingStatus,
    CallEndRequest
)
from ..config.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter()
# Replace your make_call function with this ENHANCED version:

@router.post("/make-call")
async def make_call(
    call_data: CallRequest,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Enhanced Agent-Mediated Calling 
    Uses working TATA agent routing with better UX
    """
    try:
        from ..services.call_routing_service import call_routing_service
        
        logger.info(f"📞 Agent-mediated call: {current_user.get('email')} → {call_data.phone_number} (Lead: {call_data.lead_id})")
        
        # Get user's phone number for instructions
        user_phone = current_user.get("phone")
        if not user_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User phone number not configured. Please update your profile."
            )
        
        # Verify lead exists
        db = get_database()
        lead = await db.leads.find_one({"lead_id": call_data.lead_id})
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found"
            )
        
        # Use the WORKING agent routing (exactly what created TATA_227402)
        call_result = await call_routing_service.route_call(
            user_id=str(current_user["_id"]),
            to_number=call_data.phone_number
        )
        
        if call_result.get("success"):
            logger.info(f"✅ Agent-mediated call successful: {call_result.get('call_id')}")
            
            # Extract agent info for better UX
            routed_agent = call_result.get("routed_through", "TATA Agent")
            agent_extension = call_result.get("agent_extension", "Available")
            
            return CallResponse(
                success=True,
                message=f"📞 Call initiated via {routed_agent}! Your phone ({user_phone}) will ring first.",
                data={
                    "call_id": call_result.get("call_id"),
                    "call_type": "agent_mediated",
                    "routing_info": {
                        "your_phone": user_phone,
                        "customer_phone": call_data.phone_number,
                        "routed_through": routed_agent,
                        "agent_extension": agent_extension,
                        "routing_method": call_result.get("routing_method")
                    },
                    "lead_info": {
                        "lead_id": call_data.lead_id,
                        "lead_name": call_data.lead_name or lead.get("first_name", "Unknown"),
                        "company": lead.get("company")
                    },
                    "call_flow": {
                        "step_1": f"🤖 TATA Agent ({routed_agent}) receives call request",
                        "step_2": f"📱 Your phone ({user_phone}) will ring in ~5-10 seconds",
                        "step_3": f"✅ Answer your phone to proceed",
                        "step_4": f"📞 Customer ({call_data.phone_number}) will be called automatically",
                        "step_5": f"🗣️ Direct conversation with {call_data.lead_name or 'customer'}"
                    },
                    "status": "initiated",
                    "provider": "TATA Cloud Phone",
                    "instructions": f"📱 Watch for incoming call on {user_phone} - Answer it to connect with {call_data.lead_name or 'the customer'}!"
                }
            )
        else:
            error_msg = call_result.get("error", "Unknown error")
            logger.error(f"❌ Agent-mediated call failed: {error_msg}")
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Call initiation failed: {error_msg}. The TATA agent routing system encountered an issue."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent-mediated call failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Call system error: {str(e)}"
        )

@router.get("/history")
async def get_call_history(
    limit: int = 50,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Get call history for current user"""
    try:
        db = get_database()
        user_id = str(current_user["_id"])
        
        # Get direct calls from call routing logs (includes both agent routing and direct calls)
        calls = await db.call_routing_logs.find(
            {
                "$or": [
                    {"user_id": user_id},
                    {"routed_agent": current_user.get("phone")}  # Calls where user's phone was the "agent"
                ]
            }
        ).sort("created_at", -1).limit(limit).to_list(None)
        
        # Convert ObjectId to string for JSON serialization
        for call in calls:
            call["_id"] = str(call["_id"])
            
            # Add time ago
            if call.get("created_at"):
                time_diff = datetime.utcnow() - call["created_at"]
                if time_diff.days > 0:
                    call["time_ago"] = f"{time_diff.days}d ago"
                elif time_diff.seconds > 3600:
                    call["time_ago"] = f"{time_diff.seconds // 3600}h ago"
                else:
                    call["time_ago"] = f"{time_diff.seconds // 60}m ago"
        
        return {
            "success": True,
            "calls": calls,
            "total": len(calls),
            "user": current_user.get("email"),
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Failed to get call history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get call history: {str(e)}"
        )

@router.get("/test-direct-call")
async def test_direct_call(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Test endpoint to check user's phone configuration"""
    try:
        from ..services.call_routing_service import call_routing_service
        
        user_phone = current_user.get("phone")
        
        return {
            "success": True,
            "user_email": current_user.get("email"),
            "user_phone": user_phone,
            "calling_enabled": bool(user_phone),
            "message": "Ready for direct calling" if user_phone else "Please add phone number to your profile",
            "mock_mode": call_routing_service.mock_mode,
            "tata_connection": "Available" if call_routing_service.jwt_token else "Not configured"
        }
        
    except Exception as e:
        logger.error(f"Test direct call failed: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

@router.get("/status")
async def get_calling_status(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Get user's calling capability status and agent availability"""
    try:
        from ..services.call_routing_service import call_routing_service
        
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
                "calling_enabled": bool(user.get("phone")),  # Based on phone number availability
                "user_phone": user.get("phone"),
                "routing_method": "direct_user_calling",
                "calling_status": "active" if user.get("phone") else "phone_required",
                "available_agents": len(agent_pool),
                "tata_connection": "connected" if agent_pool else "disconnected",
                "agent_details": [
                    {
                        "id": agent.get("id"),
                        "name": agent.get("name"),
                        "extension": agent.get("eid"),
                        "status": "available"
                    }
                    for agent in agent_pool
                ] if agent_pool else [],
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

@router.get("/agents")
async def get_available_agents(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Get list of available TATA agents (for reference/debugging)"""
    try:
        from ..services.call_routing_service import call_routing_service
        
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
        
        # Format agent information
        agents_info = []
        for agent in agent_pool:
            agents_info.append({
                "id": agent.get("id"),
                "name": agent.get("name"),
                "extension": agent.get("eid"),
                "status": "available"
            })
        
        return {
            "success": True,
            "data": {
                "agents": agents_info,
                "total_agents": len(agents_info),
                "note": "These agents are available for routing, but direct calling uses your phone number"
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
        from ..services.call_routing_service import call_routing_service
        
        # Test by getting agent pool
        agent_pool = await call_routing_service.get_tata_agent_pool()
        
        if agent_pool:
            return {
                "success": True,
                "data": {
                    "connection": "successful",
                    "agents_found": len(agent_pool),
                    "base_url": call_routing_service.base_url,
                    "mock_mode": call_routing_service.mock_mode,
                    "authentication": "Bearer JWT - Working"
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "success": False,
                "data": {
                    "connection": "failed",
                    "error": "No agents found",
                    "base_url": call_routing_service.base_url,
                    "mock_mode": call_routing_service.mock_mode
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        
    except Exception as e:
        logger.error(f"TATA connection test failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# Helper function for direct phone-to-phone calling
async def _make_direct_phone_call(from_phone: str, to_phone: str, user_id: str) -> Dict[str, Any]:
    """Make direct phone-to-phone call using TATA format for external numbers"""
    try:
        from ..services.call_routing_service import call_routing_service
        
        # Clean phone numbers for TATA (remove + and country code for Indian numbers)
        clean_from = from_phone.replace("+91-", "").replace("+91", "").replace("-", "")
        clean_to = to_phone.replace("+91-", "").replace("+91", "").replace("-", "")
        
        logger.info(f"📡 Direct phone call: {clean_from} → {clean_to}")
        
        headers = {
            "Authorization": f"Bearer {call_routing_service.jwt_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Try direct calling payload format
        call_payload = {
            'from_number': clean_from,     # Clean 10-digit number
            'to_number': clean_to,         # Clean 10-digit number  
            'async': 1
        }
        
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{call_routing_service.base_url}/api/v1/click-to-call",
                headers=headers,
                json=call_payload,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                
                if response.status == 200:
                    response_data = await response.json()
                    call_id = f"DIRECT_{response_data.get('call_id', '123456')}"
                    
                    return {
                        "success": True,
                        "call_id": call_id,
                        "status": "initiated",
                        "provider": "TATA Cloud Phone"
                    }
                else:
                    # If direct format fails, try alternative formats
                    return await _try_alternative_direct_formats(
                        from_phone, to_phone, user_id, headers, call_routing_service
                    )
                    
    except Exception as e:
        logger.error(f"Direct phone call failed: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

async def _try_alternative_direct_formats(from_phone: str, to_phone: str, user_id: str, 
                                        headers: dict, call_routing_service) -> Dict[str, Any]:
    """Try alternative TATA formats for direct calling"""
    
    # Clean numbers
    clean_from = from_phone.replace("+91-", "").replace("+91", "").replace("-", "")
    clean_to = to_phone.replace("+91-", "").replace("+91", "").replace("-", "")
    
    # Alternative payload formats for direct calling
    formats = [
        {
            'caller': clean_from,
            'callee': clean_to,
            'async': 1
        },
        {
            'source': clean_from,
            'destination': clean_to,
            'async': 1
        },
        {
            'from': clean_from,
            'to': clean_to,
            'call_type': 'direct'
        },
        {
            'originator': clean_from,
            'target': clean_to,
            'async': 1
        }
    ]
    
    import aiohttp
    for i, payload in enumerate(formats):
        try:
            logger.info(f"🔍 Trying direct format {i+1}: {payload}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{call_routing_service.base_url}/api/v1/click-to-call",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    if response.status == 200:
                        response_data = await response.json()
                        call_id = f"DIRECT_{response_data.get('call_id', f'ALT{i+1}_123456')}"
                        
                        logger.info(f"✅ Direct format {i+1} successful!")
                        
                        return {
                            "success": True,
                            "call_id": call_id,
                            "status": "initiated",
                            "provider": "TATA Cloud Phone",
                            "format_used": i+1
                        }
                    else:
                        error_text = await response.text()
                        logger.info(f"❌ Direct format {i+1} failed: {response.status}")
                        
        except Exception as e:
            logger.info(f"❌ Direct format {i+1} error: {str(e)}")
            
    return {
        "success": False,
        "error": "All direct calling formats failed"
    }

# Helper function for logging direct calls
async def _log_direct_call(call_id: str, user_id: str, user_email: str, 
                          user_phone: str, customer_phone: str, lead_id: str, 
                          lead_name: str, status: str):
    """Log direct call details for tracking"""
    try:
        db = get_database()
        
        call_log = {
            "user_id": user_id,
            "routed_agent": user_phone,  # User's phone as "agent"
            "to_number": customer_phone,
            "call_success": True,
            "call_id": call_id,
            "created_at": datetime.utcnow(),
            "routing_method": "direct_user_calling",
            # Additional fields for direct calling
            "call_type": "direct_user_call",
            "user_email": user_email,
            "user_phone": user_phone,
            "lead_id": lead_id,
            "lead_name": lead_name,
            "status": status,
            "provider": "TATA Cloud Phone",
            "call_direction": "outbound"
        }
        
        await db.call_routing_logs.insert_one(call_log)
        logger.info(f"📝 Direct call logged: {call_id} ({user_email} → {customer_phone})")
        
    except Exception as e:
        # Don't fail the call if logging fails
        logger.warning(f"Direct call logging failed (non-critical): {str(e)}")

# Debug endpoints for troubleshooting
@router.get("/debug/user-phone")
async def debug_user_phone(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Debug endpoint to check user phone configuration"""
    return {
        "user_id": str(current_user["_id"]),
        "email": current_user.get("email"),
        "phone": current_user.get("phone"),
        "calling_ready": bool(current_user.get("phone")),
        "all_user_fields": list(current_user.keys())
    }

@router.get("/debug/test-working-routing")
async def debug_test_working_routing(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Test the original working agent routing for comparison"""
    try:
        from ..services.call_routing_service import call_routing_service
        
        # Test original route_call method
        call_result = await call_routing_service.route_call(
            user_id=str(current_user["_id"]),
            to_number="+91-1234567890"  # Test number
        )
        
        return {
            "success": True,
            "message": "Testing original working routing (not a real call)",
            "result": call_result,
            "note": "This tests the working agent routing method for comparison"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "note": "Original routing test failed"
        }