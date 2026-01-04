import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from cogs.time_handler import TimerHandler
from cogs.broadcast.storage import BroadcastStorage
from cogs.broadcast.oauth_server import OAuthServer
from utils.logger import get_logger

logger = get_logger("Leveling")

# Avoid reading TOKEN here; keep secrets in the entry file.
# Keep APP_ID validation but allow .env for local dev convenience.
load_dotenv()
APP_ID = os.getenv("DISCORD_CLIENT_ID")
if not APP_ID:
    logger.critical("No DISCORD CLIENT ID found in environment variables!")
    raise ValueError("No DISCORD CLIENT ID found in environment variables!")

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    logger.critical("No MONGO_URI found in environment variables!")
    raise ValueError("No MONGO_URI found in environment variables!")

# Configure Discord intents (enable only those you really need)
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.members = True
intents.presences = True


class CustomBot(commands.AutoShardedBot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            application_id=int(APP_ID),
        )
        self.timer_handler = TimerHandler(self)
        self.broadcast_storage = BroadcastStorage(MONGO_URI)
        self.broadcast_worker = None  # Set during cog load
        self.oauth_server = None  # OAuth callback server for user authorization
        self.initial_sync_done = False
        self.api_process = None
        self._ready = False

    def get_bot_guild_ids(self):
        return [guild.id for guild in self.guilds]

    def is_ready(self) -> bool:
        try:
            ready_status = self._ready
            guild_count = len(self.guilds)
            logger.info(f"Checking bot readiness: ready={ready_status}, guild_count={guild_count}")
            return ready_status and guild_count > 0
        except Exception as e:
            logger.error(f"Error while checking bot readiness: {e}", exc_info=True)
            return False

    async def setup_hook(self):
        logger.info("Running setup hook...")
        try:
            # Initialize broadcast database indexes
            logger.info("Setting up broadcast system database indexes...")
            await self.broadcast_storage.setup_indexes()
            logger.info("Broadcast database indexes created successfully.")

            # Start OAuth server for user authorization
            logger.info("Starting OAuth callback server...")
            self.oauth_server = OAuthServer(self, self.broadcast_storage)
            await self.oauth_server.start()
            logger.info("OAuth server started successfully.")

            # Load all extensions before syncing so all commands are registered
            # Core infrastructure
            await self.load_extension("cogs.core.guild_lifecycle")

            # Bump system
            await self.load_extension("cogs.start_up")
            await self.load_extension("cogs.bump.detection.handler")
            await self.load_extension("cogs.bump.commands.setup")  # Contains /bump setup and /bump settings
            await self.load_extension("cogs.bump.display.embed_manager")

            # Other systems
            await self.load_extension("idle.idle")
            await self.load_extension("cogs.premium.premium")
            await self.load_extension("cogs.premium.admin_panel")  # Owner-only admin panel

            # Load broadcast system cogs
            logger.info("Loading broadcast system cogs...")
            await self.load_extension("cogs.broadcast.commands.alerts")
            await self.load_extension("cogs.broadcast.commands.broadcast_admin")
            await self.load_extension("cogs.broadcast.listeners.member_tracking")
            await self.load_extension("cogs.broadcast.worker")
            logger.info("Broadcast system cogs loaded successfully.")

            # Store reference to broadcast worker
            self.broadcast_worker = self.get_cog("BroadcastWorker")

            # Do the initial sync here (idempotent across restarts)
            if not self.initial_sync_done:
                try:
                    await self.tree.sync()  # or use guild-scoped sync during development
                    self.initial_sync_done = True
                    logger.info("Initial command sync completed in setup_hook.")
                except Exception as e:
                    logger.error(f"Command sync in setup_hook failed: {e}", exc_info=True)

            logger.info("All cogs loaded successfully.")
        except Exception as e:
            logger.error(f"Error in setup_hook: {e}", exc_info=True)
            raise

    async def on_ready(self):
        # Do not exit early unless both ready and sync are already done
        if self._ready and self.initial_sync_done:
            logger.info("on_ready called again, skipping redundant work.")
            return

        logger.info("on_ready fired.")
        try:
            # Fallback: if setup_hook didn't manage to sync, do it here
            if not self.initial_sync_done:
                logger.info("Performing command sync in on_ready (fallback)...")
                await self.tree.sync()
                self.initial_sync_done = True
                logger.info("Command sync completed successfully (on_ready).")

            # Optional small delay to let caches populate
            await asyncio.sleep(1)

            logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
            if self.guilds:
                logger.info(f"Connected to {len(self.guilds)} guild(s).")
            else:
                logger.warning("No guilds connected yet.")

            self._ready = True
            logger.info("Bot is now marked as ready.")
        except Exception as e:
            logger.error(f"Error in on_ready: {e}", exc_info=True)



# Keep a single shared instance for imports across the app.
bot = CustomBot()

def get_bot_instance():
    return bot