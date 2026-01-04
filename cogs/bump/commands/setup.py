import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Select, Button, Modal, TextInput, ChannelSelect, RoleSelect
from typing import List, Optional, Dict, Any

from cogs.bump.storage.database import bump_storage
from cogs.bump.storage.config import BUMP_BOTS, SUPPORTED_BOTS, BUMP_BOTS_CHOICES, BUMP_BOTS_PREMIUM
from utils.logger import get_logger

logger = get_logger("BumpCommands")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_cooldown(seconds: int) -> str:
    """
    Convert seconds to a human-readable format.

    Args:
        seconds: Number of seconds

    Returns:
        Formatted string (e.g., "2 hours", "30 minutes", "1 hour")
    """
    hours = seconds / 3600
    minutes = seconds / 60

    if hours >= 1 and hours.is_integer():
        h = int(hours)
        return f"{h} hour" if h == 1 else f"{h} hours"
    else:
        m = int(minutes)
        return f"{m} minute" if m == 1 else f"{m} minutes"


def format_bot_list(enabled_bots: List[str], config: Dict[str, Any]) -> str:
    """
    Format enabled bots with their cooldowns.

    Args:
        enabled_bots: List of enabled bot names
        config: Guild configuration dictionary

    Returns:
        Formatted string (e.g., "Disboard (2h), Bumpit (1h)")
    """
    if not enabled_bots:
        return "None"

    bot_delays = config.get("bot_delay", {})
    formatted = []

    for bot_name in enabled_bots:
        delay_seconds = bot_delays.get(bot_name, BUMP_BOTS.get(bot_name, 0))
        hours = delay_seconds / 3600
        minutes = delay_seconds / 60

        if hours >= 1 and hours.is_integer():
            delay_str = f"{int(hours)}h"
        else:
            delay_str = f"{int(minutes)}m"

        formatted.append(f"{bot_name.capitalize()} ({delay_str})")

    return ", ".join(formatted)


def create_config_embed(config: Dict[str, Any]) -> discord.Embed:
    """
    Create a detailed configuration embed (extracted from old view_config command).

    Args:
        config: Guild configuration dictionary

    Returns:
        Discord embed with full configuration
    """
    embed = discord.Embed(
        title="📋 Bump Configuration",
        color=0x7603FF
    )

    bump_channel_id = config.get("bump_channel")
    bump_role_id = config.get("bump_role")
    enabled_bots = config.get("enabled_bots", [])
    custom_message = config.get("custom_message", "")
    timers_enabled = config.get("timers_message", True)
    premium = config.get("premium", {})

    # Basic settings
    bump_channel = f"<#{bump_channel_id}>" if bump_channel_id else "Not set"
    bump_role = f"<@&{bump_role_id}>" if bump_role_id else "Not set"
    timer_channel_id = config.get("timers_channel")
    timer_channel = f"<#{timer_channel_id}>" if timer_channel_id else "Not set"

    embed.add_field(
        name="⚙️ Basic Settings",
        value=(
            f"**Bump Channel:** {bump_channel}\n"
            f"**Bump Role:** {bump_role}\n"
            f"**Timer Channel:** {timer_channel}\n"
            f"**Timer Display:** {'Enabled' if timers_enabled else 'Disabled'}"
        ),
        inline=False
    )

    # Enabled bots
    if enabled_bots:
        bot_list = ", ".join([b.capitalize() for b in enabled_bots])
    else:
        bot_list = "None (all bots disabled)"

    embed.add_field(
        name="🤖 Enabled Bots",
        value=bot_list,
        inline=False
    )

    # Custom message
    if custom_message:
        preview = custom_message if len(custom_message) <= 100 else custom_message[:97] + "..."
        embed.add_field(
            name="💬 Custom Message",
            value=f"```{preview}```",
            inline=False
        )

    # Premium status
    if premium.get("enabled"):
        embed.add_field(
            name="⭐ Premium Status",
            value=f"**Active** (activated by <@{premium.get('activated_by')}>)",
            inline=False
        )

    embed.set_footer(text="Use the dropdown menu to modify settings")

    return embed


def create_setup_menu_embed(config: Dict[str, Any]) -> discord.Embed:
    """
    Create the setup menu embed.

    Args:
        config: Guild configuration dictionary

    Returns:
        Discord embed for setup menu
    """
    embed = discord.Embed(
        title="🎉 Bump Reminder Setup",
        description="Welcome! Let's configure your bump reminders.\nSelect a setting from the dropdown below to get started.",
        color=0x7603FF
    )

    bump_channel_id = config.get("bump_channel")
    bump_role_id = config.get("bump_role")
    enabled_bots = config.get("enabled_bots", [])

    # Current configuration summary
    bump_channel = f"<#{bump_channel_id}>" if bump_channel_id else "❌ Not set"
    bump_role = f"<@&{bump_role_id}>" if bump_role_id else "❌ Not set"
    bots = format_bot_list(enabled_bots, config) if enabled_bots else "❌ None selected"

    # Check if setup is complete
    is_complete = bump_channel_id and bump_role_id

    embed.add_field(
        name="📍 Current Setup Progress",
        value=(
            f"**Bump Channel:** {bump_channel}\n"
            f"**Bump Role:** {bump_role}\n"
            f"**Enabled Bots:** {bots}"
        ),
        inline=False
    )

    if is_complete:
        embed.add_field(
            name="✅ Setup Complete!",
            value="All required settings are configured. Use `/bump settings` to customize further.",
            inline=False
        )
    else:
        embed.add_field(
            name="⚠️ Required Settings",
            value="You must configure **Bump Channel** and **Bump Role** to complete setup.",
            inline=False
        )

    return embed


