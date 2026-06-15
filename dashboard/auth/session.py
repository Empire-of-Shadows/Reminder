"""Session CRUD for the shared WebSessions.SharedSessions collection (SSO).

Schema (shared across Host/Codex/Ecom/ImperialReminder/TheDecree + main site):
    token            opaque random Mongo lookup id (token_urlsafe(48))
    user_id          Discord user id (string)
    user_data        Discord /users/@me payload
    guilds           Discord /users/@me/guilds payload (refreshed on staleness)
    access_token     OAuth access token (server-side only; never returned to client)
    refresh_token    OAuth refresh token (rotates on each refresh)
    token_expires_at when the access token expires (UTC datetime, may be None)
    guilds_fetched_at, created_at, last_accessed, expires_at  (UTC datetimes)
    schema_version   2
"""

import asyncio
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from dashboard import db
from dashboard.config import (
    DASHBOARD_CLIENT_ID,
    DASHBOARD_CLIENT_SECRET,
    DISCORD_API_BASE,
    SESSION_MAX_AGE_DAYS,
)
from utils.logger import get_logger

logger = get_logger("dashboard.auth.session")

SESSION_SCHEMA_VERSION = 2

# How long a session's cached guild list is trusted before a transparent refresh
# from Discord (/users/@me/guilds), so the SSO snapshot self-heals without re-login.
GUILDS_REFRESH_TTL_SECONDS = 300

_TOKEN_URL = f"{DISCORD_API_BASE}/oauth2/token"
_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Single-flight locks per session token so concurrent requests don't stampede
# Discord with duplicate refreshes.
_refresh_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def create_session(
    user_data: dict,
    guilds: list[dict],
    access_token: str | None = None,
    refresh_token: str | None = None,
    expires_in: int | None = None,
) -> str:
    """Create a new session and return the opaque session token."""
    token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    token_expires_at = now + timedelta(seconds=int(expires_in)) if expires_in else None
    doc = {
        "token": token,
        "user_id": user_data["id"],
        "user_data": user_data,
        "guilds": guilds,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expires_at": token_expires_at,
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


# --- Guild-list refresh (keeps the SSO snapshot self-healing) ----------------


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_stale(fetched_at: datetime | None, ttl: int = GUILDS_REFRESH_TTL_SECONDS) -> bool:
    fetched_at = _as_utc(fetched_at)
    if fetched_at is None:
        return True
    return (datetime.now(timezone.utc) - fetched_at).total_seconds() >= ttl


async def _refresh_access_token(refresh_token: str) -> dict | None:
    """Exchange a refresh token for a fresh access token (GateKeeper creds).

    Returns the token payload, or None on failure (e.g. the user revoked the app).
    """
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "client_id": DASHBOARD_CLIENT_ID,
                    "client_secret": DASHBOARD_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError as e:
        logger.warning("OAuth token refresh error: %s", e)
        return None
    if resp.status_code != 200:
        logger.info("OAuth token refresh failed: %s", resp.status_code)
        return None
    return resp.json()


async def _backoff(token: str, session: dict, updates: dict | None = None) -> dict:
    """On a failed refresh, persist any token updates and push guilds_fetched_at
    forward (retry in ~60s) so we don't hammer Discord on every request."""
    set_doc = dict(updates or {})
    set_doc["guilds_fetched_at"] = datetime.now(timezone.utc) - timedelta(
        seconds=GUILDS_REFRESH_TTL_SECONDS - 60
    )
    await db.shared_sessions().update_one({"token": token}, {"$set": set_doc})
    session.update(set_doc)
    return session


async def refresh_guilds_if_stale(session: dict) -> dict:
    """Best-effort refresh of the session's cached Discord guild list.

    When the snapshot is older than ``GUILDS_REFRESH_TTL_SECONDS`` and the
    session carries an OAuth access token, re-fetch ``/users/@me/guilds``
    (refreshing the access token first if it expired). Every failure path falls
    back to the cached snapshot — this never raises and never 500s a request.
    """
    token = session.get("token")
    # Legacy/token-less session (e.g. minted before this rollout): nothing to do.
    if not token or not session.get("access_token"):
        return session
    if not _is_stale(session.get("guilds_fetched_at")):
        return session

    async with _refresh_locks[token]:
        # Re-read under the lock — another request may have refreshed already.
        latest = await db.shared_sessions().find_one({"token": token})
        if latest is None:
            return session
        if not _is_stale(latest.get("guilds_fetched_at")):
            session["guilds"] = latest.get("guilds", session.get("guilds"))
            session["guilds_fetched_at"] = latest.get("guilds_fetched_at")
            return session

        access_token = latest.get("access_token")
        refresh_token = latest.get("refresh_token")
        token_expires_at = _as_utc(latest.get("token_expires_at"))
        updates: dict = {}

        # Refresh the access token if it has expired.
        if access_token and token_expires_at and token_expires_at <= datetime.now(timezone.utc):
            if not refresh_token:
                return await _backoff(token, session)
            new_tokens = await _refresh_access_token(refresh_token)
            if not new_tokens:
                return await _backoff(token, session)
            access_token = new_tokens.get("access_token", access_token)
            updates["access_token"] = access_token
            if new_tokens.get("refresh_token"):
                updates["refresh_token"] = new_tokens["refresh_token"]
            if new_tokens.get("expires_in"):
                updates["token_expires_at"] = datetime.now(timezone.utc) + timedelta(
                    seconds=int(new_tokens["expires_in"])
                )

        # Fetch the current guild list.
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(
                    f"{DISCORD_API_BASE}/users/@me/guilds",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError as e:
            logger.warning("Guild refresh error: %s", e)
            return await _backoff(token, session, updates)

        if resp.status_code != 200:
            logger.info("Guild refresh failed: %s", resp.status_code)
            return await _backoff(token, session, updates)

        updates["guilds"] = resp.json()
        updates["guilds_fetched_at"] = datetime.now(timezone.utc)
        await db.shared_sessions().update_one({"token": token}, {"$set": updates})
        session.update(updates)
        return session


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
