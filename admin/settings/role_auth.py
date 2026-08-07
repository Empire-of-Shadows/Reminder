"""Role-based authorization for the admin panel.

The panel is ADMIN-ONLY: there is no Mod tier. Tier resolution goes through the
engine ``auth.resolve_panel_role_from_config`` (via ``bindings.resolve_panel_role``):
Manage Server -> admin, else the configured ``roles.admin_role_ids`` list (set
from the panel's Panel Access Roles leaf or the dashboard Settings page).
Anything else resolves to "none" - no panel, no dashboard.
"""

from __future__ import annotations

from typing import Literal

import discord

from storage.config_manager import GuildConfig


PanelRole = Literal["admin", "none"]


def get_panel_role(member: discord.Member, cfg: GuildConfig) -> PanelRole:
    """Return the panel access tier for `member`. Manage Server -> admin."""
    if getattr(member, "guild_permissions", None) and member.guild_permissions.manage_guild:
        return "admin"
    return "none"
