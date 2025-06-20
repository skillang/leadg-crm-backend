# app/services/task_service.py
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, date, time, timedelta
from bson import ObjectId
import logging

from ..config.database import get_database
from ..models.task import TaskCreate, TaskUpdate, TaskStatus, TaskPriority
from ..models.lead import LeadStatus

logger = logging.getLogger(__name__)

class TaskService:
    def __init__(self):
        pass
    
    async def create_task(self, lead_id: str, task_data: TaskCreate, created_by: str) -> Dict[str, Any]:
        """Create a new task for a lead"""
        try:
            logger.info(f"Creating task for lead_id: {lead_id}")
            logger.info(f"Task data: {task_data.dict()}")
            
            # Direct database call (like your working lead service)
            db = get_database()  # ✅ No await
            
            # Verify lead exists
            lead = await db.leads.find_one({"lead_id": lead_id})
            if not lead:
                raise ValueError(f"Lead {lead_id} not found")
            
            logger.info(f"Lead found: {lead.get('company_name')}")
            
            # Get assigned user name if provided
            assigned_to_name = "Unassigned"
            if task_data.assigned_to:
                assigned_user = await db.users.find_one({"_id": ObjectId(task_data.assigned_to)})
                if assigned_user:
                    first_name = assigned_user.get('first_name', '')
                    last_name = assigned_user.get('last_name', '')
                    full_name = assigned_user.get('full_name', '')
                    email = assigned_user.get('email', '')
                    
                    # Try different name combinations
                    if first_name and last_name:
                        assigned_to_name = f"{first_name} {last_name}".strip()
                    elif full_name:
                        assigned_to_name = full_name
                    elif email:
                        assigned_to_name = email
                    
                    logger.info(f"Assigned to: {assigned_to_name}")
            
            # Convert dates to strings for MongoDB
            due_date_str = task_data.due_date.isoformat() if task_data.due_date else None
            due_time_str = task_data.due_time if isinstance(task_data.due_time, str) else str(task_data.due_time) if task_data.due_time else None
            
            # Create combined datetime for queries
            due_datetime = None
            if task_data.due_date:
                if task_data.due_time:
                    if isinstance(task_data.due_time, str):
                        hour, minute = map(int, task_data.due_time.split(':'))
                        due_datetime = datetime.combine(task_data.due_date, time(hour, minute))
                    else:
                        due_datetime = datetime.combine(task_data.due_date, task_data.due_time)
                else:
                    due_datetime = datetime.combine(task_data.due_date, time(23, 59))
            
            # Determine status
            status = "pending"
            if due_datetime and due_datetime < datetime.utcnow():
                status = "overdue"
            
            # Create task document
            task_doc = {
                "lead_id": lead["lead_id"],
                "lead_object_id": lead["_id"],
                "task_title": task_data.task_title,
                "task_description": task_data.task_description or "",
                "task_type": task_data.task_type,
                "priority": task_data.priority,
                "assigned_to": task_data.assigned_to,
                "assigned_to_name": assigned_to_name,
                "due_date": due_date_str,
                "due_time": due_time_str,
                "due_datetime": due_datetime,
                "status": status,
                "notes": task_data.notes or "",
                "created_by": ObjectId(created_by),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "completed_at": None,
                "completion_notes": ""
            }
            
            logger.info(f"Task document prepared for insert")
            
            # Insert task
            result = await db.lead_tasks.insert_one(task_doc)
            task_doc["id"] = str(result.inserted_id)
            task_doc["_id"] = str(result.inserted_id)
            
            logger.info(f"Task created successfully: {task_doc['id']}")
            
            # Create activity log (optional, can comment out if causing issues)
            try:
                activity_doc = {
                    "lead_object_id": lead["lead_id"],
                    "activity_type": "task_created",
                    "description": f"Task '{task_data.task_title}' created",
                    "created_by": ObjectId(created_by),
                    "created_at": datetime.utcnow(),
                    "metadata": {
                        "task_id": str(result.inserted_id),
                        "task_title": task_data.task_title,
                        "assigned_to": assigned_to_name
                    }
                }
                await db.lead_activities.insert_one(activity_doc)
                logger.info("Activity logged successfully")
            except Exception as activity_error:
                logger.warning(f"Failed to log activity: {activity_error}")
                # Don't fail the whole task creation if activity logging fails
            
            return task_doc
            
        except Exception as e:
            logger.error(f"Error creating task: {str(e)}")
            logger.error(f"Error type: {type(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise Exception(f"Failed to create task: {str(e)}")
    
    async def get_lead_tasks(self, lead_id: str, user_id: str, user_role: str, status_filter: Optional[str] = None) -> Dict[str, Any]:
        """Get all tasks for a lead"""
        try:
            logger.info(f"Getting tasks for lead: {lead_id}, user: {user_id}, role: {user_role}")
            
            db = get_database()  # ✅ No await
            
            # Get lead first to get ObjectId
            lead = await db.leads.find_one({"lead_id": lead_id})
            if not lead:
                raise ValueError(f"Lead {lead_id} not found")
            
            # Build query using lead ObjectId
            query = {"lead_object_id": lead["_id"]}
            
            # Role-based filtering
            if user_role != "admin":
                query["$or"] = [
                    {"assigned_to": user_id},
                    {"created_by": ObjectId(user_id)}
                ]
            
            # Status filtering
            if status_filter and status_filter != "all":
                if status_filter == "overdue":
                    query["status"] = "overdue"
                elif status_filter == "due_today":
                    today = date.today().isoformat()
                    query["due_date"] = today
                    query["status"] = {"$nin": ["completed", "cancelled"]}
                elif status_filter == "pending":
                    query["status"] = {"$in": ["pending", "in_progress"]}
                else:
                    query["status"] = status_filter
            
            logger.info(f"Query: {query}")
            
            # Get tasks
            tasks_cursor = db.lead_tasks.find(query).sort("created_at", -1)
            tasks = await tasks_cursor.to_list(None)
            
            logger.info(f"Found {len(tasks)} tasks")
            
            # 🔧 FIX: Populate user names for each task
            enriched_tasks = []
            for task in tasks:
                # Convert ObjectIds to strings and add user names
                task["id"] = str(task["_id"])
                task["created_by"] = str(task["created_by"])  # Convert ObjectId to string
                task["lead_object_id"] = str(task["lead_object_id"])
                
                # 🔑 Get creator name
                try:
                    creator = await db.users.find_one({"_id": ObjectId(task["created_by"])})
                    if creator:
                        first_name = creator.get('first_name', '')
                        last_name = creator.get('last_name', '')
                        if first_name and last_name:
                            task["created_by_name"] = f"{first_name} {last_name}".strip()
                        else:
                            task["created_by_name"] = creator.get('email', 'Unknown User')
                    else:
                        task["created_by_name"] = "Unknown User"
                except Exception as e:
                    logger.warning(f"Could not get creator name for task {task['id']}: {e}")
                    task["created_by_name"] = "Unknown User"
                
                # 🔑 Get assigned user name (if exists)
                if task.get("assigned_to"):
                    try:
                        assigned_user = await db.users.find_one({"_id": ObjectId(task["assigned_to"])})
                        if assigned_user:
                            first_name = assigned_user.get('first_name', '')
                            last_name = assigned_user.get('last_name', '')
                            if first_name and last_name:
                                task["assigned_to_name"] = f"{first_name} {last_name}".strip()
                            else:
                                task["assigned_to_name"] = assigned_user.get('email', 'Unknown User')
                    except Exception as e:
                        logger.warning(f"Could not get assigned user name: {e}")
                
                # Add overdue status
                if task.get("due_datetime") and task["status"] not in ["completed", "cancelled"]:
                    task["is_overdue"] = task["due_datetime"] < datetime.utcnow()
                else:
                    task["is_overdue"] = False
                
                enriched_tasks.append(task)
            
            return {
                "tasks": enriched_tasks,
                "total": len(enriched_tasks),
                "stats": {}  # Can add stats here if needed
            }
            
        except Exception as e:
            logger.error(f"Error getting lead tasks: {str(e)}")
            raise Exception(f"Failed to get lead tasks: {str(e)}")

    async def get_task_by_id(self, task_id: str, user_id: str, user_role: str) -> Optional[Dict[str, Any]]:
        """Get a specific task by ID - simple working version"""
        print("=" * 50)
        print(f"GET_TASK_BY_ID CALLED!")
        print(f"Task ID: {task_id}")
        print(f"User ID: {user_id}")
        print(f"User Role: {user_role}")
        print("=" * 50)
        
        try:
            print("Step 1: Getting database...")
            db = get_database()
            print("Step 1: ✅ Database connection successful")
            
            print("Step 2: Converting task_id to ObjectId...")
            task_obj_id = ObjectId(task_id)
            print(f"Step 2: ✅ ObjectId: {task_obj_id}")
            
            print("Step 3: Querying database...")
            task = await db.lead_tasks.find_one({"_id": task_obj_id})
            print(f"Step 3: Task found: {task is not None}")
            
            if not task:
                print("Step 3: ❌ Task not found")
                return None
            
            print("Step 4: Processing task...")
            result = {
                "id": str(task["_id"]),
                "task_title": task.get("task_title"),
                "lead_id": task.get("lead_id"), 
                "status": task.get("status"),
                "created_by": str(task.get("created_by", "")),
                "assigned_to": task.get("assigned_to", ""),
                "created_by_name": "Debug User",
                "assigned_to_name": "Debug Assignee", 
                "is_overdue": False,
                "debug": "simple_version"
            }
            
            print("Step 4: ✅ Task processed successfully")
            print(f"Result keys: {list(result.keys())}")
            return result
            
        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            print(f"ERROR TYPE: {type(e)}")
            import traceback
            print(f"TRACEBACK: {traceback.format_exc()}")
            raise e

    async def update_task(self, task_id: str, task_data: TaskUpdate, user_id: str, user_role: str) -> bool:
        """Update a task"""
        try:
            db = get_database()  # ✅ No await
            
            # Build query with access control
            query = {"_id": ObjectId(task_id)}
            if user_role != "admin":
                query["$or"] = [
                    {"assigned_to": user_id},
                    {"created_by": ObjectId(user_id)}
                ]
            
            # Get current task
            current_task = await db.lead_tasks.find_one(query)
            if not current_task:
                return False
            
            # Prepare update data
            update_data = {}
            for field, value in task_data.dict(exclude_unset=True).items():
                if value is not None:
                    if field == "due_date" and isinstance(value, date):
                        update_data[field] = value.isoformat()
                    elif field == "due_time" and isinstance(value, time):
                        update_data[field] = value.isoformat()
                    else:
                        update_data[field] = value
            
            update_data["updated_at"] = datetime.utcnow()
            
            # Update task
            result = await db.lead_tasks.update_one(query, {"$set": update_data})
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error updating task: {str(e)}")
            return False

    async def complete_task(self, task_id: str, completion_notes: Optional[str], user_id: str, user_role: str) -> bool:
        """Mark task as completed"""
        try:
            db = get_database()  # ✅ No await
            
            # Build query with access control
            query = {"_id": ObjectId(task_id)}
            if user_role != "admin":
                query["$or"] = [
                    {"assigned_to": user_id},
                    {"created_by": ObjectId(user_id)}
                ]
            
            # Update task
            update_data = {
                "status": "completed",
                "completed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            if completion_notes:
                update_data["completion_notes"] = completion_notes
            
            result = await db.lead_tasks.update_one(query, {"$set": update_data})
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error completing task: {str(e)}")
            return False
    
    async def delete_task(self, task_id: str, user_id: str, user_role: str) -> bool:
        """Delete a task"""
        try:
            db = get_database()  # ✅ No await
            
            # Build query with access control
            query = {"_id": ObjectId(task_id)}
            if user_role != "admin":
                query["created_by"] = ObjectId(user_id)  # Only creator can delete
            
            result = await db.lead_tasks.delete_one(query)
            return result.deleted_count > 0
            
        except Exception as e:
            logger.error(f"Error deleting task: {str(e)}")
            return False
    
    async def get_user_tasks(self, user_id: str, status_filter: Optional[str] = None) -> Dict[str, Any]:
        """Get all tasks assigned to a user across all leads"""
        try:
            db = get_database()  # ✅ No await
            
            query = {"assigned_to": user_id}
            
            if status_filter and status_filter != "all":
                if status_filter == "overdue":
                    query["status"] = "overdue"
                elif status_filter == "due_today":
                    today = date.today().isoformat()
                    query["due_date"] = today
                    query["status"] = {"$nin": ["completed", "cancelled"]}
                else:
                    query["status"] = status_filter
            
            tasks_cursor = db.lead_tasks.find(query).sort("due_datetime", 1)
            tasks = await tasks_cursor.to_list(None)
            
            # Convert ObjectIds to strings and add user names
            enriched_tasks = []
            for task in tasks:
                task["id"] = str(task["_id"])
                task["created_by"] = str(task["created_by"])
                task["lead_object_id"] = str(task["lead_object_id"])
                
                # Add creator name
                try:
                    creator = await db.users.find_one({"_id": ObjectId(task["created_by"])})
                    if creator:
                        first_name = creator.get('first_name', '')
                        last_name = creator.get('last_name', '')
                        if first_name and last_name:
                            task["created_by_name"] = f"{first_name} {last_name}".strip()
                        else:
                            task["created_by_name"] = creator.get('email', 'Unknown User')
                    else:
                        task["created_by_name"] = "Unknown User"
                except Exception as e:
                    task["created_by_name"] = "Unknown User"
                
                # Add overdue status
                if task.get("due_datetime") and task["status"] not in ["completed", "cancelled"]:
                    task["is_overdue"] = task["due_datetime"] < datetime.utcnow()
                else:
                    task["is_overdue"] = False
                
                enriched_tasks.append(task)
            
            return {
                "tasks": enriched_tasks,
                "total": len(enriched_tasks)
            }
            
        except Exception as e:
            logger.error(f"Error getting user tasks: {str(e)}")
            return {"tasks": [], "total": 0}
    
    async def _calculate_task_stats(self, lead_id: str, user_id: str, user_role: str) -> Dict[str, int]:
        """Calculate task statistics for a lead"""
        try:
            db = get_database()  # ✅ No await
            
            # Get lead ObjectId
            lead = await db.leads.find_one({"lead_id": lead_id})
            if not lead:
                return {}
            
            # Build base query
            base_query = {"lead_object_id": lead["_id"]}
            if user_role != "admin":
                base_query["$or"] = [
                    {"assigned_to": user_id},
                    {"created_by": ObjectId(user_id)}
                ]
            
            # Calculate various stats
            total_tasks = await db.lead_tasks.count_documents(base_query)
            
            pending_query = {**base_query, "status": {"$in": ["pending", "in_progress"]}}
            pending_tasks = await db.lead_tasks.count_documents(pending_query)
            
            overdue_query = {**base_query, "status": "overdue"}
            overdue_tasks = await db.lead_tasks.count_documents(overdue_query)
            
            today = date.today().isoformat()
            due_today_query = {
                **base_query,
                "due_date": today,
                "status": {"$nin": ["completed", "cancelled"]}
            }
            due_today = await db.lead_tasks.count_documents(due_today_query)
            
            completed_query = {**base_query, "status": "completed"}
            completed_tasks = await db.lead_tasks.count_documents(completed_query)
            
            return {
                "total_tasks": total_tasks,
                "pending_tasks": pending_tasks,
                "overdue_tasks": overdue_tasks,
                "due_today": due_today,
                "completed_tasks": completed_tasks
            }
            
        except Exception as e:
            logger.error(f"Error calculating task stats: {str(e)}")
            return {}

# Global service instance
task_service = TaskService()