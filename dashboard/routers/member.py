"""Member-tier API - what this server's bump reminder is doing for YOU.

Everything here is gated on ``require_guild_member``: signed in, and in this
server according to the session's Discord guild list. It is deliberately NOT
``require_panel_access`` - a plain member with no Manage Server and no panel
role reaches these routes, which is the whole point of the member view.

The hard rule for this file: **no manager-only values ever leave it.** No
channel ids, no role ids, no custom message text, no admin role lists. A member
gets booleans and timings ("a bump is due in 40 minutes", "yes you get pinged"),
never the setup itself. Anything added here must pass that test.

Each endpoint stands alone so the dashboard can fetch them additively - the
"will you be pinged" check needs a live Discord member fetch, and it must not
be able to take the bump timings down with it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from dashboard.auth.dependencies import require_guild_member
from dashboard.services import stats as stats_service
from storage.config_manager import get_guild_config_manager
from storage.settings.collections import db_manager
from storage.log import get_logger
from storage.sub_systems.bump_config import (
    BOT_DISPLAY_NAMES,
    BUMP_BOTS,
    BUMP_BOTS_PREMIUM,
)

logger = get_logger("dashboard.routers.member")

router = APIRouter(tags=["member"])

_PREMIUM_STATE_COLLECTION = "premium_state"


def _iso(value) -> str | None:
    """Datetime -> ISO-8601. Naive values are read as UTC (how every writer here
    stores them). Anything else becomes None."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


@router.get("/guilds/{guild_id}/member/bumps")
async def member_bumps(guild_id: int, _session: dict = Depends(require_guild_member)):
    """Per-bot bump timings for a member of this server.

    The rows come from the same ``stats_service.guild_bump_stats`` the admin
    overview uses, so a member and a manager can never be told two different
    stories about the same cooldown. That payload carries no channel or role
    ids - only bot keys, timings and status - which is why it is safe here.
    """
    gcm = await get_guild_config_manager(db_manager)
    config = await gcm.get_config(guild_id)
    try:
        premium = await stats_service.guild_is_premium(guild_id)
    except Exception:
        logger.warning("premium lookup failed for guild %s", guild_id, exc_info=True)
        premium = False
    return stats_service.guild_bump_stats(config, premium=premium)


@router.get("/guilds/{guild_id}/member/reminder")
async def member_reminder(guild_id: int, session: dict = Depends(require_guild_member)):
    """Whether this member is one of the people the bump reminder pings.

    ``you_will_be_pinged`` is deliberately three-valued. The engine's
    ``member_role_ids`` returns an empty set both for "this member holds no
    roles" and for "Discord did not answer", and the two cannot be told apart
    from here - so an empty answer becomes ``null`` ("we could not confirm")
    rather than a confident "no". Saying "you will not be pinged" to somebody
    who actually holds the role is the one wrong answer this endpoint could
    give, and it is the one that would make them miss a bump.
    """
    from dashboard._engine.auth.panel_access import member_role_ids

    gcm = await get_guild_config_manager(db_manager)
    config = await gcm.get_config(guild_id)

    role_configured = bool(config.bump_role)
    watching = bool(config.bump_channel)
    tracked = len([b for b in (config.enabled_bots or []) if b in BUMP_BOTS])

    if not role_configured:
        return {
            "reminder_role_set": False,
            "bump_channel_set": watching,
            "bots_tracked": tracked,
            "you_will_be_pinged": False,
            "status": "no_role",
        }

    user_id = session.get("user_id") or (session.get("user_data") or {}).get("id")
    if not user_id:
        return {
            "reminder_role_set": True,
            "bump_channel_set": watching,
            "bots_tracked": tracked,
            "you_will_be_pinged": None,
            "status": "unknown",
        }

    try:
        held = await member_role_ids(str(guild_id), str(user_id))
    except Exception:
        logger.warning(
            "member role lookup failed for %s in guild %s", user_id, guild_id, exc_info=True
        )
        held = frozenset()

    if not held:
        return {
            "reminder_role_set": True,
            "bump_channel_set": watching,
            "bots_tracked": tracked,
            "you_will_be_pinged": None,
            "status": "unknown",
        }

    pinged = str(config.bump_role) in held
    return {
        "reminder_role_set": True,
        "bump_channel_set": watching,
        "bots_tracked": tracked,
        "you_will_be_pinged": pinged,
        "status": "yes" if pinged else "no",
    }


@router.get("/guilds/{guild_id}/member/entitlements")
async def member_entitlements(guild_id: int, _session: dict = Depends(require_guild_member)):
    """What this server's members can actually use here.

    Premium on ImperialReminder is a *server* entitlement, not a personal one -
    it unlocks the same two things for everybody in the server. So this reports
    the server's state and what it does or does not unlock, plus the commands a
    member can run. The custom reminder's wording is not included: whether one
    is in use is a member's business, its text is the manager's.
    """
    gcm = await get_guild_config_manager(db_manager)
    config = await gcm.get_config(guild_id)

    try:
        premium = await stats_service.guild_is_premium(guild_id)
    except Exception:
        logger.warning("premium lookup failed for guild %s", guild_id, exc_info=True)
        premium = False

    doc = None
    try:
        doc = await db_manager.get_collection_manager(
            _PREMIUM_STATE_COLLECTION
        ).find_one({"_id": f"guild:{guild_id}"})
    except Exception:
        logger.warning("premium_state lookup failed for guild %s", guild_id, exc_info=True)
    doc = doc or {}
    tier = doc.get("tier")

    written = bool((config.custom_message or "").strip())
    enabled = [str(b) for b in (config.enabled_bots or []) if str(b) in BUMP_BOTS]
    delays = config.bot_delay or {}

    faster = []
    for key in enabled:
        premium_cooldown = BUMP_BOTS_PREMIUM.get(key)
        if premium_cooldown is None:
            continue
        standard = int(BUMP_BOTS[key])
        current = int(delays.get(key, standard) or standard)
        faster.append({
            "key": key,
            "name": BOT_DISPLAY_NAMES.get(key, key.title()),
            "standard_cooldown": standard,
            "premium_cooldown": int(premium_cooldown),
            "active": bool(premium and current == int(premium_cooldown)),
        })

    return {
        "is_premium": bool(premium),
        "tier": str(tier) if (premium and tier) else None,
        "expires_at": _iso(doc.get("expires_at")),
        "custom_wording": {
            "available": bool(premium),
            "written": written,
            "in_use": bool(premium and written),
        },
        "faster_cooldowns": faster,
        "commands": [
            {
                "name": "/help",
                "detail": "Browse what the bot does and how the reminders work.",
            },
            {
                "name": "/premium status",
                "detail": "Check whether this server has premium and when it runs out.",
            },
        ],
    }
