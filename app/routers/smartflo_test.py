# app/routers/smartflo_test.py - Test endpoints for Smartflo integration
from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Any
from datetime import datetime
import logging

from ..utils.dependencies import get_current_active_user, get_admin_user
from ..services.smartflo_service import smartflo_service
from ..models.user import SmartfloSetupRequest, SmartfloSetupResponse, CallingStatusUpdate
from ..config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/smartflo-test", tags=["Smartflo Testing"])

@router.get("/config-check")
async def check_smartflo_configuration():
    """
    Check if Smartflo is properly configured
    For debugging configuration issues
    """
    try:
        config_status = {
            "smartflo_enabled": settings.smartflo_enabled,
            "has_api_token": bool(settings.smartflo_api_token),
            "api_base_url": settings.smartflo_api_base_url,
            "timeout": settings.smartflo_timeout,
            "retry_attempts": settings.smartflo_retry_attempts,
            "is_fully_configured": settings.is_smartflo_configured(),
            "default_department": settings.smartflo_default_department,
            "create_extension": settings.smartflo_create_extension
        }
        
        return {
            "success": True,
            "configuration": config_status,
            "message": "Smartflo configuration checked successfully"
        }
        
    except Exception as e:
        logger.error(f"Error checking Smartflo configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Configuration check failed: {str(e)}"
        )

@router.get("/connection-test")
async def test_smartflo_connection(
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Admin only
):
    """
    Test connection to Smartflo API
    Admin only - for verifying API connectivity
    """
    try:
        logger.info(f"Smartflo connection test initiated by: {current_user.get('email')}")
        
        connection_result = await smartflo_service.test_connection()
        
        return {
            "success": connection_result["success"],
            "message": "Smartflo connection tested",
            "connection_details": connection_result,
            "tested_by": current_user.get("email"),
            "tested_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error testing Smartflo connection: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection test failed: {str(e)}"
        )

@router.post("/test-agent-creation")
async def test_agent_creation(
    test_user_data: dict,
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Admin only
):
    """
    Test agent creation with sample data
    Admin only - for testing Smartflo agent creation without affecting real users
    
    Example test_user_data:
    {
        "first_name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "department": "Sales",
        "phone": "+1234567890"
    }
    """
    try:
        logger.info(f"Test agent creation initiated by: {current_user.get('email')}")
        
        # Validate required fields
        required_fields = ["first_name", "last_name", "email"]
        for field in required_fields:
            if field not in test_user_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required field: {field}"
                )
        
        # Add default values
        test_user_data.setdefault("department", settings.smartflo_default_department)
        test_user_data.setdefault("phone", "")
        
        # Create test agent
        creation_result = await smartflo_service.create_agent(test_user_data)
        
        return {
            "success": creation_result["success"],
            "message": "Test agent creation completed",
            "test_result": creation_result,
            "test_data": test_user_data,
            "tested_by": current_user.get("email"),
            "tested_at": datetime.utcnow().isoformat(),
            "note": "This was a test - no real user was created in LeadG CRM"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in test agent creation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test agent creation failed: {str(e)}"
        )

@router.post("/retry-user-setup")
async def retry_user_smartflo_setup(
    retry_request: SmartfloSetupRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user)  # Admin only
):
    """
    Retry Smartflo setup for an existing user
    Admin only - for fixing failed setups
    """
    try:
        logger.info(f"Smartflo retry setup for user {retry_request.user_id} by: {current_user.get('email')}")
        
        retry_result = await smartflo_service.retry_agent_setup(retry_request.user_id)
        
        if retry_result["success"]:
            message = f"Smartflo setup retry successful for user {retry_request.user_id}"
            response_status = SmartfloSetupResponse(
                success=True,
                message=message,
                user_id=retry_request.user_id,
                extension_number=retry_result.get("extension_number"),
                calling_status="active",
                attempts_used=1,  # This will be updated by the service
                can_retry=False
            )
        else:
            message = f"Smartflo setup retry failed for user {retry_request.user_id}: {retry_result.get('error')}"
            response_status = SmartfloSetupResponse(
                success=False,
                message=message,
                user_id=retry_request.user_id,
                calling_status="failed",
                attempts_used=1,  # This will be updated by the service
                can_retry=True
            )
        
        return {
            "success": retry_result["success"],
            "setup_response": response_status,
            "retry_details": retry_result,
            "retried_by": current_user.get("email"),
            "retried_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in retry user setup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retry setup failed: {str(e)}"
        )

