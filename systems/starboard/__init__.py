# systems/starboard/__init__.py
from systems.base_system import System
from .processor import StarboardProcessor
from .storage import StarboardStorage
from .renderer import StarboardRenderer

class StarboardSystem(System):
    """Starboard system for highlighting popular messages"""
    
    def __init__(self, bot):
        super().__init__(bot)
        
        # Components
        self.processor = StarboardProcessor(self)
        self.storage = StarboardStorage(self)
        self.renderer = StarboardRenderer(self)
        
        # Settings cache
        self.settings_cache = {}  # Guild ID -> settings
        
        # Active tasks
        self.reaction_tasks = {}  # Guild ID -> asyncio task
    
    async def initialize(self):
        """Initialize the starboard system"""
        # Register event handlers
        self.register_event("on_reaction_add", self.processor.process_reaction_add, priority=50)
        self.register_event("on_reaction_remove", self.processor.process_reaction_remove, priority=50)
        self.register_event("on_message", self.processor.process_message, priority=40)
        
        # Load settings from database for all guilds
        await self.load_settings()
        
        # Start background tasks for checking reactions
        await self.start_reaction_tasks()
        
        print("Starboard system initialized")
    
    async def load_settings(self):
        """Load settings from database"""
        collection = self.bot.db["starboard_settings"]
        async for doc in collection.find({}):
            guild_id = doc["guild_id"]
            self.settings_cache[guild_id] = doc
        
        print(f"Loaded starboard settings for {len(self.settings_cache)} guilds")
    
    async def get_settings(self, guild_id: int):
        """Get settings for a guild"""
        if guild_id not in self.settings_cache:
            # Load or create default settings
            settings = await self.storage.get_settings(guild_id)
            self.settings_cache[guild_id] = settings
        
        return self.settings_cache[guild_id]
    
    async def start_reaction_tasks(self):
        """Start background tasks for checking reactions"""
        for guild_id in self.settings_cache:
            if guild_id not in self.reaction_tasks or self.reaction_tasks[guild_id].done():
                self.reaction_tasks[guild_id] = self.bot.loop.create_task(
                    self.processor.check_reactions_task(guild_id)
                )
    
    async def cleanup(self):
        """Clean up resources when bot is shutting down"""
        # Cancel all running tasks
        for task in self.reaction_tasks.values():
            if not task.done():
                task.cancel()
