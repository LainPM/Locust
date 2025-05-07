# systems/moderation/filter/blacklist.py
import discord
import re
import datetime
from typing import Dict, List, Set, Any

class BlacklistFilter:
    """Handles blacklist filtering for content moderation"""
    
    def __init__(self, filter_system):
        self.filter_system = filter_system
        self.system = filter_system.system
        self.bot = filter_system.system.bot
        
        # Cache for blacklist items
        self.cache = {}  # Guild ID -> {item: match_type}
    
    async def initialize(self):
        """Initialize the blacklist filter"""
        # Load blacklist for all guilds
        await self.load_all()
    
    async def load_all(self):
        """Load all blacklists"""
        # Load blacklists
        async for doc in self.bot.db.blacklist.find({}):
            guild_id = doc["guild_id"]
            if guild_id not in self.cache:
                self.cache[guild_id] = {}
                
            self.cache[guild_id][doc["item"]] = doc["match_type"]
        
        print(f"Loaded blacklists for {len(self.cache)} guilds")
    
    async def add_item(self, guild_id: int, item: str, match_type: str, reason: str = None, added_by: int = None):
        """Add an item to the blacklist"""
        # Remove from whitelist first
        await self.filter_system.whitelist.remove_item(guild_id, item)
        
        # Add to blacklist
        await self.bot.db.blacklist.update_one(
            {"guild_id": guild_id, "item": item},
            {"$set": {
                "match_type": match_type,
                "reason": reason,
                "added_by": added_by,
                "added_at": datetime.datetime.utcnow().isoformat()
            }},
            upsert=True
        )
        
        # Update cache
        if guild_id not in self.cache:
            self.cache[guild_id] = {}
        self.cache[guild_id][item] = match_type
        
        return True
    
    async def remove_item(self, guild_id: int, item: str):
        """Remove an item from the blacklist"""
        # Remove from database
        result = await self.bot.db.blacklist.delete_one({"guild_id": guild_id, "item": item})
        
        # Update cache
        if guild_id in self.cache and item in self.cache[guild_id]:
            del self.cache[guild_id][item]
        
        return result.deleted_count > 0
    
    async def get_items(self, guild_id: int, match_type: str = None):
        """Get blacklisted items for a guild"""
        # Get from database
        query = {"guild_id": guild_id}
        if match_type and match_type != "all":
            query["match_type"] = match_type
            
        cursor = self.bot.db.blacklist.find(query)
        return await cursor.to_list(length=None)
    
    def check(self, content: str, guild_id: int):
        """Check if content matches any blacklisted item"""
        # Ensure guild exists in cache
        if guild_id not in self.cache:
            return None
            
        content = content.lower()
        
        # Check each item
        for item, match_type in self.cache[guild_id].items():
            if self.filter_system.matches(content, item, match_type):
                return item
                
        return None
