from fastapi import APIRouter, Depends, HTTPException
from dashboard.auth.dependencies import get_current_user
from dashboard.auth.panel_role import resolve_panel_role, require_panel_access, MOD_ALLOWED_SECTIONS
from dashboard._engine.auth.csrf import verify_csrf
from storage.settings.collections import db_manager
from storage.config_manager import get_guild_config_manager, GuildConfig
from storage.sub_systems.bump_config import SUPPORTED_BOTS
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
    "roles",
}


async def _validate_guild_ids(guild_id: int, updates: dict) -> None:
    """Reject channel/role snowflakes that don't belong to this guild.

    Uses the cached guild channel/role fetchers. Fails open when the fetch
    comes back empty (Discord unreachable) so an API hiccup never blocks a
    legitimate save - the bot degrades gracefully on foreign ids anyway.
    """
    from dashboard.routers.dashboard import guild_channels, guild_roles

    channel_keys = [k for k in ("bump_channel", "timers_channel") if updates.get(k)]
    if channel_keys:
        channels = await guild_channels(str(guild_id))
        valid_channels = {str(c["id"]) for c in channels}
        if valid_channels:
            for k in channel_keys:
                if str(updates[k]) not in valid_channels:
                    raise HTTPException(
                        status_code=422, detail=f"{k} is not a channel in this guild"
                    )

    role_cfg = updates.get("roles") or {}
    wants_roles = bool(updates.get("bump_role")) or bool(
        role_cfg.get("admin_role_ids") or role_cfg.get("mod_role_ids")
    )
    if wants_roles:
        roles = await guild_roles(str(guild_id))
        valid_roles = {str(r["id"]) for r in roles}
        if valid_roles:
            if updates.get("bump_role") and str(updates["bump_role"]) not in valid_roles:
                raise HTTPException(
                    status_code=422, detail="bump_role is not a role in this guild"
                )
            for list_key in ("admin_role_ids", "mod_role_ids"):
                if any(str(r) not in valid_roles for r in role_cfg.get(list_key, [])):
                    raise HTTPException(
                        status_code=422,
                        detail=f"roles.{list_key} contains a role not in this guild",
                    )


def _coerce_id(value) -> int:
    """Parse an incoming ID (string/number/None) to an int; 0 means unset."""
    if value in (None, "", 0, "0"):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _serialize(config: GuildConfig, panel_role: str) -> dict:
    """Config dict with snowflake IDs as strings ('' when unset)."""
    data = config.to_dict()
    for key in _ID_FIELDS:
        val = data.get(key) or 0
        data[key] = str(val) if val else ""
    # Role-id lists travel as strings too.
    roles = data.get("roles") or {}
    data["roles"] = {
        "admin_role_ids": [str(r) for r in (roles.get("admin_role_ids") or [])],
        "mod_role_ids": [str(r) for r in (roles.get("mod_role_ids") or [])],
    }
    data["panel_role"] = panel_role
    data["mod_allowed_sections"] = sorted(MOD_ALLOWED_SECTIONS)
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
    # Mod tier is read-only (MOD_ALLOWED_SECTIONS is empty); only admins write.
    if role != "admin":
        raise HTTPException(status_code=403, detail="Mod role cannot change settings")

    gcm = await get_guild_config_manager(db_manager)

    # Build a whitelisted partial update and write it as one surgical $set.
    # Never replace the whole document: the bot process writes timestamps and
    # premium flags concurrently, and a full-document write from a cached
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
            value = value if isinstance(value, dict) else {}
            updates[key] = {
                "admin_role_ids": [str(r) for r in (value.get("admin_role_ids") or [])],
                "mod_role_ids": [str(r) for r in (value.get("mod_role_ids") or [])],
            }

    if updates:
        await _validate_guild_ids(guild_id, updates)
        if not await gcm.set_values(guild_id, updates):
            raise HTTPException(status_code=500, detail="Failed to save settings")

    config = await gcm.get_config(guild_id)
    return _serialize(config, role)
