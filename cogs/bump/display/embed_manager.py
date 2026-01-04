import asyncio
from typing import List, Tuple
import discord
from discord.ext import commands

from cogs.bump.storage.database import bump_storage
from utils.logger import get_logger

logger = get_logger("TimerEmbedManager")


class TimerEmbedManager(commands.Cog):
    """Manages the persistent timer embed that shows bump cooldown status."""

    def __init__(self, bot):
        self.bot = bot
        self._pending_updates = {}  # guild_id -> task mapping
        self._update_lock = asyncio.Lock()

    def create_timer_embed(
        self,
        active_timers: List[Tuple[str, int]],
        expired_timers: List[str],
        role_id: int
    ) -> discord.Embed:
        """
        Create an embed showing bump timer status.

        Args:
            active_timers: List of (bot_name, end_timestamp) tuples
            expired_timers: List of bot_names that are ready to bump
            role_id: Role ID to mention for bumping

        Returns:
            Discord embed with timer information
        """
        purple = 0x7603FF
        embed = discord.Embed(
            title="Bump Timer Status",
            color=purple
        )

        # Add active timers
        if active_timers:
            active_text = []
            for bot_name, end_timestamp in sorted(active_timers, key=lambda x: x[1]):
                active_text.append(
                    f"**{bot_name.capitalize()}**: <t:{end_timestamp}:R>"
                )
            embed.add_field(
                name="⏰ Active Timers",
                value="\n".join(active_text),
                inline=False
            )

        # Add expired timers
        if expired_timers:
            expired_text = []
            for bot_name in expired_timers:
                expired_text.append(f"**{bot_name.capitalize()}**: Ready to bump!")
            embed.add_field(
                name="✅ Ready to Bump",
                value="\n".join(expired_text),
                inline=False
            )

        # Add footer
        if expired_timers:
            embed.set_footer(text=f"💡 Bump now and I'll remind you when it's time again!")
        else:
            embed.set_footer(text=f"🕐 Timers update automatically after each bump")

        return embed

    async def schedule_embed_update(
        self,
        guild_id: int,
        channel_id: int,
        role_id: int,
        active_timers: List[Tuple[str, int]],
        expired_timers: List[str]
    ):
        """
        Schedule an update to the timer embed message.

        This method debounces updates to avoid spamming Discord API when multiple
        bumps happen in quick succession.

        Args:
            guild_id: Discord guild ID
            channel_id: Channel to post/update the embed in
            role_id: Role ID for bump notifications
            active_timers: List of (bot_name, end_timestamp) tuples
            expired_timers: List of bot_names ready to bump
        """
        try:
            # Cancel any pending update for this guild
            async with self._update_lock:
                if guild_id in self._pending_updates:
                    self._pending_updates[guild_id].cancel()

                # Schedule new update with 2-second debounce
                task = asyncio.create_task(
                    self._delayed_update(
                        guild_id, channel_id, role_id, active_timers, expired_timers
                    )
                )
                self._pending_updates[guild_id] = task

        except Exception as e:
            logger.error(f"[{guild_id}] Error scheduling embed update: {e}", exc_info=True)

    async def _delayed_update(
        self,
        guild_id: int,
        channel_id: int,
        role_id: int,
        active_timers: List[Tuple[str, int]],
        expired_timers: List[str]
    ):
        """
        Perform the actual embed update after debounce delay.
        Deletes the old message and sends a new one to keep it at the bottom.
        """
        try:
            # Wait for debounce to batch multiple bumps together
            # This allows users to bump multiple bots without spamming timer messages
            await asyncio.sleep(10)

            # Check if timers should be displayed
            config = await bump_storage.get_guild(guild_id)
            if not config.get("timers_message", True):
                logger.debug(f"[{guild_id}] Timer messages disabled, skipping update")
                return

            # Get the channel
            channel = self.bot.get_channel(channel_id)
            if not channel:
                try:
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        channel = await guild.fetch_channel(channel_id)
                except Exception as e:
                    logger.warning(f"[{guild_id}] Could not fetch channel {channel_id}: {e}")
                    return

            if not channel:
                logger.warning(f"[{guild_id}] Channel {channel_id} not found for embed update")
                return

            # Create the embed
            embed = self.create_timer_embed(active_timers, expired_timers, role_id)

            # Delete the old timer message if it exists
            existing_msg_id = await bump_storage.load_embed_message_id(guild_id, channel_id)

            if existing_msg_id:
                try:
                    message = await channel.fetch_message(existing_msg_id)
                    await message.delete()
                    logger.debug(f"[{guild_id}] Deleted old timer embed message {existing_msg_id}")
                except discord.NotFound:
                    logger.debug(f"[{guild_id}] Old timer message {existing_msg_id} already deleted")
                except discord.Forbidden:
                    logger.warning(f"[{guild_id}] Missing permissions to delete old timer message {existing_msg_id}")
                except discord.HTTPException as e:
                    logger.warning(f"[{guild_id}] Failed to delete old timer message: {e}")

            # Send new message (will appear at the bottom)
            try:
                message = await channel.send(embed=embed)
                await bump_storage.save_embed_message_id(guild_id, channel_id, message.id)
                logger.info(f"[{guild_id}] Sent new timer embed message {message.id}")
            except discord.Forbidden:
                logger.error(f"[{guild_id}] Missing permissions to send embed in channel {channel_id}")
            except discord.HTTPException as e:
                logger.error(f"[{guild_id}] Failed to send embed message: {e}")

        except asyncio.CancelledError:
            logger.debug(f"[{guild_id}] Embed update cancelled (likely debounced)")
            raise
        except Exception as e:
            logger.error(f"[{guild_id}] Error updating timer embed: {e}", exc_info=True)
        finally:
            # Clean up pending update tracking
            async with self._update_lock:
                self._pending_updates.pop(guild_id, None)

    async def manual_update(self, guild_id: int, channel_id: int):
        """
        Manually trigger a timer embed update for a guild.

        This is useful for slash commands that want to refresh the timer display.

        Args:
            guild_id: Discord guild ID
            channel_id: Channel containing the timer embed

        Returns:
            True if successful, False otherwise
        """
        try:
            config = await bump_storage.get_guild(guild_id)
            if not config:
                logger.warning(f"[{guild_id}] No config found for manual update")
                return False

            role_id = config.get("bump_role")
            if not role_id:
                logger.warning(f"[{guild_id}] No bump role configured")
                return False

            # Import here to avoid circular dependency
            from cogs.bump.detection.handler import BumpHandler
            bump_handler = BumpHandler(self.bot)
            active_timers, expired_timers = await bump_handler.get_timers(config)

            await self.schedule_embed_update(
                guild_id, channel_id, role_id, active_timers, expired_timers
            )
            return True

        except Exception as e:
            logger.error(f"[{guild_id}] Error in manual embed update: {e}", exc_info=True)
            return False


async def setup(bot):
    """Load the TimerEmbedManager cog."""
    logger.info("Setting up TimerEmbedManager Cog...")
    await bot.add_cog(TimerEmbedManager(bot))
