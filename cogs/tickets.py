import os
import discord
from discord.ext import commands
from discord import app_commands, ui
import io
from datetime import datetime
import asyncio
from typing import Optional, List, Dict, Any

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Use the bot's MongoDB connection
        self.mongo_client = bot.mongo_client
        self.db = self.mongo_client["ticket_system"]
        self.config_col = self.db["config"]
        self.tickets_col = self.db["tickets"]
        self.transcripts_col = self.db["transcripts"]
        
        # Add persistent views on startup
        bot.loop.create_task(self.register_persistent_views())
    
    async def register_persistent_views(self):
        """Register persistent views for tickets when cog is loaded"""
        await self.bot.wait_until_ready()
        
        # Register the generic ticket panel view for all configs
        self.bot.add_view(TicketPanelView(self.bot))
        
        # Register the ticket management views
        self.bot.add_view(TicketManagementView(self.bot))
        
        print("Ticket System persistent views registered")
    
    async def get_config(self, guild_id: int):
        """Get ticket configuration for a guild"""
        return await self.config_col.find_one({"guild_id": guild_id})

    @app_commands.command(name="setup_ticket_system", description="Setup the ticketing system")
    @app_commands.describe(
        ticket_panel='Channel to post the ticket panel',
        transcript_channel='Channel to send transcripts',
        ticket_category='Category to create tickets under',
        ticket_types='Comma-separated ticket types (e.g. Support,Bug)',
        moderator_roles='Comma-separated role IDs or @roles',
        panel_title='Title for the ticket panel embed (optional)',
        panel_description='Description for the ticket panel embed (optional)'
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_ticket_system(
        self, interaction: discord.Interaction,
        ticket_panel: discord.TextChannel,
        transcript_channel: discord.TextChannel,
        ticket_category: discord.CategoryChannel,
        ticket_types: str,
        moderator_roles: str,
        panel_title: Optional[str] = "Ticket Support",
        panel_description: Optional[str] = "Click a button below to create a ticket"
    ):
        """Setup the ticket system with customizable panel"""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild.id
        
        # Parse ticket types and moderator roles
        types = [t.strip() for t in ticket_types.split(',')]
        
        # Handle role mentions or IDs
        role_ids = []
        for role_str in moderator_roles.split(','):
            role_str = role_str.strip()
            # Extract role ID from mention if needed
            if role_str.startswith('<@&') and role_str.endswith('>'):
                role_str = role_str[3:-1]
            
            try:
                role_id = int(role_str)
                role_ids.append(role_id)
            except ValueError:
                continue
        
        # Create or update config in MongoDB
        await self.config_col.update_one(
            {"guild_id": guild_id},
            {"$set": {
                "ticket_panel_id": ticket_panel.id,
                "transcript_channel_id": transcript_channel.id,
                "ticket_category_id": ticket_category.id,
                "ticket_types": types,
                "mod_roles": role_ids,
                "panel_title": panel_title,
                "panel_description": panel_description
            }},
            upsert=True
        )

        # Create and send the ticket panel
        embed = discord.Embed(
            title=panel_title,
            description=panel_description,
            color=discord.Color.blurple()
        )
        
        # Create a dynamic view with buttons for each ticket type
        view = TicketPanelView(self.bot)
        view.add_ticket_buttons(types)
        
        try:
            message = await ticket_panel.send(embed=embed, view=view)
            
            # Update config with message ID for persistent views
            await self.config_col.update_one(
                {"guild_id": guild_id},
                {"$set": {"panel_message_id": message.id}}
            )
            
            await interaction.followup.send("Ticket system set up successfully!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error sending ticket panel: {e}", ephemeral=True)

    @app_commands.command(name="ticket_stats", description="View ticket statistics")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def ticket_stats(self, interaction: discord.Interaction):
        """View statistics about tickets in the server"""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild.id
        
        try:
            # Get ticket statistics
            total_tickets = await self.tickets_col.count_documents({"guild_id": guild_id})
            open_tickets = await self.tickets_col.count_documents({"guild_id": guild_id, "status": "open"})
            closed_tickets = await self.tickets_col.count_documents({"guild_id": guild_id, "status": "closed"})
            deleted_tickets = await self.tickets_col.count_documents({"guild_id": guild_id, "status": "deleted"})
            
            embed = discord.Embed(
                title="Ticket Statistics",
                color=discord.Color.blue()
            )
            embed.add_field(name="Total Tickets", value=str(total_tickets), inline=True)
            embed.add_field(name="Open Tickets", value=str(open_tickets), inline=True)
            embed.add_field(name="Closed Tickets", value=str(closed_tickets), inline=True)
            embed.add_field(name="Deleted Tickets", value=str(deleted_tickets), inline=True)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error retrieving ticket statistics: {e}", ephemeral=True)

    async def create_ticket(self, interaction: discord.Interaction, ticket_type: str):
        """Create a new ticket"""
        try:
            guild_id = interaction.guild.id
            
            # Get ticket config
            config = await self.get_config(guild_id)
            if not config:
                return await interaction.followup.send("Ticket system not configured!", ephemeral=True)
            
            # Get next case number
            case_count = await self.tickets_col.count_documents({"guild_id": guild_id})
            case_number = case_count + 1
            
            # Set up channel permissions
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
            }
            
            # Add mod role permissions
            for role_id in config["mod_roles"]:
                role = interaction.guild.get_role(int(role_id))
                if role:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
            
            # Create the ticket channel
            category = interaction.guild.get_channel(config["ticket_category_id"])
            if not category:
                return await interaction.followup.send("Ticket category not found!", ephemeral=True)
            
            # Create safe channel name
            safe_username = ''.join(c for c in interaction.user.name if c.isalnum() or c in '-_')
            channel_name = f"{ticket_type.lower()}-{case_number}-{safe_username}"
            if len(channel_name) > 100:  # Discord channel name length limit
                channel_name = channel_name[:100]
            
            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket {case_number} | Created by {interaction.user} | Type: {ticket_type}"
            )
            
            # Store ticket in MongoDB
            timestamp = datetime.utcnow()
            ticket_id = await self.tickets_col.insert_one({
                "guild_id": guild_id,
                "channel_id": channel.id,
                "user_id": interaction.user.id,
                "case_number": case_number,
                "ticket_type": ticket_type,
                "status": "open",
                "created_at": timestamp,
                "updated_at": timestamp,
                "users_involved": [interaction.user.id],
                "message_count": 0,
                "attachments_saved": 0,
                "attachments_skipped": 0
            })
            
            # Create welcome embed
            embed = discord.Embed(
                title=f"Ticket {case_number}: {ticket_type}",
                description=f"Thank you for creating a ticket, {interaction.user.mention}. A staff member will be with you shortly.",
                color=discord.Color.green(),
                timestamp=timestamp
            )
            embed.add_field(name="Case ID", value=str(case_number), inline=True)
            embed.add_field(name="Status", value="Open", inline=True)
            embed.add_field(name="Created By", value=interaction.user.mention, inline=True)
            embed.set_footer(text=f"Ticket ID: {channel.id}")
            
            # Create management view with close button
            view = TicketManagementView(self.bot)
            
            # Send and pin welcome message
            welcome_msg = await channel.send(
                content=f"{interaction.user.mention} Welcome to your ticket!",
                embed=embed,
                view=view
            )
            
            try:
                await welcome_msg.pin()
            except Exception as e:
                print(f"Error pinning message: {e}")
            
            # Send confirmation to user
            await interaction.followup.send(
                f"Ticket created: {channel.mention}\nCase ID: {case_number}",
                ephemeral=True
            )
            
            return channel
            
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to create channels!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error creating ticket: {e}", ephemeral=True)
        
        return None

    async def close_ticket(self, interaction: discord.Interaction, reason: str = "Closed by user"):
        """Close a ticket"""
        channel = interaction.channel
        guild_id = interaction.guild.id
        
        try:
            # Get ticket data
            ticket_data = await self.tickets_col.find_one(
                {"guild_id": guild_id, "channel_id": channel.id}
            )
            
            if not ticket_data:
                return await interaction.followup.send("This channel is not a ticket!", ephemeral=True)
            
            if ticket_data["status"] == "closed":
                return await interaction.followup.send("This ticket is already closed!", ephemeral=True)
            
            # Update ticket status
            timestamp = datetime.utcnow()
            await self.tickets_col.update_one(
                {"guild_id": guild_id, "channel_id": channel.id},
                {"$set": {
                    "status": "closed",
                    "updated_at": timestamp,
                    "closed_by": interaction.user.id,
                    "close_reason": reason
                }}
            )
            
            # Rename channel
            current_name = channel.name
            if not current_name.endswith("-closed"):
                try:
                    await channel.edit(name=f"{current_name}-closed")
                except Exception as e:
                    print(f"Error renaming channel: {e}")
            
            # Remove permissions from ticket creator
            creator_id = ticket_data.get("user_id")
            if creator_id:
                creator = interaction.guild.get_member(creator_id)
                if creator:
                    try:
                        await channel.set_permissions(creator, send_messages=False)
                    except Exception as e:
                        print(f"Error updating permissions: {e}")
            
            # Send closed message
            embed = discord.Embed(
                title=f"Ticket {ticket_data.get('case_number')} Closed",
                description=f"This ticket has been closed by {interaction.user.mention}\nReason: {reason}",
                color=discord.Color.red(),
                timestamp=timestamp
            )
            
            # Create closed ticket view with actions
            view = TicketActionView(self.bot)
            
            await interaction.followup.send(embed=embed, view=view)
            return True
            
        except Exception as e:
            await interaction.followup.send(f"Error closing ticket: {e}", ephemeral=True)
            return False

    async def reopen_ticket(self, interaction: discord.Interaction):
        """Reopen a closed ticket"""
        channel = interaction.channel
        guild_id = interaction.guild.id
        
        try:
            # Get ticket data
            ticket_data = await self.tickets_col.find_one(
                {"guild_id": guild_id, "channel_id": channel.id}
            )
            
            if not ticket_data:
                return await interaction.followup.send("This channel is not a ticket!", ephemeral=True)
            
            if ticket_data["status"] != "closed":
                return await interaction.followup.send("This ticket is not closed!", ephemeral=True)
            
            # Update ticket status
            timestamp = datetime.utcnow()
            await self.tickets_col.update_one(
                {"guild_id": guild_id, "channel_id": channel.id},
                {"$set": {
                    "status": "open",
                    "updated_at": timestamp,
                    "reopened_by": interaction.user.id,
                    "reopened_at": timestamp
                }}
            )
            
            # Rename channel - remove -closed suffix
            current_name = channel.name
            if current_name.endswith("-closed"):
                try:
                    await channel.edit(name=current_name.replace("-closed", ""))
                except Exception as e:
                    print(f"Error renaming channel: {e}")
            
            # Restore permissions for ticket creator
            creator_id = ticket_data.get("user_id")
            if creator_id:
                creator = interaction.guild.get_member(creator_id)
                if creator:
                    try:
                        await channel.set_permissions(creator, view_channel=True, send_messages=True)
                    except Exception as e:
                        print(f"Error updating permissions: {e}")
            
            # Send reopened message
            embed = discord.Embed(
                title=f"Ticket {ticket_data.get('case_number')}: {ticket_data.get('ticket_type')}",
                description=f"This ticket has been reopened by {interaction.user.mention}",
                color=discord.Color.green(),
                timestamp=timestamp
            )
            embed.add_field(name="Case ID", value=str(ticket_data.get('case_number')), inline=True)
            embed.add_field(name="Status", value="Open", inline=True)
            
            # Add ticket management view again
            view = TicketManagementView(self.bot)
            
            await interaction.followup.send(embed=embed, view=view)
            return True
            
        except Exception as e:
            await interaction.followup.send(f"Error reopening ticket: {e}", ephemeral=True)
            return False

    async def delete_ticket(self, interaction: discord.Interaction, confirm: bool = False):
        """Delete a ticket channel"""
        channel = interaction.channel
        guild_id = interaction.guild.id
        
        if not confirm:
            # Check if a transcript exists first
            transcript_exists = False
            try:
                transcript = await self.transcripts_col.find_one(
                    {"guild_id": guild_id, "channel_id": channel.id}
                )
                transcript_exists = transcript is not None
            except Exception as e:
                print(f"Error checking transcript: {e}")
            
            if not transcript_exists:
                # No transcript - show confirmation
                embed = discord.Embed(
                    title="⚠️ Warning: No Transcript",
                    description="No transcript has been generated for this ticket.\nIf you continue, all ticket history will be permanently lost.",
                    color=discord.Color.gold()
                )
                
                view = TicketDeleteConfirmView(self.bot)
                await interaction.followup.send(embed=embed, view=view)
                return False
        
        # Update ticket status
        try:
            timestamp = datetime.utcnow()
            await self.tickets_col.update_one(
                {"guild_id": guild_id, "channel_id": channel.id},
                {"$set": {
                    "status": "deleted",
                    "deleted_at": timestamp,
                    "deleted_by": interaction.user.id
                }}
            )
            
            # Send deletion message and delay
            await channel.send("🗑️ **Deleting ticket in 3 seconds...**")
            await asyncio.sleep(3)
            
            # Delete the channel
            await channel.delete()
            return True
            
        except Exception as e:
            print(f"Error deleting ticket: {e}")
            await interaction.followup.send(f"Error deleting ticket: {e}", ephemeral=True)
            return False

    async def generate_transcript(self, interaction: discord.Interaction):
        """Generate and send a transcript of the ticket"""
        channel = interaction.channel
        guild_id = interaction.guild.id
        
        try:
            # Get ticket data
            ticket_data = await self.tickets_col.find_one(
                {"guild_id": guild_id, "channel_id": channel.id}
            )
            
            if not ticket_data:
                return await interaction.followup.send("This channel is not a ticket!", ephemeral=True)
            
            # Get config
            config = await self.get_config(guild_id)
            if not config:
                return await interaction.followup.send("Ticket system config not found!", ephemeral=True)
            
            transcript_channel_id = config.get("transcript_channel_id")
            transcript_channel = interaction.guild.get_channel(transcript_channel_id)
            
            if not transcript_channel:
                return await interaction.followup.send("Transcript channel not found!", ephemeral=True)
            
            # Get message history
            history = [msg async for msg in channel.history(limit=None, oldest_first=True)]
            
            # Count messages per user
            user_messages = {}
            for msg in history:
                if msg.author.id not in user_messages:
                    user_messages[msg.author.id] = 1
                else:
                    user_messages[msg.author.id] += 1
            
            # Update user involvement in ticket data
            users_involved = list(user_messages.keys())
            await self.tickets_col.update_one(
                {"guild_id": guild_id, "channel_id": channel.id},
                {"$set": {
                    "users_involved": users_involved,
                    "message_count": len(history)
                }}
            )
            
            # Build transcript content
            server_info = (
                f"<Server-Info> "
                f"Server: {interaction.guild.name} ({interaction.guild.id}) "
                f"Channel: {channel.name} ({channel.id}) "
                f"Messages: {len(history)} "
            )
            
            user_info = "<User-Info> "
            for i, (user_id, msg_count) in enumerate(user_messages.items(), 1):
                user = interaction.guild.get_member(user_id)
                if user:
                    user_name = f"{user.name}"
                    if hasattr(user, 'discriminator') and user.discriminator != '0':
                        user_name += f"#{user.discriminator}"
                    user_info += f"\n{i} - {user_name} ({user_id}): {msg_count}"
            
            transcript_content = "<Transcript> "
            for msg in history:
                timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M')
                author_name = f"{msg.author.name}"
                if hasattr(msg.author, 'discriminator') and msg.author.discriminator != '0':
                    author_name += f"#{msg.author.discriminator}"
                
                content = msg.content or "[No content]"
                # Escape HTML tags
                content = content.replace('<', '&lt;').replace('>', '&gt;')
                
                transcript_content += f"\n[{timestamp}] {author_name}: {content}"
                
                # Add attachments
                if msg.attachments:
                    for attachment in msg.attachments:
                        transcript_content += f"\n[{timestamp}] {author_name} [Attachment]: {attachment.url}"
            
            # Combine all sections with proper formatting
            full_transcript = f"<html><body><pre>{server_info}\n\n{user_info}\n\n{transcript_content}</pre></body></html>"
            
            # Save transcript to database
            timestamp = datetime.utcnow()
            result = await self.transcripts_col.insert_one({
                "guild_id": guild_id,
                "channel_id": channel.id,
                "case_number": ticket_data.get("case_number"),
                "transcript_html": full_transcript,
                "timestamp": timestamp,
                "generated_by": interaction.user.id
            })
            
            # Create transcript file
            data = io.BytesIO(full_transcript.encode('utf-8'))
            filename = f"ticket-{ticket_data.get('case_number')}-{channel.name}.html"
            
            # Create embed
            embed = discord.Embed(
                title=f"Ticket Transcript: Case #{ticket_data.get('case_number')}",
                description=f"Transcript for ticket {channel.mention}",
                color=discord.Color.blue(),
                timestamp=timestamp
            )
            embed.add_field(name="Ticket Type", value=ticket_data.get("ticket_type"), inline=True)
            embed.add_field(name="Created By", value=f"<@{ticket_data.get('user_id')}>", inline=True)
            embed.add_field(name="Messages", value=str(len(history)), inline=True)
            
            # Add closure information if available
            if ticket_data.get('status') == 'closed':
                close_reason = ticket_data.get("close_reason", "Not specified")
                embed.add_field(name="Close Reason", value=close_reason, inline=False)
                
                # Add who closed it and when
                closed_by = ticket_data.get("closed_by")
                if closed_by:
                    embed.add_field(name="Closed By", value=f"<@{closed_by}>", inline=True)
            
            # Send file to transcript channel
            discord_file = discord.File(data, filename=filename)
            transcript_msg = await transcript_channel.send(embed=embed, file=discord_file)
            
            # Get transcript URL and update database
            if transcript_msg.attachments:
                transcript_url = transcript_msg.attachments[0].url
                
                # Add view button to message
                view = discord.ui.View()
                view.add_item(discord.ui.Button(
                    label="View Transcript",
                    style=discord.ButtonStyle.link,
                    url=transcript_url
                ))
                
                await transcript_msg.edit(view=view)
                
                # Update transcript URL in database
                await self.transcripts_col.update_one(
                    {"_id": result.inserted_id},
                    {"$set": {"url": transcript_url}}
                )
                
                # Send confirmation to user
                await interaction.followup.send(
                    f"Transcript generated and sent to {transcript_channel.mention}\n"
                    f"[View Transcript]({transcript_url})",
                    ephemeral=True
                )
                
                return True
            else:
                await interaction.followup.send(
                    f"Transcript generated and sent to {transcript_channel.mention}, but there was an issue getting the URL.",
                    ephemeral=True
                )
                return False
                
        except Exception as e:
            await interaction.followup.send(f"Error generating transcript: {e}", ephemeral=True)
            return False


