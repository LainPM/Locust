from systems.base_system import System
from .player import MusicPlayer
from .queue import MusicQueue

class MusicSystem(System):
    """Music player system for voice channels"""
    
    def __init__(self, bot):
        super().__init__(bot)
        
        # Components
        self.player = MusicPlayer(self)
        self.queue = MusicQueue(self)
        
        # Voice clients
        self.voice_clients = {}  # Guild ID -> voice client
    
    async def initialize(self):
        """Initialize the music system"""
        # Nothing to initialize for now
        print("Music system initialized")
    
    async def cleanup(self):
        """Clean up resources when bot is shutting down"""
        # Disconnect from all voice channels
        for guild_id, voice_client in self.voice_clients.items():
            if voice_client and voice_client.is_connected():
                await voice_client.disconnect()
        
        self.voice_clients = {}
        print("Music system cleaned up")
