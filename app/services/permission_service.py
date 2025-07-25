# app/services/permission_service.py - Permission Management Service
"""
Service for managing user lead creation permissions.
Handles granting, revoking, and querying user permissions.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import HTTPException
from ..config.database import get_database
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

class PermissionService:
    """Service class for managing user permissions"""
    
    def __init__(self):
        self.db = None
    
    def _get_db(self):
        """Lazy database connection - only connect when needed"""
        if self.db is None:
            self.db = get_database()
        return self.db
    
    async def update_user_permissions(
        self, 
        user_email: str, 
        permissions: Dict[str, Any],
        admin_user: Dict[str, Any],
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update user lead creation permissions
        
        Args:
            user_email: Email of user to update
            permissions: Dict with permission flags
            admin_user: Admin user making the change
            reason: Optional reason for the change
            
        Returns:
            Dict with success status and details
        """
        try:
            logger.info(f"Updating permissions for {user_email} by {admin_user.get('email')}")
            
            db = self._get_db()  # Use lazy connection
            
            # Verify target user exists and is active
            user = await db.users.find_one({"email": user_email, "is_active": True})
            if not user:
                raise HTTPException(
                    status_code=404, 
                    detail=f"User {user_email} not found or inactive"
                )
            
            # Prevent self-permission modification
            admin_email = admin_user.get("email")
            if user_email == admin_email:
                raise HTTPException(
                    status_code=400, 
                    detail="Cannot modify your own permissions"
                )
            
            # Prevent modifying other admin permissions
            if user.get("role") == "admin":
                raise HTTPException(
                    status_code=400,
                    detail="Cannot modify permissions for admin users"
                )
            
            # Get current permissions
            current_permissions = user.get("permissions", {})
            
            # Prepare update data
            update_data = {
                "permissions.can_create_single_lead": permissions.get("can_create_single_lead", False),
                "permissions.can_create_bulk_leads": permissions.get("can_create_bulk_leads", False),
                "permissions.last_modified_by": admin_email,
                "permissions.last_modified_at": datetime.utcnow()
            }
            
            # Set granted_by and granted_at only if granting new permissions for the first time
            granting_permission = (
                permissions.get("can_create_single_lead", False) or 
                permissions.get("can_create_bulk_leads", False)
            )
            
            if granting_permission and not current_permissions.get("granted_by"):
                update_data["permissions.granted_by"] = admin_email
                update_data["permissions.granted_at"] = datetime.utcnow()
            
            # Update user permissions in database
            result = await db.users.update_one(
                {"email": user_email},
                {"$set": update_data}
            )
            
            if result.modified_count == 0:
                logger.warning(f"No changes made to permissions for {user_email}")
                return {
                    "success": True,
                    "message": "No changes were needed",
                    "user_email": user_email,
                    "permissions_changed": False
                }
            
            # Get updated user data
            updated_user = await db.users.find_one({"email": user_email})
            updated_permissions = updated_user.get("permissions", {})
            
            # Log the permission change
            await self._log_permission_change(
                user_email=user_email,
                old_permissions=current_permissions,
                new_permissions=permissions,
                admin_user=admin_user,
                reason=reason
            )
            
            logger.info(f"✅ Successfully updated permissions for {user_email}")
            
            return {
                "success": True,
                "message": "Permissions updated successfully",
                "user_email": user_email,
                "permissions_changed": True,
                "old_permissions": {
                    "can_create_single_lead": current_permissions.get("can_create_single_lead", False),
                    "can_create_bulk_leads": current_permissions.get("can_create_bulk_leads", False)
                },
                "new_permissions": {
                    "can_create_single_lead": updated_permissions.get("can_create_single_lead", False),
                    "can_create_bulk_leads": updated_permissions.get("can_create_bulk_leads", False),
                    "granted_by": updated_permissions.get("granted_by"),
                    "granted_at": updated_permissions.get("granted_at"),
                    "last_modified_by": updated_permissions.get("last_modified_by"),
                    "last_modified_at": updated_permissions.get("last_modified_at")
                }
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating permissions for {user_email}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update permissions: {str(e)}"
            )
    
    async def get_users_with_permissions(self, include_admins: bool = False) -> List[Dict[str, Any]]:
        """
        Get all users with their current permissions
        
        Args:
            include_admins: Whether to include admin users in results
            
        Returns:
            List of users with permission information
        """
        try:
            logger.info("Fetching users with permissions")
            
            db = self._get_db()  # Use lazy connection
            
            # Build query
            query = {"is_active": True}
            if not include_admins:
                query["role"] = {"$ne": "admin"}
            
            # Get users from database
            cursor = db.users.find(
                query, 
                {
                    "email": 1, 
                    "first_name": 1, 
                    "last_name": 1, 
                    "role": 1, 
                    "permissions": 1,
                    "created_at": 1,
                    "last_login": 1,
                    "departments": 1
                }
            )
            
            users = await cursor.to_list(None)
            
            # Process users and ensure permissions field exists
            processed_users = []
            for user in users:
                # Ensure permissions field exists
                if "permissions" not in user:
                    user["permissions"] = {
                        "can_create_single_lead": False,
                        "can_create_bulk_leads": False,
                        "granted_by": None,
                        "granted_at": None,
                        "last_modified_by": None,
                        "last_modified_at": None
                    }
                
                # Add computed fields
                user["_id"] = str(user["_id"])
                user["full_name"] = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                if not user["full_name"]:
                    user["full_name"] = user.get("email", "Unknown")
                
                # Add permission summary
                permissions = user.get("permissions", {})
                user["permission_summary"] = {
                    "has_any_permission": (
                        permissions.get("can_create_single_lead", False) or 
                        permissions.get("can_create_bulk_leads", False)
                    ),
                    "permission_level": self._get_permission_level(permissions),
                    "granted_by": permissions.get("granted_by"),
                    "granted_at": permissions.get("granted_at")
                }
                
                processed_users.append(user)
            
            # Sort by permission level and name
            processed_users.sort(key=lambda x: (
                x["permission_summary"]["permission_level"], 
                x["full_name"]
            ))
            
            logger.info(f"Retrieved {len(processed_users)} users with permissions")
            
            return processed_users
            
        except Exception as e:
            logger.error(f"Error fetching users with permissions: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch users: {str(e)}"
            )
    
    async def revoke_all_permissions(
        self, 
        user_email: str, 
        admin_user: Dict[str, Any],
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Revoke all lead creation permissions from a user
        
        Args:
            user_email: Email of user to revoke permissions from
            admin_user: Admin user making the change
            reason: Optional reason for revocation
            
        Returns:
            Dict with success status and details
        """
        try:
            logger.info(f"Revoking all permissions for {user_email} by {admin_user.get('email')}")
            
            # Use the update method to revoke all permissions
            result = await self.update_user_permissions(
                user_email=user_email,
                permissions={
                    "can_create_single_lead": False,
                    "can_create_bulk_leads": False
                },
                admin_user=admin_user,
                reason=reason or "All permissions revoked"
            )
            
            if result["success"]:
                result["message"] = f"All permissions revoked for {user_email}"
                logger.info(f"✅ Successfully revoked all permissions for {user_email}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error revoking permissions for {user_email}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to revoke permissions: {str(e)}"
            )
    
    async def get_permission_summary(self) -> Dict[str, Any]:
        """
        Get a summary of permission distribution across all users
        
        Returns:
            Dict with permission statistics
        """
        try:
            logger.info("Generating permission summary")
            
            db = self._get_db()  # Use lazy connection
            
            # Get all active non-admin users
            users = await db.users.find(
                {"is_active": True, "role": {"$ne": "admin"}},
                {"permissions": 1}
            ).to_list(None)
            
            # Calculate statistics
            total_users = len(users)
            users_with_single_permission = 0
            users_with_bulk_permission = 0
            users_with_any_permission = 0
            users_with_no_permissions = 0
            
            for user in users:
                permissions = user.get("permissions", {})
                can_single = permissions.get("can_create_single_lead", False)
                can_bulk = permissions.get("can_create_bulk_leads", False)
                
                if can_single:
                    users_with_single_permission += 1
                if can_bulk:
                    users_with_bulk_permission += 1
                if can_single or can_bulk:
                    users_with_any_permission += 1
                else:
                    users_with_no_permissions += 1
            
            # Calculate percentages
            def calc_percentage(count: int, total: int) -> float:
                return round((count / total * 100) if total > 0 else 0, 1)
            
            summary = {
                "total_users": total_users,
                "users_with_single_permission": users_with_single_permission,
                "users_with_bulk_permission": users_with_bulk_permission,
                "users_with_any_permission": users_with_any_permission,
                "users_with_no_permissions": users_with_no_permissions,
                "percentages": {
                    "with_single_permission": calc_percentage(users_with_single_permission, total_users),
                    "with_bulk_permission": calc_percentage(users_with_bulk_permission, total_users),
                    "with_any_permission": calc_percentage(users_with_any_permission, total_users),
                    "with_no_permissions": calc_percentage(users_with_no_permissions, total_users)
                }
            }
            
            logger.info(f"Permission summary: {users_with_any_permission}/{total_users} users have permissions")
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating permission summary: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate permission summary: {str(e)}"
            )
    
    async def _log_permission_change(
        self,
        user_email: str,
        old_permissions: Dict[str, Any],
        new_permissions: Dict[str, Any],
        admin_user: Dict[str, Any],
        reason: Optional[str] = None
    ) -> None:
        """
        Log permission changes for audit purposes
        
        Args:
            user_email: User whose permissions changed
            old_permissions: Previous permission state
            new_permissions: New permission state
            admin_user: Admin who made the change
            reason: Optional reason for the change
        """
        try:
            # Create audit log entry
            audit_entry = {
                "action": "permission_change",
                "target_user_email": user_email,
                "admin_user_email": admin_user.get("email"),
                "admin_user_name": f"{admin_user.get('first_name', '')} {admin_user.get('last_name', '')}".strip(),
                "timestamp": datetime.utcnow(),
                "changes": {
                    "old_permissions": {
                        "can_create_single_lead": old_permissions.get("can_create_single_lead", False),
                        "can_create_bulk_leads": old_permissions.get("can_create_bulk_leads", False)
                    },
                    "new_permissions": {
                        "can_create_single_lead": new_permissions.get("can_create_single_lead", False),
                        "can_create_bulk_leads": new_permissions.get("can_create_bulk_leads", False)
                    }
                },
                "reason": reason
            }
            
            db = self._get_db()  # Use lazy connection
            
            # Store in audit collection (create if doesn't exist)
            await db.permission_audit_log.insert_one(audit_entry)
            
            logger.info(f"Logged permission change for {user_email}")
            
        except Exception as e:
            logger.error(f"Failed to log permission change: {str(e)}")
            # Don't raise exception - logging failure shouldn't break permission update
    
    def _get_permission_level(self, permissions: Dict[str, Any]) -> int:
        """
        Get numeric permission level for sorting
        
        Args:
            permissions: User permissions dict
            
        Returns:
            int: Permission level (0=none, 1=single, 2=bulk, 3=both)
        """
        can_single = permissions.get("can_create_single_lead", False)
        can_bulk = permissions.get("can_create_bulk_leads", False)
        
        if can_single and can_bulk:
            return 3  # Both permissions
        elif can_bulk:
            return 2  # Bulk only
        elif can_single:
            return 1  # Single only
        else:
            return 0  # No permissions

# Create singleton instance
permission_service = PermissionService()