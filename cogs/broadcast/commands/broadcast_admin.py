"""
Admin Broadcast Commands
Allows server admins to create and manage DM broadcasts
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, Button, View, Modal, TextInput
from datetime import datetime
from bson import ObjectId
from utils.logger import get_logger
from ..validator import validate_broadcast_content, validate_broadcast_name
from ..config import (
    MIN_RECURRING_INTERVAL_MINUTES,
    MAX_ACTIVE_BROADCASTS_PER_GUILD,
    LARGE_BROADCAST_THRESHOLD
)

logger = get_logger("BroadcastAdmin")


class BroadcastAdmin(commands.GroupCog, name="broadcast"):
    """Admin commands for managing DM broadcasts"""

    def __init__(self, bot):
        self.bot = bot
        self.storage = bot.broadcast_storage

    @app_commands.command(name="manage", description="Manage server broadcasts")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def manage_broadcasts(self, interaction: discord.Interaction):
        """Open broadcast management menu"""

        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server!",
                ephemeral=True
            )
            return

        # Get all broadcasts for this guild
        broadcasts = await self.storage.get_guild_broadcasts(interaction.guild.id, active_only=False)

        # Create menu view
        view = BroadcastMenuView(self.bot, self.storage, interaction.guild.id, interaction.user.id, broadcasts)
        embed = await view.create_main_embed(interaction.guild.name)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="send", description="Send a one-time broadcast to all opted-in members")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(message="Message to send")
    async def send_one_time(
        self,
        interaction: discord.Interaction,
        message: str
    ):
        """Send a one-time broadcast announcement"""

        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server!",
                ephemeral=True
            )
            return

        # Validate content
        is_valid, reason = await validate_broadcast_content(
            message,
            interaction.user.id,
            interaction.guild.id,
            self.storage
        )

        if not is_valid:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        # Get eligible recipients
        subs = await self.storage.get_guild_subscriptions(interaction.guild.id)

        if not subs:
            await interaction.response.send_message(
                "❌ No opted-in members to send to. Users must use `/alerts join` first.",
                ephemeral=True
            )
            return

        # Require confirmation for large broadcasts
        if len(subs) >= LARGE_BROADCAST_THRESHOLD:
            view = ConfirmBroadcastView(
                self.bot,
                self.storage,
                interaction.guild.id,
                interaction.user.id,
                message,
                len(subs)
            )

            await interaction.response.send_message(
                f"⚠️ **Confirm Broadcast**\n\n"
                f"You're about to send a one-time message to **{len(subs)} members**.\n\n"
                f"**Preview:**\n{message[:500]}\n\n"
                f"Are you sure you want to continue?",
                view=view,
                ephemeral=True
            )
            return

        # Send immediately (small broadcast)
        await interaction.response.defer(ephemeral=True)

        broadcast_id = await self.storage.create_broadcast({
            "guild_id": interaction.guild.id,
            "created_by": interaction.user.id,
            "broadcast_name": f"One-time ({datetime.utcnow().strftime('%Y-%m-%d %H:%M')})",
            "message_content": message,
            "interval_minutes": None,  # One-time
            "is_active": False,  # Don't schedule recurring
            "paused": False
        })

        # Trigger immediate send
        successful, failed = await self.bot.broadcast_worker.send_broadcast(broadcast_id)

        embed = discord.Embed(
            title="✅ Broadcast Sent",
            description=f"One-time broadcast has been delivered.",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="✅ Successful", value=str(successful), inline=True)
        embed.add_field(name="❌ Failed", value=str(failed), inline=True)
        embed.add_field(name="📊 Total", value=str(successful + failed), inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"One-time broadcast sent by admin {interaction.user.id} in guild {interaction.guild.id}")

    # Helper methods

    async def _find_broadcast_by_name(self, guild_id: int, name: str):
        """Find a broadcast by name in a guild"""
        broadcasts = await self.storage.get_guild_broadcasts(guild_id, active_only=False)
        for broadcast in broadcasts:
            if broadcast["broadcast_name"] == name:
                return broadcast
        return None

    async def _schedule_broadcast(self, broadcast_id: str):
        """Schedule a recurring broadcast using TimerHandler"""
        # This will be called by the broadcast worker
        # For now, just log
        logger.info(f"Scheduled broadcast {broadcast_id}")

    async def _cancel_broadcast_timer(self, broadcast_id: str):
        """Cancel a scheduled broadcast timer"""
        # This will use TimerHandler to cancel
        logger.info(f"Cancelled timer for broadcast {broadcast_id}")


# ============================================================================
# BROADCAST MANAGEMENT MENU
# ============================================================================

class BroadcastMenuView(View):
    """Main broadcast management menu"""

    def __init__(self, bot, storage, guild_id, admin_id, broadcasts):
        super().__init__(timeout=300)  # 5 minute timeout
        self.bot = bot
        self.storage = storage
        self.guild_id = guild_id
        self.admin_id = admin_id
        self.broadcasts = broadcasts

        # Add appropriate UI elements
        if broadcasts:
            self.add_item(BroadcastSelectMenu(self))

        self.add_item(CreateBroadcastButton())

        if broadcasts:
            self.add_item(RefreshButton())

    async def create_main_embed(self, guild_name: str) -> discord.Embed:
        """Create the main menu embed"""

        embed = discord.Embed(
            title="📢 Broadcast Management",
            description=f"Manage broadcasts for **{guild_name}**",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        if not self.broadcasts:
            embed.add_field(
                name="ℹ️ No Broadcasts",
                value="You haven't created any broadcasts yet.\nClick **Create New Broadcast** to get started!",
                inline=False
            )
        else:
            active_count = sum(1 for b in self.broadcasts if b.get("is_active") and not b.get("paused"))
            paused_count = sum(1 for b in self.broadcasts if b.get("paused"))

            embed.add_field(
                name="📊 Overview",
                value=f"**Total:** {len(self.broadcasts)}\n**Active:** {active_count}\n**Paused:** {paused_count}",
                inline=True
            )

            # Get subscriber count
            subs = await self.storage.get_guild_subscriptions(self.guild_id)
            embed.add_field(
                name="👥 Subscribers",
                value=f"{len(subs)} opted-in members",
                inline=True
            )

            embed.add_field(
                name="💡 Usage",
                value="Select a broadcast from the dropdown to manage it, or create a new one.",
                inline=False
            )

        embed.set_footer(text=f"Tip: Use /broadcast send for one-time announcements")

        return embed


class BroadcastSelectMenu(Select):
    """Dropdown to select a broadcast to manage"""

    def __init__(self, parent_view):
        self.parent_view = parent_view

        # Create options from broadcasts
        options = []
        for broadcast in parent_view.broadcasts[:25]:  # Discord max 25
            status_emoji = "⏸️" if broadcast.get("paused") else "✅"
            interval = broadcast.get("interval_minutes")

            # Format description
            if interval:
                desc = f"{status_emoji} Every {interval}min | Sent {broadcast.get('times_sent', 0)} times"
            else:
                desc = f"One-time broadcast"

            options.append(discord.SelectOption(
                label=broadcast["broadcast_name"][:100],
                value=str(broadcast["_id"]),
                description=desc[:100],
                emoji=status_emoji
            ))

        super().__init__(
            placeholder="Select a broadcast to manage...",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle broadcast selection"""

        if interaction.user.id != self.parent_view.admin_id:
            await interaction.response.send_message(
                "❌ Only the admin who opened this menu can use it.",
                ephemeral=True
            )
            return

        broadcast_id = self.values[0]

        # Find the broadcast
        broadcast = None
        for b in self.parent_view.broadcasts:
            if str(b["_id"]) == broadcast_id:
                broadcast = b
                break

        if not broadcast:
            await interaction.response.send_message(
                "❌ Broadcast not found.",
                ephemeral=True
            )
            return

        # Show broadcast details view
        view = BroadcastDetailsView(
            self.parent_view.bot,
            self.parent_view.storage,
            self.parent_view.guild_id,
            self.parent_view.admin_id,
            broadcast
        )

        embed = await view.create_details_embed()

        await interaction.response.edit_message(embed=embed, view=view)


