import asyncio
import time
from discord.ext import commands
from storage.log import get_logger

logger = get_logger("StartUp")

class StartUp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Fires on reconnects. On first boot this cog is loaded *inside* the
        # main on_ready handler, so this listener misses that dispatch - the
        # entry point calls reschedule_all_guilds() directly for boot.
        await self.reschedule_all_guilds()

    async def reschedule_all_guilds(self):
        logger.info("Initializing tasks for all guilds...")
        for guild in self.bot.guilds:
            asyncio.create_task(self.process_guild(guild))
        logger.info("Tasks initialized for all guilds.")

    async def process_guild(self, guild):
        try:
            config = await self.bot.guild_config_manager.get_config(guild.id)
            if not config.bump_channel or not config.bump_role:
                return

            channel = self.bot.get_channel(config.bump_channel)
            if not channel:
                return

            bump_handler = self.bot.get_cog("BumpHandler")
            if not bump_handler:
                return

            active_timers, expired_timers = await bump_handler.get_timers(config)

            for bot_name, end_time in active_timers:
                remaining = end_time - time.time()
                asyncio.create_task(bump_handler.schedule_reminder(channel, remaining, config.bump_role, bot_name))

            # Cooldowns that elapsed while the bot was offline must still fire,
            # otherwise the reminder is silently lost on restart - but only if the
            # reminder for that bump never went out. Without this check every restart
            # re-pings a cooldown that was already announced (BumpHandler records
            # `{bot}_reminded` = the bump it reminded about, once the message sends).
            backfill = {}
            for bot_name in expired_timers:
                bumped_at = int(config.timestamps.get(f"{bot_name}_timestamp", 0) or 0)
                reminded_key = f"{bot_name}_reminded"
                if reminded_key not in config.timestamps:
                    # Guild predating the marker: there is no record of what was already
                    # announced, so assume it was rather than re-pinging on this boot.
                    backfill[f"timestamps.{reminded_key}"] = bumped_at
                    continue
                if int(config.timestamps.get(reminded_key, 0) or 0) >= bumped_at:
                    logger.debug(
                        f"[{guild.id}] Skipping {bot_name} reminder on boot - already sent"
                    )
                    continue
                asyncio.create_task(bump_handler.schedule_reminder(channel, 0, config.bump_role, bot_name))

            if backfill:
                await self.bot.guild_config_manager.set_values(guild.id, backfill)
        except Exception as e:
            logger.exception(f"[{guild.id}] Error during processing: {e}")

async def setup(bot):
    logger.info("Setting up StartUp Cog...")
    await bot.add_cog(StartUp(bot))