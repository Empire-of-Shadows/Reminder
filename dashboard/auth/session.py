"""Session CRUD for the shared WebSessions.SharedSessions collection (SSO).

Schema (locked across Host/Codex/Ecom/ImperialReminder):
    token            opaque random Mongo lookup id (token_urlsafe(48))
    user_id          Discord user id (string)
    user_data        Discord /users/@me payload
    guilds           Discord /users/@me/guilds payload
    guilds_fetched_at, created_at, last_accessed, expires_at  (UTC datetimes)
    schema_version   1
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from dashboard import db
from dashboard.config import SESSION_MAX_AGE_DAYS
from utils.logger import get_logger

logger = get_logger("dashboard.auth.session")

SESSION_SCHEMA_VERSION = 1


async def create_session(user_data: dict, guilds: list[dict]) -> str:
    """Create a new session and return the opaque session token."""
    token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    doc = {
        "token": token,
        "user_id": user_data["id"],
        "user_data": user_data,
        "guilds": guilds,
        "guilds_fetched_at": now,
        "created_at": now,
        "last_accessed": now,
        "expires_at": now + timedelta(days=SESSION_MAX_AGE_DAYS),
        "schema_version": SESSION_SCHEMA_VERSION,
    }
    await db.shared_sessions().insert_one(doc)
    logger.info("Session created user=%s expires=%s", user_data.get("id"), doc["expires_at"].isoformat())
    return token


async def get_session(token: str) -> dict[str, Any] | None:
    """Look up session, slide expiration, return doc or None."""
    doc = await db.shared_sessions().find_one({"token": token})
    if doc is None:
        return None
    now = datetime.now(timezone.utc)
    expires_at = doc.get("expires_at", datetime.min)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        await delete_session(token)
        return None
    # Sliding expiration: refresh expires_at + last_accessed on every hit.
    new_expires = now + timedelta(days=SESSION_MAX_AGE_DAYS)
    await db.shared_sessions().update_one(
        {"token": token},
        {"$set": {"last_accessed": now, "expires_at": new_expires}},
    )
    doc["last_accessed"] = now
    doc["expires_at"] = new_expires
    return doc


async def delete_session(token: str):
    """Delete a session by token."""
    await db.shared_sessions().delete_one({"token": token})


# --- OAuth state (Mongo-backed with TTL) -------------------------------------

OAUTH_STATE_TTL_SECONDS = 600


async def ensure_oauth_state_ttl_index() -> None:
    """Create TTL index on WebSessions.OAuthStates.created_at (10 min)."""
    await db.oauth_states().create_index(
        "created_at",
        expireAfterSeconds=OAUTH_STATE_TTL_SECONDS,
        name="oauth_state_ttl",
    )


async def ensure_session_ttl_index() -> None:
    """Create TTL index on WebSessions.SharedSessions.expires_at."""
    await db.shared_sessions().create_index(
        "expires_at",
        expireAfterSeconds=0,
        name="session_expires_ttl",
    )


async def store_oauth_state(state: str, redirect_url: str) -> None:
    """Persist an OAuth state token bound to its post-login redirect URL."""
    await db.oauth_states().insert_one({
        "state": state,
        "redirect_url": redirect_url,
        "created_at": datetime.now(timezone.utc),
    })


async def consume_oauth_state(state: str) -> str | None:
    """Atomically retrieve + delete an OAuth state. Returns redirect_url or None."""
    doc = await db.oauth_states().find_one_and_delete({"state": state})
    return doc.get("redirect_url") if doc else None
