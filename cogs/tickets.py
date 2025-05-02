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
        """Register interactions on bot ready"""
        self.bot.add_view(TicketView(self.bot))
        print("Ticket system ready")
    
    async def get_ticket(self, guild_id, channel_id):
        """Get fresh ticket data from DB"""
        return await self.tickets_col.find_one({"guild_id": guild_id, "channel_id": channel_id})
    
    @app_commands.command(name="setup_tickets")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tickets(
        self, interaction: discord.Interaction,
        ticket_channel: discord.TextChannel,
        ticket_category: discord.CategoryChannel,
        transcript_channel: discord.TextChannel,
        mod_role: discord.Role
    ):
        """Setup the ticket system"""
        await interaction.response.defer(ephemeral=True)
        
        # Save config
        await self.config_col.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {
                "ticket_channel_id": ticket_channel.id,
                "ticket_category_id": ticket_category.id,
                "transcript_channel_id": transcript_channel.id,
                "mod_role_id": mod_role.id
            }},
            upsert=True
        )
        
        # Create ticket panel
        embed = discord.Embed(
            title="Support Tickets",
            description="Click the button below to create a support ticket",
            color=discord.Color.blue()
        )
        
        # Create ticket button
        view = TicketView(self.bot)
        
        await ticket_channel.send(embed=embed, view=view)
        await interaction.followup.send("Ticket system setup complete!", ephemeral=True)


class TicketView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        
        # Create ticket button
        self.add_item(ui.Button(
            label="Create Ticket",
            style=discord.ButtonStyle.primary,
            custom_id="create_ticket",
            emoji="🎫"
        ))
    
    @ui.button(label="Create Ticket", style=discord.ButtonStyle.primary, custom_id="create_ticket", emoji="🎫")
    async def create_ticket(self, interaction: discord.Interaction, button: ui.Button):
        """Create a ticket"""
        await interaction.response.defer(ephemeral=True)
        
        cog = self.bot.get_cog("TicketSystem")
        
        # Get config
        config = await cog.config_col.find_one({"guild_id": interaction.guild.id})
        if not config:
            return await interaction.followup.send("Ticket system not configured!", ephemeral=True)
        
        # Get case number
        case_count = await cog.tickets_col.count_documents({"guild_id": interaction.guild.id})
        case_number = case_count + 1
        
        # Create channel
        category = interaction.guild.get_channel(config["ticket_category_id"])
        mod_role = interaction.guild.get_role(config["mod_role_id"])
        
        # Set permissions
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        
        # Create channel
        channel_name = f"ticket-{case_number}-{interaction.user.name.lower()}"[:100]
        
        try:
            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites
            )
            
            # Save ticket to DB
            timestamp = datetime.utcnow()
            await cog.tickets_col.insert_one({
                "guild_id": interaction.guild.id,
                "channel_id": channel.id,
                "user_id": interaction.user.id,
                "case_number": case_number,
                "status": "open",
                "created_at": timestamp
            })
            
            # Create welcome message
            embed = discord.Embed(
                title=f"Ticket #{case_number}",
                description=f"Thanks for creating a ticket, {interaction.user.mention}",
                color=discord.Color.green()
            )
            
            # Add ticket controls
            controls = TicketControls(self.bot)
            
            await channel.send(f"{interaction.user.mention} {mod_role.mention}", embed=embed, view=controls)
            await interaction.followup.send(f"Ticket created! {channel.mention}", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"Error creating ticket: {e}", ephemeral=True)


