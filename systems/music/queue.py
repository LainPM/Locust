import discord
import asyncio
from typing import List, Dict, Any, Optional

class MusicQueue:
    """Component for managing music queues"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        
        # Queue by guild
        self.queues = {}  # Guild ID -> list of songs
    
    async def add_to_queue(self, guild_id: int, song_info: Dict[str, Any]) -> int:
        """Add a song to the queue. Returns position in queue."""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        
        self.queues[guild_id].append(song_info)
        return len(self.queues[guild_id])
    
    async def remove_from_queue(self, guild_id: int, position: int) -> Optional[Dict[str, Any]]:
        """Remove a song from the queue by position"""
        if guild_id not in self.queues or position < 0 or position >= len(self.queues[guild_id]):
            return None
        
        return self.queues[guild_id].pop(position)
    
    async def clear_queue(self, guild_id: int) -> bool:
        """Clear the queue for a guild"""
        if guild_id in self.queues:
            self.queues[guild_id] = []
            return True
        return False
    
    async def get_queue(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get the current queue for a guild"""
        return self.queues.get(guild_id, [])
    
    async def get_next_song(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get the next song in queue and remove it"""
        if guild_id in self.queues and self.queues[guild_id]:
            return self.queues[guild_id].pop(0)
        return None
    
    async def shuffle_queue(self, guild_id: int) -> bool:
        """Shuffle the queue for a guild"""
        import random
        
        if guild_id in self.queues and self.queues[guild_id]:
            random.shuffle(self.queues[guild_id])
            return True
        return False
    
    async def move_song(self, guild_id: int, old_position: int, new_position: int) -> bool:
        """Move a song in the queue to a new position"""
        if guild_id not in self.queues:
            return False
            
        queue = self.queues[guild_id]
        
        if old_position < 0 or old_position >= len(queue) or new_position < 0 or new_position >= len(queue):
            return False
        
        # Move the song
        song = queue.pop(old_position)
        queue.insert(new_position, song)
        
        return True
