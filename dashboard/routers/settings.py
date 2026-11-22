from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from dashboard.auth.dependencies import get_current_user
from dashboard.auth.panel_role import resolve_panel_role, require_panel_access
from dashboard._engine.auth.panel_access import has_manage_guild
from dashboard._engine.discord_cache import (
    discord_cache,
    missing_permissions,
    permission_label,
)
from dashboard._engine.auth.csrf import verify_csrf
from dashboard.services import stats as stats_service
from storage.audit_log import get_audit_log_manager
from storage.settings.collections import db_manager
from storage.config_manager import get_guild_config_manager, GuildConfig
from storage.sub_systems.bump_config import (
    BUMP_BOTS,
    BUMP_BOTS_CHOICES,
    SUPPORTED_BOTS,
)
from storage.log import get_logger

logger = get_logger("dashboard.routers.settings")
router = APIRouter(tags=["settings"])

# Discord snowflake IDs are 64-bit and exceed JS's safe-integer range, so they
# must cross the wire as strings (JSON numbers would lose precision in the
# browser). They are stored as ints in Mongo (the bot needs ints for the Discord
# API), so we stringify on the way out and parse back to int on the way in.
_ID_FIELDS = ("bump_channel", "bump_role", "timers_channel")
_ALLOWED_KEYS = {
    "bump_channel", "bump_role", "enabled_bots",
    "timers_channel", "timers_message", "custom_message",
    "roles", "bot_delay",
}

#: Which settings-page section a changed key belongs to, for the audit trail.
#: ``bot_delay.<bot>`` is handled separately; everything else is a flat key.
_KEY_SECTIONS = {
    "bump_channel": "bumps",
    "bump_role": "bumps",
    "enabled_bots": "bots",
    "timers_channel": "timers",
    "timers_message": "timers",
    "custom_message": "message",
    "roles": "access",
}


#: Shown when the server's channel list cannot be read. The fleet wording (TheCodex 2026-11-20).
_CHANNEL_LIST_UNREADABLE = (
    "Could not check that channel against this server's channel list. Try again in a moment."
)

#: Discord channel type the panel's Bump Channel and Timers Channel pickers offer
#: (``channel_types=[discord.ChannelType.text]`` in admin/settings/panel_configs.py).
_TEXT_CHANNEL_TYPE = 0

_CHANNEL_LABELS = {"bump_channel": "bump channel", "timers_channel": "timers channel"}


async def _validate_guild_ids(guild_id: int, before: GuildConfig, updates: dict) -> None:
    """Refuse a channel or role that does not belong to this server.

    Only values this save CHANGES are checked, so an id that was already stored
    never blocks an unrelated save.

    Channels fail CLOSED (security review 2026-11-21, TheCodex's 2026-11-20 rule):
    when the server's channel list cannot be read the save is refused with a "try
    again". Until then an unreadable list let any id through, and the bot resolved
    the stored channel globally, so an admin of one server could point the bump or
    timers channel at another server's channel and have reminders posted there.
    A channel of the wrong kind is refused too (the panel offers text channels only).

    Roles fail OPEN (owner decision 2026-09-14: only the channel list is a security
    boundary), and are checked against the server's FULL role list
    (``guild_roles_raw``), not the assignable-only list the role picker shows.
    """
    changed_channels = [
        key for key in ("bump_channel", "timers_channel")
        if updates.get(key) and updates[key] != int(getattr(before, key) or 0)
    ]
    if changed_channels:
        channels = await discord_cache.guild_channels_raw(str(guild_id))
        if not channels:
            raise HTTPException(status_code=422, detail=_CHANNEL_LIST_UNREADABLE)
        by_id = {str(c["id"]): c for c in channels}
        for key in changed_channels:
            channel = by_id.get(str(updates[key]))
            label = _CHANNEL_LABELS[key]
            if channel is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"That {label} is not in this server. Pick one of this server's channels.",
                )
            if channel.get("type") != _TEXT_CHANNEL_TYPE:
                raise HTTPException(
                    status_code=422,
                    detail=f"The {label} must be a text channel. Pick a text channel from the list.",
                )

    new_bump_role = updates.get("bump_role")
    if new_bump_role == int(before.bump_role or 0):
        new_bump_role = 0
    stored_admin = {str(r) for r in _normalized_roles(before.roles)["admin_role_ids"]}
    added_admin = [
        str(r) for r in (updates.get("roles") or {}).get("admin_role_ids", [])
        if str(r) not in stored_admin
    ]
    if not new_bump_role and not added_admin:
        return

    # A readable list always holds @everyone, so an empty one means Discord could
    # not be read: let the save through.
    by_id = {str(r["id"]): r for r in await discord_cache.guild_roles_raw(str(guild_id))}
    if not by_id:
        return

    if new_bump_role and str(new_bump_role) not in by_id:
        raise HTTPException(
            status_code=422,
            detail="That bump role is not in this server. Pick one of this server's roles.",
        )
    for rid in added_admin:
        if rid == str(guild_id):
            raise HTTPException(
                status_code=422,
                detail="@everyone cannot manage this bot - that would give every member full "
                       "access. Pick a specific role.",
            )
        role = by_id.get(rid)
        if role is None:
            raise HTTPException(
                status_code=422,
                detail="Manager roles include a role that is not in this server. "
                       "Pick it again from the list.",
            )
        if role.get("managed"):
            raise HTTPException(
                status_code=422,
                detail=f"@{role['name']} is managed by an integration, so anyone that "
                       f"integration hands it to would get full access. Pick a normal role.",
            )


