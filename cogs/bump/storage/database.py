# Python
"""
Bump System Database Storage
MongoDB abstraction with atomic operations and caching
"""

import os
import asyncio
from collections import defaultdict
from copy import deepcopy
from time import time
from typing import Any, Optional, Dict, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

from utils.logger import get_logger
from .config import DEFAULT_GUILD_CONFIG

logger = get_logger("BumpStorage")
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")


def _deep_merge(default: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge default structure with a current document (non-destructive),
    preserving _id and timer_message_* keys.
    """
    result = {}
    for key, default_value in default.items():
        if isinstance(default_value, dict):
            cur_val = current.get(key)
            if isinstance(cur_val, dict):
                result[key] = _deep_merge(default_value, cur_val)
            else:
                # Copy default nested structure
                result[key] = deepcopy(default_value)
        else:
            result[key] = current.get(key, default_value)

    # Preserve special fields not in default
    for key, value in current.items():
        if key not in result and (key == "_id" or str(key).startswith("timer_message_")):
            result[key] = value

    return result


class BumpStorage:
    """
    MongoDB storage for bump tracking with atomic operations and caching.

    Features:
    - Atomic updates with $set / $unset
    - Race-free upsert of default config
    - Optional in-memory cache with TTL
    - Per-guild locks to prevent race conditions
    """

    def __init__(self, *, enable_cache: bool = True, cache_ttl_seconds: int = 30):
        self.client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        self.db = self.client["ImperialReminder"]
        self.collection = self.db["GuildData"]

        # Simple in-memory cache: guild_id -> (expires_at, config)
        self._cache_enabled = enable_cache
        self._cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

        # Kick off index creation (non-blocking)
        self._init_indexes_task = asyncio.create_task(self._ensure_indexes())

    async def _ensure_indexes(self):
        """Create database indexes for efficient queries"""
        try:
            await self.collection.create_index(
                [("premium.enabled", 1)],
                name="premium_enabled_idx"
            )
            logger.info("Bump storage indexes ensured.")
        except Exception as e:
            logger.error(f"Failed to ensure bump storage indexes: {e}", exc_info=True)

    def _now(self) -> float:
        return float(time())

    def _cache_get(self, gid: str) -> Optional[Dict[str, Any]]:
        """Get config from cache if not expired"""
        if not self._cache_enabled:
            return None
        entry = self._cache.get(gid)
        if not entry:
            return None
        exp, cfg = entry
        if self._now() <= exp:
            return deepcopy(cfg)
        # Expired
        self._cache.pop(gid, None)
        return None

    def _cache_set(self, gid: str, config: Dict[str, Any]):
        """Store config in cache with TTL"""
        if not self._cache_enabled:
            return
        self._cache[gid] = (self._now() + self._cache_ttl, deepcopy(config))

    def _cache_invalidate(self, gid: str):
        """Remove config from cache"""
        self._cache.pop(gid, None)

    async def get_guild(self, guild_id: int) -> Dict[str, Any]:
        """
        Fetch and validate a guild config. If missing, atomically insert defaults.
        Uses in-memory cache with TTL to reduce DB load.
        """
        gid = str(guild_id)

        # Cache first
        cached = self._cache_get(gid)
        if cached is not None:
            return cached

        async with self._locks[gid]:
            # Re-check cache once inside lock
            cached = self._cache_get(gid)
            if cached is not None:
                return cached

            try:
                # Atomically upsert a default doc on first access
                doc = await self.collection.find_one_and_update(
                    {"_id": gid},
                    {"$setOnInsert": dict(deepcopy(DEFAULT_GUILD_CONFIG))},
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
                # Ensure defaults are present non-destructively
                merged = _deep_merge(DEFAULT_GUILD_CONFIG, doc or {})
                self._cache_set(gid, merged)
                # If doc had missing keys, optionally persist them lazily
                if doc is not None and merged.keys() - doc.keys():
                    # Only set missing top-level keys to avoid heavy writes
                    missing = {k: merged[k] for k in merged.keys() if k not in doc}
                    if missing:
                        await self.collection.update_one({"_id": gid}, {"$set": missing})
                return merged
            except Exception as e:
                logger.error(f"Failed to fetch guild {gid} configuration: {e}", exc_info=True)
                raise

    async def set_value(self, guild_id: int, key: str, value: Any, *, allow_new: bool = True) -> bool:
        """
        Atomically set a value at a dot-path key using $set.
        If allow_new=False, will verify the path exists in the default schema.
        """
        gid = str(guild_id)
        try:
            if not allow_new and not self._path_allowed(key):
                logger.warning(f"Attempted to set undefined key (blocked): {key}")
                return False

            res = await self.collection.update_one({"_id": gid}, {"$set": {key: value}}, upsert=True)
            self._cache_invalidate(gid)
            if res.matched_count or res.upserted_id:
                logger.info(f"Set {key} for guild {gid}")
            return True
        except Exception as e:
            logger.error(f"Failed to set {key} for guild {gid}: {e}", exc_info=True)
            return False

    async def set_many(self, guild_id: int, updates: Dict[str, Any], *, allow_new: bool = True) -> bool:
        """
        Atomically set multiple dot-path keys using a single $set.
        """
        gid = str(guild_id)
        try:
            if not allow_new:
                disallowed = [k for k in updates.keys() if not self._path_allowed(k)]
                if disallowed:
                    logger.warning(f"Blocked undefined keys for guild {gid}: {disallowed}")
                    return False

            res = await self.collection.update_one({"_id": gid}, {"$set": updates}, upsert=True)
            self._cache_invalidate(gid)
            if res.matched_count or res.upserted_id:
                logger.info(f"Set {len(updates)} keys for guild {gid}")
            return True
        except Exception as e:
            logger.error(f"Failed to set many for guild {gid}: {e}", exc_info=True)
            return False

    async def delete_key(self, guild_id: int, key: str) -> bool:
        """
        Atomically unset a dot-path key.
        """
        gid = str(guild_id)
        try:
            res = await self.collection.update_one({"_id": gid}, {"$unset": {key: ""}})
            self._cache_invalidate(gid)
            if res.modified_count:
                logger.info(f"Unset {key} for guild {gid}")
            return bool(res.modified_count)
        except Exception as e:
            logger.error(f"Failed to unset {key} for guild {gid}: {e}", exc_info=True)
            return False

    async def increment(self, guild_id: int, key: str, amount: int = 1) -> Optional[int]:
        """
        Atomically increment a numeric field and return the new value.
        """
        gid = str(guild_id)
        try:
            doc = await self.collection.find_one_and_update(
                {"_id": gid},
                {"$inc": {key: amount}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            self._cache_invalidate(gid)
            # Traverse the dotted key to return the new value
            cur = doc
            for part in key.split("."):
                cur = cur.get(part, {})
            if isinstance(cur, (int, float)):
                return int(cur)
            return None
        except Exception as e:
            logger.error(f"Failed to increment {key} for guild {gid}: {e}", exc_info=True)
            return None

    async def set_guild(self, guild_id: int, key: str, value: Any):
        """
        Backward-compatible: delegates to set_value with allow_new guarding nested structure.
        """
        allow_new = not ("." in key and key.split(".")[0] not in DEFAULT_GUILD_CONFIG)
        ok = await self.set_value(guild_id, key, value, allow_new=allow_new)
        if not ok:
            raise RuntimeError(f"Failed to set key {key} for guild {guild_id}")

    async def get_value(self, guild_id: int, key: str, default: Any = None) -> Any:
        """
        Read a nested value from the cached/merged config.
        """
        cfg = await self.get_guild(guild_id)
        cur: Any = cfg
        try:
            for part in key.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return default
            return cur
        except Exception:
            return default

    async def save_bump_time(self, guild_id: int, bot_name: str):
        """Store the current time for the bump timestamp in the nested structure."""
        key = f"timestamps.{bot_name}_timestamp"
        value = int(time())
        await self.set_value(guild_id, key, value)

    async def load_bump_time(self, guild_id: int, bot_name: str) -> int:
        """Fetch the last bump time for a bot (fixed to read nested timestamps)."""
        return int(await self.get_value(guild_id, f"timestamps.{bot_name}_timestamp", 0) or 0)

    async def save_embed_message_id(self, guild_id: int, channel_id: int, message_id: Optional[int]):
        """Save the timer embed message ID for a channel"""
        await self.set_value(guild_id, f"timer_message_{channel_id}", message_id)

    async def load_embed_message_id(self, guild_id: int, channel_id: int) -> Optional[int]:
        """Load the timer embed message ID for a channel"""
        val = await self.get_value(guild_id, f"timer_message_{channel_id}")
        return int(val) if isinstance(val, int) else (None if val in (None, 0, "0") else None)

    async def cleanup_old_timestamps(self, max_age: int = 86400):
        """
        Scan documents for timestamps.*_timestamp older than max_age and unset them.
        """
        try:
            now = int(time())
            async for doc in self.collection.find({}, projection={"_id": 1, "timestamps": 1}):
                gid = doc["_id"]
                timestamps = (doc or {}).get("timestamps", {}) or {}
                to_unset = {}
                for k, v in timestamps.items():
                    if isinstance(v, int) and k.endswith("_timestamp"):
                        if now - v > max_age:
                            to_unset[f"timestamps.{k}"] = ""
                if to_unset:
                    await self.collection.update_one({"_id": gid}, {"$unset": to_unset})
                    self._cache_invalidate(gid)
                    logger.info(f"Cleaned timestamps for guild {gid}: {list(to_unset.keys())}")
        except Exception as e:
            logger.error(f"Failed cleaning old timestamps: {e}", exc_info=True)

    def _path_allowed(self, key: str) -> bool:
        """
        Validate a dot-path against DEFAULT_GUILD_CONFIG for allow_new=False operations.
        Only checks existence of the path shape, not types.
        """
        parts = key.split(".")
        cur: Any = DEFAULT_GUILD_CONFIG
        for i, part in enumerate(parts):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                # Allow dynamic timer_message_* fields at root
                if i == 0 and part.startswith("timer_message_"):
                    return True
                return False
        return True


# Initialize the MongoDB Bump Storage Manager
bump_storage = BumpStorage()
