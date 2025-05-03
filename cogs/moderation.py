import discord
from discord.ext import commands
from discord import app_commands, ui
import datetime
from typing import Optional, Union, Dict, Any, List

class ModLogPaginationView(ui.View):
    """Pagination view for moderation logs"""
    def __init__(self, mod_logs, target_user, user_id, guild, logs_per_page=5, timeout=180):
        super().__init__(timeout=timeout)
        self.mod_logs = mod_logs
        self.logs_per_page = logs_per_page
        self.current_page = 1
        self.max_pages = max(1, ((len(mod_logs) - 1) // logs_per_page) + 1)
        self.target_user = target_user
        self.user_id = user_id
        self.guild = guild
        
        # Set initial button states
        self.previous_button.disabled = True
        if self.max_pages <= 1:
            self.next_button.disabled = True

    @ui.button(label="Previous", style=discord.ButtonStyle.secondary, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: ui.Button):
        self.current_page = max(1, self.current_page - 1)
        
        # Update button states
        button.disabled = self.current_page == 1
        self.next_button.disabled = False
        
        # Send response
        await self._update_message(interaction)

    @ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        self.current_page = min(self.max_pages, self.current_page + 1)
        
        # Update button states
        button.disabled = self.current_page >= self.max_pages
        self.previous_button.disabled = False
        
        # Send response
        await self._update_message(interaction)
    
    async def _update_message(self, interaction: discord.Interaction):
        """Handle updating the message while handling potential errors"""
        embed = self.create_log_embed()
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.errors.InteractionResponded:
            try:
                # Fallback if the interaction was already responded to
                await interaction.followup.edit_message(embed=embed, view=self)
            except Exception as e:
                print(f"Error updating pagination: {e}")
        except Exception as e:
            print(f"Error in pagination: {e}")
            
    def create_log_embed(self):
        """Create embed for current page of logs"""
        start_idx = (self.current_page - 1) * self.logs_per_page
        end_idx = min(start_idx + self.logs_per_page, len(self.mod_logs))
        current_logs = self.mod_logs[start_idx:end_idx]
        
        embed = discord.Embed(
            title=f"Moderation Logs for {self.target_user}",
            description=f"Showing logs {start_idx+1}-{end_idx} of {len(self.mod_logs)}",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now()
        )
        
        for log in current_logs:
            # Extract log info
            case_id = log.get("case_id", "Unknown")
            action_type = log.get("action_type", "unknown").title()
            reason = log.get("reason", "No reason provided")
            
            # Format timestamp
            timestamp = log.get("timestamp")
            formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S") if isinstance(timestamp, datetime.datetime) else "Unknown time"
            
            # Get moderator safely
            moderator_id = log.get("moderator_id")
            moderator_name = "Unknown Moderator"
            if moderator_id and self.guild:
                moderator = self.guild.get_member(moderator_id)
                if moderator:
                    moderator_name = moderator.mention
            
            # Format field value
            value = [f"**Reason:** {reason}", f"**By:** {moderator_name}", f"**When:** {formatted_time}"]
            
            # Add action-specific details
            if log.get("duration"):
                value.append(f"**Duration:** {log['duration']} minutes")
            if log.get("delete_days"):
                value.append(f"**Messages Deleted:** {log['delete_days']} days")
                
            embed.add_field(
                name=f"Case #{case_id} | {action_type} | {formatted_time}",
                value="\n".join(value),
                inline=False
            )
        
        embed.set_footer(text=f"User ID: {self.user_id} | Page {self.current_page}/{self.max_pages}")
        return embed

class Moderation(commands.Cog):
    """Moderation commands for Discord server management"""
    
    def __init__(self, bot):
        self.bot = bot
        self.modlogs_collection = bot.warnings_collection
    
    # ===== UTILITY FUNCTIONS =====
    
    def check_permissions(self, interaction: discord.Interaction, permission: str = "moderate_members") -> bool:
        """Check if user has required permission"""
        permissions = interaction.user.guild_permissions
        
        if permission == "moderate_members":
            return permissions.moderate_members
        elif permission == "kick_members":
            return permissions.kick_members
        elif permission == "ban_members":
            return permissions.ban_members
        # Fallback check for general moderation
        return permissions.ban_members or permissions.kick_members or permissions.moderate_members
    
    async def create_and_send_embed(self, interaction: discord.Interaction, 
                                  action: str, target: discord.Member, 
                                  reason: str, case_id: int,
                                  **kwargs) -> None:
        """Create and send action embed to the channel"""
        
        embed = self._create_mod_embed(action, target, interaction.user, reason, case_id, **kwargs)
        
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error sending embed: {e}")
    
    def _create_mod_embed(self, action: str, target: discord.Member, 
                         moderator: discord.Member, reason: str, 
                         case_id: int, **kwargs) -> discord.Embed:
        """Create a standardized embed for moderation actions"""
        
        # Determine color based on action
        color_map = {
            "Warn": discord.Color.yellow(),
            "Mute": discord.Color.red(),
            "Unmute": discord.Color.green(),
            "Kick": discord.Color.red(),
            "Ban": discord.Color.red(),
            "Unban": discord.Color.green()
        }
        color = color_map.get(action, discord.Color.red())
        
        # Create base embed
        embed = discord.Embed(
            title=f"User {action}ed",
            description=f"**{target}** has been {action.lower()}ed.",
            color=color,
            timestamp=datetime.datetime.now()
        )
        
        # Add standard fields
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        embed.add_field(name=f"{action}ed by", value=moderator.mention, inline=False)
        embed.add_field(name="Case ID", value=f"#{case_id}", inline=False)
        
        # Add action-specific fields from kwargs
        if kwargs.get("duration"):
            embed.add_field(name="Duration", value=f"{kwargs['duration']} minutes", inline=False)
        if kwargs.get("delete_days"):
            embed.add_field(name="Message Deletion", value=f"Deleted messages from the past {kwargs['delete_days']} days", inline=False)
        
        # Set thumbnail and footer
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text=f"User ID: {target.id}")
        
        return embed
    
    async def create_and_send_dm(self, user: discord.Member, guild: discord.Guild, 
                                action: str, reason: str, case_id: int, 
                                moderator_name: str, **kwargs) -> bool:
        """
        Try to send a DM to a user about a moderation action.
        Returns True if successful, False otherwise.
        """
        try:
            # Create DM embed
            color_map = {
                "Warn": discord.Color.yellow(),
                "Mute": discord.Color.red(),
                "Unmute": discord.Color.green(),
                "Kick": discord.Color.red(),
                "Ban": discord.Color.red(),
                "Unban": discord.Color.green()
            }
            color = color_map.get(action, discord.Color.red())
            
            embed = discord.Embed(
                title=f"You were {action.lower()}ed in {guild.name}",
                description=f"You have been {action.lower()}ed.",
                color=color,
                timestamp=datetime.datetime.now()
            )
            
            # Add standard fields
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            embed.add_field(name=f"{action}ed by", value=moderator_name, inline=False)
            embed.add_field(name="Case ID", value=f"#{case_id}", inline=False)
            
            # Add action-specific fields
            if kwargs.get("duration"):
                embed.add_field(name="Duration", value=f"{kwargs['duration']} minutes", inline=False)
            
            # Set thumbnail and footer
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            embed.set_footer(text=f"Server ID: {guild.id}")
            
            # Send DM
            await user.send(embed=embed)
            return True
        except Exception:
            return False
    
    async def log_mod_action(self, guild_id: int, user_id: int, 
                           moderator_id: int, action_type: str, 
                           reason: str, **kwargs) -> int:
        """
        Log a moderation action to the database and return the case ID
        """
        try:
            # Find the next case ID
            latest_case = await self.modlogs_collection.find_one(
                {"guild_id": guild_id},
                sort=[("case_id", -1)]
            )
            
            next_case_id = 1  # Default if no previous cases
            if latest_case and "case_id" in latest_case:
                try:
                    next_case_id = int(latest_case["case_id"]) + 1
                except (ValueError, TypeError):
                    pass
            
            # Create log entry
            log_entry = {
                "guild_id": guild_id,
                "user_id": user_id,
                "moderator_id": moderator_id,
                "action_type": action_type,
                "reason": reason,
                "timestamp": datetime.datetime.now(),
                "case_id": next_case_id
            }
            
            # Add additional fields from kwargs
            for key, value in kwargs.items():
                if value is not None:
                    log_entry[key] = value
            
            # Insert log
            await self.modlogs_collection.insert_one(log_entry)
            return next_case_id
        except Exception as e:
            print(f"Error logging moderation action: {e}")
            return 0  # Return 0 for error cases
    
    async def get_user_logs(self, guild_id: int, user_id: int) -> List[Dict[str, Any]]:
        """Get all moderation logs for a user in a guild"""
        try:
            cursor = self.modlogs_collection.find(
                {"guild_id": guild_id, "user_id": user_id}
            ).sort("timestamp", -1)  # Newest first
            
            return await cursor.to_list(length=None)
        except Exception as e:
            print(f"Error retrieving user logs: {e}")
            return []
    
    async def handle_mod_command(self, interaction: discord.Interaction, user: discord.Member, 
                               action: str, permission: str, reason: str, **kwargs) -> None:
        """Handle standard moderation command flow"""
        # Check permissions
        if not self.check_permissions(interaction, permission):
            await interaction.response.send_message(
                f"You don't have permission to {action.lower()} members!", 
                ephemeral=True
            )
            return
        
        # Check if bot has required permissions
        if not getattr(interaction.guild.me.guild_permissions, permission):
            await interaction.response.send_message(
                f"I don't have permission to {action.lower()} members!", 
                ephemeral=True
            )
            return
        
        # Check if target has higher role than moderator
        if (user.top_role >= interaction.user.top_role and 
            interaction.user.id != interaction.guild.owner_id):
            await interaction.response.send_message(
                f"You cannot {action.lower()} someone with a higher or equal role!", 
                ephemeral=True
            )
            return
        
        # Defer response for longer operations
        await interaction.response.defer()
        
        try:
            # Execute mod action
            await self._execute_mod_action(interaction, user, action, reason, **kwargs)
        except discord.Forbidden:
            await interaction.followup.send(
                f"I don't have permission to {action.lower()} this user!", 
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"An error occurred: {str(e)}", 
                ephemeral=True
            )
    
    async def _execute_mod_action(self, interaction: discord.Interaction, 
                                user: discord.Member, action: str, 
                                reason: str, **kwargs) -> None:
        """Execute the specific moderation action"""
        
        # Log the action to database and get case ID
        case_id = await self.log_mod_action(
            guild_id=interaction.guild.id,
            user_id=user.id,
            moderator_id=interaction.user.id,
            action_type=action.lower(),
            reason=reason,
            **kwargs
        )
        
        # Try to send DM first
        dm_sent = await self.create_and_send_dm(
            user, interaction.guild, action, reason, 
            case_id, interaction.user.display_name, **kwargs
        )
        
        # Execute the actual moderation action
        if action == "Mute":
            timeout_duration = datetime.timedelta(minutes=kwargs.get("duration", 10))
            await user.timeout(timeout_duration, reason=reason)
        elif action == "Unmute":
            await user.timeout(None, reason=reason)
        elif action == "Kick":
            await user.kick(reason=reason)
        elif action == "Ban":
            await user.ban(
                delete_message_days=kwargs.get("delete_days", 0), 
                reason=reason
            )
        # "Warn" doesn't need any additional action
        
        # Create and send embed to channel
        await self.create_and_send_embed(
            interaction, action, user, reason, case_id, **kwargs
        )
        
        # If DM failed, send notification
        if not dm_sent:
            await interaction.followup.send(
                f"Note: Could not DM {user.mention} about this {action.lower()}.", 
                ephemeral=True
            )
    
    # ===== COMMANDS =====
    
    @app_commands.command(name="warn", description="Warn a user")
    @app_commands.describe(
        user="The user to warn",
        reason="Reason for the warning"
    )
    @app_commands.default_permissions(kick_members=True)
    async def warn(self, interaction: discord.Interaction, 
                 user: discord.Member, reason: str = "No reason provided"):
        await self.handle_mod_command(
            interaction, user, "Warn", "kick_members", reason
        )
    
    @app_commands.command(name="mute", description="Timeout a user for a specified duration")
    @app_commands.describe(
        user="The user to mute",
        duration="Duration in minutes (default: 10)",
        reason="Reason for the mute"
    )
    @app_commands.default_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, 
                 user: discord.Member, duration: int = 10, 
                 reason: str = None):
        
        # Additional check for mute specifically
        if user.is_timed_out():
            await interaction.response.send_message(
                f"{user.mention} is already muted/timed out.", 
                ephemeral=True
            )
            return
            
        await self.handle_mod_command(
            interaction, user, "Mute", "moderate_members", reason, duration=duration
        )
    
    @app_commands.command(name="unmute", description="Remove timeout from a user")
    @app_commands.describe(
        user="The user to unmute",
        reason="Reason for removing the timeout"
    )
    @app_commands.default_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, 
                   user: discord.Member, reason: str = None):
        
        # Check if user is actually timed out
        if not user.is_timed_out():
            await interaction.response.send_message(
                f"{user.mention} is not currently muted/timed out.", 
                ephemeral=True
            )
            return
            
        await self.handle_mod_command(
            interaction, user, "Unmute", "moderate_members", reason
        )
    
    @app_commands.command(name="kick", description="Kick a user from the server")
    @app_commands.describe(
        user="The user to kick",
        reason="Reason for the kick"
    )
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, 
                 user: discord.Member, reason: str = None):
        await self.handle_mod_command(
            interaction, user, "Kick", "kick_members", reason
        )
    
    @app_commands.command(name="ban", description="Ban a user from the server")
    @app_commands.describe(
        user="The user to ban",
        delete_days="Number of days of messages to delete (0-7)",
        reason="Reason for the ban"
    )
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, 
                user: discord.Member, delete_days: int = 0, 
                reason: str = None):
        
        # Ensure delete_days is within bounds
        delete_days = max(0, min(delete_days, 7))
        
        await self.handle_mod_command(
            interaction, user, "Ban", "ban_members", reason, delete_days=delete_days
        )
    
    @app_commands.command(name="unban", description="Unban a user from the server")
    @app_commands.describe(
        user_id="The ID of the user to unban",
        reason="Reason for the unban"
    )
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, 
                  user_id: str, reason: str = None):
        # Check permission
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message(
                "You don't have permission to unban members!", 
                ephemeral=True
            )
        
        # Check if bot can unban
        if not interaction.guild.me.guild_permissions.ban_members:
            return await interaction.response.send_message(
                "I don't have permission to unban members!", 
                ephemeral=True
            )
        
        # Defer response
        await interaction.response.defer()
        
        try:
            # Convert user_id to int
            try:
                user_id_int = int(user_id)
            except ValueError:
                return await interaction.followup.send(
                    "Invalid user ID. Please provide a valid numeric ID.", 
                    ephemeral=True
                )
            
            # Find ban entry
            try:
                ban_entry = await interaction.guild.fetch_ban(discord.Object(id=user_id_int))
                banned_user = ban_entry.user
            except discord.NotFound:
                return await interaction.followup.send(
                    f"User with ID {user_id} is not banned.", 
                    ephemeral=True
                )
            
            # Unban user
            await interaction.guild.unban(banned_user, reason=reason)
            
            # Create embed
            embed = discord.Embed(
                title="User Unbanned",
                description=f"**{banned_user}** has been unbanned.",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            embed.add_field(name="Unbanned by", value=interaction.user.mention, inline=False)
            if banned_user.avatar:
                embed.set_thumbnail(url=banned_user.avatar.url)
            embed.set_footer(text=f"User ID: {banned_user.id}")
            
            await interaction.followup.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to unban this user!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="modlogs", description="Check moderation logs for a user")
    @app_commands.describe(
        user="The user to check logs for"
    )
    @app_commands.default_permissions(kick_members=True)
    async def modlogs(self, interaction: discord.Interaction, user: discord.Member):
        # Check permission
        if not self.check_permissions(interaction):
            return await interaction.response.send_message(
                "You don't have permission to view moderation logs!", 
                ephemeral=True
            )
        
        # Defer response
        await interaction.response.defer()
        
        try:
            # Get user logs
            logs_list = await self.get_user_logs(interaction.guild.id, user.id)
            
            if not logs_list:
                return await interaction.followup.send(
                    f"{user.mention} has no moderation logs.", 
                    ephemeral=False
                )
            
            # Set up pagination
            logs_per_page = 5
            log_count = len(logs_list)
            
            # Create pagination view
            view = ModLogPaginationView(
                logs_list, 
                user.display_name, 
                user.id, 
                interaction.guild, 
                logs_per_page=logs_per_page
            )
            
            # Display first page
            embed = view.create_log_embed()
            embed.set_thumbnail(url=user.display_avatar.url)
            
            # Always use the view - this is the fix
            await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            print(f"Error in modlogs command: {e}")
            await interaction.followup.send(
                f"An error occurred while fetching moderation logs: {str(e)}", 
                ephemeral=True
            )
    
    @app_commands.command(name="clearmodlogs", description="Clear all moderation logs for a user")
    @app_commands.describe(
        user="The user to clear moderation logs for"
    )
    @app_commands.default_permissions(ban_members=True)
    async def clearmodlogs(self, interaction: discord.Interaction, user: discord.Member):
        # Check permission
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message(
                "You don't have permission to clear moderation logs!", 
                ephemeral=True
            )
        
        # Defer response
        await interaction.response.defer()
        
        guild_id = interaction.guild.id
        user_id = user.id
        
        # Get log count
        log_count = await self.modlogs_collection.count_documents({
            "guild_id": guild_id, 
            "user_id": user_id
        })
        
        if log_count == 0:
            return await interaction.followup.send(
                f"{user.mention} has no moderation logs to clear.",
                ephemeral=False
            )
        
        # Delete logs
        result = await self.modlogs_collection.delete_many({
            "guild_id": guild_id, 
            "user_id": user_id
        })
        
        # Create embed
        embed = discord.Embed(
            title="Moderation Logs Cleared",
            description=f"Cleared {log_count} moderation logs for {user.mention}.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="Cleared by", value=interaction.user.mention, inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="removecase", description="Remove a specific moderation case by ID")
    @app_commands.describe(
        case_id="The case ID to remove"
    )
    @app_commands.default_permissions(ban_members=True)
    async def removecase(self, interaction: discord.Interaction, case_id: int):
        # Check permission
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message(
                "You don't have permission to remove moderation cases!", 
                ephemeral=True
            )
        
        # Defer response
        await interaction.response.defer()
        
        guild_id = interaction.guild.id
        
        # Find case
        case = await self.modlogs_collection.find_one({
            "guild_id": guild_id,
            "case_id": case_id
        })
        
        if not case:
            return await interaction.followup.send(
                f"Case #{case_id} not found.", 
                ephemeral=True
            )
        
        # Get user info
        user_id = case.get("user_id")
        action_type = case.get("action_type", "unknown")
        
        # Delete case
        await self.modlogs_collection.delete_one({
            "guild_id": guild_id,
            "case_id": case_id
        })
        
        # Get user mention if possible
        user = interaction.guild.get_member(user_id) if user_id else None
        user_mention = user.mention if user else f"User ID: {user_id}"
        
        # Create embed
        embed = discord.Embed(
            title="Case Removed",
            description=f"Case #{case_id} has been removed.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="User", value=user_mention, inline=False)
        embed.add_field(name="Action Type", value=action_type.title(), inline=False)
        embed.add_field(name="Removed by", value=interaction.user.mention, inline=False)
        embed.set_footer(text=f"Guild ID: {guild_id}")
        
        await interaction.followup.send(embed=embed)

# Setup function for loading the cog
async def setup(bot):
    await bot.add_cog(Moderation(bot))
