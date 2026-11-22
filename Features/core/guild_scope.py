"""Resolve a server's stored channel and role ids through THAT server only.

Security review 2026-11-21 (item 5). The bump channel, timers channel and bump role
are stored per server, but the bot used to resolve the channel with the global
``bot.get_channel``, which finds a channel in ANY server the bot is in. A channel id
belonging to another server (saved before the dashboard refused foreign channels, or
by any other writer) would then have this server's reminders and countdown posted
into that other server. Every lookup here goes through the setting's own guild and
refuses an object that is not in it.

A plain module, not a cog: it has no ``setup()``, so the loader leaves it alone.
"""
from __future__ import annotations

from typing import Iterable, Optional

import discord

from storage.log import get_logger

logger = get_logger("GuildScope")


def _belongs_to(obj, guild_id: int) -> bool:
    guild = getattr(obj, "guild", None)
    return guild is not None and getattr(guild, "id", None) == guild_id


def _as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def cached_guild_channel(bot, guild_id, channel_id):
    """The channel from the cache of ``guild_id`` only, or None. Never calls Discord."""
    guild_id, channel_id = _as_int(guild_id), _as_int(channel_id)
    if not guild_id or not channel_id:
        return None
    guild = bot.get_guild(guild_id)
    if guild is None:
        return None
    channel = guild.get_channel_or_thread(channel_id)
    if channel is None:
        return None
    if not _belongs_to(channel, guild.id):
        logger.warning(f"[{guild_id}] Refusing channel {channel_id}: it is not in this server")
        return None
    return channel


async def resolve_guild_channel(bot, guild_id, channel_id):
    """The channel of ``guild_id``, from the cache or fetched from that guild, or None.

    ``Guild.fetch_channel`` already refuses a channel of another guild (discord.py
    raises ``InvalidData``); the explicit check below covers both paths.
    """
    guild_id, channel_id = _as_int(guild_id), _as_int(channel_id)
    if not guild_id or not channel_id:
        return None
    guild = bot.get_guild(guild_id)
    if guild is None:
        return None
    channel = guild.get_channel_or_thread(channel_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException,
                discord.InvalidData) as e:
            logger.debug(f"[{guild_id}] Could not fetch channel {channel_id}: {e}")
            return None
    if not _belongs_to(channel, guild.id):
        logger.warning(f"[{guild_id}] Refusing channel {channel_id}: it is not in this server")
        return None
    return channel


def guild_role_ids(guild, role_ids: Iterable) -> list[int]:
    """The ids in ``role_ids`` that are roles of ``guild``, in their given order.

    A role id from another server is dropped, so a reminder never carries a mention
    (or an allowed-mention entry) for a role this server does not have.
    """
    out: list[int] = []
    for raw in role_ids:
        rid = _as_int(raw)
        if not rid or rid in out:
            continue
        role: Optional[discord.Role] = guild.get_role(rid)
        if role is None:
            logger.warning(f"[{guild.id}] Leaving out role {rid}: it is not in this server")
            continue
        out.append(rid)
    return out
