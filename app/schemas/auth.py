from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any

class LoginRequest(BaseModel):
    """Login request schema"""
    email: EmailStr
    password: str
    remember_me: bool = False
    fcm_token: Optional[str] = None  

    class Config:
        json_schema_extra = {
            "example": {
                "email": "admin@leadg.com",
                "password": "SecurePass123",
                "remember_me": False
            }
        }

class LoginResponse(BaseModel):
    """Login response schema"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]

class RegisterResponse(BaseModel):
    """Register response schema"""
    success: bool
    message: str
    user: Dict[str, Any]

class RefreshTokenRequest(BaseModel):
    """Refresh token request schema"""
    refresh_token: str

class RefreshTokenResponse(BaseModel):
    """Refresh token response schema"""
    access_token: str
    refresh_token: str 
    token_type: str = "bearer"
    expires_in: int

class LogoutRequest(BaseModel):
    """Logout request schema"""
    refresh_token: Optional[str] = None

class AuthResponse(BaseModel):
    """Generic auth response schema"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None