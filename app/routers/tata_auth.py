# app/routers/tata_auth.py
# Tata Tele Authentication Router - Foundation for all Tata API operations

from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Any
import logging
from datetime import datetime

from ..services.tata_auth_service import tata_auth_service
from ..utils.dependencies import get_admin_user
from ..models.tata_integration import (
    TataLoginRequest, TataLoginResponse, TataTokenRefreshResponse,
    TataLogoutResponse, TataIntegrationHealth
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================================
# TATA AUTHENTICATION ENDPOINTS
# ============================================================================

@router.post("/login", response_model=TataLoginResponse)
async def login_to_tata(
    login_request: TataLoginRequest,
    current_user: dict = Depends(get_admin_user)  # Only admins can manage Tata auth
):
    """
    Login to Tata Tele API and store encrypted tokens
    
    - **Admin Only**: Only admin users can initiate Tata login
    - **Secure Storage**: Tokens are encrypted before storage
    - **Auto-refresh**: Tokens auto-refresh when needed
    """
    try:
        logger.info(f"Admin {current_user['email']} initiating Tata login")
        
        # Validate request
        if not login_request.email or not login_request.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email and password are required"
            )
        
        # Attempt login through service
        result = await tata_auth_service.login(
            email=login_request.email,
            password=login_request.password
        )
        
        if not result["success"]:
            logger.warning(f"Tata login failed for admin {current_user['email']}: {result['message']}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Tata login failed: {result['message']}"
            )
        
        logger.info(f"Tata login successful for admin {current_user['email']}")
        
        return TataLoginResponse(
            success=True,
            message="Successfully logged into Tata Tele API",
            access_token="***ENCRYPTED***",  # Don't expose actual token
            expires_at=result["expires_at"],
            login_time=datetime.utcnow()
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error in Tata login: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error during Tata login: {str(e)}"
        )

@router.post("/refresh", response_model=TataTokenRefreshResponse)
async def refresh_tata_token(
    current_user: dict = Depends(get_admin_user)  # Only admins can manage tokens
):
    """
    Refresh Tata Tele API access token
    
    - **Auto-refresh**: Automatically refreshes if token expires within 5 minutes
    - **Health Check**: Validates token health before refresh
    - **Error Recovery**: Attempts re-login if refresh fails
    """
    try:
        logger.info(f"Admin {current_user['email']} requesting Tata token refresh")
        
        # Attempt token refresh
        result = await tata_auth_service.refresh_token()
        
        if not result["success"]:
            logger.warning(f"Tata token refresh failed: {result['message']}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token refresh failed: {result['message']}"
            )
        
        logger.info(f"Tata token refresh successful for admin {current_user['email']}")
        
        return TataTokenRefreshResponse(
            success=True,
            message="Token refreshed successfully",
            expires_at=result["expires_at"],
            refresh_time=datetime.utcnow()
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error in Tata token refresh: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error during token refresh: {str(e)}"
        )

@router.post("/logout", response_model=TataLogoutResponse)
async def logout_from_tata(
    current_user: dict = Depends(get_admin_user)  # Only admins can manage auth
):
    """
    Logout from Tata Tele API and clear stored tokens
    
    - **Secure Cleanup**: Removes encrypted tokens from database
    - **API Logout**: Calls Tata API logout endpoint
    - **Audit Logging**: Logs logout event for security audit
    """
    try:
        logger.info(f"Admin {current_user['email']} initiating Tata logout")
        
        # Attempt logout through service
        result = await tata_auth_service.logout()
        
        if not result["success"]:
            logger.warning(f"Tata logout warning: {result['message']}")
            # Continue with local cleanup even if API logout fails
        
        logger.info(f"Tata logout completed for admin {current_user['email']}")
        
        return TataLogoutResponse(
            success=True,
            message="Successfully logged out from Tata Tele API",
            logout_time=datetime.utcnow()
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error in Tata logout: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error during Tata logout: {str(e)}"
        )

@router.get("/health", response_model=TataIntegrationHealth)
async def get_tata_integration_health(
    current_user: dict = Depends(get_admin_user)  # Only admins can check health
):
    """
    Get Tata Tele integration health status
    
    - **Token Status**: Checks if tokens are valid and not expired
    - **API Connectivity**: Tests connection to Tata API
    - **Service Health**: Overall integration health score
    - **Statistics**: Integration usage statistics
    """
    try:
        logger.info(f"Admin {current_user['email']} checking Tata integration health")
        
        # Get health status from service
        health_status = await tata_auth_service.get_health_status()
        
        return TataIntegrationHealth(
            is_authenticated=health_status["is_authenticated"],
            token_valid=health_status["token_valid"],
            token_expires_at=health_status.get("token_expires_at"),
            api_connectivity=health_status["api_connectivity"],
            last_successful_call=health_status.get("last_successful_call"),
            integration_status=health_status["integration_status"],
            health_score=health_status["health_score"],
            total_api_calls=health_status.get("total_api_calls", 0),
            failed_calls_24h=health_status.get("failed_calls_24h", 0),
            last_health_check=datetime.utcnow()
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error checking Tata health: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error checking integration health: {str(e)}"
        )

# ============================================================================
# INTERNAL STATUS ENDPOINTS (for debugging)
# ============================================================================

@router.get("/debug/token-status")
async def debug_token_status(
    current_user: dict = Depends(get_admin_user)  # Admin only for debugging
):
    """
    Debug endpoint to check current token status
    **Admin Only** - For debugging token issues
    """
    try:
        result = await tata_auth_service.check_token_status()
        
        # Mask sensitive information
        debug_info = {
            "has_token": result.get("has_token", False),
            "token_expired": result.get("token_expired", True),
            "expires_at": result.get("expires_at"),
            "time_until_expiry": result.get("time_until_expiry"),
            "needs_refresh": result.get("needs_refresh", True)
        }
        
        return {
            "success": True,
            "debug_info": debug_info,
            "checked_at": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Error in debug token status: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "checked_at": datetime.utcnow()
        }

# ============================================================================
# ROUTER METADATA
# ============================================================================

# Router tags and metadata for API documentation
router.tags = ["Tata Authentication"]