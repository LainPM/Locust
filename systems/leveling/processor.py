# systems/leveling/processor.py
import discord
import datetime
import random
from typing import Dict, Any

class LevelingProcessor:
    """Handles XP processing and leveling logic"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
    
    async def process_message(self, message: discord.Message) -> bool:
        """Process a message for XP"""
        # Skip if not in guild
        if not message.guild:
            return True  # Continue event propagation
        
        # Get guild settings
        guild_id = message.guild.id
        settings = await self.system.get_settings(guild_id)
        
        # Check if system is enabled
        if not settings.get("enabled", True):
            return True  # Continue event propagation
        
        # Check if channel is excluded
        if str(message.channel.id) in settings.get("excluded_channels", []):
            return True  # Continue event propagation
        
        # Check cooldown
        user_id = message.author.id
        current_time = datetime.datetime.utcnow()
        cooldown = settings.get("cooldown", 60)  # Default 60 seconds
        
        cooldown_key = f"{user_id}_{guild_id}"
        if cooldown_key in self.system.xp_cooldowns:
            last_time = self.system.xp_cooldowns[cooldown_key]
            if (current_time - last_time).total_seconds() < cooldown:
                return True  # Still on cooldown, continue event propagation
        
        # Update cooldown
        self.system.xp_cooldowns[cooldown_key] = current_time
        
        # Award XP
        min_xp = settings.get("min_xp", 15)
        max_xp = settings.get("max_xp", 25)
        xp_to_add = random.randint(min_xp, max_xp)
        
        # Process the XP and leveling
        new_xp, new_level, level_up = await self.system.storage.update_user_xp(
            user_id, guild_id, xp_to_add
        )
        
        # Handle level up
        if level_up:
            await self.handle_level_up(message, user_id, guild_id, new_level, settings)
        
        return True  # Continue event propagation
    
    async def handle_level_up(self, message, user_id, guild_id, new_level, settings):
        """Handle user level up event"""
        # Check if announcements are enabled
        if not settings.get("announce_level_up", True):
            return
        
        # Determine where to send the announcement
        if settings.get("level_up_channel"):
            # Send to specific channel
            channel_id = int(settings["level_up_channel"])
            channel = message.guild.get_channel(channel_id)
            if channel:
                await channel.send(f"🎉 {message.author.mention} just reached level {new_level}!")
        else:
            # Send to current channel
            await message.channel.send(f"🎉 {message.author.mention} just reached level {new_level}!")
        
        # Check for role rewards
        await self.system.rewards.check_role_rewards(message.guild, message.author, new_level)
