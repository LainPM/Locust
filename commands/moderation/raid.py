# commands/moderation/raid.py
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal

class RaidCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="setup_antiraid",
        description="Set up the anti-raid protection system"
    )
    @app_commands.describe(
        sensitivity="Raid detection sensitivity (0=Off, 1=Low, 2=Medium, 3=High)",
        mod_role="Moderator role to ping (optional)",
        manager_role="Community Manager role to ping (optional)",
        raid_alert_channel="Channel for detailed raid reports (optional)"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_antiraid(
        self,
        interaction: discord.Interaction,
        sensitivity: int,
        mod_role: Optional[discord.Role] = None,
        manager_role: Optional[discord.Role] = None,
        raid_alert_channel: Optional[discord.TextChannel] = None
    ):
        """Set up the anti-raid system for your server"""
        await interaction.response.defer(ephemeral=True)
        
        # Get the moderation system
        moderation_system = await self.bot.get_system("ModerationSystem")
        if not moderation_system:
            return await interaction.followup.send("Moderation system is not available.")
        
        # Validate sensitivity
        if sensitivity not in (0, 1, 2, 3):
            return await interaction.followup.send("Sensitivity must be 0 (Off), 1 (Low), 2 (Medium), or 3 (High)", ephemeral=True)
        
        # Update settings
        await moderation_system.raid_protection.update_settings(
            interaction.guild.id,
            {
                "enabled": sensitivity > 0,
                "sensitivity": sensitivity,
                "mod_role_id": mod_role.id if mod_role else None,
                "manager_role_id": manager_role.id if manager_role else None,
                "raid_alert_channel_id": raid_alert_channel.id if raid_alert_channel else None
            }
        )
        
        # Build response message
        if sensitivity == 0:
            message = "✅ Anti-Raid system has been **disabled** for this server."
        else:
            sensitivity_names = {1: "Low", 2: "Medium", 3: "High"}
            timeout_durations = {1: "5 minutes", 2: "10 minutes", 3: "30 minutes"}
            message = f"✅ Anti-Raid system has been set up with **{sensitivity_names[sensitivity]}** sensitivity!\n\n"
            
            message += f"• Default timeout duration: **{timeout_durations[sensitivity]}**\n"
                
            if mod_role:
                message += f"• Moderator Role: {mod_role.mention}\n"
                
            if manager_role:
                if sensitivity == 3:
                    message += f"• Community Manager: {manager_role.mention} (always pinged)\n"
                elif sensitivity == 2:
                    message += f"• Community Manager: {manager_role.mention} (pinged for extended timeouts)\n"
                else:
                    message += f"• Community Manager: {manager_role.mention} (pinged only for severe cases)\n"
                
            if raid_alert_channel:
                message += f"• Alert Channel: {raid_alert_channel.mention} ✅\n"
            
            message += "\nThe system will automatically monitor for raid behavior, delete recent raid messages, and timeout raiders."
        
        await interaction.followup.send(message, ephemeral=False)
    
    @app_commands.command(
        name="raid_mode",
        description="Manually enable or disable raid mode"
    )
    @app_commands.describe(
        enabled="Whether to enable or disable raid mode",
        duration_minutes="How long raid mode should last (default: 10 minutes)",
        action="Action to take on new members during raid mode"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Mute", value="mute"),
        app_commands.Choice(name="Kick", value="kick"),
        app_commands.Choice(name="Ban", value="ban")
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def raid_mode(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        duration_minutes: Optional[int] = 10,
        action: Optional[str] = "mute"
    ):
        """Manually control raid mode"""
        await interaction.response.defer(ephemeral=False)
        
        # Get the moderation system
        moderation_system = await self.bot.get_system("ModerationSystem")
        if not moderation_system:
            return await interaction.followup.send("Moderation system is not available.")
        
        # Enable or disable raid mode
        if enabled:
            # Validate duration
            if duration_minutes < 1 or duration_minutes > 120:
                return await interaction.followup.send("Duration must be between 1 and 120 minutes.")
            
            # Activate raid mode
            activated = await moderation_system.raid_protection.activate_raid_mode(
                interaction.guild.id,
                duration_minutes * 60,
                action,
                interaction.user.id
            )
            
            if activated:
                embed = discord.Embed(
                    title="🛡️ Raid Mode Activated",
                    description=f"Raid mode has been manually activated for {duration_minutes} minutes.",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.utcnow()
                )
                
                embed.add_field(
                    name="Action",
                    value=f"New members will be automatically {action}d.",
                    inline=False
                )
                
                embed.add_field(
                    name="Activated By",
                    value=interaction.user.mention,
                    inline=False
                )
                
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("Failed to activate raid mode. It may already be active.")
        else:
            # Deactivate raid mode
            deactivated = await moderation_system.raid_protection.deactivate_raid_mode(
                interaction.guild.id,
                interaction.user.id
            )
            
            if deactivated:
                embed = discord.Embed(
                    title="🛡️ Raid Mode Deactivated",
                    description="Raid mode has been manually deactivated.",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.utcnow()
                )
                
                embed.add_field(
                    name="Deactivated By",
                    value=interaction.user.mention,
                    inline=False
                )
                
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("Failed to deactivate raid mode. It may not be active.")

async def setup(bot):
    await bot.add_cog(RaidCommands(bot))
