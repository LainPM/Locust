# systems/moderation/filter/__init__.py
import discord
import re
from typing import Dict, Optional

from .blacklist import BlacklistFilter
from .whitelist import WhitelistFilter

class ContentFilter:
    """Filter component for content moderation"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        
        # Sub-components
        self.blacklist = BlacklistFilter(self)
        self.whitelist = WhitelistFilter(self)
        
        # Settings cache
        self.settings_cache = {}  # Guild ID -> settings
    
    async def initialize(self):
        """Initialize the filter component"""
        # Initialize sub-components
        await self.blacklist.initialize()
        await self.whitelist.initialize()
        
        # Load settings
        await self.load_settings()
    
    async def load_settings(self):
        """Load filter settings for all guilds"""
        async for doc in self.bot.db.filter_settings.find({}):
            guild_id = doc["guild_id"]
            self.settings_cache[guild_id] = doc
    
    async def get_settings(self, guild_id: int) -> Dict:
        """Get filter settings for a guild"""
        if guild_id not in self.settings_cache:
            settings = await self.load_guild_settings(guild_id)
            self.settings_cache[guild_id] = settings
        
        return self.settings_cache[guild_id]
    
    async def load_guild_settings(self, guild_id: int) -> Dict:
        """Load filter settings for a guild"""
        settings = await self.bot.db.filter_settings.find_one({"guild_id": guild_id})
        
        if not settings:
            # Create default settings
            settings = {
                "guild_id": guild_id,
                "enabled": False,
                "delete_matches": True,
                "notify_user": True,
                "notify_channel": None,
                "log_channel": None,
                "auto_warn": False,
                "created_at": datetime.datetime.utcnow().isoformat()
            }
            
            await self.bot.db.filter_settings.insert_one(settings)
        
        return settings
    
    async def update_settings(self, guild_id: int, updates: Dict) -> bool:
        """Update filter settings"""
        result = await self.bot.db.filter_settings.update_one(
            {"guild_id": guild_id},
            {"$set": updates}
        )
        
        # Update cache
        if guild_id in self.settings_cache:
            self.settings_cache[guild_id].update(updates)
        
        return result.modified_count > 0
    
    def matches(self, content: str, item: str, match_type: str) -> bool:
        """Check if content matches an item with given match type"""
        try:
            if match_type == "contains":
                return item.lower() in content.lower()
            if match_type == "exact":
                return content.lower() == item.lower()
            if match_type == "starts_with":
                return content.lower().startswith(item.lower())
            if match_type == "ends_with":
                return content.lower().endswith(item.lower())
            if match_type == "regex":
                return bool(re.search(item, content, re.IGNORECASE))
        except Exception as e:
            print(f"Error in filter pattern matching: {e}")
            return False
        return False
    
    async def check_message(self, message: discord.Message) -> bool:
        """
        Check if message should be filtered
        Returns True if message passes filter, False if it's filtered
        """
        guild_id = message.guild.id
        
        # Get settings
        settings = await self.get_settings(guild_id)
        
        # Check if filtering is enabled
        if not settings.get("enabled", False):
            return True  # Filtering disabled, allow message
        
        # Check if message content is empty
        if not message.content:
            return True
        
        content = message.content
        
        # Check whitelist first
        whitelist_match = self.whitelist.check(content, guild_id)
        if whitelist_match:
            return True  # Whitelisted, allow message
        
        # Check blacklist
        blacklist_match = self.blacklist.check(content, guild_id)
        if blacklist_match:
            # Message matched blacklist
            await self._handle_filtered_message(message, blacklist_match)
            return False  # Filtered, stop message processing
        
        # No blacklist match found
        return True
    
    async def _handle_filtered_message(self, message: discord.Message, matched_item: str):
        """Handle a message that matched the blacklist"""
        guild_id = message.guild.id
        user_id = message.author.id
        settings = await self.get_settings(guild_id)
        
        # Try to delete the message
        if settings.get("delete_matches", True):
            try:
                await message.delete()
            except Exception as e:
                print(f"Failed to delete filtered message: {e}")
        
        # Track violation
        evidence = f"Message contained blacklisted content: {message.content[:100]}"
        await self.system.increment_violation(guild_id, user_id, "filter", evidence)
        
        # Notify user if enabled
        if settings.get("notify_user", True):
            try:
                await message.author.send(
                    f"Your message in {message.guild.name} was removed because it contained blacklisted content."
                )
            except Exception:
                # Unable to DM user
                try:
                    await message.channel.send(
                        f"{message.author.mention}, your message was removed because it contained blacklisted content.",
                        delete_after=5
                    )
                except Exception:
                    pass  # Can't notify at all
        
        # Log to log channel if configured
        log_channel_id = settings.get("log_channel")
        if log_channel_id:
            log_channel = message.guild.get_channel(int(log_channel_id))
            if log_channel:
                embed = discord.Embed(
                    title="Message Filtered",
                    description=f"A message by {message.author.mention} was filtered.",
                    color=discord.Color.orange(),
                    timestamp=datetime.datetime.utcnow()
                )
                embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                embed.add_field(name="Filter Match", value=matched_item, inline=True)
                embed.add_field(name="Content", value=f"```{message.content[:1000]}```", inline=False)
                embed.set_footer(text=f"User ID: {user_id}")
                
                try:
                    await log_channel.send(embed=embed)
                except Exception as e:
                    print(f"Failed to log filtered message: {e}")
