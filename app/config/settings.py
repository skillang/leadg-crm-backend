from pydantic_settings import BaseSettings
from typing import List
import secrets
import json
import os

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
    
    # Database
    mongodb_url: str = "mongodb://localhost:27017"
    database_name: str = "leadg_crm"
    
    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"  # Allow extra fields
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Override with environment variables if they exist
        if os.getenv("SECRET_KEY"):
            self.secret_key = os.getenv("SECRET_KEY")
        if os.getenv("DEBUG"):
            self.debug = os.getenv("DEBUG").lower() == "true"
    
    def get_allowed_origins(self) -> List[str]:
        """Get allowed origins from env or default"""
        origins_str = os.getenv("ALLOWED_ORIGINS", '["http://localhost:3000", "http://127.0.0.1:3000"]')
        try:
            return json.loads(origins_str)
        except:
            # Fallback: split by comma if not JSON
            return [origin.strip() for origin in origins_str.split(",")]

# Global settings instance
settings = Settings()