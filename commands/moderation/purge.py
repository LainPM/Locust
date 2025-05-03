# commands/moderation/purge.py
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Union

class PurgeCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="purge",
        description="Delete a number of messages from a channel"
    )
    @app_commands.describe(amount="Number of messages to delete (max 1000)")
    @app_commands.default_permissions(manage_messages=True)
    async def purge(
        self,
        interaction: discord.Interaction,
        amount: int = 100
    ):
        """Delete a specified number of messages from the channel"""
        await interaction.response.defer(ephemeral=True)
        
        # Get the moderation system
        moderation_system = await self.bot.get_system("ModerationSystem")
        if not moderation_system:
            return await interaction.followup.send("Moderation system is not available.")
        
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.followup.send("You don't have permission to manage messages.")
        
        if not interaction.guild.me.guild_permissions.manage_messages:
            return await interaction.followup.send("I don't have permission to delete messages.")
        
        # Execute the purge
        deleted = await moderation_system.purge_handler.delete_messages(
            interaction.channel,
            amount,
            reason=f"Purge command by {interaction.user}"
        )
        
        # Reply with results
        if deleted:
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)
        else:
            await interaction.followup.send("No messages were deleted.", ephemeral=True)
    
    @app_commands.command(
        name="purgeuser",
        description="Delete messages from a specific user"
    )
    @app_commands.describe(
        user="The user whose messages to delete",
        amount="Number of messages to check (max 1000)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def purge_user(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        amount: int = 100
    ):
        """Delete messages from a specific user"""
        await interaction.response.defer(ephemeral=True)
        
        # Get the moderation system
        moderation_system = await self.bot.get_system("ModerationSystem")
        if not moderation_system:
            return await interaction.followup.send("Moderation system is not available.")
        
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.followup.send("You don't have permission to manage messages.")
        
        if not interaction.guild.me.guild_permissions.manage_messages:
            return await interaction.followup.send("I don't have permission to delete messages.")
        
        # Execute the purge
        deleted = await moderation_system.purge_handler.delete_user_messages(
            interaction.channel,
            user,
            amount,
            reason=f"User purge command by {interaction.user}"
        )
        
        # Reply with results
        if deleted:
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages from {user.mention}.", ephemeral=True)
        else:
            await interaction.followup.send(f"No messages from {user.mention} were deleted.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PurgeCommand(bot))
