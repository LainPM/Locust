import discord
from discord.ext import commands
from discord import app_commands, ui
import io
from datetime import datetime
import asyncio
from typing import Optional, List

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.mongo_client["ticket_system"]
        self.config_col = self.db["config"]
        self.tickets_col = self.db["tickets"]
        self.transcripts_col = self.db["transcripts"]
        bot.loop.create_task(self.register_views())
    
    async def register_views(self):
        """Register persistent views"""
        await self.bot.wait_until_ready()
        self.bot.add_view(TicketPanelView(self.bot))
        self.bot.add_view(TicketManagementView(self.bot))
        self.bot.add_view(TicketActionView(self.bot))
        print("Ticket views registered")

    @app_commands.command(name="setup_ticket_system")
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

        # Create panel
        embed = discord.Embed(title=panel_title, description=panel_description, color=discord.Color.blurple())
        view = TicketPanelView(self.bot)
        for i, t in enumerate(types):
            btn = ui.Button(label=t, style=discord.ButtonStyle.primary, custom_id=f"ticket:create:{t}", row=i//5)
            btn.callback = view.create_ticket
            view.add_item(btn)
        
        await ticket_panel.send(embed=embed, view=view)
        await interaction.followup.send("Ticket system set up successfully!", ephemeral=True)


class TicketPanelView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    async def create_ticket(self, interaction: discord.Interaction):
        """Create a ticket when button is pressed"""
        await interaction.response.defer(ephemeral=True)
        
        # Get ticket type from button custom_id
        ticket_type = interaction.data["custom_id"].split(":")[-1]
        
        # Get config and setup
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
        for role_id in config["mod_roles"]:
            role = interaction.guild.get_role(int(role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        
        # Create channel
        category = interaction.guild.get_channel(config["ticket_category_id"])
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
            custom_id="ticket:close",
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
        
        # Get fresh ticket data
        ticket = await cog.tickets_col.find_one({"guild_id": guild_id, "channel_id": channel.id})
        if not ticket:
            return await interaction.followup.send("This is not a ticket channel!", ephemeral=True)
        
        # Always re-check status from DB to avoid stale data
        ticket = await cog.tickets_col.find_one({"guild_id": guild_id, "channel_id": channel.id})
        if ticket.get("status") != "open":
            return await interaction.followup.send("This ticket is already closed!", ephemeral=True)
        
        # Update ticket
        timestamp = datetime.utcnow()
        await cog.tickets_col.update_one(
            {"guild_id": guild_id, "channel_id": channel.id},
            {"$set": {
                "status": "closed",
                "closed_at": timestamp,
                "closed_by": interaction.user.id
            }}
        )
        
        # Rename channel
        try:
            await channel.edit(name=f"{channel.name}-closed")
        except:
            pass
        
        # Remove user permissions
        try:
            creator = interaction.guild.get_member(ticket["user_id"])
            if creator:
                await channel.set_permissions(creator, send_messages=False)
        except:
            pass
        
        # Send closed message
        embed = discord.Embed(
            title=f"Ticket {ticket['case_number']} Closed",
            description=f"This ticket has been closed by {interaction.user.mention}",
            color=discord.Color.red()
        )
        
        # Add action view
        view = TicketActionView(self.bot)
        
        await interaction.followup.send(embed=embed, view=view)


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
            emoji="🗒️"
        )
        transcript_btn.callback = self.create_transcript

        reopen_btn = ui.Button(
            label="Reopen",
            style=discord.ButtonStyle.success,
            custom_id="ticket:reopen",
            emoji="🔓"
        )
        reopen_btn.callback = self.reopen_ticket

        delete_btn = ui.Button(
            label="Delete",
            style=discord.ButtonStyle.danger,
            custom_id="ticket:delete",
            emoji="🗑️"
        )
        delete_btn.callback = self.delete_ticket

        self.add_item(transcript_btn)
        self.add_item(reopen_btn)
        self.add_item(delete_btn)

    async def reopen_ticket(self, interaction: discord.Interaction):
        """Reopen a ticket"""
        await interaction.response.defer(ephemeral=False)

        cog = self.bot.get_cog("TicketSystem")
        channel = interaction.channel
        guild_id = interaction.guild.id

        # Get ticket data
        ticket = await cog.tickets_col.find_one({"guild_id": guild_id, "channel_id": channel.id})
        if not ticket:
            return await interaction.followup.send("This is not a ticket channel!", ephemeral=True)

        if ticket["status"] == "open":
            return await interaction.followup.send("This ticket is already open!", ephemeral=True)

        # Update ticket
        timestamp = datetime.utcnow()
        await cog.tickets_col.update_one(
            {"guild_id": guild_id, "channel_id": channel.id},
            {"$set": {
                "status": "open",
                "reopened_at": timestamp,
                "reopened_by": interaction.user.id,
                "closed_at": None,
                "closed_by": None
            }}
        )

        # Rename channel if it was marked closed
        if "-closed" in channel.name:
            new_name = channel.name.replace("-closed", "")
            try:
                await channel.edit(name=new_name)
            except Exception as e:
                print(f"Failed to rename ticket channel: {e}")
                return await interaction.followup.send("Ticket status was updated, but the channel name couldn't be changed.", ephemeral=True)

        # Restore user permissions
        try:
            creator = interaction.guild.get_member(ticket["user_id"])
            if creator:
                await channel.set_permissions(creator, view_channel=True, send_messages=True)
        except Exception as e:
            print(f"Failed to restore user permissions: {e}")

        # Send reopened message
        embed = discord.Embed(
            title=f"Ticket {ticket['case_number']}: {ticket['ticket_type']}",
            description=f"This ticket has been reopened by {interaction.user.mention}",
            color=discord.Color.green()
        )

        # Add management view back
        view = TicketManagementView(self.bot)

        try:
            await interaction.message.edit(view=None)
        except Exception as e:
            print(f"Failed to remove old view: {e}")

        await interaction.followup.send(embed=embed, view=view)
    
    async def delete_ticket(self, interaction: discord.Interaction):
        """Delete a ticket"""
        await interaction.response.defer(ephemeral=True)
        
        # Check for transcript first
        cog = self.bot.get_cog("TicketSystem")
        channel = interaction.channel
        guild_id = interaction.guild.id
        
        transcript_exists = await cog.transcripts_col.find_one(
            {"guild_id": guild_id, "channel_id": channel.id}
        ) is not None
        
        if not transcript_exists:
            # Show warning
            embed = discord.Embed(
                title="⚠️ Warning: No Transcript",
                description="No transcript has been generated. All ticket history will be lost.",
                color=discord.Color.gold()
            )
            
            view = ui.View(timeout=60)
            
            # Add confirm/cancel buttons
            confirm_btn = ui.Button(
                label="Delete Anyway", 
                style=discord.ButtonStyle.danger,
                custom_id="ticket:delete:confirm"
            )
            
            cancel_btn = ui.Button(
                label="Cancel", 
                style=discord.ButtonStyle.secondary,
                custom_id="ticket:delete:cancel"
            )
            
            async def confirm_callback(confirm_interaction):
                await confirm_interaction.response.defer(ephemeral=True)
                await self._perform_delete(confirm_interaction)
            
            async def cancel_callback(cancel_interaction):
                await cancel_interaction.response.defer(ephemeral=True)
                await cancel_interaction.message.delete()
                await cancel_interaction.followup.send("Deletion cancelled", ephemeral=True)
            
            confirm_btn.callback = confirm_callback
            cancel_btn.callback = cancel_callback
            
            view.add_item(confirm_btn)
            view.add_item(cancel_btn)
            
            await interaction.followup.send(embed=embed, view=view)
        else:
            # Transcript exists, delete immediately
            await self._perform_delete(interaction)
    
    async def _perform_delete(self, interaction: discord.Interaction):
        """Actually delete the ticket channel"""
        cog = self.bot.get_cog("TicketSystem")
        channel = interaction.channel
        guild_id = interaction.guild.id
        
        # Update ticket status
        await cog.tickets_col.update_one(
            {"guild_id": guild_id, "channel_id": channel.id},
            {"$set": {
                "status": "deleted",
                "deleted_at": datetime.utcnow(),
                "deleted_by": interaction.user.id
            }}
        )
        
        # Send deletion message and delay
        await channel.send("🗑️ **Deleting ticket in 3 seconds...**")
        await asyncio.sleep(3)
        
        # Delete the channel
        try:
            await channel.delete()
        except Exception as e:
            await interaction.followup.send(f"Error deleting channel: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
