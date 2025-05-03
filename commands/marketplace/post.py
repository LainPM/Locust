# commands/marketplace/post.py
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal

class MarketplacePostCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="post",
        description="Create a marketplace post"
    )
    @app_commands.describe(
        post_type="Type of post to create"
    )
    @app_commands.choices(post_type=[
        app_commands.Choice(name="Hiring", value="Hiring"),
        app_commands.Choice(name="For-Hire", value="For-Hire"),
        app_commands.Choice(name="Selling", value="Selling")
    ])
    @app_commands.guild_only()
    async def post(
        self,
        interaction: discord.Interaction,
        post_type: str
    ):
        """Create a marketplace post"""
        # Get the marketplace system
        marketplace_system = await self.bot.get_system("MarketplaceSystem")
        if not marketplace_system:
            return await interaction.response.send_message("Marketplace system is not available.")
        
        # Get server settings
        guild_id = interaction.guild.id
        settings = await marketplace_system.get_settings(guild_id)
        
        if not settings:
            return await interaction.response.send_message(
                "Marketplace hasn't been set up in this server. Please ask an admin to run `/setup_marketposts`.",
                ephemeral=True
            )
        
        # Create and show the post modal
        modal = await marketplace_system.renderer.create_post_modal(post_type, interaction, marketplace_system)
        await interaction.response.send_modal(modal)

async def setup(bot):
    await bot.add_cog(MarketplacePostCommand(bot))
