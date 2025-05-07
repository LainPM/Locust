# systems/tickets/views.py
import discord
from discord import ui
from typing import Dict, List, Any, Optional

class TicketPanelView(ui.View):
    """View for the ticket panel with buttons for each ticket type"""
    
    def __init__(self, system):
        super().__init__(timeout=None)  # Persistent view
        self.system = system
        self.ticket_types = ["Support", "Bug Report", "Other"]  # Default types
        
        # Try to get ticket types from settings
        try:
            guild_id = next(iter(self.system.settings_cache), None)
            if guild_id:
                settings = self.system.settings_cache[guild_id]
                if "ticket_types" in settings and settings["ticket_types"]:
                    self.ticket_types = settings["ticket_types"]
        except Exception as e:
            print(f"Error getting ticket types: {e}")
        
        # Add buttons for each ticket type
        self._add_ticket_buttons()
    
    def _add_ticket_buttons(self):
        """Add buttons for each ticket type"""
        # Clear existing buttons
        self.clear_items()
        
        # Add ticket type buttons (up to 5 due to Discord limit)
        for i, ticket_type in enumerate(self.ticket_types[:5]):
            button = ui.Button(
                label=ticket_type,
                style=discord.ButtonStyle.primary,
                custom_id=f"ticket_create_{ticket_type}"
            )
            button.callback = self.create_ticket_callback
            self.add_item(button)
    
    async def create_ticket_callback(self, interaction: discord.Interaction):
        """Callback for ticket creation buttons"""
        # Get ticket type from custom ID
        custom_id = interaction.data["custom_id"]
        ticket_type = custom_id.replace("ticket_create_", "")
        
        # Defer the response to avoid timeout
        await interaction.response.defer(ephemeral=True)
        
        # Check if user already has an open ticket
        user_tickets = await self.system.storage.get_user_tickets(
            interaction.guild.id,
            interaction.user.id
        )
        
        active_tickets = [t for t in user_tickets if t.get("status") == "open"]
        
        if active_tickets:
            await interaction.followup.send(
                "You already have an open ticket. Please use your existing ticket or wait for it to be closed.",
                ephemeral=True
            )
            return
        
        # Create the ticket
        ticket_channel = await self.system.processor.create_ticket(
            interaction.guild,
            interaction.user,
            ticket_type
        )
        
        if ticket_channel:
            await interaction.followup.send(
                f"Ticket created! Please check {ticket_channel.mention}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Failed to create ticket. Please try again later or contact an administrator.",
                ephemeral=True
            )

class TicketManagementView(ui.View):
    """View for ticket management with close and other actions"""
    
    def __init__(self, system):
        super().__init__(timeout=None)  # Persistent view
        self.system = system
    
    @ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        """Close the ticket"""
        await interaction.response.defer(ephemeral=True)
        
        # Check if user is allowed to close the ticket
        ticket = await self.system.storage.get_ticket(interaction.channel.id)
        if not ticket:
            await interaction.followup.send("This doesn't appear to be a valid ticket channel.", ephemeral=True)
            return
        
        # Check if user is ticket creator or has permission
        is_creator = ticket["user_id"] == interaction.user.id
        is_staff = False
        
        # Get settings to check for staff roles
        settings = await self.system.get_settings(interaction.guild.id)
        staff_roles = settings.get("moderator_roles", [])
        
        # Check if user has any staff roles
        for role in interaction.user.roles:
            if role.id in staff_roles:
                is_staff = True
                break
        
        if not (is_creator or is_staff):
            await interaction.followup.send("You don't have permission to close this ticket.", ephemeral=True)
            return
        
        # Close the ticket
        success = await self.system.processor.close_ticket(interaction.channel, interaction.user)
        
        if success:
            await interaction.followup.send("Ticket will be closed shortly.", ephemeral=True)
        else:
            await interaction.followup.send("Failed to close the ticket. Please try again later.", ephemeral=True)

class ClosedTicketView(ui.View):
    """View for closed tickets"""
    
    def __init__(self, system):
        super().__init__(timeout=None)  # Persistent view
        self.system = system
    
    @ui.button(label="Delete Now", style=discord.ButtonStyle.danger, custom_id="ticket_delete_now")
    async def delete_now(self, interaction: discord.Interaction, button: ui.Button):
        """Delete the channel immediately"""
        await interaction.response.defer(ephemeral=True)
        
        # Check permissions
        settings = await self.system.get_settings(interaction.guild.id)
        staff_roles = settings.get("moderator_roles", [])
        
        is_staff = False
        for role in interaction.user.roles:
            if role.id in staff_roles:
                is_staff = True
                break
        
        if not is_staff:
            await interaction.followup.send("You don't have permission to delete this ticket.", ephemeral=True)
            return
        
        # Delete the channel
        try:
            await interaction.followup.send("Deleting this channel now...", ephemeral=True)
            await interaction.channel.delete(reason=f"Ticket manually deleted by {interaction.user}")
        except Exception as e:
            print(f"Failed to delete channel: {e}")
            await interaction.followup.send("Failed to delete the channel.", ephemeral=True)
