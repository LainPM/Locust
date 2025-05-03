# systems/starboard/storage.py
import datetime
from typing import Dict, List, Any, Optional

class StarboardStorage:
    """Storage component for the Starboard system"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        self.db = system.bot.db
        
        # Collection names
        self.settings_collection_name = "starboard_settings"
        self.posts_collection_name = "starboard_posts"
    
    async def get_settings(self, guild_id: int) -> Dict:
        """Get guild starboard settings"""
        settings = await self.db[self.settings_collection_name].find_one({"guild_id": guild_id})
        
        if not settings:
            # Create default settings
            settings = {
                "guild_id": guild_id,
                "enabled": False,
                "featured_channel_id": None,
                "showcase_channels": [],
                "threshold": 3,
                "star_emoji": "⭐",
                "attachments_only": False,
                "auto_threads": False,
                "bot_react": True,
                "created_at": datetime.datetime.now()
            }
            
            await self.db[self.settings_collection_name].insert_one(settings)
        
        return settings
    
    async def update_settings(self, guild_id: int, updates: Dict) -> bool:
        """Update guild settings"""
        result = await self.db[self.settings_collection_name].update_one(
            {"guild_id": guild_id},
            {"$set": updates}
        )
        
        # Update cache
        if guild_id in self.system.settings_cache:
            self.system.settings_cache[guild_id].update(updates)
        
        return result.modified_count > 0
    
    async def add_post(self, post_data: Dict) -> str:
        """Add a new post to the database"""
        result = await self.db[self.posts_collection_name].insert_one(post_data)
        return str(result.inserted_id)
    
    async def get_post(self, guild_id: int, channel_id: int, message_id: int) -> Optional[Dict]:
        """Get a post by guild, channel, and message ID"""
        return await self.db[self.posts_collection_name].find_one({
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": message_id
        })
    
    async def update_post_star_count(self, post_id, star_count: int) -> bool:
        """Update the star count for a post"""
        result = await self.db[self.posts_collection_name].update_one(
            {"_id": post_id},
            {"$set": {"star_count": star_count}}
        )
        return result.modified_count > 0
    
    async def mark_post_featured(self, post_id, featured_message_id: int) -> bool:
        """Mark a post as featured"""
        result = await self.db[self.posts_collection_name].update_one(
            {"_id": post_id},
            {"$set": {
                "featured": True,
                "featured_message_id": featured_message_id,
                "featured_at": datetime.datetime.now()
            }}
        )
        return result.modified_count > 0
    
    async def unmark_post_featured(self, post_id) -> bool:
        """Unmark a post as featured"""
        result = await self.db[self.posts_collection_name].update_one(
            {"_id": post_id},
            {"$set": {
                "featured": False,
                "featured_message_id": None
            }}
        )
        return result.modified_count > 0
    
    async def delete_post(self, post_id) -> bool:
        """Delete a post"""
        result = await self.db[self.posts_collection_name].delete_one({"_id": post_id})
        return result.deleted_count > 0
    
    async def get_pending_posts(self, guild_id: int, threshold: int) -> List[Dict]:
        """Get posts that have reached the threshold but aren't featured yet"""
        cursor = self.db[self.posts_collection_name].find({
            "guild_id": guild_id,
            "featured": False,
            "star_count": {"$gte": threshold}
        })
        
        return await cursor.to_list(length=None)
    
    async def get_featured_posts(self, guild_id: int) -> List[Dict]:
        """Get all featured posts for a guild"""
        cursor = self.db[self.posts_collection_name].find({
            "guild_id": guild_id,
            "featured": True
        })
        
        return await cursor.to_list(length=None)
