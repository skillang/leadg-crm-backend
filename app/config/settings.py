# app/config/settings.py - Updated with Email (ZeptoMail) configuration
from pydantic_settings import BaseSettings
from typing import List
import secrets
import json
import os
from dotenv import load_dotenv

# Load .env file before anything else
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
    
    # WhatsApp Business API Configuration
    whatsapp_base_url: str = "https://wa.mydreamstechnology.in/api"
    whatsapp_license_number: str = ""
    whatsapp_api_key: str = ""
    
    # CMS Configuration
    cms_base_url: str = "https://cms.skillang.com/api"
    cms_templates_endpoint: str = "whatsapp-templates"
    
    # 🆕 EMAIL CMS CONFIGURATION
    email_templates_endpoint: str = "mail-templates"  # Email-specific endpoint
    
    # 🆕 EMAIL CONFIGURATION (ZEPTOMAIL)
    zeptomail_url: str = "api.zeptomail.in/"
    zeptomail_token: str = ""
    max_bulk_recipients: int = 500
    email_rate_limit: int = 100
    min_schedule_minutes: int = 5
    max_schedule_days: int = 30
    
    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60
    
    # Email Configuration (SMTP - keep existing for backward compatibility)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@leadg.com"
    smtp_from_name: str = "LeadG CRM"
    
    # File Upload Configuration
    max_file_size: int = 10485760  # 10MB
    allowed_file_types: List[str] = ["image/jpeg", "image/png", "application/pdf", "text/csv"]
    upload_directory: str = "uploads/"
    
    # Redis Configuration (optional)
    redis_url: str = "redis://localhost:6379"
    redis_db: int = 0
    
    # Logging Configuration
    log_level: str = "INFO"
    log_file: str = "logs/app.log"
    
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"
    
    def __init__(self, **kwargs):
        # Reload .env again to ensure loading
        load_dotenv(override=True)
        
        super().__init__(**kwargs)
        
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
        if os.getenv("MONGODB_MIN_POOL_SIZE"):
            self.mongodb_min_pool_size = int(os.getenv("MONGODB_MIN_POOL_SIZE"))
        if os.getenv("MONGODB_MAX_IDLE_TIME_MS"):
            self.mongodb_max_idle_time_ms = int(os.getenv("MONGODB_MAX_IDLE_TIME_MS"))
        if os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS"):
            self.mongodb_server_selection_timeout_ms = int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS"))
        
        # WhatsApp configuration
        if os.getenv("WHATSAPP_BASE_URL"):
            self.whatsapp_base_url = os.getenv("WHATSAPP_BASE_URL")
        if os.getenv("WHATSAPP_LICENSE_NUMBER"):
            self.whatsapp_license_number = os.getenv("WHATSAPP_LICENSE_NUMBER")
        if os.getenv("WHATSAPP_API_KEY"):
            self.whatsapp_api_key = os.getenv("WHATSAPP_API_KEY")
        
        # CMS configuration
        if os.getenv("CMS_BASE_URL"):
            self.cms_base_url = os.getenv("CMS_BASE_URL")
        if os.getenv("CMS_TEMPLATES_ENDPOINT"):
            self.cms_templates_endpoint = os.getenv("CMS_TEMPLATES_ENDPOINT")
        
        # 🆕 EMAIL CMS CONFIGURATION
        if os.getenv("EMAIL_TEMPLATES_ENDPOINT"):
            self.email_templates_endpoint = os.getenv("EMAIL_TEMPLATES_ENDPOINT")
        
        # 🆕 ZEPTOMAIL EMAIL CONFIGURATION
        if os.getenv("ZEPTOMAIL_URL"):
            self.zeptomail_url = os.getenv("ZEPTOMAIL_URL")
        if os.getenv("ZEPTOMAIL_TOKEN"):
            self.zeptomail_token = os.getenv("ZEPTOMAIL_TOKEN")
        if os.getenv("MAX_BULK_RECIPIENTS"):
            self.max_bulk_recipients = int(os.getenv("MAX_BULK_RECIPIENTS"))
        if os.getenv("EMAIL_RATE_LIMIT"):
            self.email_rate_limit = int(os.getenv("EMAIL_RATE_LIMIT"))
        if os.getenv("MIN_SCHEDULE_MINUTES"):
            self.min_schedule_minutes = int(os.getenv("MIN_SCHEDULE_MINUTES"))
        if os.getenv("MAX_SCHEDULE_DAYS"):
            self.max_schedule_days = int(os.getenv("MAX_SCHEDULE_DAYS"))
        
        # Email configuration (existing SMTP)
        if os.getenv("SMTP_HOST"):
            self.smtp_host = os.getenv("SMTP_HOST")
        if os.getenv("SMTP_PORT"):
            self.smtp_port = int(os.getenv("SMTP_PORT"))
        if os.getenv("SMTP_USERNAME"):
            self.smtp_username = os.getenv("SMTP_USERNAME")
        if os.getenv("SMTP_PASSWORD"):
            self.smtp_password = os.getenv("SMTP_PASSWORD")
        if os.getenv("SMTP_FROM_EMAIL"):
            self.smtp_from_email = os.getenv("SMTP_FROM_EMAIL")
        if os.getenv("SMTP_FROM_NAME"):
            self.smtp_from_name = os.getenv("SMTP_FROM_NAME")
        
        # File upload configuration
        if os.getenv("MAX_FILE_SIZE"):
            self.max_file_size = int(os.getenv("MAX_FILE_SIZE"))
        if os.getenv("UPLOAD_DIRECTORY"):
            self.upload_directory = os.getenv("UPLOAD_DIRECTORY")
        if os.getenv("ALLOWED_FILE_TYPES"):
            try:
                self.allowed_file_types = json.loads(os.getenv("ALLOWED_FILE_TYPES"))
            except:
                pass
        
        # Server configuration
        if os.getenv("HOST"):
            self.host = os.getenv("HOST")
        if os.getenv("PORT"):
            self.port = int(os.getenv("PORT"))
        
        # Rate limiting
        if os.getenv("RATE_LIMIT_REQUESTS"):
            self.rate_limit_requests = int(os.getenv("RATE_LIMIT_REQUESTS"))
        if os.getenv("RATE_LIMIT_WINDOW"):
            self.rate_limit_window = int(os.getenv("RATE_LIMIT_WINDOW"))
        
        # Redis configuration
        if os.getenv("REDIS_URL"):
            self.redis_url = os.getenv("REDIS_URL")
        if os.getenv("REDIS_DB"):
            self.redis_db = int(os.getenv("REDIS_DB"))
        
        # Logging configuration
        if os.getenv("LOG_LEVEL"):
            self.log_level = os.getenv("LOG_LEVEL")
        if os.getenv("LOG_FILE"):
            self.log_file = os.getenv("LOG_FILE")
    
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
    
    def get_upload_path(self) -> str:
        """Get full upload directory path"""
        if not os.path.exists(self.upload_directory):
            os.makedirs(self.upload_directory, exist_ok=True)
        return self.upload_directory
    
    def is_email_configured(self) -> bool:
        """Check if email is properly configured"""
        return bool(self.smtp_username) and bool(self.smtp_password)
    
    # 🆕 NEW: ZeptoMail configuration helper
    def is_zeptomail_configured(self) -> bool:
        """Check if ZeptoMail is properly configured"""
        return bool(self.zeptomail_token) and bool(self.zeptomail_url)
    
    # 🆕 NEW: Get ZeptoMail configuration
    def get_zeptomail_config(self) -> dict:
        """Get ZeptoMail configuration dictionary"""
        return {
            "url": self.zeptomail_url,
            "token": self.zeptomail_token,
            "max_bulk_recipients": self.max_bulk_recipients,
            "rate_limit": self.email_rate_limit,
            "min_schedule_minutes": self.min_schedule_minutes,
            "max_schedule_days": self.max_schedule_days
        }
    
    def is_whatsapp_configured(self) -> bool:
        """Check if WhatsApp is properly configured"""
        return bool(self.whatsapp_license_number) and bool(self.whatsapp_api_key)
    
    def get_whatsapp_config(self) -> dict:
        """Get WhatsApp configuration dictionary"""
        return {
            "base_url": self.whatsapp_base_url,
            "license_number": self.whatsapp_license_number,
            "api_key": self.whatsapp_api_key
        }
    
    def get_cms_config(self) -> dict:
        """Get CMS configuration dictionary"""
        return {
            "base_url": self.cms_base_url,
            "templates_endpoint": self.cms_templates_endpoint
        }

# Global settings instance
settings = Settings()