import discord
from discord import app_commands
from discord.ext import commands
import datetime
# from ..utils.duration_parser import format_timedelta # No longer needed here as duration_str is stored

class ModlogsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="modlogs", description="View moderation logs for a user.")
    @app_commands.checks.has_permissions(moderate_members=True) # Or a more specific modlog viewing permission
    @app_commands.describe(user="The user whose moderation logs you want to see.")
    async def modlogs(self, interaction: discord.Interaction, user: discord.User):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)

        if not self.bot.db_manager: # Check if db_manager is initialized
            await interaction.followup.send("Database connection is not available.", ephemeral=True)
            return

        warnings_list = await self.bot.db_manager.get_warnings(guild_id=interaction.guild.id, user_id=user.id)
        mutes_list = await self.bot.db_manager.get_mutes(guild_id=interaction.guild.id, user_id=user.id)
        kicks_list = await self.bot.db_manager.get_kicks(guild_id=interaction.guild.id, user_id=user.id)
        bans_list = await self.bot.db_manager.get_bans(guild_id=interaction.guild.id, user_id=user.id)
        
        embed = discord.Embed(
            title=f"Moderation Logs for {user.name}#{user.discriminator}",
            color=discord.Color.light_grey(), # Changed color slightly
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)

        if not any([warnings_list, mutes_list, kicks_list, bans_list]):
            embed.description = "No moderation actions found for this user."
        else:
            # Sort all actions by timestamp to get an overall chronological view if needed,
            # or sort within each category. For this example, sorting within categories.
            # Showing latest 5 for each category as an example.

            if warnings_list:
                warn_text = ""
                for warn in sorted(warnings_list, key=lambda x: x['timestamp'], reverse=True)[:5]:
                    mod_obj = interaction.guild.get_member(warn['moderator_id']) or self.bot.get_user(warn['moderator_id']) or f"ID: {warn['moderator_id']}"
                    mod_mention = mod_obj.mention if isinstance(mod_obj, (discord.User, discord.Member)) else str(mod_obj)
                    timestamp_str = discord.utils.format_dt(warn['timestamp'], style='R') # Relative time
                    case_id_str = f" (Case: {warn.get('case_id', 'N/A')})"
                    warn_text += f"- Reason: {warn['reason']} by {mod_mention} {timestamp_str}{case_id_str}\n"
                embed.add_field(name=f"Recent Warnings ({len(warnings_list)})", value=warn_text if warn_text else "None", inline=False)

            if mutes_list:
                mute_text = ""
                for m in sorted(mutes_list, key=lambda x: x['timestamp'], reverse=True)[:5]:
                    mod_obj = interaction.guild.get_member(m['moderator_id']) or self.bot.get_user(m['moderator_id']) or f"ID: {m['moderator_id']}"
                    mod_mention = mod_obj.mention if isinstance(mod_obj, (discord.User, discord.Member)) else str(mod_obj)
                    timestamp_str = discord.utils.format_dt(m['timestamp'], style='R')
                    
                    duration_display = f"(Duration: {m.get('duration_str', 'N/A')})"
                    
                    active_status = ""
                    if m.get('active', False): # Check 'active' field from DB
                        if m.get('expires_at') is None: # Permanent active mute
                            active_status = " (Active - Permanent)"
                        elif m['expires_at'] > datetime.datetime.now(datetime.timezone.utc):
                            active_status = f" (Active - ends {discord.utils.format_dt(m['expires_at'], style='R')})"
                        else: # Expired but still marked active (should be cleaned up by a task ideally)
                            active_status = f" (Expired {discord.utils.format_dt(m['expires_at'], style='R')})"
                    else: # Not active
                        if m.get('expires_at') and m['expires_at'] <= datetime.datetime.now(datetime.timezone.utc):
                             active_status = f" (Expired {discord.utils.format_dt(m['expires_at'], style='R')})"
                        else: # Manually unmuted or duration ended and record updated
                             active_status = " (Inactive)"

                    case_id_str = f" (Case: {m.get('case_id', 'N/A')})"
                    mute_text += f"- Reason: {m['reason']} by {mod_mention} {timestamp_str} {duration_display}{active_status}{case_id_str}\n"
                embed.add_field(name=f"Recent Mutes ({len(mutes_list)})", value=mute_text if mute_text else "None", inline=False)
            
            if kicks_list:
                kick_text = ""
                for kick in sorted(kicks_list, key=lambda x: x['timestamp'], reverse=True)[:5]:
                    mod_obj = interaction.guild.get_member(kick['moderator_id']) or self.bot.get_user(kick['moderator_id']) or f"ID: {kick['moderator_id']}"
                    mod_mention = mod_obj.mention if isinstance(mod_obj, (discord.User, discord.Member)) else str(mod_obj)
                    timestamp_str = discord.utils.format_dt(kick['timestamp'], style='R')
                    case_id_str = f" (Case: {kick.get('case_id', 'N/A')})"
                    kick_text += f"- Reason: {kick['reason']} by {mod_mention} {timestamp_str}{case_id_str}\n"
                embed.add_field(name=f"Recent Kicks ({len(kicks_list)})", value=kick_text if kick_text else "None", inline=False)

            if bans_list:
                ban_text = ""
                for ban in sorted(bans_list, key=lambda x: x['timestamp'], reverse=True)[:5]:
                    mod_obj = interaction.guild.get_member(ban['moderator_id']) or self.bot.get_user(ban['moderator_id']) or f"ID: {ban['moderator_id']}"
                    mod_mention = mod_obj.mention if isinstance(mod_obj, (discord.User, discord.Member)) else str(mod_obj)
                    timestamp_str = discord.utils.format_dt(ban['timestamp'], style='R')
                    case_id_str = f" (Case: {ban.get('case_id', 'N/A')})"
                    # Note: Bans are generally considered active unless an unban record exists.
                    # This example doesn't explicitly show unbans.
                    ban_text += f"- Reason: {ban['reason']} by {mod_mention} {timestamp_str}{case_id_str}\n"
                embed.add_field(name=f"Recent Bans ({len(bans_list)})", value=ban_text if ban_text else "None", inline=False)
        
        embed.set_footer(text=f"Requested by {interaction.user.name} | User ID: {user.id}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(f"You don't have the required permissions to use this command.", ephemeral=True)
        else:
            # Log the error for debugging
            print(f"Error in ModlogsCog: {error} - Interaction: {interaction.data}")
            # Send a generic error message
            if not interaction.response.is_done():
                await interaction.response.send_message("An unexpected error occurred with this command.", ephemeral=True)
            else:
                await interaction.followup.send("An unexpected error occurred with this command.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModlogsCog(bot))