#: The most roles the admin panel's Panel Access Roles picker holds (its node's
#: ``max_values``, the engine ``panel_roles_pair`` default of 10). The panel passes every
#: stored id to the picker as a default value with no trim, so a longer list saved here
#: would stop that panel screen from opening. test_dashboard_list_caps pins this to the node.
ACCESS_ROLES_MAX = 10


def _refuse_overlong_lists(before: GuildConfig, updates: dict) -> None:
    """400 when a save makes the Manager roles list longer than the panel can show.

    A list may always shrink, and one already over the cap may be saved unchanged, so an
    unrelated save never fails and the way back under the cap stays open. (Enabled Bots
    cannot grow past the panel's cap: only the supported bots survive parsing.)
    """
    if "roles" not in updates:
        return
    wanted = updates["roles"].get("admin_role_ids") or []
    stored = _normalized_roles(before.roles)["admin_role_ids"]
    if len(wanted) > ACCESS_ROLES_MAX and len(wanted) > len(stored):
        raise HTTPException(
            status_code=400,
            detail=f"Manager roles can hold at most {ACCESS_ROLES_MAX} roles, the same as in "
                   f"the Discord admin panel. Remove some, then save again.",
        )


#: What the bot needs in the Bump Channel and the Timers Channel - the same list the
#: in-Discord panel checks (admin/settings/panel_configs.py required_channel_perms).
_CHANNEL_PERMS = ["view_channel", "send_messages", "embed_links", "read_message_history"]


