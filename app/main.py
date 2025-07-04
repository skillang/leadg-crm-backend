# app/main.py - Updated with Smartflo Test Router
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import time

from .config.settings import settings
from .config.database import connect_to_mongo, close_mongo_connection
from .routers import auth, leads, tasks, notes, documents, timeline, contacts
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
    
    # 🚀 NEW: Log Smartflo configuration status on startup
    if settings.is_smartflo_configured():
        logger.info("📞 Smartflo integration is CONFIGURED and ENABLED")
        logger.info(f"📞 Smartflo API URL: {settings.smartflo_api_base_url}")
    else:
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

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to LeadG CRM API with Smartflo Calling Integration",
        "version": settings.version,
        "docs": "/docs" if settings.debug else "Docs disabled in production",
        "endpoints": {
            "auth": "/api/v1/auth",
            "leads": "/api/v1/leads",
            "tasks": "/api/v1/tasks",
            "notes": "/api/v1/notes",
            "documents": "/api/v1/documents",
            "timeline": "/api/v1",
            "contacts": "/api/v1/contacts",
            "smartflo_test": "/api/v1/smartflo-test",  # 🚀 NEW
            "health": "/health"
        },
        "smartflo": {
            "integration": "enabled" if settings.is_smartflo_configured() else "not_configured",
            "status": "Users will get automatic calling setup" if settings.is_smartflo_configured() else "Manual configuration required"
        }
    }

# Include routers
app.include_router(
    auth.router,
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

app.include_router(
    leads.router,
    prefix="/api/v1/leads",
    tags=["Leads"]
)

app.include_router(
    tasks.router,
    prefix="/api/v1/tasks",
    tags=["Tasks"]
)

app.include_router(
    notes.router,
    prefix="/api/v1/notes",
    tags=["Notes"]
)

app.include_router(
    documents.router,
    prefix="/api/v1/documents",
    tags=["Documents"]
)

app.include_router(
    timeline.router,
    prefix="/api/v1",
    tags=["Timeline"]
)

app.include_router(
    contacts.router,
    prefix="/api/v1/contacts",
    tags=["Contacts"]
)

# 🚀 NEW: Include Smartflo test router
app.include_router(
    smartflo_test.router,
    prefix="/api/v1",
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