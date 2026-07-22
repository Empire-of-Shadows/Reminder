"""
Startup sync logic (shared sibling-pattern across EoS bots).

Holds the cog-loading machinery and command-table logging used during startup:
    - `load_cogs()`        → priority cogs first (sequential), the rest in parallel
    - `attach_databases()` → wire DB-dependent managers onto the bot (per-bot body)
    - `log_all_commands()` → prefix table + slash command tree (children under parent)

Per-bot differences are limited to the logger import, `COG_DIRECTORIES` /
`PRIORITY_COG_DIRECTORIES`, and the body of `attach_databases()`.
"""

import asyncio
import os
from pathlib import Path

import discord
from tabulate import tabulate

from startup.bot import bot, s
from storage.log import get_logger

logger = get_logger("Sync")


# Cog discovery roots. Priority cogs load first (sequential) for ordering-sensitive
# setup; the rest load in parallel for a faster boot.
COG_DIRECTORIES = ["./commands", "./Features", "./admin"]
PRIORITY_COG_DIRECTORIES: list[str] = []


def discover_cog_modules(directories: list[str]) -> list[tuple[str, str]]:
    """
    Walk directories and return a list of (module_name, file_path) tuples.
    Does not load anything — just discovers (skips already-loaded modules).
    """
    cogs = []
    for base_dir in directories:
        if not os.path.exists(base_dir):
            logger.debug(f"Directory does not exist, skipping: {base_dir}")
            continue
        for root, _, files in os.walk(base_dir):
            for file in files:
                if not file.endswith(".py") or file.startswith("__"):
                    continue
                module_name = generate_cog_module_name(root, file)
                if module_name not in bot.extensions:
                    cogs.append((module_name, os.path.join(root, file)))
    return cogs


