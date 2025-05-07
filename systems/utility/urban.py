# systems/utility/urban.py
import discord
import aiohttp
import json
from typing import Dict, List, Any, Optional

class UrbanDictionary:
    """Urban Dictionary lookup component"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        self.base_url = "https://api.urbandictionary.com/v0/"
    
    async def initialize(self) -> bool:
        """Initialize the component"""
        return True
    
    async def lookup(self, term: str) -> Optional[List[Dict[str, Any]]]:
        """Look up a term on Urban Dictionary"""
        async with aiohttp.ClientSession() as session:
            try:
                # Make API request
                async with session.get(f"{self.base_url}define?term={term}") as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    # Check if we got definitions
                    if "list" not in data or not data["list"]:
                        return None
                    
                    return data["list"]
                    
            except Exception as e:
                print(f"Error looking up UD term: {e}")
                return None
    
    async def send_result(self, interaction: discord.Interaction, results: List[Dict[str, Any]]):
        """Send Urban Dictionary results with pagination"""
        if not results:
            await interaction.followup.send("No definitions found.")
            return
        
        # Start with the first definition
        current_page = 0
        total_pages = len(results)
        
        # Create embed for first definition
        embed = await self._create_definition_embed(results[current_page], current_page, total_pages)
        
        # Create pagination buttons
        view = UrbanPaginationView(results, interaction.user.id)
        
        # Send initial message
        await interaction.followup.send(embed=embed, view=view)
    
    async def _create_definition_embed(self, definition: Dict[str, Any], page: int, total_pages: int) -> discord.Embed:
        """Create an embed for a definition"""
        # Clean up text (Urban Dictionary can have offensive content)
        word = definition.get("word", "Unknown")
        definition_text = definition.get("definition", "No definition")
        example = definition.get("example", "No example")
        
        # Create embed
        embed = discord.Embed(
            title=f"Urban Dictionary: {word}",
            url=definition.get("permalink", "https://www.urbandictionary.com"),
            color=discord.Color.blurple()
        )
        
        # Add main content
        embed.add_field(name="Definition", value=definition_text[:1024], inline=False)
        
        if example:
            embed.add_field(name="Example", value=example[:1024], inline=False)
        
        # Add votes
        thumbs_up = definition.get("thumbs_up", 0)
        thumbs_down = definition.get("thumbs_down", 0)
        embed.add_field(name="Votes", value=f"👍 {thumbs_up} | 👎 {thumbs_down}", inline=True)
        
        # Add page counter
        embed.set_footer(text=f"Definition {page + 1} of {total_pages}")
        
        return embed

# UI Components
class UrbanPaginationView(discord.ui.View):
    """Pagination view for Urban Dictionary results"""
    
    def __init__(self, results: List[Dict[str, Any]], user_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.results = results
        self.current_page = 0
        self.user_id = user_id
        
        # Update button states
        self._update_buttons()
    
    def _update_buttons(self):
        """Update button states based on current page"""
        # Disable previous button if on first page
        self.children[0].disabled = self.current_page == 0
        
        # Disable next button if on last page
        self.children[1].disabled = self.current_page >= len(self.results) - 1
    
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle previous button click"""
        # Check if the interaction user is the one who requested
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your definition lookup!", ephemeral=True)
            return
        
        # Go to previous page
        self.current_page = max(0, self.current_page - 1)
        
        # Create new embed
        embed = await self._create_definition_embed(
            self.results[self.current_page], 
            self.current_page, 
            len(self.results)
        )
        
        # Update buttons
        self._update_buttons()
        
        # Edit message
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle next button click"""
        # Check if the interaction user is the one who requested
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your definition lookup!", ephemeral=True)
            return
        
        # Go to next page
        self.current_page = min(len(self.results) - 1, self.current_page + 1)
        
        # Create new embed
        embed = await self._create_definition_embed(
            self.results[self.current_page], 
            self.current_page, 
            len(self.results)
        )
        
        # Update buttons
        self._update_buttons()
        
        # Edit message
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def _create_definition_embed(self, definition: Dict[str, Any], page: int, total_pages: int) -> discord.Embed:
        """Create an embed for a definition"""
        # Clean up text
        word = definition.get("word", "Unknown")
        definition_text = definition.get("definition", "No definition")
        example = definition.get("example", "No example")
        
        # Create embed
        embed = discord.Embed(
            title=f"Urban Dictionary: {word}",
            url=definition.get("permalink", "https://www.urbandictionary.com"),
            color=discord.Color.blurple()
        )
        
        # Add main content - limit to 1024 characters for embed field limits
        embed.add_field(name="Definition", value=definition_text[:1024], inline=False)
        
        if example:
            embed.add_field(name="Example", value=example[:1024], inline=False)
        
        # Add votes
        thumbs_up = definition.get("thumbs_up", 0)
        thumbs_down = definition.get("thumbs_down", 0)
        embed.add_field(name="Votes", value=f"👍 {thumbs_up} | 👎 {thumbs_down}", inline=True)
        
        # Add page counter
        embed.set_footer(text=f"Definition {page + 1} of {total_pages}")
        
        return embed
