import asyncio
import time
from discord.ext import commands
from utils.logger import get_logger

logger = get_logger("StartUp")

class StartUp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
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

            active_timers, _ = await bump_handler.get_timers(config)

            for bot_name, end_time in active_timers:
                remaining = end_time - time.time()
                asyncio.create_task(bump_handler.schedule_reminder(channel, remaining, config.bump_role, bot_name))
        except Exception as e:
            logger.exception(f"[{guild.id}] Error during processing: {e}")

async def setup(bot):
    logger.info("Setting up StartUp Cog...")
    await bot.add_cog(StartUp(bot))