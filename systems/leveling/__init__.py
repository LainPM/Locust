# systems/leveling/__init__.py
from .processor import LevelingProcessor
from .storage import LevelingStorage
from .renderer import RankCardRenderer
from .rewards import RewardManager

from systems.base_system import System

class LevelingSystem(System):
    """XP and level management system"""
    
    def __init__(self, bot):
        super().__init__(bot)
        
        # Components
        self.processor = LevelingProcessor(self)
        self.storage = LevelingStorage(self)
        self.renderer = RankCardRenderer(self)
        self.rewards = RewardManager(self)
        
        # Settings and cache
        self.settings_cache = {}  # Guild ID -> settings
        self.xp_cooldowns = {}  # User ID -> last message timestamp
        
    async def initialize(self):
        """Initialize the leveling system"""
        # Register event handlers
        self.register_event("on_message", self.processor.process_message, priority=50)
        
        # Register commands
        # Will be implemented later
        
        # Load settings from database for all guilds
        await self.load_settings()
        
        print("Leveling system initialized")
    
    async def load_settings(self):
        """Load settings from database"""
        collection = self.bot.db["level_settings"]
        async for doc in collection.find({}):
            guild_id = doc["guild_id"]
            self.settings_cache[guild_id] = doc
        
        print(f"Loaded leveling settings for {len(self.settings_cache)} guilds")
    
    async def get_settings(self, guild_id: int) -> Dict:
        """Get settings for a guild"""
        if guild_id not in self.settings_cache:
            # Load or create default settings
            settings = await self.storage.get_settings(guild_id)
            self.settings_cache[guild_id] = settings
        
        return self.settings_cache[guild_id]