async def _validate_like_the_panel(guild_id: int, before: GuildConfig, updates: dict) -> None:
    """Refuse the saves the in-Discord panel refuses, for the values this save changes.

    The panel refuses a bump role that can never ping anybody and a channel the bot
    cannot fully use; the dashboard used to accept both, and the result was a server
    that looked set up and silently reminded nobody. Discord lookups fail open
    (an unreachable API must not block a save), like the role checks in
    ``_validate_guild_ids``; only its channel membership check fails closed.
    """
    new_role = updates.get("bump_role")
    if new_role and new_role != int(before.bump_role or 0):
        if str(new_role) == str(guild_id):
            raise HTTPException(
                status_code=422,
                detail="@everyone cannot be the bump role - the reminder would ping nobody. "
                       "Pick a normal, mentionable role.",
            )
        role = await discord_cache.guild_role(str(guild_id), str(new_role))
        if role is not None:
            if role["managed"]:
                raise HTTPException(
                    status_code=422,
                    detail=f"@{role['name']} is managed by an integration, so Discord will not "
                           f"let it be mentioned and the reminder would ping nobody. Pick a "
                           f"normal, mentionable role.",
                )
            if not role["mentionable"]:
                raise HTTPException(
                    status_code=422,
                    detail=f"@{role['name']} is not mentionable, so the reminder would ping "
                           f"nobody. Turn on 'Allow anyone to @mention this role' in Server "
                           f"Settings > Roles, or pick another role.",
                )

    for key in ("bump_channel", "timers_channel"):
        new_channel = updates.get(key)
        if not new_channel or new_channel == int(getattr(before, key) or 0):
            continue
        perms = await discord_cache.bot_channel_permissions(str(guild_id), str(new_channel))
        missing = missing_permissions(perms, _CHANNEL_PERMS)
        if missing:
            label = "bump channel" if key == "bump_channel" else "timers channel"
            raise HTTPException(
                status_code=422,
                detail=f"The bot is missing permissions in that {label}: "
                       f"{', '.join(permission_label(m) for m in missing)}. Grant them in the "
                       f"channel's settings, then save again.",
            )


def _coerce_id(value) -> int:
    """Parse an incoming ID (string/number/None) to an int; 0 means unset."""
    if value in (None, "", 0, "0"):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalized_roles(raw) -> dict:
    """The canonical wire shape for the panel-access role list."""
    raw = raw if isinstance(raw, dict) else {}
    return {"admin_role_ids": [str(r) for r in (raw.get("admin_role_ids") or [])]}


def _coerce_bot_delay(value) -> dict[str, int]:
    """Validate an incoming ``bot_delay`` map into ``{bot: seconds}``.

    Two separate checks, and both matter. The key must be a bot this bot
    actually supports, and the value must be one of the cooldowns offered for
    THAT bot (``BUMP_BOTS_CHOICES``) - a free-typed number here would let the
    dashboard schedule a reminder shorter than the listing service's real
    cooldown, so every reminder after it would be for a bump that cannot be
    made.
    """
    value = value if isinstance(value, dict) else {}
    out: dict[str, int] = {}
    for bot, raw in value.items():
        bot = str(bot)
        if bot not in SUPPORTED_BOTS:
            raise HTTPException(
                status_code=422, detail=f"'{bot}' is not a supported bump bot"
            )
        try:
            seconds = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422, detail=f"bot_delay.{bot} must be a number of seconds"
            )
        allowed = set(BUMP_BOTS_CHOICES.get(bot, {}).values())
        if seconds not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"bot_delay.{bot} is not one of the cooldowns offered for that bot",
            )
        out[bot] = seconds
    return out


def _old_value(config: GuildConfig, key: str) -> Any:
    """The stored value a proposed update would replace, in the update's own shape."""
    if key.startswith("bot_delay."):
        bot = key.split(".", 1)[1]
        delays = config.bot_delay or {}
        return int(delays.get(bot, BUMP_BOTS.get(bot, 0)) or 0)
    if key == "roles":
        return _normalized_roles(config.roles)
    return getattr(config, key, None)


def _serialize(config: GuildConfig, panel_role: str) -> dict:
    """Config dict with snowflake IDs as strings ('' when unset)."""
    data = config.to_dict()
    for key in _ID_FIELDS:
        val = data.get(key) or 0
        data[key] = str(val) if val else ""
    # Role-id lists travel as strings too.
    data["roles"] = _normalized_roles(data.get("roles"))
    data["panel_role"] = panel_role
    return data


@router.get("/guilds/{guild_id}/settings")
async def get_settings(guild_id: int, session: dict = Depends(require_panel_access)):
    role = await resolve_panel_role(session, str(guild_id))
    gcm = await get_guild_config_manager(db_manager)
    config = await gcm.get_config(guild_id)
    return _serialize(config, role)


