# app/main.py - Updated with /v1 route prefix
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import time

from .config.settings import settings
from .config.database import connect_to_mongo, close_mongo_connection
from .routers import auth, leads, tasks, notes, documents, timeline, contacts, calls
# 🚀 NEW: Import Smartflo test router
from .routers import smartflo_test

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("🚀 Starting LeadG CRM API with Smartflo Integration...")
    await connect_to_mongo()
    
    # ✅ OPTIONAL: Create indexes programmatically on startup
    await create_database_indexes()
    
    # 🔍 ENHANCED DEBUG: Complete environment variable debugging
    import os
    logger.info("🔍 === ENVIRONMENT VARIABLE DEBUG ===")
    
    # Check if .env file exists
    env_file_exists = os.path.exists(".env")
    logger.info(f"🔍 .env file exists: {env_file_exists}")
    
    # Check all SMARTFLO environment variables
    smartflo_vars = {k: v for k, v in os.environ.items() if "SMARTFLO" in k}
    logger.info(f"🔍 SMARTFLO environment variables found: {len(smartflo_vars)}")
    for key, value in smartflo_vars.items():
        display_value = f"{value[:30]}..." if len(value) > 30 else value
        logger.info(f"🔍   {key} = {display_value}")
    
    # Direct environment variable checks
    jwt_token = os.getenv("SMARTFLO_JWT_TOKEN")
    mock_mode = os.getenv("SMARTFLO_MOCK_MODE")
    base_url = os.getenv("TATA_CLOUDPHONE_BASE_URL")
    enabled = os.getenv("SMARTFLO_ENABLED")
    
    logger.info(f"🔍 Direct checks:")
    logger.info(f"🔍   SMARTFLO_JWT_TOKEN: {'LOADED' if jwt_token else 'NOT FOUND'}")
    logger.info(f"🔍   SMARTFLO_MOCK_MODE: {mock_mode}")
    logger.info(f"🔍   TATA_CLOUDPHONE_BASE_URL: {base_url}")
    logger.info(f"🔍   SMARTFLO_ENABLED: {enabled}")
    
    if jwt_token:
        logger.info(f"🔍   Token length: {len(jwt_token)}")
        logger.info(f"🔍   Token preview: {jwt_token[:50]}...")
    
    # Check settings instance
    logger.info(f"🔍 Settings instance:")
    logger.info(f"🔍   settings.smartflo_api_token: {'LOADED' if settings.smartflo_api_token else 'EMPTY'}")
    logger.info(f"🔍   settings.smartflo_enabled: {settings.smartflo_enabled}")
    logger.info(f"🔍   settings.is_smartflo_configured(): {settings.is_smartflo_configured()}")
    
    logger.info("🔍 === END DEBUG ===")
    
    # 🚀 UPDATED: Use settings instance instead of direct env check
    if settings.is_smartflo_configured():
        logger.info("📞 SMARTFLO JWT TOKEN: LOADED ✅")
        logger.info(f"📞 TATA BASE URL: {base_url}")
        logger.info(f"📞 MOCK MODE: {mock_mode}")
        logger.info("📞 Smartflo integration is CONFIGURED and ENABLED")
        logger.info(f"📞 Smartflo API URL: {settings.smartflo_api_base_url}")
    else:
        logger.warning("⚠️ SMARTFLO JWT TOKEN: NOT FOUND ❌")
        logger.warning("⚠️ TATA integration will not work")
        logger.warning("⚠️ Smartflo integration is NOT properly configured")
        logger.warning("⚠️ User registration will work but without calling features")
    
    logger.info("✅ Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down LeadG CRM API...")
    await close_mongo_connection()
    logger.info("✅ Application shutdown complete")

