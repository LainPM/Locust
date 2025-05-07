# systems/leveling/storage.py
import logging
import datetime
from typing import Dict, List, Any, Optional, Union
import math

class LevelingStorage:
    """Storage handler for the leveling system"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        self.logger = logging.getLogger('axis_bot.systems.leveling.storage')
        self.db = self.bot.db_manager
        
        # Define collection names
        self.users_collection = "leveling_users"
        self.settings_collection = "leveling_settings"
        self.rewards_collection = "leveling_rewards"
        
        # Collection prefixes based on system name
        self.system_name = "leveling"
        
        # Schema versions
        self.schema_versions = {
            self.users_collection: 2,
            self.settings_collection: 1,
            self.rewards_collection: 1
        }
    
    async def initialize(self) -> bool:
        """Initialize storage (create collections, indexes, etc.)"""
        try:
            self.logger.info("Initializing leveling system storage")
            
            # Check schema versions
            for collection in self.schema_versions:
                await self.db.check_schema_version(collection)
            
            # Create necessary indexes
            await self.create_indexes()
            
            self.logger.info("Leveling system storage initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error initializing leveling storage: {str(e)}", exc_info=True)
            return False
    
    async def create_indexes(self) -> bool:
        """Create necessary indexes for efficient queries"""
        try:
            # Define indexes for each collection
            indexes = {
                self.users_collection: [
                    # Index for looking up a specific user in a guild
                    {
                        "keys": {"guild_id": 1, "user_id": 1},
                        "unique": True,
                        "name": "user_lookup_index"
                    },
                    # Index for leaderboard queries
                    {
                        "keys": {"guild_id": 1, "xp": -1},
                        "name": "leaderboard_index"
                    },
                    # Index for level-based queries
                    {
                        "keys": {"guild_id": 1, "level": -1},
                        "name": "level_index"
                    }
                ],
                self.settings_collection: [
                    # Index for guild settings
                    {
                        "keys": {"guild_id": 1},
                        "unique": True,
                        "name": "guild_settings_index"
                    }
                ],
                self.rewards_collection: [
                    # Index for finding rewards by guild and level
                    {
                        "keys": {"guild_id": 1, "level": 1},
                        "unique": True,
                        "name": "reward_lookup_index"
                    },
                    # Index for finding all rewards in a guild
                    {
                        "keys": {"guild_id": 1},
                        "name": "guild_rewards_index"
                    }
                ]
            }
            
            # Create all indexes
            await self.db.ensure_system_indexes(self.system_name, indexes)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error creating indexes: {str(e)}", exc_info=True)
            return False
    
    async def get_user_data(self, guild_id: int, user_id: int) -> Dict[str, Any]:
        """Get user's level data from database"""
        data = await self.db.find_one(
            self.users_collection, 
            {"guild_id": guild_id, "user_id": user_id}
        )
        
        if not data:
            # Create new user data if not exists
            data = {
                "user_id": user_id,
                "guild_id": guild_id,
                "xp": 0,
                "level": 0,
                "messages": 0,
                "messages_count": 0,
                "last_message": datetime.datetime.utcnow(),
                "created_at": datetime.datetime.utcnow(),
                "updated_at": datetime.datetime.utcnow()
            }
            
            try:
                await self.db.insert_one(self.users_collection, data)
                self.logger.debug(f"Created new user data for {user_id} in guild {guild_id}")
            except Exception as e:
                self.logger.error(f"Error creating user data: {str(e)}", exc_info=True)
        
        return data
    
    async def update_user_xp(self, guild_id: int, user_id: int, xp_to_add: int) -> Dict[str, Any]:
        """Update user's XP and level"""
        # Get current user data
        user_data = await self.get_user_data(guild_id, user_id)
        
        # Calculate new XP and level
        new_xp = user_data["xp"] + xp_to_add
        new_level = self.calculate_level(new_xp)
        
        # Check if level up occurred
        level_up = new_level > user_data["level"]
        
        # Prepare update data
        update_data = {
            "xp": new_xp,
            "level": new_level,
            "last_message": datetime.datetime.utcnow(),
            "messages": user_data["messages"] + 1,
            "messages_count": user_data["messages_count"] + 1
        }
        
        # Update in database
        try:
            await self.db.update_one(
                self.users_collection,
                {"guild_id": guild_id, "user_id": user_id},
                {"$set": update_data}
            )
            
            # Return updated data with level up flag
            return {
                **user_data,
                **update_data,
                "level_up": level_up,
                "old_level": user_data["level"]
            }
        except Exception as e:
            self.logger.error(f"Error updating user XP: {str(e)}", exc_info=True)
            return user_data
    
    def calculate_level(self, xp: int) -> int:
        """Calculate level based on XP"""
        # Formula: level = sqrt(xp / 100)
        return math.floor(math.sqrt(xp / 100))
    
    def calculate_xp_for_level(self, level: int) -> int:
        """Calculate XP needed for a specific level"""
        return level * level * 100
    
    def calculate_progress(self, xp: int, level: int) -> float:
        """Calculate progress to next level (0-100%)"""
        current_level_xp = self.calculate_xp_for_level(level)
        next_level_xp = self.calculate_xp_for_level(level + 1)
        
        if next_level_xp - current_level_xp == 0:
            return 100  # Avoid division by zero
            
        progress = ((xp - current_level_xp) / (next_level_xp - current_level_xp)) * 100
        return min(100, max(0, progress))  # Ensure between 0-100
    
    async def get_guild_settings(self, guild_id: int) -> Dict[str, Any]:
        """Get level settings for a guild"""
        settings = await self.db.find_one(
            self.settings_collection, 
            {"guild_id": guild_id}
        )
        
        if not settings:
            # Create default settings
            settings = {
                "guild_id": guild_id,
                "enabled": True,
                "cooldown": 60,  # Seconds between XP gain
                "min_xp": 15,
                "max_xp": 25,
                "announce_level_up": True,
                "level_up_channel": None,
                "excluded_channels": [],
                "role_rewards": {},  # level: role_id
                "allow_card_customization": True,
                "xp_multipliers": {},  # role_id: multiplier
                "created_at": datetime.datetime.utcnow(),
                "updated_at": datetime.datetime.utcnow()
            }
            
            try:
                await self.db.insert_one(self.settings_collection, settings)
                self.logger.info(f"Created default level settings for guild {guild_id}")
            except Exception as e:
                self.logger.error(f"Error creating guild settings: {str(e)}", exc_info=True)
        
        return settings
    
    async def update_guild_settings(self, guild_id: int, settings: Dict[str, Any]) -> bool:
        """Update guild settings"""
        # Add updated timestamp
        settings["updated_at"] = datetime.datetime.utcnow()
        
        try:
            await self.db.update_one(
                self.settings_collection,
                {"guild_id": guild_id},
                {"$set": settings}
            )
            
            self.logger.info(f"Updated level settings for guild {guild_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error updating guild settings: {str(e)}", exc_info=True)
            return False
    
    async def get_leaderboard(self, guild_id: int, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Get the top users by XP in a guild"""
        try:
            leaderboard = await self.db.find(
                self.users_collection,
                {"guild_id": guild_id},
                sort=[("xp", -1)],
                skip=offset,
                limit=limit
            )
            
            return leaderboard
        except Exception as e:
            self.logger.error(f"Error getting leaderboard: {str(e)}", exc_info=True)
            return []
    
    async def get_user_rank(self, guild_id: int, user_id: int) -> int:
        """Get user's rank position in the server"""
        try:
            # Use aggregation for efficient rank calculation
            pipeline = [
                {"$match": {"guild_id": guild_id}},
                {"$sort": {"xp": -1}},
                {"$group": {"_id": None, "users": {"$push": "$user_id"}}},
                {"$project": {"rank": {"$indexOfArray": ["$users", user_id]}}}
            ]
            
            result = await self.db.aggregate(self.users_collection, pipeline)
            
            if not result:
                return 0
                
            # Add 1 because indexOfArray is 0-based
            return result[0]["rank"] + 1 if result[0]["rank"] >= 0 else 0
        except Exception as e:
            self.logger.error(f"Error getting user rank: {str(e)}", exc_info=True)
            return 0
    
    async def reset_user(self, guild_id: int, user_id: int) -> bool:
        """Reset a user's XP and level"""
        try:
            # Get current data for backup
            user_data = await self.get_user_data(guild_id, user_id)
            
            # Create a backup record
            backup = {
                "user_id": user_id,
                "guild_id": guild_id,
                "previous_xp": user_data.get("xp", 0),
                "previous_level": user_data.get("level", 0),
                "reset_at": datetime.datetime.utcnow(),
                "reset_reason": "admin_command"
            }
            
            # Insert backup record
            await self.db.insert_one("leveling_resets", backup)
            
            # Reset user data
            reset_data = {
                "xp": 0,
                "level": 0,
                "messages": user_data.get("messages", 0),  # Keep message count
                "reset_count": user_data.get("reset_count", 0) + 1
            }
            
            await self.db.update_one(
                self.users_collection,
                {"guild_id": guild_id, "user_id": user_id},
                {"$set": reset_data}
            )
            
            self.logger.info(f"Reset user {user_id} in guild {guild_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error resetting user: {str(e)}", exc_info=True)
            return False
    
    async def get_role_rewards(self, guild_id: int) -> Dict[str, int]:
        """Get role rewards for a guild"""
        try:
            settings = await self.get_guild_settings(guild_id)
            return settings.get("role_rewards", {})
        except Exception as e:
            self.logger.error(f"Error getting role rewards: {str(e)}", exc_info=True)
            return {}
    
    async def set_role_reward(self, guild_id: int, level: int, role_id: int) -> bool:
        """Set a role reward for a specific level"""
        try:
            # Convert to strings for MongoDB compatibility
            level_str = str(level)
            role_id_str = str(role_id)
            
            # Get current settings
            settings = await self.get_guild_settings(guild_id)
            
            # Update role rewards
            role_rewards = settings.get("role_rewards", {})
            role_rewards[level_str] = role_id_str
            
            # Update settings
            settings["role_rewards"] = role_rewards
            await self.update_guild_settings(guild_id, settings)
            
            self.logger.info(f"Set role reward for level {level} in guild {guild_id}: role {role_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error setting role reward: {str(e)}", exc_info=True)
            return False
    
    async def remove_role_reward(self, guild_id: int, level: int) -> bool:
        """Remove a role reward for a specific level"""
        try:
            # Convert to string for MongoDB compatibility
            level_str = str(level)
            
            # Get current settings
            settings = await self.get_guild_settings(guild_id)
            
            # Update role rewards
            role_rewards = settings.get("role_rewards", {})
            if level_str in role_rewards:
                del role_rewards[level_str]
                
                # Update settings
                settings["role_rewards"] = role_rewards
                await self.update_guild_settings(guild_id, settings)
                
                self.logger.info(f"Removed role reward for level {level} in guild {guild_id}")
                return True
            else:
                # No reward found for this level
                return False
        except Exception as e:
            self.logger.error(f"Error removing role reward: {str(e)}", exc_info=True)
            return False
    
    async def get_user_profile(self, guild_id: int, user_id: int) -> Dict[str, Any]:
        """Get user's profile customization settings"""
        try:
            profile = await self.db.find_one(
                "leveling_profiles",
                {"user_id": user_id, "guild_id": guild_id}
            )
            
            if not profile:
                # Create default profile
                profile = {
                    "user_id": user_id,
                    "guild_id": guild_id,
                    "background_color": "#232527",
                    "progress_bar_color": "#5865F2",
                    "text_color": "#FFFFFF",
                    "progress_bar_background": "#3C3F45",
                    "background_image": None,
                    "overlay_opacity": 0.7,
                    "created_at": datetime.datetime.utcnow(),
                    "updated_at": datetime.datetime.utcnow()
                }
                
                await self.db.insert_one("leveling_profiles", profile)
                self.logger.debug(f"Created default profile for user {user_id} in guild {guild_id}")
            
            return profile
        except Exception as e:
            self.logger.error(f"Error getting user profile: {str(e)}", exc_info=True)
            
            # Return default profile on error
            return {
                "user_id": user_id,
                "guild_id": guild_id,
                "background_color": "#232527",
                "progress_bar_color": "#5865F2",
                "text_color": "#FFFFFF",
                "progress_bar_background": "#3C3F45",
                "background_image": None,
                "overlay_opacity": 0.7
            }
    
    async def update_user_profile(self, guild_id: int, user_id: int, profile_data: Dict[str, Any]) -> bool:
        """Update user's profile customization settings"""
        try:
            # Add updated timestamp
            profile_data["updated_at"] = datetime.datetime.utcnow()
            
            await self.db.update_one(
                "leveling_profiles",
                {"user_id": user_id, "guild_id": guild_id},
                {"$set": profile_data},
                upsert=True
            )
            
            self.logger.debug(f"Updated profile for user {user_id} in guild {guild_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error updating user profile: {str(e)}", exc_info=True)
            return False
    
    async def backup_guild_data(self, guild_id: int) -> bool:
        """Backup all leveling data for a guild"""
        try:
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Backup users collection (filtered by guild)
            users_backup = f"backup_{timestamp}_guild_{guild_id}"
            
            # Get all users for this guild
            users = await self.db.find(self.users_collection, {"guild_id": guild_id})
            
            if users:
                # Create backup collection
                backup_collection = f"{self.users_collection}_backup_{users_backup}"
                
                # Remove _id to avoid duplicates
                for user in users:
                    if '_id' in user:
                        user['original_id'] = user['_id']
                        del user['_id']
                
                # Insert into backup collection
                await self.db.insert_many(backup_collection, users)
                
                # Also backup settings and profiles
                await self.db.backup_collection(self.settings_collection)
                await self.db.backup_collection("leveling_profiles")
                
                self.logger.info(f"Backed up leveling data for guild {guild_id}: {len(users)} users")
                return True
            else:
                self.logger.warning(f"No users found for guild {guild_id}, skipping backup")
                return False
        except Exception as e:
            self.logger.error(f"Error backing up guild data: {str(e)}", exc_info=True)
            return False
