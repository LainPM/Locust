# cogs/moderation.py
import discord
from discord.ext import commands
from discord import app_commands, ui
import datetime

class PaginationView(ui.View):
    def __init__(self, mod_logs, target_user, user_id, guild, logs_per_page=5, timeout=180):
        super().__init__(timeout=timeout)
        self.mod_logs = mod_logs
        self.logs_per_page = logs_per_page
        self.current_page = 1
        self.max_pages = max(1, ((len(mod_logs) - 1) // logs_per_page) + 1)
        self.target_user = target_user
        self.user_id = user_id
        self.guild = guild  # Store guild reference for member lookups
        
        # Disable buttons as needed initially
        self.previous_button.disabled = True
        if self.max_pages <= 1:
            self.next_button.disabled = True

    @ui.button(label="Previous", style=discord.ButtonStyle.secondary, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: ui.Button):
        self.current_page -= 1
        # Update button states
        button.disabled = self.current_page == 1
        self.next_button.disabled = False
        
        # Create the updated embed
        embed = self.create_log_embed()
        
        # Respond to the interaction
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.errors.InteractionResponded:
            # If already responded, use followup
            await interaction.followup.edit_message(embed=embed, view=self)
        except Exception as e:
            print(f"Error in previous button: {e}")

    @ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        self.current_page += 1
        # Update button states
        button.disabled = self.current_page >= self.max_pages
        self.previous_button.disabled = False
        
        # Create the updated embed
        embed = self.create_log_embed()
        
        # Respond to the interaction
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.errors.InteractionResponded:
            # If already responded, use followup
            await interaction.followup.edit_message(embed=embed, view=self)
        except Exception as e:
            print(f"Error in next button: {e}")
            
    def create_log_embed(self):
        # Calculate start and end indices for the current page
        start_idx = (self.current_page - 1) * self.logs_per_page
        end_idx = min(start_idx + self.logs_per_page, len(self.mod_logs))
        current_logs = self.mod_logs[start_idx:end_idx]
        
        # Create embed for current page
        embed = discord.Embed(
            title=f"Moderation Logs for {self.target_user}",
            description=f"Showing logs {start_idx+1}-{end_idx} of {len(self.mod_logs)}",
            color=discord.Color.from_rgb(255, 165, 0),  # Orange color
            timestamp=datetime.datetime.now()
        )
        
        for log in current_logs:
            case_id = log.get("case_id", "Unknown")
            action_type = log.get("action_type", "unknown")
            reason = log.get("reason", "No reason provided")
            moderator_id = log.get("moderator_id")
            
            # Handle timestamp correctly
            timestamp = log.get("timestamp")
            if isinstance(timestamp, datetime.datetime):
                formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            else:
                formatted_time = "Unknown time"
            
            # Get moderator mention more safely
            moderator_name = "Unknown Moderator"
            if moderator_id and self.guild:
                moderator = self.guild.get_member(moderator_id)
                if moderator:
                    moderator_name = moderator.mention
                    
            # Format the field value based on action type
            value = f"**Reason:** {reason}\n**By:** {moderator_name}\n**When:** {formatted_time}"
            
            # Add action-specific details if they exist
            if "duration" in log and log["duration"]:
                value += f"\n**Duration:** {log['duration']} minutes"
            if "delete_days" in log and log["delete_days"]:
                value += f"\n**Messages Deleted:** {log['delete_days']} days"
                
            embed.add_field(
                name=f"Case #{case_id} | {action_type.title()} | {formatted_time}",
                value=value,
                inline=False
            )
        
        # Set footer
        embed.set_footer(text=f"User ID: {self.user_id} | Page {self.current_page}/{self.max_pages}")
        
        return embed

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Reference to MongoDB collection for moderation logs
        self.modlogs_collection = bot.warnings_collection  # Using the same collection for now

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
    
    # Helper function to log moderation actions to database
    async def log_mod_action(self, guild_id, user_id, moderator_id, action_type, reason, **kwargs):
        """
        Log a moderation action to the database
        
        Parameters:
        - guild_id: ID of the guild where action took place
        - user_id: ID of the user who received the action
        - moderator_id: ID of the moderator who performed the action
        - action_type: Type of action (warn, mute, unmute, kick, ban)
        - reason: Reason for the action
        - **kwargs: Additional data for specific action types
        """
        # Get the next case ID for this guild
        latest_case = await self.modlogs_collection.find_one(
            {"guild_id": guild_id},
            sort=[("case_id", -1)]  # Sort by case_id in descending order
        )
        
        # Determine the next case ID
        if latest_case and "case_id" in latest_case:
            try:
                next_case_id = int(latest_case["case_id"]) + 1
            except (ValueError, TypeError):
                # If case_id isn't a valid integer, start at 1
                next_case_id = 1
        else:
            # No previous cases found, start at 1
            next_case_id = 1
            
        log_entry = {
            "guild_id": guild_id,
            "user_id": user_id,
            "moderator_id": moderator_id,
            "action_type": action_type,
            "reason": reason,
            "timestamp": datetime.datetime.now(),
            "case_id": next_case_id
        }
        
        # Add any additional data from kwargs
        log_entry.update(kwargs)
        
        # Insert log to database
        await self.modlogs_collection.insert_one(log_entry)
        
        # Return the case ID for reference
        return next_case_id

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
            
            # Log the action to database and get case ID
            case_id = await self.log_mod_action(
                guild_id=interaction.guild.id,
                user_id=user.id,
                moderator_id=interaction.user.id,
                action_type="mute",
                reason=reason,
                duration=duration
            )
            
            # Create embed with case ID
            embed = self.create_mod_embed("Mute", user, interaction.user, reason)
            embed.add_field(name="Duration", value=f"{duration} minutes", inline=False)
            embed.add_field(name="Case ID", value=f"#{case_id}", inline=False)
            
            # Try to send DM to user with case ID
            try:
                dm_embed = discord.Embed(
                    title=f"You were muted in {interaction.guild.name}",
                    description=f"You have been muted for {duration} minutes.",
                    color=discord.Color.from_rgb(255, 0, 0),  # Red color
                    timestamp=datetime.datetime.now()
                )
                dm_embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
                dm_embed.add_field(name="Muted by", value=interaction.user.display_name, inline=False)
                dm_embed.add_field(name="Case ID", value=f"#{case_id}", inline=False)
                dm_embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
                dm_embed.set_footer(text=f"Server ID: {interaction.guild.id}")
                
                await user.send(embed=dm_embed)
            except discord.Forbidden:
                # If DM fails, add note to channel embed
                await interaction.followup.send(f"Note: Could not DM {user.mention} about this mute.", ephemeral=True)
                
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
            
            # Log the action to database and get case ID
            case_id = await self.log_mod_action(
                guild_id=interaction.guild.id,
                user_id=user.id,
                moderator_id=interaction.user.id,
                action_type="unmute",
                reason=reason
            )
            
            # Create embed with case ID
            embed = discord.Embed(
                title="User Unmuted",
                description=f"{user.mention} has been unmuted.",
                color=discord.Color.from_rgb(0, 255, 0),  # Green color
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            embed.add_field(name="Unmuted by", value=interaction.user.mention, inline=False)
            embed.add_field(name="Case ID", value=f"#{case_id}", inline=False)
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text=f"User ID: {user.id}")
            
            # Try to send DM to user with case ID
            try:
                dm_embed = discord.Embed(
                    title=f"You were unmuted in {interaction.guild.name}",
                    description=f"Your timeout has been removed.",
                    color=discord.Color.from_rgb(0, 255, 0),  # Green color
                    timestamp=datetime.datetime.now()
                )
                dm_embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
                dm_embed.add_field(name="Unmuted by", value=interaction.user.display_name, inline=False)
                dm_embed.add_field(name="Case ID", value=f"#{case_id}", inline=False)
                dm_embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
                dm_embed.set_footer(text=f"Server ID: {interaction.guild.id}")
                
                await user.send(embed=dm_embed)
            except discord.Forbidden:
                # If DM fails, add note to channel embed
                await interaction.followup.send(f"Note: Could not DM {user.mention} about this unmute.", ephemeral=True)
            
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
            # Try to send DM to user before kicking with case ID (need to create case first)
            # Log the action to database and get case ID
            case_id = await self.log_mod_action(
                guild_id=interaction.guild.id,
                user_id=user.id,
                moderator_id=interaction.user.id,
                action_type="kick",
                reason=reason
            )
            
            # Try to DM the user before kicking
            try:
                dm_embed = discord.Embed(
                    title=f"You were kicked from {interaction.guild.name}",
                    description="You have been kicked from the server.",
                    color=discord.Color.from_rgb(255, 0, 0),  # Red color
                    timestamp=datetime.datetime.now()
                )
                dm_embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
                dm_embed.add_field(name="Kicked by", value=interaction.user.display_name, inline=False)
                dm_embed.add_field(name="Case ID", value=f"#{case_id}", inline=False)
                dm_embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
                
                await user.send(embed=dm_embed)
            except Exception:
                # If DM fails, continue with kick
                pass
            
            # Now kick the user
            await user.kick(reason=reason)
            
            # Create embed with case ID for server
            embed = self.create_mod_embed("Kick", user, interaction.user, reason)
            embed.add_field(name="Case ID", value=f"#{case_id}", inline=False)
            
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
            # Log the action to database and get case ID
            case_id = await self.log_mod_action(
                guild_id=interaction.guild.id,
                user_id=user.id,
                moderator_id=interaction.user.id,
                action_type="ban",
                reason=reason,
                delete_days=delete_days
            )
            
            # Try to DM the user before banning
            try:
                dm_embed = discord.Embed(
                    title=f"You were banned from {interaction.guild.name}",
                    description="You have been banned from the server.",
                    color=discord.Color.from_rgb(255, 0, 0),  # Red color
                    timestamp=datetime.datetime.now()
                )
                dm_embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
                dm_embed.add_field(name="Banned by", value=interaction.user.display_name, inline=False)
                dm_embed.add_field(name="Case ID", value=f"#{case_id}", inline=False)
                dm_embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
                
                await user.send(embed=dm_embed)
            except Exception:
                # If DM fails, continue with ban
                pass
            
            # Now ban the user
            await user.ban(delete_message_days=delete_days, reason=reason)
            
            # Create embed for server with case ID
            embed = self.create_mod_embed("Ban", user, interaction.user, reason)
            if delete_days > 0:
                embed.add_field(name="Message Deletion", value=f"Deleted messages from the past {delete_days} days", inline=False)
            embed.add_field(name="Case ID", value=f"#{case_id}", inline=False)
            
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
        
        # Add warning to MongoDB and get case ID
        case_id = await self.log_mod_action(
            guild_id=interaction.guild.id,
            user_id=user.id,
            moderator_id=interaction.user.id,
            action_type="warn",
            reason=reason
        )
        
        # Get warning count
        warning_count = await self.modlogs_collection.count_documents({
            "guild_id": interaction.guild.id, 
            "user_id": user.id,
            "action_type": "warn"
        })
        
        # Create warning embed for channel with case ID
        embed = discord.Embed(
            title="User Warned",
            description=f"{user.mention} has been warned.",
            color=discord.Color.from_rgb(255, 255, 0),  # Yellow color
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Warned by", value=interaction.user.mention, inline=False)
        embed.add_field(name="Warning Count", value=str(warning_count), inline=False)
        embed.add_field(name="Case ID", value=f"#{case_id}", inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")
        
        # Send embed to channel
        await interaction.response.send_message(embed=embed)
        
        # Create DM embed with case ID
        dm_embed = discord.Embed(
            title=f"Warning from {interaction.guild.name}",
            description=f"You have been warned by {interaction.user.display_name}.",
            color=discord.Color.from_rgb(255, 255, 0),  # Yellow color
            timestamp=datetime.datetime.now()
        )
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        dm_embed.add_field(name="Warning Count", value=str(warning_count), inline=False)
        dm_embed.add_field(name="Case ID", value=f"#{case_id}", inline=False)
        dm_embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        dm_embed.set_footer(text=f"Server ID: {interaction.guild.id}")
        
        # Try to send DM
        try:
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            # If DM fails, add note to channel embed
            await interaction.followup.send(f"Note: Could not DM {user.mention} about this warning.", ephemeral=True)
    
    @app_commands.command(name="modlogs", description="Check moderation logs for a user")
@app_commands.describe(
    user="The user to check logs for"
)
@app_commands.default_permissions(kick_members=True)
async def modlogs(self, 
                 interaction: discord.Interaction, 
                 user: discord.Member):
    # Check if user has permission
    if not self.check_permissions(interaction):
        return await interaction.response.send_message("You don't have permission to view moderation logs!", ephemeral=True)
    
    # Let the user know we're fetching logs
    await interaction.response.defer(thinking=True)
    
    guild_id = interaction.guild.id
    user_id = user.id
    
    try:
        # Get logs from MongoDB using to_list with length=None to get all documents
        cursor = self.modlogs_collection.find({"guild_id": guild_id, "user_id": user_id}).sort("timestamp", -1)  # Newest first
        logs_list = await cursor.to_list(length=None)
        
        if not logs_list:
            return await interaction.followup.send(f"{user.mention} has no moderation logs.", ephemeral=False)
        
        log_count = len(logs_list)
        logs_per_page = 5
        
        # Create initial embed for first page
        embed = discord.Embed(
            title=f"Moderation Logs for {user.display_name}",
            description=f"{user.mention} has {log_count} logs. Showing most recent logs.",
            color=discord.Color.from_rgb(255, 165, 0),  # Orange color
            timestamp=datetime.datetime.now()
        )
        
        # Display first page of logs
        for i, log in enumerate(logs_list[:logs_per_page], 1):
            case_id = log.get("case_id", "Unknown")
            action_type = log.get("action_type", "unknown")
            reason = log.get("reason", "No reason provided")
            moderator_id = log.get("moderator_id")
            
            # Handle timestamp correctly
            timestamp = log.get("timestamp")
            if isinstance(timestamp, datetime.datetime):
                formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            else:
                formatted_time = "Unknown time"
            
            # Get moderator mention safely
            moderator_name = "Unknown Moderator"
            if moderator_id:
                moderator = interaction.guild.get_member(moderator_id)
                if moderator:
                    moderator_name = moderator.mention
            
            # Format field content based on action type
            value = f"**Reason:** {reason}\n**By:** {moderator_name}\n**When:** {formatted_time}"
            
            # Add action-specific details if they exist
            if "duration" in log and log["duration"]:
                value += f"\n**Duration:** {log['duration']} minutes"
            if "delete_days" in log and log["delete_days"]:
                value += f"\n**Messages Deleted:** {log['delete_days']} days"
            
            embed.add_field(
                name=f"Case #{case_id} | {action_type.title()} | {formatted_time}",
                value=value,
                inline=False
            )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {user.id} | Page 1/{(log_count-1)//logs_per_page + 1}")
        
        # Create pagination view if there are more than logs_per_page logs
        if log_count > logs_per_page:
            view = PaginationView(logs_list, user.display_name, user.id, interaction.guild, logs_per_page=logs_per_page)
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed)
            
    except Exception as e:
        print(f"Error in modlogs command: {e}")
        await interaction.followup.send(f"An error occurred while fetching moderation logs: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="clearmodlogs", description="Clear all moderation logs for a user")
    @app_commands.describe(
        user="The user to clear moderation logs for"
    )
    @app_commands.default_permissions(ban_members=True)
    async def clearmodlogs(self, 
                          interaction: discord.Interaction, 
                          user: discord.Member):
        # Check if user has permission (requiring ban_members for this to be more restrictive)
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message("You don't have permission to clear moderation logs!", ephemeral=True)
        
        guild_id = interaction.guild.id
        user_id = user.id
        
        # Get log count first
        log_count = await self.modlogs_collection.count_documents({
            "guild_id": guild_id, 
            "user_id": user_id
        })
        
        if log_count == 0:
            return await interaction.response.send_message(f"{user.mention} has no moderation logs to clear.", ephemeral=False)
        
        # Delete all logs for this user from MongoDB
        result = await self.modlogs_collection.delete_many({
            "guild_id": guild_id, 
            "user_id": user_id
        })
        
        # Create embed - NOT logging this action to modlogs
        embed = discord.Embed(
            title="Moderation Logs Cleared",
            description=f"Cleared {log_count} moderation logs for {user.mention}.",
            color=discord.Color.from_rgb(0, 255, 0),  # Green color
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="Cleared by", value=interaction.user.mention, inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="removecase", description="Remove a specific moderation case by ID")
    @app_commands.describe(
        case_id="The case ID to remove"
    )
    @app_commands.default_permissions(ban_members=True)
    async def removecase(self, 
                        interaction: discord.Interaction, 
                        case_id: int):
        # Check if user has permission
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message("You don't have permission to remove moderation cases!", ephemeral=True)
        
        guild_id = interaction.guild.id
        
        # Find the case
        case = await self.modlogs_collection.find_one({
            "guild_id": guild_id,
            "case_id": case_id
        })
        
        if not case:
            return await interaction.response.send_message(f"Case #{case_id} not found.", ephemeral=True)
        
        # Get user information for the case
        user_id = case.get("user_id")
        action_type = case.get("action_type", "unknown")
        
        # Delete the case
        await self.modlogs_collection.delete_one({
            "guild_id": guild_id,
            "case_id": case_id
        })
        
        # Try to get user mention if possible
        user = interaction.guild.get_member(user_id) if user_id else None
        user_mention = user.mention if user else f"User ID: {user_id}"
        
        # Create embed - NOT logging this action to modlogs
        embed = discord.Embed(
            title="Case Removed",
            description=f"Case #{case_id} has been removed.",
            color=discord.Color.from_rgb(0, 255, 0),  # Green color
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="User", value=user_mention, inline=False)
        embed.add_field(name="Action Type", value=action_type.title(), inline=False)
        embed.add_field(name="Removed by", value=interaction.user.mention, inline=False)
        embed.set_footer(text=f"Guild ID: {guild_id}")
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