class CreateBroadcastButton(Button):
    """Button to create a new broadcast"""

    def __init__(self):
        super().__init__(
            label="Create New Broadcast",
            style=discord.ButtonStyle.green,
            emoji="➕"
        )

    async def callback(self, interaction: discord.Interaction):
        """Show create broadcast modal"""

        modal = CreateBroadcastModal(self.view.bot, self.view.storage, self.view.guild_id)
        await interaction.response.send_modal(modal)


class RefreshButton(Button):
    """Button to refresh the broadcast list"""

    def __init__(self):
        super().__init__(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
            emoji="🔄"
        )

    async def callback(self, interaction: discord.Interaction):
        """Refresh the broadcast list"""

        if interaction.user.id != self.view.admin_id:
            await interaction.response.send_message(
                "❌ Only the admin who opened this menu can use it.",
                ephemeral=True
            )
            return

        # Refresh broadcasts
        broadcasts = await self.view.storage.get_guild_broadcasts(self.view.guild_id, active_only=False)
        self.view.broadcasts = broadcasts

        # Rebuild view
        guild = interaction.guild
        new_view = BroadcastMenuView(
            self.view.bot,
            self.view.storage,
            self.view.guild_id,
            self.view.admin_id,
            broadcasts
        )

        embed = await new_view.create_main_embed(guild.name)

        await interaction.response.edit_message(embed=embed, view=new_view)


