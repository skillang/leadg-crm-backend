from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import IndexModel, ASCENDING
from .settings import settings
import logging
import ssl

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client = None
        self.database = None

# Global database instance
db = Database()

async def connect_to_mongo():
    """Create database connection with Atlas support"""
    try:
        # 🔥 UPDATED: MongoDB Atlas connection with proper options
        if settings.is_atlas_connection():
            logger.info("🌐 Connecting to MongoDB Atlas...")
            
            # Atlas-specific connection options
            connection_options = {
                **settings.get_mongodb_connection_options(),
                "tls": True,  # Enable TLS for Atlas
                "tlsAllowInvalidCertificates": False,  # Ensure certificate validation
                "authSource": "admin",  # Atlas uses admin as auth source
                "appName": "LeadG-CRM"  # Application name for Atlas monitoring
            }
            
            # Create client with Atlas options
            db.client = AsyncIOMotorClient(
                settings.mongodb_url,
                **connection_options
            )
            
        else:
            logger.info("🏠 Connecting to local MongoDB...")
            # Local MongoDB connection (fallback)
            db.client = AsyncIOMotorClient(settings.mongodb_url)
        
        # Set database
        db.database = db.client[settings.database_name]
        
        # Test the connection with timeout
        logger.info("🔍 Testing database connection...")
        await db.client.admin.command('ping')
        
        # Get server info for logging
        server_info = await db.client.server_info()
        logger.info(f"✅ Successfully connected to MongoDB {server_info.get('version')}")
        
        if settings.is_atlas_connection():
            # Log Atlas-specific connection info
            cluster_info = await db.client.admin.command('buildInfo')
            logger.info(f"🌐 Connected to Atlas cluster - MongoDB {cluster_info.get('version')}")
            logger.info(f"📊 Database: {settings.database_name}")
        
        # Create indexes for better performance
        await create_indexes()
        
    except Exception as e:
        error_msg = f"❌ Failed to connect to MongoDB: {e}"
        logger.error(error_msg)
        
        # Provide specific Atlas troubleshooting
        if settings.is_atlas_connection():
            logger.error("🌐 Atlas Connection Troubleshooting:")
            logger.error("   1. Check your connection string format")
            logger.error("   2. Verify username and password are correct")
            logger.error("   3. Ensure your IP is whitelisted in Atlas")
            logger.error("   4. Check database name exists in Atlas")
            logger.error("   5. Verify network access rules")
        
        raise Exception(error_msg)

async def close_mongo_connection():
    """Close database connection"""
    if db.client:
        db.client.close()
        logger.info("🔌 Disconnected from MongoDB")

async def create_indexes():
    """Create database indexes for optimization"""
    try:
        logger.info("📑 Creating database indexes...")
        
        # Users collection indexes
        users_collection = db.database.users
        await users_collection.create_indexes([
            IndexModel([("email", ASCENDING)], unique=True),
            IndexModel([("username", ASCENDING)], unique=True),
            IndexModel([("is_active", ASCENDING)]),
            IndexModel([("role", ASCENDING)]),
        ])
        
        # Leads collection indexes
        leads_collection = db.database.leads
        await leads_collection.create_indexes([
            IndexModel([("lead_id", ASCENDING)], unique=True),
            IndexModel([("email", ASCENDING)]),
            IndexModel([("assigned_to", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_at", ASCENDING)]),
            IndexModel([("source", ASCENDING)]),
        ])
        
        # Tasks collection indexes
        tasks_collection = db.database.lead_tasks
        await tasks_collection.create_indexes([
            IndexModel([("lead_id", ASCENDING)]),
            IndexModel([("lead_object_id", ASCENDING)]),
            IndexModel([("assigned_to", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("due_datetime", ASCENDING)]),
            IndexModel([("created_by", ASCENDING)]),
        ])
        
        # Notes collection indexes (if exists)
        notes_collection = db.database.lead_notes
        await notes_collection.create_indexes([
            IndexModel([("lead_id", ASCENDING)]),
            IndexModel([("lead_object_id", ASCENDING)]),
            IndexModel([("created_by", ASCENDING)]),
            IndexModel([("note_type", ASCENDING)]),
            IndexModel([("tags", ASCENDING)]),
            IndexModel([("created_at", ASCENDING)]),
        ])
        
        # Activities collection indexes
        activities_collection = db.database.lead_activities
        await activities_collection.create_indexes([
            IndexModel([("lead_id", ASCENDING)]),
            IndexModel([("activity_type", ASCENDING)]),
            IndexModel([("created_by", ASCENDING)]),
            IndexModel([("created_at", ASCENDING)]),
        ])
        
        # 🔗 NEW: Contacts collection indexes
        contacts_collection = db.database.lead_contacts
        await contacts_collection.create_indexes([
            IndexModel([("lead_id", ASCENDING)]),
            IndexModel([("created_by", ASCENDING)]),
            IndexModel([("is_primary", ASCENDING)]),
            IndexModel([("email", ASCENDING)]),
            IndexModel([("role", ASCENDING)]),
            IndexModel([("relationship", ASCENDING)]),
            IndexModel([("created_at", ASCENDING)]),
            IndexModel([("linked_leads", ASCENDING)]),  # For linked leads functionality
            # Compound indexes for better query performance
            IndexModel([("lead_id", ASCENDING), ("is_primary", ASCENDING)]),
            IndexModel([("lead_id", ASCENDING), ("role", ASCENDING)]),
            IndexModel([("lead_id", ASCENDING), ("created_at", ASCENDING)]),
        ])
        
        # Token blacklist for logout functionality
        token_blacklist = db.database.token_blacklist
        await token_blacklist.create_indexes([
            IndexModel([("token_jti", ASCENDING)], unique=True),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
        ])
        
        logger.info("📑 Database indexes created successfully")
        
    except Exception as e:
        logger.error(f"❌ Failed to create indexes: {e}")
        # Don't fail the connection if index creation fails
        logger.warning("⚠️ Continuing without optimal indexes")

def get_database():
    """Get database instance - FIXED for Motor compatibility"""
    if db.database is None:  # 🔧 FIXED: Use 'is None' instead of boolean check
        raise Exception("Database not connected. Call connect_to_mongo() first.")
    return db.database

async def test_database_connection():
    """Test database operations - FIXED for Motor compatibility"""
    try:
        database = get_database()
        
        # Test basic operations
        test_result = await database.command("ping")
        logger.info(f"✅ Database ping successful: {test_result}")
        
        # Test collections access
        collections = await database.list_collection_names()
        logger.info(f"📂 Available collections: {collections}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Database test failed: {e}")
        return False