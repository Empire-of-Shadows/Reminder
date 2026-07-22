import asyncio
import json
import re
import time
from collections import defaultdict

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from Features.bump.display.embed_manager import TimerEmbedManager
from storage.sub_systems.bump_config import (
    DISBOARD_ID, DISBOARD_KEYWORD, TWO, Bump4You, BUMP4YOU_ID, BUMPIT_ID,
    BUMPIT_SUCCESS_KEYWORD, ONE, BUMP_BOTS, WEBUMP_ID, WEBUMP_SUCCESS,
    SUCCESS_KEYWORDS, BUMP_BOTS_INFO
)
from storage.log import get_logger

logger = get_logger("BumpHandler")

# Keep normalization simple and safe for Unicode
_ZWSP_RE = re.compile(r"[\u200B-\u200D\uFEFF]")

class BumpHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_queues = defaultdict(list)
        self.channel_tasks = {}
        self.embed_manager = TimerEmbedManager(bot)
        # Track processed bumps: (guild_id, bot_name) -> timestamp
        self._processed_bumps = {}
        self._bump_cooldown = 5.0  # seconds to ignore duplicate bump detections

    async def cog_unload(self):
        """Cancel pending 10s batch-send tasks so reload/shutdown never orphans them."""
        tasks = list(self.channel_tasks.values())
        self.channel_tasks.clear()
        self.channel_queues.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"Cancelled {len(tasks)} pending reminder batch task(s) on unload")

    def _resolve_bot_info(self, *, author_id: int | None, webhook_id: int | None, application_id: int | None):
        """
        Resolve (bot_name, delay) for a known bump bot using author_id, webhook_id, or application_id.
        """
        if author_id and author_id in BUMP_BOTS_INFO:
            return BUMP_BOTS_INFO[author_id]
        if webhook_id and webhook_id in BUMP_BOTS_INFO:
            return BUMP_BOTS_INFO[webhook_id]
        if application_id and application_id in BUMP_BOTS_INFO:
            return BUMP_BOTS_INFO[application_id]
        return None

    def _is_bump_recently_processed(self, guild_id: int, bot_name: str) -> bool:
        """
        Check if this bump was recently processed to prevent duplicate handling.
        """
        current_time = time.time()

        # Clean up old entries (older than 60 seconds)
        old_keys = [k for k, v in self._processed_bumps.items() if current_time - v > 60]
        for old_key in old_keys:
            self._processed_bumps.pop(old_key, None)

        key = (guild_id, bot_name)
        # Check if this bump was recently processed
        if key in self._processed_bumps:
            last_processed = self._processed_bumps[key]
            if current_time - last_processed < self._bump_cooldown:
                logger.debug(
                    f"[{guild_id}] Skipping duplicate {bot_name} bump detection "
                    f"(last processed {current_time - last_processed:.1f}s ago)"
                )
                return True

        # Mark this bump as processed
        self._processed_bumps[key] = current_time
        return False

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild:
            return

        config = await self.bot.guild_config_manager.get_config(message.guild.id)
        if not config or message.channel.id != config.bump_channel:
            return

        enabled_bots = config.enabled_bots

        # Resolve via author or webhook (for application webhook posts)
        bot_info = self._resolve_bot_info(
            author_id=getattr(message.author, "id", None),
            webhook_id=getattr(message, "webhook_id", None),
            application_id=None,
        )

        # Try to grab all text (embeds + content + components); if nothing found, refetch once
        text = await self.extract_all_text(message, allow_refetch=True)
        logger.info(
            f"[on_message] Guild={message.guild.id} Channel={message.channel.id} "
            f"Author={message.author.id} WebhookID={getattr(message, 'webhook_id', None)} Text='{text}'"
        )

        if bot_info:
            bot_name, delay = bot_info
            if bot_name in enabled_bots and any(keyword in text for keyword in SUCCESS_KEYWORDS):
                # Check for duplicate detection
                if self._is_bump_recently_processed(message.guild.id, bot_name):
                    return
                await self.handle_bump_success(message, bot_name, delay)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not after.guild:
            return

        config = await self.bot.guild_config_manager.get_config(after.guild.id)
        if not config or after.channel.id != config.bump_channel:
            return

        enabled_bots = config.enabled_bots

        # Resolve via author or webhook for edited message
        bot_info = self._resolve_bot_info(
            author_id=getattr(after.author, "id", None),
            webhook_id=getattr(after, "webhook_id", None),
            application_id=None,
        )

        # --- Always refetch if it's WeBump ---
        if bot_info and bot_info[0] == "WeBump":
            try:
                after = await after.channel.fetch_message(after.id)
                logger.debug(f"Force-refetch WeBump message {after.id}")
            except Exception as e:
                logger.warning(f"Failed to refetch after edit for {after.id}: {e}")

        after_text = await self.extract_all_text(after, allow_refetch=False)

        logger.info(
            f"[on_message_edit] Guild={after.guild.id} Channel={after.channel.id} Author={after.author.id} "
            f"WebhookID={getattr(after, 'webhook_id', None)} Text='{after_text}'"
        )

        if bot_info:
            bot_name, delay = bot_info
            if bot_name in enabled_bots and any(keyword in after_text for keyword in SUCCESS_KEYWORDS):
                # Check for duplicate detection
                if self._is_bump_recently_processed(after.guild.id, bot_name):
                    return
                await self.handle_bump_success(after, bot_name, delay)

    async def handle_bump_success(self, message, bot_name, delay):
        try:
            bot_name = bot_name.lower()
            logger.info(f"[{message.guild.id}] {bot_name.capitalize()} bump detected.")

            # Save bump timestamp using the new config manager
            await self.bot.guild_config_manager.set_value(
                message.guild.id, 
                f"timestamps.{bot_name}_timestamp", 
                int(time.time())
            )
            logger.info(f"[{message.guild.id}] Saved bump timestamp for {bot_name} successfully.")

            config = await self.bot.guild_config_manager.get_config(message.guild.id)
            if not config:
                logger.warning(f"[{message.guild.id}] No configuration found for the guild.")
                return

            bot_delay = config.bot_delay.get(bot_name, delay)
            logger.info(f"[{message.guild.id}] Fetched custom delay for {bot_name}: {bot_delay} seconds.")

            active_timers, expired_timers = await self.get_timers(config)

            role_id = config.bump_role
            await self.embed_manager.schedule_embed_update(
                message.guild.id, message.channel.id, role_id, active_timers, expired_timers
            )

            logger.info(f"[{message.guild.id}] Scheduling {bot_name} reminder in {bot_delay:.2f} seconds.")
            asyncio.create_task(self.schedule_reminder(message.channel, bot_delay, role_id, bot_name))

        except Exception as e:
            logger.error(f"[{message.guild.id}] Error handling bump success: {e}", exc_info=True)

    async def get_timers(self, config):
        active_timers = []
        expired_timers = []
        enabled_bots = config.enabled_bots or list(BUMP_BOTS.keys())
        now = time.time()

        for bot_name in enabled_bots:
            delay = config.bot_delay.get(bot_name, BUMP_BOTS.get(bot_name, 7200))
            timestamp = config.timestamps.get(f"{bot_name}_timestamp", 0)
            if timestamp:
                remaining = delay - (now - timestamp)
                if remaining > 0:
                    active_timers.append((bot_name, int(timestamp + delay)))
                else:
                    expired_timers.append(bot_name)

        return active_timers, expired_timers

    async def schedule_reminder(self, channel, remaining_time, role_id, bot_name):
        try:
            logger.info(f"[{channel.guild.id}] Scheduling {bot_name} reminder in {remaining_time:.2f}s")

            await self.bot.timer_handler.run_timer(
                channel_id=channel.id,
                guild_id=channel.guild.id,
                name=bot_name,
                delay=float(remaining_time),
                callback=self._send_bump_reminder,
                timer_type="bump",
                args=(channel.id, channel.guild.id, role_id, bot_name),
                jitter=3.0,
                max_retries=2,
                backoff=5.0,
                callback_timeout=10.0,
                replace_if_sooner_than=2.0
            )
        except Exception as e:
            logger.error(f"Error scheduling bump reminder for {bot_name}: {e}")

    async def _send_bump_reminder(self, channel_id: int, guild_id: int, role_id: int, bot_name: str):
        try:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        channel = await guild.fetch_channel(channel_id)
                except Exception:
                    channel = None

            if channel is None:
                logger.warning(f"[{guild_id}] Channel {channel_id} not found for reminder {bot_name}")
                return

            await self.queue_reminder(channel, role_id, bot_name)
        except Exception as e:
            logger.error(f"[{guild_id}] Failed sending reminder for {bot_name} in {channel_id}: {e}")

    async def queue_reminder(self, channel, role_id, bot_name):
        channel_id = channel.id
        existing_reminders = self.channel_queues[channel_id]
        self.channel_queues[channel_id] = [(r, b) for r, b in existing_reminders if b != bot_name]
        self.channel_queues[channel_id].append((role_id, bot_name))

        if channel_id not in self.channel_tasks:
            self.channel_tasks[channel_id] = asyncio.create_task(self._delayed_send(channel))

    async def _delayed_send(self, channel):
        await asyncio.sleep(10)  # Batch delay window

        reminders = self.channel_queues.pop(channel.id, [])
        self.channel_tasks.pop(channel.id, None)

        if reminders:
            config = await self.bot.guild_config_manager.get_config(channel.guild.id)
            premium_enabled = config.premium.get("enabled", False)
            webhook_url = config.premium.get("guild_webhook")

            bots = ", ".join(f"**{bot_name}**" for _, bot_name in reminders)
            role_mentions = set(role_id for role_id, _ in reminders if role_id)
            role_mentions_text = " ".join(f"<@&{r}>" for r in role_mentions)

            custom_message = config.custom_message
            if custom_message and premium_enabled:
                message = custom_message.replace("{bump_role}", role_mentions_text).replace("{bots}", bots)
            else:
                message = f"{role_mentions_text} It's time to bump again for: {bots}!"

            # Only the configured bump role(s) may ever ping - never @everyone,
            # never users, never other roles a custom_message might smuggle in.
            mentions = discord.AllowedMentions(
                everyone=False,
                users=False,
                roles=[discord.Object(id=r) for r in role_mentions],
            )

            try:
                if premium_enabled and webhook_url:
                    try:
                        async with aiohttp.ClientSession() as session:
                            webhook = discord.Webhook.from_url(webhook_url, session=session)
                            await webhook.send(content=message, allowed_mentions=mentions)
                        logger.info(
                            f"Sent batched bump reminder via webhook for {channel.guild.id} in {channel.id}: {bots}")
                    except Exception as webhook_error:
                        logger.error(f"Failed to send via webhook for guild {channel.guild.id}: {webhook_error}")
                        await channel.send(message, allowed_mentions=mentions)
                else:
                    await channel.send(message, allowed_mentions=mentions)
                    logger.info(f"Sent batched bump reminder for {channel.guild.id} in {channel.id}: {bots}")
            except Exception as e:
                logger.error(f"Failed to send bump reminder for guild {channel.guild.id}: {e}")

    # Text extraction methods (kept from original but modernized)
    def normalize_text(self, s: str) -> str:
        if not s: return ""
        s = _ZWSP_RE.sub("", s)
        s = s.lower()
        return " ".join(s.split())

    def get_embed_text(self, message: discord.Message) -> str:
        if not getattr(message, "embeds", None): return ""
        parts = []
        for embed in message.embeds:
            if embed.title: parts.append(str(embed.title))
            if embed.description: parts.append(str(embed.description))
            for field in embed.fields:
                if field.name: parts.append(str(field.name))
                if field.value: parts.append(str(field.value))
            if embed.footer and embed.footer.text: parts.append(str(embed.footer.text))
            if embed.author and embed.author.name: parts.append(str(embed.author.name))
        return "\n".join(p for p in parts if p)

    def get_component_text(self, message: discord.Message) -> str:
        parts = []
        for row in getattr(message, "components", []):
            for child in getattr(row, "children", []):
                if hasattr(child, "label") and child.label:
                    parts.append(str(child.label))
                if hasattr(child, "options"):
                    for opt in child.options:
                        if opt.label: parts.append(str(opt.label))
                        if opt.description: parts.append(str(opt.description))
        return "\n".join(p for p in parts if p)

    def _extract_misc_from_message(self, message: discord.Message) -> str:
        parts = []
        for att in getattr(message, "attachments", []):
            if att.description: parts.append(str(att.description))
            if att.filename: parts.append(str(att.filename))
        for st in getattr(message, "stickers", []):
            if st.name: parts.append(str(st.name))
            if st.tags: parts.append(str(st.tags))
        return "\n".join(p for p in parts if p)

    async def extract_all_text(self, message: discord.Message, *, allow_refetch: bool) -> str:
        embed_text = self.get_embed_text(message)
        content_text = message.content or ""
        component_text = self.get_component_text(message)
        misc_text = self._extract_misc_from_message(message)

        combined = "\n".join(x for x in [embed_text, content_text, component_text, misc_text] if x).strip()
        normalized = self.normalize_text(combined)

        if normalized or not allow_refetch:
            return normalized

        try:
            fresh = await message.channel.fetch_message(message.id)
            embed_text = self.get_embed_text(fresh)
            content_text = fresh.content or ""
            component_text = self.get_component_text(fresh)
            misc_text = self._extract_misc_from_message(fresh)
            combined = "\n".join(x for x in [embed_text, content_text, component_text, misc_text] if x).strip()
            return self.normalize_text(combined)
        except Exception:
            return normalized

async def setup(bot):
    logger.info("Setting up BumpHandler Cog...")
    await bot.add_cog(BumpHandler(bot))