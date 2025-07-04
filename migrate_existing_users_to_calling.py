# migrate_existing_users_to_calling.py - Enable calling for existing users
import asyncio
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def migrate_existing_users():
    """Enable calling capability for all existing users"""
    print("🔄 MIGRATING EXISTING USERS TO CALL ROUTING")
    print("=" * 60)
    
    try:
        # Initialize database connection
        sys.path.append('.')
        from app.config.database import connect_to_mongo, get_database
        
        print("📊 Connecting to database...")
        await connect_to_mongo()
        db = get_database()
        print("✅ Database connected")
        
        # Import call routing service
        from app.services.call_routing_service import call_routing_service
        
        # Find all existing users
        print("\n🔍 Finding existing users...")
        all_users = await db.users.find({}).to_list(None)
        print(f"📋 Found {len(all_users)} total users")
        
        # Filter users who need calling setup
        users_needing_migration = []
        users_already_setup = []
        
        for user in all_users:
            if user.get("calling_enabled"):
                users_already_setup.append(user)
            else:
                users_needing_migration.append(user)
        
        print(f"✅ Already have calling: {len(users_already_setup)} users")
        print(f"🔄 Need migration: {len(users_needing_migration)} users")
        
        if len(users_needing_migration) == 0:
            print("\n🎉 All users already have calling capability!")
            return {"success": True, "migrated": 0, "already_setup": len(users_already_setup)}
        
        # Setup calling for each user
        print(f"\n📞 Setting up calling capability...")
        
        successful_migrations = []
        failed_migrations = []
        
        for i, user in enumerate(users_needing_migration, 1):
            user_email = user.get("email", "unknown")
            user_id = str(user["_id"])
            
            print(f"\n🧪 [{i}/{len(users_needing_migration)}] Migrating: {user_email}")
            
            try:
                # Prepare user data for calling setup
                user_data = {
                    "first_name": user.get("first_name", "Unknown"),
                    "last_name": user.get("last_name", "User"),
                    "email": user_email,
                    "phone": user.get("phone", ""),
                    "department": user.get("department", "General")
                }
                
                # Setup calling capability
                routing_result = await call_routing_service.setup_user_calling(user_data)
                
                if routing_result.get("success"):
                    calling_setup = routing_result["calling_setup"]
                    
                    # Update user record in database
                    update_data = {
                        "calling_enabled": True,
                        "routing_method": "next_available_agent",
                        "tata_agent_pool": calling_setup["tata_agent_pool"],
                        "agent_details": calling_setup["agent_details"],
                        "calling_status": "active",
                        "calling_provider": "TATA Cloud Phone",
                        "calling_setup_date": datetime.utcnow(),
                        "migration_date": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                    
                    result = await db.users.update_one(
                        {"_id": user["_id"]},
                        {"$set": update_data}
                    )
                    
                    if result.modified_count > 0:
                        available_agents = routing_result.get("available_agents", 0)
                        print(f"   ✅ Success: {available_agents} agents available")
                        successful_migrations.append({
                            "email": user_email,
                            "user_id": user_id,
                            "available_agents": available_agents
                        })
                    else:
                        print(f"   ❌ Database update failed")
                        failed_migrations.append({"email": user_email, "error": "Database update failed"})
                else:
                    error = routing_result.get("error", "Unknown error")
                    print(f"   ❌ Setup failed: {error}")
                    failed_migrations.append({"email": user_email, "error": error})
                
            except Exception as e:
                print(f"   ❌ Migration failed: {str(e)}")
                failed_migrations.append({"email": user_email, "error": str(e)})
        
        # Show migration summary
        print(f"\n" + "=" * 60)
        print("📊 MIGRATION SUMMARY:")
        print(f"✅ Successful migrations: {len(successful_migrations)}")
        print(f"❌ Failed migrations: {len(failed_migrations)}")
        print(f"⏭️ Already had calling: {len(users_already_setup)}")
        
        if successful_migrations:
            print(f"\n✅ SUCCESSFUL MIGRATIONS:")
            for migration in successful_migrations:
                print(f"   📞 {migration['email']} → {migration['available_agents']} agents available")
        
        if failed_migrations:
            print(f"\n❌ FAILED MIGRATIONS:")
            for migration in failed_migrations:
                print(f"   💥 {migration['email']} → {migration['error']}")
        
        return {
            "success": len(failed_migrations) == 0,
            "migrated": len(successful_migrations),
            "failed": len(failed_migrations),
            "already_setup": len(users_already_setup)
        }
        
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}

