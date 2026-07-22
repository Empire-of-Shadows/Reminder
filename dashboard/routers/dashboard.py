"""Dashboard API routes — user info, guild listing, channels/roles, public stats.

Adapted to ImperialReminder: access is governed solely by the Discord
MANAGE_GUILD permission (no admin/mod panel-role concept). Discord API results
are cached with short TTLs and single-flight locks to avoid 429s.
"""

import asyncio
import time
from collections import defaultdict

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from dashboard.auth.dependencies import get_current_user
from dashboard.auth.panel_role import require_panel_access, resolve_panel_role
from dashboard.config import BOT_TOKEN, DISCORD_API_BASE, MANAGE_GUILD_PERMISSION
from dashboard.services import stats as stats_service
from storage.config_manager import get_guild_config_manager
from storage.settings.collections import db_manager
from storage.sub_systems.bump_config import BOT_DISPLAY_NAMES, SUPPORTED_BOTS
from storage.log import get_logger

logger = get_logger("dashboard.routers.dashboard")

router = APIRouter(tags=["dashboard"])

_DISCORD_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_CONFIG_COLLECTION = "settings_guild_data"
_ADMIN_PROBE_LIMIT = 25

# Bot invite permissions: View Channels + Send Messages + Embed Links + Mention Everyone.
_INVITE_PERMISSIONS = 0x400 | 0x800 | 0x4000 | 0x20000  # 150528

# TTL caches for Discord API results.
_bot_guilds_cache: dict[str, object] = {"ids": set(), "ts": 0.0}
_bot_id_cache: dict[str, object] = {"id": None, "ts": 0.0}
_CACHE_TTL = 300  # 5 minutes
_RESOURCE_CACHE_TTL = 60

_bot_guilds_lock = asyncio.Lock()
_bot_id_lock = asyncio.Lock()
_channels_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_roles_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_channels_cache: dict[str, dict] = {}
_roles_cache: dict[str, dict] = {}


def _has_manage(guild: dict) -> bool:
    perms = int(guild.get("permissions", 0))
    return (perms & MANAGE_GUILD_PERMISSION) == MANAGE_GUILD_PERMISSION


@router.get("/me")
async def me(session: dict = Depends(get_current_user)):
    """Return the current user's profile plus panel-access flags.

    Mirrors the sibling dashboards: probe configured panel roles across
    bot-present session guilds. admin = MANAGE_GUILD anywhere OR an admin role
    anywhere; mod = a mod role anywhere.
    """
    user = session["user_data"]
    can_manage_any = any(_has_manage(g) for g in session.get("guilds", []))

    bot_guild_ids = await _fetch_bot_guild_ids()
    candidate_ids = [
        g["id"] for g in session.get("guilds", []) if g["id"] in bot_guild_ids
    ][:_ADMIN_PROBE_LIMIT]
    results = await asyncio.gather(
        *(resolve_panel_role(session, gid) for gid in candidate_ids),
        return_exceptions=True,
    )
    roles = [r for r in results if isinstance(r, str)]
    can_access_admin_any = can_manage_any or any(r == "admin" for r in roles)
    can_access_mod_any = any(r == "mod" for r in roles)

    return {
        "id": user["id"],
        "username": user.get("username"),
        "global_name": user.get("global_name"),
        "avatar": user.get("avatar"),
        "discriminator": user.get("discriminator"),
        "can_manage_any": can_manage_any,
        "can_access_admin_any": can_access_admin_any,
        "can_access_mod_any": can_access_mod_any,
        "can_access_settings_any": can_access_admin_any or can_access_mod_any,
    }


async def _fetch_bot_guild_ids() -> set[str]:
    """Fetch the set of guild IDs the bot is currently in (cached, single-flight)."""
    if not BOT_TOKEN:
        return set()

    now = time.monotonic()
    if _bot_guilds_cache["ids"] and now - _bot_guilds_cache["ts"] < _CACHE_TTL:
        return _bot_guilds_cache["ids"]

    async with _bot_guilds_lock:
        now = time.monotonic()
        if _bot_guilds_cache["ids"] and now - _bot_guilds_cache["ts"] < _CACHE_TTL:
            return _bot_guilds_cache["ids"]

        guild_ids: set[str] = set()
        headers = {"Authorization": f"Bot {BOT_TOKEN}"}
        after = "0"

        async with httpx.AsyncClient(timeout=_DISCORD_TIMEOUT) as client:
            while True:
                url = f"{DISCORD_API_BASE}/users/@me/guilds?limit=200&after={after}"
                resp = await client.get(url, headers=headers)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", "2"))
                    logger.info("Bot guilds rate-limited, retrying in %.1fs", retry_after)
                    await asyncio.sleep(retry_after)
                    resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    logger.warning("Failed to fetch bot guilds: %s", resp.status_code)
                    return _bot_guilds_cache["ids"] or guild_ids
                guilds = resp.json()
                if not guilds:
                    break
                for g in guilds:
                    guild_ids.add(g["id"])
                if len(guilds) < 200:
                    break
                after = guilds[-1]["id"]

        _bot_guilds_cache["ids"] = guild_ids
        _bot_guilds_cache["ts"] = now
        return guild_ids


