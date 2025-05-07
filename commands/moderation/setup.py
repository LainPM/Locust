# commands/moderation/setup.py
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal

class ModerationSetupCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="setup_filter",
        description="Set up the content filter system"
    )
    @app_commands.describe(
        enabled="Whether to enable the content filter",
        log_channel="Channel to log filter actions to",
        notify_user="Whether to notify users when their messages are filtered",
        delete_matches="Whether to delete messages that match the filter"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def setup_filter(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        log_channel: Optional[discord.TextChannel] = None,
        notify_user: Optional[bool] = True,
        delete_matches: Optional[bool] = True
    ):
        """Set up the content filter system"""
        await interaction.response.defer(ephemeral=True)
        
        # Check for admin permissions
        if not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send("You need administrator permissions to set up the filter system.", ephemeral=True)
        
        # Get the moderation system
        moderation_system = await self.bot.get_system("ModerationSystem")
        if not moderation_system:
            return await interaction.followup.send("Moderation system is not available.", ephemeral=True)
        
        guild_id = interaction.guild.id
        
        # Create new settings
        settings = {
            "enabled": enabled,
            "log_channel": log_channel.id if log_channel else None,
            "notify_user": notify_user,
            "delete_matches": delete_matches,
            "updated_at": datetime.datetime.utcnow().isoformat(),
            "updated_by": interaction.user.id
        }
        
        # Update settings
        await self.bot.db["filter_settings"].update_one(
            {"guild_id": guild_id},
            {"$set": settings},
            upsert=True
        )
        
        # Update cache
        moderation_system.filter_settings_cache[guild_id] = await moderation_system.filter.load_settings(guild_id)
        
        # Create confirmation message
        status = "enabled" if enabled else "disabled"
        
        embed = discord.Embed(
            title="Content Filter Setup",
            description=f"The content filter system has been {status}.",
            color=discord.Color.green() if enabled else discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        
        embed.add_field(name="Delete Matches", value="Yes" if delete_matches else "No", inline=True)
        embed.add_field(name="Notify Users", value="Yes" if notify_user else "No", inline=True)
        
        if log_channel:
            embed.add_field(name="Log Channel", value=log_channel.mention, inline=True)
        
        # Add usage instructions
        embed.add_field(
            name="Usage",
            value=(
                "/blacklist <item> - Add an item to the blacklist\n"
                "/whitelist <item> - Add an item to the whitelist\n"
                "/view_blacklist - View blacklisted items\n"
                "/view_whitelist - View whitelisted items\n"
            ),
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(
        name="setup_raid_protection",
        description="Set up the raid protection system"
    )
    @app_commands.describe(
        enabled="Whether to enable raid protection",
        sensitivity="Sensitivity level for raid detection",
        mod_role="Role to ping for raid alerts",
        alert_channel="Channel to send raid alerts to",
        auto_raid_mode="Whether to automatically enable raid mode when a raid is detected",
        raid_mode_action="Action to take during raid mode"
    )
    @app_commands.choices(
        sensitivity=[
            app_commands.Choice(name="Low", value=1),
            app_commands.Choice(name="Medium", value=2),
            app_commands.Choice(name="High", value=3)
        ],
        raid_mode_action=[
            app_commands.Choice(name="Mute", value="mute"),
            app_commands.Choice(name="Kick", value="kick"),
            app_commands.Choice(name="Ban", value="ban")
        ]
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def setup_raid_protection(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        sensitivity: int = 1,
        mod_role: Optional[discord.Role] = None,
        alert_channel: Optional[discord.TextChannel] = None,
        auto_raid_mode: Optional[bool] = True,
        raid_mode_action: Optional[str] = "mute"
    ):
        """Set up the raid protection system"""
        await interaction.response.defer(ephemeral=True)
        
        # Check for admin permissions
        if not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send("You need administrator permissions to set up raid protection.", ephemeral=True)
        
        # Get the moderation system
        moderation_system = await self.bot.get_system("ModerationSystem")
        if not moderation_system:
            return await interaction.followup.send("Moderation system is not available.", ephemeral=True)
        
        guild_id = interaction.guild.id
        
        # Create new settings
        settings = {
            "enabled": enabled,
            "sensitivity": sensitivity,
            "mod_role_id": mod_role.id if mod_role else None,
            "alert_channel_id": alert_channel.id if alert_channel else None,
            "auto_raid_mode": auto_raid_mode,
            "raid_mode_action": raid_mode_action,
            "updated_at": datetime.datetime.utcnow().isoformat(),
            "updated_by": interaction.user.id
        }
        
        # Update settings
        await self.bot.db["raid_settings"].update_one(
            {"guild_id": guild_id},
            {"$set": settings},
            upsert=True
        )
        
        # Update cache
        moderation_system.raid_settings_cache[guild_id] = await moderation_system.raid_protection.load_settings(guild_id)
        
        # Create confirmation message
        sensitivity_names = {1: "Low", 2: "Medium", 3: "High"}
        status = "enabled" if enabled else "disabled"
        
        embed = discord.Embed(
            title="Raid Protection Setup",
            description=f"Raid protection has been {status}.",
            color=discord.Color.green() if enabled else discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        
        if enabled:
            embed.add_field(name="Sensitivity", value=sensitivity_names.get(sensitivity, "Low"), inline=True)
            embed.add_field(name="Auto Raid Mode", value="Yes" if auto_raid_mode else "No", inline=True)
            embed.add_field(name="Raid Mode Action", value=raid_mode_action.title(), inline=True)
            
            if mod_role:
                embed.add_field(name="Alert Mention", value=mod_role.mention, inline=True)
                
            if alert_channel:
                embed.add_field(name="Alert Channel", value=alert_channel.mention, inline=True)
        
        # Add usage instructions
        embed.add_field(
            name="Usage",
            value=(
                "/raid_mode on - Manually enable raid mode\n"
                "/raid_mode off - Manually disable raid mode\n"
                "/raid_stats - View current raid statistics\n"
            ),
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ModerationSetupCommand(bot))
