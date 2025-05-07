# systems/ai/storage.py
import datetime
from typing import Dict, List, Any, Optional

class AIStorage:
    """Storage for AI chat conversations"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        
        # Database collections
        self.conversations_collection = "ai_conversations"
        self.settings_collection = "ai_settings"
    
    async def get_conversation(self, user_id: int, channel_id: int) -> Optional[Dict[str, Any]]:
        """Get conversation data for a user in a channel"""
        try:
            conversation = await self.bot.db[self.conversations_collection].find_one({
                "user_id": user_id,
                "channel_id": channel_id
            })
            
            return conversation
        except Exception as e:
            print(f"Error getting conversation: {e}")
            return None
    
    async def save_conversation(self, user_id: int, channel_id: int, messages: List[Dict[str, Any]]) -> bool:
        """Save or update conversation data"""
        try:
            await self.bot.db[self.conversations_collection].update_one(
                {"user_id": user_id, "channel_id": channel_id},
                {
                    "$set": {
                        "messages": messages,
                        "updated_at": datetime.datetime.now().isoformat()
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            print(f"Error saving conversation: {e}")
            return False
    
    async def clear_conversation(self, user_id: int, channel_id: int) -> bool:
        """Clear conversation history for a user in a channel"""
        try:
            await self.bot.db[self.conversations_collection].delete_one({
                "user_id": user_id,
                "channel_id": channel_id
            })
            return True
        except Exception as e:
            print(f"Error clearing conversation: {e}")
            return False
    
    async def get_settings(self, guild_id: int) -> Dict[str, Any]:
        """Get AI settings for a guild"""
        settings = await self.bot.db[self.settings_collection].find_one({
            "guild_id": guild_id
        })
        
        if not settings:
            # Create default settings
            settings = {
                "guild_id": guild_id,
                "enabled": True,
                "bot_name": "Axis",
                "trigger_phrase": "hey axis",
                "allowed_channels": [],
                "blacklisted_users": [],
                "max_history": 10,
                "conversation_timeout": 30,  # Minutes
                "created_at": datetime.datetime.now().isoformat(),
                "updated_at": datetime.datetime.now().isoformat()
            }
            
            try:
                await self.bot.db[self.settings_collection].insert_one(settings)
            except Exception as e:
                print(f"Error creating AI settings: {e}")
        
        return settings
    
    async def update_settings(self, guild_id: int, updates: Dict[str, Any]) -> bool:
        """Update AI settings for a guild"""
        try:
            updates["updated_at"] = datetime.datetime.now().isoformat()
            
            await self.bot.db[self.settings_collection].update_one(
                {"guild_id": guild_id},
                {"$set": updates},
                upsert=True
            )
            
            return True
        except Exception as e:
            print(f"Error updating AI settings: {e}")
            return False
