import asyncio
from datetime import datetime, timedelta, timezone
import aiohttp
from discord.ext import commands, tasks
from utils.logger import get_logger

logger = get_logger("PremiumManager")

class PremiumManagerCog(commands.Cog, name="premium_logic"):
    def __init__(self, bot):
        self.bot = bot
        self._initialized = False

    async def cog_load(self):
        self.expiry_sweeper.start()

    async def cog_unload(self):
        self.expiry_sweeper.cancel()

    @tasks.loop(minutes=60)
    async def expiry_sweeper(self):
        """Periodic task to handle expired premium subscriptions."""
        try:
            logger.info("Checking for expired subscriptions...")
            now = datetime.now(timezone.utc)

            # Using the new premium_manager
            pm = self.bot.premium_manager
            codes_col = self.bot.db_manager.premium_codes

            expired = await codes_col.find_many({
                "expires_at": {"$lt": now.isoformat()},
                "expired": False,
            })

            for sub in expired:
                user_id = sub["issued_to"]
                guild_id = sub.get("linked_guild")

                await codes_col.update_one({"_id": sub["_id"]}, {"$set": {"expired": True}})

                if guild_id and str(guild_id) != "0":
                    await self.bot.guild_config_manager.set_value(int(guild_id), "premium.enabled", False)
                    await self.bot.guild_config_manager.set_value(int(guild_id), "premium.activated_by", 0)
                    logger.info(f"Premium revoked for guild {guild_id}")

                try:
                    user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                    if user: await user.send("⚠️ Your premium subscription has expired.")
                except: pass

        except Exception as e:
            logger.error(f"Error in expiry_sweeper: {e}", exc_info=True)

    @expiry_sweeper.before_loop
    async def _wait_until_ready(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(PremiumManagerCog(bot))