class TicketPanelView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    def add_ticket_buttons(self, ticket_types: List[str]):
        """Add ticket type buttons to the view"""
        self.clear_items()  # Remove any existing buttons
        
        for i, ticket_type in enumerate(ticket_types):
            button = ui.Button(
                style=discord.ButtonStyle.primary,
                label=ticket_type,
                custom_id=f"ticket_panel:create:{ticket_type}",
                row=i // 5  # Max 5 buttons per row
            )
            button.callback = self.button_callback
            self.add_item(button)
    
    async def button_callback(self, interaction: discord.Interaction):
        """Handle ticket creation button press"""
        await interaction.response.defer(ephemeral=True)
        
        # Extract ticket type from custom_id
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("ticket_panel:create:"):
            return await interaction.followup.send("Invalid button!", ephemeral=True)
        
        ticket_type = custom_id.split(":", 2)[2]
        
        # Create the ticket
        ticket_cog = self.bot.get_cog("TicketSystem")
        if ticket_cog:
            await ticket_cog.create_ticket(interaction, ticket_type)
        else:
            await interaction.followup.send("Ticket system not found!", ephemeral=True)


class TicketManagementView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        
        # Add close button
        close_btn = ui.Button(
            label="Close Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="ticket:close",
            emoji="🔒"
        )
        close_btn.callback = self.close_callback
        self.add_item(close_btn)
    
    async def close_callback(self, interaction: discord.Interaction):
        """Handle close button press"""
        await interaction.response.defer(ephemeral=False)
        
        # Create confirmation modal
        modal = CloseTicketModal(self.bot)
        await interaction.followup.send_modal(modal)


