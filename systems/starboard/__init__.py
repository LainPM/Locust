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
        collection = s
