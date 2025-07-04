# app/routers/smartflo_test.py - UPDATED VERSION WITH FIXES
from fastapi import APIRouter, Depends, HTTPException, status 
from typing import Dict, Any
from datetime import datetime
import logging

# Fixed import - make sure this matches your file name exactly
from ..services.smartflo_jwt_service import smartflo_jwt_service
from ..utils.dependencies import get_current_active_user, get_admin_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/smartflo-test", tags=["Smartflo Testing"])

# =====================================================================
# BASIC HEALTH & DEBUG ENDPOINTS
# =====================================================================

@router.get("/health")
async def smartflo_service_health():
    """
    Health check for Smartflo service (No auth required)
    """
    try:
        import os
        
        return {
            "service": "Smartflo JWT Service",
            "status": "active",
            "jwt_configured": bool(os.getenv("SMARTFLO_JWT_TOKEN")),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "service": "Smartflo JWT Service",
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@router.get("/debug-env")
async def debug_environment(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Debug environment variables"""
    import os
    
    jwt_token = os.getenv("SMARTFLO_JWT_TOKEN")
    
    return {
        "environment_debug": {
            "SMARTFLO_JWT_TOKEN_EXISTS": bool(jwt_token),
            "SMARTFLO_JWT_TOKEN_LENGTH": len(jwt_token) if jwt_token else 0,
            "SMARTFLO_JWT_TOKEN_PREVIEW": jwt_token[:50] + "..." if jwt_token else "No token found",
            "SMARTFLO_MOCK_MODE": os.getenv("SMARTFLO_MOCK_MODE"),
            "TATA_CLOUDPHONE_BASE_URL": os.getenv("TATA_CLOUDPHONE_BASE_URL")
        },
        "tested_by": current_user.get("email"),
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/debug-connection")
async def debug_smartflo_connection(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Debug endpoint to check Smartflo configuration and connectivity
    """
    try:
        import os
        
        jwt_token = os.getenv("SMARTFLO_JWT_TOKEN")
        
        debug_info = {
            "jwt_token_configured": bool(jwt_token),
            "jwt_token_length": len(jwt_token) if jwt_token else 0,
            "jwt_token_preview": jwt_token[:20] + "..." if jwt_token else None,
            "base_url": smartflo_jwt_service.base_url,
            "service_initialized": True
        }
        
        # Test connection
        connection_test = await smartflo_jwt_service.test_connection()
        debug_info["connection_test"] = connection_test
        
        return {
            "success": True,
            "debug_info": debug_info,
            "tested_by": current_user.get("email"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Debug connection failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# =====================================================================
# CONNECTION & AUTHENTICATION TESTS
# =====================================================================

@router.get("/connection")
async def test_connection(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Simple connection test endpoint
    """
    try:
        connection_result = await smartflo_jwt_service.test_connection()
        return {
            "success": True,
            "connection_result": connection_result,
            "tested_by": current_user.get("email"),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Connection test failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "tested_by": current_user.get("email"),
            "timestamp": datetime.utcnow().isoformat()
        }

@router.post("/test-jwt-bearer")
async def test_jwt_bearer_auth(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Test JWT Bearer token authentication with Smartflo
    Admin only endpoint to verify Smartflo connectivity
    """
    try:
        logger.info(f"Testing Smartflo JWT Bearer connection for admin: {current_user.get('email')}")
        
        connection_result = await smartflo_jwt_service.test_connection()
        
        return {
            "success": True,
            "connection_result": connection_result,
            "note": "Uses existing JWT token directly as Bearer token",
            "tested_by": current_user.get("email"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"JWT Bearer test failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection test failed: {str(e)}"
        )

# =====================================================================
# AGENT MANAGEMENT TESTS
# =====================================================================

@router.get("/agents")
async def get_agents(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Get TATA agents list
    """
    try:
        from ..services.call_routing_service import call_routing_service
        
        agents = await call_routing_service.get_tata_agent_pool()
        
        return {
            "success": True,
            "agent_data": agents,
            "count": len(agents) if agents else 0,
            "tested_by": current_user.get("email"),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Get agents failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "tested_by": current_user.get("email"),
            "timestamp": datetime.utcnow().isoformat()
        }

@router.post("/test-jwt-agent-creation")
async def test_jwt_agent_creation(
    agent_data: Dict[str, str],
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Test agent creation in Smartflo using JWT Bearer token
    Creates a test agent and returns extension number
    """
    try:
        logger.info(f"Testing Smartflo agent creation for: {agent_data.get('email')}")
        
        # Create agent in Smartflo
        agent_result = await smartflo_jwt_service.create_agent(agent_data)
        
        if agent_result.get("success"):
            return {
                "success": True,
                "test_result": agent_result,
                "authentication_method": "Bearer JWT Token (your existing token)",
                "tested_by": current_user.get("email"),
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "success": False,
                "test_result": agent_result,
                "authentication_method": "Bearer JWT Token",
                "tested_by": current_user.get("email"),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Agent creation test failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent creation test failed: {str(e)}"
        )

# =====================================================================
# CALL TESTING
# =====================================================================

@router.post("/test-direct-call")
async def test_direct_call(
    call_data: Dict[str, str],
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Test making a direct call using Smartflo API
    """
    try:
        from_extension = call_data.get("from_extension")
        to_number = call_data.get("to_number")
        agent_id = call_data.get("agent_id")
        
        if not all([from_extension, to_number, agent_id]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required fields: from_extension, to_number, agent_id"
            )
        
        call_result = await smartflo_jwt_service.make_test_call(
            from_extension=from_extension,
            to_number=to_number,
            agent_id=agent_id
        )
        
        return {
            "success": call_result.get("success", False),
            "call_result": call_result,
            "tested_by": current_user.get("email"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Direct call test failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Call test failed: {str(e)}"
        )
    

@router.get("/debug-raw-env")
async def debug_raw_env():
    """Debug raw environment loading"""
    import os
    
    # Try different variations
    token1 = os.getenv("SMARTFLO_JWT_TOKEN")
    token2 = os.getenv("SMARTFLO_JWT_TOKEN ")  # with space
    token3 = os.getenv(" SMARTFLO_JWT_TOKEN")  # space at start
    
    return {
        "raw_debug": {
            "SMARTFLO_JWT_TOKEN": {
                "exists": token1 is not None,
                "length": len(token1) if token1 else 0,
                "value": token1[:50] + "..." if token1 else "None"
            },
            "with_trailing_space": {
                "exists": token2 is not None,
                "length": len(token2) if token2 else 0
            },
            "with_leading_space": {
                "exists": token3 is not None,
                "length": len(token3) if token3 else 0
            },
            "all_env_vars_containing_SMARTFLO": [
                key for key in os.environ.keys() if "SMARTFLO" in key.upper()
            ]
        }
    }