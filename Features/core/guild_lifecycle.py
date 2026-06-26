import asyncio
from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import commands

from storage.logging import get_logger

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

            # Cache guild
            if hasattr(self.bot, "cache_manager"):
                await self.bot.cache_manager.cache_all(guild)

        except Exception as e:
            logger.error(f"Error on_guild_join for {guild.name}: {e}", exc_info=True)

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
