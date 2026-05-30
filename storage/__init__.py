"""
Storage module for ImperialReminder Bot

Provides MongoDB-backed database management, guild configuration, caching, and
collection access. Mirrors the storage layer convention used across the
Empire of Shadows ecosystem (TheCodex / TheHost).
"""

from storage.database_manager import db_manager, DatabaseManager
from storage.config_manager import (
    GuildConfig,
    GuildConfigManager,
    get_guild_config_manager,
)
from storage.core.collection_manager import CollectionManager
from storage.core.collection_config import CollectionConfig
from storage.core.connection_pool import ConnectionPool

__all__ = [
    "db_manager",
    "DatabaseManager",
    "GuildConfig",
    "GuildConfigManager",
    "get_guild_config_manager",
    "CollectionManager",
    "CollectionConfig",
    "ConnectionPool",
]
