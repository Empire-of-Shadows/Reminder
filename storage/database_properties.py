from storage.core.collection_manager import CollectionManager

class DatabaseProperties:
    @property
    def settings_guild_data(self) -> CollectionManager:
        """Get Guild Data collection manager."""
        return self.get_collection_manager('settings_guild_data')

    @property
    def premium_codes(self) -> CollectionManager:
        """Get Premium Codes collection manager."""
        return self.get_collection_manager('premium_codes')

    @property
    def premium_entitlements(self) -> CollectionManager:
        """Get Premium Entitlements collection manager."""
        return self.get_collection_manager('premium_entitlements')
