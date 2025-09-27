import asyncio
import json
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URL = "mongodb+srv://admin:lokskill123@skillang-cluster.pd58sjb.mongodb.net/?retryWrites=true&w=majority&appName=skillang-cluster"
DATABASE_NAME = "leadg_crm"

async def connect_database():
    print("Connecting to database...")
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    await db.command("ping")
    print("Connected successfully!")
    return client, db

def clean_phone(phone):
    if not phone:
        return None
    clean = ''.join(c for c in str(phone) if c.isdigit() or c == '+')
    if clean.startswith('+'):
        clean = clean[1:]
    return clean if len(clean) >= 10 else None

def clean_email(email):
    return str(email).lower().strip() if email else None

async def find_duplicates(db):
    print("\nScanning for duplicates...")
    
    leads = await db.leads.find({}).to_list(length=None)
    print(f"Found {len(leads)} total leads")
    
    email_groups = {}
    phone_groups = {}
    
    for lead in leads:
        # Email grouping
        if lead.get("email"):
            email = clean_email(lead["email"])
            if email:
                if email not in email_groups:
                    email_groups[email] = []
                email_groups[email].append(lead)
        
        # Phone grouping
        phone = lead.get("contact_number") or lead.get("phone_number")
        if phone:
            phone = clean_phone(phone)
            if phone:
                if phone not in phone_groups:
                    phone_groups[phone] = []
                phone_groups[phone].append(lead)
    
    duplicates = []
    
    for email, group in email_groups.items():
        if len(group) > 1:
            duplicates.append({"type": "EMAIL", "value": email, "leads": group})
    
    for phone, group in phone_groups.items():
        if len(group) > 1:
            duplicates.append({"type": "PHONE", "value": phone, "leads": group})
    
    print(f"Found {len(duplicates)} duplicate groups")
    return duplicates

async def get_call_count(db, lead_id):
    try:
        lead = await db.leads.find_one({"lead_id": lead_id})
        if lead and lead.get("call_stats", {}).get("total_calls"):
            return int(lead["call_stats"]["total_calls"])
        
        calls = await db.call_logs.count_documents({"lead_id": lead_id})
        
        if calls == 0:
            activities = await db.lead_activities.count_documents({
                "lead_id": lead_id,
                "activity_type": {"$in": ["call_logged", "call_completed"]}
            })
            calls += activities
        
        return calls
    except:
        return 0

def display_lead(lead, calls, number, status=""):
    print(f"\n{number}. {lead['lead_id']} - {lead.get('name', 'No Name')}")
    print(f"   Email: {lead.get('email', 'N/A')}")
    print(f"   Phone: {lead.get('contact_number', lead.get('phone_number', 'N/A'))}")
    print(f"   Calls: {calls}")
    print(f"   Assigned: {lead.get('assigned_to', 'Unassigned')}")
    if status:
        print(f"   >>> {status}")

async def backup_lead(db, lead_id, backup_data):
    try:
        lead = await db.leads.find_one({"lead_id": lead_id})
        if lead:
            lead["_id"] = str(lead["_id"])
            
            # Get related data too
            tasks = await db.lead_tasks.find({"lead_id": lead_id}).to_list(None)
            notes = await db.lead_notes.find({"lead_id": lead_id}).to_list(None)
            activities = await db.lead_activities.find({"lead_id": lead_id}).to_list(None)
            calls = await db.call_logs.find({"lead_id": lead_id}).to_list(None)
            
            # Convert ObjectIds to strings
            for item_list in [tasks, notes, activities, calls]:
                for item in item_list:
                    if "_id" in item:
                        item["_id"] = str(item["_id"])
            
            # Add to consolidated backup
            backup_data["leads"].append({
                "lead": lead,
                "tasks": tasks,
                "notes": notes,
                "activities": activities,
                "calls": calls,
                "deleted_at": datetime.now().isoformat()
            })
            
            print(f"   Added to backup: {lead_id}")
            return True
    except Exception as e:
        print(f"   Backup error: {e}")
        return False

def save_consolidated_backup(backup_data):
    try:
        filename = f"duplicate_cleanup_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(backup_data, f, indent=2, default=str)
        print(f"\nConsolidated backup saved: {filename}")
        return filename
    except Exception as e:
        print(f"Error saving backup: {e}")
        return None

