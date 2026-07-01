"""Role-based authorization for the admin panel.

ImperialReminder gates the panel on Discord's Manage Server permission only —
there is no configured admin/mod role concept (matching the dashboard, which
uses MANAGE_GUILD exclusively). Two tiers are exposed:
  - "admin": full panel access (Discord manage_guild)
  - "none":  no panel access

`MOD_ALLOWED_CATEGORIES` is kept (empty) so `admin_cog.AdminCog` can import it
unchanged; the mod tier is never granted here.
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
