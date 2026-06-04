import asyncio
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from collections import OrderedDict

from utils.logger import get_logger

logger = get_logger("GuildConfig")

# Default cooldown Timers (in seconds)
THREE_0 = 30 * 60  # 30 minutes
ONE = 60 * 60      # 1 hour
TWO = 2 * 60 * 60  # 2 hours

def _default_roles() -> Dict[str, Any]:
    """Canonical panel-role config, shared across the ecosystem dashboards."""
    return {"admin_role_ids": [], "mod_role_ids": []}


def _normalize_roles(raw: Any) -> Dict[str, Any]:
    """Coerce a stored ``roles`` value into the canonical two-list shape."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "admin_role_ids": list(raw.get("admin_role_ids") or []),
        "mod_role_ids": list(raw.get("mod_role_ids") or []),
    }


def _default_premium() -> Dict[str, Any]:
    return {
        "enabled": False,
        "activated_by": 0,
        "guild_webhook": 0,
    }

def _default_bot_delay() -> Dict[str, Any]:
    return {
        "bumpit": ONE,
        "bump4you": TWO,
        "disboard": TWO,
        "webump": TWO,
        "onebump": TWO,
        "unfocused": TWO,
    }

def _default_timestamps() -> Dict[str, Any]:
    return {
        "bumpit_timestamp": 0,
        "bump4you_timestamp": 0,
        "disboard_timestamp": 0,
        "webump_timestamp": 0,
        "onebump_timestamp": 0,
        "unfocused_timestamp": 0,
    }

DEFAULT_GUILD_CONFIG_DICT = {
    "enabled_bots": [],
    "bump_channel": 0,
    "bump_role": 0,
    "timers_channel": 0,
    "timers_message": True,
    "custom_message": "",
    "roles": _default_roles(),
    "premium": _default_premium(),
    "bot_delay": _default_bot_delay(),
    "timestamps": _default_timestamps(),
}

@dataclass
class GuildConfig:
    """Represents configuration for a single guild in ImperialReminder."""
    guild_id: int
    enabled_bots: List[str] = field(default_factory=list)
    bump_channel: int = 0
    bump_role: int = 0
    timers_channel: int = 0
    timers_message: bool = True
    custom_message: str = ""
    # Canonical panel-role config (roles.admin_role_ids / roles.mod_role_ids),
    # consumed by the dashboard to gate the Settings page.
    roles: Dict[str, Any] = field(default_factory=_default_roles)
    premium: Dict[str, Any] = field(default_factory=_default_premium)
    bot_delay: Dict[str, Any] = field(default_factory=_default_bot_delay)
    timestamps: Dict[str, Any] = field(default_factory=_default_timestamps)
    # Dynamic fields like timer_message_{channel_id} are handled in to_dict/from_dict
    extra_data: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        data = {
            "guild_id": str(self.guild_id),
            "enabled_bots": self.enabled_bots,
            "bump_channel": self.bump_channel,
            "bump_role": self.bump_role,
            "timers_channel": self.timers_channel,
            "timers_message": self.timers_message,
            "custom_message": self.custom_message,
            "roles": self.roles,
            "premium": self.premium,
            "bot_delay": self.bot_delay,
            "timestamps": self.timestamps,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        # Merge extra_data (e.g. timer_message_{channel_id})
        data.update(self.extra_data)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GuildConfig":
        """Create from dictionary (database document)."""
        guild_id = int(data.get("guild_id") or data.get("_id") or 0)
        
        # Identify extra data (keys not in standard fields)
        standard_keys = {
            "guild_id", "_id", "enabled_bots", "bump_channel", "bump_role",
            "timers_channel", "timers_message", "custom_message", "roles", "premium",
            "bot_delay", "timestamps", "created_at", "updated_at"
        }
        extra_data = {k: v for k, v in data.items() if k not in standard_keys}

        return cls(
            guild_id=guild_id,
            enabled_bots=data.get("enabled_bots", []),
            bump_channel=data.get("bump_channel", 0),
            bump_role=data.get("bump_role", 0),
            timers_channel=data.get("timers_channel", 0),
            timers_message=data.get("timers_message", True),
            custom_message=data.get("custom_message", ""),
            roles=_normalize_roles(data.get("roles")),
            premium=data.get("premium", _default_premium()),
            bot_delay=data.get("bot_delay", _default_bot_delay()),
            timestamps=data.get("timestamps", _default_timestamps()),
            extra_data=extra_data,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

class GuildConfigManager:
    """Manages per-guild configuration for ImperialReminder."""

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self._cache: Dict[int, GuildConfig] = {}
        self._cache_time: Dict[int, datetime] = {}
        self._cache_checked: Dict[int, datetime] = {}
        self._cache_grace_seconds = 30
        self._collection = None
        self._initialized = False
        self._cache_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the manager and connect to the collection."""
        if self._initialized:
            return
        try:
            self._collection = self.db_manager.get_collection_manager('settings_guild_data')
            self._initialized = True
            logger.info("GuildConfigManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize GuildConfigManager: {e}", exc_info=True)
            raise

    async def get_config(self, guild_id: int, use_cache: bool = True) -> GuildConfig:
        """Get the configuration for a guild."""
        if not self._initialized:
            await self.initialize()

        if use_cache and guild_id in self._cache:
            now = datetime.now(timezone.utc)
            last_check = self._cache_checked.get(guild_id)
            if last_check and (now - last_check).total_seconds() < self._cache_grace_seconds:
                return self._cache[guild_id]
            
            # Check for staleness
            doc_meta = await self._collection.find_one(
                {"_id": str(guild_id)}, projection={"updated_at": 1}
            )
            self._cache_checked[guild_id] = now
            db_updated = doc_meta.get("updated_at") if doc_meta else None
            if db_updated and isinstance(db_updated, datetime):
                if db_updated.tzinfo is None:
                    db_updated = db_updated.replace(tzinfo=timezone.utc)
                if db_updated > self._cache_time.get(guild_id, now):
                    logger.debug(f"Config stale for guild {guild_id}, refetching")
                else:
                    return self._cache[guild_id]
            else:
                return self._cache[guild_id]

        try:
            doc = await self._collection.find_one({"_id": str(guild_id)})

            if doc:
                config = GuildConfig.from_dict(doc)
            else:
                config = GuildConfig(guild_id=guild_id)
                logger.debug(f"Using default config for unconfigured guild {guild_id}")

            async with self._cache_lock:
                now = datetime.now(timezone.utc)
                self._cache[guild_id] = config
                self._cache_time[guild_id] = now
                self._cache_checked[guild_id] = now

            return config

        except Exception as e:
            logger.error(f"Error fetching config for guild {guild_id}: {e}", exc_info=True)
            return GuildConfig(guild_id=guild_id)

    async def save_config(self, config: GuildConfig) -> bool:
        """Save a guild's configuration to the database."""
        if not self._initialized:
            await self.initialize()

        try:
            now = datetime.now(timezone.utc)
            config.updated_at = now
            if config.created_at is None:
                config.created_at = now

            await self._collection.replace_one(
                {"_id": str(config.guild_id)},
                config.to_dict(),
                upsert=True
            )

            async with self._cache_lock:
                self._cache[config.guild_id] = config
                self._cache_time[config.guild_id] = now
                self._cache_checked[config.guild_id] = now

            return True

        except Exception as e:
            logger.error(f"Error saving config for guild {config.guild_id}: {e}", exc_info=True)
            return False

    async def set_value(self, guild_id: int, key: str, value: Any) -> bool:
        """Set a specific value for a guild."""
        if not self._initialized:
            await self.initialize()
        try:
            now = datetime.now(timezone.utc)
            await self._collection.update_one(
                {"_id": str(guild_id)},
                {
                    "$set": {key: value, "updated_at": now},
                    "$setOnInsert": {"created_at": now}
                },
                upsert=True
            )
            # Invalidate cache
            async with self._cache_lock:
                self._cache.pop(guild_id, None)
            return True
        except Exception as e:
            logger.error(f"Error setting '{key}' for guild {guild_id}: {e}", exc_info=True)
            return False

_guild_config_manager: Optional[GuildConfigManager] = None

async def get_guild_config_manager(db_manager=None) -> GuildConfigManager:
    """Get or create the global GuildConfigManager instance."""
    global _guild_config_manager
    if _guild_config_manager is None:
        if db_manager is None:
            raise ValueError("db_manager is required for first initialization")
        _guild_config_manager = GuildConfigManager(db_manager)
        await _guild_config_manager.initialize()
    return _guild_config_manager
