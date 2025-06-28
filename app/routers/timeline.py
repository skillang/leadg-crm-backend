# app/routers/timeline.py - FIXED VERSION
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from app.utils.dependencies import get_current_user
from app.config.database import get_database
from bson import ObjectId
import logging

router = APIRouter(prefix="/timeline", tags=["timeline"])
logger = logging.getLogger(__name__)

# Timeline activity types (content-focused)
TIMELINE_CONTENT_ACTIVITIES = [
    # Task activities
    "task_created", 
    "task_completed", 
    "task_updated", 
    "task_deleted",
    
    # Document activities
    "document_uploaded",
    "document_approved", 
    "document_rejected",
    "document_deleted",
    
    # Note activities
    "note_added",
    "note_updated", 
    "note_deleted"
]

def convert_objectid_to_str(obj):
    """Recursively convert ObjectId to string in any data structure"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: convert_objectid_to_str(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid_to_str(item) for item in obj]
    else:
        return obj

@router.get("/debug/test/{lead_id}")
async def debug_timeline_data(lead_id: str):
    """
    Debug endpoint to test your data structure - FIXED ObjectId serialization
    """
    try:
        db = get_database()
        
        # Test the exact query
        query = {
            "lead_id": lead_id,
            "activity_type": {"$in": TIMELINE_CONTENT_ACTIVITIES}
        }
        
        count = await db.lead_activities.count_documents(query)
        
        # Get sample activities and convert ObjectIds to strings
        sample = []
        async for activity in db.lead_activities.find(query).limit(3):
            # Convert ObjectIds to strings for JSON serialization
            converted_activity = convert_objectid_to_str(activity)
            sample.append(converted_activity)
        
        # Also test getting one raw activity to see full structure
        raw_activity = await db.lead_activities.find_one({})
        converted_raw = convert_objectid_to_str(raw_activity) if raw_activity else None
        
        return {
            "success": True,
            "lead_id": lead_id,
            "query_used": query,
            "count_found": count,
            "sample_activities": sample,
            "raw_activity_example": converted_raw,
            "filtered_activity_types": TIMELINE_CONTENT_ACTIVITIES,
            "debug_info": {
                "total_activities_in_db": await db.lead_activities.count_documents({}),
                "activities_for_this_lead": await db.lead_activities.count_documents({"lead_id": lead_id}),
                "all_activity_types_for_lead": await get_activity_types_for_lead(db, lead_id)
            }
        }
        
    except Exception as e:
        logger.error(f"Debug endpoint error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "lead_id": lead_id,
            "error_type": type(e).__name__
        }

async def get_activity_types_for_lead(db, lead_id: str):
    """Get all activity types for a specific lead"""
    try:
        pipeline = [
            {"$match": {"lead_id": lead_id}},
            {"$group": {"_id": "$activity_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        
        activity_types = []
        async for result in db.lead_activities.aggregate(pipeline):
            activity_types.append({
                "activity_type": result["_id"],
                "count": result["count"]
            })
        
        return activity_types
    except Exception as e:
        logger.error(f"Error getting activity types: {str(e)}")
        return []

@router.get("/leads/{lead_id}")
async def get_lead_timeline(
    lead_id: str,
    current_user: dict = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    activity_type: Optional[str] = Query(None, description="Filter by activity type"),
    date_from: Optional[str] = Query(None, description="Start date (ISO format)"),
    date_to: Optional[str] = Query(None, description="End date (ISO format)"),
    search: Optional[str] = Query(None, description="Search in descriptions")
):
    """
    Get Timeline for a specific lead - CONTENT ACTIVITIES ONLY
    """
    try:
        # Check lead access permissions
        await check_lead_access(lead_id, current_user)
        
        db = get_database()
        
        # Build base query - ONLY content activities for this lead
        query = {
            "lead_id": lead_id,
            "activity_type": {"$in": TIMELINE_CONTENT_ACTIVITIES}
        }
        
        # Add activity type filter
        if activity_type and activity_type in TIMELINE_CONTENT_ACTIVITIES:
            query["activity_type"] = activity_type
        
        # Add date range filter
        if date_from or date_to:
            date_filter = {}
            if date_from:
                try:
                    date_filter["$gte"] = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid date_from format")
            if date_to:
                try:
                    date_filter["$lte"] = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid date_to format")
            query["created_at"] = date_filter
        
        # Add search filter
        if search:
            query["description"] = {"$regex": search, "$options": "i"}
        
        # Calculate pagination
        skip = (page - 1) * limit
        
        # Get total count for pagination
        total_count = await db.lead_activities.count_documents(query)
        
        # Get activities with sorting (newest first)
        activities = []
        async for activity in db.lead_activities.find(query).sort("created_at", -1).skip(skip).limit(limit):
            formatted_activity = format_timeline_activity(activity)
            activities.append(formatted_activity)
        
        return {
            "success": True,
            "lead_id": lead_id,
            "timeline": activities,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_count,
                "pages": (total_count + limit - 1) // limit if total_count > 0 else 0,
                "has_next": page * limit < total_count,
                "has_prev": page > 1
            },
            "filters": {
                "activity_type": activity_type,
                "date_from": date_from,
                "date_to": date_to,
                "search": search
            },
            "summary": {
                "total_activities": total_count,
                "activity_types_available": TIMELINE_CONTENT_ACTIVITIES
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Timeline error for lead {lead_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Timeline fetch failed: {str(e)}")

@router.get("/leads/{lead_id}/stats")
async def get_timeline_stats(
    lead_id: str,
    current_user: dict = Depends(get_current_user),
    days: int = Query(30, ge=1, le=365, description="Stats for last N days")
):
    """
    Get timeline statistics for a lead
    """
    try:
        await check_lead_access(lead_id, current_user)
        
        db = get_database()
        
        # Date range for stats
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Aggregation pipeline for stats
        pipeline = [
            {
                "$match": {
                    "lead_id": lead_id,
                    "activity_type": {"$in": TIMELINE_CONTENT_ACTIVITIES},
                    "created_at": {"$gte": start_date}
                }
            },
            {
                "$group": {
                    "_id": "$activity_type",
                    "count": {"$sum": 1},
                    "latest": {"$max": "$created_at"}
                }
            }
        ]
        
        stats = {}
        async for stat in db.lead_activities.aggregate(pipeline):
            stats[stat["_id"]] = {
                "count": stat["count"],
                "latest": stat["latest"].isoformat() if stat["latest"] else None
            }
        
        # Calculate totals by category
        task_count = sum(stats.get(activity, {}).get("count", 0) 
                        for activity in TIMELINE_CONTENT_ACTIVITIES 
                        if activity.startswith("task_"))
        
        document_count = sum(stats.get(activity, {}).get("count", 0) 
                           for activity in TIMELINE_CONTENT_ACTIVITIES 
                           if activity.startswith("document_"))
        
        note_count = sum(stats.get(activity, {}).get("count", 0) 
                        for activity in TIMELINE_CONTENT_ACTIVITIES 
                        if activity.startswith("note_"))
        
        return {
            "success": True,
            "lead_id": lead_id,
            "period_days": days,
            "stats": stats,
            "summary": {
                "total_activities": task_count + document_count + note_count,
                "tasks": task_count,
                "documents": document_count,
                "notes": note_count
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Timeline stats error for lead {lead_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/activity-types")
async def get_timeline_activity_types():
    """
    Get available activity types for timeline filtering
    """
    return {
        "timeline_activities": TIMELINE_CONTENT_ACTIVITIES,
        "categories": {
            "tasks": [act for act in TIMELINE_CONTENT_ACTIVITIES if act.startswith("task_")],
            "documents": [act for act in TIMELINE_CONTENT_ACTIVITIES if act.startswith("document_")],
            "notes": [act for act in TIMELINE_CONTENT_ACTIVITIES if act.startswith("note_")]
        },
        "display_info": get_all_activity_display_info()
    }

def format_timeline_activity(activity: dict) -> dict:
    """
    Format activity for timeline display - FIXED ObjectId handling
    """
    activity_type = activity["activity_type"]
    
    # Get display information
    display_info = get_activity_display_info(activity_type)
    
    # Format time displays
    created_at = activity["created_at"]
    
    # Convert ObjectId fields to strings
    formatted = {
        "id": str(activity["_id"]),
        "activity_type": activity_type,
        "description": activity["description"],
        "created_by_name": activity.get("created_by_name", "Unknown User"),
        "created_by_id": str(activity["created_by"]) if activity.get("created_by") else None,
        "created_at": created_at.isoformat(),
        "date_display": format_date_display(created_at),
        "time_display": format_time_display(created_at),
        "is_system_generated": activity.get("is_system_generated", True),
        "metadata": convert_objectid_to_str(activity.get("metadata", {})),  # Convert ObjectIds in metadata
        "display": {
            "icon": display_info["icon"],
            "color": display_info["color"],
            "category": display_info["category"],
            "priority": display_info["priority"]
        }
    }
    
    return formatted

def get_activity_display_info(activity_type: str) -> dict:
    """
    Get display information for activity types
    """
    display_map = {
        # Task activities
        "task_created": {
            "icon": "📝",
            "color": "blue",
            "category": "tasks",
            "priority": 1
        },
        "task_completed": {
            "icon": "✅",
            "color": "green", 
            "category": "tasks",
            "priority": 2
        },
        "task_updated": {
            "icon": "✏️",
            "color": "orange",
            "category": "tasks", 
            "priority": 3
        },
        "task_deleted": {
            "icon": "🗑️",
            "color": "red",
            "category": "tasks",
            "priority": 4
        },
        
        # Document activities
        "document_uploaded": {
            "icon": "📄",
            "color": "purple",
            "category": "documents",
            "priority": 1
        },
        "document_approved": {
            "icon": "✅",
            "color": "green",
            "category": "documents",
            "priority": 2
        },
        "document_rejected": {
            "icon": "❌", 
            "color": "red",
            "category": "documents",
            "priority": 3
        },
        "document_deleted": {
            "icon": "🗑️",
            "color": "red",
            "category": "documents",
            "priority": 4
        },
        
        # Note activities
        "note_added": {
            "icon": "📝",
            "color": "indigo",
            "category": "notes",
            "priority": 1
        },
        "note_updated": {
            "icon": "✏️",
            "color": "yellow",
            "category": "notes",
            "priority": 2
        },
        "note_deleted": {
            "icon": "🗑️",
            "color": "red", 
            "category": "notes",
            "priority": 3
        }
    }
    
    return display_map.get(activity_type, {
        "icon": "📌",
        "color": "gray",
        "category": "other",
        "priority": 99
    })

def get_all_activity_display_info() -> dict:
    """
    Get display info for all activity types
    """
    return {activity_type: get_activity_display_info(activity_type) 
            for activity_type in TIMELINE_CONTENT_ACTIVITIES}

def format_date_display(dt: datetime) -> str:
    """
    Format date for human-readable display
    """
    now = datetime.utcnow()
    diff = now - dt
    
    if diff.days == 0:
        return "Today"
    elif diff.days == 1:
        return "Yesterday"
    elif diff.days < 7:
        return f"{diff.days} days ago"
    elif diff.days < 30:
        weeks = diff.days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    else:
        return dt.strftime("%b %d, %Y")

def format_time_display(dt: datetime) -> str:
    """
    Format time for display
    """
    return dt.strftime("%I:%M %p")

async def check_lead_access(lead_id: str, current_user: dict):
    """
    Check if user has access to this lead
    """
    db = get_database()
    
    # Get lead
    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Check permissions
    user_role = current_user.get("role", "user")
    user_email = current_user.get("email") or str(current_user.get("user_id") or current_user.get("_id"))
    
    if user_role != "admin":
        # Regular users can only access leads assigned to them
        lead_assigned_to = lead.get("assigned_to", "")
        if lead_assigned_to != user_email:
            raise HTTPException(
                status_code=403, 
                detail="Not authorized to access this lead"
            )
    
    return lead