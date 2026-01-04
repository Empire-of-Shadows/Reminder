"""
Member Tracking Listener
Deactivates subscriptions when users leave guilds
"""

import discord
from discord.ext import commands
from utils.logger import get_logger

logger = get_logger("MemberTracking")


class MemberTracking(commands.Cog):
    """Tracks member join/leave events for subscription management"""

    def __init__(self, bot):
        self.bot = bot
        self.storage = bot.broadcast_storage

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """
        Deactivate subscription when user leaves guild

        This prevents sending DMs to users who are no longer in the server,
        which could be seen as spam.
        """
        guild_id = member.guild.id
        user_id = member.id

        # Check if user has a subscription
        subscription = await self.storage.get_subscription(guild_id, user_id)

        if subscription and subscription.get("is_subscribed"):
            # Deactivate subscription
            await self.storage.deactivate_subscription(
                guild_id,
                user_id,
                reason="left_guild"
            )

            logger.info(
                f"Deactivated subscription for user {user_id} in guild {guild_id} "
                f"(left server: {member.guild.name})"
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Optionally reactivate subscription if user rejoins

        If a user had previously subscribed and left, we can reactivate
        their subscription when they rejoin (they'll need to re-opt-in manually).
        """
        guild_id = member.guild.id
        user_id = member.id

        # Check if user has a deactivated subscription
        subscription = await self.storage.get_subscription(guild_id, user_id)

        if subscription and subscription.get("left_guild_at"):
            # Clear the left_guild_at timestamp but keep is_subscribed = False
            # User must manually rejoin with /alerts join
            await self.storage.subscriptions.update_one(
                {"_id": f"{guild_id}_{user_id}"},
                {"$set": {"left_guild_at": None}}
            )

            logger.info(
                f"User {user_id} rejoined guild {guild_id} "
                f"(previous subscription exists but not reactivated)"
            )

    # NOTE: on_guild_remove cleanup is now handled by the unified GuildLifecycleManager
    # in cogs/core/guild_lifecycle.py to coordinate cleanup across all bot systems


async def setup(bot):
    """Load the cog"""
    await bot.add_cog(MemberTracking(bot))
    logger.info("MemberTracking cog loaded")
