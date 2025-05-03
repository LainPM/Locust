# systems/ai/__init__.py
from systems.base_system import System
from .processor import AIProcessor
from .storage import AIStorage

class AISystem(System):
    """AI-powered features and interactions"""
    
    def __init__(self, bot):
        super().__init__(bot)
        
        # Components
        self.processor = AIProcessor(self)
        self.storage = AIStorage(self)
        
        # Runtime data
        self.active_conversations = set()
        self.conversation_timeouts = {}
        self.user_messages = {}
    
    async def initialize(self):
        """Initialize the AI system"""
        # Register event handlers
        self.register_event("on_message", self.processor.process_message, priority=20)
        
        # Start cleanup task
        self.bot.loop.create_task(self.processor.cleanup_old_data())
        
        print("AI system initialized")
    
    async def cleanup(self):
        """Clean up resources when bot is shutting down"""
        # Cancel all running tasks
        if hasattr(self.processor, 'cleanup_task') and not self.processor.cleanup_task.done():
            self.processor.cleanup_task.cancel()
