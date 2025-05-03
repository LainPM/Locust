# systems/tickets/__init__.py
from systems.base_system import System
from .storage import TicketStorage
from .processor import TicketProcessor
from .renderer import TicketRenderer

class TicketSystem(System):
    """Ticket system for user support and requests"""
    
    def __init__(self, bot):
        super().__init__(bot)
        
        # Components
        self.storage = TicketStorage(self)
        self.processor = TicketProcessor(self)
        self.renderer = TicketRenderer(self)
        
        # Settings cache
        self.settings_cache = {}  # Guild ID -> settings
        
        # Active views
        self.active_views = {}
    
    async def initialize(self):
        """Initialize the ticket system"""
        # Load settings from database for all guilds
        await self.load_settings()
        
        # Register persistent views
        await self.register_views()
        
        print("Ticket system initialized")
    
    async def load_settings(self):
        """Load settings from database"""
        collection = self.bot.db["ticket_config"]
        async for doc in collection.find({}):
            guild_id = doc["guild_id"]
            self.settings_cache[guild_id] = doc
        
        print(f"Loaded ticket settings for {len(self.settings_cache)} guilds")
    
    async def get_settings(self, guild_id: int):
        """Get settings for a guild"""
        if guild_id not in self.settings_cache:
            # Load or create default settings
            settings = await self.storage.get_settings(guild_id)
            self.settings_cache[guild_id] = settings
        
        return self.settings_cache[guild_id]
    
    async def register_views(self):
        """Register persistent views for tickets"""
        from .views import TicketPanelView, TicketManagementView, ClosedTicketView
        
        # Register views with the bot
        self.bot.add_view(TicketPanelView(self))
        self.bot.add_view(TicketManagementView(self))
        self.bot.add_view(ClosedTicketView(self))
