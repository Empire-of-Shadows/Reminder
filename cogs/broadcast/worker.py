"""
Broadcast Delivery Worker
Background task that sends scheduled broadcasts with rate limiting and decay system
"""

import asyncio
import discord
from discord.ext import tasks, commands
from datetime import datetime, timedelta
from typing import Tuple
from utils.logger import get_logger
from .config import (
    DM_SEND_DELAY_SECONDS,
    DEFAULT_DECAY_CONFIG,
    BUTTON_ACKNOWLEDGE,
    BUTTON_OPT_OUT
)

logger = get_logger("BroadcastWorker")


class BroadcastWorker(commands.Cog):
    """Background worker for delivering scheduled broadcasts"""

    def __init__(self, bot):
        self.bot = bot
        self.storage = bot.broadcast_storage
        self._scheduled_broadcasts = {}  # broadcast_id: timer_info
        self.delivery_checker.start()

    def cog_unload(self):
        """Stop background tasks when cog is unloaded"""
        self.delivery_checker.cancel()

    @tasks.loop(seconds=60)
    async def delivery_checker(self):
        """
        Check for due broadcasts every 60 seconds

        This is a lightweight checker that schedules broadcasts using TimerHandler
        when they become due.
        """
        try:
            # Find all active, non-paused broadcasts
            all_broadcasts = []

            # We need to check all guilds the bot is in
            for guild in self.bot.guilds:
                broadcasts = await self.storage.get_guild_broadcasts(
                    guild.id,
                    active_only=True
                )
                all_broadcasts.extend(broadcasts)

            for broadcast in all_broadcasts:
                broadcast_id = str(broadcast["_id"])

                # Skip if paused
                if broadcast.get("paused"):
                    continue

                # Skip one-time broadcasts (interval_minutes is None)
                if broadcast.get("interval_minutes") is None:
                    continue

                # Check if already scheduled
                if broadcast_id in self._scheduled_broadcasts:
                    continue

                # Calculate when next send is due
                last_sent = broadcast.get("last_sent")
                interval_minutes = broadcast["interval_minutes"]

                # Apply decay multiplier
                current_multiplier = broadcast["decay_config"].get("current_multiplier", 1.0)
                effective_interval = interval_minutes * current_multiplier

                if last_sent:
                    next_send = last_sent + timedelta(minutes=effective_interval)
                    if datetime.utcnow() >= next_send:
                        # Due now - schedule immediately
                        await self._schedule_broadcast(broadcast_id, 0)
                    else:
                        # Schedule for future
                        delay_seconds = (next_send - datetime.utcnow()).total_seconds()
                        await self._schedule_broadcast(broadcast_id, max(0, delay_seconds))
                else:
                    # Never sent before - send now
                    await self._schedule_broadcast(broadcast_id, 0)

        except Exception as e:
            logger.error(f"Error in delivery_checker: {e}", exc_info=True)

    @delivery_checker.before_loop
    async def before_delivery_checker(self):
        """Wait for bot to be ready before starting"""
        await self.bot.wait_until_ready()
        logger.info("BroadcastWorker delivery checker started")

    async def _schedule_broadcast(self, broadcast_id: str, delay_seconds: float):
        """
        Schedule a broadcast using TimerHandler

        Args:
            broadcast_id: Broadcast ObjectId as string
            delay_seconds: Seconds until broadcast should be sent
        """
        broadcast = await self.storage.get_broadcast(broadcast_id)

        if not broadcast:
            logger.warning(f"Broadcast {broadcast_id} not found, skipping schedule")
            return

        guild_id = broadcast["guild_id"]

        # Use TimerHandler to schedule the send
        await self.bot.timer_handler.run_timer(
            channel_id=0,  # Not channel-specific
            guild_id=guild_id,
            name=f"broadcast_{broadcast_id}",
            delay=delay_seconds,
            callback=self._send_broadcast_callback,
            timer_type="broadcast",
            args=(broadcast_id,),
            jitter=0,  # No jitter for broadcasts
            max_retries=1,
            backoff=60.0,
            callback_timeout=300.0,  # 5 minute timeout for large broadcasts
            replace_if_sooner_than=60.0  # Only replace if >1min earlier
        )

        self._scheduled_broadcasts[broadcast_id] = {
            "guild_id": guild_id,
            "scheduled_at": datetime.utcnow()
        }

        logger.info(f"Scheduled broadcast {broadcast_id} to send in {delay_seconds}s")

    async def _send_broadcast_callback(self, broadcast_id: str):
        """
        Timer callback to send a broadcast

        This is called by TimerHandler when a broadcast is due.
        """
        try:
            await self.send_broadcast(broadcast_id)

            # Remove from scheduled dict
            if broadcast_id in self._scheduled_broadcasts:
                del self._scheduled_broadcasts[broadcast_id]

            # Reschedule if recurring
            broadcast = await self.storage.get_broadcast(broadcast_id)
            if broadcast and broadcast.get("interval_minutes") is not None:
                # Will be picked up by next delivery_checker run
                pass

        except Exception as e:
            logger.error(f"Error sending broadcast {broadcast_id}: {e}", exc_info=True)

    async def send_broadcast(self, broadcast_id: str) -> Tuple[int, int]:
        """
        Send a broadcast to all eligible users

        Args:
            broadcast_id: Broadcast ObjectId as string

        Returns:
            Tuple of (successful_sends, failed_sends)
        """
        broadcast = await self.storage.get_broadcast(broadcast_id)

        if not broadcast:
            logger.error(f"Broadcast {broadcast_id} not found")
            return 0, 0

        guild_id = broadcast["guild_id"]

        # Check and apply decay system
        if not await self._check_and_apply_decay(broadcast_id):
            logger.warning(f"Broadcast {broadcast_id} disabled by decay system")
            return 0, 0

        # Get guild
        guild = self.bot.get_guild(guild_id)
        if not guild:
            logger.error(f"Guild {guild_id} not found for broadcast {broadcast_id}")
            return 0, 0

        # Get eligible subscriptions
        subscriptions = await self.storage.get_guild_subscriptions(
            guild_id,
            active_only=True,
            verified_only=True
        )

        # Filter out acknowledged users
        acknowledged = broadcast.get("acknowledged_users", [])
        subscriptions = [
            sub for sub in subscriptions
            if sub["user_id"] not in acknowledged
        ]

        if not subscriptions:
            logger.info(f"No eligible recipients for broadcast {broadcast_id}")
            return 0, 0

        logger.info(f"Sending broadcast {broadcast_id} to {len(subscriptions)} users in guild {guild.name}")

        successful = 0
        failed = 0

        for sub in subscriptions:
            try:
                user = await self.bot.fetch_user(sub["user_id"])

                # Create control view
                view = BroadcastControlView(broadcast_id, guild_id, guild.name)

                # Send DM
                await user.send(
                    f"📢 **Message from {guild.name}**\n\n{broadcast['message_content']}",
                    view=view
                )

                successful += 1

                # Update subscription
                await self.storage.reset_dm_failures(guild_id, sub["user_id"])

                # Rate limit
                await asyncio.sleep(DM_SEND_DELAY_SECONDS)

            except discord.Forbidden:
                # User has DMs disabled or blocked bot
                failed += 1
                failures = await self.storage.increment_dm_failures(guild_id, sub["user_id"])
                logger.warning(
                    f"Failed to DM user {sub['user_id']} in guild {guild_id} "
                    f"(failures: {failures})"
                )

            except discord.NotFound:
                # User no longer exists
                failed += 1
                await self.storage.deactivate_subscription(
                    guild_id,
                    sub["user_id"],
                    reason="user_not_found"
                )
                logger.warning(f"User {sub['user_id']} not found, deactivated subscription")

            except Exception as e:
                failed += 1
                logger.error(f"Error sending DM to user {sub['user_id']}: {e}", exc_info=True)

        # Update broadcast stats
        times_sent = await self.storage.increment_broadcast_sends(broadcast_id)

        # Log to audit trail
        await self.storage.log_broadcast_send(
            broadcast_id,
            guild_id,
            broadcast["created_by"],
            successful,
            failed
        )

        logger.info(
            f"Broadcast {broadcast_id} sent: {successful} successful, {failed} failed "
            f"(total sends: {times_sent})"
        )

        return successful, failed

    async def _check_and_apply_decay(self, broadcast_id: str) -> bool:
        """
        Check broadcast against decay system and apply limits

        Returns:
            True if broadcast should continue, False if disabled
        """
        broadcast = await self.storage.get_broadcast(broadcast_id)

        if not broadcast:
            return False

        decay = broadcast.get("decay_config", DEFAULT_DECAY_CONFIG)
        times_sent = broadcast.get("times_sent", 0)

        # Check if exceeded max sends
        if times_sent >= decay["max_sends"]:
            await self.storage.update_broadcast(broadcast_id, {
                "is_active": False,
                "paused": True
            })

            logger.warning(
                f"Broadcast {broadcast_id} auto-disabled after {times_sent} sends "
                f"(max: {decay['max_sends']})"
            )

            return False

        # Check if should increase interval
        increase_after = decay["increase_interval_after"]

        if times_sent >= increase_after:
            # Calculate new multiplier
            sends_over = times_sent - increase_after
            multiplier_increase = decay.get("multiplier_increase", 0.1)
            multiplier_every_n = decay.get("multiplier_every_n_sends", 10)

            new_multiplier = 1.0 + (sends_over // multiplier_every_n) * multiplier_increase

            # Update if changed
            current_multiplier = decay.get("current_multiplier", 1.0)

            if new_multiplier != current_multiplier:
                await self.storage.update_broadcast(broadcast_id, {
                    "decay_config.current_multiplier": new_multiplier
                })

                original_interval = broadcast.get("interval_minutes", 0)
                new_interval = original_interval * new_multiplier

                logger.info(
                    f"Broadcast {broadcast_id} interval increased to {new_multiplier:.1f}x "
                    f"({original_interval}m → {new_interval:.0f}m) after {times_sent} sends"
                )

        return True

    async def cancel_broadcast_timer(self, broadcast_id: str):
        """Cancel a scheduled broadcast timer"""

        # Cancel via TimerHandler
        timer_name = f"broadcast_{broadcast_id}"

        # Find timer and cancel (this will need TimerHandler support)
        # For now, just remove from our tracking
        if broadcast_id in self._scheduled_broadcasts:
            del self._scheduled_broadcasts[broadcast_id]

        logger.info(f"Cancelled timer for broadcast {broadcast_id}")


class BroadcastControlView(discord.ui.View):
    """
    Interactive buttons for broadcast DMs

    Allows users to acknowledge, opt-out, or report spam
    """

    def __init__(self, broadcast_id: str, guild_id: int, guild_name: str):
        super().__init__(timeout=None)  # Persistent view
        self.broadcast_id = broadcast_id
        self.guild_id = guild_id
        self.guild_name = guild_name

        # Set custom_ids for persistent buttons
        self.acknowledge_button.custom_id = f"broadcast_ack:{broadcast_id}"
        self.opt_out_button.custom_id = f"broadcast_optout:{guild_id}"

    @discord.ui.button(label=BUTTON_ACKNOWLEDGE, style=discord.ButtonStyle.secondary, emoji="✅")
    async def acknowledge_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """User acknowledges this broadcast (stops future sends of this specific broadcast)"""

        # Import here to avoid circular dependency
        from shared_bot import CustomBot
        bot: CustomBot = interaction.client
        storage = bot.broadcast_storage

        # Add user to acknowledged list
        await storage.add_acknowledged_user(self.broadcast_id, interaction.user.id)

        await interaction.response.send_message(
            f"✅ **Acknowledged**\n\n"
            f"You won't receive this specific reminder from **{self.guild_name}** anymore.\n\n"
            f"You're still subscribed to other broadcasts. Use `/alerts leave` to unsubscribe completely.",
            ephemeral=True
        )

        logger.info(f"User {interaction.user.id} acknowledged broadcast {self.broadcast_id}")

    @discord.ui.button(label=BUTTON_OPT_OUT, style=discord.ButtonStyle.danger, emoji="🚫")
    async def opt_out_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """User opts out of all broadcasts from this guild"""

        # Import here to avoid circular dependency
        from shared_bot import CustomBot
        bot: CustomBot = interaction.client
        storage = bot.broadcast_storage

        # Deactivate subscription
        await storage.deactivate_subscription(
            self.guild_id,
            interaction.user.id,
            reason="manual"
        )

        await interaction.response.send_message(
            f"👋 **Unsubscribed**\n\n"
            f"You won't receive any more DM alerts from **{self.guild_name}**.\n\n"
            f"You can rejoin anytime with `/alerts join` in that server.",
            ephemeral=True
        )

        logger.info(f"User {interaction.user.id} opted out of guild {self.guild_id} via DM button")


async def setup(bot):
    """Load the cog"""
    await bot.add_cog(BroadcastWorker(bot))
    logger.info("BroadcastWorker cog loaded")
