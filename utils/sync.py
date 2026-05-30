import logging
import os
from pathlib import Path

from discord.ext import commands
from tabulate import tabulate

from utils.env import load_project_env
from utils.bot import bot, s
from utils.logger import get_logger

# Load environment variables from docker/.env
load_project_env()
logger = get_logger("Sync")


# Constants
COG_DIRECTORIES = ["./commands", "./Features"]


@bot.command(name="load_cogs", help="Loads all cogs in the COG_DIRECTORIES list.")
@commands.is_owner()
async def load_cogs_command(ctx):
	"""
	Loads all cogs specified in the `COG_DIRECTORIES` list and sends a message pre- and post-execution.
	"""
	await ctx.send("Loading cogs...")
	await load_cogs()
	await ctx.send("Cogs loaded successfully.")


async def attach_databases():
	"""
	Attaches specific collections as bot attributes and logs the status.
	"""
	success_logs = [f"{s}🔄 Starting database attachment process...\n"]
	failed_logs = []

	try:
		# Initialize DatabaseManager first
		from storage.database_manager import db_manager
		try:
			await db_manager.initialize()
			result, is_success = await attach_attribute("db_manager", db_manager)
			(success_logs if is_success else failed_logs).append(result)
		except Exception as db_error:
			failed_logs.append(f"{s}❌ db_manager → Error: {db_error}\n")
			raise  # Can't continue without db_manager

		# Initialize Cache Manager
		from storage.cache import create_cache_manager
		try:
			cache_manager = create_cache_manager(db_manager)
			result, is_success = await attach_attribute("cache_manager", cache_manager)
			(success_logs if is_success else failed_logs).append(result)
		except Exception as cache_error:
			failed_logs.append(f"{s}❌ cache_manager → Error: {cache_error}\n")

		# Initialize Audit Log Manager
		from storage.audit_log import get_audit_log_manager
		try:
			audit_log_manager = get_audit_log_manager(db_manager)
			result, is_success = await attach_attribute("audit_log", audit_log_manager)
			(success_logs if is_success else failed_logs).append(result)
		except Exception as audit_error:
			failed_logs.append(f"{s}❌ audit_log → Error: {audit_error}\n")

		# Initialize unified GuildConfigManager
		try:
			from storage.config_manager import get_guild_config_manager
			guild_config_manager = await get_guild_config_manager(db_manager)
			result, is_success = await attach_attribute("guild_config_manager", guild_config_manager)
			(success_logs if is_success else failed_logs).append(result)
		except Exception as config_error:
			failed_logs.append(f"{s}❌ guild_config_manager → Error: {config_error}\n")

		# Initialize Setup Gatekeeper
		try:
			from storage.setup_gatekeeper import setup_gatekeeper
			setup_gatekeeper.set_config_manager(guild_config_manager)
			result, is_success = await attach_attribute("setup_gatekeeper", setup_gatekeeper)
			(success_logs if is_success else failed_logs).append(result)
		except Exception as gate_error:
			failed_logs.append(f"{s}❌ setup_gatekeeper → Error: {gate_error}\n")

		# Initialize PremiumManager
		from storage.premium_manager import get_premium_manager
		try:
			premium_manager = await get_premium_manager(db_manager)
			result, is_success = await attach_attribute("premium_manager", premium_manager)
			(success_logs if is_success else failed_logs).append(result)
		except Exception as premium_error:
			failed_logs.append(f"{s}❌ premium_manager → Error: {premium_error}\n")

		# Initialize TimerHandler
		from Features.time_handler import TimerHandler
		try:
			timer_handler = TimerHandler(bot)
			result, is_success = await attach_attribute("timer_handler", timer_handler)
			(success_logs if is_success else failed_logs).append(result)
		except Exception as timer_error:
			failed_logs.append(f"{s}❌ timer_handler → Error: {timer_error}\n")
	except Exception as e:
		failed_logs.append(f"{s}❌ Encountered a critical error during database attachment → {e}\n")

	# Add group headers for success and failure logs
	if failed_logs:
		failed_logs.insert(0, f"{s}❌ Failed to attach the following attributes:\n")
	if success_logs:
		success_logs.insert(1 if failed_logs else 0, f"{s}✅ Successfully attached the following attributes:\n")

	# Combine and log the final result
	final_log = failed_logs + success_logs
	logger.info("\n" + "".join(final_log) + f"{s}✅ Database attachment process completed.\n")


async def attach_attribute(attribute_name, attribute_value):
	"""
	Safely attaches an attribute to the bot and returns its status.
	"""
	try:
		setattr(bot, attribute_name, attribute_value)  # Attach to bot
		return f"{s}✅ {attribute_name}: {attribute_value}\n", True
	except Exception as e:
		return f"{s}❌ {attribute_name} → Error: {e}\n", False


async def load_cogs():
	"""
	Load all cogs from specified directories in `COG_DIRECTORIES`.
	"""
	success_logs = [f"{s}🔄 Starting cog loading process...\n"]
	failed_logs = []

	for base_dir in COG_DIRECTORIES:
		for root, _, files in os.walk(base_dir):
			for file in files:
				if not file.endswith(".py") or file.startswith("__"):
					continue

				module_name = generate_cog_module_name(root, file)

				# Skip already loaded
				if module_name in bot.extensions:
					success_logs.append(f"{s}🔄 Skipping already loaded cog: {module_name}\n")
					continue

				# Safely load the cog
				result, is_success = await safely_load_cog(module_name, os.path.join(root, file))
				if result is None:
					continue
				if is_success:
					success_logs.append(result)
				else:
					failed_logs.append(result)

	# Add summary headers
	if failed_logs:
		failed_logs.insert(0, f"{s}❌ Failed to load the following cogs:\n")
	success_logs.append(f"{s}✅ Successfully loaded the following cogs:\n")

	# Combine and log the final output
	final_logs = failed_logs + success_logs if failed_logs else success_logs
	logger.info("\n" + "".join(final_logs) + f"{s}✅ Cog loading process completed.\n")


async def safely_load_cog(module, file_path):
	"""
	Dynamically import and load a cog module.
	"""
	try:
		with open(file_path, "r", encoding="utf-8") as f:
			content = f.read()
		if "\ndef setup(" not in content and "\nasync def setup(" not in content:
			logger.debug(f"Skipping {module} — no setup() function")
			return None, None
	except Exception:
		pass

	try:
		await bot.load_extension(module)
		return f"{s}✅ {module}\n", True
	except Exception as e:
		return f"{s}❌ {module} → Error: {e}\n", False


def generate_cog_module_name(root, file):
	"""
	Helper to generate the fully qualified module name from root and file.
	"""
	relative_path = os.path.relpath(os.path.join(root, file), start=".").replace("\\", "/")
	module_name = relative_path.replace("/", ".").removesuffix(".py")
	return module_name
