import os
import discord
from discord.ext import commands
from discord import app_commands, ui
import io
from datetime import datetime
import asyncio
from typing import Optional, List, Dict, Any

# MongoDB setup
class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Use the bot's MongoDB connection
        self.db = bot.mongo_client["ticket_system"]
        self.config_col = self.db["config"]
        self.tickets_col = self.db["tickets"]
        self.transcripts_col = self.db["transcripts"]

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
        guild_id = interaction.guild.id
        
        # Parse ticket types and moderator roles
        types = [t.strip() for t in ticket_types.split(',')]
        roles = [int(r.strip('<@&> ')) for r in moderator_roles.split(',')]
        
        # Create or update config in MongoDB
        await self.config_col.update_one(
            {"guild_id": guild_id},
            {"$set": {
                "ticket_panel_id": ticket_panel.id,
                "transcript_channel_id": transcript_channel.id,
                "ticket_category_id": ticket_category.id,
                "ticket_types": types,
                "mod_roles": roles,
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
        
        view = TicketPanelView(self.bot, types)
        message = await ticket_panel.send(embed=embed, view=view)
        
        # Make view persistent
        self.bot.add_view(view, message_id=message.id)
        
        await interaction.response.send_message("Ticket system set up successfully!", ephemeral=True)

    @app_commands.command(name="stats", description="View ticket statistics")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def ticket_stats(self, interaction: discord.Interaction):
        """View statistics about tickets in the server"""
        guild_id = interaction.guild.id
        
        # Get ticket statistics
        total_tickets = await self.tickets_col.count_documents({"guild_id": guild_id})
        open_tickets = await self.tickets_col.count_documents({"guild_id": guild_id, "status": "open"})
        closed_tickets = await self.tickets_col.count_documents({"guild_id": guild_id, "status": "closed"})
        
        embed = discord.Embed(
            title="Ticket Statistics",
            color=discord.Color.blue()
        )
        embed.add_field(name="Total Tickets", value=str(total_tickets), inline=True)
        embed.add_field(name="Open Tickets", value=str(open_tickets), inline=True)
        embed.add_field(name="Closed Tickets", value=str(closed_tickets), inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class TicketPanelView(ui.View):
    def __init__(self, bot, types):
        super().__init__(timeout=None)
        self.bot = bot
        
        # Add a button for each ticket type with consistent custom_id format
        for i, t in enumerate(types):
            btn = ui.Button(
                label=t, 
                style=discord.ButtonStyle.primary, 
                custom_id=f"ticket_system:create_{t}_{i}"  # Add index to ensure uniqueness
            )
            btn.callback = self._on_ticket_button
            self.add_item(btn)

    async def _on_ticket_button(self, interaction: discord.Interaction):
        """Handle ticket creation button press"""
        try:
            # Extract ticket type from custom_id (format: "ticket_system:create_TYPE_INDEX")
            custom_id_parts = interaction.data['custom_id'].split('_')
            ticket_type = custom_id_parts[2]  # Get the ticket type part
            
            # Use a try block for the entire ticket creation process
            try:
                # Defer response to prevent timeout during channel creation
                await interaction.response.defer(ephemeral=True)
                
                # Get ticket config from MongoDB
                config = await self.bot.cogs["TicketSystem"].config_col.find_one({"guild_id": interaction.guild.id})
                if not config:
                    await interaction.followup.send("Ticket system not configured!", ephemeral=True)
                    return
                
                # Get next case number
                case_count = await self.bot.cogs["TicketSystem"].tickets_col.count_documents({})
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
                # Safe channel name - remove invalid characters
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
                await self.bot.cogs["TicketSystem"].tickets_col.insert_one({
                    "guild_id": interaction.guild.id,
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
                
                # Create ticket message with buttons
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
                
                view = OpenTicketView(self.bot)
                initial_message = await channel.send(
                    content=f"{interaction.user.mention} Welcome to your ticket!",
                    embed=embed,
                    view=view
                )
                
                # Pin the initial message
                try:
                    await initial_message.pin()
                except Exception as e:
                    print(f"Error pinning message: {e}")
                
                # Add view to bot's persistent views
                self.bot.add_view(view, message_id=initial_message.id)
                
                # Send confirmation to user
                await interaction.followup.send(
                    f"Ticket created: {channel.mention}\nCase ID: {case_number}",
                    ephemeral=True
                )
                
            except discord.Forbidden:
                await interaction.followup.send("I don't have permission to create channels!", ephemeral=True)
            except discord.HTTPException as e:
                await interaction.followup.send(f"Error creating ticket: {e}", ephemeral=True)
            except Exception as e:
                print(f"Unexpected error creating ticket: {e}")
                await interaction.followup.send("An unexpected error occurred. Please try again or contact an administrator.", ephemeral=True)
                
        except Exception as e:
            # Catch any errors in the button handler itself
            print(f"Error in ticket button handler: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("An error occurred. Please try again.", ephemeral=True)
            except:
                pass  # If we can't respond, just continue

class OpenTicketView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        
        # Use a custom_id that includes "close_ticket" to make it persistent
        btn = ui.Button(
            label="Close Ticket", 
            style=discord.ButtonStyle.danger, 
            custom_id="ticket_system:close_ticket",
            emoji="🔒"
        )
        btn.callback = self._on_close
        self.add_item(btn)

    async def _on_close(self, interaction: discord.Interaction):
        """Handle ticket closing button press"""
        # Get the channel and guild data
        channel = interaction.channel
        guild_id = interaction.guild.id
        
        # Check if ticket exists in database
        ticket_data = await self.bot.cogs["TicketSystem"].tickets_col.find_one(
            {"guild_id": guild_id, "channel_id": channel.id}
        )
        
        if not ticket_data:
            await interaction.response.send_message(
                "Error: Ticket data not found. Please contact an administrator.",
                ephemeral=True
            )
            return
        
        # For all tickets, use the modal
        try:
            await interaction.response.send_modal(CloseModal(self.bot))
        except Exception as e:
            print(f"Error sending modal: {e}")
            await interaction.response.send_message(
                "There was an error processing your request. Please try again.",
                ephemeral=True
            )

class CloseModal(ui.Modal, title="Close Ticket"):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
    
    reason = ui.TextInput(
        label="Reason for closing",
        style=discord.TextStyle.paragraph,
        placeholder="Please provide a reason for closing this ticket.",
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        """Handle closing ticket modal submission"""
        channel = interaction.channel
        guild_id = interaction.guild.id
        
        # First check if ticket exists and get its current status
        ticket_data = await self.bot.cogs["TicketSystem"].tickets_col.find_one(
            {"guild_id": guild_id, "channel_id": channel.id}
        )
        
        # Acknowledge the interaction immediately to prevent timeout
        try:
            await interaction.response.defer(ephemeral=False)
        except Exception as e:
            print(f"Error acknowledging interaction: {e}")
            # If we can't acknowledge, the interaction might have expired
            # We'll continue with the process but send messages to the channel instead
        
        if not ticket_data:
            try:
                await interaction.followup.send(
                    "Error: Ticket data not found. Please contact an administrator.",
                    ephemeral=True
                )
            except:
                await channel.send("Error: Ticket data not found. Please contact an administrator.")
            return
            
        # Update ticket status in MongoDB
        timestamp = datetime.utcnow()
        await self.bot.cogs["TicketSystem"].tickets_col.update_one(
            {"guild_id": guild_id, "channel_id": channel.id},
            {"$set": {
                "status": "closed",
                "updated_at": timestamp,
                "closed_by": interaction.user.id,
                "close_reason": self.reason.value
            }}
        )
        
        # Rename the channel to indicate it's closed
        try:
            new_name = f"{channel.name}-closed"
            await channel.edit(name=new_name)
        except Exception as e:
            print(f"Error renaming channel: {e}")
        
        # Remove permissions from ticket creator
        ticket_data = await self.bot.cogs["TicketSystem"].tickets_col.find_one(
            {"guild_id": guild_id, "channel_id": channel.id}
        )
        creator_id = ticket_data.get("user_id")
        
        if creator_id:
            creator = interaction.guild.get_member(creator_id)
            if creator:
                # Set read-only permissions
                try:
                    await channel.set_permissions(creator, send_messages=False)
                except Exception as e:
                    print(f"Error updating permissions: {e}")
        
        # Send closed message with buttons
        embed = discord.Embed(
            title=f"Ticket {ticket_data.get('case_number')} Closed",
            description=f"This ticket has been closed by {interaction.user.mention}",
            color=discord.Color.red(),
            timestamp=timestamp
        )
        embed.add_field(name="Reason", value=self.reason.value, inline=False)
        
        view = ClosedTicketView(self.bot)
        
        # Use followup or channel.send depending on interaction state
        try:
            message = await interaction.followup.send(
                embed=embed,
                view=view,
                ephemeral=False
            )
            # Register the view with the message ID
            self.bot.add_view(view, message_id=message.id)
        except Exception as e:
            print(f"Error sending followup: {e}")
            # Fallback to sending to channel directly
            message = await channel.send(
                embed=embed,
                view=view
            )
            # Register the view with the message ID
            self.bot.add_view(view, message_id=message.id)

class ClosedTicketView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        
        # Generate transcript button with consistent custom ID
        transcript_btn = ui.Button(
            label="Generate Transcript",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_system:gen_transcript",
            emoji="📝"
        )
        transcript_btn.callback = self._gen_transcript
        
        # Delete ticket button with consistent custom ID
        delete_btn = ui.Button(
            label="Delete Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_system:delete_ticket",
            emoji="🗑️"
        )
        delete_btn.callback = self._delete_ticket
        
        # Reopen ticket button with consistent custom ID
        reopen_btn = ui.Button(
            label="Reopen Ticket",
            style=discord.ButtonStyle.success,
            custom_id="ticket_system:reopen_ticket",
            emoji="🔓"
        )
        reopen_btn.callback = self._reopen_ticket
        
        self.add_item(transcript_btn)
        self.add_item(delete_btn)
        self.add_item(reopen_btn)

    async def _gen_transcript(self, interaction: discord.Interaction):
        """Generate and send ticket transcript"""
        guild_id = interaction.guild.id
        channel_id = interaction.channel.id
        
        # Defer interaction to prevent timeout during transcript generation
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as e:
            print(f"Error deferring interaction: {e}")
        
        # Get ticket data
        ticket_data = None
        try:
            ticket_data = await self.bot.cogs["TicketSystem"].tickets_col.find_one(
                {"guild_id": guild_id, "channel_id": channel_id}
            )
        except Exception as e:
            print(f"Error retrieving ticket data: {e}")
            try:
                await interaction.followup.send("Database error. Please contact an administrator.", ephemeral=True)
            except:
                await interaction.channel.send("Database error. Please contact an administrator.")
            return
            
        if not ticket_data:
            try:
                await interaction.followup.send("Ticket not found in database. Please contact an administrator.", ephemeral=True)
            except:
                await interaction.channel.send("Ticket not found in database. Please contact an administrator.")
            return
        
        # Get config for transcript channel
        config = None
        try:
            config = await self.bot.cogs["TicketSystem"].config_col.find_one({"guild_id": guild_id})
        except Exception as e:
            print(f"Error retrieving config: {e}")
            try:
                await interaction.followup.send("Config not found. Please contact an administrator.", ephemeral=True)
            except:
                await interaction.channel.send("Config not found. Please contact an administrator.")
            return
            
        if not config:
            try:
                await interaction.followup.send("Ticket system config not found. Please contact an administrator.", ephemeral=True)
            except:
                await interaction.channel.send("Ticket system config not found. Please contact an administrator.")
            return
        
        # Get message history with error handling
        try:
            history = [msg async for msg in interaction.channel.history(limit=None, oldest_first=True)]
        except Exception as e:
            print(f"Error retrieving message history: {e}")
            try:
                await interaction.followup.send("Could not retrieve message history. Please try again.", ephemeral=True)
            except:
                await interaction.channel.send("Could not retrieve message history. Please try again.")
            return
            
        # Count messages per user
        user_messages = {}
        for msg in history:
            if msg.author.id not in user_messages:
                user_messages[msg.author.id] = 1
            else:
                user_messages[msg.author.id] += 1
        
        # Update user involvement in ticket data
        users_involved = list(user_messages.keys())
        try:
            await self.bot.cogs["TicketSystem"].tickets_col.update_one(
                {"guild_id": guild_id, "channel_id": channel_id},
                {"$set": {
                    "users_involved": users_involved,
                    "message_count": len(history)
                }}
            )
        except Exception as e:
            print(f"Error updating user involvement: {e}")
            # Not critical, continue anyway
        
        # Build server info section
        server_info = (
            f"<Server-Info> "
            f"Server: {interaction.guild.name} ({interaction.guild.id}) "
            f"Channel: {interaction.channel.name} ({interaction.channel.id}) "
            f"Messages: {len(history)} "
            f"Attachments Saved: {ticket_data.get('attachments_saved', 0)} "
            f"Attachments Skipped: {ticket_data.get('attachments_skipped', 0)}"
        )
        
        # Build user info section
        user_info = "<User-Info> "
        for i, (user_id, msg_count) in enumerate(user_messages.items(), 1):
            user = interaction.guild.get_member(user_id)
            if user:
                user_info += f"\n{i} - {user.name}#{user.discriminator if hasattr(user, 'discriminator') else '0'} ({user_id}): {msg_count}"
        
        # Build message transcript
        transcript = "<Base-Transcript> "
        for msg in history:
            timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M')
            author_name = f"{msg.author.name}#{msg.author.discriminator if hasattr(msg.author, 'discriminator') else '0'}"
            content = msg.content.replace('<', '&lt;').replace('>', '&gt;')
            transcript += f"\n[{timestamp}] {author_name}: {content}"
        
        # Add closing message if available
        if ticket_data.get('close_reason'):
            closer = interaction.guild.get_member(ticket_data.get('closed_by'))
            closer_name = closer.name if closer else "Unknown"
            transcript += f"\n[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')}] {self.bot.user.name}: Ticket is closing and transcript will be generated shortly. Closed by {closer_name} for reason: {ticket_data.get('close_reason')}"
        
        # Combine all sections
        full_transcript = f"<html><body><pre>{server_info}\n\n{user_info}\n\n{transcript}</pre></body></html>"
        
        # Save transcript to MongoDB
        transcript_id = None
        try:
            timestamp = datetime.utcnow()
            result = await self.bot.cogs["TicketSystem"].transcripts_col.insert_one({
                "case_number": ticket_data.get("case_number"),
                "guild_id": guild_id,
                "channel_id": channel_id,
                "transcript_html": full_transcript,
                "timestamp": timestamp,
                "generated_by": interaction.user.id
            })
            transcript_id = result.inserted_id
        except Exception as e:
            print(f"Error saving transcript to database: {e}")
            try:
                await interaction.followup.send("Error saving transcript to database. The transcript may not be properly recorded.", ephemeral=True)
            except:
                await interaction.channel.send("Error saving transcript to database. The transcript may not be properly recorded.")
            # Continue to try to send the file anyway
        
        # Send to transcript channel
        transcript_channel = None
        try:
            transcript_channel_id = config.get("transcript_channel_id")
            transcript_channel = interaction.guild.get_channel(transcript_channel_id)
        except Exception as e:
            print(f"Error getting transcript channel: {e}")
        
        if not transcript_channel:
            try:
                await interaction.followup.send("Transcript channel not found or accessible. Please contact an administrator.", ephemeral=True)
            except:
                await interaction.channel.send("Transcript channel not found or accessible. Please contact an administrator.")
            return
        
        # Create the transcript file
        try:
            data = io.BytesIO(full_transcript.encode('utf-8'))
            filename = f"ticket-{ticket_data.get('case_number')}-{interaction.channel.name}.html"
        except Exception as e:
            print(f"Error creating transcript file: {e}")
            try:
                await interaction.followup.send("Error creating transcript file. Please try again.", ephemeral=True)
            except:
                await interaction.channel.send("Error creating transcript file. Please try again.")
            return
        
        # Create embed with transcript info
        embed = None
        try:
            embed = discord.Embed(
                title=f"Ticket Transcript: Case #{ticket_data.get('case_number')}",
                description=f"Transcript for ticket {interaction.channel.mention}",
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
                    
                # Add reopen info if applicable
                if ticket_data.get("reopened_by"):
                    embed.add_field(name="Last Reopened By", value=f"<@{ticket_data.get('reopened_by')}>", inline=True)
        except Exception as e:
            print(f"Error creating transcript embed: {e}")
            # Create a simple embed if complex one fails
            try:
                embed = discord.Embed(
                    title=f"Ticket Transcript: Case #{ticket_data.get('case_number')}",
                    description="Error creating full transcript details",
                    color=discord.Color.red()
                )
            except:
                # If we can't even create a simple embed, we'll proceed without one
                pass
        
        # Send the transcript file with embed - prioritize reliable delivery
        transcript_url = None
        sent_message = None
        try:
            # Create file and send
            discord_file = discord.File(data, filename=filename)
            
            if embed:
                sent_message = await transcript_channel.send(embed=embed, file=discord_file)
            else:
                sent_message = await transcript_channel.send(file=discord_file)
                
            # Get the URL from the attachment
            if sent_message and sent_message.attachments:
                transcript_url = sent_message.attachments[0].url
        except Exception as e:
            print(f"Error sending transcript to channel: {e}")
            try:
                await interaction.followup.send(f"Error sending transcript to channel: {e}", ephemeral=True)
            except:
                await interaction.channel.send(f"Error sending transcript to channel: {e}")
            return
            
            # Add View Transcript button to the message
            view.add_item(discord.ui.Button(
                label="View Transcript",
                style=discord.ButtonStyle.link,
                url=transcript_url
            ))
            
            # Edit the message to add the view
            await sent_message.edit(view=view)
            
            # Update transcript URL in MongoDB
            await self.bot.cogs["TicketSystem"].transcripts_col.update_one(
                {"_id": transcript_id.inserted_id},
                {"$set": {"url": transcript_url}}
            )
            
            # Send confirmation with link to user
            await interaction.response.send_message(
                f"Transcript generated and sent to {transcript_channel.mention}\n"
                f"[View Transcript]({transcript_url})",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Transcript was generated but there was an issue with the file attachment. Please check {transcript_channel.mention}.",
                ephemeral=True
            )

    async def _delete_ticket(self, interaction: discord.Interaction):
        """Delete the ticket channel"""
        guild_id = interaction.guild.id
        channel_id = interaction.channel.id
        
        # Get ticket data to check permissions
        ticket_data = await self.bot.cogs["TicketSystem"].tickets_col.find_one(
            {"guild_id": guild_id, "channel_id": channel_id}
        )
        
        # Check if transcript exists
        transcript = await self.bot.cogs["TicketSystem"].transcripts_col.find_one(
            {"guild_id": guild_id, "channel_id": channel_id}
        )
        
        if not transcript:
            confirmation = ConfirmView()
            await interaction.response.send_message(
                "No transcript has been generated for this ticket. Are you sure you want to delete it?",
                view=confirmation,
                ephemeral=True
            )
            
            # Wait for confirmation
            await confirmation.wait()
            if not confirmation.value:
                return
        
        await interaction.response.send_message("Deleting ticket channel...", ephemeral=True)
        
        # Update ticket status to deleted in MongoDB
        await self.bot.cogs["TicketSystem"].tickets_col.update_one(
            {"guild_id": guild_id, "channel_id": channel_id},
            {"$set": {
                "status": "deleted",
                "deleted_at": datetime.utcnow(),
                "deleted_by": interaction.user.id
            }}
        )
        
        # Add a slight delay to allow the ephemeral message to be seen
        await asyncio.sleep(2)
        
        # Delete the channel
        try:
            await interaction.channel.delete()
        except Exception as e:
            # If we get here, the ephemeral message is already sent, so we can't send another response
            print(f"Error deleting channel: {e}")

    async def _reopen_ticket(self, interaction: discord.Interaction):
        """Reopen a closed ticket"""
        guild_id = interaction.guild.id
        channel_id = interaction.channel.id
        
        # Update ticket status in MongoDB
        timestamp = datetime.utcnow()
        await self.bot.cogs["TicketSystem"].tickets_col.update_one(
            {"guild_id": guild_id, "channel_id": channel_id},
            {"$set": {
                "status": "open",
                "updated_at": timestamp,
                "reopened_by": interaction.user.id,
                "reopened_at": timestamp
            }}
        )
        
        # Get ticket data
        ticket_data = await self.bot.cogs["TicketSystem"].tickets_col.find_one(
            {"guild_id": guild_id, "channel_id": channel_id}
        )
        
        # Rename the channel to remove -closed
        original_name = interaction.channel.name.replace('-closed', '')
        await interaction.channel.edit(name=original_name)
        
        # Restore permissions for the ticket creator
        creator_id = ticket_data.get("user_id")
        if creator_id:
            creator = interaction.guild.get_member(creator_id)
            if creator:
                await interaction.channel.set_permissions(creator, view_channel=True, send_messages=True)
        
        # Create new embed and view for reopened ticket
        embed = discord.Embed(
            title=f"Ticket {ticket_data.get('case_number')}: {ticket_data.get('ticket_type')}",
            description=f"This ticket has been reopened by {interaction.user.mention}",
            color=discord.Color.green(),
            timestamp=timestamp
        )
        embed.add_field(name="Case ID", value=str(ticket_data.get('case_number')), inline=True)
        embed.add_field(name="Status", value="Open", inline=True)
        
        # Create new open ticket view
        view = OpenTicketView(self.bot)
        
        # Send message about ticket being reopened
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=False
        )
        
        # Get the message reference to add the view to persistent views
        try:
            # Get the original response message to add the view
            original_message = await interaction.original_response()
            # Add the view to bot's persistent views with the message ID
            self.bot.add_view(view, message_id=original_message.id)
        except Exception as e:
            # If we can't get the original response, at least log the error
            print(f"Error registering view for reopened ticket: {e}")

class ConfirmView(ui.View):
    def __init__(self):
        super().__init__(timeout=60.0)
        self.value = None
    
    @ui.button(label="Yes", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        self.value = True
        self.stop()
        await interaction.response.send_message("Confirmed", ephemeral=True)
    
    @ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        self.value = False
        self.stop()
        await interaction.response.send_message("Cancelled", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
