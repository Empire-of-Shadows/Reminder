import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from utils.logger import get_logger

logger = get_logger("AuditLog")

class AuditLogManager:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self._collection = db_manager.get_raw_collection("ImperialReminder", "audit_log")

    async def log(self, guild_id: int, user_id: int, action: str, details: Optional[Dict[str, Any]] = None):
        try:
            entry = {
                "guild_id": guild_id,
                "user_id": user_id,
                "action": action,
                "details": details or {},
                "timestamp": datetime.now(timezone.utc)
            }
            await self._collection.insert_one(entry)
        except Exception as e:
            logger.error(f"Error writing to audit log: {e}")

_audit_log_manager = None

def get_audit_log_manager(db_manager=None):
    global _audit_log_manager
    if _audit_log_manager is None:
        if db_manager is None: raise ValueError("db_manager required")
        _audit_log_manager = AuditLogManager(db_manager)
    return _audit_log_manager