async def _guild_ids_with_config(guild_ids: list[str]) -> set[str]:
    """Return which of the given guild IDs have an existing config doc."""
    if not guild_ids:
        return set()
    try:
        coll = db_manager.get_collection_manager(_CONFIG_COLLECTION)
        docs = await coll.find_many(
            {"_id": {"$in": [str(gid) for gid in guild_ids]}},
            projection={"_id": 1},
        )
        return {str(doc["_id"]) for doc in docs}
    except Exception:
        logger.warning("has_config lookup failed", exc_info=True)
        return set()


@router.get("/guilds")
async def guilds(session: dict = Depends(get_current_user)):
    """Return guilds the user can manage, with bot status and panel-role tier.

    Shows a guild if the user holds MANAGE_GUILD (admin — even when the bot is
    absent, so they can invite it) OR holds a configured admin/mod role in a
    guild the bot is in.
    """
    session_guilds = session.get("guilds", [])
    if not session_guilds:
        return []

    ids = [g["id"] for g in session_guilds]
    bot_guild_ids, configured_ids = await asyncio.gather(
        _fetch_bot_guild_ids(), _guild_ids_with_config(ids)
    )

    probe_targets = [gid for gid in ids if gid in bot_guild_ids]
    role_results = await asyncio.gather(
        *(resolve_panel_role(session, gid) for gid in probe_targets),
        return_exceptions=True,
    )
    panel_roles = {
        gid: (r if isinstance(r, str) else "none")
        for gid, r in zip(probe_targets, role_results)
    }

    out: list[dict] = []
    for guild in session_guilds:
        gid = guild["id"]
        has_manage = _has_manage(guild)
        panel_role = panel_roles.get(gid, "none")
        if not has_manage and panel_role == "none":
            continue
        bot_present = gid in bot_guild_ids
        out.append({
            "id": gid,
            "name": guild["name"],
            "icon": guild.get("icon"),
            "bot_in_guild": bot_present,
            "has_config": gid in configured_ids,
            "setup_required": not bot_present,
            "panel_role": panel_role if panel_role != "none" else ("admin" if has_manage else "none"),
        })
    return out


@router.get("/bot-invite-url")
async def bot_invite_url():
    """Return the ImperialReminder bot invite URL with required permissions."""
    if not BOT_TOKEN:
        return {"url": None}

    now = time.monotonic()
    if _bot_id_cache["id"] and now - _bot_id_cache["ts"] < _CACHE_TTL:
        bot_id = _bot_id_cache["id"]
    else:
        async with _bot_id_lock:
            now = time.monotonic()
            if _bot_id_cache["id"] and now - _bot_id_cache["ts"] < _CACHE_TTL:
                bot_id = _bot_id_cache["id"]
            else:
                async with httpx.AsyncClient(timeout=_DISCORD_TIMEOUT) as client:
                    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
                    resp = await client.get(f"{DISCORD_API_BASE}/users/@me", headers=headers)
                    if resp.status_code == 429:
                        retry_after = float(resp.headers.get("Retry-After", "2"))
                        await asyncio.sleep(retry_after)
                        resp = await client.get(f"{DISCORD_API_BASE}/users/@me", headers=headers)
                    if resp.status_code != 200:
                        logger.warning("Failed to fetch bot user info: %s", resp.status_code)
                        return {"url": None}
                    bot_id = resp.json()["id"]
                    _bot_id_cache["id"] = bot_id
                    _bot_id_cache["ts"] = now

    url = (
        f"https://discord.com/oauth2/authorize"
        f"?client_id={bot_id}"
        f"&permissions={_INVITE_PERMISSIONS}"
        f"&scope=bot%20applications.commands"
    )
    return {"url": url}


@router.get("/bump-bots")
async def bump_bots():
    """Return the supported bump bots with friendly display names."""
    return [
        {"key": key, "name": BOT_DISPLAY_NAMES.get(key, key.title())}
        for key in SUPPORTED_BOTS
    ]


