"""
Admin Panel Config Trees for ImperialReminder.

Defines the PanelNode config tree for the bump-reminder admin panel. The shared
engine (admin_cog + views/panel_engine) consumes this tree; only get/set/clear
accessor helpers and the tree shape are bot-specific.

Accessor contract (per PanelNode):
    get_values:   async (guild_id) -> list
    set_values:   async (guild_id, values) -> bool
    clear_values: async (guild_id) -> bool
"""

import discord

from .panel_branding import PANEL_DESCRIPTION, PANEL_TITLE
from .views.panel_engine import PanelNode
from storage.config_manager import get_guild_config_manager
from storage.premium_manager import get_premium_manager
from storage.sub_systems.bump_config import (
    BUMP_BOTS,
    BUMP_BOTS_CHOICES,
    BUMP_BOTS_PREMIUM,
    SUPPORTED_BOTS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Channel / role accessors
# ─────────────────────────────────────────────────────────────────────────────

async def _get_channel(guild_id: int, attr: str) -> list:
    cm = await get_guild_config_manager()
    config = await cm.get_config(guild_id)
    val = getattr(config, attr, 0)
    return [val] if val else []


async def _set_channel(guild_id: int, values: list, attr: str) -> bool:
    cm = await get_guild_config_manager()
    return await cm.set_value(guild_id, attr, int(values[0]) if values else 0)


async def _clear_channel(guild_id: int, attr: str) -> bool:
    cm = await get_guild_config_manager()
    return await cm.set_value(guild_id, attr, 0)


async def _post_save_bump_channel(interaction, guild_id: int, values: list) -> None:
    """Default the timers channel to the bump channel when unset (mirrors old /bump setup)."""
    if not values:
        return
    cm = await get_guild_config_manager()
    config = await cm.get_config(guild_id)
    if not config.timers_channel:
        await cm.set_value(guild_id, "timers_channel", int(values[0]))


async def _get_role(guild_id: int) -> list:
    cm = await get_guild_config_manager()
    config = await cm.get_config(guild_id)
    return [config.bump_role] if config.bump_role else []


async def _set_role(guild_id: int, values: list) -> bool:
    cm = await get_guild_config_manager()
    return await cm.set_value(guild_id, "bump_role", int(values[0]) if values else 0)


async def _clear_role(guild_id: int) -> bool:
    cm = await get_guild_config_manager()
    return await cm.set_value(guild_id, "bump_role", 0)


# ─────────────────────────────────────────────────────────────────────────────
# Bump bots accessors
# ─────────────────────────────────────────────────────────────────────────────

async def _get_enabled_bots(guild_id: int) -> list:
    cm = await get_guild_config_manager()
    config = await cm.get_config(guild_id)
    return [str(b) for b in (config.enabled_bots or [])]


async def _set_enabled_bots(guild_id: int, values: list) -> bool:
    cm = await get_guild_config_manager()
    return await cm.set_value(guild_id, "enabled_bots", [str(v) for v in values])


async def _get_delay(guild_id: int, bot_name: str) -> list:
    cm = await get_guild_config_manager()
    config = await cm.get_config(guild_id)
    val = config.bot_delay.get(bot_name, BUMP_BOTS.get(bot_name))
    return [str(val)] if val is not None else []


async def _set_delay(guild_id: int, values: list, bot_name: str) -> bool:
    if not values:
        return False
    cm = await get_guild_config_manager()
    return await cm.set_value(guild_id, f"bot_delay.{bot_name}", int(values[0]))


# ─────────────────────────────────────────────────────────────────────────────
# Messages accessors
# ─────────────────────────────────────────────────────────────────────────────

async def _get_custom_message(guild_id: int) -> list:
    cm = await get_guild_config_manager()
    config = await cm.get_config(guild_id)
    return [config.custom_message] if config.custom_message else []


async def _set_custom_message(guild_id: int, values: list) -> bool:
    cm = await get_guild_config_manager()
    return await cm.set_value(guild_id, "custom_message", values[0] if values else "")


async def _clear_custom_message(guild_id: int) -> bool:
    cm = await get_guild_config_manager()
    return await cm.set_value(guild_id, "custom_message", "")


async def _get_timers_message(guild_id: int) -> list:
    cm = await get_guild_config_manager()
    config = await cm.get_config(guild_id)
    return ["on"] if config.timers_message else ["off"]


async def _set_timers_message(guild_id: int, values: list) -> bool:
    cm = await get_guild_config_manager()
    enabled = (values[0] == "on") if values else True
    return await cm.set_value(guild_id, "timers_message", enabled)


# ─────────────────────────────────────────────────────────────────────────────
# Premium accessors
# ─────────────────────────────────────────────────────────────────────────────

def _premium_status_text(guild_id: int) -> str:
    """Sync status line for the Premium menu description.

    Reads the GuildConfigManager's in-memory cache (warmed when the panel opens
    and after activation via the post-save hook) since description_builder is
    synchronous and cannot await a DB fetch.
    """
    base = (
        "Premium features coming in the future\n\n"
    )
    try:
        from storage import config_manager as _cm_mod
        mgr = _cm_mod._guild_config_manager
        cfg = mgr.peek(guild_id) if mgr else None
    except Exception:
        cfg = None

    if cfg and cfg.premium.get("enabled"):
        by = cfg.premium.get("activated_by")
        suffix = f" (activated by <@{by}>)" if by else ""
        return base + f"**Status:** ✅ Premium active{suffix}"
    return base + "**Status:** ❌ Not active. Enter a premium code below to activate."


async def _activate_premium(guild_id: int, values: list) -> bool:
    """Validate and link a premium code, then flip premium.enabled on.

    The link itself is a conditional atomic update (unlinked + unexpired guard
    in the Mongo filter), so one code can never be claimed by two guilds even
    under concurrent redemption; premium.enabled is only set when the claim
    actually matched.
    """
    code = (values[0] if values else "").strip()
    if not code:
        return False
    pm = await get_premium_manager()
    sub = await pm.get_code(code)
    if not sub:
        return False
    claimed = await pm.link_code_to_guild(code, guild_id)
    if not claimed:
        return False  # expired, past expires_at, or already linked elsewhere
    cm = await get_guild_config_manager()
    await cm.set_value(guild_id, "premium.enabled", True)
    return True


async def _after_activate_premium(interaction, guild_id: int, values: list) -> None:
    """Record who activated premium and warm the config cache for status display."""
    cm = await get_guild_config_manager()
    await cm.set_value(guild_id, "premium.activated_by", interaction.user.id)
    await cm.get_config(guild_id)  # repopulate cache so the status line is fresh


# ─────────────────────────────────────────────────────────────────────────────
# Lock computation
# ─────────────────────────────────────────────────────────────────────────────

async def _main_locked_children(guild_id: int) -> set[str]:
    """Lock Bump Bots / Messages until a bump channel and role are set."""
    cm = await get_guild_config_manager()
    config = await cm.get_config(guild_id)
    if not (config.bump_channel and config.bump_role):
        return {"bots", "messages"}
    return set()


# ─────────────────────────────────────────────────────────────────────────────
# Core Setup
# ─────────────────────────────────────────────────────────────────────────────

SETUP_CONFIG = PanelNode(
    key="setup",
    label="Core Setup",
    kind="menu",
    category_group="main",
    description=(
        "The minimum configuration. A **Bump Channel** and **Bump Role** are "
        "required before reminders run."
    ),
    children={
        "bump_channel": PanelNode(
            key="bump_channel",
            label="Bump Channel",
            kind="channel_select",
            description="Channel your bump bots post in — reminders are sent here.",
            get_values=lambda gid: _get_channel(gid, "bump_channel"),
            set_values=lambda gid, vals: _set_channel(gid, vals, "bump_channel"),
            clear_values=lambda gid: _clear_channel(gid, "bump_channel"),
            post_save_hook=_post_save_bump_channel,
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            required_channel_perms=["send_messages", "embed_links"],
        ),
        "bump_role": PanelNode(
            key="bump_role",
            label="Bump Role",
            kind="role_select",
            description="Role mentioned when it's time to bump again.",
            get_values=_get_role,
            set_values=_set_role,
            clear_values=_clear_role,
            min_values=1,
            max_values=1,
        ),
        "timers_channel": PanelNode(
            key="timers_channel",
            label="Timers Channel",
            kind="channel_select",
            description=(
                "Channel where the live countdown timer embed is shown. "
                "Defaults to the Bump Channel."
            ),
            get_values=lambda gid: _get_channel(gid, "timers_channel"),
            set_values=lambda gid, vals: _set_channel(gid, vals, "timers_channel"),
            clear_values=lambda gid: _clear_channel(gid, "timers_channel"),
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            required_channel_perms=["send_messages", "embed_links"],
        ),
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# Bump Bots
# ─────────────────────────────────────────────────────────────────────────────

def _bot_label(bot_name: str) -> str:
    return bot_name.capitalize()


def _build_cooldown_children() -> dict:
    """Build one option_select node per supported bot for the Cooldowns submenu."""
    children: dict[str, PanelNode] = {}
    for bot_name in SUPPORTED_BOTS:
        choices = BUMP_BOTS_CHOICES.get(bot_name, {f"{BUMP_BOTS[bot_name] // 60} Minutes": BUMP_BOTS[bot_name]})
        options = [(str(secs), label) for label, secs in choices.items()]
        prem = BUMP_BOTS_PREMIUM.get(bot_name)
        premium_values = {str(prem)} if prem is not None else None
        children[f"cd_{bot_name}"] = PanelNode(
            key=f"cd_{bot_name}",
            label=_bot_label(bot_name),
            kind="option_select",
            description=f"Reminder cooldown for {_bot_label(bot_name)}.",
            options=options,
            premium_values=premium_values,
            get_values=lambda gid, b=bot_name: _get_delay(gid, b),
            set_values=lambda gid, vals, b=bot_name: _set_delay(gid, vals, b),
            min_values=1,
            max_values=1,
        )
    return children


BOTS_CONFIG = PanelNode(
    key="bots",
    label="Bump Bots",
    kind="menu",
    category_group="feature",
    description="Choose which bump bots to track and tune each one's reminder cooldown.",
    children={
        "enabled_bots": PanelNode(
            key="enabled_bots",
            label="Enabled Bots",
            kind="option_select",
            description="Pick which bump bots Imperial Reminder should watch.",
            options=[(b, _bot_label(b)) for b in SUPPORTED_BOTS],
            get_values=_get_enabled_bots,
            set_values=_set_enabled_bots,
            min_values=0,
            max_values=len(SUPPORTED_BOTS),
        ),
        "cooldowns": PanelNode(
            key="cooldowns",
            label="Cooldowns",
            kind="menu",
            description="Per-bot reminder cooldowns. 💎 options require Premium.",
            children=_build_cooldown_children(),
        ),
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# Messages
# ─────────────────────────────────────────────────────────────────────────────

MESSAGES_CONFIG = PanelNode(
    key="messages",
    label="Messages",
    kind="menu",
    category_group="feature",
    description="Customize reminder text and the live timer embed.",
    children={
        "custom_message": PanelNode(
            key="custom_message",
            label="Custom Reminder Message",
            kind="modal_input",
            description=(
                "Optional message appended to reminders. Placeholders: "
                "`{bump_role}` (the role mention) and `{bots}` (the bots due). "
                "Leave empty to clear."
            ),
            modal_title="Custom Reminder Message",
            modal_label="Message",
            modal_placeholder="Time to bump! {bump_role}",
            modal_min_length=0,
            modal_max_length=500,
            modal_paragraph=True,
            modal_required=False,
            get_values=_get_custom_message,
            set_values=_set_custom_message,
            clear_values=_clear_custom_message,
        ),
        "timers_message": PanelNode(
            key="timers_message",
            label="Show Timer Embed",
            kind="option_select",
            description="Whether to display the live countdown timer embed.",
            options=[("on", "On (Default)"), ("off", "Off")],
            get_values=_get_timers_message,
            set_values=_set_timers_message,
            min_values=1,
            max_values=1,
        ),
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# Premium
# ─────────────────────────────────────────────────────────────────────────────

PREMIUM_CONFIG = PanelNode(
    key="premium",
    label="Premium",
    kind="menu",
    category_group="feature",
    description_builder=_premium_status_text,
    children={
        "activate": PanelNode(
            key="activate",
            label="Activate Premium Code",
            kind="modal_input",
            description="Enter a premium code provided by staff to activate Premium.",
            modal_title="Activate Premium",
            modal_label="Premium Code",
            modal_placeholder="Enter your code...",
            modal_min_length=1,
            modal_max_length=32,
            modal_required=True,
            set_values=_activate_premium,
            post_save_hook=_after_activate_premium,
        ),
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# Top-level panel tree
# ─────────────────────────────────────────────────────────────────────────────

MAIN_PANEL = PanelNode(
    key="main",
    label=PANEL_TITLE,
    kind="menu",
    description=PANEL_DESCRIPTION,
    locked_children=_main_locked_children,
    lock_reason=(
        "Finish **Core Setup** first — set a **Bump Channel** and **Bump Role**, "
        "then this section unlocks."
    ),
    children={
        "setup": SETUP_CONFIG,
        "bots": BOTS_CONFIG,
        "messages": MESSAGES_CONFIG,
        "premium": PREMIUM_CONFIG,
    },
)
