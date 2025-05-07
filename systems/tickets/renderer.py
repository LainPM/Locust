# systems/tickets/renderer.py
import discord
from typing import Dict, List, Any, Optional

class TicketRenderer:
    """Renderer component for the Ticket system"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
    
    async def create_ticket_panel(self, settings: Dict[str, Any]) -> discord.Embed:
        """Create the ticket panel embed"""
        # Get settings values with defaults
        title = settings.get("panel_title", "Support Tickets")
        description = settings.get("panel_description", "Click a button below to create a ticket")
        
        # Create embed
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )
        
        # Add ticket types
        ticket_types = settings.get("ticket_types", ["Support", "Bug Report", "Other"])
        ticket_types_text = ", ".join(ticket_types)
        
        embed.add_field(
            name="Available Ticket Types",
            value=ticket_types_text,
            inline=False
        )
        
        # Add footer
        embed.set_footer(text="Click a button below to create a ticket")
        
        return embed
    
    async def create_initial_message(self, ticket_type: str, user: discord.User) -> discord.Embed:
        """Create the initial ticket message embed"""
        embed = discord.Embed(
            title=f"New {ticket_type} Ticket",
            description=f"Thank you for opening a ticket, {user.mention}. Support staff will assist you shortly.",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Instructions",
            value="Please describe your issue in as much detail as possible.",
            inline=False
        )
        
        embed.set_footer(text="Use the buttons below to manage this ticket")
        
        return embed
    
    async def create_closing_message(self, user: discord.User) -> discord.Embed:
        """Create the ticket closing message embed"""
        embed = discord.Embed(
            title="Ticket Closed",
            description=f"This ticket has been closed by {user.mention}. This channel will be deleted in 10 seconds.",
            color=discord.Color.red()
        )
        
        return embed
    
    async def create_transcript_embed(self, channel_name: str, closed_by_id: int) -> discord.Embed:
        """Create the transcript embed"""
        embed = discord.Embed(
            title=f"Ticket Transcript - {channel_name}",
            description=f"Ticket closed by <@{closed_by_id}>",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        return embed
