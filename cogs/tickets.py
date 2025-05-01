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
        
        # Add a button for each ticket type
        for t in types:
            btn = ui.Button(label=t, style=discord.ButtonStyle.primary, custom_id=f"create_{t}")
            btn.callback = self._on_ticket_button
            self.add_item(btn)

    async def _on_ticket_button(self, interaction: discord.Interaction):
        """Handle ticket creation button press"""
        # Extract ticket type from custom_id
        ticket_type = interaction.data['custom_id'].split('_', 1)[1]
        
        # Get ticket config from MongoDB
        config = await self.bot.cogs["TicketSystem"].config_col.find_one({"guild_id": interaction.guild.id})
        if not config:
            await interaction.response.send_message("Ticket system not configured!", ephemeral=True)
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
        channel_name = f"{ticket_type.lower()}-{case_number}-{interaction.user.name}"
        
        try:
            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket {case_number} | Created by {interaction.user} | Type: {ticket_type}"
            )
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to create channels!", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"Error creating channel: {e}", ephemeral=True)
            return
        
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
        await initial_message.pin()
        
        # Add view to bot's persistent views
        self.bot.add_view(view, message_id=initial_message.id)
        
        # Send confirmation to user
        await interaction.response.send_message(
            f"Ticket created: {channel.mention}\nCase ID: {case_number}",
            ephemeral=True
        )

class OpenTicketView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        
        # Close ticket button
        close_btn = ui.Button(
            label="Close Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="close_ticket",
            emoji="🔒"
        )
        close_btn.callback = self._on_close
        self.add_item(close_btn)

    async def _on_close(self, interaction: discord.Interaction):
        """Handle ticket closing button press"""
        await interaction.response.send_modal(CloseModal(self.bot))

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
        
        if not ticket_data:
            await interaction.response.send_message(
                "Error: Ticket data not found. Please contact an administrator.",
                ephemeral=True
            )
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
        new_name = f"{channel.name}-closed"
        await channel.edit(name=new_name)
        
        # Remove permissions from ticket creator
        ticket_data = await self.bot.cogs["TicketSystem"].tickets_col.find_one(
            {"guild_id": guild_id, "channel_id": channel.id}
        )
        creator_id = ticket_data.get("user_id")
        
        if creator_id:
            creator = interaction.guild.get_member(creator_id)
            if creator:
                # Set read-only permissions
                await channel.set_permissions(creator, send_messages=False)
        
        # Send closed message with buttons
        embed = discord.Embed(
            title=f"Ticket {ticket_data.get('case_number')} Closed",
            description=f"This ticket has been closed by {interaction.user.mention}",
            color=discord.Color.red(),
            timestamp=timestamp
        )
        embed.add_field(name="Reason", value=self.reason.value, inline=False)
        
        view = ClosedTicketView(self.bot)
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=False
        )

class ClosedTicketView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        
        # Generate transcript button
        transcript_btn = ui.Button(
            label="Generate Transcript",
            style=discord.ButtonStyle.primary,
            custom_id="gen_transcript",
            emoji="📝"
        )
        transcript_btn.callback = self._gen_transcript
        
        # Delete ticket button
        delete_btn = ui.Button(
            label="Delete Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="delete_ticket",
            emoji="🗑️"
        )
        delete_btn.callback = self._delete_ticket
        
        # Reopen ticket button
        reopen_btn = ui.Button(
            label="Reopen Ticket",
            style=discord.ButtonStyle.success,
            custom_id="reopen_ticket",
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
        
        # Get ticket data
        ticket_data = await self.bot.cogs["TicketSystem"].tickets_col.find_one(
            {"guild_id": guild_id, "channel_id": channel_id}
        )
        
        if not ticket_data:
            await interaction.response.send_message("Ticket data not found!", ephemeral=True)
            return
        
        # Get config for transcript channel
        config = await self.bot.cogs["TicketSystem"].config_col.find_one({"guild_id": guild_id})
        if not config:
            await interaction.response.send_message("Ticket system config not found!", ephemeral=True)
            return
        
        # Get message history
        history = [msg async for msg in interaction.channel.history(limit=None, oldest_first=True)]
        
        # Count messages per user
        user_messages = {}
        for msg in history:
            if msg.author.id not in user_messages:
                user_messages[msg.author.id] = 1
            else:
                user_messages[msg.author.id] += 1
        
        # Update user involvement in ticket data
        users_involved = list(user_messages.keys())
        await self.bot.cogs["TicketSystem"].tickets_col.update_one(
            {"guild_id": guild_id, "channel_id": channel_id},
            {"$set": {
                "users_involved": users_involved,
                "message_count": len(history)
            }}
        )
        
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
        timestamp = datetime.utcnow()
        transcript_id = await self.bot.cogs["TicketSystem"].transcripts_col.insert_one({
            "case_number": ticket_data.get("case_number"),
            "guild_id": guild_id,
            "channel_id": channel_id,
            "transcript_html": full_transcript,
            "timestamp": timestamp,
            "generated_by": interaction.user.id
        })
        
        # Send to transcript channel
        transcript_channel = interaction.guild.get_channel(config["transcript_channel_id"])
        if not transcript_channel:
            await interaction.response.send_message("Transcript channel not found!", ephemeral=True)
            return
        
        data = io.BytesIO(full_transcript.encode('utf-8'))
        filename = f"ticket-{ticket_data.get('case_number')}-{interaction.channel.name}.html"
        
        # Create embed with transcript info
        embed = discord.Embed(
            title=f"Ticket Transcript: Case #{ticket_data.get('case_number')}",
            description=f"Transcript for ticket {interaction.channel.mention}",
            color=discord.Color.blue(),
            timestamp=timestamp
        )
        embed.add_field(name="Ticket Type", value=ticket_data.get("ticket_type"), inline=True)
        embed.add_field(name="Created By", value=f"<@{ticket_data.get('user_id')}>", inline=True)
        embed.add_field(name="Messages", value=str(len(history)), inline=True)
        embed.add_field(name="Close Reason", value=ticket_data.get("close_reason", "Not specified"), inline=False)
        
        # Send the transcript file with embed and add a view transcript button
        view = discord.ui.View()
        
        # Create and send file to get URL
        sent_message = await transcript_channel.send(
            embed=embed,
            file=discord.File(data, filename=filename)
        )
        
        if sent_message.attachments:
            transcript_url = sent_message.attachments[0].url
            
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