async def load_cogs():
    """
    Load all cogs from the configured directories. Priority cogs (ordering-sensitive)
    load first sequentially; the remaining cogs load in parallel for a faster boot.
    """
    success_logs = [f"{s}Starting cog loading process...\n"]
    failed_logs = []

    # Phase 1: discover all cogs
    priority_cogs = discover_cog_modules(PRIORITY_COG_DIRECTORIES)
    regular_cogs = discover_cog_modules(COG_DIRECTORIES)

    # Filter priority cogs out of the regular set (avoid double-loading)
    priority_modules = {mod for mod, _ in priority_cogs}
    regular_cogs = [(mod, path) for mod, path in regular_cogs if mod not in priority_modules]

    logger.debug(f"Discovered {len(priority_cogs)} priority cogs, {len(regular_cogs)} regular cogs")

    # Phase 2: load priority cogs first (sequential — ordering matters)
    if priority_cogs:
        success_logs.append(f"{s}Loading priority cogs (sequential)...\n")
        for module_name, file_path in priority_cogs:
            result, is_success = await safely_load_cog(module_name, file_path)
            if result is None:
                continue
            if is_success:
                success_logs.append(result)
            else:
                failed_logs.append(result)

    # Phase 3: load remaining cogs in parallel
    if regular_cogs:
        success_logs.append(f"{s}Loading remaining cogs (parallel)...\n")
        results = await asyncio.gather(
            *[safely_load_cog(mod, path) for mod, path in regular_cogs],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                failed_logs.append(f"{s}Unexpected error: {result}\n")
            else:
                log_msg, is_success = result
                if log_msg is None:
                    continue
                if is_success:
                    success_logs.append(log_msg)
                else:
                    failed_logs.append(log_msg)

    # Summary
    if failed_logs:
        failed_logs.insert(0, f"{s}Failed to load the following cogs:\n")
    success_logs.append(f"{s}Successfully loaded cogs:\n")

    final_logs = failed_logs + success_logs if failed_logs else success_logs
    logger.info("\n" + "".join(final_logs) + f"{s}Cog loading process completed.\n")


async def safely_load_cog(module, file_path):
    """
    Dynamically import and load a cog module.
    Returns a formatted log line and a success flag. Skips files without setup().
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "\ndef setup(" not in content and "\nasync def setup(" not in content:
            logger.debug(f"Skipping {module} - no setup() function")
            return None, None
    except Exception:
        pass  # File unreadable; let load_extension surface the real error

    try:
        await bot.load_extension(module)
        return f"{s}  {module}\n", True
    except Exception as e:
        return f"{s}  FAILED {module} -> Error: {e}\n", False


def generate_cog_module_name(root, file):
    """Generate the fully qualified module name from root and file."""
    relative_path = os.path.relpath(os.path.join(root, file), start=str(Path("."))).replace("\\", "/")
    module_name = relative_path.replace("/", ".").removesuffix(".py")
    logger.debug(f"Generating module name for {file}: {module_name}")
    return module_name


async def attach_attribute(attribute_name, attribute_value):
    """Safely attach an attribute to the bot and return its status."""
    try:
        setattr(bot, attribute_name, attribute_value)
        return f"{s}✅ {attribute_name}: {attribute_value}\n", True
    except Exception as e:
        return f"{s}❌ {attribute_name} → Error: {e}\n", False


async def attach_databases():
    """
    Initialize and attach the DB-dependent managers onto the bot instance.
    Groups successfully attached (`✅`) and failed (`❌`) attributes in one log.
    """
    success_logs = [f"{s}🔄 Starting database attachment process...\n"]
    failed_logs = []

    try:
        # Initialize DatabaseManager first
        from storage.settings.collections import db_manager
        try:
            await db_manager.initialize()
            result, is_success = await attach_attribute("db_manager", db_manager)
            (success_logs if is_success else failed_logs).append(result)
        except Exception as db_error:
            failed_logs.append(f"{s}❌ db_manager → Error: {db_error}\n")
            raise  # Can't continue without db_manager

        # Audit log manager
        from storage.audit_log import get_audit_log_manager
        try:
            audit_log_manager = get_audit_log_manager(db_manager)
            result, is_success = await attach_attribute("audit_log", audit_log_manager)
            (success_logs if is_success else failed_logs).append(result)
        except Exception as audit_error:
            failed_logs.append(f"{s}❌ audit_log → Error: {audit_error}\n")

        # Unified GuildConfigManager
        try:
            from storage.config_manager import get_guild_config_manager
            guild_config_manager = await get_guild_config_manager(db_manager)
            result, is_success = await attach_attribute("guild_config_manager", guild_config_manager)
            (success_logs if is_success else failed_logs).append(result)
        except Exception as config_error:
            failed_logs.append(f"{s}❌ guild_config_manager → Error: {config_error}\n")

        # Setup gatekeeper
        try:
            from storage.setup_gatekeeper import setup_gatekeeper
            setup_gatekeeper.set_config_manager(guild_config_manager)
            result, is_success = await attach_attribute("setup_gatekeeper", setup_gatekeeper)
            (success_logs if is_success else failed_logs).append(result)
        except Exception as gate_error:
            failed_logs.append(f"{s}❌ setup_gatekeeper → Error: {gate_error}\n")

        # Premium manager
        from storage.premium_manager import get_premium_manager
        try:
            premium_manager = await get_premium_manager(db_manager)
            result, is_success = await attach_attribute("premium_manager", premium_manager)
            (success_logs if is_success else failed_logs).append(result)
        except Exception as premium_error:
            failed_logs.append(f"{s}❌ premium_manager → Error: {premium_error}\n")

        # Timer handler
        from Features.time_handler import TimerHandler
        try:
            timer_handler = TimerHandler(bot)
            result, is_success = await attach_attribute("timer_handler", timer_handler)
            (success_logs if is_success else failed_logs).append(result)
        except Exception as timer_error:
            failed_logs.append(f"{s}❌ timer_handler → Error: {timer_error}\n")
    except Exception as e:
        failed_logs.append(f"{s}❌ Encountered a critical error during database attachment → {e}\n")

    if failed_logs:
        failed_logs.insert(0, f"{s}❌ Failed to attach the following attributes:\n")
    if success_logs:
        success_logs.insert(1 if failed_logs else 0, f"{s}✅ Successfully attached the following attributes:\n")

    final_log = failed_logs + success_logs
    logger.info("\n" + "".join(final_log) + f"{s}✅ Database attachment process completed.\n")


async def log_all_commands(bot) -> None:
    """
    Log all registered prefix and slash commands in tabular form.

    Slash commands are rendered as a tree: each group lists its subcommands
    indented beneath it, with descriptions.
    """
    prefix_commands = [
        [cmd.name, cmd.help or "No description provided", ", ".join(cmd.aliases) or "None"]
        for cmd in bot.commands
    ]

    if prefix_commands:
        prefix_table = tabulate(
            prefix_commands,
            headers=["Prefix Command", "Description", "Aliases"],
            tablefmt="fancy_grid",
        )
        logger.info(f"📝 Registered Prefix Commands ({len(prefix_commands)}):\n{prefix_table}")
    else:
        logger.info("📝 No prefix commands registered")

    slash_rows: list[list[str]] = []
    leaf_count = 0

    def add_command(cmd, depth: int = 0):
        nonlocal leaf_count
        label = ("  " * depth + "↳ " if depth else "") + cmd.name
        description = getattr(cmd, "description", None) or "No description provided"
        if isinstance(cmd, discord.app_commands.Group):
            slash_rows.append([label, description, "Group"])
            for sub in cmd.commands:
                add_command(sub, depth + 1)
        else:
            leaf_count += 1
            slash_rows.append([label, description, "Subcmd" if depth else "Slash"])

    for cmd in bot.tree.get_commands():
        add_command(cmd)

    if slash_rows:
        slash_table = tabulate(
            slash_rows,
            headers=["Command", "Description", "Type"],
            tablefmt="fancy_grid",
        )
        logger.info(f"⚡ Registered Slash Commands ({leaf_count}):\n{slash_table}")
    else:
        logger.info("⚡ No slash commands registered")
