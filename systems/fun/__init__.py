# systems/fun/__init__.py
from systems.base_system import System
from .lovecalc import LoveCalculator

class FunSystem(System):
    """Fun commands and features"""
    
    def __init__(self, bot):
        super().__init__(bot)
        
        # Components
        self.lovecalc = LoveCalculator(self)
    
    async def initialize(self):
        """Initialize the fun system"""
        print("Fun system initialized")
