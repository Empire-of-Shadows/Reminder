"""Dashboard stats aggregation.

Pulls everything from the per-guild bump config in the ``settings_guild_data``
collection — the dashboard runs as a separate process from the bot, so there is
no live TimerHandler access. The next-due time for each bump bot is computed as
``last_bump + cooldown``, which is the useful signal for a bump reminder bot.

Mirrors TheHost's ``services/user_stats.py`` (IR has no per-user data, so the
unit of aggregation is the guild rather than the user).
"""

import time
from datetime import datetime, timezone

from storage.config_manager import GuildConfig
from storage.settings.collections import db_manager
from storage.sub_systems.bump_config import BOT_DISPLAY_NAMES, BUMP_BOTS

_CONFIG_COLLECTION = "settings_guild_data"
_PREMIUM_STATE_COLLECTION = "premium_state"


async def guild_is_premium(guild_id) -> bool:
    """Read the engine's derived premium_state doc for a guild.

    The dashboard runs without the bot's PremiumManager, so it reads the derived
    state directly and applies the lazy-expiry rule itself (a stored
    ``is_premium: true`` past its ``expires_at`` counts as lapsed).
    """
    coll = db_manager.get_collection_manager(_PREMIUM_STATE_COLLECTION)
    doc = await coll.find_one({"_id": f"guild:{guild_id}"})
    if not doc or not doc.get("is_premium"):
        return False
    expires = doc.get("expires_at")
    if isinstance(expires, datetime):
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            return False
    return True


async def public_stats() -> dict:
    """Ecosystem-wide counts for the public hero (no auth)."""
    coll = db_manager.get_collection_manager(_CONFIG_COLLECTION)

    servers = await coll.count_documents({})
    # Engine premium: derived state docs (may slightly overcount if a lapsed
    # state has not been recomputed yet - fine for a public counter).
    premium_servers = await db_manager.get_collection_manager(
        _PREMIUM_STATE_COLLECTION
    ).count_documents({"scope": "guild", "is_premium": True})

    # Sum of enabled bots across every guild = total bump bots being tracked.
    docs = await coll.find_many({}, projection={"enabled_bots": 1})
    bots_tracked = sum(len(doc.get("enabled_bots") or []) for doc in docs)

    return {
        "servers": int(servers),
        "bots_tracked": int(bots_tracked),
        "premium_servers": int(premium_servers),
    }


def guild_bump_stats(config: GuildConfig, premium: bool = False) -> dict:
    """Per-bot bump status for one guild, computed from an already-fetched config.

    Pure function (no I/O) so the router controls the DB fetch; ``premium`` comes
    from ``guild_is_premium`` (engine entitlement state), not the retired
    ``premium.enabled`` config flag.
    """
    now = int(time.time())

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
