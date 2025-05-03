# systems/basic/__init__.py
from systems.base_system import System

class BasicSystem(System):
    """Basic utility commands and functions"""
    
    def __init__(self, bot):
        super().__init__(bot)
    
    async def initialize(self):
        """Initialize the basic system"""
        print("Basic system initialized")
        
    async def get_latency(self):
        """Get bot latency in milliseconds"""
        return round(self.bot.latency * 1000)