@router.put("/guilds/{guild_id}/settings")
async def update_settings(
    guild_id: int,
    patch: dict,
    session: dict = Depends(require_panel_access),
    _csrf: None = Depends(verify_csrf),
):
    role = await resolve_panel_role(session, str(guild_id))
    # Admin-only surface: require_panel_access already rejects "none", so this is
    # defense in depth against a future tier ever being added.
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    gcm = await get_guild_config_manager(db_manager)
    # Read before writing: the audit trail needs the value each change replaced,
    # and "unchanged" has to be decidable so a save that touched nothing does
    # not fill the history with entries nobody made.
    before = await gcm.get_config(guild_id)

    # Build a whitelisted partial update and write it as one surgical $set.
    # Never replace the whole document: the bot process writes timestamps concurrently, and a full-document write from a cached
    # snapshot would silently clobber them.
    updates: dict = {}
    for key, value in patch.items():
        if key not in _ALLOWED_KEYS:
            continue
        if key in _ID_FIELDS:
            updates[key] = _coerce_id(value)
        elif key == "enabled_bots":
            bots = value if isinstance(value, list) else []
            updates[key] = [str(b) for b in bots if str(b) in SUPPORTED_BOTS]
        elif key == "timers_message":
            updates[key] = bool(value)
        elif key == "custom_message":
            updates[key] = str(value or "")
        elif key == "roles":
            updates[key] = _normalized_roles(value)
        elif key == "bot_delay":
            # Per-bot cooldowns are written as dotted leaves so saving one bot's
            # cooldown never rewrites another's.
            for bot, seconds in _coerce_bot_delay(value).items():
                updates[f"bot_delay.{bot}"] = seconds

    # Changing who can manage needs Manage Server itself, as it does in the panel:
    # otherwise a Panel Access role holder could hand that access to anyone.
    if "roles" in updates and updates["roles"] != _normalized_roles(before.roles):
        if not await has_manage_guild(session, str(guild_id)):
            raise HTTPException(
                status_code=403,
                detail="Only members with the Manage Server permission can change who can manage this bot.",
            )

    if updates:
        _refuse_overlong_lists(before, updates)
        # Membership first: nothing else is worth checking for a channel elsewhere.
        await _validate_guild_ids(guild_id, before, updates)
        await _validate_like_the_panel(guild_id, before, updates)
        if not await gcm.set_values(guild_id, updates):
            raise HTTPException(status_code=500, detail="Failed to save settings")
        await _audit_changes(guild_id, session, before, updates)

    config = await gcm.get_config(guild_id)
    return _serialize(config, role)


async def _audit_changes(
    guild_id: int, session: dict, before: GuildConfig, updates: dict
) -> None:
    """Record one audit entry per key this save actually changed.

    Until this existed the in-Discord panel wrote to the audit log and the
    dashboard did not, so a server's change history quietly omitted every edit
    made on the web - and so did the privacy export built on the same records.
    ``source`` distinguishes the two writers.

    Best-effort by design: a save that succeeded must not be reported as failed
    because the trail could not be appended.
    """
    changed = [
        (key, value)
        for key, value in updates.items()
        if _old_value(before, key) != value
    ]
    if not changed:
        return

    user_data = session.get("user_data") or {}
    actor_id = user_data.get("id") or session.get("user_id")
    if actor_id is None:
        return
    actor_name = (
        user_data.get("global_name")
        or user_data.get("username")
        or str(actor_id)
    )

    try:
        audit = get_audit_log_manager(db_manager)
    except Exception:
        logger.warning("audit log unavailable for guild %s", guild_id, exc_info=True)
        return

    for key, value in changed:
        section = (
            "cooldowns" if key.startswith("bot_delay.") else _KEY_SECTIONS.get(key, "")
        )
        try:
            await audit.log_config_change(
                guild_id=guild_id,
                actor_id=actor_id,
                actor_name=actor_name,
                action="set",
                section=section,
                key=key,
                old_value=_old_value(before, key),
                new_value=value,
                source="dashboard",
            )
        except Exception:
            logger.warning(
                "audit entry failed for guild %s key %s", guild_id, key, exc_info=True
            )