class TicketControls(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    @ui.button(label="Close", style=discord.ButtonStyle.red, custom_id="ticket:close", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        """Close a ticket"""
        await interaction.response.defer(ephemeral=False)
        cog = self.bot.get_cog("TicketSystem")
        
        # Get fresh ticket data
        ticket = await cog.get_ticket(interaction.guild.id, interaction.channel.id)
        if not ticket:
            return await interaction.followup.send("This is not a ticket channel!")
        
        # Check if already closed
        if ticket.get("status") != "open":
            return await interaction.followup.send("This ticket is already closed!")
        
        # Update ticket status in DB
        try:
            await cog.tickets_col.update_one(
                {"_id": ticket["_id"]},  # Use _id for exact match
                {"$set": {
                    "status": "closed",
                    "closed_at": datetime.utcnow(),
                    "closed_by": interaction.user.id
                }}
            )
            
            # Disable send messages for ticket creator
            user = interaction.guild.get_member(ticket["user_id"])
            if user:
                await interaction.channel.set_permissions(user, send_messages=False)
            
            # Rename channel
            await interaction.channel.edit(name=f"{interaction.channel.name}-closed")
            
            # Send closed message
            embed = discord.Embed(
                title="Ticket Closed",
                description=f"This ticket has been closed by {interaction.user.mention}",
                color=discord.Color.red()
            )
            
            # Send closed ticket controls
            closed_controls = ClosedTicketControls(self.bot)
            await interaction.followup.send(embed=embed, view=closed_controls)
            
        except Exception as e:
            await interaction.followup.send(f"Error closing ticket: {e}")


class ClosedTicketControls(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    @ui.button(label="Transcript", style=discord.ButtonStyle.blurple, custom_id="ticket:transcript", emoji="📝")
    async def create_transcript(self, interaction: discord.Interaction, button: ui.Button):
        """Generate a transcript"""
        await interaction.response.defer(ephemeral=True)
        cog = self.bot.get_cog("TicketSystem")
        
        # Get config
        config = await cog.config_col.find_one({"guild_id": interaction.guild.id})
        if not config:
            return await interaction.followup.send("Ticket system not configured!", ephemeral=True)
        
        # Get transcript channel
        transcript_channel = interaction.guild.get_channel(config["transcript_channel_id"])
        if not transcript_channel:
            return await interaction.followup.send("Transcript channel not found!", ephemeral=True)
        
        # Get ticket data
        ticket = await cog.get_ticket(interaction.guild.id, interaction.channel.id)
        if not ticket:
            return await interaction.followup.send("This is not a ticket channel!", ephemeral=True)
        
        try:
            # Get message history
            messages = [msg async for msg in interaction.channel.history(limit=None, oldest_first=True)]
            
            # Create transcript
            content = f"Ticket #{ticket['case_number']} Transcript\n"
            content += f"Channel: {interaction.channel.name}\n"
            content += f"Created by: <@{ticket['user_id']}>\n\n"
            
            for msg in messages:
                time = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                content += f"[{time}] {msg.author.name}: {msg.content}\n"
                
                # Add attachments
                for attachment in msg.attachments:
                    content += f"[{time}] {msg.author.name} [Attachment]: {attachment.url}\n"
            
            # Create file
            file_data = io.BytesIO(content.encode('utf-8'))
            file = discord.File(file_data, filename=f"transcript-{ticket['case_number']}.txt")
            
            # Send transcript
            embed = discord.Embed(
                title=f"Transcript: Ticket #{ticket['case_number']}",
                color=discord.Color.blue()
            )
            
            # Send to transcript channel
            transcript_msg = await transcript_channel.send(embed=embed, file=file)
            
            # Save to DB
            if transcript_msg.attachments:
                url = transcript_msg.attachments[0].url
                await cog.transcripts_col.insert_one({
                    "guild_id": interaction.guild.id,
                    "channel_id": interaction.channel.id,
                    "case_number": ticket["case_number"],
                    "url": url,
                    "created_at": datetime.utcnow(),
                    "created_by": interaction.user.id
                })
                
                # Add view link
                view = discord.ui.View()
                view.add_item(discord.ui.Button(
                    label="View Transcript", 
                    style=discord.ButtonStyle.link,
                    url=url
                ))
                
                await transcript_msg.edit(view=view)
                await interaction.followup.send(f"Transcript created! [View Transcript]({url})", ephemeral=True)
            else:
                await interaction.followup.send("Transcript created but URL not available", ephemeral=True)
                
        except Exception as e:
            await interaction.followup.send(f"Error creating transcript: {e}", ephemeral=True)
    
    @ui.button(label="Reopen", style=discord.ButtonStyle.green, custom_id="ticket:reopen", emoji="🔓")
    async def reopen_ticket(self, interaction: discord.Interaction, button: ui.Button):
        """Reopen a ticket"""
        await interaction.response.defer(ephemeral=False)
        cog = self.bot.get_cog("TicketSystem")
        
        # Get ticket data - fresh query
        ticket = await cog.get_ticket(interaction.guild.id, interaction.channel.id)
        if not ticket:
            return await interaction.followup.send("This is not a ticket channel!")
        
        # Check if ticket is already open
        if ticket.get("status") == "open":
            return await interaction.followup.send("This ticket is already open!")
        
        # Update ticket in DB
        try:
            await cog.tickets_col.update_one(
                {"_id": ticket["_id"]},  # Use _id for exact match
                {"$set": {
                    "status": "open",
                    "reopened_at": datetime.utcnow(),
                    "reopened_by": interaction.user.id,
                    "closed_at": None,
                    "closed_by": None
                }}
            )
            
            # Remove -closed from channel name
            new_name = interaction.channel.name.replace("-closed", "")
            await interaction.channel.edit(name=new_name)
            
            # Restore user permissions
            user = interaction.guild.get_member(ticket["user_id"])
            if user:
                await interaction.channel.set_permissions(user, send_messages=True)
            
            # Send reopened message
            embed = discord.Embed(
                title="Ticket Reopened",
                description=f"This ticket has been reopened by {interaction.user.mention}",
                color=discord.Color.green()
            )
            
            # Remove this message's view
            try:
                await interaction.message.edit(view=None)
            except:
                pass
            
            # Add new open ticket controls
            controls = TicketControls(self.bot)
            await interaction.followup.send(embed=embed, view=controls)
            
        except Exception as e:
            await interaction.followup.send(f"Error reopening ticket: {e}")
    
    @ui.button(label="Delete", style=discord.ButtonStyle.red, custom_id="ticket:delete", emoji="🗑️")
    async def delete_ticket(self, interaction: discord.Interaction, button: ui.Button):
        """Delete a ticket"""
        await interaction.response.defer(ephemeral=True)
        cog = self.bot.get_cog("TicketSystem")
        
        # Check if transcript exists
        transcript = await cog.transcripts_col.find_one({
            "guild_id": interaction.guild.id,
            "channel_id": interaction.channel.id
        })
        
        if not transcript:
            # Ask for confirmation
            embed = discord.Embed(
                title="⚠️ Warning: No Transcript",
                description="No transcript has been generated. All ticket history will be lost.",
                color=discord.Color.gold()
            )
            
            confirm_view = DeleteConfirmView(self.bot)
            await interaction.followup.send(embed=embed, view=confirm_view)
        else:
            # Transcript exists, proceed with deletion
            await self._delete_ticket(interaction)
    
    async def _delete_ticket(self, interaction: discord.Interaction):
        """Helper to delete the ticket channel"""
        cog = self.bot.get_cog("TicketSystem")
        
        # Get ticket data
        ticket = await cog.get_ticket(interaction.guild.id, interaction.channel.id)
        if not ticket:
            return await interaction.followup.send("This is not a ticket channel!", ephemeral=True)
        
        # Update ticket in DB
        await cog.tickets_col.update_one(
            {"_id": ticket["_id"]},
            {"$set": {
                "status": "deleted",
                "deleted_at": datetime.utcnow(),
                "deleted_by": interaction.user.id
            }}
        )
        
        # Delete channel after delay
        await interaction.channel.send("🗑️ **Deleting ticket in 5 seconds...**")
        await asyncio.sleep(5)
        await interaction.channel.delete()


class DeleteConfirmView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=60)  # 60 second timeout
        self.bot = bot
    
    @ui.button(label="Yes, Delete", style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        """Confirm ticket deletion"""
        await interaction.response.defer(ephemeral=True)
        
        # Get parent view
        closed_controls = self.bot.get_cog("TicketSystem").closed_controls
        
        # Delete message with this view
        await interaction.message.delete()
        
        # Perform delete
        await closed_controls._delete_ticket(interaction)
    
    @ui.button(label="Cancel", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        """Cancel ticket deletion"""
        await interaction.response.defer(ephemeral=True)
        await interaction.message.delete()
        await interaction.followup.send("Deletion cancelled", ephemeral=True)


async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
