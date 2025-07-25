# migration_add_permissions.py - One-time Database Migration for Lead Creation Permissions
"""
This script adds permission fields to all existing users in the database.
Run this ONCE after updating the code to add permission functionality.

Usage:
    python migration_add_permissions.py

What it does:
1. Connects to your MongoDB database
2. Finds all users without 'permissions' field
3. Adds default permissions (all False) to those users
4. Reports the number of users updated
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the parent directory to the path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.database import get_database, connect_to_mongo, close_mongo_connection
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def add_permission_fields_to_users():
    """
    Add permission fields to all existing users who don't have them
    
    Returns:
        dict: Summary of migration results
    """
    try:
        logger.info("🚀 Starting permission fields migration...")
        
        # Connect to database
        await connect_to_mongo()
        db = get_database()
        
        logger.info("✅ Connected to database")
        
        # Check current state
        total_users = await db.users.count_documents({})
        users_without_permissions = await db.users.count_documents({"permissions": {"$exists": False}})
        users_with_permissions = total_users - users_without_permissions
        
        logger.info(f"📊 Current state:")
        logger.info(f"   Total users: {total_users}")
        logger.info(f"   Users with permissions: {users_with_permissions}")
        logger.info(f"   Users without permissions: {users_without_permissions}")
        
        if users_without_permissions == 0:
            logger.info("✅ All users already have permission fields - no migration needed")
            return {
                "success": True,
                "message": "No migration needed - all users already have permissions",
                "total_users": total_users,
                "updated_users": 0,
                "skipped_users": total_users
            }
        
        # Define default permissions structure
        default_permissions = {
            "can_create_single_lead": False,
            "can_create_bulk_leads": False,
            "granted_by": None,
            "granted_at": None,
            "last_modified_by": None,
            "last_modified_at": None
        }
        
        logger.info(f"🔄 Adding default permissions to {users_without_permissions} users...")
        logger.info(f"   Default permissions: {default_permissions}")
        
        # Add permission fields to users who don't have them
        result = await db.users.update_many(
            {"permissions": {"$exists": False}},  # Users without permissions field
            {
                "$set": {
                    "permissions": default_permissions,
                    "permissions_migrated_at": datetime.utcnow(),
                    "permissions_migration_version": "1.0"
                }
            }
        )
        
        logger.info(f"✅ Migration completed successfully!")
        logger.info(f"   Users updated: {result.modified_count}")
        logger.info(f"   Users matched: {result.matched_count}")
        
        # Verify the migration
        users_still_without_permissions = await db.users.count_documents({"permissions": {"$exists": False}})
        if users_still_without_permissions == 0:
            logger.info("🎉 Migration verification successful - all users now have permissions")
        else:
            logger.warning(f"⚠️ Migration verification failed - {users_still_without_permissions} users still without permissions")
        
        return {
            "success": True,
            "message": f"Successfully added permissions to {result.modified_count} users",
            "total_users": total_users,
            "updated_users": result.modified_count,
            "matched_users": result.matched_count,
            "remaining_without_permissions": users_still_without_permissions
        }
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "message": "Migration failed - see logs for details"
        }
    
    finally:
        # Always close the database connection
        await close_mongo_connection()
        logger.info("🔌 Database connection closed")

async def verify_migration():
    """
    Verify that the migration was successful
    
    Returns:
        dict: Verification results
    """
    try:
        logger.info("🔍 Verifying migration results...")
        
        await connect_to_mongo()
        db = get_database()
        
        # Check current state after migration
        total_users = await db.users.count_documents({})
        users_with_permissions = await db.users.count_documents({"permissions": {"$exists": True}})
        users_without_permissions = await db.users.count_documents({"permissions": {"$exists": False}})
        
        # Get sample user with permissions
        sample_user = await db.users.find_one(
            {"permissions": {"$exists": True}},
            {"email": 1, "permissions": 1}
        )
        
        logger.info("📊 Post-migration state:")
        logger.info(f"   Total users: {total_users}")
        logger.info(f"   Users with permissions: {users_with_permissions}")
        logger.info(f"   Users without permissions: {users_without_permissions}")
        
        if sample_user:
            logger.info(f"📋 Sample user permissions structure:")
            logger.info(f"   User: {sample_user.get('email', 'Unknown')}")
            logger.info(f"   Permissions: {sample_user.get('permissions', {})}")
        
        success = users_without_permissions == 0
        
        if success:
            logger.info("✅ Migration verification: SUCCESS")
        else:
            logger.warning("❌ Migration verification: FAILED")
        
        return {
            "success": success,
            "total_users": total_users,
            "users_with_permissions": users_with_permissions,
            "users_without_permissions": users_without_permissions,
            "sample_permissions": sample_user.get("permissions", {}) if sample_user else None
        }
        
    except Exception as e:
        logger.error(f"❌ Verification failed: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }
    
    finally:
        await close_mongo_connection()

async def main():
    """Main migration function"""
    print("=" * 60)
    print("🔒 LeadG CRM - Permission Fields Migration")
    print("=" * 60)
    print()
    
    # Run the migration
    migration_result = await add_permission_fields_to_users()
    
    print()
    print("=" * 60)
    print("📊 MIGRATION RESULTS")
    print("=" * 60)
    print(f"Success: {migration_result['success']}")
    print(f"Message: {migration_result['message']}")
    
    if migration_result['success']:
        print(f"Total users: {migration_result['total_users']}")
        print(f"Updated users: {migration_result['updated_users']}")
        if migration_result['updated_users'] > 0:
            print()
            print("🎉 Migration completed successfully!")
            print()
            print("Next steps:")
            print("1. Start your LeadG CRM application")
            print("2. Login as an admin")
            print("3. Go to Admin Panel > User Permissions")
            print("4. Grant lead creation permissions to users as needed")
            print()
        else:
            print("ℹ️ No users needed migration (all already have permissions)")
    else:
        print(f"Error: {migration_result.get('error', 'Unknown error')}")
        print()
        print("🚨 Migration failed! Please check the logs and try again.")
    
    print("=" * 60)
    
    # Run verification
    print()
    verification_result = await verify_migration()
    
    if verification_result['success']:
        print("✅ Migration verification passed!")
    else:
        print("❌ Migration verification failed!")
        print(f"Error: {verification_result.get('error', 'Unknown error')}")

if __name__ == "__main__":
    """
    Run the migration script
    
    This script is safe to run multiple times - it only updates users
    who don't already have permission fields.
    """
    try:
        # Run the migration
        asyncio.run(main())
        
    except KeyboardInterrupt:
        print("\n⛔ Migration cancelled by user")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Migration failed with error: {str(e)}")
        sys.exit(1)