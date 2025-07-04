# app/config/settings.py - Force .env loading
from pydantic_settings import BaseSettings
from typing import List
import secrets
import json
import os
from dotenv import load_dotenv

# 🔧 FORCE: Load .env file before anything else
load_dotenv(override=True)

class Settings(BaseSettings):
    # App Config
    app_name: str = "LeadG CRM API"
    version: str = "1.0.0"
    debug: bool = True
    
    # Security
    secret_key: str = "your-secret-key-here"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # MongoDB Atlas Configuration
    mongodb_url: str = "mongodb+srv://username:password@cluster.mongodb.net/database?retryWrites=true&w=majority"
    database_name: str = "leadg_crm"
    
    # MongoDB Atlas Connection Options
    mongodb_max_pool_size: int = 10
    mongodb_min_pool_size: int = 1
    mongodb_max_idle_time_ms: int = 30000
    mongodb_server_selection_timeout_ms: int = 5000
    mongodb_connect_timeout_ms: int = 10000
    mongodb_socket_timeout_ms: int = 10000
    
    # Smartflo API Configuration
    smartflo_enabled: bool = True
    smartflo_api_base_url: str = "https://api-smartflo.tatateleservices.com/v1"
    smartflo_api_token: str = ""
    smartflo_timeout: int = 30
    smartflo_retry_attempts: int = 3
    smartflo_retry_delay: int = 5
    smartflo_default_department: str = "Sales"
    smartflo_create_extension: bool = True
    
    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"
    
    def __init__(self, **kwargs):
        # 🔧 FORCE: Reload .env again to ensure loading
        load_dotenv(override=True)
        
        super().__init__(**kwargs)
        
        # 🔍 DEBUG: Print environment loading status
        print(f"🔍 INIT DEBUG - SMARTFLO_JWT_TOKEN found: {bool(os.getenv('SMARTFLO_JWT_TOKEN'))}")
        
        # Override with environment variables if they exist
        if os.getenv("SECRET_KEY"):
            self.secret_key = os.getenv("SECRET_KEY")
        if os.getenv("DEBUG"):
            self.debug = os.getenv("DEBUG").lower() == "true"
        
        # MongoDB Atlas environment variable handling
        if os.getenv("MONGODB_URL"):
            self.mongodb_url = os.getenv("MONGODB_URL")
        if os.getenv("DATABASE_NAME"):
            self.database_name = os.getenv("DATABASE_NAME")
        if os.getenv("MONGODB_MAX_POOL_SIZE"):
            self.mongodb_max_pool_size = int(os.getenv("MONGODB_MAX_POOL_SIZE"))
        
        # 🚀 SMARTFLO environment variable handling - FIXED
        if os.getenv("SMARTFLO_JWT_TOKEN"):
            self.smartflo_api_token = os.getenv("SMARTFLO_JWT_TOKEN")
            print(f"🔍 Successfully set smartflo_api_token: {bool(self.smartflo_api_token)}")
        else:
            print("🔍 SMARTFLO_JWT_TOKEN not found in environment")
            
        if os.getenv("SMARTFLO_ENABLED"):
            self.smartflo_enabled = os.getenv("SMARTFLO_ENABLED").lower() == "true"
        if os.getenv("SMARTFLO_API_BASE_URL"):
            self.smartflo_api_base_url = os.getenv("SMARTFLO_API_BASE_URL")
    
    def get_allowed_origins(self) -> List[str]:
        """Get allowed origins from env or default"""
        origins_str = os.getenv("ALLOWED_ORIGINS", '["http://localhost:3000", "http://127.0.0.1:3000"]')
        try:
            return json.loads(origins_str)
        except:
            return [origin.strip() for origin in origins_str.split(",")]
    
    def get_mongodb_connection_options(self) -> dict:
        """Get MongoDB Atlas connection options"""
        return {
            "maxPoolSize": self.mongodb_max_pool_size,
            "minPoolSize": self.mongodb_min_pool_size,
            "maxIdleTimeMS": self.mongodb_max_idle_time_ms,
            "serverSelectionTimeoutMS": self.mongodb_server_selection_timeout_ms,
            "connectTimeoutMS": self.mongodb_connect_timeout_ms,
            "socketTimeoutMS": self.mongodb_socket_timeout_ms,
            "retryWrites": True,
            "w": "majority"
        }
    
    def is_atlas_connection(self) -> bool:
        """Check if using MongoDB Atlas"""
        return "mongodb+srv://" in self.mongodb_url or "mongodb.net" in self.mongodb_url
    
    def get_smartflo_headers(self) -> dict:
        """Get Smartflo API headers"""
        return {
            "Authorization": f"Bearer {self.smartflo_api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def is_smartflo_configured(self) -> bool:
        """Check if Smartflo is properly configured"""
        return (
            self.smartflo_enabled and 
            bool(self.smartflo_api_token) and 
            bool(self.smartflo_api_base_url)
        )

# Global settings instance
settings = Settings()