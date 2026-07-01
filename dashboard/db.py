"""MongoDB clients for the dashboard service.

Two independent connections (matching TheHost / TheCodex):
- bot data: ImperialReminder's own Mongo via the bot DatabaseManager (MONGO_URI).
  Powers the guild-config routers (storage.config_manager).
- shared sessions: a dedicated client on SHARED_SESSIONS_URI holding
  WebSessions.SharedSessions + WebSessions.OAuthStates, shared with the other
  ecosystem dashboards for cross-subdomain SSO.
"""

from pymongo import AsyncMongoClient

from dashboard.config import SHARED_SESSIONS_URI
from storage.manager import db_manager

_shared_client: AsyncMongoClient | None = None


async def connect():
    """Open the shared-session client and initialize the bot DatabaseManager."""
    global _shared_client
    if not SHARED_SESSIONS_URI:
        raise RuntimeError("SHARED_SESSIONS_URI environment variable is required")
    _shared_client = AsyncMongoClient(SHARED_SESSIONS_URI)
    await _shared_client.admin.command("ping")
    # Bot manager (MONGO_URI) powers the guild-config routers.
    await db_manager.initialize()


async def close():
    global _shared_client
    if _shared_client:
        await _shared_client.close()
        _shared_client = None
    await db_manager.close()


def _get_client() -> AsyncMongoClient:
    """Return the shared-session client (used for the health ping)."""
    if _shared_client is None:
        raise RuntimeError("Shared sessions database not connected - call connect() first")
    return _shared_client


# --- Shared session store accessors (locked names across the ecosystem) ------

def shared_sessions():
    """WebSessions.SharedSessions - cross-subdomain OAuth session storage."""
    return _get_client()["WebSessions"]["SharedSessions"]


def oauth_states():
    """WebSessions.OAuthStates - short-lived OAuth state for CSRF protection.

    TTL-indexed on `created_at` (10 minutes).
    """
    return _get_client()["WebSessions"]["OAuthStates"]
