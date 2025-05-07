# systems/marketplace/storage.py
import datetime
from typing import Dict, List, Optional

class MarketplaceStorage:
    """Storage component for the Marketplace system"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        self.db = system.bot.db
    
    async def get_settings(self, guild_id: int) -> Dict:
        """Get marketplace settings for a guild"""
        settings = await self.db.marketplace_settings.find_one({"guild_id": guild_id})
        
        if not settings:
            # Create default settings
            settings = {
                "guild_id": guild_id,
                "hiring_channel_id": None,
                "forhire_channel_id": None,
                "selling_channel_id": None,
                "approvals_category_id": None,
                "approval_view_roles": [],
                "approval_mod_roles": [],
                "created_at": datetime.datetime.utcnow().isoformat()
            }
            
            await self.db.marketplace_settings.insert_one(settings)
        
        return settings
    
    async def update_settings(self, guild_id: int, updates: Dict) -> bool:
        """Update marketplace settings"""
        result = await self.db.marketplace_settings.update_one(
            {"guild_id": guild_id},
            {"$set": updates}
        )
        
        # Update cache
        if guild_id in self.system.settings_cache:
            self.system.settings_cache[guild_id].update(updates)
        
        return result.modified_count > 0
    
    async def get_post(self, post_id) -> Optional[Dict]:
        """Get a post by ID"""
        from bson.objectid import ObjectId
        try:
            post_object_id = ObjectId(post_id)
            return await self.db.marketplace_posts.find_one({"_id": post_object_id})
        except:
            return None
    
    async def add_post(self, post_data: Dict) -> str:
        """Add a new post"""
        result = await self.db.marketplace_posts.insert_one(post_data)
        return str(result.inserted_id)
    
    async def update_post(self, post_id, updates: Dict) -> bool:
        """Update a post"""
        from bson.objectid import ObjectId
        try:
            post_object_id = ObjectId(post_id)
            result = await self.db.marketplace_posts.update_one(
                {"_id": post_object_id},
                {"$set": updates}
            )
            return result.modified_count > 0
        except:
            return False
    
    async def delete_post(self, post_id) -> bool:
        """Delete a post"""
        from bson.objectid import ObjectId
        try:
            post_object_id = ObjectId(post_id)
            result = await self.db.marketplace_posts.delete_one({"_id": post_object_id})
            return result.deleted_count > 0
        except:
            return False
    
    async def get_user_posts(self, guild_id: int, user_id: int) -> List[Dict]:
        """Get all posts by a user in a guild"""
        cursor = self.db.marketplace_posts.find({
            "guild_id": guild_id,
            "user_id": user_id
        }).sort("created_at", -1)
        
        return await cursor.to_list(length=None)
    
    async def get_pending_posts(self, guild_id: int) -> List[Dict]:
        """Get all pending posts in a guild"""
        cursor = self.db.marketplace_posts.find({
            "guild_id": guild_id,
            "status": "pending"
        }).sort("created_at", 1)
        
        return await cursor.to_list(length=None)
    
    async def schedule_deletion(self, channel_id: int, guild_id: int, hours: float = 24) -> bool:
        """Schedule a channel for deletion"""
        deletion_time = datetime.datetime.utcnow() + datetime.timedelta(hours=hours)
        
        await self.db.scheduled_deletions.insert_one({
            "channel_id": channel_id,
            "guild_id": guild_id,
            "deletion_time": deletion_time
        })
        
        return True
    
    async def get_scheduled_deletions(self) -> List[Dict]:
        """Get all scheduled deletions"""
        current_time = datetime.datetime.utcnow()
        
        cursor = self.db.scheduled_deletions.find({
            "deletion_time": {"$lte": current_time}
        })
        
        return await cursor.to_list(length=None)
    
    async def remove_scheduled_deletion(self, channel_id: int) -> bool:
        """Remove a scheduled deletion"""
        result = await self.db.scheduled_deletions.delete_one({"channel_id": channel_id})
        return result.deleted_count > 0
