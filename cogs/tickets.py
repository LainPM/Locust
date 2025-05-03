import discord
from discord.ext import commands
from discord import app_commands, ui
import io
from datetime import datetime
import asyncio
from typing import Optional

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.mongo_client["ticket_system"]
        self.config_col = self.db["config"]
        self.tickets_col = self.db["tickets"]
        self.transcripts_col = self.db["transcripts"]
        
    @commands.Cog.listener()
    async def on_ready(self):
        # Register persistent views
        self.bot.add_view(TicketPanelView(self.bot))
        self.bot.add_view(TicketManagementView(self.bot))
        self.bot.add_view(ClosedTicketView(self.bot))
        print("Ticket system ready")

    @app_commands.command(name="setup_ticket_system")
    @app_commands.describe(
        ticket_panel='Channel to post the ticket panel',
        transcript_channel='Channel to send transcripts',
        ticket_category='Category to create tickets under',
        ticket_types='Comma-separated ticket types (e.g. Support,Bug)',
        moderator_roles='Comma-separated role IDs or @roles',
        panel_title='Title for the ticket panel embed (optional)',
        panel_description='Description for the ticket panel embed (optional)'
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def setup_ticket_system(
        self, interaction: discord.Interaction,
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
        
        # Parse inputs
        types = [t.strip() for t in ticket_types.split(',')]
        role_ids = []
        for role_str in moderator_roles.split(','):
            role_str = role_str.strip()
            if role_str.startswith('<@&') and role_str.endswith('>'):
                role_str = role_str[3:-1]
            try:
                role_ids.append(int(role_str))
            except ValueError:
                continue
        
        # Save config
        await self.config_col.update_one(
            {"guild_id": interaction.guild.id},
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

        # Create panel with custom title and description
        embed = discord.Embed(
            title=panel_title,
            description=panel_description,
            color=discord.Color.blue()
        )
        
        # Create panel view with buttons for each ticket type
        view = TicketPanelView(self.bot)
        
        # Add buttons for each ticket type
        for i, ticket_type in enumerate(types):
            button = ui.Button(
                style=discord.ButtonStyle.primary,
                label=ticket_type,
                custom_id=f"ticket_create:{ticket_type}",
                row=i // 5  # Max 5 buttons per row
            )
            button.callback = view.create_ticket
            view.add_item(button)
        
        await ticket_panel.send(embed=embed, view=view)
        await interaction.followup.send("Ticket system set up successfully!", ephemeral=True)


class TicketPanelView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    async def create_ticket(self, interaction: discord.Interaction):
        """Create a new ticket"""
        await interaction.response.defer(ephemeral=True)
        
        # Get ticket type from button custom_id
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("ticket_create:"):
            return await interaction.followup.send("Invalid button!", ephemeral=True)
        
        ticket_type = custom_id.split(":", 1)[1]
        
        # Get config
        cog = self.bot.get_cog("TicketSystem")
        config = await cog.config_col.find_one({"guild_id": interaction.guild.id})
        if not config:
            return await interaction.followup.send("Ticket system not configured!", ephemeral=True)
        
        # Get case number
        case_count = await cog.tickets_col.count_documents({"guild_id": interaction.guild.id})
        case_number = case_count + 1
        
        # Setup permissions
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        
        # Add mod roles
        for role_id in config.get("mod_roles", []):
            role = interaction.guild.get_role(int(role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        
        # Create channel
        category = interaction.guild.get_channel(config["ticket_category_id"])
        if not category:
            return await interaction.followup.send("Ticket category not found!", ephemeral=True)
        
        safe_username = ''.join(c for c in interaction.user.name if c.isalnum() or c in '-_')
        channel_name = f"{ticket_type.lower()}-{case_number}-{safe_username}"[:100]
        
        try:
            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket {case_number} | Type: {ticket_type}"
            )
            
            # Save ticket to DB
            timestamp = datetime.utcnow()
            await cog.tickets_col.insert_one({
                "guild_id": interaction.guild.id,
                "channel_id": channel.id,
                "user_id": interaction.user.id,
                "case_number": case_number,
                "ticket_type": ticket_type,
                "status": "open",
                "created_at": timestamp
            })
            
            # Send welcome message
            embed = discord.Embed(
                title=f"Ticket {case_number}: {ticket_type}",
                description=f"Thank you for creating a ticket, {interaction.user.mention}",
                color=discord.Color.green()
            )
            
            # Create management view
            view = TicketManagementView(self.bot)
            
            # Send and pin message
            welcome_msg = await channel.send(
                content=f"{interaction.user.mention} Welcome to your ticket!",
                embed=embed,
                view=view
            )
            await welcome_msg.pin()
            
            await interaction.followup.send(f"Ticket created: {channel.mention}", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"Error creating ticket: {e}", ephemeral=True)


class TicketManagementView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        
        # Add close button
        close_btn = ui.Button(
            label="Close Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_close",
            emoji="🔒"
        )
        close_btn.callback = self.close_ticket
        self.add_item(close_btn)
    
    async def close_ticket(self, interaction: discord.Interaction):
        """Close the ticket"""
        await interaction.response.defer(ephemeral=False)
        
        cog = self.bot.get_cog("TicketSystem")
        channel = interaction.channel
        guild_id = interaction.guild.id
        
        # Get ticket data
        ticket = await cog.tickets_col.find_one({
            "guild_id": guild_id, 
            "channel_id": channel.id
        })
        
        if not ticket:
            return await interaction.followup.send("This is not a ticket channel!", ephemeral=True)
        
        # Update ticket
        await cog.tickets_col.update_one(
            {"_id": ticket["_id"]},  # Use _id for exact matching
            {"$set": {
                "status": "closed",
                "closed_at": datetime.utcnow(),
                "closed_by": interaction.user.id
            }}
        )
        
        # Rename channel
        try:
            await channel.edit(name=f"{channel.name}-closed")
        except Exception as e:
            print(f"Error renaming channel: {e}")
        
        # Remove user permissions
        try:
            creator = interaction.guild.get_member(ticket["user_id"])
            if creator:
                await channel.set_permissions(creator, send_messages=False)
        except Exception as e:
            print(f"Error updating permissions: {e}")
        
        # Send closed message
        embed = discord.Embed(
            title=f"Ticket {ticket['case_number']} Closed",
            description=f"This ticket has been closed by {interaction.user.mention}",
            color=discord.Color.red()
        )
        
        # Add closed ticket view
        view = ClosedTicketView(self.bot)
        
        await interaction.followup.send(embed=embed, view=view)


class ClosedTicketView(ui.View):
    """View for closed ticket actions"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        
        # Add transcript button
        transcript_btn = ui.Button(
            label="Transcript",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_transcript",
            emoji="📝"
        )
        transcript_btn.callback = self.create_transcript
        self.add_item(transcript_btn)
        
        # Add delete button
        delete_btn = ui.Button(
            label="Delete",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_delete",
            emoji="🗑️"
        )
        delete_btn.callback = self.delete_ticket
        self.add_item(delete_btn)
    
    async def create_transcript(self, interaction: discord.Interaction):
        """Generate a transcript"""
        await interaction.response.defer(ephemeral=True)
        
        cog = self.bot.get_cog("TicketSystem")
        channel = interaction.channel
        guild_id = interaction.guild.id
        
        # Get ticket and config
        ticket = await cog.tickets_col.find_one({
            "guild_id": guild_id, 
            "channel_id": channel.id
        })
        
        config = await cog.config_col.find_one({"guild_id": guild_id})
        
        if not ticket or not config:
            return await interaction.followup.send("Error: Ticket or config not found", ephemeral=True)
        
        # Get transcript channel
        transcript_channel = interaction.guild.get_channel(config["transcript_channel_id"])
        if not transcript_channel:
            return await interaction.followup.send("Transcript channel not found", ephemeral=True)
        
        try:
            # Get message history
            history = [msg async for msg in channel.history(limit=None, oldest_first=True)]
            
            # Generate transcript content
            transcript_content = f"Ticket #{ticket['case_number']} Transcript\n"
            transcript_content += f"Channel: {channel.name}\n"
            transcript_content += f"Created by: <@{ticket['user_id']}>\n\n"
            
            for msg in history:
                time = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                author_name = msg.author.name
                content = msg.content or "[No content]"
                
                # Escape HTML chars
                content = content.replace('<', '&lt;').replace('>', '&gt;')
                
                transcript_content += f"[{time}] {author_name}: {content}\n"
                
                # Add attachments
                for attachment in msg.attachments:
                    transcript_content += f"[{time}] {author_name} [Attachment]: {attachment.url}\n"
            
            # Create HTML file
            html_content = f"<html><body><pre>{transcript_content}</pre></body></html>"
            
            # Create file
            data = io.BytesIO(html_content.encode('utf-8'))
            filename = f"ticket-{ticket['case_number']}.html"
            file = discord.File(data, filename=filename)
            
            # Create embed
            embed = discord.Embed(
                title=f"Ticket Transcript: Case #{ticket['case_number']}",
                description=f"Transcript for ticket {channel.mention}",
                color=discord.Color.blue()
            )
            
            # Send to transcript channel
            transcript_msg = await transcript_channel.send(embed=embed, file=file)
            
            # Save to DB
            if transcript_msg.attachments:
                url = transcript_msg.attachments[0].url
                
                await cog.transcripts_col.insert_one({
                    "guild_id": guild_id,
                    "channel_id": channel.id,
                    "case_number": ticket["case_number"],
                    "url": url,
                    "created_at": datetime.utcnow(),
                    "created_by": interaction.user.id
                })
                
                # Add link button
                view = discord.ui.View()
                view.add_item(discord.ui.Button(
                    label="View Transcript",
                    style=discord.ButtonStyle.link,
                    url=url
                ))
                
                await transcript_msg.edit(view=view)
                
                await interaction.followup.send(
                    f"Transcript created! [View Transcript]({url})",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"Transcript created and sent to {transcript_channel.mention}",
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.followup.send(f"Error creating transcript: {e}", ephemeral=True)
    
    async def delete_ticket(self, interaction: discord.Interaction):
        """Delete a ticket"""
        await interaction.response.defer(ephemeral=True)
        
        # Check for transcript first
        cog = self.bot.get_cog("TicketSystem")
        channel = interaction.channel
        guild_id = interaction.guild.id
        
        # Check if transcript exists
        transcript_exists = await cog.transcripts_col.find_one({
            "guild_id": guild_id,
            "channel_id": channel.id
        }) is not None
        
        if not transcript_exists:
            # Show warning
            embed = discord.Embed(
                title="⚠️ Warning: No Transcript",
                description="No transcript has been generated. All ticket history will be lost.",
                color=discord.Color.gold()
            )
            
            view = DeleteConfirmView(self.bot)
            await interaction.followup.send(embed=embed, view=view)
        else:
            # Transcript exists, delete directly
            await self._perform_delete(interaction)
    
    async def _perform_delete(self, interaction: discord.Interaction):
        """Actually delete the ticket channel"""
        cog = self.bot.get_cog("TicketSystem")
        channel = interaction.channel
        guild_id = interaction.guild.id
        
        # Get ticket data
        ticket = await cog.tickets_col.find_one({
            "guild_id": guild_id, 
            "channel_id": channel.id
        })
        
        if not ticket:
            return await interaction.followup.send("This is not a ticket channel!", ephemeral=True)
        
        # Update DB
        await cog.tickets_col.update_one(
            {"_id": ticket["_id"]},
            {"$set": {
                "status": "deleted",
                "deleted_at": datetime.utcnow(),
                "deleted_by": interaction.user.id
            }}
        )
        
        # Send deletion message and delay
        await channel.send("🗑️ **Deleting ticket in 5 seconds...**")
        await asyncio.sleep(5)
        
        # Delete the channel
        try:
            await channel.delete()
        except Exception as e:
            await interaction.followup.send(f"Error deleting channel: {e}", ephemeral=True)


class DeleteConfirmView(ui.View):
    """View for confirming ticket deletion"""
    def __init__(self, bot):
        super().__init__(timeout=60)  # 60 second timeout
        self.bot = bot
    
    @ui.button(label="Yes, Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        """Confirm ticket deletion"""
        await interaction.response.defer(ephemeral=True)
        
        # Delete confirmation message
        try:
            await interaction.message.delete()
        except:
            pass
        
        # Perform delete directly
        cog = self.bot.get_cog("TicketSystem")
        channel = interaction.channel
        guild_id = interaction.guild.id
        
        # Get ticket data
        ticket = await cog.tickets_col.find_one({
            "guild_id": guild_id, 
            "channel_id": channel.id
        })
        
        if ticket:
            # Update DB
            await cog.tickets_col.update_one(
                {"_id": ticket["_id"]},
                {"$set": {
                    "status": "deleted",
                    "deleted_at": datetime.utcnow(),
                    "deleted_by": interaction.user.id
                }}
            )
            
            # Delete channel after delay
            await channel.send("🗑️ **Deleting ticket in 5 seconds...**")
            await asyncio.sleep(5)
            try:
                await channel.delete()
            except Exception as e:
                await interaction.followup.send(f"Error deleting channel: {e}", ephemeral=True)
        else:
            await interaction.followup.send("Ticket not found in database", ephemeral=True)
    
    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        """Cancel ticket deletion"""
        await interaction.response.defer(ephemeral=True)
        await interaction.message.delete()
        await interaction.followup.send("Deletion cancelled", ephemeral=True)


async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
