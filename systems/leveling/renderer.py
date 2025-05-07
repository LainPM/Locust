# systems/leveling/renderer.py
import discord
import io
from typing import Dict, Any

class LevelingRenderer:
    """Simple renderer for leveling cards"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
    
    async def initialize(self) -> bool:
        """Initialize the renderer"""
        return True
    
    async def create_rank_card(self, user, user_data: Dict[str, Any], rank: int, guild) -> discord.File:
        """Create a simple rank card as a text file"""
        # For now, just return a text file with rank info
        content = f"""
Rank Card for {user.display_name}
================================
Rank: #{rank}
Level: {user_data.get('level', 0)}
XP: {user_data.get('xp', 0)}
Messages: {user_data.get('messages', 0)}
        """
        
        # Create a file object
        file_bytes = io.BytesIO(content.encode('utf-8'))
        return discord.File(fp=file_bytes, filename="rank.txt")
    
    def hex_to_bgr(self, hex_color: str) -> tuple:
        """Utility method to convert hex color to BGR (for future implementation)"""
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return (b, g, r)
    
    def is_valid_hex_color(self, color: str) -> bool:
        """Utility method to validate hex colors (for future implementation)"""
        import re
        pattern = r'^#?([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$'
        return bool(re.match(pattern, color))
