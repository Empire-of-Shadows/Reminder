import asyncio
from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import commands

from storage.log import get_logger

logger = get_logger("GuildLifecycle")

class GuildLifecycleManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        gid = guild.id
        try:
            logger.info(f"Joined guild {guild.name} ({gid})")
            
            # Initialize config
            await self.bot.guild_config_manager.get_config(gid)
            
            # Sync commands
            try:
                await self.bot.tree.sync(guild=guild)
                logger.info(f"Synced commands to {guild.name}")
            except Exception as e:
                logger.warning(f"Failed to sync commands to {guild.name}: {e}")

            # A server that re-invites the bot still has its settings and bump
            # timestamps; rebuild its timers now instead of at the next restart.
            startup = self.bot.get_cog("StartUp")
            if startup is not None:
                await startup.process_guild(guild)

        except Exception as e:
            logger.error(f"Error on_guild_join for {guild.name}: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Forget a deleted Bump Channel or Timers Channel.

        Left in place, the dead id keeps the server looking set up: bumps are
        watched for in a channel that no longer exists, reminders fail, and the
        not-set-up notice never fires. Clearing it puts the server back in the
        state it is really in.
        """
        guild = getattr(channel, "guild", None)
        if guild is None:
            return
        try:
            config = await self.bot.guild_config_manager.get_config(guild.id)
            updates = {}
            if config.bump_channel and int(config.bump_channel) == channel.id:
                updates["bump_channel"] = 0
            if config.timers_channel and int(config.timers_channel) == channel.id:
                updates["timers_channel"] = 0
            if not updates:
                return
            await self.bot.guild_config_manager.set_values(guild.id, updates)
            if hasattr(self.bot, "setup_gatekeeper"):
                self.bot.setup_gatekeeper.invalidate(guild.id)
            logger.info(f"[{guild.id}] Cleared deleted channel {channel.id} from {sorted(updates)}")
        except Exception as e:
            logger.error(f"Error handling channel delete in guild {guild.id}: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        """Forget a deleted Bump Role or Panel Access Role (same reasoning as channels)."""
        guild = role.guild
        try:
            config = await self.bot.guild_config_manager.get_config(guild.id)
            updates = {}
            if config.bump_role and int(config.bump_role) == role.id:
                updates["bump_role"] = 0
            admin_ids = list((config.roles or {}).get("admin_role_ids") or [])
            kept = [r for r in admin_ids if str(r) != str(role.id)]
            if len(kept) != len(admin_ids):
                updates["roles.admin_role_ids"] = kept
            if not updates:
                return
            await self.bot.guild_config_manager.set_values(guild.id, updates)
            if hasattr(self.bot, "setup_gatekeeper"):
                self.bot.setup_gatekeeper.invalidate(guild.id)
            logger.info(f"[{guild.id}] Cleared deleted role {role.id} from {sorted(updates)}")
        except Exception as e:
            logger.error(f"Error handling role delete in guild {guild.id}: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        gid = guild.id
        try:
            logger.info(f"Left guild {guild.name} ({gid})")
            
            # Cancel timers
            if hasattr(self.bot, "timer_handler"):
                self.bot.timer_handler.cancel_by_scope(guild_id=gid)
            
            # Invalidate setup gatekeeper
            if hasattr(self.bot, "setup_gatekeeper"):
                self.bot.setup_gatekeeper.invalidate(gid)

        except Exception as e:
            logger.error(f"Error on_guild_remove for {guild.name}: {e}", exc_info=True)

async def setup(bot):
    logger.info("Setting up GuildLifecycleManager Cog...")
    await bot.add_cog(GuildLifecycleManager(bot))
