import os
import discord
from discord.ext import commands

from utils.env import load_project_env

# Load environment variables from docker/.env
load_project_env()
TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")

# Configure Discord intents - deliberately lean: guilds for the guild/channel
# cache, guild_messages + message_content for bump-success detection (the bot
# reads other bots' messages/embeds in the configured bump channel). members is
# kept only for the guild snapshot cache and is removed with it in the storage
# migration.
intents = discord.Intents.none()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
intents.members = True

# Initialize bot instance. Slash-only (ecosystem convention): no text prefix,
# the bot only responds to application commands / mentions. AllowedMentions is
# locked down at the constructor; the reminder sender explicitly re-enables
# ONLY the configured bump role per send.
bot = commands.Bot(
    command_prefix=commands.when_mentioned,
    intents=intents,
    help_command=None,
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=False),
)

# Configuration defaults
TIMEZONE_NAME = "America/Chicago"

# Logging indent helper
s = " " * 5

__all__ = [
    "bot", "TOKEN",
    "s", "TIMEZONE_NAME"
]
