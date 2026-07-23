"""Audit-log seam - ImperialReminder (bot-owned, NOT vendored).

Thin construction seam over the engine ``storage.services.audit_log.AuditLog``: the
singleton factory keeps the pre-migration ``get_audit_log_manager()`` API so call sites
(``startup/sync.py`` attach, the admin seam's ``audit_log_entry``) are unchanged. The
engine writer accepts arbitrary keyword fields, so the existing
``log(guild_id=..., user_id=..., action=..., details=...)`` calls flow through as-is;
entries gain the engine's Mongo/JSON coercion and a ``created_at`` timestamp that the
registered ``audit_log`` collection's TTL index uses for 365-day retention.
"""

from typing import Optional

from storage.services.audit_log import AuditLog

_audit_log: Optional[AuditLog] = None


def get_audit_log_manager(db_manager=None) -> AuditLog:
    """Get or create the shared engine AuditLog over the registered collection."""
    global _audit_log
    if _audit_log is None:
        if db_manager is None:
            raise ValueError("db_manager required")
        _audit_log = AuditLog(db_manager.get_collection_manager("audit_log"))
    return _audit_log
