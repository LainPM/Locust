# systems/tickets/processor.py
import discord
import asyncio
import datetime
from typing import Dict, List, Any, Optional

class TicketProcessor:
    """Processor component for the Ticket system"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
    
    async def setup(self, guild: discord.Guild, 
                  ticket_panel: discord.TextChannel,
                  transcript_channel: discord.TextChannel,
                  ticket_category: discord.CategoryChannel,
                  ticket_types: str,
                  moderator_roles: str,
                  panel_title: str,
                  panel_description: str) -> bool:
        """Set up the ticket system for a guild"""
        try:
            # Parse ticket types
            ticket_types_list = [t.strip() for t in ticket_types.split(',') if t.strip()]
            if not ticket_types_list:
                ticket_types_list = ["Support", "Bug Report", "Other"]
            
            # Parse moderator roles
            moderator_roles_list = []
            for role_str in moderator_roles.split(','):
                role_str = role_str.strip()
                
                # Check if it's a role mention
                if role_str.startswith('<@&') and role_str.endswith('>'):
                    role_id = int(role_str[3:-1])
                    moderator_roles_list.append(role_id)
                # Check if it's a role ID
                elif role_str.isdigit():
                    role_id = int(role_str)
                    moderator_roles_list.append(role_id)
                # Try to find role by name
                else:
                    role = discord.utils.get(guild.roles, name=role_str)
                    if role:
                        moderator_roles_list.append(role.id)
            
            # Update settings
            guild_id = guild.id
            settings = {
                "guild_id": guild_id,
                "enabled": True,
                "panel_channel_id": ticket_panel.id,
                "transcript_channel_id": transcript_channel.id,
                "ticket_category_id": ticket_category.id,
                "ticket_types": ticket_types_list,
                "moderator_roles": moderator_roles_list,
                "panel_title": panel_title,
                "panel_description": panel_description,
                "updated_at": datetime.datetime.now().isoformat()
            }
            
            # Save settings
            await self.system.storage.update_settings(guild_id, settings)
            
            # Create the panel message
            await self._create_panel_message(guild_id, ticket_panel, settings)
            
            return True
        except Exception as e:
            print(f"Error setting up ticket system: {e}")
            return False
    
    async def _create_panel_message(self, guild_id: int, channel: discord.TextChannel, settings: Dict[str, Any]):
        """Create the ticket panel message"""
        # Create embed
        embed = discord.Embed(
            title=settings["panel_title"],
            description=settings["panel_description"],
            color=discord.Color.blue()
        )
        
        # Create view with buttons for each ticket type
        from systems.tickets.views import TicketPanelView
        view = TicketPanelView(self.system)
        
        # Send the panel message
        await channel.send(embed=embed, view=view)
    
    async def create_ticket(self, guild: discord.Guild, user: discord.User, ticket_type: str) -> Optional[discord.TextChannel]:
        """Create a new ticket"""
        try:
            # Get settings
            guild_id = guild.id
            settings = await self.system.get_settings(guild_id)
            
            # Check if enabled
            if not settings.get("enabled", False):
                return None
            
            # Get category
            category_id = settings.get("ticket_category_id")
            if not category_id:
                return None
                
            category = guild.get_channel(category_id)
            if not category:
                return None
            
            # Create ticket channel
            channel_name = f"ticket-{user.name}-{ticket_type.lower().replace(' ', '-')}"
            
            # Create permissions overrides
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }
            
            # Add moderator role overwrites
            for role_id in settings.get("moderator_roles", []):
                role = guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            # Create the channel
            ticket_channel = await category.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                topic=f"Ticket for {user.display_name} - Type: {ticket_type}"
            )
            
            # Store ticket in database
            await self.system.storage.create_ticket(
                guild_id,
                user.id,
                ticket_channel.id,
                ticket_type
            )
            
            # Send initial message
            await self._send_initial_message(ticket_channel, user, ticket_type)
            
            return ticket_channel
        except Exception as e:
            print(f"Error creating ticket: {e}")
            return None
    
    async def _send_initial_message(self, channel: discord.TextChannel, user: discord.User, ticket_type: str):
        """Send the initial ticket message"""
        # Create embed
        embed = discord.Embed(
            title=f"New {ticket_type} Ticket",
            description=f"Thank you for opening a ticket, {user.mention}. Support staff will assist you shortly.",
            color=discord.Color.green()
        )
        
        # Create view with ticket controls
        from systems.tickets.views import TicketManagementView
        view = TicketManagementView(self.system)
        
        # Send message
        await channel.send(f"{user.mention}", embed=embed, view=view)
    
    async def close_ticket(self, channel: discord.TextChannel, user: discord.User) -> bool:
        """Close a ticket"""
        try:
            # Get ticket data
            ticket = await self.system.storage.get_ticket(channel.id)
            if not ticket:
                return False
            
            # Close the ticket in database
            await self.system.storage.close_ticket(channel.id, user.id)
            
            # Create transcript
            transcript = await self._create_transcript(channel)
            
            # Send transcript to transcript channel if configured
            guild_id = ticket["guild_id"]
            settings = await self.system.get_settings(guild_id)
            
            transcript_channel_id = settings.get("transcript_channel_id")
            if transcript_channel_id:
                transcript_channel = self.bot.get_channel(transcript_channel_id)
                if transcript_channel:
                    # Send transcript
                    embed = discord.Embed(
                        title=f"Ticket Transcript - {channel.name}",
                        description=f"Ticket closed by <@{user.id}>",
                        color=discord.Color.blue(),
                        timestamp=datetime.datetime.now()
                    )
                    
                    await transcript_channel.send(embed=embed, file=transcript)
            
            # Send closing message in ticket channel
            embed = discord.Embed(
                title="Ticket Closed",
                description=f"This ticket has been closed by {user.mention}. This channel will be deleted in 10 seconds.",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now()
            )
            
            from systems.tickets.views import ClosedTicketView
            view = ClosedTicketView(self.system)
            
            await channel.send(embed=embed, view=view)
            
            # Schedule channel deletion
            await asyncio.sleep(10)
            try:
                await channel.delete(reason=f"Ticket closed by {user}")
            except:
                pass  # Channel might be deleted already
            
            return True
        except Exception as e:
            print(f"Error closing ticket: {e}")
            return False
    
    async def _create_transcript(self, channel: discord.TextChannel) -> discord.File:
        """Create a transcript file of the ticket"""
        # Simple text transcript for now
        transcript_content = f"Transcript of ticket #{channel.id} - {channel.name}\n"
        transcript_content += f"Created at: {channel.created_at}\n"
        transcript_content += f"-----------------------------------\n\n"
        
        try:
            # Get all messages
            messages = []
            async for message in channel.history(limit=500, oldest_first=True):
                messages.append(message)
            
            # Format each message
            for message in messages:
                timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                transcript_content += f"[{timestamp}] {message.author.display_name}: {message.content}\n"
                
                # Add attachments
                for attachment in message.attachments:
                    transcript_content += f"[Attachment: {attachment.filename} - {attachment.url}]\n"
                
                transcript_content += "\n"
            
            # Create file
            import io
            transcript_file = discord.File(
                io.BytesIO(transcript_content.encode()),
                filename=f"transcript-{channel.name}.txt"
            )
            
            return transcript_file
        except Exception as e:
            print(f"Error creating transcript: {e}")
            
            # Return empty transcript in case of error
            empty_content = f"Could not generate transcript due to an error: {str(e)}"
            return discord.File(
                io.BytesIO(empty_content.encode()),
                filename=f"transcript-error-{channel.name}.txt"
            )
