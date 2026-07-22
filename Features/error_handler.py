"""Global application-command error handler for ImperialReminder.

Registers a single `CommandTree.on_error` so that unhandled slash-command and
interaction errors are logged with context and surfaced to the user as a clean
ephemeral message instead of Discord's bare "interaction failed".

Ported from TheDecree/TheCodex (`Features/error_handler.py`); the handler is
defensive and only sends a response when one has not already been sent, so it
never double-responds over a local handler.
"""

import discord
from discord import app_commands
from discord.ext import commands

from storage.log import get_logger

logger = get_logger("ErrorHandler")


class ErrorHandler(commands.Cog):
    """Installs a global app-command error handler on the command tree."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._previous = bot.tree.on_error
        bot.tree.on_error = self.on_app_command_error

    async def cog_unload(self):
        # Restore whatever handler was in place before this cog loaded.
        self.bot.tree.on_error = self._previous

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        original = getattr(error, "original", error)

        if isinstance(error, app_commands.CommandOnCooldown):
            await self._respond(
                interaction,
                "Slow down",
                f"This command is on cooldown. Try again in "
                f"**{round(error.retry_after, 1)}** seconds.",
                discord.Color.orange(),
            )
            return

        if isinstance(error, app_commands.MissingPermissions):
            perms = ", ".join(p.replace("_", " ").title() for p in error.missing_permissions)
            await self._respond(
                interaction,
                "Missing Permissions",
                f"You need the following permissions:\n**{perms}**",
            )
            return

        if isinstance(error, app_commands.BotMissingPermissions):
            perms = ", ".join(p.replace("_", " ").title() for p in error.missing_permissions)
            logger.warning(f"Bot missing permissions in guild {interaction.guild_id}: {perms}")
            await self._respond(
                interaction,
                "Bot Missing Permissions",
                f"I need the following permissions to do this:\n**{perms}**\n\n"
                "Please ask a server administrator to grant them.",
            )
            return

        if isinstance(error, app_commands.CheckFailure):
            # Most checks already sent their own response; only fill the gap.
            await self._respond(
                interaction,
                "Command Unavailable",
                "This command cannot be used right now.",
                discord.Color.orange(),
            )
            return

        if isinstance(error, app_commands.CommandNotFound):
            logger.debug(f"Command not found: {getattr(interaction.command, 'qualified_name', 'unknown')}")
            return

        # Stale interaction (404 Unknown interaction) - nothing we can send.
        if isinstance(original, discord.NotFound) and getattr(original, "code", None) == 10062:
            logger.debug("Interaction expired before a response could be sent")
            return

        if isinstance(original, discord.Forbidden):
            logger.warning(f"Forbidden in guild {interaction.guild_id}: {original}")
            await self._respond(
                interaction,
                "Permission Denied",
                "I don't have permission to do that. Please check my role and "
                "channel permissions.",
            )
            return

        # Anything else is unexpected: log with full context + stack trace.
        logger.error(
            "Unhandled command error: %s: %s",
            type(original).__name__,
            original,
            extra={
                "guild_id": interaction.guild_id,
                "user_id": getattr(interaction.user, "id", None),
                "command": getattr(interaction.command, "qualified_name", None),
            },
            exc_info=original,
        )
        await self._respond(
            interaction,
            "Something went wrong",
            "An unexpected error occurred. It has been logged and will be "
            "investigated. Please try again in a moment.",
        )

    async def _respond(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        color: discord.Color = discord.Color.red(),
    ):
        """Send an ephemeral error embed, but only if nothing was sent yet."""
        embed = discord.Embed(title=title, description=description, color=color)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException as e:
            # A local handler may have already responded, or the interaction
            # expired. Nothing more we can do; don't mask the original error.
            logger.debug(f"Could not deliver error response: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandler(bot))
