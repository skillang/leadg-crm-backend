# app/main.py - Cleaned version without Smartflo/TATA integration
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import time

from .config.settings import settings
from .config.database import connect_to_mongo, close_mongo_connection
from .routers import auth, leads, tasks, notes, documents, timeline, contacts ,lead_categories


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
    
    # ✅ Indexes are already created in database.py connection
    
    logger.info("✅ Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down LeadG CRM API...")
    await close_mongo_connection()
    logger.info("✅ Application shutdown complete")

# Note: Database indexes are created automatically in app/config/database.py

# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="LeadG CRM - Customer Relationship Management API",
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
        "modules": ["auth", "leads", "tasks", "notes", "documents", "timeline", "contacts"]
    }

@app.get("/")
async def root():
    """Root endpoint"""
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
            "health": "/health"
        }
    }

# Include routers with /v1 prefix
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )