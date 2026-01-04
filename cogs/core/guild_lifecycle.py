# Python
import asyncio
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.logger import get_logger

logger = get_logger("GuildLifecycle")

REQUIRED_PERMISSIONS = (
    "send_messages",
    "embed_links",
    "read_message_history",
)


class GuildLifecycleManager(commands.Cog):
    """
    Unified guild lifecycle management for all bot systems.

    Coordinates initialization and cleanup across:
    - Bump tracking system
    - Broadcast system
    - Any future systems
    """

    def __init__(self, bot):
        self.bot = bot

    async def _sync_commands_with_backoff(self, guild: discord.Guild, *, attempts: int = 3) -> bool:
        """Sync slash commands to a guild with exponential backoff"""
        delay = 2.0
        for i in range(1, attempts + 1):
            try:
                await self.bot.tree.sync(guild=guild)
                logger.info(f"✅ Synced commands to {guild.name} ({guild.id}) [attempt {i}]")
                return True
            except Exception as e:
                logger.warning(f"⚠️ Sync attempt {i}/{attempts} failed for {guild.name} ({guild.id}): {e}")
                if i < attempts:
                    await asyncio.sleep(delay)
                    delay *= 2.0
        logger.error(f"❌ Failed to sync commands to {guild.name} ({guild.id}) after {attempts} attempts")
        return False

    def _report_missing_permissions(self, guild: discord.Guild) -> list[str]:
        """Check for missing bot permissions in a guild"""
        try:
            me = guild.me
            if not me:
                return ["bot member not resolvable"]

            channel: Optional[discord.abc.GuildChannel] = guild.system_channel
            if channel is None:
                for ch in guild.text_channels:
                    channel = ch
                    break
            if channel is None:
                return ["no text channels available to inspect permissions"]

            channel_perms = channel.permissions_for(me)
            missing = []
            for p in REQUIRED_PERMISSIONS:
                if not getattr(channel_perms, p, False):
                    missing.append(p)
            return missing
        except Exception as e:
            logger.error(f"[{guild.id}] Failed to compute missing permissions: {e}", exc_info=True)
            return ["unable to compute"]

    async def _send_owner_onboarding(self, guild: discord.Guild):
        """Send onboarding message to guild owner"""
        try:
            owner = guild.owner or await self.bot.fetch_user(guild.owner_id)
            if not owner:
                return
            missing = self._report_missing_permissions(guild)
            missing_text = ", ".join(missing) if missing else "none"

            msg = (
                f"Hi! Thanks for adding me to {guild.name}.\n\n"
                f"Quick start:\n"
                f"1) Set the bump channel and role in /setup_bump\n"
                f"2) Enable the bots you use (DISBOARD/others) in /bump_settings\n"
                f"3) I'll schedule reminders after the next bump\n\n"
                f"Permissions check (at a sample channel): missing -> {missing_text}\n"
                f"If you need help, run /help."
            )
            await owner.send(msg)
        except discord.Forbidden:
            pass
        except Exception as e:
            logger.warning(f"[{guild.id}] Could not DM owner onboarding message: {e}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """
        Handle bot joining a new guild.

        Initializes both bump and broadcast systems.
        """
        gid = guild.id
        try:
            # === BUMP SYSTEM INITIALIZATION ===
            from cogs.bump.storage.database import bump_storage

            # Ensure default bump config exists
            cfg = await bump_storage.get_guild(gid)
            logger.info(f"[{gid}] Loaded/initialized bump config for {guild.name}")

            # Clear any stale bump timers
            try:
                if hasattr(self.bot, "timer_handler"):
                    count = self.bot.timer_handler.cancel_by_scope(guild_id=gid, timer_type="bump")
                    if count:
                        logger.info(f"[{gid}] Cleared {count} stale bump timers on join")
            except Exception as e:
                logger.warning(f"[{gid}] Unable to clear stale bump timers on join: {e}")

            # === BROADCAST SYSTEM INITIALIZATION ===
            # Note: Broadcast subscriptions are created on-demand when users opt-in
            # No initialization needed here

            # === SHARED SETUP ===
            # Try syncing commands with retry
            await self._sync_commands_with_backoff(guild)

            # Best-effort onboarding message to owner
            asyncio.create_task(self._send_owner_onboarding(guild))

            # Log missing permissions
            missing = self._report_missing_permissions(guild)
            if missing:
                logger.warning(f"[{gid}] Missing permissions in a sample channel: {missing}")

            logger.info(f"[{gid}] Join initialization complete for {guild.name}")

        except Exception as e:
            logger.error(f"[{gid}] Error during on_guild_join for {guild.name}: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """
        Handle bot being removed from a guild.

        Coordinates cleanup across all systems:
        - Cancels all bump timers
        - Archives bump configuration
        - Deactivates broadcast subscriptions
        - Pauses broadcast schedules
        """
        gid = int(guild.id)
        try:
            # === BUMP SYSTEM CLEANUP ===
            # Cancel all bump timers for this guild
            try:
                if hasattr(self.bot, "timer_handler"):
                    count = self.bot.timer_handler.cancel_by_scope(guild_id=gid, timer_type="bump")
                    if count:
                        logger.info(f"[{gid}] Cancelled {count} bump timer(s) on guild removal")
            except Exception as e:
                logger.warning(f"[{gid}] Unable to cancel bump timers on guild removal: {e}")

            # Archive and delete bump config
            await self._archive_and_delete_bump_config(guild)

            # === BROADCAST SYSTEM CLEANUP ===
            if hasattr(self.bot, "broadcast_storage"):
                storage = self.bot.broadcast_storage

                # Deactivate all subscriptions
                subscriptions = await storage.get_guild_subscriptions(
                    gid,
                    active_only=False,
                    verified_only=False
                )

                deactivated_count = 0
                for sub in subscriptions:
                    if sub.get("is_subscribed"):
                        await storage.deactivate_subscription(
                            gid,
                            sub["user_id"],
                            reason="bot_removed"
                        )
                        deactivated_count += 1

                # Deactivate all broadcasts
                broadcasts = await storage.get_guild_broadcasts(gid, active_only=True)
                for broadcast in broadcasts:
                    await storage.update_broadcast(
                        str(broadcast["_id"]),
                        {"is_active": False, "paused": True}
                    )

                    # Cancel broadcast timers
                    try:
                        if hasattr(self.bot, "timer_handler"):
                            self.bot.timer_handler.cancel_by_scope(
                                guild_id=gid,
                                timer_type="broadcast"
                            )
                    except Exception as e:
                        logger.warning(f"[{gid}] Unable to cancel broadcast timers: {e}")

                logger.info(
                    f"[{gid}] Broadcast cleanup: "
                    f"deactivated {deactivated_count} subscriptions, {len(broadcasts)} broadcasts"
                )

            logger.info(f"[{gid}] Full cleanup complete for {guild.name}")

        except Exception as e:
            logger.error(f"[{gid}] Error during on_guild_remove for {guild.name}: {e}", exc_info=True)

    async def _archive_and_delete_bump_config(self, guild: discord.Guild):
        """Archive and delete bump configuration for a guild"""
        gid = str(guild.id)
        try:
            from cogs.bump.storage.database import bump_storage

            # Fetch current config if exists
            doc = await bump_storage.collection.find_one({"_id": gid})
            if doc:
                # Soft-archive to a separate collection before deletion
                doc_copy = {
                    **doc,
                    "removed_at": datetime.now(timezone.utc).isoformat(),
                    "reason": "guild_removed"
                }
                await bump_storage.db["BumpArchive"].insert_one(doc_copy)

                # Delete the original
                result = await bump_storage.collection.delete_one({"_id": gid})
                if result.deleted_count > 0:
                    logger.info(f"[{gid}] Removed bump configuration for guild: {guild.name} ({guild.id}).")
                else:
                    logger.warning(f"[{gid}] Bump config delete returned 0 for: {guild.name} ({guild.id}).")
            else:
                logger.warning(f"[{gid}] No bump configuration found to delete for guild: {guild.name} ({guild.id}).")
        except Exception as e:
            logger.error(f"[{gid}] Failed to archive/delete bump config for {guild.name} ({guild.id}): {e}", exc_info=True)


async def setup(bot):
    """Load the lifecycle management cogs"""
    await bot.add_cog(GuildLifecycleManager(bot))
    logger.info("Guild lifecycle management cogs loaded")
