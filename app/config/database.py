# app/config/database.py - Enhanced with Multi-Assignment and Selective Round Robin Indexes

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
            settings.mongodb_url,
            maxPoolSize=settings.mongodb_max_pool_size,
            minPoolSize=settings.mongodb_min_pool_size,
            maxIdleTimeMS=settings.mongodb_max_idle_time_ms,
            serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms
        )
        
        _database = _client[settings.database_name]
        
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
    """Create database indexes for optimal performance with enhanced multi-assignment support"""
    try:
        db = get_database()
        logger.info("📊 Creating enhanced database indexes...")
        
        # ============================================================================
        # USERS COLLECTION INDEXES (ENHANCED)
        # ============================================================================
        await db.users.create_index("email", unique=True)
        await db.users.create_index("username", unique=True)
        await db.users.create_index([("role", 1), ("is_active", 1)])
        await db.users.create_index("created_at")
        
        # 🆕 NEW: Enhanced indexes for selective round robin
        await db.users.create_index([("role", 1), ("is_active", 1), ("total_assigned_leads", 1)])
        await db.users.create_index("total_assigned_leads")  # For round robin load balancing
        await db.users.create_index("departments")  # For department-based assignment
        await db.users.create_index([("departments", 1), ("is_active", 1)])
        await db.users.create_index([("email", 1), ("is_active", 1)])  # Fast user validation
        
        logger.info("✅ Enhanced Users indexes created")
        
        # ============================================================================
        # LEADS COLLECTION INDEXES (ENHANCED WITH MULTI-ASSIGNMENT)
        # ============================================================================
        await db.leads.create_index("lead_id", unique=True)
        await db.leads.create_index("email")
        await db.leads.create_index("contact_number")
        
        # 🆕 NEW: Enhanced assignment indexes for multi-user assignment
        await db.leads.create_index("assigned_to")  # Primary assignment
        await db.leads.create_index("co_assignees")  # Co-assignee queries
        await db.leads.create_index("is_multi_assigned")  # Filter multi-assigned leads
        await db.leads.create_index([("assigned_to", 1), ("is_multi_assigned", 1)])  # Compound for user queries
        await db.leads.create_index([("co_assignees", 1), ("is_multi_assigned", 1)])  # Co-assignee queries
        
        # Multi-assignment compound indexes for efficient user lead queries
        await db.leads.create_index([("assigned_to", 1), ("status", 1)])
        await db.leads.create_index([("assigned_to", 1), ("created_at", -1)])
        await db.leads.create_index([("co_assignees", 1), ("status", 1)])
        await db.leads.create_index([("co_assignees", 1), ("created_at", -1)])
        
        # Enhanced assignment method tracking
        await db.leads.create_index("assignment_method")  # Track assignment methods
        await db.leads.create_index([("assignment_method", 1), ("created_at", -1)])
        
        # Existing essential indexes
        await db.leads.create_index([("created_by", 1), ("created_at", -1)])
        await db.leads.create_index([("stage", 1), ("created_at", -1)])
        await db.leads.create_index([("category", 1), ("stage", 1)])
        await db.leads.create_index("tags")
        await db.leads.create_index("source")
        await db.leads.create_index("status")
        await db.leads.create_index("created_at")
        await db.leads.create_index("updated_at")
        
        # 🆕 NEW: Indexes for new optional fields
        await db.leads.create_index("age")
        await db.leads.create_index("experience")
        await db.leads.create_index("nationality")
        await db.leads.create_index([("category", 1), ("age", 1)])  # Category-age analysis
        await db.leads.create_index([("nationality", 1), ("category", 1)])  # Nationality-category analysis
        
        logger.info("✅ Enhanced Leads indexes created")
        
        # ============================================================================
        # LEAD_STAGES COLLECTION INDEXES
        # ============================================================================
        await db.lead_stages.create_index("name", unique=True)
        await db.lead_stages.create_index([("is_active", 1), ("sort_order", 1)])
        await db.lead_stages.create_index("is_default")
        await db.lead_stages.create_index("created_by")
        await db.lead_stages.create_index("created_at")
        logger.info("✅ Lead Stages indexes created")
        
        # ============================================================================
        # LEAD_STATUSES COLLECTION INDEXES
        # ============================================================================
        await db.lead_statuses.create_index("name", unique=True)
        await db.lead_statuses.create_index([("is_active", 1), ("sort_order", 1)])
        await db.lead_statuses.create_index("is_default")
        await db.lead_statuses.create_index("created_by")
        await db.lead_statuses.create_index("created_at")
        logger.info("✅ Lead Statuses indexes created")
        
        # ============================================================================
        # TASKS COLLECTION INDEXES (ENHANCED)
        # ============================================================================
        await db.lead_tasks.create_index([("lead_id", 1), ("created_at", -1)])
        await db.lead_tasks.create_index([("assigned_to", 1), ("status", 1)])
        await db.lead_tasks.create_index([("assigned_to", 1), ("due_datetime", 1)])
        await db.lead_tasks.create_index([("created_by", 1), ("created_at", -1)])
        await db.lead_tasks.create_index("lead_object_id")
        await db.lead_tasks.create_index("task_type")
        await db.lead_tasks.create_index("priority")
        await db.lead_tasks.create_index("status")
        await db.lead_tasks.create_index("due_datetime")
        await db.lead_tasks.create_index([("status", 1), ("due_datetime", 1)])
        
        # 🆕 NEW: Enhanced task assignment indexes for multi-assignment scenarios
        await db.lead_tasks.create_index([("lead_id", 1), ("assigned_to", 1)])
        await db.lead_tasks.create_index([("assigned_to", 1), ("created_at", -1)])
        
        logger.info("✅ Enhanced Tasks indexes created")
        
        # ============================================================================
        # LEAD_ACTIVITIES COLLECTION INDEXES (ENHANCED)
        # ============================================================================
        await db.lead_activities.create_index([("lead_id", 1), ("created_at", -1)])
        await db.lead_activities.create_index([("lead_object_id", 1), ("created_at", -1)])
        await db.lead_activities.create_index([("created_by", 1), ("created_at", -1)])
        await db.lead_activities.create_index("activity_type")
        await db.lead_activities.create_index([("activity_type", 1), ("created_at", -1)])
        await db.lead_activities.create_index("created_at")
        await db.lead_activities.create_index("is_system_generated")
        
        # 🆕 NEW: Multi-assignment activity tracking
        await db.lead_activities.create_index([("lead_id", 1), ("activity_type", 1)])
        await db.lead_activities.create_index([("activity_type", 1), ("is_system_generated", 1)])
        
        logger.info("✅ Enhanced Activities indexes created")
        
        # ============================================================================
        # 🆕 NEW: LEAD_COUNTERS COLLECTION INDEXES
        # ============================================================================
        await db.lead_counters.create_index("category", unique=True)
        await db.lead_counters.create_index("_id", unique=True)  # For sequence counters
        logger.info("✅ Lead Counters indexes created")
        
        # ============================================================================
        # AUTHENTICATION COLLECTIONS INDEXES
        # ============================================================================
        await db.token_blacklist.create_index("token_jti", unique=True)
        await db.token_blacklist.create_index("expires_at", expireAfterSeconds=0)
        await db.token_blacklist.create_index("blacklisted_at")
        
        await db.user_sessions.create_index([("user_id", 1), ("created_at", -1)])
        await db.user_sessions.create_index("session_id", unique=True)
        await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
        await db.user_sessions.create_index([("user_id", 1), ("is_active", 1)])
        logger.info("✅ Authentication indexes created")
        
        # ============================================================================
        # 🆕 NEW: FUTURE COLLECTIONS INDEXES (READY FOR IMPLEMENTATION)
        # ============================================================================
        
        # Lead Notes Collection indexes (for future implementation)
        try:
            await db.lead_notes.create_index([("lead_id", 1), ("created_at", -1)])
            await db.lead_notes.create_index([("created_by", 1), ("created_at", -1)])
            await db.lead_notes.create_index("tags")
            await db.lead_notes.create_index([("lead_id", 1), ("tags", 1)])
            await db.lead_notes.create_index("title")  # For title searches
            logger.info("✅ Notes indexes created")
        except:
            logger.info("ℹ️ Notes collection not yet created - indexes will be created when collection exists")
        
        # Lead Documents Collection indexes (for future implementation)
        try:
            await db.lead_documents.create_index([("lead_id", 1), ("created_at", -1)])
            await db.lead_documents.create_index([("created_by", 1), ("status", 1)])
            await db.lead_documents.create_index("document_type")
            await db.lead_documents.create_index("status")
            await db.lead_documents.create_index([("lead_id", 1), ("document_type", 1)])
            await db.lead_documents.create_index([("status", 1), ("created_at", -1)])
            logger.info("✅ Documents indexes created")
        except:
            logger.info("ℹ️ Documents collection not yet created - indexes will be created when collection exists")
        
        # Lead Contacts Collection indexes (for future implementation)
        try:
            await db.lead_contacts.create_index([("lead_id", 1), ("is_primary", -1)])
            await db.lead_contacts.create_index("email")
            await db.lead_contacts.create_index("contact_number")
            await db.lead_contacts.create_index("role")
            await db.lead_contacts.create_index([("lead_id", 1), ("role", 1)])
            await db.lead_contacts.create_index([("lead_id", 1), ("is_primary", 1)])
            logger.info("✅ Contacts indexes created")
        except:
            logger.info("ℹ️ Contacts collection not yet created - indexes will be created when collection exists")
        
        logger.info("🎯 All enhanced database indexes created successfully!")
        logger.info("🚀 System optimized for multi-user assignment and selective round robin!")
        
    except Exception as e:
        logger.error(f"❌ Error creating indexes: {e}")
        # Don't fail the application startup if index creation fails
        logger.warning("⚠️ Continuing without optimal indexes - some queries may be slower")

