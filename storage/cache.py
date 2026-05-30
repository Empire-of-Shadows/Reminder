import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timezone
import discord
from pymongo import UpdateOne
from utils.logger import get_logger

logger = get_logger("GuildCacheManager")

class GuildCacheManager:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self._guilds = db_manager.get_raw_collection("ImperialReminder", "serverdata_guilds")
        self._members = db_manager.get_raw_collection("ImperialReminder", "serverdata_members")
        self._roles = db_manager.get_raw_collection("ImperialReminder", "serverdata_roles")

    async def cache_all(self, guild: discord.Guild):
        """Cache all guild data (info, roles, members)."""
        try:
            logger.info(f"Caching guild {guild.name} ({guild.id})")
            await asyncio.gather(
                self.cache_guild_info(guild),
                self.cache_roles(guild),
                self.cache_members(guild)
            )
        except Exception as e:
            logger.error(f"Error caching guild {guild.id}: {e}")

    async def cache_guild_info(self, guild: discord.Guild):
        data = {
            "id": guild.id,
            "name": guild.name,
            "member_count": guild.member_count,
            "owner_id": guild.owner_id,
            "updated_at": datetime.now(timezone.utc)
        }
        await self._guilds.update_one({"id": guild.id}, {"$set": data}, upsert=True)

    async def cache_roles(self, guild: discord.Guild):
        roles_data = []
        for role in guild.roles:
            roles_data.append(UpdateOne(
                {"guild_id": guild.id, "id": role.id},
                {"$set": {
                    "name": role.name,
                    "position": role.position,
                    "permissions": role.permissions.value,
                    "color": str(role.color)
                }},
                upsert=True
            ))
        if roles_data:
            await self._roles.bulk_write(roles_data, ordered=False)

    async def cache_members(self, guild: discord.Guild):
        # Simplified: Only cache members if they are in the guild
        members_data = []
        for member in guild.members:
            members_data.append(UpdateOne(
                {"guild_id": guild.id, "id": member.id},
                {"$set": {
                    "username": member.name,
                    "display_name": member.display_name,
                    "roles": [r.id for r in member.roles if not r.is_default()],
                    "joined_at": member.joined_at.isoformat() if member.joined_at else None
                }},
                upsert=True
            ))
        if members_data:
            # chunking for large guilds
            for i in range(0, len(members_data), 1000):
                await self._members.bulk_write(members_data[i:i+1000], ordered=False)

def create_cache_manager(db_manager) -> GuildCacheManager:
    return GuildCacheManager(db_manager)

cache_manager: Optional[GuildCacheManager] = None