# ============================================================================
# BROADCAST DETAILS VIEW
# ============================================================================

class BroadcastDetailsView(View):
    """View showing details of a specific broadcast"""

    def __init__(self, bot, storage, guild_id, admin_id, broadcast):
        super().__init__(timeout=300)
        self.bot = bot
        self.storage = storage
        self.guild_id = guild_id
        self.admin_id = admin_id
        self.broadcast = broadcast

        # Add buttons based on broadcast state
        if broadcast.get("paused"):
            self.add_item(ResumeButton())
        else:
            self.add_item(PauseButton())

        self.add_item(EditButton())
        self.add_item(DeleteButton())
        self.add_item(BackButton())

    async def create_details_embed(self) -> discord.Embed:
        """Create embed showing broadcast details"""

        broadcast = self.broadcast

        status_emoji = "⏸️ Paused" if broadcast.get("paused") else "✅ Active"

        embed = discord.Embed(
            title=f"📝 {broadcast['broadcast_name']}",
            description=broadcast.get("message_content", "No message content")[:2048],
            color=discord.Color.orange() if broadcast.get("paused") else discord.Color.green(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(
            name="Status",
            value=status_emoji,
            inline=True
        )

        interval = broadcast.get("interval_minutes")
        if interval:
            embed.add_field(
                name="Interval",
                value=f"{interval} minutes",
                inline=True
            )
        else:
            embed.add_field(
                name="Type",
                value="One-time",
                inline=True
            )

        embed.add_field(
            name="Times Sent",
            value=str(broadcast.get("times_sent", 0)),
            inline=True
        )

        last_sent = broadcast.get('last_sent')
        if last_sent:
            embed.add_field(
                name="Last Sent",
                value=f"<t:{int(last_sent.timestamp())}:R>",
                inline=True
            )

        created_at = broadcast.get('created_at')
        if created_at:
            embed.add_field(
                name="Created",
                value=f"<t:{int(created_at.timestamp())}:R>",
                inline=True
            )

        embed.set_footer(text=f"Broadcast ID: {broadcast['_id']}")

        return embed


class PauseButton(Button):
    """Button to pause a broadcast"""

    def __init__(self):
        super().__init__(
            label="Pause",
            style=discord.ButtonStyle.secondary,
            emoji="⏸️"
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.admin_id:
            await interaction.response.send_message(
                "❌ Only the admin who opened this menu can use it.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        # Pause the broadcast
        await self.view.storage.update_broadcast(str(self.view.broadcast["_id"]), {"paused": True})

        # Cancel timer
        await self.view.bot.get_cog("broadcast")._cancel_broadcast_timer(str(self.view.broadcast["_id"]))

        # Refresh view
        broadcast = await self.view.storage.get_broadcast(str(self.view.broadcast["_id"]))
        self.view.broadcast = broadcast

        new_view = BroadcastDetailsView(
            self.view.bot,
            self.view.storage,
            self.view.guild_id,
            self.view.admin_id,
            broadcast
        )

        embed = await new_view.create_details_embed()
        await interaction.followup.edit_message(
            message_id=interaction.message.id,
            embed=embed,
            view=new_view
        )

        logger.info(f"Broadcast {broadcast['_id']} paused by admin {interaction.user.id}")


class ResumeButton(Button):
    """Button to resume a broadcast"""

    def __init__(self):
        super().__init__(
            label="Resume",
            style=discord.ButtonStyle.success,
            emoji="▶️"
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.admin_id:
            await interaction.response.send_message(
                "❌ Only the admin who opened this menu can use it.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        # Resume the broadcast
        await self.view.storage.update_broadcast(str(self.view.broadcast["_id"]), {"paused": False})

        # Reschedule timer
        await self.view.bot.get_cog("broadcast")._schedule_broadcast(str(self.view.broadcast["_id"]))

        # Refresh view
        broadcast = await self.view.storage.get_broadcast(str(self.view.broadcast["_id"]))
        self.view.broadcast = broadcast

        new_view = BroadcastDetailsView(
            self.view.bot,
            self.view.storage,
            self.view.guild_id,
            self.view.admin_id,
            broadcast
        )

        embed = await new_view.create_details_embed()
        await interaction.followup.edit_message(
            message_id=interaction.message.id,
            embed=embed,
            view=new_view
        )

        logger.info(f"Broadcast {broadcast['_id']} resumed by admin {interaction.user.id}")


class EditButton(Button):
    """Button to edit a broadcast"""

    def __init__(self):
        super().__init__(
            label="Edit",
            style=discord.ButtonStyle.primary,
            emoji="✏️"
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.admin_id:
            await interaction.response.send_message(
                "❌ Only the admin who opened this menu can use it.",
                ephemeral=True
            )
            return

        modal = EditBroadcastModal(
            self.view.bot,
            self.view.storage,
            self.view.guild_id,
            self.view.admin_id,
            self.view.broadcast
        )
        await interaction.response.send_modal(modal)


class DeleteButton(Button):
    """Button to delete a broadcast"""

    def __init__(self):
        super().__init__(
            label="Delete",
            style=discord.ButtonStyle.danger,
            emoji="🗑️"
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.admin_id:
            await interaction.response.send_message(
                "❌ Only the admin who opened this menu can use it.",
                ephemeral=True
            )
            return

        # Show confirmation
        view = ConfirmDeleteView(
            self.view.bot,
            self.view.storage,
            self.view.guild_id,
            self.view.admin_id,
            self.view.broadcast
        )

        await interaction.response.send_message(
            f"⚠️ **Confirm Deletion**\n\n"
            f"Are you sure you want to permanently delete broadcast **{self.view.broadcast['broadcast_name']}**?\n\n"
            f"This action cannot be undone.",
            view=view,
            ephemeral=True
        )


class BackButton(Button):
    """Button to go back to main menu"""

    def __init__(self):
        super().__init__(
            label="Back to Menu",
            style=discord.ButtonStyle.secondary,
            emoji="◀️"
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.admin_id:
            await interaction.response.send_message(
                "❌ Only the admin who opened this menu can use it.",
                ephemeral=True
            )
            return

        # Go back to main menu
        broadcasts = await self.view.storage.get_guild_broadcasts(self.view.guild_id, active_only=False)

        view = BroadcastMenuView(
            self.view.bot,
            self.view.storage,
            self.view.guild_id,
            self.view.admin_id,
            broadcasts
        )

        embed = await view.create_main_embed(interaction.guild.name)

        await interaction.response.edit_message(embed=embed, view=view)


# ============================================================================
# MODALS
# ============================================================================

class CreateBroadcastModal(Modal):
    """Modal for creating a new broadcast"""

    def __init__(self, bot, storage, guild_id):
        super().__init__(title="Create New Broadcast")
        self.bot = bot
        self.storage = storage
        self.guild_id = guild_id

        self.name = TextInput(
            label="Broadcast Name",
            placeholder="e.g., Daily Bump Reminder",
            style=discord.TextStyle.short,
            max_length=100,
            required=True
        )
        self.add_item(self.name)

        self.message = TextInput(
            label="Message Content",
            placeholder="The message to send to opted-in members...",
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=True
        )
        self.add_item(self.message)

        self.interval = TextInput(
            label="Interval (minutes)",
            placeholder=f"Minimum: {MIN_RECURRING_INTERVAL_MINUTES} minutes",
            style=discord.TextStyle.short,
            max_length=6,
            required=True
        )
        self.add_item(self.interval)

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name.value.strip()
        message = self.message.value.strip()

        try:
            interval_minutes = int(self.interval.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ Interval must be a number.",
                ephemeral=True
            )
            return

        # Validate name
        name_valid, name_error = await validate_broadcast_name(name)
        if not name_valid:
            await interaction.response.send_message(name_error, ephemeral=True)
            return

        # Validate interval
        if interval_minutes < MIN_RECURRING_INTERVAL_MINUTES:
            await interaction.response.send_message(
                f"❌ Minimum interval is {MIN_RECURRING_INTERVAL_MINUTES} minutes to prevent spam.",
                ephemeral=True
            )
            return

        # Check active broadcast limit
        active_count = await self.storage.count_active_broadcasts(self.guild_id)
        if active_count >= MAX_ACTIVE_BROADCASTS_PER_GUILD:
            await interaction.response.send_message(
                f"❌ Maximum of {MAX_ACTIVE_BROADCASTS_PER_GUILD} active broadcasts reached.\n"
                f"Please delete or pause an existing broadcast first.",
                ephemeral=True
            )
            return

        # Check if name already exists
        existing_broadcasts = await self.storage.get_guild_broadcasts(self.guild_id, active_only=False)
        if any(b["broadcast_name"] == name for b in existing_broadcasts):
            await interaction.response.send_message(
                f"❌ A broadcast named `{name}` already exists. Please choose a different name.",
                ephemeral=True
            )
            return

        # Validate content
        is_valid, reason = await validate_broadcast_content(
            message,
            interaction.user.id,
            self.guild_id,
            self.storage
        )

        if not is_valid:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Create broadcast
        broadcast_id = await self.storage.create_broadcast({
            "guild_id": self.guild_id,
            "created_by": interaction.user.id,
            "broadcast_name": name,
            "message_content": message,
            "interval_minutes": interval_minutes,
            "is_active": True,
            "paused": False
        })

        # Schedule the recurring broadcast
        await self.bot.get_cog("broadcast")._schedule_broadcast(broadcast_id)

        embed = discord.Embed(
            title="✅ Broadcast Created",
            description=f"Recurring reminder **{name}** has been created and scheduled.",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(
            name="📝 Message",
            value=message[:1024],
            inline=False
        )

        embed.add_field(
            name="⏰ Interval",
            value=f"{interval_minutes} minutes",
            inline=True
        )

        # Get subscriber count
        subs = await self.storage.get_guild_subscriptions(self.guild_id)
        embed.add_field(
            name="👥 Eligible Recipients",
            value=f"{len(subs)} opted-in members",
            inline=True
        )

        embed.set_footer(text=f"Broadcast ID: {broadcast_id}")

        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"Broadcast created: {broadcast_id} by admin {interaction.user.id} in guild {self.guild_id}")


class EditBroadcastModal(Modal):
    """Modal for editing an existing broadcast"""

    def __init__(self, bot, storage, guild_id, admin_id, broadcast):
        super().__init__(title=f"Edit: {broadcast['broadcast_name']}")
        self.bot = bot
        self.storage = storage
        self.guild_id = guild_id
        self.admin_id = admin_id
        self.broadcast = broadcast

        self.message = TextInput(
            label="Message Content",
            placeholder="The message to send to opted-in members...",
            style=discord.TextStyle.paragraph,
            default=broadcast.get("message_content", ""),
            max_length=2000,
            required=True
        )
        self.add_item(self.message)

        if broadcast.get("interval_minutes"):
            self.interval = TextInput(
                label="Interval (minutes)",
                placeholder=f"Minimum: {MIN_RECURRING_INTERVAL_MINUTES} minutes",
                style=discord.TextStyle.short,
                default=str(broadcast.get("interval_minutes")),
                max_length=6,
                required=True
            )
            self.add_item(self.interval)

    async def on_submit(self, interaction: discord.Interaction):
        message = self.message.value.strip()

        updates = {"message_content": message}

        # Validate interval if applicable
        if self.broadcast.get("interval_minutes"):
            try:
                interval_minutes = int(self.interval.value.strip())
            except ValueError:
                await interaction.response.send_message(
                    "❌ Interval must be a number.",
                    ephemeral=True
                )
                return

            if interval_minutes < MIN_RECURRING_INTERVAL_MINUTES:
                await interaction.response.send_message(
                    f"❌ Minimum interval is {MIN_RECURRING_INTERVAL_MINUTES} minutes.",
                    ephemeral=True
                )
                return

            updates["interval_minutes"] = interval_minutes

        # Validate content
        is_valid, reason = await validate_broadcast_content(
            message,
            interaction.user.id,
            self.guild_id,
            self.storage
        )

        if not is_valid:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Update broadcast
        await self.storage.update_broadcast(str(self.broadcast["_id"]), updates)

        embed = discord.Embed(
            title="✅ Broadcast Updated",
            description=f"Broadcast **{self.broadcast['broadcast_name']}** has been updated.",
            color=discord.Color.green()
        )

        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"Broadcast {self.broadcast['_id']} updated by admin {interaction.user.id}")


# ============================================================================
# CONFIRMATION VIEWS
# ============================================================================

class ConfirmDeleteView(View):
    """Confirmation view for deleting a broadcast"""

    def __init__(self, bot, storage, guild_id, admin_id, broadcast):
        super().__init__(timeout=30)
        self.bot = bot
        self.storage = storage
        self.guild_id = guild_id
        self.admin_id = admin_id
        self.broadcast = broadcast

    @discord.ui.button(label="✅ Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message(
                "❌ Only the admin who initiated this can confirm.",
                ephemeral=True
            )
            return

        # Delete the broadcast
        await self.storage.delete_broadcast(str(self.broadcast["_id"]))

        # Cancel timer
        await self.bot.get_cog("broadcast")._cancel_broadcast_timer(str(self.broadcast["_id"]))

        await interaction.response.send_message(
            f"🗑️ **Broadcast Deleted**\n\n"
            f"Broadcast **{self.broadcast['broadcast_name']}** has been permanently deleted.",
            ephemeral=True
        )

        logger.info(f"Broadcast {self.broadcast['_id']} deleted by admin {interaction.user.id}")
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message(
                "❌ Only the admin who initiated this can cancel.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "❌ Deletion cancelled.",
            ephemeral=True
        )
        self.stop()


class ConfirmBroadcastView(discord.ui.View):
    """Confirmation view for large broadcasts"""

    def __init__(self, bot, storage, guild_id, admin_id, message, recipient_count):
        super().__init__(timeout=60)
        self.bot = bot
        self.storage = storage
        self.guild_id = guild_id
        self.admin_id = admin_id
        self.message = message
        self.recipient_count = recipient_count

    @discord.ui.button(label="✅ Confirm Send", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm and send the broadcast"""

        if interaction.user.id != self.admin_id:
            await interaction.response.send_message(
                "❌ Only the admin who initiated this can confirm.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Create broadcast
        broadcast_id = await self.storage.create_broadcast({
            "guild_id": self.guild_id,
            "created_by": self.admin_id,
            "broadcast_name": f"One-time ({datetime.utcnow().strftime('%Y-%m-%d %H:%M')})",
            "message_content": self.message,
            "interval_minutes": None,
            "is_active": False,
            "paused": False
        })

        # Send
        successful, failed = await self.bot.broadcast_worker.send_broadcast(broadcast_id)

        embed = discord.Embed(
            title="✅ Broadcast Sent",
            description=f"Broadcast delivered to {self.recipient_count} members.",
            color=discord.Color.green()
        )

        embed.add_field(name="✅ Successful", value=str(successful), inline=True)
        embed.add_field(name="❌ Failed", value=str(failed), inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Disable buttons
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the broadcast"""

        if interaction.user.id != self.admin_id:
            await interaction.response.send_message(
                "❌ Only the admin who initiated this can cancel.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "❌ Broadcast cancelled.",
            ephemeral=True
        )

        self.stop()


async def setup(bot):
    """Load the cog"""
    await bot.add_cog(BroadcastAdmin(bot))
    logger.info("BroadcastAdmin cog loaded")
