"""User-scoped data service - export and erasure for a single Discord account.

ImperialReminder tracks *servers*, not members: there is no per-user profile,
message log, or activity record anywhere in its collections. Only two kinds of
document can be tied to a person:

* ``audit_log`` entries naming them as the actor of a settings change (written
  as ``user_id`` by the admin panel seam, as ``actor_id`` by the premium cog).
* ``entitlements`` records they granted (``granted_by``) or that were granted
  to them directly (``scope="user"``).

Export dumps both. Erasure redacts the actor identity from audit entries rather
than dropping them: the entry is the *server's* record that a setting changed,
and letting an admin wipe their own trail from a public web UI would gut the
audit log. Entitlements are grant records and are left intact, mirroring
TheHost, which keeps premium on delete.

Both id fields are written inconsistently across the codebase (int from the
admin seam, str from the premium cog), so every filter matches both forms.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from storage.settings.collections import db_manager
from storage.log import get_logger

logger = get_logger("dashboard.services.user_data")

AUDIT_COLLECTION = "audit_log"
ENTITLEMENTS_COLLECTION = "entitlements"

REDACTED_NAME = "[redacted]"


def _both_forms(value: str) -> list[Any]:
    """The int and str spellings of a snowflake, for filters that must match both."""
    forms: list[Any] = [str(value)]
    try:
        forms.append(int(value))
    except (TypeError, ValueError):
        pass
    return forms


def _actor_filter(user_id: str) -> dict:
    forms = _both_forms(user_id)
    return {"$or": [{"user_id": {"$in": forms}}, {"actor_id": {"$in": forms}}]}


def _guild_clause(guild_id: str) -> dict:
    return {"guild_id": {"$in": _both_forms(guild_id)}}


def _audit_filter(user_id: str, guild_id: str | None) -> dict:
    if guild_id is None:
        return _actor_filter(user_id)
    return {"$and": [_actor_filter(user_id), _guild_clause(guild_id)]}


def _entitlement_filter(user_id: str, guild_id: str | None) -> dict:
    forms = _both_forms(user_id)
    mine = {
        "$or": [
            {"granted_by": {"$in": forms}},
            {"scope": "user", "scope_id": {"$in": forms}},
        ]
    }
    if guild_id is None:
        return mine
    return {"$and": [mine, {"scope": "guild", "scope_id": str(guild_id)}]}


def _audit():
    return db_manager.get_collection_manager(AUDIT_COLLECTION)


def _entitlements():
    return db_manager.get_collection_manager(ENTITLEMENTS_COLLECTION)


def _serializable(doc: dict) -> dict:
    """Drop Mongo's ``_id`` and hand back plain values (json dumps with default=str
    finishes the job for datetimes)."""
    return {k: v for k, v in doc.items() if k != "_id"}


async def guild_ids_with_data(user_id: str) -> set[str]:
    """Guild ids where this user has any stored record. Powers the scope picker."""
    ids: set[str] = set()
    try:
        rows = await _audit().aggregate([
            {"$match": _actor_filter(user_id)},
            {"$group": {"_id": "$guild_id"}},
        ])
        ids |= {str(r["_id"]) for r in rows if r.get("_id") is not None}
    except Exception:
        logger.warning("audit guild scan failed for user %s", user_id, exc_info=True)
    try:
        rows = await _entitlements().aggregate([
            {"$match": {**_entitlement_filter(user_id, None), "scope": "guild"}},
            {"$group": {"_id": "$scope_id"}},
        ])
        ids |= {str(r["_id"]) for r in rows if r.get("_id") is not None}
    except Exception:
        logger.warning("entitlement guild scan failed for user %s", user_id, exc_info=True)
    return ids


async def fetch_audit_entries(user_id: str, guild_id: str | None) -> list[dict]:
    docs = await _audit().find_many(
        _audit_filter(user_id, guild_id),
        sort=[("created_at", -1)],
    )
    return [_serializable(d) for d in docs]


async def fetch_entitlements(user_id: str, guild_id: str | None) -> list[dict]:
    docs = await _entitlements().find_many(_entitlement_filter(user_id, guild_id))
    return [_serializable(d) for d in docs]


async def export_all(user_id: str, guild_id: str | None = None) -> dict:
    """Everything ImperialReminder holds against this account, optionally one server."""
    return {
        "service": "ImperialReminder",
        "exported_at": datetime.now(timezone.utc),
        "user_id": str(user_id),
        "guild_id": str(guild_id) if guild_id is not None else None,
        "note": (
            "ImperialReminder stores no per-member tracking data. These are the only "
            "records tied to your Discord account."
        ),
        "audit_log_entries": await fetch_audit_entries(user_id, guild_id),
        "premium_entitlements": await fetch_entitlements(user_id, guild_id),
    }


async def erase_all(user_id: str, guild_id: str | None = None) -> dict[str, int]:
    """Redact this user's identity from their audit entries.

    The change record survives (servers rely on it); the actor's Discord id and
    name do not. Returns per-collection counts, keyed like TheHost's delete.
    """
    audit = _audit()
    matches = await audit.find_many(_audit_filter(user_id, guild_id), projection={"_id": 1})
    ids = [d["_id"] for d in matches]
    if not ids:
        return {"audit_log_entries": 0}

    await audit.update_many(
        {"_id": {"$in": ids}},
        {"$set": {"redacted_at": datetime.now(timezone.utc)}},
    )
    # Only touch the identity fields a given entry actually carries, so redaction
    # never invents keys on entries that were written by the other code path.
    for field, value in (
        ("user_id", None),
        ("actor_id", None),
        ("actor_name", REDACTED_NAME),
        ("details.actor_name", REDACTED_NAME),
    ):
        await audit.update_many(
            {"_id": {"$in": ids}, field: {"$exists": True}},
            {"$set": {field: value}},
        )
    return {"audit_log_entries": len(ids)}
