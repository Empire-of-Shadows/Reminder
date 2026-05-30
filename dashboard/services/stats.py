"""Dashboard stats aggregation.

Pulls everything from the per-guild bump config in the ``settings_guild_data``
collection — the dashboard runs as a separate process from the bot, so there is
no live TimerHandler access. The next-due time for each bump bot is computed as
``last_bump + cooldown``, which is the useful signal for a bump reminder bot.

Mirrors TheHost's ``services/user_stats.py`` (IR has no per-user data, so the
unit of aggregation is the guild rather than the user).
"""

import time

from storage.config_manager import GuildConfig
from storage.database_manager import db_manager
from storage.sub_systems.bump_config import BOT_DISPLAY_NAMES, BUMP_BOTS

_CONFIG_COLLECTION = "settings_guild_data"


async def public_stats() -> dict:
    """Ecosystem-wide counts for the public hero (no auth)."""
    coll = db_manager.get_collection_manager(_CONFIG_COLLECTION)

    servers = await coll.count_documents({})
    premium_servers = await coll.count_documents({"premium.enabled": True})

    # Sum of enabled bots across every guild = total bump bots being tracked.
    docs = await coll.find_many({}, projection={"enabled_bots": 1})
    bots_tracked = sum(len(doc.get("enabled_bots") or []) for doc in docs)

    return {
        "servers": int(servers),
        "bots_tracked": int(bots_tracked),
        "premium_servers": int(premium_servers),
    }


def guild_bump_stats(config: GuildConfig) -> dict:
    """Per-bot bump status for one guild, computed from an already-fetched config.

    Pure function (no I/O) so the router controls the DB fetch.
    """
    now = int(time.time())
    premium = bool(config.premium.get("enabled")) if config.premium else False

    bots: list[dict] = []
    for key in config.enabled_bots:
        if key not in BUMP_BOTS:
            continue
        raw_ts = config.timestamps.get(f"{key}_timestamp") or 0
        last_bump = int(raw_ts) if raw_ts else None
        cooldown = int(config.bot_delay.get(key, BUMP_BOTS[key]))
        next_due = last_bump + cooldown if last_bump else None
        status = "ready" if next_due is None or now >= next_due else "waiting"
        bots.append({
            "key": key,
            "name": BOT_DISPLAY_NAMES.get(key, key.title()),
            "last_bump": last_bump,
            "cooldown": cooldown,
            "next_due": next_due,
            "status": status,
        })

    config_complete = bool(config.bump_channel) and bool(config.bump_role)

    return {
        "guild_id": str(config.guild_id),
        "premium": premium,
        "config_complete": config_complete,
        "enabled_count": len(bots),
        "server_time": now,
        "bots": bots,
    }
