"""
User Alert Commands
Allows users to opt-in/out of admin broadcast DMs
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from utils.logger import get_logger
from ..config import (
    DEFAULT_OPT_IN_MESSAGE,
    DEFAULT_FIRST_TIME_AUTH_MESSAGE,
    DEFAULT_ALREADY_SUBSCRIBED_MESSAGE,
    DEFAULT_NOT_SUBSCRIBED_MESSAGE,
    DEFAULT_OPT_OUT_MESSAGE,
    USER_AUTH_URL_TEMPLATE
)

logger = get_logger("AlertCommands")


class AlertCommands(commands.GroupCog, name="alerts"):
    """Commands for managing DM alert subscriptions"""

    def __init__(self, bot):
        self.bot = bot
        self.storage = bot.broadcast_storage  # Set by bot during cog load

    @app_commands.command(name="subscribe", description="Toggle your DM alert subscription for this server")
    async def subscribe_alerts(self, interaction: discord.Interaction):
        """Toggle user's DM alert subscription for this server"""

        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server!",
                ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        user_id = interaction.user.id

        # Check current subscription status
        existing = await self.storage.get_subscription(guild_id, user_id)

        # Determine if user is currently subscribed
        is_subscribed = (
            existing and
            existing.get("is_subscribed") and
            not existing.get("left_guild_at")
        )

        if is_subscribed:
            # User is subscribed - unsubscribe them
            await self.storage.deactivate_subscription(guild_id, user_id, reason="manual")

            await interaction.response.send_message(
                DEFAULT_OPT_OUT_MESSAGE.format(guild_name=interaction.guild.name),
                ephemeral=True
            )

            logger.info(f"User {user_id} unsubscribed from guild {guild_id}")

        else:
            # User is not subscribed - subscribe them
            # Check if user has global authorization
            is_authorized = await self.storage.is_user_authorized(user_id)

            if is_authorized:
                # Simple opt-in (already authorized)
                await self.storage.create_subscription(guild_id, user_id, verified=True)

                await interaction.response.send_message(
                    DEFAULT_OPT_IN_MESSAGE.format(guild_name=interaction.guild.name),
                    ephemeral=True
                )

                logger.info(f"User {user_id} subscribed to guild {guild_id} (already authorized)")

            else:
                # First-time user - needs to authorize the app
                await self.storage.create_subscription(guild_id, user_id, verified=False)

                # Create authorization button with guild_id in state parameter
                auth_url = USER_AUTH_URL_TEMPLATE.format(
                    client_id=self.bot.user.id,
                    guild_id=guild_id
                )

                view = discord.ui.View()
                view.add_item(discord.ui.Button(
                    label="🔐 Authorize App",
                    url=auth_url,
                    style=discord.ButtonStyle.link
                ))

                await interaction.response.send_message(
                    DEFAULT_FIRST_TIME_AUTH_MESSAGE.format(guild_name=interaction.guild.name),
                    view=view,
                    ephemeral=True
                )

                logger.info(f"User {user_id} started authorization process for guild {guild_id}")

    @app_commands.command(name="status", description="Check your alert subscription status for this server")
    async def alert_status(self, interaction: discord.Interaction):
        """Show user's subscription status for this server"""

        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server!",
                ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        user_id = interaction.user.id

        subscription = await self.storage.get_subscription(guild_id, user_id)
        is_authorized = await self.storage.is_user_authorized(user_id)

        if subscription and subscription.get("is_subscribed") and not subscription.get("left_guild_at"):
            # User is subscribed
            last_sent = subscription.get("last_dm_sent")
            last_sent_text = (
                f"<t:{int(last_sent.timestamp())}:R>"
                if last_sent else "Never"
            )

            subscribed_at = subscription.get("subscribed_at")
            subscribed_text = (
                f"<t:{int(subscribed_at.timestamp())}:R>"
                if subscribed_at else "Unknown"
            )

            embed = discord.Embed(
                title="✅ Alert Subscription Status",
                description=f"You're subscribed to admin DM alerts for **{interaction.guild.name}**",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )

            embed.add_field(
                name="📅 Subscribed",
                value=subscribed_text,
                inline=True
            )

            embed.add_field(
                name="📬 Last Alert",
                value=last_sent_text,
                inline=True
            )

            embed.add_field(
                name="🔐 Authorization Status",
                value="✅ Authorized" if is_authorized else "⚠️ Pending",
                inline=True
            )

            embed.set_footer(text="Run /alerts subscribe again to unsubscribe")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        else:
            # User is not subscribed
            embed = discord.Embed(
                title="❌ Alert Subscription Status",
                description=f"You're not subscribed to admin DM alerts for **{interaction.guild.name}**",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )

            embed.add_field(
                name="How to subscribe",
                value="Use `/alerts subscribe` to start receiving important notifications from server admins.",
                inline=False
            )

            if is_authorized:
                embed.add_field(
                    name="🔐 Authorization Status",
                    value="✅ Already authorized - you can subscribe instantly!",
                    inline=False
                )
            else:
                embed.add_field(
                    name="🔐 Authorization Required",
                    value="First time subscribing will require one-time app authorization.",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        logger.info(f"User {user_id} checked status for guild {guild_id}")


async def setup(bot):
    """Load the cog"""
    await bot.add_cog(AlertCommands(bot))
    logger.info("AlertCommands cog loaded")
