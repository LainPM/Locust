# systems/moderation/filter.py
import discord
import re
import datetime
from typing import Dict, List, Set, Any, Tuple

class ContentFilter:
    """Filter component for content moderation"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        
        # Cache for blacklist and whitelist
        self.blacklist_cache = {}  # Guild ID -> {item: match_type}
        self.whitelist_cache = {}  # Guild ID -> {item: match_type}
    
    async def initialize(self):
        """Initialize the filter component"""
        # Load blacklist and whitelist for all guilds
        await self.load_all_filters()
    
    async def load_all_filters(self):
        """Load all blacklists and whitelists"""
        # Load blacklists
        async for doc in self.bot.db.blacklist.find({}):
            guild_id = doc["guild_id"]
            if guild_id not in self.blacklist_cache:
                self.blacklist_cache[guild_id] = {}
                
            self.blacklist_cache[guild_id][doc["item"]] = doc["match_type"]
        
        # Load whitelists
        async for doc in self.bot.db.whitelist.find({}):
            guild_id = doc["guild_id"]
            if guild_id not in self.whitelist_cache:
                self.whitelist_cache[guild_id] = {}
                
            self.whitelist_cache[guild_id][doc["item"]] = doc["match_type"]
        
        print(f"Loaded content filters for {len(self.blacklist_cache)} guilds")
    
    async def load_settings(self, guild_id: int) -> Dict:
        """Load filter settings for a guild"""
        settings = await self.bot.db["filter_settings"].find_one({"guild_id": guild_id})
        
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
            
            await self.bot.db["filter_settings"].insert_one(settings)
        
        return settings
    
    async def check_message(self, message: discord.Message) -> bool:
        """
        Check if message should be filtered
        Returns True if message passes filter, False if it's filtered
        """
        guild_id = message.guild.id
        
        # Get settings
        settings = await self.system.get_filter_settings(guild_id)
        
        # Check if filtering is enabled
        if not settings.get("enabled", False):
            return True  # Filtering disabled, allow message
        
        # Ensure blacklist and whitelist are loaded for this guild
        if guild_id not in self.blacklist_cache:
            self.blacklist_cache[guild_id] = {}
            
            # Load from database
            async for doc in self.bot.db.blacklist.find({"guild_id": guild_id}):
                self.blacklist_cache[guild_id][doc["item"]] = doc["match_type"]
        
        if guild_id not in self.whitelist_cache:
            self.whitelist_cache[guild_id] = {}
            
            # Load from database
            async for doc in self.bot.db.whitelist.find({"guild_id": guild_id}):
                self.whitelist_cache[guild_id][doc["item"]] = doc["match_type"]
        
        # Check if message content is empty
        if not message.content:
            return True
        
        content = message.content.lower()
        
        # Check whitelist first
        for item, match_type in self.whitelist_cache.get(guild_id, {}).items():
            if self._matches(content, item, match_type):
                return True  # Whitelisted, allow message
        
        # Check blacklist
        for item, match_type in self.blacklist_cache.get(guild_id, {}).items():
            if self._matches(content, item, match_type):
                # Message matched blacklist
                await self._handle_filtered_message(message, item, match_type)
                return False  # Filtered, stop message processing
        
        # No blacklist match found
        return True
    
    def _matches(self, content: str, item: str, match_type: str) -> bool:
        """Check if content matches a filter item"""
        try:
            if match_type == "contains":
                return item.lower() in content
            if match_type == "exact":
                return content == item.lower()
            if match_type == "starts_with":
                return content.startswith(item.lower())
            if match_type == "ends_with":
                return content.endswith(item.lower())
            if match_type == "regex":
                return bool(re.search(item, content, re.IGNORECASE))
        except Exception as e:
            print(f"Error in filter pattern matching: {e}")
            return False
        return False
    
    async def _handle_filtered_message(self, message: discord.Message, matched_item: str, match_type: str):
        """Handle a message that matched the blacklist"""
        guild_id = message.guild.id
        user_id = message.author.id
        settings = await self.system.get_filter_settings(guild_id)
        
        # Try to delete the message
        if settings.get("delete_matches", True):
            try:
                await message.delete()
            except Exception as e:
                print(f"Failed to delete filtered message: {e}")
        
        # Track violation
        evidence = f"Message contained blacklisted content (match: {match_type}): {message.content[:100]}"
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
                embed.add_field(name="Filter Match", value=match_type, inline=True)
                embed.add_field(name="Content", value=f"```{message.content[:1000]}```", inline=False)
                embed.set_footer(text=f"User ID: {user_id}")
                
                try:
                    await log_channel.send(embed=embed)
                except Exception as e:
                    print(f"Failed to log filtered message: {e}")
