# systems/marketplace/renderer.py
import discord
from discord import ui
from typing import Dict, Any, Optional

class MarketplaceRenderer:
    """Renderer for marketplace UI elements"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
    
    async def create_post_modal(self, post_type: str, interaction: discord.Interaction, marketplace_system) -> ui.Modal:
        """Create a modal for post creation"""
        # Create a modal based on post type
        if post_type == "Hiring":
            return HiringModal(post_type, marketplace_system)
        elif post_type == "For-Hire":
            return ForHireModal(post_type, marketplace_system)
        elif post_type == "Selling":
            return SellingModal(post_type, marketplace_system)
        else:
            # Default modal
            return GenericPostModal(post_type, marketplace_system)
    
    async def create_post_embed(self, post_data: Dict[str, Any]) -> discord.Embed:
        """Create an embed for a marketplace post"""
        post_type = post_data.get("type", "Unknown")
        
        # Set color based on post type
        if post_type == "Hiring":
            color = discord.Color.blue()
        elif post_type == "For-Hire":
            color = discord.Color.green()
        elif post_type == "Selling":
            color = discord.Color.gold()
        else:
            color = discord.Color.light_grey()
        
        # Create the embed
        embed = discord.Embed(
            title=post_data.get("title", "Untitled Post"),
            description=post_data.get("description", "No description provided."),
            color=color
        )
        
        # Add fields
        if "price" in post_data and post_data["price"]:
            embed.add_field(name="Price", value=post_data["price"], inline=True)
            
        if "contact" in post_data and post_data["contact"]:
            embed.add_field(name="Contact", value=post_data["contact"], inline=True)
        
        if "additional_info" in post_data and post_data["additional_info"]:
            embed.add_field(name="Additional Information", value=post_data["additional_info"], inline=False)
        
        # Add user info
        user_id = post_data.get("user_id")
        if user_id:
            user = self.bot.get_user(user_id)
            if user:
                embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
                embed.set_footer(text=f"Posted by {user.display_name}")
        
        return embed

# Modal classes for different post types
class GenericPostModal(ui.Modal):
    """Generic post creation modal"""
    
    def __init__(self, post_type: str, marketplace_system):
        super().__init__(title=f"Create {post_type} Post")
        self.post_type = post_type
        self.marketplace_system = marketplace_system
        
        # Add basic fields
        self.title_input = ui.TextInput(
            label="Title",
            placeholder="Enter a title for your post",
            required=True,
            max_length=100
        )
        self.add_item(self.title_input)
        
        self.description_input = ui.TextInput(
            label="Description",
            placeholder="Describe what you're offering or looking for",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1000
        )
        self.add_item(self.description_input)
        
        self.price_input = ui.TextInput(
            label="Price",
            placeholder="Enter your price or budget (e.g. $10, $5-20/hr)",
            required=False,
            max_length=50
        )
        self.add_item(self.price_input)
        
        self.contact_input = ui.TextInput(
            label="Contact Information",
            placeholder="How should people contact you?",
            required=False,
            max_length=100
        )
        self.add_item(self.contact_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission"""
        # Create post data
        post_data = {
            "type": self.post_type,
            "title": self.title_input.value,
            "description": self.description_input.value,
            "price": self.price_input.value,
            "contact": self.contact_input.value,
            "user_id": interaction.user.id,
            "guild_id": interaction.guild.id,
            "timestamp": discord.utils.utcnow().isoformat()
        }
        
        # Submit to marketplace system
        await interaction.response.defer(ephemeral=True)
        
        # Basic placeholder response for now
        await interaction.followup.send(f"Your {self.post_type} post has been submitted for approval!", ephemeral=True)

class HiringModal(GenericPostModal):
    """Modal for hiring posts"""
    
    def __init__(self, post_type: str, marketplace_system):
        super().__init__(post_type, marketplace_system)
        
        # Additional field for hiring posts
        self.requirements_input = ui.TextInput(
            label="Requirements",
            placeholder="List any specific requirements or qualifications",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.add_item(self.requirements_input)

class ForHireModal(GenericPostModal):
    """Modal for for-hire posts"""
    
    def __init__(self, post_type: str, marketplace_system):
        super().__init__(post_type, marketplace_system)
        
        # Additional field for for-hire posts
        self.skills_input = ui.TextInput(
            label="Skills & Experience",
            placeholder="List your relevant skills and experience",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.add_item(self.skills_input)

class SellingModal(GenericPostModal):
    """Modal for selling posts"""
    
    def __init__(self, post_type: str, marketplace_system):
        super().__init__(post_type, marketplace_system)
        
        # Additional field for selling posts
        self.details_input = ui.TextInput(
            label="Item Details",
            placeholder="Provide details about the item (condition, features, etc.)",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.add_item(self.details_input)
