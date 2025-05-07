# systems/moderation/filter/whitelist.py
import discord
import re
import datetime
from typing import Dict, List, Set, Any

class WhitelistFilter:
    """Handles whitelist filtering for content moderation"""
    
    def __init__(self, filter_system):
        self.filter_system = filter_system
        self.system = filter_system.system
        self.bot = filter_system.system.bot
        
        # Cache for whitelist items
        self.cache = {}  # Guild ID -> {item: match_type}
    
    async def initialize(self):
        """Initialize the whitelist filter"""
        # Load whitelist for all guilds
        await self.load_all()
    
    async def load_all(self):
        """Load all whitelists"""
        # Load whitelists
        async for doc in self.bot.db.whitelist.find({}):
            guild_id = doc["guild_id"]
            if guild_id not in self.cache:
                self.cache[guild_id] = {}
                
            self.cache[guild_id][doc["item"]] = doc["match_type"]
        
        print(f"Loaded whitelists for {len(self.cache)} guilds")
    
    async def add_item(self, guild_id: int, item: str, match_type: str, reason: str = None, added_by: int = None):
        """Add an item to the whitelist"""
        # Remove from blacklist first
        await self.filter_system.blacklist.remove_item(guild_id, item)
        
        # Add to whitelist
        await self.bot.db.whitelist.update_one(
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
        """Remove an item from the whitelist"""
        # Remove from database
        result = await self.bot.db.whitelist.delete_one({"guild_id": guild_id, "item": item})
        
        # Update cache
        if guild_id in self.cache and item in self.cache[guild_id]:
            del self.cache[guild_id][item]
        
        return result.deleted_count > 0
    
    async def get_items(self, guild_id: int, match_type: str = None):
        """Get whitelisted items for a guild"""
        # Get from database
        query = {"guild_id": guild_id}
        if match_type and match_type != "all":
            query["match_type"] = match_type
            
        cursor = self.bot.db.whitelist.find(query)
        return await cursor.to_list(length=None)
    
    def check(self, content: str, guild_id: int):
        """Check if content matches any whitelisted item"""
        # Ensure guild exists in cache
        if guild_id not in self.cache:
            return None
            
        content = content.lower()
        
        # Check each item
        for item, match_type in self.cache[guild_id].items():
            if self.filter_system.matches(content, item, match_type):
                return item
                
        return None
