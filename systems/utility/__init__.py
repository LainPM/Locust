# systems/utility/__init__.py
from systems.base_system import System
from .urban import UrbanDictionary
from .roblox import RobloxLookup

class UtilitySystem(System):
    """Utility commands and features"""
    
    def __init__(self, bot):
        super().__init__(bot)
        
        # Components
        self.urban = UrbanDictionary(self)
        self.roblox = RobloxLookup(self)
    
    async def initialize(self):
        """Initialize the utility system"""
        # Initialize components
        await self.urban.initialize()
        await self.roblox.initialize()
        
        print("Utility system initialized")
