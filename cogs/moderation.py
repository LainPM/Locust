import discord
from discord import app_commands
from discord.ext import commands
import datetime
from ..utils.duration_parser import parse_duration, format_timedelta # If utils is in cogs/

# Helper function to create a standardized embed for mod actions
def create_mod_action_embed(action: str, user: discord.Member | discord.User, moderator: discord.User, reason: str, guild_name: str, duration: str = None, case_id: str | int = "N/A"):
    embed = discord.Embed(
        title=f"User {action} (Case #{case_id})",
        color=discord.Color.orange() if action in ["Warned", "Muted"] else discord.Color.red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=False)
    embed.add_field(name="Moderator", value=f"{moderator.mention} ({moderator.id})", inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    if duration:
        embed.add_field(name="Duration", value=duration, inline=False)
    embed.set_footer(text=f"Action taken in {guild_name} | Case ID: {case_id}")
    if user.avatar:
        embed.set_thumbnail(url=user.avatar.url)
    return embed

class ModerationCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="warn", description="Warns a user.")
    @app_commands.checks.has_permissions(moderate_members=True) # Example permission check
    @app_commands.describe(user="The user to warn.", reason="The reason for the warning.")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        if user == interaction.user:
            await interaction.response.send_message("You cannot warn yourself.", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("You cannot warn a bot.", ephemeral=True)
            return
        if user.guild_permissions.administrator: # Basic check to prevent warning admins
             await interaction.response.send_message("You cannot warn an administrator.", ephemeral=True)
             return
        
        await interaction.response.defer(ephemeral=False)

        if not self.bot.db_manager:
            await interaction.followup.send("Database connection is not available.", ephemeral=True)
            return

        warning_doc = await self.bot.db_manager.add_warning(
            guild_id=interaction.guild.id,
            user_id=user.id,
            moderator_id=interaction.user.id,
            reason=reason
        )
        
        case_id = warning_doc.get('case_id', 'N/A')
        embed = create_mod_action_embed("Warned", user, interaction.user, reason, interaction.guild.name, case_id=case_id)
        
        await interaction.followup.send(embed=embed)
        try:
            await user.send(f"You have been warned in **{interaction.guild.name}** for: {reason}. Case ID: {case_id}")
        except discord.Forbidden:
            await interaction.followup.send("Could not DM the user about the warning.", ephemeral=True)

    @app_commands.command(name="mute", description="Mutes a user for a specified duration.")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(user="The user to mute.", duration_str="Duration (e.g., 1h30m, 2d, 5m, perm). 'perm' or empty for permanent (no timeout).", reason="The reason for the mute.")
    async def mute(self, interaction: discord.Interaction, user: discord.Member, duration_str: str, reason: str):
        if user == interaction.user:
            await interaction.response.send_message("You cannot mute yourself.", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("You cannot mute a bot.", ephemeral=True)
            return
        if user.guild_permissions.administrator:
             await interaction.response.send_message("You cannot mute an administrator.", ephemeral=True)
             return
        
        await interaction.response.defer(ephemeral=False)

        if not self.bot.db_manager:
            await interaction.followup.send("Database connection is not available.", ephemeral=True)
            return

        delta = None
        actual_duration_display = "Permanent"
        expires_at = None
        delta_for_timeout = None # Initialize to ensure it's defined

        if duration_str and duration_str.lower() not in ["perm", "permanent", "none", ""]:
            delta = parse_duration(duration_str)
            if delta is None:
                await interaction.followup.send("Invalid duration format. Use like '1h30m', '2d', '5m', or 'perm'.", ephemeral=True)
                return
            if delta.total_seconds() <= 0:
                await interaction.followup.send("Duration must be positive.", ephemeral=True)
                return
            
            expires_at = datetime.datetime.now(datetime.timezone.utc) + delta
            actual_duration_display = format_timedelta(delta)
            
            if delta.total_seconds() > 28 * 24 * 60 * 60: # Discord timeout limit is 28 days
                await interaction.followup.send("Mute duration via timeout cannot exceed 28 days. For longer mutes, this will be a database record only, and Discord's timeout won't be applied.", ephemeral=True)
                # Do not apply Discord timeout if over 28 days, but still record it
                delta_for_timeout = None # Explicitly set to None
            else:
                delta_for_timeout = delta
        else: # Permanent mute (no Discord timeout)
            delta_for_timeout = None
            actual_duration_display = "Permanent"


        if delta_for_timeout: # Apply Discord's timeout feature if delta_for_timeout is set
            try:
                await user.timeout(delta_for_timeout, reason=reason)
            except discord.Forbidden:
                await interaction.followup.send("I don't have permissions to timeout this user. They might have a higher role. Mute recorded in DB.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"Failed to timeout user: {e}. Mute recorded in DB.", ephemeral=True)
        
        mute_doc = await self.bot.db_manager.add_mute(
            guild_id=interaction.guild.id,
            user_id=user.id,
            moderator_id=interaction.user.id,
            reason=reason,
            duration_str=actual_duration_display, # Store formatted duration
            expires_at=expires_at
        )
        
        case_id = mute_doc.get('case_id', 'N/A')
        embed = create_mod_action_embed("Muted", user, interaction.user, reason, interaction.guild.name, duration=actual_duration_display, case_id=case_id)
        
        await interaction.followup.send(embed=embed)
        try:
            await user.send(f"You have been muted in **{interaction.guild.name}** for: {reason}. Duration: {actual_duration_display}. Case ID: {case_id}")
        except discord.Forbidden:
            await interaction.followup.send("Could not DM the user about the mute.", ephemeral=True)

    @app_commands.command(name="kick", description="Kicks a user from the server.")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.describe(user="The user to kick.", reason="The reason for the kick.")
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        if user == interaction.user:
            await interaction.response.send_message("You cannot kick yourself.", ephemeral=True)
            return
        if user.bot: 
            await interaction.response.send_message("You cannot kick a bot using this command.", ephemeral=True)
            return
        if not interaction.guild.me.guild_permissions.kick_members:
            await interaction.response.send_message("I don't have permission to kick members.", ephemeral=True)
            return
        if user.guild_permissions.administrator or user.top_role >= interaction.guild.me.top_role :
             await interaction.response.send_message("You cannot kick this user due to role hierarchy or permissions.", ephemeral=True)
             return
        
        await interaction.response.defer(ephemeral=False)

        if not self.bot.db_manager:
            await interaction.followup.send("Database connection is not available.", ephemeral=True)
            return

        kick_doc = await self.bot.db_manager.add_kick(
            guild_id=interaction.guild.id,
            user_id=user.id,
            moderator_id=interaction.user.id,
            reason=reason
        )
        case_id = kick_doc.get('case_id', 'N/A')
        
        dm_message = f"You have been kicked from **{interaction.guild.name}** for: {reason}. Case ID: {case_id}"
        try:
            await user.send(dm_message)
        except discord.Forbidden:
            pass 

        try:
            await user.kick(reason=reason)
            embed = create_mod_action_embed("Kicked", user, interaction.user, reason, interaction.guild.name, case_id=case_id)
            await interaction.followup.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send("I lack the permissions to kick this user. They might have a higher role than me or I lack 'Kick Members' permission.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"Failed to kick user: {e}", ephemeral=True)


    @app_commands.command(name="ban", description="Bans a user from the server.")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.describe(user="The user to ban.", reason="The reason for the ban.")
    async def ban(self, interaction: discord.Interaction, user: discord.User, reason: str): # Can ban users not in server
        if user == interaction.user:
            await interaction.response.send_message("You cannot ban yourself.", ephemeral=True)
            return
        if not interaction.guild.me.guild_permissions.ban_members:
            await interaction.response.send_message("I don't have permission to ban members.", ephemeral=True)
            return
        
        if isinstance(user, discord.Member):
            if user.guild_permissions.administrator or user.top_role >= interaction.guild.me.top_role:
                await interaction.response.send_message("You cannot ban this user due to role hierarchy or permissions.", ephemeral=True)
                return
        
        await interaction.response.defer(ephemeral=False)

        if not self.bot.db_manager:
            await interaction.followup.send("Database connection is not available.", ephemeral=True)
            return

        ban_doc = await self.bot.db_manager.add_ban(
            guild_id=interaction.guild.id,
            user_id=user.id,
            moderator_id=interaction.user.id,
            reason=reason
        )
        case_id = ban_doc.get('case_id', 'N/A')

        dm_message = f"You have been banned from **{interaction.guild.name}** for: {reason}. Case ID: {case_id}"
        try:
            await user.send(dm_message)
        except discord.Forbidden:
            pass 
        except AttributeError: 
            pass


        try:
            await interaction.guild.ban(user, reason=reason)
            embed = create_mod_action_embed("Banned", user, interaction.user, reason, interaction.guild.name, case_id=case_id)
            await interaction.followup.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send("I lack the permissions to ban this user. They might have a higher role than me or I lack 'Ban Members' permission.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"Failed to ban user: {e}", ephemeral=True)

    # Error handler for this cog's commands
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(f"You don't have the required permissions to use this command: {error.missing_permissions[0].replace('_', ' ').title()}", ephemeral=True)
        elif isinstance(error, app_commands.BotMissingPermissions):
            await interaction.response.send_message(f"I am missing permissions to perform this action: {error.missing_permissions[0].replace('_', ' ').title()}", ephemeral=True)
        else:
            await interaction.response.send_message("An unexpected error occurred with this command.", ephemeral=True)
            # Optionally, log the error to bot's console/log file
            print(f"Error in ModerationCommands cog: {error}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCommands(bot))
