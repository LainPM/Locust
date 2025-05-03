import discord
from discord import app_commands
from discord.ext import commands
from enum import Enum
import re
from typing import Optional, List, Dict, Any, Union
import math
import datetime
import asyncio
import json
from datetime import timedelta

class MatchType(Enum):
    CONTAINS = "contains"
    EXACT = "exact"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    REGEX = "regex"

class PaginationView(discord.ui.View):
    def __init__(self, items: List[Dict[str, Any]], match_type: str, 
                 page: int, items_per_page: int, is_blacklist: bool, 
                 interaction: discord.Interaction):
        super().__init__(timeout=180)  # 3 minute timeout
        self.items = items
        self.match_type = match_type
        self.current_page = page
        self.items_per_page = items_per_page
        self.is_blacklist = is_blacklist
        self.interaction = interaction
        self.total_pages = math.ceil(len(self.filtered_items) / self.items_per_page)
        
        # Disable buttons if needed
        self.update_buttons()

    @property
    def filtered_items(self) -> List[Dict[str, Any]]:
        """Get items filtered by match_type"""
        if self.match_type == "all":
            return self.items
        return [item for item in self.items if item.get("match_type") == self.match_type]
    
    def get_embed(self) -> discord.Embed:
        """Generate the embed for the current page"""
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        
        filtered = self.filtered_items
        page_items = filtered[start_idx:end_idx]
        
        title = "Blacklisted Items" if self.is_blacklist else "Whitelisted Items"
        color = discord.Color.red() if self.is_blacklist else discord.Color.green()
        
        embed = discord.Embed(
            title=title,
            description=f"Filter: {self.match_type} | Page {self.current_page}/{self.total_pages}",
            color=color
        )
        
        if not page_items:
            embed.add_field(name="No items found", value="Try a different page or filter", inline=False)
        else:
            for doc in page_items:
                embed.add_field(
                    name=doc["item"], 
                    value=f"Type: {doc['match_type']}" + (f"\nReason: {doc.get('reason')}" if doc.get('reason') else ""),
                    inline=False
                )
                
        embed.set_footer(text=f"Showing {len(page_items)} items | Total: {len(filtered)} items")
        return embed
    
    def update_buttons(self):
        """Update button states based on current page"""
        # Disable prev button if on first page
        self.prev_button.disabled = (self.current_page <= 1)
        # Disable next button if on last page
        self.next_button.disabled = (self.current_page >= self.total_pages)

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.grey)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(1, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = min(self.total_pages, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def on_timeout(self):
        """Remove buttons when the view times out"""
        # Disable all buttons
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        # Try to update the message - might fail if message is too old
        try:
            await self.message.edit(view=self)
        except:
            pass

class PunishmentType(Enum):
    WARNING = "warning"
    MUTE = "mute"
    KICK = "kick"
    BAN = "ban"

class TimeWindowUnit(Enum):
    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"

class PunishmentSettingsView(discord.ui.View):
    """Interactive view for punishment settings"""
    def __init__(self, cog, settings: Dict[str, Any], interaction: discord.Interaction):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.settings = settings
        self.guild_id = interaction.guild.id
        self.original_interaction = interaction
        
    def get_embed(self) -> discord.Embed:
        """Generate the settings embed"""
        settings = self.settings
        embed = discord.Embed(
            title="Blacklist Punishment Settings",
            description=f"Current configuration for {self.original_interaction.guild.name}",
            color=discord.Color.blue()
        )
        
        # Status field
        status = "✅ Enabled" if settings.get("enabled", True) else "❌ Disabled"
        embed.add_field(name="Status", value=status, inline=False)
        
        # Basic settings
        embed.add_field(name="Violation Threshold", 
                        value=f"{settings['violation_threshold']} violations", 
                        inline=True)
        
        # Time window
        window_value = settings.get("time_window_value", 0)
        window_unit = settings.get("time_window_unit", TimeWindowUnit.MINUTES.value)
        if window_value > 0:
            embed.add_field(name="Time Window", 
                            value=f"{window_value} {window_unit}", 
                            inline=True)
        else:
            embed.add_field(name="Time Window", 
                            value="No time limit", 
                            inline=True)
        
        # Punishment details
        punishment_type = settings["punishment_type"]
        if punishment_type == PunishmentType.WARNING.value:
            embed.add_field(name="Punishment", value="Warning only", inline=True)
        elif punishment_type == PunishmentType.MUTE.value:
            duration = settings.get("duration_seconds", 0)
            if duration > 0:
                minutes = duration // 60
                seconds = duration % 60
                time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
                embed.add_field(name="Punishment", value=f"Mute for {time_str}", inline=True)
            else:
                embed.add_field(name="Punishment", value="Permanent Mute", inline=True)
        elif punishment_type == PunishmentType.KICK.value:
            embed.add_field(name="Punishment", value="Kick from server", inline=True)
        elif punishment_type == PunishmentType.BAN.value:
            embed.add_field(name="Punishment", value="Ban from server", inline=True)
            
        # Violation reset explanation
        if settings.get("auto_reset_violations", True):
            embed.add_field(name="Violation Reset", 
                            value="Violations are reset after punishment is applied",
                            inline=False)
        else:
            embed.add_field(name="Violation Reset", 
                            value="Violations are NOT reset after punishment (accumulative)",
                            inline=False)
            
        # Escalation info
        if settings.get("enable_escalation", False):
            escalation_steps = settings.get("escalation_steps", [])
            if escalation_steps:
                escalation_info = "\n".join([
                    f"Level {i+1}: {step['punishment_type']} "
                    f"({step.get('duration_seconds', 0)}s)"
                    for i, step in enumerate(escalation_steps)
                ])
                embed.add_field(name="Escalation Enabled", value=escalation_info, inline=False)
            else:
                embed.add_field(name="Escalation Enabled", value="No escalation steps defined", inline=False)
        
        # Command examples
        embed.add_field(
            name="Management Commands",
            value=(
                "/punishment_config - Configure punishment settings\n"
                "/punishment_status - View current settings\n"
                "/reset_violations - Reset violations for a user\n"
                "/view_violations - View violations for users"
            ),
            inline=False
        )
        
        return embed
        
    @discord.ui.button(label="Toggle Status", style=discord.ButtonStyle.primary)
    async def toggle_status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.settings["enabled"] = not self.settings.get("enabled", True)
        await self.cog.punishment_collection.update_one(
            {"guild_id": self.guild_id},
            {"$set": {"enabled": self.settings["enabled"]}}
        )
        self.cog.punishment_cache[self.guild_id]["enabled"] = self.settings["enabled"]
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
        
    @discord.ui.button(label="Edit Settings", style=discord.ButtonStyle.secondary)
    async def edit_settings_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Create a modal for editing settings
        await interaction.response.send_modal(PunishmentSettingsModal(self.cog, self.settings, self.guild_id))
    
    async def on_timeout(self):
        """Disable buttons when the view times out"""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        try:
            await self.message.edit(view=self)
        except:
            pass

class PunishmentSettingsModal(discord.ui.Modal, title="Edit Punishment Settings"):
    """Modal for editing punishment settings"""
    
    # Basic Settings
    threshold = discord.ui.TextInput(
        label="Violation Threshold", 
        placeholder="Number of violations before punishment",
        default="3",
        required=True
    )
    
    time_window_value = discord.ui.TextInput(
        label="Time Window Value (0 = no limit)",
        placeholder="e.g., 10 (use with unit below)",
        default="0",
        required=True
    )
    
    time_window_unit = discord.ui.TextInput(
        label="Time Window Unit",
        placeholder="seconds, minutes, hours, days",
        default="minutes",
        required=True
    )
    
    punishment = discord.ui.TextInput(
        label="Punishment Type",
        placeholder="warning, mute, kick, ban",
        default="mute",
        required=True
    )
    
    duration = discord.ui.TextInput(
        label="Duration (seconds, 0 = permanent)",
        placeholder="For mute only, e.g., 300 for 5 minutes",
        default="60",
        required=True
    )
    
    def __init__(self, cog, settings, guild_id):
        super().__init__()
        self.cog = cog
        self.settings = settings
        self.guild_id = guild_id
        
        # Set default values based on current settings
        self.threshold.default = str(settings.get("violation_threshold", 3))
        self.time_window_value.default = str(settings.get("time_window_value", 0))
        self.time_window_unit.default = settings.get("time_window_unit", TimeWindowUnit.MINUTES.value)
        self.punishment.default = settings.get("punishment_type", PunishmentType.MUTE.value)
        self.duration.default = str(settings.get("duration_seconds", 60))
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Validate and convert inputs
            threshold = max(1, int(self.threshold.value))
            time_window_value = max(0, int(self.time_window_value.value))
            
            # Validate time window unit
            time_window_unit = self.time_window_unit.value.lower().strip()
            valid_units = [unit.value for unit in TimeWindowUnit]
            if time_window_unit not in valid_units:
                time_window_unit = TimeWindowUnit.MINUTES.value
            
            # Validate punishment type
            punishment_type = self.punishment.value.lower().strip()
            valid_types = [t.value for t in PunishmentType]
            if punishment_type not in valid_types:
                punishment_type = PunishmentType.MUTE.value
            
            # Duration only applies to mute
            duration_seconds = 0
            if punishment_type == PunishmentType.MUTE.value:
                duration_seconds = max(0, int(self.duration.value))
            
            # Update settings
            update_data = {
                "violation_threshold": threshold,
                "time_window_value": time_window_value,
                "time_window_unit": time_window_unit,
                "punishment_type": punishment_type,
                "duration_seconds": duration_seconds,
                "updated_at": discord.utils.utcnow().isoformat(),
                "updated_by": interaction.user.id
            }
            
            # Update database
            await self.cog.punishment_collection.update_one(
                {"guild_id": self.guild_id},
                {"$set": update_data}
            )
            
            # Update cache
            self.cog.punishment_cache[self.guild_id].update(update_data)
            
            # Update the view with new settings
            settings_view = PunishmentSettingsView(
                self.cog,
                self.cog.punishment_cache[self.guild_id],
                interaction
            )
            
            await interaction.response.send_message(
                content="✅ Punishment settings updated successfully!",
                embed=settings_view.get_embed(),
                view=settings_view,
                ephemeral=True
            )
            
            # Store message for timeout handling
            settings_view.message = await interaction.original_response()
            
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid input: Please make sure all numeric values are valid numbers.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

class ViolationsView(discord.ui.View):
    """Interactive view for viewing and managing user violations"""
    def __init__(self, cog, guild_id: int, violations: Dict[int, Dict[str, Any]], 
                 page: int = 1, items_per_page: int = 10):
        super().__init__(timeout=180)  # 3 minute timeout
        self.cog = cog
        self.guild_id = guild_id
        self.violations = violations  # {user_id: {"count": X, "timestamps": [...]}}
        self.current_page = page
        self.items_per_page = items_per_page
        self.total_pages = max(1, math.ceil(len(violations) / items_per_page))
        
        # Disable buttons if needed
        self.update_buttons()
    
    def get_embed(self, guild: discord.Guild) -> discord.Embed:
        """Generate the violations embed"""
        embed = discord.Embed(
            title="User Violations",
            description=f"Blacklist violations in {guild.name} | Page {self.current_page}/{self.total_pages}",
            color=discord.Color.orange()
        )
        
        # Get sorted violations (most to least)
        sorted_violations = sorted(
            self.violations.items(), 
            key=lambda x: x[1].get("count", 0), 
            reverse=True
        )
        
        # Get items for current page
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(sorted_violations))
        page_items = sorted_violations[start_idx:end_idx]
        
        if not page_items:
            embed.add_field(name="No violations found", value="All users are behaving well!", inline=False)
        else:
            for user_id, data in page_items:
                # Get member
                member = guild.get_member(user_id)
                name = member.display_name if member else f"Unknown User ({user_id})"
                
                # Get violation count
                count = data.get("count", 0)
                
                # Get last violation time
                last_violation = None
                timestamps = data.get("timestamps", [])
                if timestamps:
                    try:
                        last_violation = datetime.datetime.fromisoformat(timestamps[-1])
                        time_ago = (discord.utils.utcnow() - last_violation).total_seconds()
                        
                        if time_ago < 60:
                            time_str = f"{int(time_ago)}s ago"
                        elif time_ago < 3600:
                            time_str = f"{int(time_ago // 60)}m ago"
                        elif time_ago < 86400:
                            time_str = f"{int(time_ago // 3600)}h ago"
                        else:
                            time_str = f"{int(time_ago // 86400)}d ago"
                    except:
                        time_str = "Unknown time"
                else:
                    time_str = "Never"
                
                # Add to embed
                embed.add_field(
                    name=name,
                    value=f"Violations: **{count}**\nLast violation: {time_str}",
                    inline=False
                )
        
        # Add explanation footer
        embed.set_footer(text=f"Use /reset_violations to reset a user's violation count")
        return embed
    
    def update_buttons(self):
        """Update button states based on current page"""
        # Disable prev button if on first page
        self.prev_button.disabled = (self.current_page <= 1)
        # Disable next button if on last page
        self.next_button.disabled = (self.current_page >= self.total_pages)
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.grey)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(1, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.get_embed(interaction.guild), 
            view=self
        )
    
    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = min(self.total_pages, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.get_embed(interaction.guild), 
            view=self
        )
        
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.green)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Reload violations from database
        violations = {}
        async for doc in self.cog.violations_collection.find({"guild_id": self.guild_id}):
            user_id = doc["user_id"]
            violations[user_id] = {
                "count": doc["violation_count"],
                "timestamps": doc.get("timestamps", [])
            }
        
        self.violations = violations
        self.total_pages = max(1, math.ceil(len(violations) / self.items_per_page))
        self.current_page = min(self.current_page, self.total_pages)
        self.update_buttons()
        
        await interaction.response.edit_message(
            embed=self.get_embed(interaction.guild),
            view=self
        )
    
    async def on_timeout(self):
        """Disable buttons when the view times out"""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        try:
            await self.message.edit(view=self)
        except:
            pass