class CloseTicketModal(ui.Modal, title="Close Ticket"):
    """Modal for closing a ticket with a reason"""
    reason = ui.TextInput(
        label="Reason",
        placeholder="Why are you closing this ticket?",
        required=False,
        max_length=100
    )
    
    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        
        # Get the reason
        reason = self.reason.value or "Closed by user"
        
        # Close the ticket
        ticket_cog = self.bot.get_cog("TicketSystem")
        if ticket_cog:
            await ticket_cog.close_ticket(interaction, reason)
        else:
            await interaction.followup.send("Ticket system not found!", ephemeral=True)


class TicketActionView(ui.View):
    """View for closed ticket actions"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        
        # Add action buttons
        transcript_btn = ui.Button(
            label="Transcript",
            style=discord.ButtonStyle.primary,
            custom_id="ticket:transcript",
            emoji="📝"
        )
        transcript_btn.callback = self.transcript_callback
        
        reopen_btn = ui.Button(
            label="Reopen",
            style=discord.ButtonStyle.success,
            custom_id="ticket:reopen",
            emoji="🔓"
        )
        reopen_btn.callback = self.reopen_callback
        
        delete_btn = ui.Button(
            label="Delete",
            style=discord.ButtonStyle.danger,
            custom_id="ticket:delete",
            emoji="🗑️"
        )
        delete_btn.callback = self.delete_callback
        
        self.add_item(transcript_btn)
        self.add_item(reopen_btn)
        self.add_item(delete_btn)
    
    async def transcript_callback(self, interaction: discord.Interaction):
        """Generate transcript"""
        await interaction.response.defer(ephemeral=True)
        
        ticket_cog = self.bot.get_cog("TicketSystem")
        if ticket_cog:
            await ticket_cog.generate_transcript(interaction)
        else:
            await interaction.followup.send("Ticket system not found!", ephemeral=True)
    
    async def reopen_callback(self, interaction: discord.Interaction):
        """Reopen the ticket"""
        await interaction.response.defer(ephemeral=False)
        
        ticket_cog = self.bot.get_cog("TicketSystem")
        if ticket_cog:
            success = await ticket_cog.reopen_ticket(interaction)
            if success:
                # Remove this view from the message to prevent duplicate reopens
                try:
                    await interaction.message.edit(view=None)
                except:
                    pass
        else:
            await interaction.followup.send("Ticket system not found!", ephemeral=True)
    
    async def delete_callback(self, interaction: discord.Interaction):
        """Delete the ticket"""
        await interaction.response.defer(ephemeral=True)
        
        ticket_cog = self.bot.get_cog("TicketSystem")
        if ticket_cog:
            await ticket_cog.delete_ticket(interaction)
        else:
            await interaction.followup.send("Ticket system not found!", ephemeral=True)


class TicketDeleteConfirmView(ui.View):
    """View for confirming ticket deletion"""
    def __init__(self, bot):
        super().__init__(timeout=60)  # 60 second timeout
        self.bot = bot
        
        # Add confirm/cancel buttons
        confirm_btn = ui.Button(
            label="Yes, Delete",
            style=discord.ButtonStyle.danger,
            custom_id="ticket:delete:confirm"
        )
        confirm_btn.callback = self.confirm_callback
        
        cancel_btn = ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            custom_id="ticket:delete:cancel"
        )
        cancel_btn.callback = self.cancel_callback
        
        self.add_item(confirm_btn)
        self.add_item(cancel_btn)
    
    async def confirm_callback(self, interaction: discord.Interaction):
        """Confirm ticket deletion"""
        await interaction.response.defer(ephemeral=True)
        
        # Delete the confirmation message
        try:
            await interaction.message.delete()
        except:
            pass
        
        # Delete the ticket
        ticket_cog = self.bot.get_cog("TicketSystem")
        if ticket_cog:
            await ticket_cog.delete_ticket(interaction, confirm=True)
        else:
            await interaction.followup.send("Ticket system not found!", ephemeral=True)
    
    async def cancel_callback(self, interaction: discord.Interaction):
        """Cancel ticket deletion"""
        await interaction.response.defer(ephemeral=True)
        
        # Delete the confirmation message
        try:
            await interaction.message.delete()
        except:
            pass
        
        await interaction.followup.send("Ticket deletion cancelled.", ephemeral=True)


async def setup(bot):
    """Add the TicketSystem cog to the bot"""
    await bot.add_cog(TicketSystem(bot))