def create_main_menu_embed(config: Dict[str, Any]) -> discord.Embed:
    """
    Create the main settings menu embed.

    Args:
        config: Guild configuration dictionary

    Returns:
        Discord embed for main menu
    """
    embed = discord.Embed(
        title="🔧 Bump Settings Menu",
        description="Select a setting from the dropdown below to configure it.",
        color=0x7603FF
    )

    bump_channel_id = config.get("bump_channel")
    bump_role_id = config.get("bump_role")
    timer_channel_id = config.get("timers_channel")
    timers_enabled = config.get("timers_message", True)
    custom_message = config.get("custom_message", "")
    enabled_bots = config.get("enabled_bots", [])

    # Current configuration summary
    bump_channel = f"<#{bump_channel_id}>" if bump_channel_id else "Not set"
    bump_role = f"<@&{bump_role_id}>" if bump_role_id else "Not set"
    timer_channel = f"<#{timer_channel_id}>" if timer_channel_id else "Not set"

    embed.add_field(
        name="📍 Current Configuration",
        value=(
            f"**Bump Channel:** {bump_channel}\n"
            f"**Bump Role:** {bump_role}\n"
            f"**Timer Channel:** {timer_channel}\n"
            f"**Timer Display:** {'✅ Enabled' if timers_enabled else '❌ Disabled'}\n"
            f"**Custom Message:** {'✅ Set' if custom_message else '❌ Not set'}\n"
            f"**Enabled Bots:** {format_bot_list(enabled_bots, config)}"
        ),
        inline=False
    )

    return embed


# ============================================================================
# UI COMPONENTS - SETUP MENU
# ============================================================================

class SetupCategorySelect(Select):
    """Dropdown for selecting which setting to configure during setup."""

    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label="Configure Bump Channel",
                value="bump_channel",
                emoji="🔔",
                description="Set the channel where bump commands are used"
            ),
            discord.SelectOption(
                label="Configure Bump Role",
                value="bump_role",
                emoji="👥",
                description="Set the role to ping for bump reminders"
            ),
            discord.SelectOption(
                label="Select Enabled Bots",
                value="enabled_bots",
                emoji="🤖",
                description="Choose which bots to enable for reminders"
            ),
        ]
        super().__init__(
            placeholder="Select a setting to configure...",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.route_to_setup_option(interaction, self.values[0])


class SetupChannelSelect(ChannelSelect):
    """Channel select for setup (bump or timer channel)."""

    def __init__(self, parent_view, setting_type: str):
        self.parent_view = parent_view
        self.setting_type = setting_type  # "bump_channel" or "timers_channel"

        super().__init__(
            placeholder="Select a channel...",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.text]
        )

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]

        try:
            await bump_storage.set_value(
                self.parent_view.guild_id,
                self.setting_type,
                channel.id
            )

            # If setting bump channel and timer channel is not set, also set timer channel
            if self.setting_type == "bump_channel":
                config = await bump_storage.get_guild(self.parent_view.guild_id)
                if not config.get("timers_channel"):
                    await bump_storage.set_value(
                        self.parent_view.guild_id,
                        "timers_channel",
                        channel.id
                    )

            setting_name = "Bump Channel" if self.setting_type == "bump_channel" else "Timer Channel"
            logger.info(f"[{self.parent_view.guild_id}] Setup: {self.setting_type} set to {channel.id}")

            # Immediately return to setup menu
            await self.parent_view.show_setup_menu(interaction)

        except Exception as e:
            logger.error(f"[{self.parent_view.guild_id}] Failed to set {self.setting_type}: {e}")
            await interaction.response.send_message(
                f"❌ Failed to set {setting_name}. Please try again.",
                ephemeral=True
            )


class SetupRoleSelect(RoleSelect):
    """Role select for setup (bump role)."""

    def __init__(self, parent_view):
        self.parent_view = parent_view
        super().__init__(
            placeholder="Select a role...",
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]

        try:
            await bump_storage.set_value(
                self.parent_view.guild_id,
                "bump_role",
                role.id
            )

            logger.info(f"[{self.parent_view.guild_id}] Setup: bump_role set to {role.id}")

            # Immediately return to setup menu
            await self.parent_view.show_setup_menu(interaction)

        except Exception as e:
            logger.error(f"[{self.parent_view.guild_id}] Failed to set bump_role: {e}")
            await interaction.response.send_message(
                "❌ Failed to set Bump Role. Please try again.",
                ephemeral=True
            )


