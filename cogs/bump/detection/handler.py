# Python
import asyncio
import json
import re
from collections import defaultdict

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from cogs.bump.display.embed_manager import TimerEmbedManager
from cogs.bump.storage.database import bump_storage
from cogs.bump.storage.config import (
    DISBOARD_ID, DISBOARD_KEYWORD, TWO, Bump4You, BUMP4YOU_ID, BUMPIT_ID,
    BUMPIT_SUCCESS_KEYWORD, ONE, BUMP_BOTS, WEBUMP_ID, WEBUMP_SUCCESS,
    SUCCESS_KEYWORDS, BUMP_BOTS_INFO
)
from utils.main_config import utc_now
from utils.logger import get_logger

logger = get_logger("BumpHandler")

# Keep normalization simple and safe for Unicode
_ZWSP_RE = re.compile(r"[\u200B-\u200D\uFEFF]")

class BumpHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_queues = defaultdict(list)
        self.channel_tasks = {}
        self.embed_manager = TimerEmbedManager(bot)
        self._seen_raw = set()
        # Track processed bumps: (guild_id, bot_name) -> timestamp
        self._processed_bumps = {}
        self._bump_cooldown = 5.0  # seconds to ignore duplicate bump detections

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
        Returns True if this bump should be skipped (already processed recently).
        """
        import time as time_module

        key = (guild_id, bot_name)
        current_time = time_module.time()

        # Clean up old entries (older than 60 seconds)
        old_keys = [k for k, v in self._processed_bumps.items() if current_time - v > 60]
        for old_key in old_keys:
            self._processed_bumps.pop(old_key, None)

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

        config = await bump_storage.get_guild(message.guild.id)
        if not config or message.channel.id != config.get("bump_channel"):
            return

        enabled_bots = config.get("enabled_bots", [])

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

        config = await guild_storage.get_guild(after.guild.id)
        if not config or after.channel.id != config.get("bump_channel"):
            return

        enabled_bots = config.get("enabled_bots", [])

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

        # Log raw payloads for debugging
        logger.debug(f"Raw embeds: {after.embeds}")
        try:
            logger.debug(f"Embed JSON: {[e.to_dict() for e in after.embeds]}")
        except Exception as e:
            logger.warning(f"Error converting embeds to dict: {e}")

        before_text = await self.extract_all_text(before, allow_refetch=False)
        after_text = await self.extract_all_text(after, allow_refetch=False)  # no second refetch needed here

        logger.info(
            f"[on_message_edit] Guild={after.guild.id} Channel={after.channel.id} Author={after.author.id} "
            f"WebhookID={getattr(after, 'webhook_id', None)} Before='{before_text}' After='{after_text}'"
        )

        if bot_info:
            bot_name, delay = bot_info
            if bot_name in enabled_bots and any(keyword in after_text for keyword in SUCCESS_KEYWORDS):
                # Check for duplicate detection
                if self._is_bump_recently_processed(after.guild.id, bot_name):
                    return
                await self.handle_bump_success(after, bot_name, delay)


    def _extract_text_from_embed_dicts(self, embeds: list) -> str:
        parts = []
        try:
            for e in embeds or []:
                title = e.get("title")
                desc = e.get("description")
                if title:
                    parts.append(str(title))
                if desc:
                    parts.append(str(desc))

                # Fields
                for f in e.get("fields") or []:
                    if f.get("name"):
                        parts.append(str(f["name"]))
                    if f.get("value"):
                        parts.append(str(f["value"]))

                # Footer / Author
                footer = e.get("footer") or {}
                if footer.get("text"):
                    parts.append(str(footer["text"]))

                author = e.get("author") or {}
                if author.get("name"):
                    parts.append(str(author["name"]))
        except Exception as ex:
            logger.debug(f"_extract_text_from_embed_dicts error: {ex}")
        return "\n".join(p for p in parts if p)

    def _extract_text_from_component_dicts(self, components: list) -> str:
        parts = []

        # Debug logging to see raw component structure
        try:
            logger.debug(f"[_extract_text_from_component_dicts] Components: {components}")
            logger.debug(f"[_extract_text_from_component_dicts] Components count: {len(components or [])}")
        except Exception as e:
            logger.debug(f"[_extract_text_from_component_dicts] Error in debug logging: {e}")

        try:
            for row_idx, row in enumerate(components or []):
                logger.debug(f"[_extract_text_from_component_dicts] Row {row_idx}: {row}")
                row_components = row.get("components") or []
                logger.debug(f"[_extract_text_from_component_dicts] Row {row_idx} has {len(row_components)} components")

                for child_idx, child in enumerate(row_components):
                    logger.debug(f"[_extract_text_from_component_dicts] Row {row_idx} Child {child_idx}: {child}")

                    # Components v2: Type 10 text content with 'content' field
                    content = child.get("content")
                    if content:
                        logger.debug(f"[_extract_text_from_component_dicts] Found content: {content}")
                        parts.append(str(content))

                    # Recursively check for nested components (type 9 containers)
                    nested_components = child.get("components")
                    if nested_components:
                        logger.debug(f"[_extract_text_from_component_dicts] Found nested components: {len(nested_components)}")
                        for nested_idx, nested in enumerate(nested_components):
                            logger.debug(f"[_extract_text_from_component_dicts] Nested {nested_idx}: {nested}")
                            nested_content = nested.get("content")
                            if nested_content:
                                logger.debug(f"[_extract_text_from_component_dicts] Found nested content: {nested_content}")
                                parts.append(str(nested_content))

                    # Button type=2 (traditional)
                    label = child.get("label")
                    if label:
                        logger.debug(f"[_extract_text_from_component_dicts] Found label: {label}")
                        parts.append(str(label))

                    # Select menus type=3: options
                    for opt in child.get("options") or []:
                        if opt.get("label"):
                            logger.debug(f"[_extract_text_from_component_dicts] Found option label: {opt['label']}")
                            parts.append(str(opt["label"]))
                        if opt.get("description"):
                            logger.debug(f"[_extract_text_from_component_dicts] Found option desc: {opt['description']}")
                            parts.append(str(opt["description"]))

                    # Placeholder might carry text on selects
                    placeholder = child.get("placeholder")
                    if placeholder:
                        logger.debug(f"[_extract_text_from_component_dicts] Found placeholder: {placeholder}")
                        parts.append(str(placeholder))
        except Exception as ex:
            logger.debug(f"_extract_text_from_component_dicts error: {ex}", exc_info=True)

        result = "\n".join(p for p in parts if p)
        logger.debug(f"[_extract_text_from_component_dicts] Final extracted: '{result}'")
        return result

    def _normalize_raw_text(self, content: str, embeds: list, components: list) -> str:
        embed_text = self._extract_text_from_embed_dicts(embeds)
        comp_text = self._extract_text_from_component_dicts(components)
        combined = "\n".join(x for x in [content or "", embed_text, comp_text] if x).strip()
        return self.normalize_text(combined)

    # Python
    def _extract_misc_from_message(self, message: discord.Message) -> str:
        """
        Fallback textual hints from attachments, stickers, and referenced messages.
        """
        parts = []

        # Attachments: filenames and descriptions (if any)
        try:
            for att in getattr(message, "attachments", []) or []:
                if getattr(att, "description", None):
                    parts.append(str(att.description))
                if getattr(att, "filename", None):
                    parts.append(str(att.filename))
        except Exception as e:
            logger.debug(f"_extract_misc_from_message attachments error: {e}")

        # Stickers: names and tags
        try:
            for st in getattr(message, "stickers", []) or []:
                if getattr(st, "name", None):
                    parts.append(str(st.name))
                if getattr(st, "tags", None):
                    parts.append(str(st.tags))
        except Exception as e:
            logger.debug(f"_extract_misc_from_message stickers error: {e}")

        # Referenced message (replies)
        try:
            ref = getattr(message, "reference", None)
            if ref and getattr(ref, "resolved", None):
                rm = ref.resolved
                # Pull content/embeds/components from the referenced message
                parts.append(getattr(rm, "content", "") or "")
                parts.append(self.get_embed_text(rm) or "")
                parts.append(self.get_component_text(rm) or "")
                # And again, misc from referenced
                try:
                    for att in getattr(rm, "attachments", []) or []:
                        if getattr(att, "description", None):
                            parts.append(str(att.description))
                        if getattr(att, "filename", None):
                            parts.append(str(att.filename))
                except Exception:
                    pass
                try:
                    for st in getattr(rm, "stickers", []) or []:
                        if getattr(st, "name", None):
                            parts.append(str(st.name))
                        if getattr(st, "tags", None):
                            parts.append(str(st.tags))
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"_extract_misc_from_message referenced error: {e}")

        combined = "\n".join(p for p in parts if p).strip()
        return combined

    async def _history_fetch_fallback(self, message: discord.Message) -> str:
        """
        Try channel.history around the target message; sometimes objects are hydrated differently.
        """
        try:
            channel = message.channel
            # Try to get a window around the message
            async for m in channel.history(limit=10, around=message.created_at):
                if m.id == message.id:
                    embed_text = self.get_embed_text(m)
                    content_text = m.content or ""
                    component_text = self.get_component_text(m)
                    misc_text = self._extract_misc_from_message(m)
                    combined = "\n".join(
                        x for x in [embed_text, content_text, component_text, misc_text] if x).strip()
                    normalized = self.normalize_text(combined)
                    if normalized:
                        return normalized
        except Exception as e:
            logger.debug(f"_history_fetch_fallback error: {e}")
        return ""

    async def extract_all_text(self, message: discord.Message, *, allow_refetch: bool) -> str:
        """
        Aggregate normalized text from (embeds + content + components + misc).
        If nothing is found and allow_refetch=True, attempt refetch(es) and history fallback.
        Always logs raw embed data for debugging.
        """
        # Log before parsing
        try:
            # Extra diagnostics
            logger.debug(f"[extract_all_text] Content: {message.content}")
            logger.debug(f"[extract_all_text] Embeds: {message.embeds}")
            logger.debug(f"[extract_all_text] Embed JSON: {[e.to_dict() for e in message.embeds]}")
            logger.debug(f"[extract_all_text] Type={getattr(message, 'type', None)} "
                         f"Flags={getattr(getattr(message, 'flags', None), 'value', None)} "
                         f"WebhookID={getattr(message, 'webhook_id', None)} "
                         f"Attachments={len(getattr(message, 'attachments', []) or [])} "
                         f"Stickers={len(getattr(message, 'stickers', []) or [])} "
                         f"HasReference={bool(getattr(message, 'reference', None))}")
        except Exception as e:
            logger.warning(f"Error logging raw message data: {e}")

        embed_text = self.get_embed_text(message)
        content_text = message.content or ""
        component_text = self.get_component_text(message)
        misc_text = self._extract_misc_from_message(message)

        combined = "\n".join(x for x in [embed_text, content_text, component_text, misc_text] if x).strip()
        normalized = self.normalize_text(combined)

        if normalized or not allow_refetch:
            return normalized

        # First refetch
        try:
            fresh = await message.channel.fetch_message(message.id)
            logger.debug(f"[extract_all_text] Refetched message {message.id}")
            logger.debug(f"[extract_all_text] Refetched embeds: {fresh.embeds}")
            logger.debug(f"[extract_all_text] Refetched JSON: {[e.to_dict() for e in fresh.embeds]}")
            logger.debug(f"[extract_all_text] Refetched Type={getattr(fresh, 'type', None)} "
                         f"Flags={getattr(getattr(fresh, 'flags', None), 'value', None)} "
                         f"WebhookID={getattr(fresh, 'webhook_id', None)} "
                         f"Attachments={len(getattr(fresh, 'attachments', []) or [])} "
                         f"Stickers={len(getattr(fresh, 'stickers', []) or [])} "
                         f"HasReference={bool(getattr(fresh, 'reference', None))}")

            embed_text = self.get_embed_text(fresh)
            content_text = fresh.content or ""
            component_text = self.get_component_text(fresh)
            misc_text = self._extract_misc_from_message(fresh)
            combined = "\n".join(x for x in [embed_text, content_text, component_text, misc_text] if x).strip()
            normalized = self.normalize_text(combined)
            if normalized:
                return normalized
        except Exception as e:
            logger.debug(f"[extract_all_text] First refetch failed for {message.id} in {message.channel.id}: {e}")

        # Small bounded retries for bots that update embeds asynchronously
        for attempt, delay in enumerate((0.3, 0.6, 0.9), start=1):
            try:
                await asyncio.sleep(delay)
                fresh = await message.channel.fetch_message(message.id)
                logger.debug(f"[extract_all_text] Retry {attempt}: fetched message {message.id}")

                embed_text = self.get_embed_text(fresh)
                content_text = fresh.content or ""
                component_text = self.get_component_text(fresh)
                misc_text = self._extract_misc_from_message(fresh)
                combined = "\n".join(x for x in [embed_text, content_text, component_text, misc_text] if x).strip()
                normalized = self.normalize_text(combined)
                if normalized:
                    return normalized
            except Exception as e:
                logger.debug(f"[extract_all_text] Retry {attempt} failed for {message.id}: {e}")

        # History fallback
        hist = await self._history_fetch_fallback(message)
        if hist:
            return hist

        return normalized

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        """
        Use gateway payload first (no cache dependence). If still empty, fetch the message.
        Also log keys, type, flags, and minimal counts for debugging.
        """
        try:
            guild_id = payload.guild_id
            channel_id = payload.channel_id
            if not guild_id or not channel_id:
                return

            config = await bump_storage.get_guild(guild_id)
            if not config or channel_id != config.get("bump_channel"):
                return

            data = payload.data or {}
            # Diagnostics
            try:
                flags_val = (data.get("flags") if isinstance(data.get("flags"), int) else None)
                logger.debug(
                    f"[on_raw_message_edit] keys={list(data.keys())} type={data.get('type')} "
                    f"flags={flags_val} embeds={len(data.get('embeds') or [])} "
                    f"components={len(data.get('components') or [])} "
                    f"attachments={len(data.get('attachments') or [])} "
                    f"stickers={len(data.get('sticker_items') or [])} "
                    f"webhook_id={data.get('webhook_id')} has_ref={bool(data.get('message_reference'))}"
                )
                # Log raw components data
                if data.get('components'):
                    logger.debug(f"[on_raw_message_edit] RAW COMPONENTS: {data.get('components')}")
            except Exception:
                pass

            raw_text = self._normalize_raw_text(
                data.get("content") or "",
                data.get("embeds") or [],
                data.get("components") or [],
            )

            # Try to augment with referenced message content from payload
            try:
                ref = data.get("referenced_message")
                if not ref:
                    # Some payloads keep it under message_reference or omit it on edits
                    ref = data.get("message_reference", {}).get("resolved")
                if isinstance(ref, dict):
                    ref_text = self._normalize_raw_text(
                        ref.get("content") or "",
                        ref.get("embeds") or [],
                        ref.get("components") or [],
                    )
                    if ref_text:
                        raw_text = (raw_text + "\n" + ref_text).strip() if raw_text else ref_text
            except Exception:
                pass

            author_id = None
            if "author" in data and isinstance(data["author"], dict):
                author_id = data["author"].get("id")

            # Resolve via author/webhook/application for raw payloads
            try:
                aid = int(author_id) if author_id and str(author_id).isdigit() else None
            except Exception:
                aid = None
            try:
                wid = int(data.get("webhook_id")) if data.get("webhook_id") else None
            except Exception:
                wid = None
            try:
                appid = int(data.get("application_id")) if data.get("application_id") else None
            except Exception:
                appid = None

            bot_info = self._resolve_bot_info(author_id=aid, webhook_id=wid, application_id=appid)

            logger.info(
                f"[on_raw_message_edit] Guild={guild_id} Channel={channel_id} "
                f"Author={author_id} WebhookID={wid} AppID={appid} RawText='{raw_text}'"
            )

            text_for_detection = raw_text
            message = None

            if not text_for_detection or bot_info is not None:
                try:
                    channel = self.bot.get_channel(channel_id)
                    if channel is None:
                        guild = self.bot.get_guild(guild_id)
                        if guild:
                            channel = await guild.fetch_channel(channel_id)
                    if channel:
                        message = await channel.fetch_message(payload.message_id)
                        fetched_text = await self.extract_all_text(message, allow_refetch=True)
                        if fetched_text:
                            text_for_detection = fetched_text
                except Exception as e:
                    logger.debug(f"[on_raw_message_edit] Fetch/history fallback failed: {e}")

            enabled_bots = config.get("enabled_bots", [])
            if bot_info and text_for_detection:
                bot_name, delay = bot_info
                if bot_name in enabled_bots and any(kw in text_for_detection for kw in SUCCESS_KEYWORDS):
                    # Check for duplicate detection
                    if self._is_bump_recently_processed(guild_id, bot_name):
                        return
                    if message is None:
                        try:
                            channel = self.bot.get_channel(channel_id)
                            if channel:
                                message = await channel.fetch_message(payload.message_id)
                        except Exception:
                            message = None
                    if message:
                        await self.handle_bump_success(message, bot_name, delay)
        except Exception as e:
            logger.warning(f"[on_raw_message_edit] Error handling raw edit: {e}")

    @commands.Cog.listener()
    async def on_socket_raw_receive(self, msg: str):
        """
        Last-resort: parse raw gateway JSON for MESSAGE_CREATE/UPDATE and extract text directly.
        """
        import json as _json  # local alias to be safe
        try:
            data = _json.loads(msg)
        except Exception:
            return

        try:
            t = data.get("t")
            if t not in ("MESSAGE_CREATE", "MESSAGE_UPDATE"):
                return

            d = data.get("d") or {}
            guild_id = d.get("guild_id")
            channel_id = d.get("channel_id")
            if not guild_id or not channel_id:
                return

            config = await guild_storage.get_guild(int(guild_id))
            if not config or int(channel_id) != config.get("bump_channel"):
                return

            # Diagnostics
            try:
                logger.debug(
                    f"[on_socket_raw_receive:{t}] keys={list(d.keys())} "
                    f"type={d.get('type')} flags={d.get('flags')} "
                    f"embeds={len(d.get('embeds') or [])} components={len(d.get('components') or [])} "
                    f"attachments={len(d.get('attachments') or [])} stickers={len(d.get('sticker_items') or [])} "
                    f"webhook_id={d.get('webhook_id')} has_ref={bool(d.get('message_reference'))}"
                )
                # Log raw components data
                if d.get('components'):
                    logger.debug(f"[on_socket_raw_receive:{t}] RAW COMPONENTS: {d.get('components')}")
            except Exception:
                pass

            raw_text = self._normalize_raw_text(
                d.get("content") or "",
                d.get("embeds") or [],
                d.get("components") or [],
            )

            # Try referenced message from raw gateway
            try:
                ref = d.get("referenced_message")
                if not ref:
                    ref = d.get("message_reference", {}).get("resolved")
                if isinstance(ref, dict):
                    ref_text = self._normalize_raw_text(
                        ref.get("content") or "",
                        ref.get("embeds") or [],
                        ref.get("components") or [],
                    )
                    if ref_text:
                        raw_text = (raw_text + "\n" + ref_text).strip() if raw_text else ref_text
            except Exception:
                pass

            author_id = (d.get("author") or {}).get("id")

            logger.info(
                f"[on_socket_raw_receive:{t}] Guild={guild_id} Channel={channel_id} "
                f"Author={author_id} RawText='{raw_text}'"
            )
        except Exception as e:
            logger.debug(f"[on_socket_raw_receive] Parse error: {e}")

    def normalize_text(self, s: str) -> str:
        """
        Lowercase, strip zero-width chars, collapse whitespace.
        Preserve general Unicode letters/numbers and punctuation to avoid losing info.
        """
        if not s:
            return ""
        s = _ZWSP_RE.sub("", s)
        s = s.lower()
        return " ".join(s.split())

    def get_embed_text(self, message: discord.Message) -> str:
        """
        Gather textual content from embeds: title, description, fields (name/value),
        footer text, author name.
        """
        if not getattr(message, "embeds", None):
            return ""

        parts = []
        try:
            for embed in message.embeds:
                title = getattr(embed, "title", None)
                desc = getattr(embed, "description", None)

                if title:
                    parts.append(str(title))
                if desc:
                    parts.append(str(desc))

                # Fields
                fields = getattr(embed, "fields", None) or []
                for field in fields:
                    fname = getattr(field, "name", None)
                    fval = getattr(field, "value", None)
                    if fname:
                        parts.append(str(fname))
                    if fval:
                        parts.append(str(fval))

                # Footer and Author
                footer = getattr(embed, "footer", None)
                if footer and getattr(footer, "text", None):
                    parts.append(str(footer.text))

                author = getattr(embed, "author", None)
                if author and getattr(author, "name", None):
                    parts.append(str(author.name))
        except Exception as e:
            logger.warning(f"Error extracting embed text: {e}", exc_info=True)

        return "\n".join(p for p in parts if p)

    def get_component_text(self, message: discord.Message) -> str:
        """
        Extract textual labels from message components (buttons, select menus).
        This captures visible text when bots render content via components.
        """
        parts = []
        comps = getattr(message, "components", None) or []

        # Debug logging to see component structure
        try:
            logger.debug(f"[get_component_text] Components count: {len(comps)}")
            logger.debug(f"[get_component_text] Components type: {type(comps)}")
            for idx, row in enumerate(comps):
                logger.debug(f"[get_component_text] Row {idx} type: {type(row)}")
                logger.debug(f"[get_component_text] Row {idx} repr: {repr(row)}")
                # Try to convert to dict to see structure
                try:
                    if hasattr(row, 'to_dict'):
                        logger.debug(f"[get_component_text] Row {idx} dict: {row.to_dict()}")
                    elif isinstance(row, dict):
                        logger.debug(f"[get_component_text] Row {idx} is already dict: {row}")
                except Exception as e:
                    logger.debug(f"[get_component_text] Error converting row {idx} to dict: {e}")
        except Exception as e:
            logger.debug(f"[get_component_text] Error in debug logging: {e}")

        try:
            for row in comps:
                # ActionRow -> children (buttons/selects)
                children = getattr(row, "children", None) or []
                logger.debug(f"[get_component_text] Children count: {len(children)}")

                for child_idx, child in enumerate(children):
                    logger.debug(f"[get_component_text] Child {child_idx} type: {type(child)}")
                    logger.debug(f"[get_component_text] Child {child_idx} repr: {repr(child)}")

                    # Try to convert child to dict to see structure
                    try:
                        if hasattr(child, 'to_dict'):
                            child_dict = child.to_dict()
                            logger.debug(f"[get_component_text] Child {child_idx} dict: {child_dict}")
                    except Exception as e:
                        logger.debug(f"[get_component_text] Error converting child {child_idx}: {e}")

                    # Buttons
                    label = getattr(child, "label", None)
                    if label:
                        logger.debug(f"[get_component_text] Found button label: {label}")
                        parts.append(str(label))

                    # Select menus with options
                    options = getattr(child, "options", None) or []
                    logger.debug(f"[get_component_text] Options count: {len(options)}")
                    for opt in options:
                        olabel = getattr(opt, "label", None)
                        if olabel:
                            logger.debug(f"[get_component_text] Found option label: {olabel}")
                            parts.append(str(olabel))
                        odesc = getattr(opt, "description", None)
                        if odesc:
                            logger.debug(f"[get_component_text] Found option desc: {odesc}")
                            parts.append(str(odesc))
        except Exception as e:
            logger.warning(f"Error extracting component text: {e}", exc_info=True)

        result = "\n".join(p for p in parts if p)
        logger.debug(f"[get_component_text] Final extracted text: '{result}'")
        return result

    # async def extract_all_text(self, message: discord.Message, *, allow_refetch: bool) -> str:
    #     """
    #     Aggregate normalized text from (embeds + content + components).
    #     If nothing is found and allow_refetch=True, attempt a one-time refetch to get fully-populated payloads.
    #     Always logs raw embed data for debugging.
    #     """
    #     # Log before parsing
    #     try:
    #         logger.debug(f"[extract_all_text] Content: {message.content}")
    #         logger.debug(f"[extract_all_text] Embeds: {message.embeds}")
    #         logger.debug(f"[extract_all_text] Embed JSON: {[e.to_dict() for e in message.embeds]}")
    #     except Exception as e:
    #         logger.warning(f"Error logging raw message data: {e}")
    #
    #     embed_text = self.get_embed_text(message)
    #     content_text = message.content or ""
    #     component_text = self.get_component_text(message)
    #
    #     combined = "\n".join(x for x in [embed_text, content_text, component_text] if x).strip()
    #     normalized = self.normalize_text(combined)
    #
    #     if normalized or not allow_refetch:
    #         return normalized
    #
    #     # Refetch once: sometimes edited payloads are available only after refetch
    #     try:
    #         fresh = await message.channel.fetch_message(message.id)
    #         logger.debug(f"[extract_all_text] Refetched message {message.id}")
    #         logger.debug(f"[extract_all_text] Refetched embeds: {fresh.embeds}")
    #         logger.debug(f"[extract_all_text] Refetched JSON: {[e.to_dict() for e in fresh.embeds]}")
    #
    #         embed_text = self.get_embed_text(fresh)
    #         content_text = fresh.content or ""
    #         component_text = self.get_component_text(fresh)
    #         combined = "\n".join(x for x in [embed_text, content_text, component_text] if x).strip()
    #         return self.normalize_text(combined)
    #     except Exception as e:
    #         logger.debug(f"Refetch failed for message {message.id} in {message.channel.id}: {e}")
    #         return normalized

    async def schedule_reminder(self, channel, remaining_time, role_id, bot_name):
        """
        Minimal changes:
        - Do not pre-cancel; let TimerHandler coalesce if an earlier timer exists.
        - Pass context as args to a shared callback.
        - Add small jitter and safe retries.
        """
        try:
            logger.info(f"Received remaining time for {bot_name}: {remaining_time:.2f} seconds.")
            logger.info(f"Scheduling {bot_name} reminder in channel {channel.id}.")
            logger.info(f"→ Instance {id(self.bot.timer_handler)} scheduling {bot_name} for "
                        f"{remaining_time:.2f}s in {channel.id}")

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
            config = await bump_storage.get_guild(channel.guild.id)
            premium_config = config.get("premium", {})
            enabled = premium_config.get("enabled", False)
            webhook_url = premium_config.get("guild_webhook")

            bots = ", ".join(f"**{bot_name}**" for _, bot_name in reminders)
            role_mentions = set(role_id for role_id, _ in reminders)
            role_mentions_text = " ".join(f"<@&{r}>" for r in role_mentions)

            custom_message = config.get("custom_message", "")
            if custom_message and enabled:
                message = custom_message.replace("{bump_role}", role_mentions_text).replace("{bots}", bots)
            else:
                message = f"{role_mentions_text} It's time to bump again for: {bots}!"

            try:
                if enabled and webhook_url:
                    try:
                        async with aiohttp.ClientSession() as session:
                            webhook = discord.Webhook.from_url(webhook_url, session=session)
                            await webhook.send(content=message)
                        logger.info(
                            f"Sent batched bump reminder via webhook for {channel.guild.id} in {channel.id}: {bots}")
                    except Exception as webhook_error:
                        logger.error(f"Failed to send via webhook for guild {channel.guild.id}: {webhook_error}")
                        await channel.send(message)
                        logger.info(
                            f"Fallback: Sent batched bump reminder for {channel.guild.id} in {channel.id}: {bots}")
                else:
                    await channel.send(message)
                    logger.info(f"Sent batched bump reminder for {channel.guild.id} in {channel.id}: {bots}")
            except Exception as e:
                logger.error(f"Failed to send bump reminder for guild {channel.guild.id}: {e}")

    async def handle_bump_success(self, message, bot_name, delay):
        try:
            bot_name = bot_name.lower()
            logger.info(f"[{message.guild.id}] {bot_name.capitalize()} bump detected.")

            await bump_storage.save_bump_time(message.guild.id, bot_name)
            logger.info(f"[{message.guild.id}] Saved bump timestamp for {bot_name} successfully.")

            config = await bump_storage.get_guild(message.guild.id)
            if not config:
                logger.warning(f"[{message.guild.id}] No configuration found for the guild.")
                return

            bot_delay = config.get("bot_delay", {}).get(bot_name, delay)
            logger.info(f"[{message.guild.id}] Fetched custom delay for {bot_name}: {bot_delay} seconds.")

            active_timers, expired_timers = await self.get_timers(config)

            role_id = config.get("bump_role")
            await self.embed_manager.schedule_embed_update(
                message.guild.id, message.channel.id, role_id, active_timers, expired_timers
            )

            logger.info(f"[{message.guild.id}] Scheduling {bot_name} reminder in {bot_delay:.2f} seconds.")
            asyncio.create_task(self.schedule_reminder(message.channel, bot_delay, role_id, bot_name))

        except Exception as e:
            logger.error(f"[{message.guild.id}] Error handling bump success: {e}")

    async def get_timers(self, config):
        active_timers = []
        expired_timers = []
        enabled_bots = config.get("enabled_bots", list(BUMP_BOTS.keys()))

        for bot_name in enabled_bots:
            delay = config.get("bot_delay", {}).get(bot_name, BUMP_BOTS.get(bot_name, 7200))
            timestamp = config.get("timestamps", {}).get(f"{bot_name}_timestamp", 0)
            if timestamp:
                remaining = delay - (utc_now.timestamp() - timestamp)
                if remaining > 0:
                    active_timers.append((bot_name, int(timestamp + delay)))
                else:
                    expired_timers.append(bot_name)

        return active_timers, expired_timers


async def setup(bot):
    logger.info("Setting up BumpHandler Cog...")
    logger.info(f"Using TimerHandler instance: {hex(id(bot.timer_handler))}")
    await bot.add_cog(BumpHandler(bot))