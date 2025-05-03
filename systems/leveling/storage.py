# systems/leveling/storage.py
import datetime
import math
from typing import Dict, Tuple, List, Any

class LevelingStorage:
    """Handles database operations for the leveling system"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        self.db = system.bot.db
        
        # Collection names
        self.users_collection_name = "levels"
        self.settings_collection_name = "level_settings"
        self.profiles_collection_name = "level_profiles"
    
    async def get_settings(self, guild_id: int) -> Dict:
        """Get guild leveling settings"""
        settings = await self.db[self.settings_collection_name].find_one({"guild_id": guild_id})
        
        if not settings:
            # Create default settings
            settings = {
                "guild_id": guild_id,
                "enabled": True,
                "cooldown": 60,  # Seconds
                "min_xp": 15,
                "max_xp": 25,
                "announce_level_up": True,
                "level_up_channel": None,
                "excluded_channels": [],
                "role_rewards": {},  # level: role_id
                "allow_card_customization": True
            }
            
            await self.db[self.settings_collection_name].insert_one(settings)
        
        return settings
    
    async def get_user_data(self, user_id: int, guild_id: int) -> Dict:
        """Get user's level data"""
        data = await self.db[self.users_collection_name].find_one({
            "user_id": user_id,
            "guild_id": guild_id
        })
        
        if not data:
            # Create new user data
            data = {
                "user_id": user_id,
                "guild_id": guild_id,
                "xp": 0,
                "level": 0,
                "last_message": datetime.datetime.utcnow(),
                "messages": 0
            }
            
            await self.db[self.users_collection_name].insert_one(data)
        
        return data
    
    async def update_user_xp(self, user_id: int, guild_id: int, xp_to_add: int) -> Tuple[int, int, bool]:
        """Update user XP and level
        
        Returns:
            Tuple of (new_xp, new_level, level_up)
        """
        # Get current data
        data = await self.get_user_data(user_id, guild_id)
        
        # Update XP
        new_xp = data["xp"] + xp_to_add
        old_level = data["level"]
        new_level = self.calculate_level(new_xp)
        
        # Check if level up occurred
        level_up = new_level > old_level
        
        # Update in database
        await self.db[self.users_collection_name].update_one(
            {"user_id": user_id, "guild_id": guild_id},
            {"$set": {
                "xp": new_xp,
                "level": new_level,
                "last_message": datetime.datetime.utcnow(),
                "messages": data["messages"] + 1
            }}
        )
        
        return new_xp, new_level, level_up
    
    def calculate_level(self, xp: int) -> int:
        """Calculate level based on XP"""
        # Formula: level = sqrt(xp / 100)
        return math.floor(math.sqrt(xp / 100))
    
    def calculate_xp_for_level(self, level: int) -> int:
        """Calculate XP needed for a specific level"""
        return level * level * 100
    
    async def get_user_profile(self, user_id: int, guild_id: int) -> Dict:
        """Get user's profile customization settings"""
        profile = await self.db[self.profiles_collection_name].find_one({
            "user_id": user_id,
            "guild_id": guild_id
        })
        
        if not profile:
            # Create default profile
            profile = {
                "user_id": user_id,
                "guild_id": guild_id,
                "background_color": "#232527",  # Dark theme
                "progress_bar_color": "#5865F2",  # Discord blue
                "text_color": "#FFFFFF",  # White
                "progress_bar_background": "#3C3F45",  # Darker gray
                "background_image": None,  # No image by default
                "overlay_opacity": 0.7,  # Opacity of color overlay when using background image
            }
            
            await self.db[self.profiles_collection_name].insert_one(profile)
        
        return profile
    
    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict]:
        """Get the top users by XP in a guild"""
        cursor = self.db[self.users_collection_name].find({"guild_id": guild_id})
        cursor = cursor.sort("xp", -1).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    async def get_user_rank(self, user_id: int, guild_id: int) -> int:
        """Get user's rank position in the server"""
        pipeline = [
            {"$match": {"guild_id": guild_id}},
            {"$sort": {"xp": -1}},
            {"$group": {"_id": None, "users": {"$push": "$user_id"}}},
            {"$project": {"rank": {"$indexOfArray": ["$users", user_id]}}}
        ]
        
        result = await self.db[self.users_collection_name].aggregate(pipeline).to_list(length=1)
        
        if not result:
            return 0
            
        # Add 1 because indexOfArray is 0-based
        return result[0]["rank"] + 1