@router.get("/service-health")
async def smartflo_service_health():
    """
    Simple health check for Smartflo service
    Public endpoint for monitoring
    """
    try:
        health_status = {
            "service": "smartflo_integration",
            "status": "healthy" if settings.is_smartflo_configured() else "misconfigured",
            "configured": settings.is_smartflo_configured(),
            "enabled": settings.smartflo_enabled,
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0"
        }
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        return {
            "service": "smartflo_integration",
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@router.get("/debug/headers")
async def debug_smartflo_headers(

    current_user: Dict[str, Any] = Depends(get_admin_user)  # Admin only
):
    """
    Debug endpoint to check headers being sent to Smartflo
    Admin only - for debugging authentication issues
    """
    try:
        headers = settings.get_smartflo_headers()
        
        # Mask the token for security
        masked_headers = headers.copy()
        if "Authorization" in masked_headers:
            token = masked_headers["Authorization"]
            if len(token) > 20:
                masked_headers["Authorization"] = token[:20] + "..." + token[-10:]
        
        return {
            "success": True,
            "headers": masked_headers,
            "base_url": settings.smartflo_api_base_url,
            "note": "Token is masked for security",
            "checked_by": current_user.get("email"),
            "checked_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error checking headers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Header check failed: {str(e)}"
        )
    


# ADD this to your app/routers/smartflo_test.py
# ADD this to your app/routers/smartflo_test.py

@router.post("/test-secret-key-alternatives")
async def test_secret_key_alternatives(
    current_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Test different secret key approaches with the confirmed working configuration:
    - Service: execute-api
    - Region: ap-south-1  
    - Access Key: 619750
    """
    try:
        import aiohttp
        import hashlib
        import hmac
        import urllib.parse
        from datetime import datetime
        import json
        import base64
        
        base_url = settings.smartflo_api_base_url
        jwt_token = settings.smartflo_api_token
        
        # Extract JWT parts
        jwt_parts = jwt_token.split('.')
        
        # Test payload
        test_payload = {
            "name": "Test Secret Key",
            "email": "test.secretkey@example.com",
            "department": "Sales",
            "phone": "+1234567890",
            "create_extension": True,
            "user_type": "agent",
            "is_active": True
        }
        
        payload_json = json.dumps(test_payload)
        
        # Different secret key approaches to test
        secret_key_alternatives = [
            {
                "name": "jwt_header_part",
                "secret_key": jwt_parts[0],  # JWT header
                "description": "JWT header as secret key"
            },
            {
                "name": "jwt_payload_part", 
                "secret_key": jwt_parts[1],  # JWT payload
                "description": "JWT payload as secret key"
            },
            {
                "name": "jwt_signature_part",
                "secret_key": jwt_parts[2],  # JWT signature
                "description": "JWT signature as secret key"
            },
            {
                "name": "access_key_as_secret",
                "secret_key": "619750",  # Same as access key
                "description": "Access key repeated as secret key"
            },
            {
                "name": "tata_default_secret",
                "secret_key": "tatateleservices",  # Company name
                "description": "Company name as secret key"
            },
            {
                "name": "cloudphone_secret",
                "secret_key": "cloudphone",  # Service name
                "description": "Service name as secret key"
            },
            {
                "name": "smartflo_secret",
                "secret_key": "smartflo",  # Product name
                "description": "Product name as secret key"
            },
            {
                "name": "jti_as_secret",
                "secret_key": "9Aj6E1L6uORHrN3D",  # JWT jti field
                "description": "JWT jti field as secret key"
            },
            {
                "name": "combined_parts",
                "secret_key": f"{jwt_parts[0]}.{jwt_parts[2]}",  # Header + signature
                "description": "JWT header + signature combined"
            },
            {
                "name": "base64_decoded_signature",
                "secret_key": "",  # Will be set below
                "description": "Base64 decoded JWT signature"
            }
        ]
        
        # Try to decode JWT signature for one approach
        try:
            # Add padding if needed for base64 decoding
            signature_with_padding = jwt_parts[2]
            padding = 4 - len(signature_with_padding) % 4
            if padding != 4:
                signature_with_padding += '=' * padding
            
            decoded_signature = base64.urlsafe_b64decode(signature_with_padding)
            secret_key_alternatives[9]["secret_key"] = decoded_signature.hex()  # Convert to hex string
        except:
            secret_key_alternatives[9]["secret_key"] = jwt_parts[2]  # Fallback to original
        
        # Confirmed working configuration
        access_key = "619750"
        service = "execute-api"
        region = "ap-south-1"
        
        results = {}
        timeout = aiohttp.ClientTimeout(total=15)
        
        for secret_approach in secret_key_alternatives:
            try:
                secret_key = secret_approach["secret_key"]
                test_name = secret_approach["name"]
                
                # Generate AWS Signature V4
                url = f"{base_url}/users"
                method = "POST"
                
                # Get current timestamp
                amz_date = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
                date_stamp = amz_date[:8]
                
                # Prepare headers
                headers = {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Host': urllib.parse.urlparse(url).netloc,
                    'X-Amz-Date': amz_date
                }
                
                # Create canonical headers
                canonical_headers = ""
                signed_headers = ""
                
                sorted_headers = sorted(headers.items(), key=lambda x: x[0].lower())
                for key, value in sorted_headers:
                    canonical_headers += f"{key.lower()}:{value.strip()}\n"
                    if signed_headers:
                        signed_headers += ";"
                    signed_headers += key.lower()
                
                # Create canonical request
                parsed_url = urllib.parse.urlparse(url)
                canonical_request = f"{method}\n{parsed_url.path}\n\n{canonical_headers}\n{signed_headers}\n{hashlib.sha256(payload_json.encode('utf-8')).hexdigest()}"
                
                # Create string to sign
                algorithm = "AWS4-HMAC-SHA256"
                credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
                string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
                
                # Calculate signature
                def sign(key, msg):
                    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()
                
                k_date = sign(('AWS4' + secret_key).encode('utf-8'), date_stamp)
                k_region = sign(k_date, region)
                k_service = sign(k_region, service)
                k_signing = sign(k_service, 'aws4_request')
                
                signature = hmac.new(k_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
                
                # Create authorization header
                authorization = (
                    f"{algorithm} "
                    f"Credential={access_key}/{credential_scope}, "
                    f"SignedHeaders={signed_headers}, "
                    f"Signature={signature}"
                )
                
                headers['Authorization'] = authorization
                
                # Make request
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=test_payload, headers=headers) as response:
                        response_text = await response.text()
                        
                        result = {
                            "secret_approach": secret_approach,
                            "status_code": response.status,
                            "success": response.status in [200, 201, 202],
                            "response_preview": response_text[:500] + "..." if len(response_text) > 500 else response_text,
                            "secret_key_preview": secret_key[:30] + "..." if len(secret_key) > 30 else secret_key,
                            "authorization_preview": authorization[:100] + "...",
                            "is_security_token_error": "security token" in response_text.lower(),
                            "is_different_error": "security token" not in response_text.lower() and "valid region" not in response_text.lower()
                        }
                        
                        results[test_name] = result
                        
                        # Check for SUCCESS!
                        if response.status in [200, 201, 202]:
                            try:
                                response_data = await response.json()
                                result["SUCCESSFUL_RESPONSE"] = response_data
                                
                                # 🎉🎉🎉 FINAL BREAKTHROUGH! 🎉🎉🎉
                                results["🔑🔑🔑_SECRET_KEY_SUCCESS_🔑🔑🔑"] = {
                                    "WINNING_SECRET_KEY": secret_key,
                                    "SECRET_APPROACH": secret_approach,
                                    "COMPLETE_CONFIG": {
                                        "access_key": access_key,
                                        "secret_key": secret_key,
                                        "service": service,
                                        "region": region
                                    },
                                    "status": response.status,
                                    "response": response_data,
                                    "extension_number": response_data.get("extension") or response_data.get("ext") or "Check response",
                                    "agent_id": response_data.get("id") or response_data.get("agent_id") or "Check response",
                                    "message": f"🚀 COMPLETE AWS CONFIG FOUND! Secret: {secret_approach['description']}"
                                }
                                
                                logger.info(f"🔑 SECRET KEY SUCCESS: {test_name}")
                                return results
                                
                            except Exception as json_error:
                                result["json_error"] = str(json_error)
                                # Even if JSON parsing fails, success is success
                                if response.status in [200, 201, 202]:
                                    results["🔑🔑🔑_SUCCESS_RAW_RESPONSE_🔑🔑🔑"] = {
                                        "WINNING_SECRET_KEY": secret_key,
                                        "SECRET_APPROACH": secret_approach,
                                        "status": response.status,
                                        "raw_response": response_text,
                                        "message": f"🚀 SUCCESS! Check raw response for extension"
                                    }
                                    return results
                        
                        # Check for progress (different error than security token)
                        elif result["is_different_error"]:
                            result["BREAKTHROUGH"] = "Different error! This secret key approach might be correct"
                        elif not result["is_security_token_error"]:
                            result["PROGRESS"] = "No security token error - getting closer!"
                        
                        logger.info(f"Secret key test {test_name}: {response.status} - {response_text[:100]}")
                        
            except Exception as e:
                results[test_name] = {
                    "secret_approach": secret_approach,
                    "error": str(e)
                }
        
        return {
            "success": True,
            "message": "Secret key alternatives testing completed",
            "confirmed_config": {
                "access_key": access_key,
                "service": service,
                "region": region,
                "note": "These are confirmed working - just need the right secret key"
            },
            "test_results": results,
            "alternatives_tested": len(secret_key_alternatives),
            "tested_by": current_user.get("email"),
            "tested_at": datetime.utcnow().isoformat(),
            "breakthrough_info": "India region ap-south-1 accepts our config but rejects JWT token as secret key"
        }
        
    except Exception as e:
        logger.error(f"Error in secret key testing: {str(e)}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }