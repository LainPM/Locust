# systems/leveling/__init__.py
import logging
import discord
import asyncio
from typing import Dict, List, Any, Optional, Union

from systems.base_system import System
from .storage import LevelingStorage
from .processor import LevelingProcessor
from .renderer import LevelingRenderer

class LevelingSystem(System):
    """XP and leveling system for Discord servers"""
    
    def __init__(self, bot):
        super().__init__(bot)
        self.logger = logging.getLogger('axis_bot.systems.leveling')
        
        # Message cooldowns to prevent XP farming
        self.user_cooldowns = {}
    
    async def initialize(self) -> bool:
        """Initialize the leveling system"""
        try:
            self.logger.info("Initializing leveling system...")
            
            # Initialize components in the correct order
            self.storage = LevelingStorage(self)
            self.processor = LevelingProcessor(self)
            self.renderer = LevelingRenderer(self)
            
            # Initialize storage first (database)
            await self.storage.initialize()
            
            # Then initialize processor (business logic)
            await self.processor.initialize()
            
            # Finally initialize renderer (UI components)
            await self.renderer.initialize()
            
            # Start background tasks
            await self.start_background_task(
                "cleanup_cooldowns", 
                self.processor.cleanup_cooldowns
            )
            
            await self.start_background_task(
                "periodic_backup",
                self.periodic_backup,
                hours=24
            )
            
            self.logger.info("Leveling system initialized successfully")
            self.initialized = True
            return True
            
        except Exception as e:
            self.logger.error(f"Error initializing leveling system: {str(e)}", exc_info=True)
            return False
    
    async def get_settings(self, guild_id: int) -> Dict[str, Any]:
        """Get settings for the leveling system in a guild"""
        return await self.storage.get_guild_settings(guild_id)
    
    async def update_settings(self, guild_id: int, settings: Dict[str, Any]) -> bool:
        """Update settings for the leveling system in a guild"""
        return await self.storage.update_guild_settings(guild_id, settings)
    
    @System.priority(50)  # Medium priority for this event
    async def on_message(self, message):
        """Process messages for XP gain"""
        # Skip if message is in DM
        if not message.guild:
            return
            
        # Skip if message is from a bot
        if message.author.bot:
            return
            
        # Get guild ID and user ID
        guild_id = message.guild.id
        user_id = message.author.id
        
        # Get guild settings
        settings = await self.get_settings(guild_id)
        
        # Skip if leveling is disabled for this guild
        if not settings.get("enabled", True):
            return
            
        # Skip if channel is excluded
        excluded_channels = settings.get("excluded_channels", [])
        if str(message.channel.id) in excluded_channels:
            return
            
        # Check cooldown
        if not await self.processor.check_cooldown(guild_id, user_id):
            return
            
        # Generate XP
        xp_gained = await self.processor.generate_xp(
            guild_id, 
            user_id, 
            message.author, 
            min_xp=settings.get("min_xp", 15),
            max_xp=settings.get("max_xp", 25)
        )
        
        # Add XP to user
        result = await self.storage.update_user_xp(guild_id, user_id, xp_gained)
        
        # Handle level up if needed
        if result.get("level_up", False):
            await self.processor.handle_level_up(
                message.guild,
                message.author,
                message.channel,
                result["level"],
                result["old_level"],
                settings
            )
    
    async def periodic_backup(self, hours: int = 24):
        """Periodically backup all guild data"""
        self.logger.info(f"Starting periodic backup task (every {hours} hours)")
        
        while True:
            try:
                self.logger.info("Running periodic backup of all guild data")
                
                # Get all guild IDs with leveling data
                unique_guilds = await self.db.aggregate(
                    self.storage.users_collection,
                    [{"$group": {"_id": "$guild_id"}}]
                )
                
                guild_ids = [g["_id"] for g in unique_guilds]
                
                # Backup each guild's data
                for guild_id in guild_ids:
                    await self.storage.backup_guild_data(guild_id)
                
                self.logger.info(f"Backed up data for {len(guild_ids)} guilds")
                
            except Exception as e:
                self.logger.error(f"Error in periodic backup: {str(e)}", exc_info=True)
            
            # Sleep until next backup
            await asyncio.sleep(hours * 3600)
    
    async def cleanup(self):
        """Clean up resources before shutdown"""
        try:
            self.logger.info("Cleaning up leveling system...")
            
            # Stop background tasks
            for task_name, task in list(self.background_tasks.items()):
                if not task.done():
                    task.cancel()
                    self.logger.info(f"Cancelled background task: {task_name}")
            
            # Custom cleanup operations
            # ...
            
            self.logger.info("Leveling system cleaned up successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error cleaning up leveling system: {str(e)}", exc_info=True)
            return False
