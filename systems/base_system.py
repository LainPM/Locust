# systems/base_system.py
import discord
from typing import Dict, List, Any, Optional, Callable

class System:
    """Base class for all bot systems"""
    
    def __init__(self, bot):
        self.bot = bot
        self.name = self.__class__.__name__
        self.db = bot.db
    
    async def initialize(self):
        """Initialize the system - override in subclasses"""
        pass
    
    def register_event(self, event_name: str, handler: Callable, priority: int = 0):
        """Register an event handler"""
        self.bot.register_event_handler(event_name, handler, priority)
    
    async def get_system(self, name: str) -> Any:
        """Get another system by name"""
        return await self.bot.get_system(name)
