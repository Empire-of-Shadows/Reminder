"""storage_engine - collection registry + manager for ImperialReminder (bot-owned, NOT vendored).

This one file declares ImperialReminder's collections AND constructs the shared
``db_manager`` the rest of the bot imports (``from storage.settings.collections import
db_manager``). It replaces the old ``define_collections`` + ``database_properties`` +
``manager`` trio: the engine base builds its own per-collection accessor map
(``db_manager.<registry_key>``) from the registry at construction, so attribute
accessors like ``db_manager.settings_guild_data`` keep working with no properties
file.

Index shapes are carried over from the old ``define_collections.py`` and database names
are preserved, so current data (live guild settings, bump timestamps) is reused with no
migration.

ENGINE CONTRACT: the registry is a ``dict[str, CollectionConfig]`` passed as
``collection_configs=``. The dict key is the *registry key* passed to
``db_manager.get_collection_manager(key)`` and listed in ``bindings.WATCHED_COLLECTIONS``.

Template: ``EmpireSystems/Settings/storage/collections_reference.py``.
"""

from __future__ import annotations

from pymongo import IndexModel

from storage.core.collection_config import CollectionConfig
from storage.database_manager import DatabaseManagerBase
from . import bindings

# Existing database name - preserved so current data is reused (no migration).
REMINDER_DB = "ImperialReminder"


# -- ImperialReminder's collections (registry_key -> CollectionConfig) -----------
COLLECTIONS: dict[str, CollectionConfig] = {
    # Per-guild settings + bump timestamps (LIVE production data - never dropped).
    "settings_guild_data": CollectionConfig(
        name="GuildData",
        database=REMINDER_DB,
        connection="primary",
        indexes=[
            IndexModel([("premium.enabled", 1)], name="premium_enabled_idx"),
        ],
    ),
    # Entitlement-backed premium (engine ``storage.premium.PremiumManager``): raw
    # ``entitlements`` records fold into the derived ``premium_state`` doc per scope,
    # and reconcile health lives on ``bot_settings``. Indexes are owned by
    # ``PremiumManager._ensure_indexes`` (raw client), so none are declared here;
    # registering keeps the engine aware of the collections. The legacy
    # ``codes`` / ``entitlements_cache`` collections are retired (drop them
    # manually - premium data is rebuildable via manual grants).
    "entitlements": CollectionConfig(
        name="entitlements",
        database=REMINDER_DB,
        connection="primary",
        indexes=[],
    ),
    "premium_state": CollectionConfig(
        name="premium_state",
        database=REMINDER_DB,
        connection="primary",
        indexes=[],
    ),
    "premium_bot_settings": CollectionConfig(
        name="bot_settings",
        database=REMINDER_DB,
        connection="primary",
        indexes=[],
    ),
    # Admin-panel audit trail (written by the engine AuditLog service via
    # storage/audit_log.py). Collection name matches the old hand-rolled writer so
    # existing entries stay put; retention applies to new engine-written entries
    # (TTL on ``created_at``).
    "audit_log": CollectionConfig(
        name="audit_log",
        database=REMINDER_DB,
        connection="primary",
        indexes=[
            IndexModel([("guild_id", 1)], name="audit_guild_id_idx"),
            IndexModel([("created_at", 1)], name="audit_ttl",
                       expireAfterSeconds=31_536_000),  # 365 days
        ],
    ),
}


class DatabaseManager(DatabaseManagerBase):
    """ImperialReminder's MongoDB manager: engine core + the motor-era raw accessors the
    engine ``storage.premium.PremiumManager`` binds through (relay-blessed back-compat
    seam; needed by the premium consolidation phase)."""

    def get_collection(self, database_name: str, collection_name: str):
        """Back-compat alias for the engine's ``get_raw_collection`` (motor-era API)."""
        return self.get_raw_collection(database_name, collection_name)

    @property
    def db_client(self):
        """Back-compat: the primary pymongo client (the engine owns the connection pool)."""
        return self.get_client()


# -- The shared manager (constructed from bindings + the registry above) ---------
db_manager = DatabaseManager(
    primary_uri=bindings.MONGO_URIS["primary"],
    cache=bindings.build_cache(),
    watched_collections=bindings.WATCHED_COLLECTIONS,
    collection_configs=COLLECTIONS,
)
# At startup: ``await db_manager.initialize()``; at shutdown: ``await db_manager.close()``.