@router.get("/guilds/{guild_id}/channels")
async def guild_channels(guild_id: str, _session: dict = Depends(require_panel_access)):
    """Return text channels for a guild (cached 60s)."""
    now = time.monotonic()
    cached = _channels_cache.get(guild_id)
    if cached and now - cached["ts"] < _RESOURCE_CACHE_TTL:
        return cached["data"]

    async with _channels_locks[guild_id]:
        now = time.monotonic()
        cached = _channels_cache.get(guild_id)
        if cached and now - cached["ts"] < _RESOURCE_CACHE_TTL:
            return cached["data"]

        if not BOT_TOKEN:
            raise HTTPException(status_code=503, detail="Bot token not configured")

        headers = {"Authorization": f"Bot {BOT_TOKEN}"}
        async with httpx.AsyncClient(timeout=_DISCORD_TIMEOUT) as client:
            resp = await client.get(f"{DISCORD_API_BASE}/guilds/{guild_id}/channels", headers=headers)
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "2"))
                await asyncio.sleep(retry_after)
                resp = await client.get(f"{DISCORD_API_BASE}/guilds/{guild_id}/channels", headers=headers)
            if resp.status_code != 200:
                logger.warning("Failed to fetch channels for guild %s: %s", guild_id, resp.status_code)
                return []

        channels = [
            {"id": ch["id"], "name": ch["name"], "type": ch["type"], "position": ch.get("position", 0)}
            for ch in resp.json()
            if ch["type"] == 0  # GUILD_TEXT
        ]
        channels.sort(key=lambda c: c["position"])
        _channels_cache[guild_id] = {"data": channels, "ts": now}
        return channels


@router.get("/guilds/{guild_id}/roles")
async def guild_roles(guild_id: str, _session: dict = Depends(require_panel_access)):
    """Return assignable roles for a guild (cached 60s)."""
    now = time.monotonic()
    cached = _roles_cache.get(guild_id)
    if cached and now - cached["ts"] < _RESOURCE_CACHE_TTL:
        return cached["data"]

    async with _roles_locks[guild_id]:
        now = time.monotonic()
        cached = _roles_cache.get(guild_id)
        if cached and now - cached["ts"] < _RESOURCE_CACHE_TTL:
            return cached["data"]

        if not BOT_TOKEN:
            raise HTTPException(status_code=503, detail="Bot token not configured")

        headers = {"Authorization": f"Bot {BOT_TOKEN}"}
        async with httpx.AsyncClient(timeout=_DISCORD_TIMEOUT) as client:
            resp = await client.get(f"{DISCORD_API_BASE}/guilds/{guild_id}/roles", headers=headers)
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "2"))
                await asyncio.sleep(retry_after)
                resp = await client.get(f"{DISCORD_API_BASE}/guilds/{guild_id}/roles", headers=headers)
            if resp.status_code != 200:
                logger.warning("Failed to fetch roles for guild %s: %s", guild_id, resp.status_code)
                return []

        roles = [
            {"id": r["id"], "name": r["name"], "color": r.get("color", 0), "position": r.get("position", 0)}
            for r in resp.json()
            if r.get("position", 0) > 0 and not r.get("managed", False)
        ]
        roles.sort(key=lambda r: r["position"])
        _roles_cache[guild_id] = {"data": roles, "ts": now}
        return roles


# ── Public stats (unauthenticated, cached) ───────────────────────────────

_stats_cache: dict[str, object] = {"data": None, "ts": 0.0}


@router.get("/stats/public")
async def public_stats():
    """Public ecosystem counts for the login hero (cached 5 min)."""
    now = time.monotonic()
    data = _stats_cache["data"]
    if data is None or now - float(_stats_cache["ts"]) >= _CACHE_TTL:
        try:
            data = await stats_service.public_stats()
            _stats_cache["data"] = data
            _stats_cache["ts"] = now
        except Exception:
            logger.warning("public_stats compute failed", exc_info=True)
            if data is None:
                return JSONResponse(status_code=503, content={"detail": "stats unavailable"})
    return JSONResponse(content=data, headers={"Cache-Control": "public, max-age=60"})


@router.get("/guilds/{guild_id}/bump-stats")
async def guild_bump_stats(guild_id: int, _session: dict = Depends(require_panel_access)):
    """Per-bot bump status for a guild (last bump, cooldown, next due, status)."""
    gcm = await get_guild_config_manager(db_manager)
    config = await gcm.get_config(guild_id)
    return stats_service.guild_bump_stats(config)
