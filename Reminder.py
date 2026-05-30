import asyncio
import os
import signal
import sys
import time
import logging
from pathlib import Path

# Load env from docker/.env if it exists, otherwise use standard load_dotenv
from dotenv import load_dotenv
env_path = Path(__file__).parent / "docker" / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

import discord
from tabulate import tabulate

from utils.bot import bot, TOKEN, s
from utils.logger import get_logger, setup_application_logging
from utils.sync import load_cogs, attach_databases
from health_endpoint import initialize_health_server, stop_health_server
from storage.database_manager import db_manager

# Initialize application-wide logging
APPLICATION_NAME = "ImperialReminder"
app_logger = setup_application_logging(
	app_name=APPLICATION_NAME,
	log_level=logging.INFO,
	log_dir="log",
	enable_performance_logging=True,
	max_file_size=20 * 1024 * 1024,  # 20 MB
	backup_count=10
)

# Main logger for this module
logger = get_logger("main")

async def on_ready():
	"""
    Handles the bot's readiness state and performs initialization tasks.
    """
	logger.info(f"Bot logged in as {bot.user}")
	logger.info(f"Bot ID: {bot.user.id}")
	logger.info(f"Connected to {len(bot.guilds)} guilds")

	if getattr(bot, "_init_done", False):
		try:
			await bot.change_presence(status=discord.Status.online)
		except Exception as e:
			logger.error(f"Error setting presence on reconnect: {e}", exc_info=True)
		return

	startup_start = time.perf_counter()

	try:
		# Database attachment phase
		db_start = time.perf_counter()
		try:
			await attach_databases()
			db_time = time.perf_counter() - db_start
			logger.info(f"Database attachment completed in {db_time:.2f}s")
		except Exception as attaching_error:
			logger.fatal(f"Error during database attachment: {attaching_error}", exc_info=True)
			return

		# Cog loading phase
		cog_start = time.perf_counter()
		await load_cogs()
		cog_time = time.perf_counter() - cog_start
		logger.info(f"Cog loading completed in {cog_time:.2f}s")

		# Command synchronization phase
		sync_start = time.perf_counter()
		try:
			synced_global = await bot.tree.sync()
			sync_time = time.perf_counter() - sync_start
			logger.info(
				f"Command synchronization completed in {sync_time:.2f}s; "
				f"{len(synced_global)} global commands synchronized."
			)
		except Exception as e:
			logger.error(f"Error during command synchronization: {e}", exc_info=True)
			raise

		# Set initial online presence
		try:
			await bot.change_presence(status=discord.Status.online)
		except Exception as e:
			logger.error(f"Error setting initial presence: {e}", exc_info=True)

		# Log final startup metrics
		total_startup_time = time.perf_counter() - startup_start
		logger.info(f"Bot startup completed successfully in {total_startup_time:.2f}s")
		logger.info("=" * 60)
		logger.info("IMPERIAL REMINDER IS NOW ONLINE AND READY")
		logger.info("=" * 60)

		bot._init_done = True

	except Exception as e:
		logger.error(f"Critical error during bot initialization: {e}", exc_info=True)
		raise

bot.event(on_ready)

async def shutdown_handler():
	"""
    Handles the shutdown process for the application.
    """
	logger.info("Initiating graceful shutdown...")
	shutdown_start = time.perf_counter()

	# Stop health check server
	try:
		stop_health_server()
	except Exception as e:
		logger.error(f"Error stopping health server: {e}", exc_info=True)

	# Close bot connection
	try:
		if not bot.is_closed():
			await bot.close()
			logger.info("Bot connection closed successfully")
	except Exception as shutdown_error:
		logger.error(f"Error during bot shutdown: {shutdown_error}", exc_info=True)

	# Log shutdown metrics
	shutdown_time = time.perf_counter() - shutdown_start
	logger.info(f"Shutdown completed in {shutdown_time:.2f}s")
	logger.info("Application terminated")


async def start_services():
	"""
    Starts the services required for the application.
    """
	logger.info(f"Starting {APPLICATION_NAME} services...")
	logger.info(f"Python version: {os.sys.version}")
	logger.info(f"Discord.py version: {discord.__version__}")

	service_start = time.perf_counter()

	try:
		# Initialize database before health server
		logger.info("Initializing DatabaseManager...")
		try:
			await db_manager.initialize()
			logger.info("DatabaseManager initialized successfully")
		except Exception as db_err:
			logger.error(f"DatabaseManager initialization failed: {db_err}", exc_info=True)

		# Start health check server
		logger.info("Initializing health check endpoint on port 50006...")
		initialize_health_server(port=50006, bot=bot)
		logger.info("Health check endpoint initialized successfully")

		# Start the bot
		logger.info("Starting Discord bot...")
		bot_task = asyncio.create_task(bot.start(TOKEN))

		await asyncio.gather(bot_task)

	except asyncio.CancelledError:
		logger.info("Service startup was cancelled")
		raise
	except Exception as e:
		service_time = time.perf_counter() - service_start
		logger.error(f"Critical error in services after {service_time:.2f}s: {e}", exc_info=True)
		raise
	finally:
		await shutdown_handler()


if __name__ == "__main__":
	def signal_handler(signum, frame):
		logger.info(f"Received signal {signum}, initiating shutdown...")
		sys.exit(0)

	signal.signal(signal.SIGINT, signal_handler)
	signal.signal(signal.SIGTERM, signal_handler)

	try:
		logger.info(f"=== Starting {APPLICATION_NAME} ===")
		asyncio.run(start_services())
	except KeyboardInterrupt:
		logger.info("Received keyboard interrupt signal")
	except SystemExit:
		logger.info("Received system exit signal")
	except Exception as e:
		logger.critical(f"Fatal error occurred: {e}", exc_info=True)
		sys.exit(1)
	finally:
		logger.info(f"=== {APPLICATION_NAME} shutdown complete ===")
