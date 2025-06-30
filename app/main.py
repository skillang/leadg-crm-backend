from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import time


from .config.settings import settings
from .config.database import connect_to_mongo, close_mongo_connection
from .routers import auth, leads, tasks, notes, documents  # ✅ Added documents import
from app.routers import timeline
from app.routers import contacts  # Add this import

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more details
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("🚀 Starting LeadG CRM API...")
    await connect_to_mongo()
    
    # ✅ OPTIONAL: Create indexes programmatically on startup
    await create_database_indexes()
    
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
        await db.leads.create_index([("lead_id", 1)], unique=True)  # Unique lead_id
        await db.leads.create_index([("assigned_to", 1), ("status", 1)])
        await db.leads.create_index([("created_at", -1)])
        
        # Notes indexes (if you have notes)
        await db.lead_notes.create_index([("lead_id", 1), ("created_at", -1)])
        await db.lead_notes.create_index([("tags", 1)])
        
        logger.info("✅ Database indexes created successfully")
        
    except Exception as e:
        logger.warning(f"⚠️ Failed to create some indexes: {e}")
        # Don't fail startup if index creation fails

# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="LeadG CRM - Customer Relationship Management API with Documents Module",  # ✅ Updated description
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
        "message": "LeadG CRM API is running",
        "version": settings.version,
        "modules": ["auth", "leads", "tasks", "notes", "documents"]  # ✅ Added documents
    }

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to LeadG CRM API with Documents Module",  # ✅ Updated message
        "version": settings.version,
        "docs": "/docs" if settings.debug else "Docs disabled in production",
        "endpoints": {
            "auth": "/api/v1/auth",
            "leads": "/api/v1/leads",
            "tasks": "/api/v1/tasks",
            "notes": "/api/v1/notes",
            "documents": "/api/v1/documents",  # ✅ Added documents endpoint
            "health": "/health"
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

# ✅ NEW: Include documents router
app.include_router(
    documents.router,
    prefix="/api/v1/documents",
    tags=["Documents"]
)
app.include_router(
    timeline.router,
    prefix="/api/v1",
    tags=["timeline"]
    )
app.include_router(
    contacts.router,
    prefix="/api/v1/contacts",
    tags=["Contacts"]
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