# commands/moderation/filter.py
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List, Dict, Any, Literal
import math

class FilterCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="blacklist",
        description="Add or update an item in the blacklist"
    )
    @app_commands.describe(
        item="The word/phrase/link to blacklist",
        match_type="Match type",
        reason="Reason for blacklisting"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value="contains"),
        app_commands.Choice(name="Exact", value="exact"),
        app_commands.Choice(name="Starts With", value="starts_with"),
        app_commands.Choice(name="Ends With", value="ends_with"),
        app_commands.Choice(name="Regex", value="regex")
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def blacklist(
        self,
        interaction: discord.Interaction,
        item: str,
        match_type: str = "contains",
        reason: Optional[str] = None
    ):
        """Add an item to the blacklist"""
        await interaction.response.defer(ephemeral=True)
        
        # Get the moderation system
        moderation_system = await self.bot.get_system("ModerationSystem")
        if not moderation_system:
            return await interaction.followup.send("Moderation system is not available.")
        
        # Add to blacklist
        success = await moderation_system.filter.blacklist.add_item(
            interaction.guild.id,
            item,
            match_type,
            reason,
            interaction.user.id
        )
        
        if success:
            await interaction.followup.send(f"🚫 Blacklisted `{item}` ({match_type})", ephemeral=True)
        else:
            await interaction.followup.send(f"Failed to blacklist item.", ephemeral=True)
    
    @app_commands.command(
        name="whitelist",
        description="Add or update an item in the whitelist"
    )
    @app_commands.describe(
        item="The word/phrase/link to whitelist",
        match_type="Match type",
        reason="Reason for whitelisting"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value="contains"),
        app_commands.Choice(name="Exact", value="exact"),
        app_commands.Choice(name="Starts With", value="starts_with"),
        app_commands.Choice(name="Ends With", value="ends_with"),
        app_commands.Choice(name="Regex", value="regex")
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def whitelist(
        self,
        interaction: discord.Interaction,
        item: str,
        match_type: str = "contains",
        reason: Optional[str] = None
    ):
        """Add an item to the whitelist"""
        await interaction.response.defer(ephemeral=True)
        
        # Get the moderation system
        moderation_system = await self.bot.get_system("ModerationSystem")
        if not moderation_system:
            return await interaction.followup.send("Moderation system is not available.")
        
        # Add to whitelist
        success = await moderation_system.filter.whitelist.add_item(
            interaction.guild.id,
            item,
            match_type,
            reason,
            interaction.user.id
        )
        
        if success:
            await interaction.followup.send(f"✅ Whitelisted `{item}` ({match_type})", ephemeral=True)
        else:
            await interaction.followup.send(f"Failed to whitelist item.", ephemeral=True)
    
    @app_commands.command(
        name="show_blacklisted",
        description="Show all blacklisted items"
    )
    @app_commands.describe(
        match_type="Filter by match type (default: all)",
        page="Page number to view",
        ephemeral="Whether to show only to you"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="All", value="all"),
        app_commands.Choice(name="Contains", value="contains"),
        app_commands.Choice(name="Exact", value="exact"),
        app_commands.Choice(name="Starts With", value="starts_with"),
        app_commands.Choice(name="Ends With", value="ends_with"),
        app_commands.Choice(name="Regex", value="regex")
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def show_blacklisted(
        self,
        interaction: discord.Interaction,
        match_type: str = "all",
        page: int = 1,
        ephemeral: bool = True
    ):
        """Show all blacklisted items"""
        await interaction.response.defer(ephemeral=ephemeral)
        
        # Get the moderation system
        moderation_system = await self.bot.get_system("ModerationSystem")
        if not moderation_system:
            return await interaction.followup.send("Moderation system is not available.")
        
        # Get items
        items = await moderation_system.filter.blacklist.get_items(interaction.guild.id, match_type)
        
        if not items:
            return await interaction.followup.send("No blacklisted items found.", ephemeral=ephemeral)
        
        # Create pagination view
        from .views import PaginationView
        view = PaginationView(
            items=items,
            match_type=match_type,
            page=page,
            items_per_page=25,
            is_blacklist=True,
            interaction=interaction
        )
        
        # Send the view
        await interaction.followup.send(
            embed=view.get_embed(),
            view=view,
            ephemeral=ephemeral
        )
    
    @app_commands.command(
        name="show_whitelisted",
        description="Show all whitelisted items"
    )
    @app_commands.describe(
        match_type="Filter by match type (default: all)",
        page="Page number to view",
        ephemeral="Whether to show only to you"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="All", value="all"),
        app_commands.Choice(name="Contains", value="contains"),
        app_commands.Choice(name="Exact", value="exact"),
        app_commands.Choice(name="Starts With", value="starts_with"),
        app_commands.Choice(name="Ends With", value="ends_with"),
        app_commands.Choice(name="Regex", value="regex")
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def show_whitelisted(
        self,
        interaction: discord.Interaction,
        match_type: str = "all",
        page: int = 1,
        ephemeral: bool = True
    ):
        """Show all whitelisted items"""
        await interaction.response.defer(ephemeral=ephemeral)
        
        # Get the moderation system
        moderation_system = await self.bot.get_system("ModerationSystem")
        if not moderation_system:
            return await interaction.followup.send("Moderation system is not available.")
        
        # Get items
        items = await moderation_system.filter.whitelist.get_items(interaction.guild.id, match_type)
        
        if not items:
            return await interaction.followup.send("No whitelisted items found.", ephemeral=ephemeral)
        
        # Create pagination view
        from .views import PaginationView
        view = PaginationView(
            items=items,
            match_type=match_type,
            page=page,
            items_per_page=25,
            is_blacklist=False,
            interaction=interaction
        )
        
        # Send the view
        await interaction.followup.send(
            embed=view.get_embed(),
            view=view,
            ephemeral=ephemeral
        )

async def setup(bot):
    await bot.add_cog(FilterCommands(bot))
