"""Setup gate seam - ImperialReminder (bot-owned, NOT vendored).

The cached "is this guild configured enough?" check, now backed by the engine
``storage.services.setup_gate.SetupGate`` (bounded TimedLRUCache, miss-vs-False
sentinel, fail-open on loader errors). This seam keeps the pre-migration public API
(singleton ``setup_gatekeeper`` with ``set_config_manager`` / ``is_setup_complete`` /
``check_or_notify`` / ``invalidate``) and the discord-facing notify embed, which the
engine deliberately does not carry.

Requirement: a bump channel AND a bump role must be configured
(``require_all("bump_channel", "bump_role")``).
"""

from typing import Optional

import discord

from storage.log import get_logger
from storage.services.setup_gate import SetupGate, require_all

logger = get_logger("setup_gatekeeper")


class SetupGatekeeper:
    """Guards bot functionality behind a minimum setup requirement (Bump Channel & Role)."""

    def __init__(self):
        self._gate: Optional[SetupGate] = None

    def set_config_manager(self, config_manager) -> None:
        """Wire the guild config manager in; builds the engine gate over it."""
        async def _load(guild_id):
            config = await config_manager.get_config(int(guild_id))
            return config.to_dict()

        self._gate = SetupGate(
            _load,
            require_all("bump_channel", "bump_role"),
            max_size=200,
            ttl=120,
        )
        logger.info("SetupGatekeeper linked to GuildConfigManager (engine SetupGate)")

    async def is_setup_complete(self, guild_id: int) -> bool:
        if self._gate is None:
            return True  # not wired yet - fail open, same as before
        return await self._gate.is_complete(guild_id)

    async def check_or_notify(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return True
        if await self.is_setup_complete(interaction.guild.id):
            return True

        embed = discord.Embed(
            title="Setup Required",
            description=(
                "Reminders are disabled until setup is complete.\n\n"
                "**Required:**\n• Bump Channel\n• Bump Role\n\n**Fix:** `/admin panel`"
            ),
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False

    def invalidate(self, guild_id: int) -> None:
        if self._gate is not None:
            self._gate.invalidate(guild_id)


setup_gatekeeper = SetupGatekeeper()