class FilterCog(commands.Cog):
    """Cog for managing content filtering with blacklist and whitelist functionality"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.blacklist_cache = {}
        self.whitelist_cache = {}
        self.punishment_cache = {}
        self.user_violations = {}  # {guild_id: {user_id: count}}
        self.violation_timestamps = {}  # {guild_id: {user_id: [timestamp1, timestamp2, ...]}}

    async def cog_load(self):
        if hasattr(self.bot, 'db'):
            names = await self.bot.db.list_collection_names()
            if "blacklist" not in names:
                await self.bot.db.create_collection("blacklist")
            if "whitelist" not in names:
                await self.bot.db.create_collection("whitelist")
            if "blacklist_punishment" not in names:
                await self.bot.db.create_collection("blacklist_punishment")
            if "user_violations" not in names:
                await self.bot.db.create_collection("user_violations")
                
            self.blacklist_collection = self.bot.db["blacklist"]
            self.whitelist_collection = self.bot.db["whitelist"]
            self.punishment_collection = self.bot.db["blacklist_punishment"]
            self.violations_collection = self.bot.db["user_violations"]
        else:
            print("Warning: Bot database not initialized")
            return
            
        for guild in self.bot.guilds:
            await self._load_cache(guild.id)
            await self._load_punishment_cache(guild.id)
            await self._load_violations_cache(guild.id)
            
        await self.bot.tree.sync()
        
    async def _load_punishment_cache(self, guild_id: int):
        """Load punishment settings for a guild"""
        self.punishment_cache[guild_id] = await self.punishment_collection.find_one({"guild_id": guild_id})
        if not self.punishment_cache[guild_id]:
            # Set default punishment settings
            default_punishment = {
                "guild_id": guild_id,
                "violation_threshold": 3,
                "punishment_type": PunishmentType.MUTE.value,
                "duration_seconds": 60,
                "enabled": True,  # Enable by default
                "time_window_value": 5,  # 5 minutes by default
                "time_window_unit": TimeWindowUnit.MINUTES.value,
                "auto_reset_violations": True,
                "enable_escalation": False,
                "escalation_steps": [],
                "created_at": discord.utils.utcnow().isoformat()
            }
            await self.punishment_collection.insert_one(default_punishment)
            self.punishment_cache[guild_id] = default_punishment
            
    async def _load_violations_cache(self, guild_id: int):
        """Load user violations for a guild"""
        self.user_violations[guild_id] = {}
        self.violation_timestamps[guild_id] = {}
        
        async for doc in self.violations_collection.find({"guild_id": guild_id}):
            user_id = doc["user_id"]
            self.user_violations[guild_id][user_id] = doc["violation_count"]
            self.violation_timestamps[guild_id][user_id] = doc.get("timestamps", [])

    async def _load_cache(self, guild_id: int):
        self.blacklist_cache[guild_id] = {}
        self.whitelist_cache[guild_id] = {}
        async for doc in self.blacklist_collection.find({"guild_id": guild_id}):
            self.blacklist_cache[guild_id][doc["item"]] = doc["match_type"]
        async for doc in self.whitelist_collection.find({"guild_id": guild_id}):
            self.whitelist_cache[guild_id][doc["item"]] = doc["match_type"]

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self._load_cache(guild.id)
        await self._load_punishment_cache(guild.id)
        await self._load_violations_cache(guild.id)
        await self.bot.tree.sync(guild=guild)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
            
        gid = message.guild.id
        user_id = message.author.id
        
        # Load caches if needed
        if gid not in self.blacklist_cache:
            await self._load_cache(gid)
        if gid not in self.punishment_cache:
            await self._load_punishment_cache(gid)
        if gid not in self.user_violations:
            await self._load_violations_cache(gid)
            
        content = message.content.lower()
        
        # Check whitelist first
        for item, mt in self.whitelist_cache.get(gid, {}).items():
            if self._matches(content, item, mt):
                return
                
        # Check blacklist
        for item, mt in self.blacklist_cache.get(gid, {}).items():
            if self._matches(content, item, mt):
                try:
                    # Delete the message
                    await message.delete()
                    
                    # Increment violation count with timestamp
                    await self._increment_violation(gid, user_id)
                    
                    # Check if punishment threshold is reached
                    await self._check_and_punish(message.guild, message.author, message.channel)
                    
                    # Notify user
                    await message.channel.send(
                        f"{message.author.mention}, your message was removed because it contained blacklisted content.",
                        delete_after=5
                    )
                except discord.Forbidden:
                    pass
                return
                
    async def _increment_violation(self, guild_id: int, user_id: int):
        """Increment the violation count for a user"""
        # Initialize if not exists
        if guild_id not in self.user_violations:
            self.user_violations[guild_id] = {}
        if guild_id not in self.violation_timestamps:
            self.violation_timestamps[guild_id] = {}
        if user_id not in self.violation_timestamps[guild_id]:
            self.violation_timestamps[guild_id][user_id] = []
            
        # Add current timestamp
        now = discord.utils.utcnow().isoformat()
        self.violation_timestamps[guild_id][user_id].append(now)
        
        # Get time-filtered count based on punishment settings
        count_in_window = self._get_violations_in_window(guild_id, user_id)
        
        # Update cache
        self.user_violations[guild_id][user_id] = count_in_window
        
        # Update database
        await self.violations_collection.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {
                "violation_count": count_in_window,
                "last_violation": now,
                "timestamps": self.violation_timestamps[guild_id][user_id]
            }},
            upsert=True
        )
        
    def _get_violations_in_window(self, guild_id: int, user_id: int) -> int:
        """Get the number of violations within the configured time window"""
        settings = self.punishment_cache.get(guild_id, {})
        time_window_value = settings.get("time_window_value", 0)
        
        # If no time window, return all violations
        if time_window_value <= 0:
            return len(self.violation_timestamps[guild_id][user_id])
            
        # Calculate the cutoff time
        time_window_unit = settings.get("time_window_unit", TimeWindowUnit.MINUTES.value)
        now = datetime.datetime.now(datetime.timezone.utc)
        
        if time_window_unit == TimeWindowUnit.SECONDS.value:
            cutoff = now - timedelta(seconds=time_window_value)
        elif time_window_unit == TimeWindowUnit.MINUTES.value:
            cutoff = now - timedelta(minutes=time_window_value)
        elif time_window_unit == TimeWindowUnit.HOURS.value:
            cutoff = now - timedelta(hours=time_window_value)
        elif time_window_unit == TimeWindowUnit.DAYS.value:
            cutoff = now - timedelta(days=time_window_value)
        else:
            # Default to minutes if unit is invalid
            cutoff = now - timedelta(minutes=time_window_value)
            
        # Filter timestamps to include only those within the window
        cutoff_iso = cutoff.isoformat()
        recent_timestamps = [
            ts for ts in self.violation_timestamps[guild_id][user_id]
            if ts >= cutoff_iso
        ]
        
        # Update timestamps list to remove old ones
        self.violation_timestamps[guild_id][user_id] = recent_timestamps
        
        return len(recent_timestamps)
        
    async def _check_and_punish(self, guild: discord.Guild, member: discord.Member, channel: discord.TextChannel):
        """Check if user has reached the punishment threshold and apply punishment if needed"""
        guild_id = guild.id
        user_id = member.id
        
        # Get current count and punishment settings
        current_count = self.user_violations[guild_id].get(user_id, 0)
        punishment_settings = self.punishment_cache[guild_id]
        
        # Check if punishments are disabled
        if not punishment_settings.get("enabled", True):
            return
            
        # Check if threshold reached
        if current_count >= punishment_settings["violation_threshold"]:
            # Determine punishment
            if punishment_settings.get("enable_escalation", False):
                punishment_type, duration = self._get_escalated_punishment(guild_id, user_id)
            else:
                punishment_type = punishment_settings["punishment_type"]
                duration = punishment_settings.get("duration_seconds", 60)
            
            # Check if auto-reset is enabled
            if punishment_settings.get("auto_reset_violations", True):
                # Reset violation count
                self.user_violations[guild_id][user_id] = 0
                self.violation_timestamps[guild_id][user_id] = []
                await self.violations_collection.update_one(
                    {"guild_id": guild_id, "user_id": user_id},
                    {"$set": {
                        "violation_count": 0, 
                        "timestamps": [],
                        "last_reset": discord.utils.utcnow().isoformat(),
                        "punishment_history": self.violation_timestamps[guild_id][user_id]
                    }},
                    upsert=True
                )
            
            # Check bot permissions
            bot_member = guild.get_member(self.bot.user.id)
            if not bot_member.guild_permissions.manage_roles and punishment_type == PunishmentType.MUTE.value:
                await channel.send("Cannot mute users: Bot lacks 'Manage Roles' permission.")
                return
            if not bot_member.guild_permissions.kick_members and punishment_type == PunishmentType.KICK.value:
                await channel.send("Cannot kick users: Bot lacks 'Kick Members' permission.")
                return
            if not bot_member.guild_permissions.ban_members and punishment_type == PunishmentType.BAN.value:
                await channel.send("Cannot ban users: Bot lacks 'Ban Members' permission.")
                return
            
            try:
                if punishment_type == PunishmentType.WARNING.value:
                    await self._warn_user(guild, member, channel)
                elif punishment_type == PunishmentType.MUTE.value:
                    await self._mute_user(guild, member, duration, channel)
                elif punishment_type == PunishmentType.KICK.value:
                    await self._kick_user(guild, member, channel)
                elif punishment_type == PunishmentType.BAN.value:
                    await self._ban_user(guild, member, channel)
            except discord.Forbidden:
                await channel.send(f"Failed to apply punishment: Insufficient permissions.")
            except Exception as e:
                await channel.send(f"Error applying punishment: {str(e)}")
    
    def _get_escalated_punishment(self, guild_id: int, user_id: int) -> tuple:
        """Get escalated punishment based on user's punishment history"""
        settings = self.punishment_cache.get(guild_id, {})
        escalation_steps = settings.get("escalation_steps", [])
        
        # Get punishment history count
        history_count = 0
        history = self.violations_collection.find_one(
            {"guild_id": guild_id, "user_id": user_id}
        )
        
        if history:
            history_count = history.get("escalation_level", 0)
        
        # Determine which escalation step to use
        if not escalation_steps or history_count >= len(escalation_steps):
            # Default to last step or base punishment
            if escalation_steps:
                step = escalation_steps[-1]
                punishment_type = step.get("punishment_type", PunishmentType.MUTE.value)
                duration = step.get("duration_seconds", 60)
            else:
                punishment_type = settings.get("punishment_type", PunishmentType.MUTE.value)
                duration = settings.get("duration_seconds", 60)
        else:
            step = escalation_steps[history_count]
            punishment_type = step.get("punishment_type", PunishmentType.MUTE.value)
            duration = step.get("duration_seconds", 60)
        
        # Update escalation level for next time
        self.violations_collection.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {"escalation_level": history_count + 1}}
        )
        
        return punishment_type, duration
    
    async def _warn_user(self, guild: discord.Guild, member: discord.Member, channel: discord.TextChannel):
        """Send a warning to a user"""
        dm_sent = False
        try:
            await member.send(f"⚠️ **Warning**: You have violated the content policy in {guild.name} multiple times. "
                             f"Further violations may result in more severe actions.")
            dm_sent = True
        except (discord.Forbidden, discord.HTTPException):
            # Cannot DM the user
            pass
            
        msg = f"⚠️ {member.mention} has been warned for multiple blacklist violations."
        if not dm_sent:
            msg += " (Unable to DM user)"
        await channel.send(msg)
                
    async def _mute_user(self, guild: discord.Guild, member: discord.Member, duration: int, channel: discord.TextChannel):
        """Mute a user for the specified duration"""
        # Find or create muted role
        muted_role = discord.utils.get(guild.roles, name="Muted")
        if not muted_role:
            # Create role if it doesn't exist
            try:
                muted_role = await guild.create_role(name="Muted", reason="Created for muting users")
                # Set permissions for all text channels
                for text_channel in guild.text_channels:
                    await text_channel.set_permissions(muted_role, send_messages=False, add_reactions=False)
            except discord.Forbidden:
                await channel.send("Failed to create Muted role: Insufficient permissions.")
                return
                
        # Apply muted role
        await member.add_roles(muted_role, reason="Automatic punishment for posting blacklisted content")
        
        # Determine duration string for display
        if duration <= 0:
            duration_str = "permanently"
            await channel.send(f"🔇 {member.mention} has been muted permanently due to multiple blacklist violations.")
        else:
            # Format duration for display
            if duration < 60:
                duration_str = f"{duration} seconds"
            elif duration < 3600:
                minutes = duration // 60
                seconds = duration % 60
                duration_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
                if seconds > 0:
                    duration_str += f" and {seconds} second{'s' if seconds != 1 else ''}"
            else:
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                duration_str = f"{hours} hour{'s' if hours != 1 else ''}"
                if minutes > 0:
                    duration_str += f" and {minutes} minute{'s' if minutes != 1 else ''}"
            
            await channel.send(f"🔇 {member.mention} has been muted for {duration_str} due to multiple blacklist violations.")
            
            # Schedule unmute
            await asyncio.sleep(duration)
            try:
                await member.remove_roles(muted_role, reason="Temporary mute expired")
                await channel.send(f"🔊 {member.mention} has been unmuted.", delete_after=10)
            except (discord.Forbidden, discord.HTTPException):
                # User may have left or role may have been deleted
                pass
            
    async def _kick_user(self, guild: discord.Guild, member: discord.Member, channel: discord.TextChannel):
        """Kick a user from the server"""
        dm_sent = False
        try:
            await member.send(f"You have been kicked from {guild.name} due to multiple blacklist violations.")
            dm_sent = True
        except (discord.Forbidden, discord.HTTPException):
            # Cannot DM the user
            pass
            
        await member.kick(reason="Automatic punishment for posting blacklisted content")
        
        msg = f"👢 {member.mention} has been kicked due to multiple blacklist violations."
        if not dm_sent:
            msg += " (Unable to DM user)"
        await channel.send(msg)
        
    async def _ban_user(self, guild: discord.Guild, member: discord.Member, channel: discord.TextChannel):
        """Ban a user from the server"""
        dm_sent = False
        try:
            await member.send(f"You have been banned from {guild.name} due to multiple blacklist violations.")
            dm_sent = True
        except (discord.Forbidden, discord.HTTPException):
            # Cannot DM the user
            pass
            
        await member.ban(reason="Automatic punishment for posting blacklisted content", delete_message_days=1)
        
        msg = f"🔨 {member.mention} has been banned due to multiple blacklist violations."
        if not dm_sent:
            msg += " (Unable to DM user)"
        await channel.send(msg)

    def _matches(self, content: str, item: str, match_type: str) -> bool:
        try:
            if match_type == MatchType.CONTAINS.value:
                return item.lower() in content
            if match_type == MatchType.EXACT.value:
                return content == item.lower()
            if match_type == MatchType.STARTS_WITH.value:
                return content.startswith(item.lower())
            if match_type == MatchType.ENDS_WITH.value:
                return content.endswith(item.lower())
            if match_type == MatchType.REGEX.value:
                return bool(re.search(item, content, re.IGNORECASE))
        except:
            return False
        return False

    # Single-item slash commands

    @app_commands.command(name="blacklist", description="Add or update an item in the blacklist")
    @app_commands.describe(item="The word/phrase/link to blacklist", match_type="Match type", reason="Reason for blacklisting")
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value=MatchType.CONTAINS.value),
        app_commands.Choice(name="Exact", value=MatchType.EXACT.value),
        app_commands.Choice(name="Starts With", value=MatchType.STARTS_WITH.value),
        app_commands.Choice(name="Ends With", value=MatchType.ENDS_WITH.value),
        app_commands.Choice(name="Regex", value=MatchType.REGEX.value)
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def blacklist(self, interaction: discord.Interaction, item: str, match_type: str = MatchType.CONTAINS.value, reason: Optional[str] = None):
        gid = interaction.guild.id
        await self.whitelist_collection.delete_one({"guild_id": gid, "item": item})
        self.whitelist_cache.get(gid, {}).pop(item, None)
        await self.blacklist_collection.update_one({"guild_id": gid, "item": item}, {"$set": {"match_type": match_type, "reason": reason, "added_by": interaction.user.id, "added_at": discord.utils.utcnow().isoformat()}}, upsert=True)
        self.blacklist_cache.setdefault(gid, {})[item] = match_type
        await interaction.response.send_message(f"🚫 Blacklisted `{item}` ({match_type})", ephemeral=True)

    @app_commands.command(name="whitelist", description="Add or update an item in the whitelist")
    @app_commands.describe(item="The word/phrase/link to whitelist", match_type="Match type", reason="Reason for whitelisting")
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value=MatchType.CONTAINS.value),
        app_commands.Choice(name="Exact", value=MatchType.EXACT.value),
        app_commands.Choice(name="Starts With", value=MatchType.STARTS_WITH.value),
        app_commands.Choice(name="Ends With", value=MatchType.ENDS_WITH.value),
        app_commands.Choice(name="Regex", value=MatchType.REGEX.value)
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def whitelist(self, interaction: discord.Interaction, item: str, match_type: str = MatchType.CONTAINS.value, reason: Optional[str] = None):
        gid = interaction.guild.id
        await self.blacklist_collection.delete_one({"guild_id": gid, "item": item})
        self.blacklist_cache.get(gid, {}).pop(item, None)
        await self.whitelist_collection.update_one({"guild_id": gid, "item": item}, {"$set": {"match_type": match_type, "reason": reason, "added_by": interaction.user.id, "added_at": discord.utils.utcnow().isoformat()}}, upsert=True)
        self.whitelist_cache.setdefault(gid, {})[item] = match_type
        await interaction.response.send_message(f"✅ Whitelisted `{item}` ({match_type})", ephemeral=True)

    # Bulk slash commands

    @app_commands.command(name="bulk_blacklist", description="Add or update multiple items to the blacklist")
    @app_commands.describe(items="Comma-separated list of items to blacklist", match_type="Match type for all items", reason="Optional reason applied to all items")
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value=MatchType.CONTAINS.value),
        app_commands.Choice(name="Exact", value=MatchType.EXACT.value),
        app_commands.Choice(name="Starts With", value=MatchType.STARTS_WITH.value),
        app_commands.Choice(name="Ends With", value=MatchType.ENDS_WITH.value),
        app_commands.Choice(name="Regex", value=MatchType.REGEX.value)
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def bulk_blacklist(self, interaction: discord.Interaction, items: str, match_type: str = MatchType.CONTAINS.value, reason: Optional[str] = None):
        gid = interaction.guild.id
        entries = [entry.strip() for entry in items.split(',') if entry.strip()]
        processed: List[str] = []
        for item in entries:
            # Remove from whitelist
            await self.whitelist_collection.delete_one({"guild_id": gid, "item": item})
            self.whitelist_cache.get(gid, {}).pop(item, None)
            # Upsert blacklist
            await self.blacklist_collection.update_one({"guild_id": gid, "item": item}, {"$set": {"match_type": match_type, "reason": reason, "added_by": interaction.user.id, "added_at": discord.utils.utcnow().isoformat()}}, upsert=True)
            self.blacklist_cache.setdefault(gid, {})[item] = match_type
            processed.append(item)
        await interaction.response.send_message(f"🚫 Bulk blacklisted: {', '.join(processed)} ({match_type})", ephemeral=True)

    @app_commands.command(name="bulk_whitelist", description="Add or update multiple items to the whitelist")
    @app_commands.describe(items="Comma-separated list of items to whitelist", match_type="Match type for all items", reason="Optional reason applied to all items")
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value=MatchType.CONTAINS.value),
        app_commands.Choice(name="Exact", value=MatchType.EXACT.value),
        app_commands.Choice(name="Starts With", value=MatchType.STARTS_WITH.value),
        app_commands.Choice(name="Ends With", value=MatchType.ENDS_WITH.value),
        app_commands.Choice(name="Regex", value=MatchType.REGEX.value)
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def bulk_whitelist(self, interaction: discord.Interaction, items: str, match_type: str = MatchType.CONTAINS.value, reason: Optional[str] = None):
        gid = interaction.guild.id
        entries = [entry.strip() for entry in items.split(',') if entry.strip()]
        processed: List[str] = []
        for item in entries:
            # Remove from blacklist
            await self.blacklist_collection.delete_one({"guild_id": gid, "item": item})
            self.blacklist_cache.get(gid, {}).pop(item, None)
            # Upsert whitelist
            await self.whitelist_collection.update_one({"guild_id": gid, "item": item}, {"$set": {"match_type": match_type, "reason": reason, "added_by": interaction.user.id, "added_at": discord.utils.utcnow().isoformat()}}, upsert=True)
            self.whitelist_cache.setdefault(gid, {})[item] = match_type
            processed.append(item)
        await interaction.response.send_message(f"✅ Bulk whitelisted: {', '.join(processed)} ({match_type})", ephemeral=True)

    # Updated paginated commands
    
    @app_commands.command(name="show_blacklisted", description="Show all blacklisted items")
    @app_commands.describe(
        match_type="Filter by match type (default: all)",
        page="Page number to view",
        ephemeral="Whether to show only to you"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="All", value="all"),
        app_commands.Choice(name="Contains", value=MatchType.CONTAINS.value),
        app_commands.Choice(name="Exact", value=MatchType.EXACT.value),
        app_commands.Choice(name="Starts With", value=MatchType.STARTS_WITH.value),
        app_commands.Choice(name="Ends With", value=MatchType.ENDS_WITH.value),
        app_commands.Choice(name="Regex", value=MatchType.REGEX.value)
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def show_blacklisted(self, interaction: discord.Interaction, match_type: str = "all", page: int = 1, ephemeral: bool = True):
        gid = interaction.guild.id
        items = await self.blacklist_collection.find({"guild_id": gid}).to_list(length=None)
        
        if not items:
            return await interaction.response.send_message("No blacklisted items found.", ephemeral=ephemeral)
        
        # Paginate with 25 items per page (Discord's limit for embed fields)
        items_per_page = 25
        
        # Validate page number
        filtered_items = items if match_type == "all" else [item for item in items if item.get("match_type") == match_type]
        total_pages = max(1, math.ceil(len(filtered_items) / items_per_page))
        page = max(1, min(page, total_pages))  # Ensure page is in valid range
        
        # Create paginator view
        view = PaginationView(
            items=items,
            match_type=match_type,
            page=page,
            items_per_page=items_per_page,
            is_blacklist=True,
            interaction=interaction
        )
        
        # Send the paginated response
        await interaction.response.send_message(
            embed=view.get_embed(), 
            view=view,
            ephemeral=ephemeral
        )
        
        # Store the message for timeout handling
        view.message = await interaction.original_response()

    @app_commands.command(name="show_whitelisted", description="Show all whitelisted items")
    @app_commands.describe(
        match_type="Filter by match type (default: all)", 
        page="Page number to view",
        ephemeral="Whether to show only to you"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="All", value="all"),
        app_commands.Choice(name="Contains", value=MatchType.CONTAINS.value),
        app_commands.Choice(name="Exact", value=MatchType.EXACT.value),
        app_commands.Choice(name="Starts With", value=MatchType.STARTS_WITH.value),
        app_commands.Choice(name="Ends With", value=MatchType.ENDS_WITH.value),
        app_commands.Choice(name="Regex", value=MatchType.REGEX.value)
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def show_whitelisted(self, interaction: discord.Interaction, match_type: str = "all", page: int = 1, ephemeral: bool = True):
        gid = interaction.guild.id
        items = await self.whitelist_collection.find({"guild_id": gid}).to_list(length=None)
        
        if not items:
            return await interaction.response.send_message("No whitelisted items found.", ephemeral=ephemeral)
        
        # Paginate with 25 items per page (Discord's limit for embed fields)
        items_per_page = 25
        
        # Validate page number
        filtered_items = items if match_type == "all" else [item for item in items if item.get("match_type") == match_type]
        total_pages = max(1, math.ceil(len(filtered_items) / items_per_page))
        page = max(1, min(page, total_pages))  # Ensure page is in valid range
        
        # Create paginator view
        view = PaginationView(
            items=items,
            match_type=match_type,
            page=page,
            items_per_page=items_per_page,
            is_blacklist=False,
            interaction=interaction
        )
        
        # Send the paginated response
        await interaction.response.send_message(
            embed=view.get_embed(), 
            view=view,
            ephemeral=ephemeral
        )
        
        # Store the message for timeout handling
        view.message = await interaction.original_response()

    # New punishment management commands
    
    @app_commands.command(name="punishment_config", description="Configure blacklist punishment settings")
    @app_commands.default_permissions(administrator=True)
    async def punishment_config(self, interaction: discord.Interaction):
        """Configure punishment settings for blacklist violations"""
        gid = interaction.guild.id
        
        # Ensure punishment settings are loaded
        if gid not in self.punishment_cache:
            await self._load_punishment_cache(gid)
        
        # Create settings view
        settings_view = PunishmentSettingsView(
            self,
            self.punishment_cache[gid],
            interaction
        )
        
        await interaction.response.send_message(
            embed=settings_view.get_embed(),
            view=settings_view,
            ephemeral=True
        )
        
        # Store message for timeout handling
        settings_view.message = await interaction.original_response()
    
    @app_commands.command(name="punishment_status", description="View current blacklist punishment settings")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(ephemeral="Whether to show only to you")
    async def punishment_status(self, interaction: discord.Interaction, ephemeral: bool = True):
        """View current punishment settings"""
        gid = interaction.guild.id
        
        # Ensure punishment settings are loaded
        if gid not in self.punishment_cache:
            await self._load_punishment_cache(gid)
        
        # Create embed with current settings
        settings = self.punishment_cache[gid]
        embed = discord.Embed(
            title="Blacklist Punishment Settings",
            color=discord.Color.blue()
        )
        
        # Status field
        status = "✅ Enabled" if settings.get("enabled", True) else "❌ Disabled"
        embed.add_field(name="Status", value=status, inline=False)
        
        # Basic settings
        embed.add_field(name="Violation Threshold", 
                      value=f"{settings['violation_threshold']} violations", 
                      inline=True)
        
        # Time window
        window_value = settings.get("time_window_value", 0)
        window_unit = settings.get("time_window_unit", TimeWindowUnit.MINUTES.value)
        if window_value > 0:
            embed.add_field(name="Time Window", 
                          value=f"{window_value} {window_unit}", 
                          inline=True)
        else:
            embed.add_field(name="Time Window", 
                          value="No time limit", 
                          inline=True)
        
        # Punishment details
        punishment_type = settings["punishment_type"]
        if punishment_type == PunishmentType.WARNING.value:
            embed.add_field(name="Punishment", value="Warning only", inline=True)
        elif punishment_type == PunishmentType.MUTE.value:
            duration = settings.get("duration_seconds", 0)
            if duration > 0:
                minutes = duration // 60
                seconds = duration % 60
                time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
                embed.add_field(name="Punishment", value=f"Mute for {time_str}", inline=True)
            else:
                embed.add_field(name="Punishment", value="Permanent Mute", inline=True)
        elif punishment_type == PunishmentType.KICK.value:
            embed.add_field(name="Punishment", value="Kick from server", inline=True)
        elif punishment_type == PunishmentType.BAN.value:
            embed.add_field(name="Punishment", value="Ban from server", inline=True)
        
        # Command help
        embed.add_field(
            name="Management Commands",
            value="/punishment_config - Configure these settings",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
    
    @app_commands.command(name="reset_violations", description="Reset violation count for a user")
    @app_commands.describe(user="The user to reset violations for")
    @app_commands.default_permissions(manage_messages=True)
    async def reset_violations(self, interaction: discord.Interaction, user: discord.Member):
        """Reset violation count for a specific user"""
        gid = interaction.guild.id
        user_id = user.id
        
        # Reset in cache
        if gid in self.user_violations:
            self.user_violations[gid][user_id] = 0
        if gid in self.violation_timestamps:
            self.violation_timestamps[gid][user_id] = []
        
        # Reset in database
        await self.violations_collection.update_one(
            {"guild_id": gid, "user_id": user_id},
            {"$set": {
                "violation_count": 0,
                "timestamps": [],
                "last_reset": discord.utils.utcnow().isoformat(),
                "reset_by": interaction.user.id
            }},
            upsert=True
        )
        
        await interaction.response.send_message(
            f"✅ Violation count for {user.display_name} has been reset to 0.",
            ephemeral=True
        )
    
    @app_commands.command(name="view_violations", description="View violation counts for users")
    @app_commands.describe(ephemeral="Whether to show only to you")
    @app_commands.default_permissions(manage_messages=True)
    async def view_violations(self, interaction: discord.Interaction, ephemeral: bool = True):
        """View violation counts for all users"""
        gid = interaction.guild.id
        
        # Collate violation data
        violations = {}
        async for doc in self.violations_collection.find({"guild_id": gid}):
            user_id = doc["user_id"]
            count = doc["violation_count"]
            if count > 0:  # Only show users with violations
                violations[user_id] = {
                    "count": count,
                    "timestamps": doc.get("timestamps", [])
                }
        
        if not violations:
            await interaction.response.send_message(
                "No users have violations in this server.",
                ephemeral=ephemeral
            )
            return
        
        # Create paginated view
        view = ViolationsView(self, gid, violations)
        
        await interaction.response.send_message(
            embed=view.get_embed(interaction.guild),
            view=view,
            ephemeral=ephemeral
        )
        
        # Store message for timeout handling
        view.message = await interaction.original_response()
    
    @app_commands.command(name="add_escalation_step", description="Add an escalation step for repeat offenders")
    @app_commands.describe(
        level="Escalation level (1, 2, 3, etc.)",
        punishment_type="Type of punishment for this level",
        duration="Duration in seconds (for mute only)"
    )
    @app_commands.choices(punishment_type=[
        app_commands.Choice(name="Warning Only", value=PunishmentType.WARNING.value),
        app_commands.Choice(name="Mute", value=PunishmentType.MUTE.value),
        app_commands.Choice(name="Kick", value=PunishmentType.KICK.value),
        app_commands.Choice(name="Ban", value=PunishmentType.BAN.value)
    ])
    @app_commands.default_permissions(administrator=True)
    async def add_escalation_step(self, interaction: discord.Interaction, 
                                  level: int, 
                                  punishment_type: str,
                                  duration: int = 0):
        """Add an escalation step for repeat offenders"""
        gid = interaction.guild.id
        
        # Ensure punishment settings are loaded
        if gid not in self.punishment_cache:
            await self._load_punishment_cache(gid)
        
        # Get current settings
        settings = self.punishment_cache[gid]
        
        # Enable escalation if not already enabled
        if not settings.get("enable_escalation", False):
            settings["enable_escalation"] = True
            
        # Initialize steps if needed
        if "escalation_steps" not in settings:
            settings["escalation_steps"] = []
            
        # Create new step
        step = {
            "level": level,
            "punishment_type": punishment_type,
            "duration_seconds": duration if punishment_type == PunishmentType.MUTE.value else 0
        }
        
        # Update steps list
        steps = settings["escalation_steps"]
        
        # Find if level already exists and replace, or add new
        found = False
        for i, existing_step in enumerate(steps):
            if existing_step.get("level") == level:
                steps[i] = step
                found = True
                break
                
        if not found:
            steps.append(step)
            # Sort by level
            steps.sort(key=lambda x: x.get("level", 0))
            
        # Update cache and database
        settings["escalation_steps"] = steps
        self.punishment_cache[gid] = settings
        
        await self.punishment_collection.update_one(
            {"guild_id": gid},
            {"$set": {
                "enable_escalation": True,
                "escalation_steps": steps
            }}
        )
        
        # Format duration for display
        duration_str = ""
        if punishment_type == PunishmentType.MUTE.value and duration > 0:
            if duration < 60:
                duration_str = f" for {duration}s"
            elif duration < 3600:
                minutes = duration // 60
                seconds = duration % 60
                duration_str = f" for {minutes}m{f' {seconds}s' if seconds > 0 else ''}"
            else:
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                duration_str = f" for {hours}h{f' {minutes}m' if minutes > 0 else ''}"
        
        await interaction.response.send_message(
            f"✅ Added escalation step: Level {level} - {punishment_type.capitalize()}{duration_str}",
            ephemeral=True
        )
        
    @app_commands.command(name="remove_escalation_step", description="Remove an escalation step")
    @app_commands.describe(level="Escalation level to remove")
    @app_commands.default_permissions(administrator=True)
    async def remove_escalation_step(self, interaction: discord.Interaction, level: int):
        """Remove an escalation step"""
        gid = interaction.guild.id
        
        # Ensure punishment settings are loaded
        if gid not in self.punishment_cache:
            await self._load_punishment_cache(gid)
        
        # Get current settings
        settings = self.punishment_cache[gid]
        
        # Check if escalation is enabled
        if not settings.get("enable_escalation", False):
            await interaction.response.send_message(
                "❌ Escalation punishment is not enabled for this server.",
                ephemeral=True
            )
            return
            
        # Check if steps exist
        steps = settings.get("escalation_steps", [])
        if not steps:
            await interaction.response.send_message(
                "❌ No escalation steps are defined for this server.",
                ephemeral=True
            )
            return
            
        # Find and remove the step
        for i, step in enumerate(steps):
            if step.get("level") == level:
                removed_step = steps.pop(i)
                
                # Update cache and database
                settings["escalation_steps"] = steps
                self.punishment_cache[gid] = settings
                
                await self.punishment_collection.update_one(
                    {"guild_id": gid},
                    {"$set": {"escalation_steps": steps}}
                )
                
                # Disable escalation if no steps left
                if not steps:
                    settings["enable_escalation"] = False
                    await self.punishment_collection.update_one(
                        {"guild_id": gid},
                        {"$set": {"enable_escalation": False}}
                    )
                
                await interaction.response.send_message(
                    f"✅ Removed escalation step: Level {level} - {removed_step.get('punishment_type').capitalize()}",
                    ephemeral=True
                )
                return
        
        # If we got here, step not found
        await interaction.response.send_message(
            f"❌ No escalation step with level {level} was found.",
            ephemeral=True
        )
        
    @app_commands.command(name="toggle_escalation", description="Enable or disable escalating punishments")
    @app_commands.describe(enabled="Whether escalation should be enabled")
    @app_commands.default_permissions(administrator=True)
    async def toggle_escalation(self, interaction: discord.Interaction, enabled: bool):
        """Enable or disable escalating punishments"""
        gid = interaction.guild.id
        
        # Ensure punishment settings are loaded
        if gid not in self.punishment_cache:
            await self._load_punishment_cache(gid)
        
        # Get current settings
        settings = self.punishment_cache[gid]
        
        # Update setting
        settings["enable_escalation"] = enabled
        self.punishment_cache[gid] = settings
        
        await self.punishment_collection.update_one(
            {"guild_id": gid},
            {"$set": {"enable_escalation": enabled}}
        )
        
        if enabled:
            steps = settings.get("escalation_steps", [])
            if not steps:
                await interaction.response.send_message(
                    "✅ Escalation punishment has been enabled, but no escalation steps are defined.\n"
                    "Use `/add_escalation_step` to define punishment steps.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"✅ Escalation punishment has been enabled with {len(steps)} defined steps.",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "✅ Escalation punishment has been disabled.",
                ephemeral=True
            )
            
    @app_commands.command(name="show_escalation_steps", description="View all escalation steps")
    @app_commands.describe(ephemeral="Whether to show only to you")
    @app_commands.default_permissions(manage_messages=True)
    async def show_escalation_steps(self, interaction: discord.Interaction, ephemeral: bool = True):
        """View all escalation steps"""
        gid = interaction.guild.id
        
        # Ensure punishment settings are loaded
        if gid not in self.punishment_cache:
            await self._load_punishment_cache(gid)
        
        # Get current settings
        settings = self.punishment_cache[gid]
        
        # Check if escalation is enabled
        enabled = settings.get("enable_escalation", False)
        steps = settings.get("escalation_steps", [])
        
        embed = discord.Embed(
            title="Escalation Punishment Steps",
            description=f"Status: {'✅ Enabled' if enabled else '❌ Disabled'}",
            color=discord.Color.blue()
        )
        
        if not steps:
            embed.add_field(
                name="No Steps Defined",
                value="Use `/add_escalation_step` to define punishment steps.",
                inline=False
            )
        else:
            # Sort steps by level
            steps.sort(key=lambda x: x.get("level", 0))
            
            for step in steps:
                level = step.get("level", 0)
                punishment_type = step.get("punishment_type", PunishmentType.WARNING.value)
                duration = step.get("duration_seconds", 0)
                
                value = punishment_type.capitalize()
                if punishment_type == PunishmentType.MUTE.value and duration > 0:
                    if duration < 60:
                        value += f" for {duration}s"
                    elif duration < 3600:
                        minutes = duration // 60
                        seconds = duration % 60
                        value += f" for {minutes}m{f' {seconds}s' if seconds > 0 else ''}"
                    else:
                        hours = duration // 3600
                        minutes = (duration % 3600) // 60
                        value += f" for {hours}h{f' {minutes}m' if minutes > 0 else ''}"
                
                embed.add_field(
                    name=f"Level {level}",
                    value=value,
                    inline=True
                )
        
        # Add command help
        embed.add_field(
            name="Management Commands",
            value=(
                "/add_escalation_step - Add a new step\n"
                "/remove_escalation_step - Remove a step\n"
                "/toggle_escalation - Enable/disable escalation"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

async def setup(bot: commands.Bot):
    await bot.add_cog(FilterCog(bot))