async def verify_migration():
    """Verify that migration was successful"""
    print(f"\n🔍 VERIFYING MIGRATION...")
    print("=" * 40)
    
    try:
        sys.path.append('.')
        from app.config.database import get_database
        
        db = get_database()
        
        # Count users with calling enabled
        calling_enabled_count = await db.users.count_documents({"calling_enabled": True})
        total_users = await db.users.count_documents({})
        
        print(f"📞 Users with calling: {calling_enabled_count}/{total_users}")
        
        if calling_enabled_count == total_users:
            print("🎉 ALL USERS HAVE CALLING CAPABILITY!")
        else:
            missing = total_users - calling_enabled_count
            print(f"⚠️  {missing} users still need calling setup")
        
        # Show sample of migrated users
        sample_users = await db.users.find(
            {"calling_enabled": True, "migration_date": {"$exists": True}}
        ).limit(3).to_list(None)
        
        if sample_users:
            print(f"\n📋 Sample migrated users:")
            for user in sample_users:
                agent_count = len(user.get("tata_agent_pool", []))
                print(f"   ✅ {user['email']} → {agent_count} agents in pool")
        
        return calling_enabled_count == total_users
        
    except Exception as e:
        print(f"❌ Verification failed: {str(e)}")
        return False

async def refresh_agent_pools():
    """Refresh agent pools for all users (handles new agents)"""
    print(f"\n🔄 REFRESHING AGENT POOLS FOR ALL USERS...")
    print("=" * 50)
    
    try:
        from app.services.call_routing_service import call_routing_service
        
        refresh_result = await call_routing_service.refresh_all_user_agent_pools()
        
        if refresh_result.get("success"):
            print(f"✅ Refreshed agent pools for {refresh_result['users_updated']} users")
            print(f"📞 Available agents: {refresh_result['agents_available']}")
            print(f"👥 Agent names: {', '.join(refresh_result['agent_names'])}")
            return True
        else:
            print(f"❌ Refresh failed: {refresh_result.get('error')}")
            return False
            
    except Exception as e:
        print(f"❌ Agent pool refresh failed: {str(e)}")
        return False

def show_migration_info():
    """Show information about what the migration does"""
    print("💡 MIGRATION INFORMATION")
    print("=" * 40)
    
    print("🎯 WHAT THIS MIGRATION DOES:")
    print("   1. Finds all existing users without calling capability")
    print("   2. Sets up call routing for each user")
    print("   3. Assigns them to available TATA agents")
    print("   4. Updates database with calling fields")
    
    print(f"\n📊 DATABASE FIELDS ADDED:")
    print("   ✅ calling_enabled: true")
    print("   ✅ routing_method: 'next_available_agent'")
    print("   ✅ tata_agent_pool: [agent IDs]")
    print("   ✅ agent_details: {agent info}")
    print("   ✅ calling_status: 'active'")
    print("   ✅ migration_date: timestamp")
    
    print(f"\n🔄 DYNAMIC AGENT UPDATES:")
    print("   ✅ System checks for new TATA agents on each call")
    print("   ✅ User agent pools auto-update when new agents found")
    print("   ✅ Manual refresh available: refresh_agent_pools()")

async def main():
    print("🚀 LEADG CRM - CALLING CAPABILITY MIGRATION")
    print("=" * 60)
    
    # Show info
    show_migration_info()
    
    # Run migration
    migration_result = await migrate_existing_users()
    
    # Verify migration
    verification_success = await verify_migration()
    
    # Refresh agent pools to ensure latest agents
    refresh_success = await refresh_agent_pools()
    
    print(f"\n" + "=" * 60)
    print("🎯 FINAL MIGRATION RESULTS:")
    print(f"📊 Migration: {'✅ Success' if migration_result.get('success') else '❌ Failed'}")
    print(f"🔍 Verification: {'✅ Passed' if verification_success else '❌ Failed'}")
    print(f"🔄 Agent Refresh: {'✅ Success' if refresh_success else '❌ Failed'}")
    
    if migration_result.get("success") and verification_success:
        print(f"\n🎉 MIGRATION COMPLETE!")
        print(f"✅ {migration_result['migrated']} users migrated to calling")
        print(f"✅ All users can now make calls through TATA agents")
        print(f"✅ System will auto-update when new agents are added")
        
        print(f"\n🚀 NEXT STEPS:")
        print("1. Start your server: python run.py")
        print("2. Test calling functionality with Postman")
        print("3. Users can now make calls through available agents")
    else:
        print(f"\n⚠️  MIGRATION HAD ISSUES:")
        if migration_result.get("failed", 0) > 0:
            print(f"   💥 {migration_result['failed']} users failed to migrate")
        print("   🔧 Check error messages above and retry")

if __name__ == "__main__":
    asyncio.run(main())