async def get_collection_stats():
    """Get database collection statistics with enhanced metrics"""
    try:
        db = get_database()
        
        collections = [
            "users",
            "leads", 
            "lead_stages",
            "lead_statuses",
            "lead_tasks",
            "lead_activities",
            "lead_counters",  # NEW
            "token_blacklist",
            "user_sessions",
            # Future collections
            "lead_notes",
            "lead_documents", 
            "lead_contacts"
        ]
        
        stats = {}
        total_documents = 0
        
        for collection_name in collections:
            try:
                count = await db[collection_name].count_documents({})
                stats[collection_name] = count
                total_documents += count
                
                # Get additional stats for key collections
                if collection_name == "leads":
                    multi_assigned = await db[collection_name].count_documents({"is_multi_assigned": True})
                    stats[f"{collection_name}_multi_assigned"] = multi_assigned
                    
                    unassigned = await db[collection_name].count_documents({"assigned_to": None})
                    stats[f"{collection_name}_unassigned"] = unassigned
                    
                elif collection_name == "users":
                    active_users = await db[collection_name].count_documents({"is_active": True})
                    stats[f"{collection_name}_active"] = active_users
                    
            except Exception as collection_error:
                stats[collection_name] = 0
                logger.debug(f"Collection {collection_name} not found or error: {collection_error}")
        
        stats["total_documents"] = total_documents
        stats["collections_found"] = len([k for k, v in stats.items() if v > 0 and not k.startswith("total")])
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting collection stats: {e}")
        return {"error": str(e)}

