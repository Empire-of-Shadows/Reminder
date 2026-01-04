# Python
import asyncio
from datetime import datetime, timedelta, timezone

import aiohttp
from discord.ext import commands, tasks

from cogs.bump.storage.database import BumpStorage
from utils.logger import get_logger

logger = get_logger("PremiumManager")

class PremiumManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = BumpStorage().db
        self.codes_collection = self.db["codes"]
        self.entitlements_collection = self.db["entitlements_cache"]

        # Ensure indexes for fast lookup and automatic cleanup of expired cache
        # - user_id: query by user
        # - expires_at: TTL index to remove docs automatically when the time passes
        self._ensure_indexes_task = asyncio.create_task(self._ensure_indexes())

        # Periodic job to process expired subscriptions
        self.expiry_sweeper.start()

    async def cog_unload(self):
        # Properly cancel background tasks on cog unload
        self.expiry_sweeper.cancel()
        if not self._ensure_indexes_task.done():
            self._ensure_indexes_task.cancel()

    async def _ensure_indexes(self):
        try:
            await self.entitlements_collection.create_index("user_id")
            # TTL index: remove cache row once expires_at is in the past
            # Note: expires_at must be a BSON datetime for TTL to work
            await self.entitlements_collection.create_index(
                "expires_at",
                expireAfterSeconds=0
            )
        except Exception as e:
            logger.error(f"Failed to create entitlements cache indexes: {e}", exc_info=True)

    async def _fetch_entitlements_from_api(self, user_id: int):
        """
        Fetch entitlements from Discord API for a user.
        Returns list of entitlement objects or an empty list on failure.
        """
        try:
            app_id = self.bot.application_id
            token = self.bot.http.token  # Using the bot token from discord.py client

            # Prefer a short-lived client session for this request to avoid relying on private internals.
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://discord.com/api/v10/applications/{app_id}/entitlements",
                    params={"user_id": user_id, "exclude_ended": "true"},
                    headers={"Authorization": f"Bot {token}"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data or []
                    text = await response.text()
                    logger.warning(
                        f"Failed to fetch entitlements for user {user_id}. "
                        f"HTTP {response.status}: {text}"
                    )
        except Exception as e:
            logger.error(f"Error fetching entitlements for user {user_id}: {e}", exc_info=True)
        return []

    async def _upsert_entitlement_cache(self, user_id: int, entitlement: dict):
        """
        Upsert a single entitlement into the cache.
        Expected entitlement fields from Discord: id, sku_id, consumed, starts_at, ends_at
        """
        try:
            entitlement_id = str(entitlement["id"])
            sku_id = str(entitlement.get("sku_id"))
            consumed = bool(entitlement.get("consumed", False))

            # ends_at can be None for lifetime; default to a safe horizon if not present
            ends_at_raw = entitlement.get("ends_at")
            if ends_at_raw:
                # Parse RFC3339/ISO8601 timestamps to aware datetime
                expires_at = datetime.fromisoformat(ends_at_raw.replace("Z", "+00:00"))
            else:
                # If Discord doesn’t provide an ends_at, cache for a short period (e.g., 2 days)
                expires_at = datetime.now(timezone.utc) + timedelta(days=2)

            doc = {
                "user_id": int(user_id),
                "entitlement_id": entitlement_id,
                "sku_id": sku_id,
                "consumed": consumed,
                "expires_at": expires_at,  # stored as BSON datetime
                "updated_at": datetime.now(timezone.utc),
            }
            await self.entitlements_collection.update_one(
                {"user_id": int(user_id), "entitlement_id": entitlement_id},
                {"$set": doc},
                upsert=True,
            )
        except Exception as e:
            logger.error(f"Failed to upsert cache for entitlement {entitlement.get('id')}: {e}", exc_info=True)

    async def get_user_entitlement(self, user_id: int) -> str | None:
        """
        Returns an active, unconsumed entitlement_id for a user.
        Strategy:
          1) Check cache for an unconsumed entitlement with future expires_at.
          2) On miss, fetch from Discord API, upsert cache, and return the first valid.
        """
        try:
            now = datetime.now(timezone.utc)
            cached = await self.entitlements_collection.find_one({
                "user_id": int(user_id),
                "consumed": False,
                "expires_at": {"$gt": now},
            })

            if cached:
                logger.info(f"[cache-hit] Entitlement for user {user_id}: {cached['entitlement_id']}")
                return str(cached["entitlement_id"])

            # Cache miss -> fetch from API
            entitlements = await self._fetch_entitlements_from_api(user_id)
            for ent in entitlements:
                if not ent.get("consumed", False):
                    # upsert and return first valid
                    await self._upsert_entitlement_cache(user_id, ent)
                    logger.info(f"[cache-fill] Entitlement for user {user_id}: {ent['id']}")
                    return str(ent["id"])

            logger.info(f"No active entitlements found for user {user_id}")
            return None

        except Exception as e:
            logger.error(f"Error in get_user_entitlement for user {user_id}: {e}", exc_info=True)
            return None

    async def consume_entitlement(self, entitlement_id: str, user_id: int):
        """Consumes an entitlement and updates cache."""
        try:
            app_id = self.bot.application_id
            token = self.bot.http.token

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://discord.com/api/v10/applications/{app_id}/entitlements/{entitlement_id}/consume",
                    headers={"Authorization": f"Bot {token}"}
                ) as response:
                    if response.status == 204:
                        logger.info(f"Successfully consumed entitlement {entitlement_id} for user {user_id}")
                        # Mark as consumed in cache
                        await self.entitlements_collection.update_one(
                            {"user_id": int(user_id), "entitlement_id": str(entitlement_id)},
                            {"$set": {"consumed": True, "updated_at": datetime.now(timezone.utc)}}
                        )
                        return True
                    else:
                        error_data = await response.text()
                        logger.warning(
                            f"Failed to consume entitlement {entitlement_id}. "
                            f"Status: {response.status}. Response: {error_data}"
                        )
                        return False

        except Exception as e:
            logger.error(f"Error consuming entitlement {entitlement_id}: {e}", exc_info=True)
            return False

    @commands.Cog.listener()
    async def on_entitlement_create(self, entitlement):
        """
        Handles new purchases and auto-renewals from the Discord shop.
        Also updates the entitlement cache instantly to avoid API round-trips.
        """
        logger.info(
            f"Received entitlement: {entitlement.id} for user {entitlement.user_id} with SKU {entitlement.sku_id}"
        )
        try:
            discord_user_id = int(entitlement.user_id)
            sku_id = str(entitlement.sku_id)
            entitlement_id = str(entitlement.id)

            subscription_durations = {
                "1376261800005341355": 30,  # 30-day premium subscription (guild)
            }
            trial_durations = {
                "1379563955608879115": 7,  # 7-day trial (once per guild)
            }

            # Cache entry based on event payload (ends_at may not be provided by the lib; use duration)
            now = datetime.now(timezone.utc)
            if sku_id in trial_durations:
                days_valid = trial_durations[sku_id]
            else:
                days_valid = subscription_durations.get(sku_id)

            if not days_valid:
                logger.warning(f"Unhandled SKU: {sku_id}")
                return

            # Allow a small grace period
            expiry_date = now + timedelta(days=days_valid + 2)

            # Upsert cache immediately
            await self.entitlements_collection.update_one(
                {"user_id": discord_user_id, "entitlement_id": entitlement_id},
                {"$set": {
                    "user_id": discord_user_id,
                    "entitlement_id": entitlement_id,
                    "sku_id": sku_id,
                    "consumed": False,
                    "expires_at": expiry_date,
                    "updated_at": now,
                }},
                upsert=True
            )

            # Existing subscriptions logic (stored in codes collection) remains as-is:
            #  - Extend existing subscription or insert new one
            #  - Uses ISO format in your codes collection; keep consistent there
            existing_subscription = await self.codes_collection.find_one({
                "issued_to": discord_user_id,
                "type": "premium" if sku_id in subscription_durations else "trial",
                "expired": False,
                "expires_at": {"$gte": now.isoformat()},
                "entitlement_id": entitlement_id
            })

            if existing_subscription:
                new_expiry_date = datetime.fromisoformat(
                    existing_subscription["expires_at"]
                ) + timedelta(days=days_valid)

                await self.codes_collection.update_one(
                    {"_id": existing_subscription["_id"]},
                    {"$set": {"expires_at": new_expiry_date.isoformat()}}
                )

                if existing_subscription.get("linked_guild"):
                    await BumpStorage().set_guild(
                        existing_subscription["linked_guild"],
                        "premium.enabled",
                        True
                    )

                user = await self.bot.fetch_user(discord_user_id)
                await user.send(
                    f"🔄 Your subscription has been renewed!\n"
                    f"Valid until: {new_expiry_date.strftime('%Y-%m-%d %H:%M:%S')} (UTC)"
                )
            else:
                subscription_data = {
                    "type": "premium" if sku_id in subscription_durations else "trial",
                    "issued_to": discord_user_id,
                    "linked_guild": 0,
                    "issued_at": now.isoformat(),
                    "expires_at": expiry_date.isoformat(),
                    "expired": False,
                    "entitlement_id": entitlement_id,
                }
                await self.codes_collection.insert_one(subscription_data)

                user = await self.bot.fetch_user(discord_user_id)
                await user.send(
                    f"🎉 Thank you for your {'purchase' if sku_id in subscription_durations else 'trial subscription'}!\n\n"
                    f"Use `/bump settings` → **Activate Premium** in your server to enable premium features.\n"
                    f"⚠️ Valid until: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')} (UTC)"
                )

        except Exception as e:
            logger.error(f"Error handling entitlement creation: {e}", exc_info=True)

    @tasks.loop(minutes=60)
    async def expiry_sweeper(self):
        """Periodic task to handle expired premium subscriptions (codes collection)."""
        start = datetime.now(timezone.utc)
        try:
            logger.info("Checking for expired subscriptions...")
            now = datetime.now(timezone.utc)

            expired_subscriptions = await self.codes_collection.find({
                "expires_at": {"$lt": now.isoformat()},
                "expired": False,
            }).to_list(length=None)

            if not expired_subscriptions:
                return

            for subscription in expired_subscriptions:
                discord_user_id = subscription["issued_to"]
                linked_guild = subscription.get("linked_guild")

                await self.codes_collection.update_one(
                    {"_id": subscription["_id"]},
                    {"$set": {"expired": True}}
                )

                if linked_guild:
                    await BumpStorage().set_guild(
                        linked_guild,
                        "premium.enabled",
                        False
                    )
                    await BumpStorage().set_guild(
                        linked_guild,
                        "premium.activated_by",
                        0
                    )
                    logger.info(f"Subscription expired and premium revoked for guild {linked_guild}.")

                # Notify user
                try:
                    user = await self.bot.fetch_user(discord_user_id)
                    if user:
                        await user.send(
                            "⚠️ Your premium subscription has expired. "
                            "Renew now to continue enjoying premium features!"
                        )
                except Exception as notify_err:
                    logger.warning(f"Failed to notify user {discord_user_id} about expiry: {notify_err}")

        except Exception as e:
            logger.error(f"Error checking expired subscriptions: {e}", exc_info=True)
        finally:
            duration = (datetime.now(timezone.utc) - start).total_seconds()
            logger.info(f"Expiry sweep completed in {duration:.2f}s")

    @expiry_sweeper.before_loop
    async def _wait_until_ready(self):
        await self.bot.wait_until_ready()