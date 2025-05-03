# systems/starboard/renderer.py
import discord
import datetime
from typing import Dict, Any

class StarboardRenderer:
    """Renderer component for the Starboard system"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
    
    async def create_starboard_embed(self, message: discord.Message, star_count: int) -> discord.Embed:
        """Create an embed for a starred message"""
        # Create the base embed
        embed = discord.Embed(
            description=message.content,
            color=discord.Color.gold(),
            timestamp=message.created_at
        )
        
        # Set author info
        embed.set_author(
            name=message.author.display_name,
            icon_url=message.author.display_avatar.url
        )
        
        # Add link to original message
        embed.add_field(name="Original", value=f"[Jump to message]({message.jump_url})", inline=False)
        
        # Add message ID in footer
        embed.set_footer(text=f"ID: {message.id}")
        
        # Add image if exists
        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    embed.set_image(url=attachment.url)
                    break
        
        return embed
