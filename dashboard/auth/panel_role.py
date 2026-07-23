"""Panel-role policy for the ImperialReminder dashboard (3-tier: admin / mod / none).

The live guild-permission plumbing (bot-token MANAGE_GUILD check, member-role fetch,
rate limiter, caches) lives in the shared engine at
``dashboard/_engine/auth/panel_access.py``. This file is only reminder's tier policy:
admin/mod role lists live on the guild config document (``ImperialReminder.GuildData``,
``_id`` = str(guild_id)) at the canonical ``roles.admin_role_ids`` /
``roles.mod_role_ids`` paths - the SAME lists the in-Discord ``/admin panel``'s
Panel Access menu edits.

Tiers:
  - "admin": MANAGE_GUILD (verified live via the bot token) OR overlap with
    roles.admin_role_ids
  - "mod":   overlap with roles.mod_role_ids (read-only on this dashboard)
  - "none":  no panel access
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from dashboard._engine.auth.panel_access import (
    PanelRole,
    has_manage_guild,
    member_role_ids,
    session_has_manage_guild,
)
from dashboard.auth.dependencies import get_current_user
from storage.settings.collections import db_manager
from storage.log import get_logger

logger = get_logger("dashboard.auth.panel_role")

# Sections a mod tier may PUT. Empty -> mods are read-only (view settings, no
# changes). Admin tier edits everything.
MOD_ALLOWED_SECTIONS: frozenset[str] = frozenset()


def _guild_data_collection():
    # Engine CollectionManager for ImperialReminder.GuildData; no raw access.
    return db_manager.get_collection_manager("settings_guild_data")


async def _guild_role_lists(guild_id: str) -> tuple[frozenset[str], frozenset[str]]:
    """Return (admin_role_ids, mod_role_ids) configured for the guild."""
    try:
        doc = await _guild_data_collection().find_one(
            {"_id": str(guild_id)}, projection={"roles": 1}
        )
    except Exception:
        logger.warning(f"panel-role config lookup failed for {guild_id}", exc_info=True)
        return (frozenset(), frozenset())
    roles = (doc or {}).get("roles") or {}
    admin_ids = frozenset(str(r) for r in (roles.get("admin_role_ids") or []))
    mod_ids = frozenset(str(r) for r in (roles.get("mod_role_ids") or []))
    return (admin_ids, mod_ids)


async def resolve_panel_role(
    session: dict, guild_id: str, *, verify_manage_live: bool = True
) -> PanelRole:
    """Resolve the user's panel tier for ``guild_id``.

    ``verify_manage_live=False`` uses the cheap session snapshot for the MANAGE_GUILD
    step (for guild-list probing); the default verifies it live via the bot token, so a
    revoked Manage Server loses dashboard admin immediately rather than after the
    session's guild-list cache expires.
    """
    if verify_manage_live:
        if await has_manage_guild(session, guild_id):
            return "admin"
    elif session_has_manage_guild(session, guild_id):
        return "admin"

    admin_ids, mod_ids = await _guild_role_lists(guild_id)
    if not admin_ids and not mod_ids:
        return "none"

    user_id = session.get("user_id") or session.get("user_data", {}).get("id")
    if not user_id:
        return "none"

    member_roles = await member_role_ids(str(guild_id), str(user_id))
    if not member_roles:
        return "none"

    if member_roles & admin_ids:
        return "admin"
    if member_roles & mod_ids:
        return "mod"
    return "none"


async def require_panel_access(
    guild_id: str,
    session: dict = Depends(get_current_user),
) -> dict:
    """FastAPI dependency: 403 unless the user resolves to admin/mod for the
    guild. Returns the session."""
    role = await resolve_panel_role(session, str(guild_id))
    if role == "none":
        raise HTTPException(status_code=403, detail="No panel access for this guild")
    return session