async def create_database_indexes():
    """Create database indexes for optimal performance"""
    try:
        from .config.database import get_database
        db = get_database()
        
        logger.info("📊 Creating database indexes...")
        
        # 🚀 NEW: Smartflo-related indexes for users collection
        await db.users.create_index([("extension_number", 1)])
        await db.users.create_index([("smartflo_agent_id", 1)])
        await db.users.create_index([("calling_status", 1)])
        await db.users.create_index([("can_make_calls", 1)])
        
        # Documents indexes
        await db.lead_documents.create_index([("lead_id", 1), ("uploaded_at", -1)])
        await db.lead_documents.create_index([("uploaded_by", 1), ("uploaded_at", -1)])
        await db.lead_documents.create_index([("status", 1), ("document_type", 1)])
        await db.lead_documents.create_index([("is_active", 1)])
        
        # Lead activities indexes (if not already created)
        await db.lead_activities.create_index([("lead_id", 1), ("created_at", -1)])
        await db.lead_activities.create_index([("activity_type", 1), ("created_at", -1)])
        
        # Tasks indexes (if not already created)
        await db.lead_tasks.create_index([("lead_id", 1), ("created_at", -1)])
        await db.lead_tasks.create_index([("assigned_to", 1), ("due_datetime", 1)])
        await db.lead_tasks.create_index([("status", 1)])
        
        # Leads indexes (if not already created)
        await db.leads.create_index([("lead_id", 1)], unique=True)
        await db.leads.create_index([("assigned_to", 1), ("status", 1)])
        await db.leads.create_index([("created_at", -1)])
        
        # Notes indexes (if you have notes)
        await db.lead_notes.create_index([("lead_id", 1), ("created_at", -1)])
        await db.lead_notes.create_index([("tags", 1)])
        
        # Contacts indexes
        await db.lead_contacts.create_index([("lead_id", 1)])
        await db.lead_contacts.create_index([("created_by", 1)])
        await db.lead_contacts.create_index([("is_primary", 1)])
        await db.lead_contacts.create_index([("email", 1)])
        
        logger.info("✅ Database indexes created successfully")
        
    except Exception as e:
        logger.warning(f"⚠️ Failed to create some indexes: {e}")

# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="LeadG CRM - Customer Relationship Management API with Smartflo Calling Integration",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Add CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time to response headers"""
    start_time = time.time()
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        return response
    except Exception as e:
        logger.error(f"Request failed: {request.method} {request.url} - Error: {str(e)}", exc_info=True)
        raise

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "LeadG CRM API is running with Smartflo Integration",
        "version": settings.version,
        "modules": ["auth", "leads", "tasks", "notes", "documents", "timeline", "contacts"],
        "smartflo": {
            "enabled": settings.smartflo_enabled,
            "configured": settings.is_smartflo_configured()
        }
    }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to LeadG CRM API with TATA Cloud Phone Integration",
        "version": settings.version,
        "docs": "/docs" if settings.debug else "Docs disabled in production",
        "endpoints": {
            "auth": "/v1/auth",
            "leads": "/v1/leads",
            "tasks": "/v1/tasks", 
            "notes": "/v1/notes",
            "documents": "/v1/documents",
            "timeline": "/v1",
            "contacts": "/v1/contacts",
            "calls": "/v1/calls",
            "smartflo_test": "/v1/smartflo-test",
            "calling": "/v1/calling",
            "health": "/health"
        },
        "tata_integration": {
            "status": "enabled" if settings.is_smartflo_configured() else "not_configured",
            "calling_endpoints": [
                "POST /v1/calls/make-call",
                "GET /v1/calls/status", 
                "GET /v1/calls/history",
                "GET /v1/calls/agents"
            ]
        }
    }

# Include routers with /v1 prefix (removed /api)
app.include_router(
    auth.router,
    prefix="/v1/auth",
    tags=["Authentication"]
)

app.include_router(
    leads.router,
    prefix="/v1/leads",
    tags=["Leads"]
)

app.include_router(
    tasks.router,
    prefix="/v1/tasks",
    tags=["Tasks"]
)

app.include_router(
    notes.router,
    prefix="/v1/notes",
    tags=["Notes"]
)

app.include_router(
    documents.router,
    prefix="/v1/documents",
    tags=["Documents"]
)

app.include_router(
    timeline.router,
    prefix="/v1",
    tags=["Timeline"]
)

app.include_router(
    contacts.router,
    prefix="/v1/contacts",
    tags=["Contacts"]
)

app.include_router(
    calls.router,
    prefix="/v1/calls",
    tags=["Calls & TATA Integration"]
)

app.include_router(
    smartflo_test.router,
    prefix="/v1",
    tags=["Smartflo Testing"]
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )