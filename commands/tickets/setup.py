# commands/tickets/setup.py
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

class TicketSetupCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="setup_ticket_system",
        description="Set up the ticket system"
    )
    @app_commands.describe(
        ticket_panel="Channel to post the ticket panel",
        transcript_channel="Channel to send transcripts",
        ticket_category="Category to create tickets under",
        ticket_types="Comma-separated ticket types (e.g. Support,Bug)",
        moderator_roles="Comma-separated role IDs or @roles",
        panel_title="Title for the ticket panel embed (optional)",
        panel_description="Description for the ticket panel embed (optional)"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def setup_ticket_system(
        self,
        interaction: discord.Interaction,
        ticket_panel: discord.TextChannel,
        transcript_channel: discord.TextChannel,
        ticket_category: discord.CategoryChannel,
        ticket_types: str,
        moderator_roles: str,
        panel_title: Optional[str] = "Support Tickets",
        panel_description: Optional[str] = "Click a button below to create a ticket"
    ):
        """Setup the ticket system"""
        await interaction.response.defer(ephemeral=True)
        
        # Get the ticket system
        ticket_system = await self.bot.get_system("TicketSystem")
        if not ticket_system:
            return await interaction.followup.send("Ticket system is not available.")
        
        # Process the setup request
        result = await ticket_system.processor.setup(
            interaction.guild,
            ticket_panel,
            transcript_channel,
            ticket_category,
            ticket_types,
            moderator_roles,
            panel_title,
            panel_description
        )
        
        if result:
            await interaction.followup.send("Ticket system set up successfully!", ephemeral=True)
        else:
            await interaction.followup.send("There was an error setting up the ticket system.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSetupCommand(bot))
