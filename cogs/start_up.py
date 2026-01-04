import asyncio
import time
from discord.ext import commands
from cogs.bump.detection.handler import BumpHandler
from cogs.premium.discordpre import PremiumManager
from cogs.bump.storage.database import bump_storage
from utils.logger import get_logger

logger = get_logger("StartUp")

class StartUp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bump_handler = BumpHandler(bot)

    @commands.Cog.listener()
    async def on_ready(self):
        """Triggered when the bot is ready."""
        logger.info("Initializing tasks for all guilds...")
        for guild in self.bot.guilds:
            asyncio.create_task(self.process_guild(guild))
        logger.info("Tasks initialized for all guilds.")


        enti = PremiumManager(self.bot)
        # entitlement_id = await enti.get_user_entitlement(1264236749060575355)
        # if entitlement_id:
        #     # Now you can consume it
        #     await enti.consume_entitlement(entitlement_id, 1264236749060575355)
        #     logger.info(f"Entitlement consumed for user {1264236749060575355}")
        # else:
        #     logger.info(f"No entitlement found for user {1264236749060575355}")

    async def process_guild(self, guild):
        """Handles processing for a single guild, including scheduling reminders and sending embeds."""
        try:
            logger.info(f"[{guild.id}] Guild '{guild.name}' - Starting processing...")
            config = await bump_storage.get_guild(guild.id)  # Load guild configuration
            if not config:
                logger.warning(f"[{guild.id}] Guild '{guild.name}' - Configuration not found. Skipping...")
                return

            channel_id = config.get("bump_channel")
            role_id = config.get("bump_role")
            if not channel_id or not role_id:
                logger.warning(f"[{guild.id}] Missing bump channel or role. Skipping...")
                return

            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"[{guild.id}] Channel {channel_id} not found. Skipping...")
                return

            # Fetch timers using the correct delays
            active_timers, expired_timers = await self.bump_handler.get_timers(config)

            # Schedule reminder tasks for active timers
            tasks = []
            for bot_name, end_time in active_timers:
                remaining = end_time - time.time()
                tasks.append(self.bump_handler.schedule_reminder(channel, remaining, role_id, bot_name))

            # Start all tasks
            for task in tasks:
                asyncio.create_task(task)
        except Exception as e:
            logger.exception(f"[{guild.id}] Error during processing: {e}")

async def setup(bot):
    logger.info("Setting up StartUp Cog...")
    await bot.add_cog(StartUp(bot))