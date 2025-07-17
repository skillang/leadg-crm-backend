# app/config/database.py - UPDATED TO INCLUDE STAGE COLLECTION INDEXES

import motor.motor_asyncio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import logging
from .settings import settings

logger = logging.getLogger(__name__)

# Global database client
_client: AsyncIOMotorClient = None
_database: AsyncIOMotorDatabase = None

async def connect_to_mongo():
    """Create database connection"""
    global _client, _database
    
    try:
        logger.info("🔌 Connecting to MongoDB...")
        
        _client = AsyncIOMotorClient(
            settings.mongodb_url,  # ✅ FIXED: was settings.MONGODB_URL
            maxPoolSize=settings.mongodb_max_pool_size,  # ✅ FIXED: was settings.MONGODB_MAX_POOL_SIZE
            minPoolSize=settings.mongodb_min_pool_size,  # ✅ FIXED: was settings.MONGODB_MIN_POOL_SIZE
            maxIdleTimeMS=settings.mongodb_max_idle_time_ms,  # ✅ FIXED: was settings.MONGODB_MAX_IDLE_TIME_MS
            serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms  # ✅ FIXED: was settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS
        )
        
        _database = _client[settings.database_name]  # ✅ FIXED: was settings.DATABASE_NAME
        
        # Test connection
        await _database.command("ping")
        logger.info("✅ Connected to MongoDB successfully")
        
    except Exception as e:
        logger.error(f"❌ Failed to connect to MongoDB: {e}")
        raise

def get_database() -> AsyncIOMotorDatabase:
    """Get database instance"""
    global _database
    if _database is None:
        raise RuntimeError("Database not initialized. Call connect_to_mongo() first.")
    return _database

async def close_mongo_connection():
    """Close database connection"""
    global _client
    if _client:
        _client.close()
        logger.info("🔌 MongoDB connection closed")

async def create_indexes():
    """Create database indexes for optimal performance"""
    try:
        db = get_database()
        logger.info("📊 Creating database indexes...")
        
        # ============================================================================
        # USERS COLLECTION INDEXES
        # ============================================================================
        await db.users.create_index("email", unique=True)
        await db.users.create_index("username", unique=True)
        await db.users.create_index([("role", 1), ("is_active", 1)])
        await db.users.create_index("created_at")
        logger.info("✅ Users indexes created")
        
        # ============================================================================
        # LEADS COLLECTION INDEXES
        # ============================================================================
        await db.leads.create_index("lead_id", unique=True)
        await db.leads.create_index("email")
        await db.leads.create_index("contact_number")
        await db.leads.create_index([("assigned_to", 1), ("stage", 1)])
        await db.leads.create_index([("created_by", 1), ("created_at", -1)])
        await db.leads.create_index([("stage", 1), ("created_at", -1)])
        await db.leads.create_index([("category", 1), ("stage", 1)])
        await db.leads.create_index("tags")
        await db.leads.create_index("source")
        await db.leads.create_index("status")
        await db.leads.create_index("created_at")
        await db.leads.create_index("updated_at")
        logger.info("✅ Leads indexes created")
        
        # ============================================================================
        # LEAD_STAGES COLLECTION INDEXES (NEW)
        # ============================================================================
        await db.lead_stages.create_index("name", unique=True)
        await db.lead_stages.create_index([("is_active", 1), ("sort_order", 1)])
        await db.lead_stages.create_index("is_default")
        await db.lead_stages.create_index("created_by")
        await db.lead_stages.create_index("created_at")
        logger.info("✅ Lead Stages indexes created")
        
        # ============================================================================
        # LEAD_STATUSES COLLECTION INDEXES (NEW)
        # ============================================================================
        await db.lead_statuses.create_index("name", unique=True)
        await db.lead_statuses.create_index([("is_active", 1), ("sort_order", 1)])
        await db.lead_statuses.create_index("is_default")
        await db.lead_statuses.create_index("created_by")
        await db.lead_statuses.create_index("created_at")
        logger.info("✅ Lead Statuses indexes created")
        
        # ============================================================================
        # TASKS COLLECTION INDEXES
        # ============================================================================
        await db.lead_tasks.create_index([("lead_id", 1), ("created_at", -1)])
        await db.lead_tasks.create_index([("assigned_to", 1), ("due_date", 1)])
        await db.lead_tasks.create_index([("created_by", 1), ("created_at", -1)])
        await db.lead_tasks.create_index([("priority", 1), ("status", 1)])
        await db.lead_tasks.create_index("due_date")
        await db.lead_tasks.create_index("status")
        await db.lead_tasks.create_index("task_type")
        logger.info("✅ Tasks indexes created")
        
        # ============================================================================
        # ACTIVITIES COLLECTION INDEXES
        # ============================================================================
        await db.lead_activities.create_index([("lead_id", 1), ("created_at", -1)])
        await db.lead_activities.create_index([("created_by", 1), ("created_at", -1)])
        await db.lead_activities.create_index("activity_type")
        await db.lead_activities.create_index("created_at")
        logger.info("✅ Activities indexes created")
        
        # ============================================================================
        # AUTHENTICATION INDEXES
        # ============================================================================
        await db.token_blacklist.create_index("token", unique=True)
        await db.token_blacklist.create_index("expires_at", expireAfterSeconds=0)
        
        await db.user_sessions.create_index([("user_id", 1), ("created_at", -1)])
        await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
        logger.info("✅ Authentication indexes created")
        
        # ============================================================================
        # FUTURE COLLECTIONS (PLANNED)
        # ============================================================================
        
        # Lead Notes Collection (TO BE CREATED)
        # await db.lead_notes.create_index([("lead_id", 1), ("created_at", -1)])
        # await db.lead_notes.create_index([("created_by", 1), ("created_at", -1)])
        # await db.lead_notes.create_index("tags")
        # logger.info("✅ Notes indexes created")
        
        # Lead Documents Collection (TO BE CREATED)
        # await db.lead_documents.create_index([("lead_id", 1), ("created_at", -1)])
        # await db.lead_documents.create_index([("created_by", 1), ("status", 1)])
        # await db.lead_documents.create_index("document_type")
        # await db.lead_documents.create_index("status")
        # logger.info("✅ Documents indexes created")
        
        # Lead Contacts Collection (TO BE CREATED)
        # await db.lead_contacts.create_index([("lead_id", 1), ("is_primary", -1)])
        # await db.lead_contacts.create_index("email")
        # await db.lead_contacts.create_index("contact_number")
        # await db.lead_contacts.create_index("role")
        # logger.info("✅ Contacts indexes created")
        
        logger.info("🎯 All database indexes created successfully!")
        
    except Exception as e:
        logger.error(f"❌ Error creating indexes: {e}")
        raise

async def get_collection_stats():
    """Get database collection statistics"""
    try:
        db = get_database()
        
        collections = [
            "users",
            "leads", 
            "lead_stages",  # NEW
            "lead_statuses",  # NEW
            "lead_tasks",
            "lead_activities",
            "token_blacklist",
            "user_sessions"
        ]
        
        stats = {}
        for collection_name in collections:
            try:
                count = await db[collection_name].count_documents({})
                stats[collection_name] = count
            except:
                stats[collection_name] = 0
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting collection stats: {e}")
        return {}

# Database lifecycle management
async def init_database():
    """Initialize database connection and indexes"""
    await connect_to_mongo()
    await create_indexes()

# Export functions
__all__ = [
    "get_database",
    "connect_to_mongo", 
    "close_mongo_connection",
    "create_indexes",
    "get_collection_stats",
    "init_database"
]