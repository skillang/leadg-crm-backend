# app/main.py - Updated with permissions router
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import time

from .config.settings import settings
from app.utils.whatsapp_scheduler import start_whatsapp_scheduler, stop_whatsapp_scheduler
from .config.database import connect_to_mongo, close_mongo_connection
from .routers import auth, leads, tasks, notes, documents, timeline, contacts, lead_categories, stages, statuses, course_levels, sources, whatsapp, emails, permissions, tata_auth, tata_calls, call_logs, tata_users ,bulk_whatsapp  # 🆕 Added permissions

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("🚀 Starting LeadG CRM API...")
    await connect_to_mongo()
    
    # Setup default stages if none exist
    await setup_default_stages()
    logger.info("✅ Default stages setup completed")
    
    # Setup default statuses if none exist
    await setup_default_statuses()
    logger.info("✅ Default statuses setup completed")
    
    # 🆕 NEW: Check course levels collection (admin must create manually)
    await setup_default_course_levels()
    logger.info("✅ Course levels collection checked")
    
    # 🆕 NEW: Check sources collection (admin must create manually)
    await setup_default_sources()
    logger.info("✅ Sources collection checked")
    
    # 🆕 NEW: Check email configuration and start scheduler
    await check_email_configuration()
    logger.info("✅ Email configuration checked")
    
    # 🆕 NEW: Start email scheduler
    await start_email_scheduler()
    logger.info("✅ Email scheduler started")
    
    # 🆕 NEW: Initialize default permissions for existing users
    await initialize_user_permissions()
    logger.info("✅ User permissions initialized")
    
    logger.info("✅ Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down LeadG CRM API...")
    await close_mongo_connection()
    logger.info("✅ Application shutdown complete")

async def setup_default_stages():
    """Setup default stages on startup"""
    try:
        from .models.lead_stage import StageHelper
        
        created_count = await StageHelper.create_default_stages()
        if created_count:
            logger.info(f"Created {created_count} default stages")
        else:
            logger.info("Default stages already exist")
            
    except Exception as e:
        logger.warning(f"Error setting up default stages: {e}")

async def setup_default_statuses():
    """Setup default statuses on startup"""
    try:
        from .models.lead_status import StatusHelper
        
        created_count = await StatusHelper.create_default_statuses()
        if created_count:
            logger.info(f"Created {created_count} default statuses")
        else:
            logger.info("Default statuses already exist")
            
    except Exception as e:
        logger.warning(f"Error setting up default statuses: {e}")

# 🆕 NEW: Setup default course levels function
async def setup_default_course_levels():
    """Check course levels collection exists - admin must create all course levels manually"""
    try:
        from .config.database import get_database
        
        db = get_database()
        
        # Just check if collection exists, don't create any defaults
        existing_count = await db.course_levels.count_documents({})
        
        if existing_count == 0:
            logger.info("📚 Course levels collection empty - admin must create course levels manually")
        else:
            active_count = await db.course_levels.count_documents({"is_active": True})
            logger.info(f"📚 Course levels: {existing_count} total, {active_count} active")
            
    except Exception as e:
        logger.warning(f"Error checking course levels: {e}")

# 🆕 NEW: Setup default sources function
async def setup_default_sources():
    """Check sources collection exists - admin must create all sources manually"""
    try:
        from .config.database import get_database
        
        db = get_database()
        
        # Just check if collection exists, don't create any defaults
        existing_count = await db.sources.count_documents({})
        
        if existing_count == 0:
            logger.info("📍 Sources collection empty - admin must create sources manually")
        else:
            active_count = await db.sources.count_documents({"is_active": True})
            logger.info(f"📍 Sources: {existing_count} total, {active_count} active")
            
    except Exception as e:
        logger.warning(f"Error checking sources: {e}")

# 🆕 NEW: Start email scheduler function
async def start_email_scheduler():
    """Start the background email scheduler"""
    try:
        if settings.is_zeptomail_configured():
            from .services.email_scheduler import email_scheduler
            await email_scheduler.start_scheduler()
            logger.info("📧 Email scheduler started successfully")
        else:
            logger.info("📧 Email scheduler disabled - ZeptoMail not configured")
    except Exception as e:
        logger.warning(f"⚠️ Failed to start email scheduler: {e}")
        logger.info("📧 Email functionality will work without scheduling")

# 🆕 NEW: Check email configuration function
async def check_email_configuration():
    """Check email (ZeptoMail) configuration on startup"""
    try:
        if settings.is_zeptomail_configured():
            logger.info("📧 ZeptoMail configuration found - email functionality enabled")
            
            # Test connection in background (don't block startup)
            try:
                from .services.zepto_client import zepto_client
                test_result = await zepto_client.test_connection()
                if test_result["success"]:
                    logger.info("✅ ZeptoMail connection test successful")
                else:
                    logger.warning(f"⚠️ ZeptoMail connection test failed: {test_result.get('message')}")
            except Exception as e:
                logger.warning(f"⚠️ ZeptoMail connection test error: {e}")
        else:
            logger.warning("📧 ZeptoMail not configured - email functionality disabled")
            logger.info("   To enable emails: Set ZEPTOMAIL_URL and ZEPTOMAIL_TOKEN in .env")
            
    except Exception as e:
        logger.warning(f"Error checking email configuration: {e}")

# 🆕 NEW: Initialize user permissions function
async def initialize_user_permissions():
    """Initialize default permissions for existing users who don't have permissions field"""
    try:
        from .config.database import get_database
        
        db = get_database()
        
        # Find users without permissions field
        users_without_permissions = await db.users.count_documents({"permissions": {"$exists": False}})
        
        if users_without_permissions > 0:
            logger.info(f"🔒 Found {users_without_permissions} users without permissions field")
            
            # Add default permissions to users who don't have them
            result = await db.users.update_many(
                {"permissions": {"$exists": False}},
                {
                    "$set": {
                        "permissions": {
                            "can_create_single_lead": False,
                            "can_create_bulk_leads": False,
                            "granted_by": None,
                            "granted_at": None,
                            "last_modified_by": None,
                            "last_modified_at": None
                        }
                    }
                }
            )
            
            logger.info(f"🔒 Added default permissions to {result.modified_count} users")
        else:
            logger.info("🔒 All users already have permissions field")
            
    except Exception as e:
        logger.warning(f"Error initializing user permissions: {e}")

# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="LeadG CRM - Customer Relationship Management API with Email Functionality and Granular Permissions",  # 🔄 Updated description
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

@app.on_event("startup")
async def startup_event():
    await start_whatsapp_scheduler()

@app.on_event("shutdown") 
async def shutdown_event():
    await stop_whatsapp_scheduler()
    
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

# 🔄 UPDATED: Health check with permissions module
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "message": "LeadG CRM API is running",
        "version": settings.version,
        "modules": ["auth", "leads", "tasks", "notes", "documents", "timeline", "contacts", "stages", "statuses", "course-levels", "sources", "whatsapp", "emails", "permissions","tata-auth", "tata-calls", "call-logs", "tata-users"]  # 🆕 Added permissions

    }

# 🔄 UPDATED: Root endpoint with permissions endpoints
@app.get("/")
async def root():
    return {
        "message": "Welcome to LeadG CRM API",
        "version": settings.version,
        "docs": "/docs" if settings.debug else "Docs disabled in production",
        "endpoints": {
            "auth": "/auth",
            "leads": "/leads",
            "tasks": "/tasks", 
            "notes": "/notes",
            "documents": "/documents",
            "timeline": "",
            "contacts": "/contacts",
            "stages": "/stages",
            "statuses": "/statuses",
            "course-levels": "/course-levels",
            "sources": "/sources",
            "lead-categories": "/lead-categories",
            "whatsapp": "/whatsapp",
            "emails": "/emails",
            "permissions": "/permissions",  # 🆕 NEW
            "health": "/health"
        }
    }

# Include routers with specific prefixes
app.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"]
)

app.include_router(
    leads.router,
    prefix="/leads",
    tags=["Leads"]
)

app.include_router(
    tasks.router,
    prefix="/tasks",
    tags=["Tasks"]
)

app.include_router(
    notes.router,
    prefix="/notes",
    tags=["Notes"]
)

app.include_router(
    documents.router,
    prefix="/documents",
    tags=["Documents"]
)

app.include_router(
    timeline.router,
    prefix="",
    tags=["Timeline"]
)

app.include_router(
    contacts.router,
    prefix="/contacts",
    tags=["Contacts"]
)

app.include_router(
    lead_categories.router,
    prefix="/lead-categories",
    tags=["Lead Categories"]
)

# Add stages router
app.include_router(
    stages.router,
    prefix="/stages",
    tags=["Stages"]
)

# Add statuses router
app.include_router(
    statuses.router,
    prefix="/statuses",
    tags=["Statuses"]
)

# Add course levels router
app.include_router(
    course_levels.router,
    prefix="/course-levels",
    tags=["Course Levels"]
)

# Add sources router
app.include_router(
    sources.router,
    prefix="/sources",
    tags=["Sources"]
)

app.include_router(
    whatsapp.router,
    prefix="/whatsapp",
    tags=["WhatsApp"]
)

# Add emails router
app.include_router(
    emails.router,
    prefix="/emails",
    tags=["Emails"]
)

# 🆕 NEW: Add permissions router
app.include_router(
    permissions.router,
    prefix="/permissions",
    tags=["Permissions"]
)

app.include_router(
    tata_auth.router,
    prefix="/tata-auth",
    tags=["Tata Authentication"]
)

app.include_router(
    tata_calls.router,
    prefix="/tata-calls",
    tags=["Tata Calls"]
)

app.include_router(
    call_logs.router,
    prefix="/call-logs",
    tags=["Call Logs & Analytics"]
)

app.include_router(
    tata_users.router,
    prefix="/tata-users", 
    tags=["Tata User Sync"]
)
# Add this line with your existing router registrations
app.include_router(
    bulk_whatsapp.router,
    prefix="/bulk-whatsapp", 
    tags=["bulk-whatsapp"]
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