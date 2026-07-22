"""storage_engine bindings - ImperialReminder.

The single integration point between the vendored storage engine and this bot's
environment. The seam imports these names; everything else under ``storage/`` (except
this ``settings/`` package and the bot-owned domain modules ``config_manager.py``,
``audit_log.py``, ``setup_gatekeeper.py``, ``premium_manager.py``, ``sub_systems/``)
is vendored engine code - do not edit it there.

Template: ``EmpireSystems/Settings/storage/bindings_reference.py``.
Reference adoption: ``FunEngagement/TheDecree/storage/settings/bindings.py``.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from utils.env import load_project_env

# Absolute import against the vendored ``storage`` package (this file lives one level
# deeper, in ``storage/settings/``).
from storage.cache.backend import CacheBackend
from storage.cache.local import LocalCache

# ImperialReminder loads MONGO_URI from docker/.env via its project env loader (not
# plain python-dotenv), so do it here before reading the URI. The entrypoint's own
# docker/.env + .env.local load still runs first when booting via Reminder.py.
load_project_env()


# -- Connections (ENGINE CONTRACT: MONGO_URIS) ----------------------------------
# ImperialReminder uses a single primary connection (every collection in the
# registry is connection='primary').
MONGO_URIS: Dict[str, Optional[str]] = {
    "primary": os.getenv("MONGO_URI"),
}


# -- Cache defaults (ENGINE CONTRACT: CACHE_DEFAULTS) ---------------------------
CACHE_DEFAULTS: Dict[str, Any] = {
    "max_size": 5000,
    "default_ttl": 300,
}


# -- Cache backend factory (ENGINE CONTRACT: build_cache) -----------------------
def build_cache() -> CacheBackend:
    """Return the cache backend this bot uses (in-process LocalCache)."""
    return LocalCache(**CACHE_DEFAULTS)


# -- Change-stream coherency (ENGINE CONTRACT: WATCHED_COLLECTIONS) -------------
# Empty = TTL-only coherency (no replica set required). The dashboard is an external
# writer to ``settings_guild_data``, but its writes are surgical dotted $set and the
# bot reads guild config with a short 30s cache TTL (see storage/config_manager.py),
# matching the pre-migration staleness bound without requiring change streams.
WATCHED_COLLECTIONS: List[str] = []


# -- Audit hook (ENGINE CONTRACT: audit_storage_event) - OPTIONAL ---------------
async def audit_storage_event(
    *,
    collection: str,
    action: str,
    query: dict,
    actor_id: Optional[int] = None,
) -> None:
    """No-op: ImperialReminder audits through the engine AuditLog service
    (ImperialReminder.AuditLog via storage/audit_log.py)."""
    return None
