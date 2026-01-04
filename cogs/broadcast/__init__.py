"""
Broadcast System Package
Guild-specific DM broadcast system with anti-spam protection
"""

from .storage import BroadcastStorage
from .validator import validate_broadcast_content, validate_broadcast_name
from .config import (
    MIN_RECURRING_INTERVAL_MINUTES,
    MAX_ACTIVE_BROADCASTS_PER_GUILD,
    DM_SEND_DELAY_SECONDS
)

__all__ = [
    "BroadcastStorage",
    "validate_broadcast_content",
    "validate_broadcast_name",
    "MIN_RECURRING_INTERVAL_MINUTES",
    "MAX_ACTIVE_BROADCASTS_PER_GUILD",
    "DM_SEND_DELAY_SECONDS"
]