async def delete_lead(db, lead_id):
    try:
        collections = ["lead_tasks", "lead_notes", "lead_activities", "call_logs", "leads"]
        total = 0
        
        for coll_name in collections:
            coll = getattr(db, coll_name)
            result = await coll.delete_many({"lead_id": lead_id})
            total += result.deleted_count
        
        print(f"   Deleted {lead_id} - {total} records")
        return True
    except Exception as e:
        print(f"   Error: {e}")
        return False

async def process_group(db, group, num, total, backup_data):
    print("\n" + "="*50)
    print(f"GROUP {num}/{total}")
    print(f"Type: {group['type']}")
    print(f"Value: {group['value']}")
    print(f"Leads: {len(group['leads'])}")
    print(f"Will delete: {len(group['leads']) - 1}")
    print("="*50)
    
    lead_data = []
    for lead in group['leads']:
        calls = await get_call_count(db, lead['lead_id'])
        lead_data.append({"lead": lead, "calls": calls})
    
    lead_data.sort(key=lambda x: (-x["calls"], x["lead"]["created_at"] or datetime.min))
    
    print("\nLeads in this group:")
    
    keep = lead_data[0]
    display_lead(keep["lead"], keep["calls"], 1, "KEEP (most calls)")
    
    delete_list = lead_data[1:]
    for i, data in enumerate(delete_list, 2):
        display_lead(data["lead"], data["calls"], i, "DELETE")
    
    print(f"\nSummary:")
    print(f"KEEP: {keep['lead']['lead_id']} ({keep['calls']} calls)")
    print(f"DELETE:")
    for data in delete_list:
        print(f"  - {data['lead']['lead_id']} ({data['calls']} calls)")
    
    print("\n" + "-"*50)
    while True:
        choice = input("Delete the listed leads? (yes/no/skip): ").lower().strip()
        if choice in ['yes', 'y']:
            break
        elif choice in ['no', 'n', 'skip', 's']:
            print("Skipping...")
            return {"deleted": 0, "kept": 0, "skipped": 1}
        else:
            print("Enter: yes, no, or skip")
    
    print("\nDeleting...")
    deleted = 0
    
    for data in delete_list:
        lead_id = data["lead"]["lead_id"]
        if await backup_lead(db, lead_id, backup_data):
            if await delete_lead(db, lead_id):
                deleted += 1
    
    print(f"\nDone! Kept {keep['lead']['lead_id']}, deleted {deleted}")
    return {"deleted": deleted, "kept": 1, "skipped": 0}

async def main():
    print("LeadG CRM Duplicate Cleaner")
    print("="*30)
    
    try:
        client, db = await connect_database()
        
        duplicates = await find_duplicates(db)
        
        if not duplicates:
            print("No duplicates found!")
            client.close()
            return
        
        print(f"\nFound {len(duplicates)} duplicate groups")
        proceed = input("Start cleanup? (yes/no): ").lower().strip()
        if proceed not in ['yes', 'y']:
            print("Cancelled")
            client.close()
            return
        
        # Initialize consolidated backup
        backup_data = {
            "cleanup_session": datetime.now().isoformat(),
            "total_groups": len(duplicates),
            "leads": []
        }
        
        stats = {"deleted": 0, "kept": 0, "skipped": 0}
        
        for i, group in enumerate(duplicates, 1):
            result = await process_group(db, group, i, len(duplicates), backup_data)
            stats["deleted"] += result["deleted"]
            stats["kept"] += result["kept"]
            stats["skipped"] += result["skipped"]
            
            if i < len(duplicates):
                input("\nPress Enter for next group...")
        
        # Save consolidated backup at the end
        if backup_data["leads"]:
            backup_data["final_stats"] = stats
            save_consolidated_backup(backup_data)
        
        print("\n" + "="*50)
        print("CLEANUP COMPLETE!")
        print("="*50)
        print(f"Groups: {len(duplicates)}")
        print(f"Skipped: {stats['skipped']}")
        print(f"Deleted: {stats['deleted']}")
        print(f"Kept: {stats['kept']}")
        
        client.close()
        
    except KeyboardInterrupt:
        print("\nStopped")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())