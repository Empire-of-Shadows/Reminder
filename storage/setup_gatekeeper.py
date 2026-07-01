import time
from collections import OrderedDict
from typing import Any, Optional
import discord
from storage.logging import get_logger

logger = get_logger("setup_gatekeeper")

class TimedLRUCache:
    def __init__(self, max_size: int = 1000, timeout: int = 300):
        self.max_size = max_size
        self.timeout = timeout
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._timestamps: OrderedDict[str, float] = OrderedDict()

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._cache:
            if time.time() - self._timestamps[key] > self.timeout:
                self.delete(key)
                return default
            self._cache.move_to_end(key)
            self._timestamps.move_to_end(key)
            return self._cache[key]
        return default

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
            self._timestamps.move_to_end(key)
        elif len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)
            self._timestamps.popitem(last=False)
        self._cache[key] = value
        self._timestamps[key] = time.time()

    def delete(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            del self._timestamps[key]
            return True
        return False

class SetupGatekeeper:
    """Guards bot functionality behind a minimum setup requirement (Bump Channel & Role)."""
    def __init__(self):
        self._cache = TimedLRUCache(max_size=200, timeout=120)
        self._config_manager = None

    def set_config_manager(self, config_manager):
        self._config_manager = config_manager
        logger.info("SetupGatekeeper linked to GuildConfigManager")

    async def is_setup_complete(self, guild_id: int) -> bool:
        cache_key = str(guild_id)
        cached = self._cache.get(cache_key)
        if cached is not None: return cached

        try:
            if not self._config_manager: return True
            config = await self._config_manager.get_config(guild_id)
            is_complete = bool(config.bump_channel and config.bump_role)
            self._cache.set(cache_key, is_complete)
            return is_complete
        except Exception as e:
            logger.error(f"Error checking setup for {guild_id}: {e}")
            return True

    async def check_or_notify(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild: return True
        if await self.is_setup_complete(interaction.guild.id): return True

        embed = discord.Embed(
            title="Setup Required",
            description="Reminders are disabled until setup is complete.\n\n**Required:**\n• Bump Channel\n• Bump Role\n\n**Fix:** `/admin panel`",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False

    def invalidate(self, guild_id: int):
        self._cache.delete(str(guild_id))

setup_gatekeeper = SetupGatekeeper()
