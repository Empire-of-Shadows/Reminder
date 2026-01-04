from typing import Optional, List, Dict, Any

import discord
from discord import Embed, SelectOption, Interaction
from discord.ui import View, Select

from cogs.bump.storage.database import BumpStorage
from cogs.bump.storage.config import BUMP_BOTS, BUMP_BOTS_PREMIUM, BUMP_BOTS_CHOICES
from utils.logger import get_logger

logger = get_logger("SSettingsView")

def create_settings_embed(config: Optional[Dict[str, Any]]) -> Embed:
    """Creates an embed displaying current bump settings."""
    if not config:
        return Embed(title="Bump Settings", description="No configuration found.", color=discord.Color.red())

    purple = 0x7603FF
    embed = Embed(title="Bump Settings", color=purple)

    enabled_bots = config.get("enabled_bots", [])
    bot_delays = config.get("bot_delay", {})

    for bot_name in BUMP_BOTS.keys():
        is_enabled = bot_name in enabled_bots
        delay_seconds = bot_delays.get(bot_name, BUMP_BOTS[bot_name])
        delay_hours = delay_seconds / 3600
        delay_minutes = delay_seconds / 60

        if delay_hours.is_integer():
            delay_str = f"{int(delay_hours)}h"
        else:
            delay_str = f"{int(delay_minutes)}m"

        premium_delay_seconds = BUMP_BOTS_PREMIUM.get(bot_name)
        premium_text = ""
        if premium_delay_seconds:
            premium_delay_hours = premium_delay_seconds / 3600
            premium_delay_minutes = premium_delay_seconds / 60
            if premium_delay_hours.is_integer():
                premium_delay_str = f"{int(premium_delay_hours)}h"
            else:
                premium_delay_str = f"{int(premium_delay_minutes)}m"
            premium_text = f" (Premium: {premium_delay_str})"

        embed.add_field(
            name=f"{'✅' if is_enabled else '❌'} {bot_name.capitalize()}",
            value=f"Current: **{delay_str}**{premium_text}",
            inline=True
        )

    return embed


class BumpSettingsView(View):
    """A view for managing bump settings."""

    def __init__(self, bot, guild_id: int, storage: BumpStorage):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.storage = storage
        self.selected_bot: Optional[str] = None
        self.config: Optional[Dict[str, Any]] = None

        # Add bot selection dropdown
        self.add_item(BotSelect(self))

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.guild_permissions.manage_guild

    async def refresh_view(self, interaction: Interaction):
        """Refreshes the view with updated settings."""
        self.config = await self.storage.get_guild(self.guild_id)
        embed = create_settings_embed(self.config)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class BotSelect(Select):
    """A select menu for choosing a bot to configure."""

    def __init__(self, parent_view: BumpSettingsView):
        self.parent_view = parent_view
        options = [SelectOption(label=bot.capitalize(), value=bot) for bot in BUMP_BOTS.keys()]
        super().__init__(placeholder="Select a bot to configure...", options=options)

    async def callback(self, interaction: Interaction):
        self.parent_view.selected_bot = self.values[0]

        # Remove existing delay select if present
        for item in self.parent_view.children:
            if isinstance(item, DelaySelect):
                self.parent_view.remove_item(item)

        # Add the delay select for the chosen bot
        self.parent_view.add_item(DelaySelect(self.parent_view))
        await interaction.response.edit_message(view=self.parent_view)


class DelaySelect(Select):
    """A select menu for choosing a delay for the selected bot."""

    def __init__(self, parent_view: BumpSettingsView):
        self.parent_view = parent_view
        self.selected_bot = parent_view.selected_bot

        options = []
        if self.selected_bot in BUMP_BOTS_CHOICES:
            choices = BUMP_BOTS_CHOICES[self.selected_bot]
            for label, seconds in choices.items():
                options.append(SelectOption(label=label, value=str(seconds)))

        super().__init__(placeholder=f"Select delay for {self.selected_bot.capitalize()}...", options=options)

    async def callback(self, interaction: Interaction):
        new_delay = int(self.values[0])

        try:
            await self.parent_view.storage.set_value(
                self.parent_view.guild_id,
                f"bot_delay.{self.selected_bot}",
                new_delay
            )
            logger.info(f"Updated {self.selected_bot} delay to {new_delay} for guild {self.parent_view.guild_id}")
        except Exception as e:
            logger.error(f"Failed to update delay for guild {self.parent_view.guild_id}: {e}")
            await interaction.response.send_message("Failed to update delay.", ephemeral=True)
            return

        # Refresh the view
        await self.parent_view.refresh_view(interaction)


async def setup(bot):
    logger.info("Setting up BumpSettings Cog...")
    # This cog does not need to be added to the bot as it is a view.
    # The view is instantiated and used in the config command.
    pass