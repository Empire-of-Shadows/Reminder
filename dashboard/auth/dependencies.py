from fastapi import Cookie, Depends, HTTPException, Request
from dashboard._engine.activity import record_actor
from dashboard._engine.auth.session import get_session, refresh_guilds_if_stale
from dashboard._engine.auth.signing import unsign_token
from dashboard.config import SESSION_COOKIE_NAME, MANAGE_GUILD_PERMISSION

async def get_current_user(
    request: Request,
    eos_session: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> dict:
    if not eos_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session_id = unsign_token(eos_session)
    if session_id is None:
        raise HTTPException(status_code=401, detail="Invalid session signature")
    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Session expired")
    # Keep the cached guild list self-healing (best-effort; never raises).
    session = await refresh_guilds_if_stale(session)
    # Name the actor so the activity log records a person, not just an IP.
    record_actor(request, session)
    return session

def user_can_manage_guild(session: dict, guild_id: str) -> bool:
    for guild in session.get("guilds", []):
        if str(guild["id"]) == str(guild_id):
            perms = int(guild.get("permissions", 0))
            return (perms & MANAGE_GUILD_PERMISSION) == MANAGE_GUILD_PERMISSION
    return False

async def require_guild_manage(
    guild_id: str,
    session: dict = Depends(get_current_user),
) -> dict:
    if not user_can_manage_guild(session, guild_id):
        raise HTTPException(status_code=403, detail="No permission")
    return session
