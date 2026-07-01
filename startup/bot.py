import os
import discord
from discord.ext import commands

from utils.env import load_project_env

# Load environment variables from docker/.env
load_project_env()
TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")

# Configure Discord intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.members = True
intents.presences = True
intents.reactions = True  # Added based on TheCodex but keeping IR ones
intents.emojis = True

# Initialize bot instance
# Using commands.Bot as the ecosystem standard, can be switched to AutoShardedBot if needed
bot = commands.Bot(
    command_prefix="!",  # IR uses !, TheCodex uses .
    intents=intents,
    help_command=None,
)

# Configuration defaults
TIMEZONE_NAME = "America/Chicago"

# Logging indent helper
s = " " * 5

__all__ = [
    "bot", "TOKEN",
    "s", "TIMEZONE_NAME"
]
