# Python
"""
Public-facing Premium Features
Commands and functionality available to premium guild members
"""

import discord
from discord.ext import commands

from utils.logger import get_logger

logger = get_logger("PremiumFeatures")

class PremiumFeatures(commands.Cog):
    """Public-facing premium features and utilities."""

    def __init__(self, bot):
        self.bot = bot

    # NOTE: Premium activation moved to /bump settings menu
    # Admin management moved to admin_panel.py (DM-only, owner-only)

    # Future public premium features can be added here


async def setup(bot):
    await bot.add_cog(PremiumFeatures(bot))
