from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from enum import Enum

class TaskType(str, Enum):
    """Task type enumeration"""
    CALL = "call"
    EMAIL = "email"
    MEETING = "meeting"
    WHASTSAPP_FOLLOWUP = "whatsapp_followup"
    FOLLOW_UP = "follow_up"
    DOCUMENT_REVIEW = "document_review"
    REMINDER = "reminder"
    OTHER = "other"

class TaskStatus(str, Enum):
    """Task status enumeration"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"

class TaskPriority(str, Enum):
    """Task priority enumeration"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class TaskBase(BaseModel):
    """Base task model"""
    task_title: str = Field(..., min_length=1, max_length=200)
    task_description: Optional[str] = Field(None, max_length=1000)
    task_type: TaskType = TaskType.OTHER
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_to: Optional[str] = None  # User ID
    due_date: Optional[date] = None
    due_time: Optional[str] = Field(None, pattern=r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$')  # Fixed pattern
    notes: Optional[str] = Field(None, max_length=500)

class TaskCreate(TaskBase):
    """Task creation model"""
    class Config:
        json_schema_extra = {
            "example": {
                "task_title": "Call the prospect",
                "task_description": "Initial contact call to discuss requirements and answer questions",
                "task_type": "call",
                "priority": "medium",
                "assigned_to": "6853b46a94c81d9328a29e82",
                "due_date": "2025-06-20",
                "due_time": "14:00",
                "notes": "Student interested in engineering programs"
            }
        }

class TaskUpdate(BaseModel):
    """Task update model"""
    task_title: Optional[str] = Field(None, min_length=1, max_length=200)
    task_description: Optional[str] = Field(None, max_length=1000)
    task_type: Optional[TaskType] = None
    priority: Optional[TaskPriority] = None
    assigned_to: Optional[str] = None
    due_date: Optional[date] = None
    due_time: Optional[str] = Field(None, pattern=r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$')  # Fixed pattern
    status: Optional[TaskStatus] = None
    notes: Optional[str] = Field(None, max_length=500)

class TaskResponse(TaskBase):
    """Task response model"""
    id: str
    lead_id: str
    status: TaskStatus
    assigned_to_name: Optional[str] = None
    created_by: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    is_overdue: bool = False

    class Config:
        from_attributes = True

class TaskListResponse(BaseModel):
    """Task list response model"""
    tasks: List[TaskResponse]
    total: int
    stats: dict  # {total_tasks: 5, overdue_tasks: 2, due_today: 1, completed: 1}

class TaskStatsResponse(BaseModel):
    """Task statistics response"""
    total_tasks: int = 0
    pending_tasks: int = 0
    overdue_tasks: int = 0
    due_today: int = 0
    completed_tasks: int = 0
    in_progress_tasks: int = 0

class TaskCompleteRequest(BaseModel):
    """Task completion request"""
    completion_notes: Optional[str] = Field(None, max_length=500)

class TaskBulkAction(BaseModel):
    """Bulk task action"""
    task_ids: List[str]
    action: str  # "complete", "delete", "reassign"
    assigned_to: Optional[str] = None  # For reassign action
    notes: Optional[str] = None