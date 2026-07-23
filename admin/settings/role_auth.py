"""Role-based authorization for the admin panel.

Tier resolution for the panel goes through the engine
``auth.resolve_panel_role_from_config`` (via ``bindings.resolve_panel_role``):
Manage Server -> admin, else the configured ``roles.admin_role_ids`` /
``roles.mod_role_ids`` lists (set from the panel's Panel Access menu or the
dashboard Settings page).

`MOD_ALLOWED_CATEGORIES` stays empty: the Discord panel has no mod-tier
sections (the mod tier is read-only and only meaningful on the dashboard), so
a mod-tier member gets no panel categories here.
"""

from __future__ import annotations

from typing import Literal

import discord

from storage.config_manager import GuildConfig


PanelRole = Literal["admin", "none"]


# No mod tier in ImperialReminder. Kept empty for import compatibility with
# the shared admin_cog (its mod-only branches never fire).
MOD_ALLOWED_CATEGORIES: frozenset[str] = frozenset()


def get_panel_role(member: discord.Member, cfg: GuildConfig) -> PanelRole:
    """Return the panel access tier for `member`. Manage Server -> admin."""
    if getattr(member, "guild_permissions", None) and member.guild_permissions.manage_guild:
        return "admin"
    return "none"