class SetupBotMultiSelect(Select):
    """Multi-select for enabled bots during setup."""

    def __init__(self, parent_view, enabled_bots: List[str]):
        self.parent_view = parent_view
        options = []
        for bot_name in SUPPORTED_BOTS:
            options.append(
                discord.SelectOption(
                    label=bot_name.capitalize(),
                    value=bot_name,
                    default=(bot_name in enabled_bots)
                )
            )

        super().__init__(
            placeholder="Select which bots to enable...",
            min_values=0,
            max_values=len(SUPPORTED_BOTS),
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        # Just defer the interaction - actual submission happens via Submit button
        # This prevents "interaction failed" when user selects from dropdown
        await interaction.response.defer()
        logger.info(f"[{self.parent_view.guild_id}] User selected bots: {self.values}")


class SubmitBotsButton(Button):
    """Submit button for bot selection during setup."""

    def __init__(self, parent_view):
        super().__init__(
            label="Submit Selection",
            style=discord.ButtonStyle.success,
            emoji="✅"
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        try:
            # Defer the interaction first
            await interaction.response.defer()

            # Get the selected bots from the multi-select
            bot_select = None
            for item in self.parent_view.children:
                if isinstance(item, SetupBotMultiSelect):
                    bot_select = item
                    break

            if not bot_select:
                logger.error(f"[{self.parent_view.guild_id}] Bot selection component not found in view")
                await interaction.followup.send(
                    "❌ Error: Bot selection not found.",
                    ephemeral=True
                )
                return

            selected = bot_select.values
            logger.info(f"[{self.parent_view.guild_id}] Setup: User selected bots: {selected}")

            # Save to database
            await bump_storage.set_value(
                self.parent_view.guild_id,
                "enabled_bots",
                selected
            )

            logger.info(f"[{self.parent_view.guild_id}] Setup: enabled_bots saved to database")

            # Refresh config and update the view
            await self.parent_view.refresh_config()
            self.parent_view.clear_items()

            # Add setup dropdown and finish button
            self.parent_view.add_item(SetupCategorySelect(self.parent_view))
            self.parent_view.add_item(FinishSetupButton(self.parent_view))

            embed = create_setup_menu_embed(self.parent_view.config)

            # Edit the original message
            if self.parent_view.message:
                await self.parent_view.message.edit(embed=embed, view=self.parent_view)
                logger.info(f"[{self.parent_view.guild_id}] Setup menu refreshed successfully")
            else:
                await interaction.edit_original_response(embed=embed, view=self.parent_view)
                logger.info(f"[{self.parent_view.guild_id}] Setup menu updated via interaction")

        except Exception as e:
            logger.error(f"[{self.parent_view.guild_id}] Failed in SubmitBotsButton callback: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "❌ Failed to save bot selection. Please try again.",
                    ephemeral=True
                )
            except:
                # If followup fails, the interaction might have timed out
                logger.error(f"[{self.parent_view.guild_id}] Could not send error message to user")


class BackToSetupButton(Button):
    """Button to return to setup menu."""

    def __init__(self, parent_view):
        super().__init__(
            label="Back to Setup",
            style=discord.ButtonStyle.secondary,
            emoji="◀️"
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        # Defer the interaction
        await interaction.response.defer()

        # Refresh config and rebuild menu
        await self.parent_view.refresh_config()
        self.parent_view.clear_items()

        # Add setup dropdown and finish button
        self.parent_view.add_item(SetupCategorySelect(self.parent_view))
        self.parent_view.add_item(FinishSetupButton(self.parent_view))

        embed = create_setup_menu_embed(self.parent_view.config)

        # Edit the original message
        if self.parent_view.message:
            await self.parent_view.message.edit(embed=embed, view=self.parent_view)
        else:
            await interaction.edit_original_response(embed=embed, view=self.parent_view)


class FinishSetupButton(Button):
    """Button to finish setup and close the menu."""

    def __init__(self, parent_view):
        super().__init__(
            label="Finish Setup",
            style=discord.ButtonStyle.primary,
            emoji="✅"
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        config = await bump_storage.get_guild(self.parent_view.guild_id)

        # Check if required settings are configured
        if not config.get("bump_channel") or not config.get("bump_role"):
            await interaction.response.send_message(
                "⚠️ Please configure both **Bump Channel** and **Bump Role** before finishing setup!",
                ephemeral=True
            )
            return

        # Show completion message
        bump_channel_id = config.get("bump_channel")
        bump_role_id = config.get("bump_role")
        enabled_bots = config.get("enabled_bots", [])

        bot_list = ", ".join([b.capitalize() for b in enabled_bots]) if enabled_bots else "None (use /bump settings to enable bots)"

        embed = discord.Embed(
            title="🎉 Setup Complete!",
            description="Your bump reminders are now configured!",
            color=discord.Color.green()
        )

        embed.add_field(
            name="📍 Your Configuration",
            value=(
                f"**Bump Channel:** <#{bump_channel_id}>\n"
                f"**Bump Role:** <@&{bump_role_id}>\n"
                f"**Enabled Bots:** {bot_list}"
            ),
            inline=False
        )

        embed.add_field(
            name="🚀 What's Next?",
            value=(
                f"I'll start tracking bumps in <#{bump_channel_id}> automatically!\n\n"
                f"Use `/bump settings` to:\n"
                f"• Modify enabled bots\n"
                f"• Configure cooldown times\n"
                f"• Set custom reminder messages (Premium)\n"
                f"• Configure separate timer channel (Premium)\n"
                f"• And more!"
            ),
            inline=False
        )

        await interaction.response.edit_message(embed=embed, view=None)

        logger.info(f"[{self.parent_view.guild_id}] Setup completed")


# ============================================================================
# SETUP VIEW
# ============================================================================

class SetupView(View):
    """
    Interactive setup menu for initial bump reminder configuration.
    """

    def __init__(self, bot, guild_id: int, initial_config: Dict[str, Any]):
        super().__init__(timeout=300)  # 5 minute timeout
        self.bot = bot
        self.guild_id = guild_id
        self.config = initial_config
        self.message = None

        # Add setup dropdown and finish button
        self.add_item(SetupCategorySelect(self))
        self.add_item(FinishSetupButton(self))

    async def refresh_config(self):
        """Reload config from database."""
        self.config = await bump_storage.get_guild(self.guild_id)

    async def on_timeout(self):
        """Disable all components on timeout."""
        for item in self.children:
            item.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except:
            pass

    async def show_setup_menu(self, interaction: discord.Interaction):
        """Show the main setup menu."""
        await self.refresh_config()
        self.clear_items()

        # Add setup dropdown and finish button
        self.add_item(SetupCategorySelect(self))
        self.add_item(FinishSetupButton(self))

        embed = create_setup_menu_embed(self.config)
        await interaction.response.edit_message(embed=embed, view=self)

    async def route_to_setup_option(self, interaction: discord.Interaction, option: str):
        """Route to the selected setup option."""
        if option == "bump_channel":
            await self.show_channel_config(interaction, "bump_channel")
        elif option == "bump_role":
            await self.show_role_config(interaction)
        elif option == "enabled_bots":
            await self.show_bot_selection(interaction)

    async def show_channel_config(self, interaction: discord.Interaction, setting_type: str):
        """Show channel configuration."""
        await self.refresh_config()
        self.clear_items()

        self.add_item(SetupChannelSelect(self, setting_type))
        self.add_item(BackToSetupButton(self))

        setting_name = "Bump Channel" if setting_type == "bump_channel" else "Timer Channel"
        current_channel_id = self.config.get(setting_type)
        current_channel = f"<#{current_channel_id}>" if current_channel_id else "Not set"

        embed = discord.Embed(
            title=f"🔔 Configure {setting_name}",
            description=f"Select the channel for {setting_name.lower()}.",
            color=0x7603FF
        )

        embed.add_field(
            name="Current Channel",
            value=current_channel,
            inline=False
        )

        if setting_type == "bump_channel":
            embed.add_field(
                name="ℹ️ Note",
                value="This is where bump commands will be used and reminders will be sent.",
                inline=False
            )

        await interaction.response.edit_message(embed=embed, view=self)

    async def show_role_config(self, interaction: discord.Interaction):
        """Show role configuration."""
        await self.refresh_config()
        self.clear_items()

        self.add_item(SetupRoleSelect(self))
        self.add_item(BackToSetupButton(self))

        current_role_id = self.config.get("bump_role")
        current_role = f"<@&{current_role_id}>" if current_role_id else "Not set"

        embed = discord.Embed(
            title="👥 Configure Bump Role",
            description="Select the role to ping for bump reminders.",
            color=0x7603FF
        )

        embed.add_field(
            name="Current Role",
            value=current_role,
            inline=False
        )

        embed.add_field(
            name="ℹ️ Note",
            value="This role will be mentioned when it's time to bump your server.",
            inline=False
        )

        await interaction.response.edit_message(embed=embed, view=self)

    async def show_bot_selection(self, interaction: discord.Interaction):
        """Show bot selection with submit button."""
        await self.refresh_config()
        self.clear_items()

        enabled_bots = self.config.get("enabled_bots", [])

        self.add_item(SetupBotMultiSelect(self, enabled_bots))
        self.add_item(SubmitBotsButton(self))
        self.add_item(BackToSetupButton(self))

        embed = discord.Embed(
            title="🤖 Select Enabled Bots",
            description="Choose which bump bots to enable for your server.\nOnly enabled bots will trigger reminders.",
            color=0x7603FF
        )

        # Show bot information
        bot_info = []
        for bot_name in SUPPORTED_BOTS:
            delay_seconds = BUMP_BOTS.get(bot_name, 0)
            delay = format_cooldown(delay_seconds)
            bot_info.append(f"**{bot_name.capitalize()}** - Default cooldown: {delay}")

        embed.add_field(
            name="Available Bots",
            value="\n".join(bot_info),
            inline=False
        )

        embed.add_field(
            name="ℹ️ How to Use",
            value="1. Select the bots you want from the dropdown\n2. Click **Submit Selection** to save\n3. You can change this later in `/bump settings`",
            inline=False
        )

        await interaction.response.edit_message(embed=embed, view=self)


# ============================================================================
# UI COMPONENTS - CORE NAVIGATION
# ============================================================================

class BackButton(Button):
    """Reusable button to return to main menu."""

    def __init__(self, parent_view):
        super().__init__(
            label="Back to Menu",
            style=discord.ButtonStyle.secondary,
            emoji="◀️"
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.show_main_menu(interaction)


class SettingCategorySelect(Select):
    """Main menu dropdown for selecting which setting to configure."""
    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label="View Full Configuration",
                value="view_config",
                emoji="📋",
                description="View all current settings"
            ),
            discord.SelectOption(
                label="Manage Enabled Bots",
                value="manage_bots",
                emoji="🤖",
                description="Enable/disable specific bump bots"
            ),
            discord.SelectOption(
                label="Manage Bot Cooldowns",
                value="manage_cooldowns",
                emoji="⏰",
                description="Configure cooldown times for each bot"
            ),
            discord.SelectOption(
                label="Set Custom Message - *Premium*",
                value="custom_message",
                emoji="💬",
                description="Set a custom bump reminder message"
            ),
            discord.SelectOption(
                label="Configure Bump Channel",
                value="bump_channel",
                emoji="🔔",
                description="Set the channel for bump commands"
            ),
            discord.SelectOption(
                label="Configure Bump Role",
                value="bump_role",
                emoji="👥",
                description="Set the role to ping for reminders"
            ),
            discord.SelectOption(
                label="Configure Timer Channel - *Premium*",
                value="timer_channel",
                emoji="📺",
                description="Set the channel for timer displays"
            ),
            discord.SelectOption(
                label="Toggle Timer Display",
                value="toggle_display",
                emoji="🎛️",
                description="Enable/disable timer status embeds"
            ),
            discord.SelectOption(
                label="Refresh Timers Now - *Premium*",
                value="refresh_timers",
                emoji="🔄",
                description="Manually refresh the timer display"
            ),
            discord.SelectOption(
                label="Activate Premium",
                value="activate_premium",
                emoji="🌟",
                description="Activate premium features with a code"
            ),
        ]
        super().__init__(
            placeholder="Select a setting to configure...",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.route_to_setting(interaction, self.values[0])


# ============================================================================
# UI COMPONENTS - BOT MANAGEMENT
# ============================================================================

class BotMultiSelect(Select):
    """Multi-select dropdown for enabling/disabling bump bots."""

    def __init__(self, parent_view, enabled_bots: List[str]):
        self.parent_view = parent_view
        options = []
        for bot_name in SUPPORTED_BOTS:
            options.append(
                discord.SelectOption(
                    label=bot_name.capitalize(),
                    value=bot_name,
                    default=(bot_name in enabled_bots)
                )
            )

        super().__init__(
            placeholder="Select which bots to enable...",
            min_values=0,
            max_values=len(SUPPORTED_BOTS),
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values
        try:
            await bump_storage.set_value(
                self.parent_view.guild_id,
                "enabled_bots",
                selected
            )
            bot_list = ', '.join([b.capitalize() for b in selected]) if selected else 'None'

            embed = discord.Embed(
                title="✅ Enabled Bots Updated",
                description=f"**Enabled bots:** {bot_list}",
                color=discord.Color.green()
            )

            logger.info(f"[{self.parent_view.guild_id}] Updated enabled bots: {selected}")

            # Show success message and return to main menu
            await interaction.response.edit_message(embed=embed, view=None)

            # Wait a moment then show main menu
            await asyncio.sleep(2)
            await self.parent_view.show_main_menu(interaction, edit=True)

        except Exception as e:
            logger.error(f"[{self.parent_view.guild_id}] Failed to update enabled bots: {e}")
            await interaction.response.send_message(
                "❌ Failed to update enabled bots. Please try again.",
                ephemeral=True
            )


# ============================================================================
# UI COMPONENTS - COOLDOWN MANAGEMENT
# ============================================================================

class BotSelect(Select):
    """Select menu for choosing which bot to configure cooldown for."""

    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label=bot.capitalize(), value=bot)
            for bot in BUMP_BOTS.keys()
        ]
        super().__init__(placeholder="Select a bot to configure...", options=options)

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.selected_bot = self.values[0]

        # Remove existing delay select if present
        for item in list(self.parent_view.children):
            if isinstance(item, DelaySelect):
                self.parent_view.remove_item(item)

        # Add the delay select for the chosen bot
        self.parent_view.add_item(DelaySelect(self.parent_view))
        await interaction.response.edit_message(view=self.parent_view)


class DelaySelect(Select):
    """Select menu for choosing delay for the selected bot."""

    def __init__(self, parent_view):
        self.parent_view = parent_view
        self.selected_bot = parent_view.selected_bot

        options = []
        if self.selected_bot in BUMP_BOTS_CHOICES:
            choices = BUMP_BOTS_CHOICES[self.selected_bot]
            for label, seconds in choices.items():
                options.append(discord.SelectOption(label=label, value=str(seconds)))

        super().__init__(
            placeholder=f"Select delay for {self.selected_bot.capitalize()}...",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        new_delay = int(self.values[0])

        try:
            await bump_storage.set_value(
                self.parent_view.guild_id,
                f"bot_delay.{self.selected_bot}",
                new_delay
            )

            embed = discord.Embed(
                title="✅ Cooldown Updated",
                description=f"**{self.selected_bot.capitalize()}** cooldown set to **{format_cooldown(new_delay)}**",
                color=discord.Color.green()
            )

            logger.info(
                f"[{self.parent_view.guild_id}] Updated {self.selected_bot} delay to {new_delay}"
            )

            # Show success message and return to main menu
            await interaction.response.edit_message(embed=embed, view=None)

            # Wait a moment then show main menu
            await asyncio.sleep(2)
            await self.parent_view.show_main_menu(interaction, edit=True)

        except Exception as e:
            logger.error(f"[{self.parent_view.guild_id}] Failed to update delay: {e}")
            await interaction.response.send_message(
                "❌ Failed to update cooldown. Please try again.",
                ephemeral=True
            )


# ============================================================================
# UI COMPONENTS - CUSTOM MESSAGE
# ============================================================================

class CustomMessageModal(Modal):
    """Modal for setting custom bump reminder message."""

    def __init__(self, parent_view, current_message: str = ""):
        super().__init__(title="Custom Bump Reminder Message")
        self.parent_view = parent_view

        self.message_input = TextInput(
            label="Custom Message",
            placeholder="Enter message... Use {bump_role} and {bots} as placeholders",
            default=current_message,
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False
        )
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        message = self.message_input.value.strip()

        try:
            await bump_storage.set_value(
                self.parent_view.guild_id,
                "custom_message",
                message
            )

            if message:
                embed = discord.Embed(
                    title="✅ Custom Message Set",
                    description=f"**Preview:**\n{message}",
                    color=discord.Color.green()
                )
                logger.info(f"[{self.parent_view.guild_id}] Custom message set")
            else:
                embed = discord.Embed(
                    title="✅ Custom Message Cleared",
                    description="Using default reminder message.",
                    color=discord.Color.green()
                )
                logger.info(f"[{self.parent_view.guild_id}] Custom message cleared")

            embed.set_footer(text="Available placeholders: {bump_role}, {bots}")

            # Show success message
            await interaction.response.send_message(embed=embed, ephemeral=True)

            # Return to main menu
            await asyncio.sleep(2)
            await self.parent_view.show_main_menu(interaction, edit=True)

        except Exception as e:
            logger.error(f"[{self.parent_view.guild_id}] Failed to set custom message: {e}")
            await interaction.response.send_message(
                "❌ Failed to save custom message. Please try again.",
                ephemeral=True
            )


# ============================================================================
# UI COMPONENTS - PREMIUM ACTIVATION
# ============================================================================

class PremiumCodeModal(Modal):
    """Modal for entering premium activation code."""

    def __init__(self, parent_view):
        super().__init__(title="Activate Premium")
        self.parent_view = parent_view

        self.code_input = TextInput(
            label="Premium Code",
            placeholder="Enter your premium activation code...",
            style=discord.TextStyle.short,
            max_length=20,
            required=True
        )
        self.add_item(self.code_input)

    async def on_submit(self, interaction: discord.Interaction):
        code = self.code_input.value.strip().upper()
        guild_id = self.parent_view.guild_id
        user_id = interaction.user.id

        try:
            await interaction.response.defer()

            # Check if guild already has premium
            config = await bump_storage.get_guild(guild_id)
            if config.get("premium", {}).get("enabled", False):
                embed = discord.Embed(
                    title="❌ Premium Already Active",
                    description="This server already has premium features activated.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                await asyncio.sleep(2)
                await self.parent_view.show_main_menu(interaction, edit=True)
                return

            # Get codes collection from database
            db = BumpStorage().db
            codes_collection = db["codes"]

            # Find valid code
            from datetime import datetime
            import pytz

            subscription = await codes_collection.find_one({
                "code": code,
                "linked_guild": 0,  # Not linked to any guild yet
                "expired": False,
                "expires_at": {"$gte": datetime.now(pytz.utc).isoformat()}
            })

            if not subscription:
                embed = discord.Embed(
                    title="❌ Invalid Code",
                    description="The code you entered is invalid, already used, or expired.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                await asyncio.sleep(2)
                await self.parent_view.show_main_menu(interaction, edit=True)
                return

            # If it's a trial, check if the guild has had a trial before
            if subscription["type"] == "trial":
                existing_guild_trial = await codes_collection.find_one({
                    "linked_guild": guild_id,
                    "type": "trial"
                })

                if existing_guild_trial:
                    embed = discord.Embed(
                        title="❌ Trial Already Used",
                        description="This server has already used its trial period.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    await asyncio.sleep(2)
                    await self.parent_view.show_main_menu(interaction, edit=True)
                    return

            # Link the subscription to the guild
            await codes_collection.update_one(
                {"_id": subscription["_id"]},
                {"$set": {"linked_guild": guild_id}}
            )

            # Activate premium for the guild
            await bump_storage.set_value(guild_id, "premium.enabled", True)
            await bump_storage.set_value(guild_id, "premium.activated_by", user_id)

            expiry_date = datetime.fromisoformat(subscription['expires_at'])

            embed = discord.Embed(
                title="✅ Premium Activated!",
                description=f"Premium features have been activated in this server!\n\n"
                           f"**Valid until:** {expiry_date.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                           f"**Type:** {subscription['type'].capitalize()}",
                color=discord.Color.green()
            )

            logger.info(f"[{guild_id}] Premium activated by user {user_id} with code {code}")

            await interaction.followup.send(embed=embed, ephemeral=True)
            await asyncio.sleep(3)
            await self.parent_view.show_main_menu(interaction, edit=True)

        except Exception as e:
            logger.error(f"[{guild_id}] Failed to activate premium: {e}", exc_info=True)
            embed = discord.Embed(
                title="❌ Activation Failed",
                description="An error occurred while activating premium. Please try again.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            await asyncio.sleep(2)
            await self.parent_view.show_main_menu(interaction, edit=True)


# ============================================================================
# UI COMPONENTS - CHANNEL CONFIGURATION
# ============================================================================

class ChannelConfigSelect(ChannelSelect):
    """Channel select for configuring bump or timer channel."""

    def __init__(self, parent_view, setting_type: str):
        self.parent_view = parent_view
        self.setting_type = setting_type  # "bump_channel" or "timer_channel"

        super().__init__(
            placeholder="Select a channel...",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.text]
        )

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]

        try:
            await bump_storage.set_value(
                self.parent_view.guild_id,
                self.setting_type,
                channel.id
            )

            setting_name = "Bump Channel" if self.setting_type == "bump_channel" else "Timer Channel"

            embed = discord.Embed(
                title=f"✅ {setting_name} Updated",
                description=f"**{setting_name}** set to {channel.mention}",
                color=discord.Color.green()
            )

            logger.info(f"[{self.parent_view.guild_id}] Updated {self.setting_type} to {channel.id}")

            # Show success message and return to main menu
            await interaction.response.edit_message(embed=embed, view=None)

            # Wait a moment then show main menu
            await asyncio.sleep(2)
            await self.parent_view.show_main_menu(interaction, edit=True)

        except Exception as e:
            logger.error(f"[{self.parent_view.guild_id}] Failed to update {self.setting_type}: {e}")
            await interaction.response.send_message(
                f"❌ Failed to update channel. Please try again.",
                ephemeral=True
            )


# ============================================================================
# UI COMPONENTS - ROLE CONFIGURATION
# ============================================================================

class RoleConfigSelect(RoleSelect):
    """Role select for configuring bump role."""

    def __init__(self, parent_view):
        self.parent_view = parent_view
        super().__init__(
            placeholder="Select a role...",
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]

        try:
            await bump_storage.set_value(
                self.parent_view.guild_id,
                "bump_role",
                role.id
            )

            embed = discord.Embed(
                title="✅ Bump Role Updated",
                description=f"**Bump Role** set to {role.mention}",
                color=discord.Color.green()
            )

            logger.info(f"[{self.parent_view.guild_id}] Updated bump_role to {role.id}")

            # Show success message and return to main menu
            await interaction.response.edit_message(embed=embed, view=None)

            # Wait a moment then show main menu
            await asyncio.sleep(2)
            await self.parent_view.show_main_menu(interaction, edit=True)

        except Exception as e:
            logger.error(f"[{self.parent_view.guild_id}] Failed to update bump_role: {e}")
            await interaction.response.send_message(
                "❌ Failed to update role. Please try again.",
                ephemeral=True
            )


# ============================================================================
# UI COMPONENTS - TIMER TOGGLE
# ============================================================================

class TimerToggleButton(Button):
    """Button for toggling timer display on or off."""

    def __init__(self, parent_view, enable: bool, current_state: bool):
        self.parent_view = parent_view
        self.enable = enable

        if enable:
            label = "✅ Enable Timer Display"
            style = discord.ButtonStyle.success if not current_state else discord.ButtonStyle.secondary
        else:
            label = "❌ Disable Timer Display"
            style = discord.ButtonStyle.danger if current_state else discord.ButtonStyle.secondary

        super().__init__(label=label, style=style)

    async def callback(self, interaction: discord.Interaction):
        try:
            await bump_storage.set_value(
                self.parent_view.guild_id,
                "timers_message",
                self.enable
            )

            if self.enable:
                embed = discord.Embed(
                    title="✅ Timer Display Enabled",
                    description="Timer status embeds will be posted/updated in your bump channel.",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="✅ Timer Display Disabled",
                    description="Only bump reminders will be sent (no timer embeds).",
                    color=discord.Color.green()
                )

            logger.info(f"[{self.parent_view.guild_id}] Timer display set to {self.enable}")

            # Show success message and return to main menu
            await interaction.response.edit_message(embed=embed, view=None)

            # Wait a moment then show main menu
            await asyncio.sleep(2)
            await self.parent_view.show_main_menu(interaction, edit=True)

        except Exception as e:
            logger.error(f"[{self.parent_view.guild_id}] Failed to toggle timer display: {e}")
            await interaction.response.send_message(
                "❌ Failed to update setting. Please try again.",
                ephemeral=True
            )


# ============================================================================
# MAIN SETTINGS VIEW
# ============================================================================

class MainSettingsView(View):
    """
    Central hub for managing all bump settings.
    Handles navigation between different setting sub-views.
    """

    def __init__(self, bot, guild_id: int, initial_config: Dict[str, Any]):
        super().__init__(timeout=300)  # 5 minute timeout
        self.bot = bot
        self.guild_id = guild_id
        self.config = initial_config
        self.message = None
        self.selected_bot: Optional[str] = None

        # Add main menu dropdown
        self.add_item(SettingCategorySelect(self))

    async def refresh_config(self):
        """Reload config from database."""
        self.config = await bump_storage.get_guild(self.guild_id)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verify user has manage_guild permission."""
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ You need `Manage Server` permission to use this menu.",
                ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        """Disable all components on timeout."""
        for item in self.children:
            item.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except:
            pass

    async def show_main_menu(self, interaction: discord.Interaction, edit: bool = False):
        """Return to main menu."""
        await self.refresh_config()
        self.clear_items()
        self.add_item(SettingCategorySelect(self))

        embed = create_main_menu_embed(self.config)

        if edit:
            # Edit the original message if we're returning from a sub-view
            try:
                if self.message:
                    await self.message.edit(embed=embed, view=self)
            except:
                # Fallback if message edit fails
                await interaction.followup.send(embed=embed, view=self, ephemeral=True)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def route_to_setting(self, interaction: discord.Interaction, setting: str):
        """Route to appropriate sub-view based on dropdown selection."""
        if setting == "view_config":
            await self.show_view_config(interaction)
        elif setting == "manage_bots":
            await self.show_bot_management(interaction)
        elif setting == "manage_cooldowns":
            await self.show_cooldown_management(interaction)
        elif setting == "custom_message":
            await self.show_custom_message(interaction)
        elif setting == "bump_channel":
            await self.show_channel_config(interaction, "bump_channel")
        elif setting == "timer_channel":
            await self.show_channel_config(interaction, "timer_channel")
        elif setting == "bump_role":
            await self.show_role_config(interaction)
        elif setting == "toggle_display":
            await self.show_timer_toggle(interaction)
        elif setting == "refresh_timers":
            await self.refresh_timers(interaction)
        elif setting == "activate_premium":
            await self.show_premium_activation(interaction)

    async def show_view_config(self, interaction: discord.Interaction):
        """Show detailed configuration view."""
        await self.refresh_config()
        self.clear_items()
        self.add_item(BackButton(self))

        embed = create_config_embed(self.config)
        await interaction.response.edit_message(embed=embed, view=self)

    async def show_bot_management(self, interaction: discord.Interaction):
        """Show bot enable/disable interface."""
        await self.refresh_config()
        self.clear_items()

        enabled_bots = self.config.get("enabled_bots", [])
        self.add_item(BotMultiSelect(self, enabled_bots))
        self.add_item(BackButton(self))

        embed = discord.Embed(
            title="🤖 Manage Enabled Bots",
            description="Select which bots to enable for bump reminders.\nOnly enabled bots will trigger reminders.",
            color=0x7603FF
        )

        await interaction.response.edit_message(embed=embed, view=self)

    async def show_cooldown_management(self, interaction: discord.Interaction):
        """Show cooldown configuration interface."""
        await self.refresh_config()
        self.clear_items()

        self.add_item(BotSelect(self))
        self.add_item(BackButton(self))

        embed = discord.Embed(
            title="⏰ Manage Bot Cooldowns",
            description="Configure cooldown times for each bot.\nSelect a bot to see available cooldown options.",
            color=0x7603FF
        )

        # Show current cooldowns
        bot_delays = self.config.get("bot_delay", {})
        delay_info = []
        for bot_name in BUMP_BOTS.keys():
            delay_seconds = bot_delays.get(bot_name, BUMP_BOTS[bot_name])
            delay_info.append(f"**{bot_name.capitalize()}:** {format_cooldown(delay_seconds)}")

        embed.add_field(
            name="Current Cooldowns",
            value="\n".join(delay_info),
            inline=False
        )

        await interaction.response.edit_message(embed=embed, view=self)

    async def show_custom_message(self, interaction: discord.Interaction):
        """Show custom message modal."""
        await self.refresh_config()

        # Check premium status
        if not self.config.get("premium", {}).get("enabled", False):
            embed = discord.Embed(
                title="🌟 Premium Feature",
                description=(
                    "Custom messages are a **premium feature**!\n\n"
                    "Use `/bump settings` and select **Activate Premium** to unlock this feature."
                ),
                color=discord.Color.gold()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        current_message = self.config.get("custom_message", "")

        modal = CustomMessageModal(self, current_message)
        await interaction.response.send_modal(modal)

    async def show_channel_config(self, interaction: discord.Interaction, setting_type: str):
        """Show channel configuration interface."""
        await self.refresh_config()

        # Check premium status for timer channel
        if setting_type == "timer_channel" and not self.config.get("premium", {}).get("enabled", False):
            embed = discord.Embed(
                title="🌟 Premium Feature",
                description=(
                    "Separate timer channel is a **premium feature**!\n\n"
                    "Use `/bump settings` and select **Activate Premium** to unlock this feature.\n\n"
                    "**Free users**: Timers display in the bump channel by default."
                ),
                color=discord.Color.gold()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        self.clear_items()

        self.add_item(ChannelConfigSelect(self, setting_type))
        self.add_item(BackButton(self))

        setting_name = "Bump Channel" if setting_type == "bump_channel" else "Timer Channel"
        current_channel_id = self.config.get(setting_type)
        current_channel = f"<#{current_channel_id}>" if current_channel_id else "Not set"

        embed = discord.Embed(
            title=f"🔔 Configure {setting_name}",
            description=f"Select a new channel for {setting_name.lower()}.",
            color=0x7603FF
        )

        embed.add_field(
            name="Current Channel",
            value=current_channel,
            inline=False
        )

        await interaction.response.edit_message(embed=embed, view=self)

    async def show_role_config(self, interaction: discord.Interaction):
        """Show role configuration interface."""
        await self.refresh_config()
        self.clear_items()

        self.add_item(RoleConfigSelect(self))
        self.add_item(BackButton(self))

        current_role_id = self.config.get("bump_role")
        current_role = f"<@&{current_role_id}>" if current_role_id else "Not set"

        embed = discord.Embed(
            title="👥 Configure Bump Role",
            description="Select a new role to ping for bump reminders.",
            color=0x7603FF
        )

        embed.add_field(
            name="Current Role",
            value=current_role,
            inline=False
        )

        await interaction.response.edit_message(embed=embed, view=self)

    async def show_timer_toggle(self, interaction: discord.Interaction):
        """Show timer display toggle interface."""
        await self.refresh_config()
        self.clear_items()

        current_state = self.config.get("timers_message", True)

        self.add_item(TimerToggleButton(self, True, current_state))
        self.add_item(TimerToggleButton(self, False, current_state))
        self.add_item(BackButton(self))

        embed = discord.Embed(
            title="🎛️ Toggle Timer Display",
            description=(
                "Control whether timer status embeds are shown.\n\n"
                f"**Current Status:** {'✅ Enabled' if current_state else '❌ Disabled'}"
            ),
            color=0x7603FF
        )

        await interaction.response.edit_message(embed=embed, view=self)

    async def refresh_timers(self, interaction: discord.Interaction):
        """Manually refresh the timer display."""
        await self.refresh_config()

        # Check premium status
        if not self.config.get("premium", {}).get("enabled", False):
            embed = discord.Embed(
                title="🌟 Premium Feature",
                description=(
                    "Manual timer refresh is a **premium feature**!\n\n"
                    "Use `/bump settings` and select **Activate Premium** to unlock this feature.\n\n"
                    "**Free users**: Timers update automatically when you bump."
                ),
                color=discord.Color.gold()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Show loading message
        embed = discord.Embed(
            title="🔄 Refreshing Timers...",
            description="Please wait...",
            color=0x7603FF
        )
        await interaction.response.edit_message(embed=embed, view=None)

        try:
            channel_id = self.config.get("bump_channel") or self.config.get("timers_channel")

            if not channel_id:
                embed = discord.Embed(
                    title="❌ No Channel Configured",
                    description="Please configure a bump/timer channel first!",
                    color=discord.Color.red()
                )
                await interaction.message.edit(embed=embed)

                # Return to main menu after delay
                await asyncio.sleep(2)
                await self.show_main_menu(interaction, edit=True)
                return

            # Get the embed manager cog
            embed_manager = self.bot.get_cog("TimerEmbedManager")
            if not embed_manager:
                embed = discord.Embed(
                    title="❌ Timer System Unavailable",
                    description="Timer system not available. Please contact support.",
                    color=discord.Color.red()
                )
                logger.error(f"[{self.guild_id}] TimerEmbedManager cog not found")
                await interaction.message.edit(embed=embed)

                # Return to main menu after delay
                await asyncio.sleep(2)
                await self.show_main_menu(interaction, edit=True)
                return

            # Trigger manual update
            success = await embed_manager.manual_update(self.guild_id, channel_id)

            if success:
                embed = discord.Embed(
                    title="✅ Timers Refreshed",
                    description="Timer display has been updated!",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Refresh Failed",
                    description="Failed to update timer display. Check that the channel is configured correctly.",
                    color=discord.Color.red()
                )

            await interaction.message.edit(embed=embed)

            # Return to main menu after delay
            import asyncio
            await asyncio.sleep(2)
            await self.show_main_menu(interaction, edit=True)

        except Exception as e:
            logger.error(f"[{self.guild_id}] Failed to refresh timers: {e}", exc_info=True)
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to refresh timer display. Please try again.",
                color=discord.Color.red()
            )
            await interaction.message.edit(embed=embed)

            # Return to main menu after delay
            import asyncio
            await asyncio.sleep(2)
            await self.show_main_menu(interaction, edit=True)

    async def show_premium_activation(self, interaction: discord.Interaction):
        """Show premium activation modal."""
        modal = PremiumCodeModal(self)
        await interaction.response.send_modal(modal)


# ============================================================================
# COG AND COMMANDS
# ============================================================================

class BumpCommands(commands.GroupCog, group_name="bump"):
    """Bump reminder commands - setup and settings."""

    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(
        name="setup",
        description="Interactive setup for bump reminders"
    )
    async def setup(self, interaction: discord.Interaction):
        """
        Interactive setup menu for configuring bump reminders.

        This command opens an interactive menu where you can configure:
        - Bump Channel (required)
        - Bump Role (required)
        - Timer Channel (optional)
        - Enabled Bots (optional)
        """
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id

        try:
            # Load current config
            config = await bump_storage.get_guild(guild_id)

            # Create setup view
            view = SetupView(self.bot, guild_id, config)
            embed = create_setup_menu_embed(config)

            message = await interaction.followup.send(
                embed=embed,
                view=view,
                ephemeral=True
            )
            view.message = message

            logger.info(f"[{guild_id}] Setup menu opened")

        except Exception as e:
            logger.error(f"[{guild_id}] Failed to open setup menu: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to open setup menu. Please try again.",
                ephemeral=True
            )

    @app_commands.command(
        name="settings",
        description="Manage bump reminder settings"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def settings(self, interaction: discord.Interaction):
        """
        Open the interactive bump settings menu.

        This command provides access to all bump configuration options:
        - View current configuration
        - Manage enabled bots
        - Configure bot cooldowns
        - Set custom messages
        - Configure channels and roles
        - Toggle timer display
        - Refresh timers
        """
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id

        try:
            config = await bump_storage.get_guild(guild_id)

            # Check if basic setup is complete
            if not config.get("bump_channel") or not config.get("bump_role"):
                embed = discord.Embed(
                    title="⚠️ Setup Required",
                    description=(
                        "Please run `/bump setup` first to configure your bump channel and role!\n\n"
                        "This is a one-time setup that takes less than a minute."
                    ),
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Create main settings view
            view = MainSettingsView(self.bot, guild_id, config)
            embed = create_main_menu_embed(config)

            message = await interaction.followup.send(
                embed=embed,
                view=view,
                ephemeral=True
            )
            view.message = message

        except Exception as e:
            logger.error(f"[{guild_id}] Failed to show bump settings: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to load settings. Please try again.",
                ephemeral=True
            )


async def setup(bot):
    """Load the BumpCommands cog."""
    logger.info("Setting up BumpCommands Cog...")
    await bot.add_cog(BumpCommands(bot))