async def get_index_stats():
    """Get index statistics for performance monitoring"""
    try:
        db = get_database()
        
        collections = ["users", "leads", "lead_tasks", "lead_activities"]
        index_stats = {}
        
        for collection_name in collections:
            try:
                collection = db[collection_name]
                indexes = await collection.list_indexes().to_list(None)
                index_stats[collection_name] = {
                    "index_count": len(indexes),
                    "indexes": [idx.get("name", "unknown") for idx in indexes]
                }
            except Exception as e:
                index_stats[collection_name] = {"error": str(e)}
        
        return index_stats
        
    except Exception as e:
        logger.error(f"Error getting index stats: {e}")
        return {"error": str(e)}

# Database lifecycle management
async def init_database():
    """Initialize database connection and indexes"""
    await connect_to_mongo()
    await create_indexes()
    
    # Log database status
    stats = await get_collection_stats()
    logger.info(f"📊 Database initialized with {stats.get('collections_found', 0)} collections")
    logger.info(f"📈 Total documents: {stats.get('total_documents', 0)}")
    
    if stats.get('leads', 0) > 0:
        logger.info(f"🎯 Leads: {stats.get('leads', 0)} total, {stats.get('leads_multi_assigned', 0)} multi-assigned, {stats.get('leads_unassigned', 0)} unassigned")
    
    if stats.get('users', 0) > 0:
        logger.info(f"👥 Users: {stats.get('users', 0)} total, {stats.get('users_active', 0)} active")

async def cleanup_database():
    """Cleanup database resources"""
    try:
        # Close any open cursors or connections
        await close_mongo_connection()
        logger.info("🧹 Database cleanup completed")
    except Exception as e:
        logger.error(f"Error during database cleanup: {e}")

# Health check functions
async def test_database_connection():
    """Test database operations and performance"""
    try:
        db = get_database()
        
        # Test basic operations
        ping_result = await db.command("ping")
        logger.info(f"✅ Database ping successful: {ping_result}")
        
        # Test collections access
        collections = await db.list_collection_names()
        logger.info(f"📂 Available collections: {len(collections)}")
        
        # Test index efficiency on leads collection (most critical)
        if "leads" in collections:
            explain_result = await db.leads.find({"assigned_to": {"$ne": None}}).explain()
            logger.info("🔍 Lead query performance test completed")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Database test failed: {e}")
        return False

# Export functions
__all__ = [
    "get_database",
    "connect_to_mongo", 
    "close_mongo_connection",
    "create_indexes",
    "get_collection_stats",
    "get_index_stats",
    "init_database",
    "cleanup_database",
    "test_database_connection"
]