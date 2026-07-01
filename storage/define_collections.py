from pymongo import IndexModel
from storage.core.collection_config import CollectionConfig
from storage.logging import get_logger

logger = get_logger("DefineCollections")

class DefineCollections:
    def _define_collection_configs(self):
        """Define collection configurations including indexes for optimal performance."""

        # Guild Settings and Bump Data
        self._collection_configs['settings_guild_data'] = CollectionConfig(
            name='GuildData',
            database='ImperialReminder',
            connection='primary',
            indexes=[
                IndexModel([("premium.enabled", 1)], name="premium_enabled_idx")
            ]
        )

        # Premium Management
        self._collection_configs['premium_codes'] = CollectionConfig(
            name='codes',
            database='ImperialReminder',
            connection='primary',
            indexes=[
                IndexModel([("code", 1)], unique=True),
                IndexModel([("linked_guild", 1)]),
                IndexModel([("issued_to", 1)])
            ]
        )

        self._collection_configs['premium_entitlements'] = CollectionConfig(
            name='entitlements_cache',
            database='ImperialReminder',
            connection='primary',
            indexes=[
                IndexModel([("user_id", 1)]),
                IndexModel([("expires_at", 1)], expireAfterSeconds=0) # TTL index
            ]
        )
