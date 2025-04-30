# cogs/moderation.py
import discord
from discord.ext import commands
from discord import app_commands
import datetime

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Reference to MongoDB collection for warnings
        self.warnings_collection = bot.warnings_collection

    # Helper function to check if user has permission to moderate
    def check_permissions(self, interaction: discord.Interaction) -> bool:
        # Check if user has ban or kick permissions
        return (interaction.user.guild_permissions.ban_members or 
                interaction.user.guild_permissions.kick_members)
    
    # Helper function to create mod action embed
    def create_mod_embed(self, action, target, moderator, reason):
        embed = discord.Embed(
            title=f"User {action}",
            description=f"**{target}** has been {action.lower()}ed.",
            color=discord.Color.from_rgb(255, 0, 0),  # Red color
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        embed.add_field(name="Moderator", value=moderator.mention, inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text=f"User ID: {target.id}")
        return embed

    @app_commands.command(name="mute", description="Timeout a user for a specified duration")
    @app_commands.describe(
        user="The user to mute",
        duration="Duration in minutes (default: 10)",
        reason="Reason for the mute"
    )
    @app_commands.default_permissions(moderate_members=True)
    async def mute(self, 
                  interaction: discord.Interaction, 
                  user: discord.Member, 
                  duration: int = 10, 
                  reason: str = None):
        # Check if user has permission
        if not interaction.user.guild_permissions.moderate_members:
            return await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
        
        # Check if the bot can timeout the user
        if not interaction.guild.me.guild_permissions.moderate_members:
            return await interaction.response.send_message("I don't have permission to timeout members!", ephemeral=True)
        
        # Check if trying to mute someone with higher role
        if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message("You cannot mute someone with a higher or equal role!", ephemeral=True)
        
        # Calculate timeout duration
        timeout_duration = datetime.timedelta(minutes=duration)
        
        try:
            await user.timeout(timeout_duration, reason=reason)
            embed = self.create_mod_embed("Mute", user, interaction.user, reason)
            embed.add_field(name="Duration", value=f"{duration} minutes", inline=False)
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to timeout this user!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    @app_commands.command(name="unmute", description="Remove timeout from a user")
    @app_commands.describe(
        user="The user to unmute",
        reason="Reason for removing the timeout"
    )
    @app_commands.default_permissions(moderate_members=True)
    async def unmute(self, 
                    interaction: discord.Interaction, 
                    user: discord.Member, 
                    reason: str = None):
        # Check if user has permission
        if not interaction.user.guild_permissions.moderate_members:
            return await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
        
        # Check if the bot can timeout the user
        if not interaction.guild.me.guild_permissions.moderate_members:
            return await interaction.response.send_message("I don't have permission to manage timeouts!", ephemeral=True)
        
        # Check if trying to unmute someone with higher role
        if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message("You cannot unmute someone with a higher or equal role!", ephemeral=True)
        
        # Check if the user is actually timed out
        if not user.is_timed_out():
            return await interaction.response.send_message(f"{user.mention} is not currently muted/timed out.", ephemeral=True)
        
        try:
            # Remove timeout by setting it to None
            await user.timeout(None, reason=reason)
            
            # Create embed
            embed = discord.Embed(
                title="User Unmuted",
                description=f"{user.mention} has been unmuted.",
                color=discord.Color.from_rgb(0, 255, 0),  # Green color
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            embed.add_field(name="Unmuted by", value=interaction.user.mention, inline=False)
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text=f"User ID: {user.id}")
            
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to unmute this user!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    @app_commands.command(name="kick", description="Kick a user from the server")
    @app_commands.describe(
        user="The user to kick",
        reason="Reason for the kick"
    )
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, 
                  interaction: discord.Interaction, 
                  user: discord.Member, 
                  reason: str = None):
        # Check if user has permission
        if not interaction.user.guild_permissions.kick_members:
            return await interaction.response.send_message("You don't have permission to kick members!", ephemeral=True)
        
        # Check if the bot can kick
        if not interaction.guild.me.guild_permissions.kick_members:
            return await interaction.response.send_message("I don't have permission to kick members!", ephemeral=True)
        
        # Check if trying to kick someone with higher role
        if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message("You cannot kick someone with a higher or equal role!", ephemeral=True)
        
        try:
            await user.kick(reason=reason)
            embed = self.create_mod_embed("Kick", user, interaction.user, reason)
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to kick this user!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

    @app_commands.command(name="ban", description="Ban a user from the server")
    @app_commands.describe(
        user="The user to ban",
        delete_days="Number of days of messages to delete (0-7)",
        reason="Reason for the ban"
    )
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, 
                 interaction: discord.Interaction, 
                 user: discord.Member, 
                 delete_days: int = 0, 
                 reason: str = None):
        # Check if user has permission
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message("You don't have permission to ban members!", ephemeral=True)
        
        # Check if the bot can ban
        if not interaction.guild.me.guild_permissions.ban_members:
            return await interaction.response.send_message("I don't have permission to ban members!", ephemeral=True)
        
        # Check if trying to ban someone with higher role
        if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message("You cannot ban someone with a higher or equal role!", ephemeral=True)
        
        # Ensure delete_days is between 0 and 7
        delete_days = max(0, min(delete_days, 7))
        
        try:
            await user.ban(delete_message_days=delete_days, reason=reason)
            embed = self.create_mod_embed("Ban", user, interaction.user, reason)
            if delete_days > 0:
                embed.add_field(name="Message Deletion", value=f"Deleted messages from the past {delete_days} days", inline=False)
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to ban this user!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="warn", description="Warn a user")
    @app_commands.describe(
        user="The user to warn",
        reason="Reason for the warning"
    )
    @app_commands.default_permissions(kick_members=True)
    async def warn(self, 
                  interaction: discord.Interaction, 
                  user: discord.Member, 
                  reason: str = "No reason provided"):
        # Check if user has permission
        if not self.check_permissions(interaction):
            return await interaction.response.send_message("You don't have permission to warn members!", ephemeral=True)
        
        # Check if trying to warn someone with higher role
        if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message("You cannot warn someone with a higher or equal role!", ephemeral=True)
        
        # Add warning to MongoDB
        guild_id = interaction.guild.id
        user_id = user.id
        warning_time = datetime.datetime.now()
        
        warning = {
            "guild_id": guild_id,
            "user_id": user_id,
            "reason": reason,
            "moderator_id": interaction.user.id,
            "timestamp": warning_time
        }
        
        # Insert warning to database
        await self.warnings_collection.insert_one(warning)
        
        # Get warning count
        warning_count = await self.warnings_collection.count_documents({"guild_id": guild_id, "user_id": user_id})
        
        # Create warning embed for channel
        embed = discord.Embed(
            title="User Warned",
            description=f"{user.mention} has been warned.",
            color=discord.Color.from_rgb(255, 255, 0),  # Yellow color
            timestamp=warning_time
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Warned by", value=interaction.user.mention, inline=False)
        embed.add_field(name="Warning Count", value=str(warning_count), inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")
        
        # Send embed to channel
        await interaction.response.send_message(embed=embed)
        
        # Create DM embed
        dm_embed = discord.Embed(
            title=f"Warning from {interaction.guild.name}",
            description=f"You have been warned by {interaction.user.display_name}.",
            color=discord.Color.from_rgb(255, 255, 0),  # Yellow color
            timestamp=warning_time
        )
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        dm_embed.add_field(name="Warning Count", value=str(warning_count), inline=False)
        dm_embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        dm_embed.set_footer(text=f"Server ID: {interaction.guild.id}")
        
        # Try to send DM
        try:
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            # If DM fails, add note to channel embed
            await interaction.followup.send(f"Note: Could not DM {user.mention} about this warning.", ephemeral=True)
    
    @app_commands.command(name="warnings", description="Check warnings for a user")
    @app_commands.describe(
        user="The user to check warnings for"
    )
    @app_commands.default_permissions(kick_members=True)
    async def warnings(self, 
                      interaction: discord.Interaction, 
                      user: discord.Member):
        # Check if user has permission
        if not self.check_permissions(interaction):
            return await interaction.response.send_message("You don't have permission to view warnings!", ephemeral=True)
        
        guild_id = interaction.guild.id
        user_id = user.id
        
        # Get warnings from MongoDB
        cursor = self.warnings_collection.find({"guild_id": guild_id, "user_id": user_id}).sort("timestamp", 1)
        warnings_list = await cursor.to_list(length=None)
        
        if not warnings_list:
            return await interaction.response.send_message(f"{user.mention} has no warnings.", ephemeral=False)
        
        warning_count = len(warnings_list)
        
        # Create embed
        embed = discord.Embed(
            title=f"Warnings for {user.display_name}",
            description=f"{user.mention} has {warning_count} warning(s).",
            color=discord.Color.from_rgb(255, 255, 0),  # Yellow color
            timestamp=datetime.datetime.now()
        )
        
        # Add each warning to embed
        for i, warning in enumerate(warnings_list, 1):
            moderator = interaction.guild.get_member(warning["moderator_id"]) or "Unknown Moderator"
            moderator_mention = moderator.mention if isinstance(moderator, discord.Member) else moderator
            timestamp = warning["timestamp"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(warning["timestamp"], datetime.datetime) else "Unknown time"
            
            embed.add_field(
                name=f"Warning {i}",
                value=f"**Reason:** {warning['reason']}\n**By:** {moderator_mention}\n**When:** {timestamp}",
                inline=False
            )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="clearwarnings", description="Clear warnings for a user")
    @app_commands.describe(
        user="The user to clear warnings for"
    )
    @app_commands.default_permissions(ban_members=True)
    async def clearwarnings(self, 
                           interaction: discord.Interaction, 
                           user: discord.Member):
        # Check if user has permission (requiring ban_members for this to be more restrictive)
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message("You don't have permission to clear warnings!", ephemeral=True)
        
        guild_id = interaction.guild.id
        user_id = user.id
        
        # Get warning count first
        warning_count = await self.warnings_collection.count_documents({"guild_id": guild_id, "user_id": user_id})
        
        if warning_count == 0:
            return await interaction.response.send_message(f"{user.mention} has no warnings to clear.", ephemeral=False)
        
        # Delete warnings from MongoDB
        result = await self.warnings_collection.delete_many({"guild_id": guild_id, "user_id": user_id})
        
        # Create embed
        embed = discord.Embed(
            title="Warnings Cleared",
            description=f"Cleared {warning_count} warning(s) for {user.mention}.",
            color=discord.Color.from_rgb(0, 255, 0),  # Green color
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="Cleared by", value=interaction.user.mention, inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
