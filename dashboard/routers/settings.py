from fastapi import APIRouter, Depends
from dashboard.auth.dependencies import get_current_user, require_guild_manage
from dashboard.auth.csrf import verify_csrf
from storage.database_manager import db_manager
from storage.config_manager import get_guild_config_manager, GuildConfig
from storage.sub_systems.bump_config import SUPPORTED_BOTS
from utils.logger import get_logger

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
}


def _coerce_id(value) -> int:
    """Parse an incoming ID (string/number/None) to an int; 0 means unset."""
    if value in (None, "", 0, "0"):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _serialize(config: GuildConfig) -> dict:
    """Config dict with snowflake IDs as strings ('' when unset)."""
    data = config.to_dict()
    for key in _ID_FIELDS:
        val = data.get(key) or 0
        data[key] = str(val) if val else ""
    return data


@router.get("/guilds/{guild_id}/settings")
async def get_settings(guild_id: int, session: dict = Depends(require_guild_manage)):
    gcm = await get_guild_config_manager(db_manager)
    config = await gcm.get_config(guild_id)
    return _serialize(config)


@router.put("/guilds/{guild_id}/settings")
async def update_settings(
    guild_id: int,
    patch: dict,
    session: dict = Depends(require_guild_manage),
    _csrf: None = Depends(verify_csrf),
):
    gcm = await get_guild_config_manager(db_manager)
    config = await gcm.get_config(guild_id)

    for key, value in patch.items():
        if key not in _ALLOWED_KEYS:
            continue
        if key in _ID_FIELDS:
            setattr(config, key, _coerce_id(value))
        elif key == "enabled_bots":
            bots = value if isinstance(value, list) else []
            setattr(config, key, [str(b) for b in bots if str(b) in SUPPORTED_BOTS])
        elif key == "timers_message":
            setattr(config, key, bool(value))
        elif key == "custom_message":
            setattr(config, key, str(value or ""))

    await gcm.save_config(config)
    return _serialize(config)
