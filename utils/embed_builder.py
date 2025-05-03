# utils/embed_builder.py
import discord
import datetime
from typing import Optional, Union, List, Dict

class EmbedBuilder:
    """Utility class for creating standardized embeds"""
    
    @staticmethod
    def standard(
        title: str,
        description: Optional[str] = None,
        color: Union[discord.Color, int] = discord.Color.blurple(),
        timestamp: bool = True,
        footer_text: Optional[str] = None,
        footer_icon: Optional[str] = None,
        thumbnail: Optional[str] = None,
        image: Optional[str] = None,
        author_name: Optional[str] = None,
        author_icon: Optional[str] = None,
        author_url: Optional[str] = None,
        fields: Optional[List[Dict[str, Union[str, bool]]]] = None
    ) -> discord.Embed:
        """Create a standardized embed with consistent formatting"""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        
        if timestamp:
            embed.timestamp = datetime.datetime.now()
        
        if footer_text:
            embed.set_footer(text=footer_text, icon_url=footer_icon)
        
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        
        if image:
            embed.set_image(url=image)
        
        if author_name:
            embed.set_author(name=author_name, icon_url=author_icon, url=author_url)
        
        if fields:
            for field in fields:
                embed.add_field(
                    name=field["name"],
                    value=field["value"],
                    inline=field.get("inline", False)
                )
        
        return embed
    
    @staticmethod
    def success(title: str, description: Optional[str] = None, **kwargs) -> discord.Embed:
        """Create a success embed with green color"""
        return EmbedBuilder.standard(
            title=title,
            description=description,
            color=discord.Color.green(),
            **kwargs
        )
    
    @staticmethod
    def error(title: str, description: Optional[str] = None, **kwargs) -> discord.Embed:
        """Create an error embed with red color"""
        return EmbedBuilder.standard(
            title=title,
            description=description,
            color=discord.Color.red(),
            **kwargs
        )
    
    @staticmethod
    def warning(title: str, description: Optional[str] = None, **kwargs) -> discord.Embed:
        """Create a warning embed with yellow color"""
        return EmbedBuilder.standard(
            title=title,
            description=description,
            color=discord.Color.yellow(),
            **kwargs
        )
    
    @staticmethod
    def info(title: str, description: Optional[str] = None, **kwargs) -> discord.Embed:
        """Create an info embed with blue color"""
        return EmbedBuilder.standard(
            title=title,
            description=description,
            color=discord.Color.blue(),
            **kwargs
        )
