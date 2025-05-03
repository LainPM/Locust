# systems/marketplace/__init__.py
from systems.base_system import System
from .storage import MarketplaceStorage
from .processor import MarketplaceProcessor
from .renderer import MarketplaceRenderer

class MarketplaceSystem(System):
    """Marketplace system for selling, buying, and hiring posts"""
    
    def __init__(self, bot):
        super().__init__(bot)
        
        # Components
        self.storage = MarketplaceStorage(self)
        self.processor = MarketplaceProcessor(self)
        self.renderer = MarketplaceRenderer(self)
        
        # Settings cache
        self.settings_cache = {}  # Guild ID -> settings
        
        # Active tasks
        self.cleanup_tasks = {}  # Guild ID -> asyncio task
    
    async def initialize(self):
        """Initialize the marketplace system"""
        # Register event handlers
        self.register_event("on_message", self.processor.process_message, priority=40)
        
        # Load settings from database for all guilds
        await self.load_settings()
        
        # Start background tasks for deleting channels
        await self.start_cleanup_tasks()
        
        print("Marketplace system initialized")
    
    async def load_settings(self):
        """Load settings from database"""
        collection = self.bot.db["marketplace_settings"]
        async for doc in collection.find({}):
            guild_id = doc["guild_id"]
            self.settings_cache[guild_id] = doc
        
        print(f"Loaded marketplace settings for {len(self.settings_cache)} guilds")
    
    async def get_settings(self, guild_id: int):
        """Get settings for a guild"""
        if guild_id not in self.settings_cache:
            # Load or create default settings
            settings = await self.storage.get_settings(guild_id)
            self.settings_cache[guild_id] = settings
        
        return self.settings_cache[guild_id]
    
    async def start_cleanup_tasks(self):
        """Start background tasks for cleaning up old channels"""
        for guild_id in self.settings_cache:
            if guild_id not in self.cleanup_tasks or self.cleanup_tasks[guild_id].done():
                self.cleanup_tasks[guild_id] = self.bot.loop.create_task(
                    self.processor.check_scheduled_deletions(guild_id)
                )
    
    async def cleanup(self):
        """Clean up resources when bot is shutting down"""
        # Cancel all running tasks
        for task in self.cleanup_tasks.values():
            if not task.done():
                task.cancel()
