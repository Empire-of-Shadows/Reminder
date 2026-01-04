"""
Broadcast System Database Storage
Handles all MongoDB operations for user subscriptions, authorizations, and broadcasts
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
from utils.logger import get_logger
from .config import (
    MAX_DM_FAILURES,
    DEFAULT_DECAY_CONFIG,
    AUDIT_LOG_RETENTION_DAYS
)

logger = get_logger("BroadcastStorage")


class BroadcastStorage:
    """Database storage handler for the broadcast system"""

    def __init__(self, mongo_uri: str):
        """
        Initialize broadcast storage

        Args:
            mongo_uri: MongoDB connection string
        """
        self.client = AsyncIOMotorClient(mongo_uri)
        self.db = self.client["ImperialReminder"]

        # Collections
        self.subscriptions = self.db["user_subscriptions"]
        self.authorizations = self.db["user_authorizations"]
        self.broadcasts = self.db["admin_broadcasts"]
        self.audit_log = self.db["broadcast_audit_log"]

        # Locks for concurrent access
        self._locks: Dict[str, asyncio.Lock] = {}

        logger.info("BroadcastStorage initialized")

    async def setup_indexes(self):
        """Create database indexes for efficient queries"""
        try:
            # Subscriptions indexes
            await self.subscriptions.create_index("guild_id")
            await self.subscriptions.create_index("user_id")
            await self.subscriptions.create_index([("guild_id", 1), ("is_subscribed", 1)])
            await self.subscriptions.create_index("left_guild_at")

            # Authorizations indexes
            await self.authorizations.create_index("user_id", unique=True)

            # Broadcasts indexes
            await self.broadcasts.create_index("guild_id")
            await self.broadcasts.create_index([("guild_id", 1), ("is_active", 1)])
            await self.broadcasts.create_index("created_by")

            # Audit log indexes (with TTL for auto-cleanup)
            # Drop existing timestamp index if it doesn't have TTL, then recreate with TTL
            try:
                existing_indexes = await self.audit_log.index_information()
                if "timestamp_1" in existing_indexes:
                    # Check if existing index has the TTL option
                    if "expireAfterSeconds" not in existing_indexes["timestamp_1"]:
                        logger.info("Dropping existing timestamp index without TTL")
                        await self.audit_log.drop_index("timestamp_1")

                await self.audit_log.create_index(
                    "timestamp",
                    expireAfterSeconds=AUDIT_LOG_RETENTION_DAYS * 24 * 60 * 60
                )
            except Exception as idx_error:
                logger.warning(f"Could not setup timestamp TTL index: {idx_error}")

            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}", exc_info=True)

    def _get_lock(self, key: str) -> asyncio.Lock:
        """Get or create a lock for a specific key"""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    # ==================== USER SUBSCRIPTIONS ====================

    async def get_subscription(self, guild_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a user's subscription for a specific guild"""
        subscription_id = f"{guild_id}_{user_id}"
        return await self.subscriptions.find_one({"_id": subscription_id})

    async def create_subscription(self, guild_id: int, user_id: int, verified: bool = False) -> str:
        """
        Create or update a user subscription

        Args:
            guild_id: Guild ID
            user_id: User ID
            verified: Whether user has authorized the app

        Returns:
            Subscription ID
        """
        subscription_id = f"{guild_id}_{user_id}"

        async with self._get_lock(subscription_id):
            await self.subscriptions.update_one(
                {"_id": subscription_id},
                {
                    "$set": {
                        "guild_id": guild_id,
                        "user_id": user_id,
                        "is_subscribed": True,
                        "subscribed_at": datetime.utcnow(),
                        "last_dm_sent": None,
                        "dm_failures": 0,
                        "left_guild_at": None
                    },
                    "$setOnInsert": {
                        "created_at": datetime.utcnow()
                    }
                },
                upsert=True
            )

        logger.info(f"Subscription created: {subscription_id} (verified={verified})")
        return subscription_id

    async def deactivate_subscription(
        self,
        guild_id: int,
        user_id: int,
        reason: str = "manual"
    ):
        """
        Deactivate a user's subscription

        Args:
            guild_id: Guild ID
            user_id: User ID
            reason: Reason for deactivation (manual, left_guild, dm_failures)
        """
        subscription_id = f"{guild_id}_{user_id}"

        update_data = {
            "is_subscribed": False,
            "deactivated_at": datetime.utcnow(),
            "deactivation_reason": reason
        }

        if reason == "left_guild":
            update_data["left_guild_at"] = datetime.utcnow()

        await self.subscriptions.update_one(
            {"_id": subscription_id},
            {"$set": update_data}
        )

        logger.info(f"Subscription deactivated: {subscription_id} (reason={reason})")

    async def get_guild_subscriptions(
        self,
        guild_id: int,
        active_only: bool = True,
        verified_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all subscriptions for a guild

        Args:
            guild_id: Guild ID
            active_only: Only return active subscriptions
            verified_only: Only return verified users (who authorized the app)

        Returns:
            List of subscription documents
        """
        query = {"guild_id": guild_id}

        if active_only:
            query["is_subscribed"] = True
            query["left_guild_at"] = None

        # If verified_only, check if user has global authorization
        subscriptions = await self.subscriptions.find(query).to_list(None)

        if verified_only:
            # Filter to only verified users
            verified_subs = []
            for sub in subscriptions:
                auth = await self.get_user_authorization(sub["user_id"])
                if auth and auth.get("is_authorized"):
                    verified_subs.append(sub)
            return verified_subs

        return subscriptions

    async def increment_dm_failures(self, guild_id: int, user_id: int) -> int:
        """
        Increment DM failure counter for a subscription

        Returns:
            New failure count
        """
        subscription_id = f"{guild_id}_{user_id}"

        result = await self.subscriptions.find_one_and_update(
            {"_id": subscription_id},
            {"$inc": {"dm_failures": 1}},
            return_document=True
        )

        if result:
            failures = result.get("dm_failures", 0)

            # Auto-deactivate after max failures
            if failures >= MAX_DM_FAILURES:
                await self.deactivate_subscription(guild_id, user_id, reason="dm_failures")
                logger.warning(f"Auto-deactivated subscription {subscription_id} after {failures} failures")

            return failures

        return 0

    async def reset_dm_failures(self, guild_id: int, user_id: int):
        """Reset DM failure counter after successful send"""
        subscription_id = f"{guild_id}_{user_id}"

        await self.subscriptions.update_one(
            {"_id": subscription_id},
            {
                "$set": {
                    "dm_failures": 0,
                    "last_dm_sent": datetime.utcnow()
                }
            }
        )

    # ==================== USER AUTHORIZATIONS ====================

    async def get_user_authorization(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user's global authorization status"""
        return await self.authorizations.find_one({"_id": str(user_id)})

    async def create_user_authorization(self, user_id: int, guild_id: int):
        """
        Mark user as authorized (completed app installation)

        Args:
            user_id: User ID
            guild_id: Guild where they first authorized
        """
        user_id_str = str(user_id)

        await self.authorizations.update_one(
            {"_id": user_id_str},
            {
                "$set": {
                    "user_id": user_id,
                    "is_authorized": True,
                    "last_interaction": datetime.utcnow()
                },
                "$setOnInsert": {
                    "first_authorized_at": datetime.utcnow()
                },
                "$addToSet": {
                    "authorized_guilds": guild_id
                }
            },
            upsert=True
        )

        logger.info(f"User {user_id} authorized (guild {guild_id})")

    async def is_user_authorized(self, user_id: int) -> bool:
        """Check if user has completed app authorization"""
        auth = await self.get_user_authorization(user_id)
        return auth is not None and auth.get("is_authorized", False)

    # ==================== BROADCASTS ====================

    async def create_broadcast(self, data: Dict[str, Any]) -> str:
        """
        Create a new broadcast

        Args:
            data: Broadcast configuration (see schema in config.py)

        Returns:
            Broadcast ObjectId as string
        """
        # Add default decay config
        data["decay_config"] = DEFAULT_DECAY_CONFIG.copy()
        data["times_sent"] = 0
        data["acknowledged_users"] = []
        data["created_at"] = datetime.utcnow()

        result = await self.broadcasts.insert_one(data)
        broadcast_id = str(result.inserted_id)

        # Log to audit trail
        await self.log_audit_action(
            broadcast_id=broadcast_id,
            guild_id=data["guild_id"],
            admin_id=data["created_by"],
            action="created",
            message_content=data["message_content"]
        )

        logger.info(f"Broadcast created: {broadcast_id} (guild {data['guild_id']})")
        return broadcast_id

    async def get_broadcast(self, broadcast_id: str) -> Optional[Dict[str, Any]]:
        """Get broadcast by ID"""
        from bson import ObjectId
        return await self.broadcasts.find_one({"_id": ObjectId(broadcast_id)})

    async def get_guild_broadcasts(
        self,
        guild_id: int,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Get all broadcasts for a guild"""
        query = {"guild_id": guild_id}

        if active_only:
            query["is_active"] = True

        return await self.broadcasts.find(query).to_list(None)

    async def update_broadcast(self, broadcast_id: str, updates: Dict[str, Any]):
        """Update broadcast fields"""
        from bson import ObjectId

        await self.broadcasts.update_one(
            {"_id": ObjectId(broadcast_id)},
            {"$set": updates}
        )

    async def increment_broadcast_sends(self, broadcast_id: str) -> int:
        """
        Increment the send counter for a broadcast

        Returns:
            New send count
        """
        from bson import ObjectId

        result = await self.broadcasts.find_one_and_update(
            {"_id": ObjectId(broadcast_id)},
            {
                "$inc": {"times_sent": 1},
                "$set": {"last_sent": datetime.utcnow()}
            },
            return_document=True
        )

        if result:
            return result.get("times_sent", 0)
        return 0

    async def add_acknowledged_user(self, broadcast_id: str, user_id: int):
        """Add user to acknowledged list (they clicked 'Stop')"""
        from bson import ObjectId

        await self.broadcasts.update_one(
            {"_id": ObjectId(broadcast_id)},
            {"$addToSet": {"acknowledged_users": user_id}}
        )

        logger.info(f"User {user_id} acknowledged broadcast {broadcast_id}")

    async def remove_acknowledged_user(self, broadcast_id: str, user_id: int):
        """Remove user from acknowledged list (they clicked 'Resume')"""
        from bson import ObjectId

        await self.broadcasts.update_one(
            {"_id": ObjectId(broadcast_id)},
            {"$pull": {"acknowledged_users": user_id}}
        )

        logger.info(f"User {user_id} resumed broadcast {broadcast_id}")

    async def delete_broadcast(self, broadcast_id: str):
        """Delete a broadcast"""
        from bson import ObjectId

        broadcast = await self.get_broadcast(broadcast_id)
        if not broadcast:
            return

        await self.broadcasts.delete_one({"_id": ObjectId(broadcast_id)})

        # Log deletion
        await self.log_audit_action(
            broadcast_id=broadcast_id,
            guild_id=broadcast["guild_id"],
            admin_id=broadcast["created_by"],
            action="deleted"
        )

        logger.info(f"Broadcast deleted: {broadcast_id}")

    async def count_active_broadcasts(self, guild_id: int) -> int:
        """Count active broadcasts for a guild"""
        return await self.broadcasts.count_documents({
            "guild_id": guild_id,
            "is_active": True
        })

    # ==================== AUDIT LOG ====================

    async def log_audit_action(
        self,
        broadcast_id: str,
        guild_id: int,
        admin_id: int,
        action: str,
        message_content: str = None,
        recipients_count: int = 0,
        blocked_reason: str = None
    ):
        """Log broadcast action to audit trail"""
        await self.audit_log.insert_one({
            "broadcast_id": broadcast_id,
            "guild_id": guild_id,
            "admin_id": admin_id,
            "action": action,
            "message_content": message_content,
            "recipients_count": recipients_count,
            "blocked_reason": blocked_reason,
            "timestamp": datetime.utcnow()
        })

    async def log_broadcast_send(
        self,
        broadcast_id: str,
        guild_id: int,
        admin_id: int,
        successful: int,
        failed: int
    ):
        """Log a broadcast send event"""
        await self.log_audit_action(
            broadcast_id=broadcast_id,
            guild_id=guild_id,
            admin_id=admin_id,
            action="sent",
            recipients_count=successful + failed
        )

    async def get_audit_logs(
        self,
        guild_id: int = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent audit logs for a guild"""
        query = {}
        if guild_id:
            query["guild_id"] = guild_id

        return await self.audit_log.find(query).sort("timestamp", -1).limit(limit).to_list(None)

    # ==================== CLEANUP ====================

    async def cleanup_old_subscriptions(self, days: int = 90):
        """Delete subscriptions for users who left guilds more than X days ago"""
        cutoff = datetime.utcnow() - timedelta(days=days)

        result = await self.subscriptions.delete_many({
            "left_guild_at": {"$lt": cutoff}
        })

        logger.info(f"Cleaned up {result.deleted_count} old subscriptions")
        return result.deleted_count

    async def close(self):
        """Close database connection"""
        self.client.close()
        logger.info("BroadcastStorage connection closed")
