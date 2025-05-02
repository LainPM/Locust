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
            
            # Create the initial close ticket button view
            view = InitialCloseButtonView(self.bot)
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

class InitialCloseButtonView(ui.View):
    """Initial view with only the close button - this is always present at the top of the ticket"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        
        btn = ui.Button(
            label="Close Ticket", 
            style=discord.ButtonStyle.danger, 
            custom_id="ticket_system:initial_close",
            emoji="🔒"
        )
        btn.callback = self._on_close_button
        self.add_item(btn)

    async def _on_close_button(self, interaction: discord.Interaction):
        """Handle the initial close button click - shows confirmation"""
        # Create a confirmation view
        view = CloseConfirmationView(self.bot)
        
        # Send confirmation message
        await interaction.response.send_message(
            "Are you sure you want to close this ticket?",
            view=view,
            ephemeral=False
        )

class CloseConfirmationView(ui.View):
    """View for confirming ticket closure"""
    def __init__(self, bot):
        super().__init__(timeout=60)  # 60 second timeout
        self.bot = bot
        
    @ui.button(label="Yes", style=discord.ButtonStyle.danger)
    async def confirm_close(self, interaction: discord.Interaction, button: ui.Button):
        """Handle confirmation to close the ticket"""
        channel = interaction.channel
        guild_id = interaction.guild.id
        user = interaction.user
        
        # Get ticket data
        ticket_data = None
        try:
            ticket_data = await self.bot.cogs["TicketSystem"].tickets_col.find_one(
                {"guild_id": guild_id, "channel_id": channel.id}
            )
        except Exception as e:
            print(f"Error retrieving ticket data: {e}")
            await interaction.response.send_message("Database error. Please try again.", ephemeral=True)
            return
            
        if not ticket_data:
            await interaction.response.send_message("Ticket not found in database. Please contact an administrator.", ephemeral=True)
            return
        
        # Update ticket status in database
        timestamp = datetime.utcnow()
        await self.bot.cogs["TicketSystem"].tickets_col.update_one(
            {"guild_id": guild_id, "channel_id": channel.id},
            {"$set": {
                "status": "closed",
                "updated_at": timestamp,
                "closed_by": user.id,
                "close_reason": "Closed by user"
            }}
        )
        
        # Rename the channel
        try:
            current_name = channel.name
            if not current_name.endswith("-closed"):
                new_name = f"{current_name}-closed"
                await channel.edit(name=new_name)
        except Exception as e:
            print(f"Error renaming channel: {e}")
        
        # Remove permissions from ticket creator
        try:
            creator_id = ticket_data.get("user_id")
            if creator_id:
                creator = interaction.guild.get_member(creator_id)
                if creator:
                    await channel.set_permissions(creator, send_messages=False)
        except Exception as e:
            print(f"Error updating permissions: {e}")
        
        # Create closed message with action buttons
        embed = discord.Embed(
            title=f"Ticket {ticket_data.get('case_number')} Closed",
            description=f"This ticket has been closed by {user.mention}",
            color=discord.Color.red(),
            timestamp=timestamp
        )
        
        # Delete the confirmation message
        try:
            await interaction.message.delete()
        except:
            pass
            
        # Create the action panel (one-time use)
        view = TicketActionsView(self.bot)
        
        # Send the closed message with action buttons
        await interaction.response.send_message(embed=embed, view=view)

    @ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def cancel_close(self, interaction: discord.Interaction, button: ui.Button):
        """Handle cancellation of ticket closure"""
        # Delete the confirmation message
        await interaction.message.delete()
        await interaction.response.send_message("Ticket closure cancelled.", ephemeral=True)

class TicketActionsView(ui.View):
    """One-time use view with action buttons (Transcript, Open, Delete)"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        
        # Generate transcript button
        transcript_btn = ui.Button(
            label="Transcript",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_system:generate_transcript",
            emoji="📝"
        )
        transcript_btn.callback = self._generate_transcript
        
        # Open ticket button 
        open_btn = ui.Button(
            label="Open",
            style=discord.ButtonStyle.success,
            custom_id="ticket_system:open_ticket",
            emoji="🔓"
        )
        open_btn.callback = self._open_ticket
        
        # Delete ticket button
        delete_btn = ui.Button(
            label="Delete",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_system:delete_ticket",
            emoji="🗑️"
        )
        delete_btn.callback = self._delete_ticket
        
        self.add_item(transcript_btn)
        self.add_item(open_btn)
        self.add_item(delete_btn)

    async def _generate_transcript(self, interaction: discord.Interaction):
        """Generate and send ticket transcript"""
        # First attempt to delete the action panel message
        try:
            await interaction.message.delete()
        except:
            pass
            
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
        try:
            server_info = (
                f"<Server-Info> "
                f"Server: {interaction.guild.name} ({interaction.guild.id}) "
                f"Channel: {interaction.channel.name} ({interaction.channel.id}) "
                f"Messages: {len(history)} "
                f"Attachments Saved: {ticket_data.get('attachments_saved', 0)} "
                f"Attachments Skipped: {ticket_data.get('attachments_skipped', 0)}"
            )
        except Exception as e:
            print(f"Error building server info: {e}")
            server_info = "<Server-Info> Error building server info"
        
        # Build user info section
        try:
            user_info = "<User-Info> "
            for i, (user_id, msg_count) in enumerate(user_messages.items(), 1):
                user = interaction.guild.get_member(user_id)
                if user:
                    user_name = f"{user.name}#{user.discriminator if hasattr(user, 'discriminator') and user.discriminator != '0' else '0'}"
                    user_info += f"\n{i} - {user_name} ({user_id}): {msg_count}"
        except Exception as e:
            print(f"Error building user info: {e}")
            user_info = "<User-Info> Error building user info"
        
        # Build message transcript
        try:
            transcript = "<Base-Transcript> "
            for msg in history:
                timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M')
                author_name = f"{msg.author.name}#{msg.author.discriminator if hasattr(msg.author, 'discriminator') and msg.author.discriminator != '0' else '0'}"
                content = msg.content.replace('<', '&lt;').replace('>', '&gt;')
                if content:  # Only add messages with content
                    transcript += f"\n[{timestamp}] {author_name}: {content}"
        except Exception as e:
            print(f"Error building transcript: {e}")
            transcript = "<Base-Transcript> Error building transcript"
        
        # Add closing message if available
        try:
            if ticket_data.get('status') == 'closed' and ticket_data.get('close_reason'):
                closer_id = ticket_data.get('closed_by')
                closer = interaction.guild.get_member(closer_id) if closer_id else None
                closer_name = closer.name if closer else "Unknown"
                close_reason = ticket_data.get('close_reason', 'No reason provided')
                transcript += f"\n[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')}] {self.bot.user.name}: Ticket is closing and transcript will be generated shortly. Closed by {closer_name} for reason: {close_reason}"
        except Exception as e:
            print(f"Error adding closing message: {e}")
            # Not critical, continue anyway
        
        # Combine all sections with proper formatting
        try:
            full_transcript = f"<html><body><pre>{server_info}\n\n{user_info}\n\n{transcript}</pre></body></html>"
        except Exception as e:
            print(f"Error combining transcript: {e}")
            full_transcript = "<html><body><pre>Error generating transcript</pre></body></html>"
        
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
                
        # Send the transcript file with embed
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
            
        # If we got a URL, add a View Transcript button and update the database
        if transcript_url:
            try:
                # Add View Transcript button to the message
                view = discord.ui.View()
                view.add_item(discord.ui.Button(
                    label="View Transcript",
                    style=discord.ButtonStyle.link,
                    url=transcript_url
                ))
                
                # Edit the message to add the view
                if sent_message:
                    await sent_message.edit(view=view)
                
                # Update transcript URL in MongoDB
                if transcript_id:
                    await self.bot.cogs["TicketSystem"].transcripts_col.update_one(
                        {"_id": transcript_id},
                        {"$set": {"url": transcript_url}}
                    )
                
                # Send confirmation with link to user
                try:
                    await interaction.followup.send(
                        f"Transcript generated and sent to {transcript_channel.mention}\n"
                        f"[View Transcript]({transcript_url})",
                        ephemeral=True
                    )
                except Exception as e:
                    print(f"Error sending confirmation to user: {e}")
                    # Try channel send as last resort
                    await interaction.channel.send(
                        f"Transcript generated and sent to {transcript_channel.mention}\n"
                        f"[View Transcript]({transcript_url})"
                    )
            except Exception as e:
                print(f"Error adding view button: {e}")
                # Still try to send confirmation if possible
                try:
                    await interaction.followup.send(
                        f"Transcript was generated and sent to {transcript_channel.mention}, but there was an issue with the link button.",
                        ephemeral=True
                    )
                except:
                    await interaction.channel.send(
                        f"Transcript was generated and sent to {transcript_channel.mention}, but there was an issue with the link button."
                    )
        else:
            # No transcript URL available
            try:
                await interaction.followup.send(
                    f"Transcript may have been generated but there was an issue with the file attachment. Please check {transcript_channel.mention}.",
                    ephemeral=True
                )
            except:
                await interaction.channel.send(
                    f"Transcript may have been generated but there was an issue with the file attachment. Please check {transcript_channel.mention}."
                )

    async def _open_ticket(self, interaction: discord.Interaction):
        """Re-open the ticket"""
        # First attempt to delete the action panel message
        try:
            await interaction.message.delete()
        except:
            pass
            
        channel = interaction.channel
        guild_id = interaction.guild.id
        user = interaction.user
        
        # Acknowledge the interaction
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as e:
            print(f"Error deferring interaction: {e}")
        
        # Get ticket data
        ticket_data = None
        try:
            ticket_data = await self.bot.cogs["TicketSystem"].tickets_col.find_one(
                {"guild_id": guild_id, "channel_id": channel.id}
            )
        except Exception as e:
            print(f"Error retrieving ticket data: {e}")
            await channel.send("Database error. Please contact an administrator.")
            return
            
        if not ticket_data:
            await channel.send("Ticket not found in database. Please contact an administrator.")
            return
        
        # Update ticket status
        timestamp = datetime.utcnow()
        try:
            await self.bot.cogs["TicketSystem"].tickets_col.update_one(
                {"guild_id": guild_id, "channel_id": channel.id},
                {"$set": {
                    "status": "open",
                    "updated_at": timestamp,
                    "reopened_by": user.id,
                    "reopened_at": timestamp
                }}
            )
        except Exception as e:
            print(f"Error updating ticket: {e}")
            await channel.send("Error updating ticket in database. Please try again.")
            return
        
        # Rename channel - remove -closed suffix
        try:
            current_name = channel.name
            new_name = current_name.replace("-closed", "")
            if new_name != current_name:  # Only rename if needed
                await channel.edit(name=new_name)
        except Exception as e:
            print(f"Error renaming channel: {e}")
            await channel.send(f"Could not rename channel: {e}")
        
        # Restore permissions for ticket creator
        try:
            creator_id = ticket_data.get("user_id")
            if creator_id:
                creator = interaction.guild.get_member(creator_id)
                if creator:
                    await channel.set_permissions(creator, view_channel=True, send_messages=True)
        except Exception as e:
            print(f"Error updating permissions: {e}")
            await channel.send(f"Could not update permissions: {e}")
        
        # Send reopened message
        embed = discord.Embed(
            title=f"Ticket {ticket_data.get('case_number')}: {ticket_data.get('ticket_type')}",
            description=f"This ticket has been reopened by {user.mention}",
            color=discord.Color.green(),
            timestamp=timestamp
        )
        embed.add_field(name="Case ID", value=str(ticket_data.get('case_number')), inline=True)
        embed.add_field(name="Status", value="Open", inline=True)
        
        await interaction.followup.send(embed=embed)

    async def _delete_ticket(self, interaction: discord.Interaction):
        """Delete the ticket"""
        # First attempt to delete the action panel message
        try:
            await interaction.message.delete()
        except:
            pass
            
        channel = interaction.channel
        guild_id = interaction.guild.id
        user = interaction.user
        
        # Acknowledge the interaction
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as e:
            print(f"Error deferring interaction: {e}")
        
        # Check if transcript exists before deleting
        transcript_exists = False
        try:
            transcript = await self.bot.cogs["TicketSystem"].transcripts_col.find_one(
                {"guild_id": guild_id, "channel_id": channel.id}
            )
            transcript_exists = transcript is not None
        except Exception as e:
            print(f"Error checking transcript: {e}")
            # If we can't check, assume no transcript for safety
            transcript_exists = False
        
        if not transcript_exists:
            # No transcript - send warning and confirmation buttons
            warning_embed = discord.Embed(
                title="⚠️ Warning: No Transcript",
                description="No transcript has been generated for this ticket.\nIf you continue, all ticket history will be permanently lost.",
                color=discord.Color.gold()
            )
            
            # Create confirmation message with direct buttons
            confirm_view = discord.ui.View(timeout=60)
            
            # Add yes and no buttons with callbacks
            yes_button = discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="Yes, Delete Ticket",
                custom_id="ticket_system:confirm_delete"
            )
            
            no_button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Cancel",
                custom_id="ticket_system:cancel_delete"
            )
            
            # Define button callbacks
            async def yes_callback(confirm_interaction):
                try:
                    await confirm_interaction.response.defer(ephemeral=True)
                    await channel.send("🗑️ **Deleting ticket in 3 seconds...**")
                    
                    # Update database
                    timestamp = datetime.utcnow()
                    await self.bot.cogs["TicketSystem"].tickets_col.update_one(
                        {"guild_id": guild_id, "channel_id": channel.id},
                        {"$set": {
                            "status": "deleted",
                            "deleted_at": timestamp,
                            "deleted_by": user.id
                        }}
                    )
                    
                    # Wait briefly
                    await asyncio.sleep(3)
                    
                    # Delete the channel
                    await channel.delete()
                except Exception as e:
                    print(f"Error in delete confirmation: {e}")
                    try:
                        await channel.send(f"Error deleting channel: {e}")
                    except:
                        pass
            
            async def no_callback(cancel_interaction):
                await cancel_interaction.response.send_message("Deletion cancelled.", ephemeral=True)
            
            yes_button.callback = yes_callback
            no_button.callback = no_callback
            
            confirm_view.add_item(yes_button)
            confirm_view.add_item(no_button)
            
            # Send the confirmation
            try:
                await channel.send(embed=warning_embed, view=confirm_view)
                await interaction.followup.send("Please confirm if you want to delete this ticket without generating a transcript.", ephemeral=True)
            except Exception as e:
                print(f"Error sending confirmation: {e}")
                await channel.send("Error sending confirmation. Please try again.")
        else:
            # Transcript exists, proceed with deletion immediately
            try:
                await channel.send("🗑️ **Deleting ticket in 3 seconds...**")
                
                # Update database
                timestamp = datetime.utcnow()
                await self.bot.cogs["TicketSystem"].tickets_col.update_one(
                    {"guild_id": guild_id, "channel_id": channel.id},
                    {"$set": {
                        "status": "deleted",
                        "deleted_at": timestamp,
                        "deleted_by": user.id
                    }}
                )
                
                # Acknowledge the interaction
                await interaction.followup.send("Deleting ticket channel...", ephemeral=True)
                
                # Wait briefly
                await asyncio.sleep(3)
                
                # Delete the channel
                await channel.delete()
            except Exception as e:
                print(f"Error deleting channel: {e}")
                await channel.send(f"Error deleting channel: {e}. Please try again or contact an administrator.")

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
