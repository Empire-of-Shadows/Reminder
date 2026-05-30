import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from utils.logger import get_logger

logger = get_logger("PremiumManager")

class PremiumManager:
    """Manager for premium features using the unified DatabaseManager"""

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self._codes = None
        self._entitlements = None
        self._initialized = False

    async def initialize(self):
        """Initialize collection managers from db_manager"""
        if self._initialized:
            return
        
        self._codes = self.db_manager.premium_codes
        self._entitlements = self.db_manager.premium_entitlements
        self._initialized = True
        logger.info("PremiumManager initialized")

    async def get_code(self, code: str) -> Optional[Dict[str, Any]]:
        return await self._codes.find_one({"code": code})

    async def link_code_to_guild(self, code: str, guild_id: int) -> bool:
        return await self._codes.update_one(
            {"code": code},
            {"$set": {"linked_guild": str(guild_id), "activated_at": datetime.now(timezone.utc)}}
        )

    async def get_user_entitlements(self, user_id: int) -> List[Dict[str, Any]]:
        return await self._entitlements.find_many({"user_id": str(user_id)})

_premium_manager: Optional[PremiumManager] = None

async def get_premium_manager(db_manager=None) -> PremiumManager:
    global _premium_manager
    if _premium_manager is None:
        if db_manager is None:
            raise ValueError("db_manager is required")
        _premium_manager = PremiumManager(db_manager)
        await _premium_manager.initialize()
    return _premium_manager
