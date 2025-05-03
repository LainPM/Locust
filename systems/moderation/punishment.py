# systems/moderation/punishment.py
import discord
import datetime
import asyncio
from typing import Dict, List, Any, Optional

class PunishmentManager:
    """Punishment management component for content moderation"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        
        # Default punishment thresholds
        self.default_thresholds = {
            "violation_threshold": 3,   # Violations before punishment
            "time_window_minutes": 10,  # Time window to count violations
            "punishments": {
                1: {"type": "warn", "duration": 0},                    # First punishment: warn
                2: {"type": "mute", "duration": 300},                  # Second: 5-minute mute
                3: {"type": "mute", "duration": 1800},                 # Third: 30-minute mute
                4: {"type": "mute", "duration": 3600 * 24},            # Fourth: 24-hour mute
                5: {"type": "kick", "duration": 0},                    # Fifth: kick
                6: {"type": "ban", "duration": 0}                      # Sixth+: ban
            }
        }
    
    async def initialize(self):
        """Initialize the punishment component"""
        # Nothing to initialize here currently
        pass
    
    async def check_for_punishment(self, guild_id: int, user_id: int, violation_count: int, violation_type: str):
        """Check if a punishment should be applied based on violation count"""
        # Get punishment settings
        settings = await self._get_punishment_settings(guild_id)
        
        # Skip if punishments not enabled
        if not settings.get("enabled", True):
            return
            
        # Get violation threshold
        threshold = settings.get("violation_threshold", self.default_thresholds["violation_threshold"])
        
        if violation_count >= threshold:
            try:
                # Get guild and member
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    return
                    
                member = await guild.fetch_member(user_id)
                if not member:
                    return
                
                # Get the appropriate punishment tier
                punishment_tier = max(1, violation_count - threshold + 1)
                
                # Get max tier
                max_tier = max(settings.get("punishments", self.default_thresholds["punishments"]).keys())
                if punishment_tier > max_tier:
                    punishment_tier = max_tier
                
                # Get punishment details
                punishment_data = settings.get("punishments", self.default_thresholds["punishments"]).get(
                    str(punishment_tier), self.default_thresholds["punishments"][1]
                )
                
                # Apply the punishment
                punishment_type = punishment_data.get("type", "warn")
                duration = punishment_data.get("duration", 0)
                
                reason = f"Automatic punishment for {violation_type} violations (Count: {violation_count})"
                
                await self.apply_punishment(guild, member, punishment_type, reason, duration)
            except Exception as e:
                print(f"Error applying automatic punishment: {e}")
    
    async def apply_punishment(self, guild: discord.Guild, member: discord.Member, 
                             punishment_type: str, reason: str, duration_seconds: int = 0,
                             evidence: str = None):
        """Apply a punishment to a member"""
        try:
            # Apply punishment based on type
            if punishment_type == "warn":
                success = await self._warn_user(guild, member, reason)
            elif punishment_type == "mute":
                success = await self._mute_user(guild, member, duration_seconds, reason)
            elif punishment_type == "kick":
                success = await self._kick_user(guild, member, reason)
            elif punishment_type == "ban":
                success = await self._ban_user(guild, member, reason)
            else:
                print(f"Unknown punishment type: {punishment_type}")
                return False
            
            # Log the punishment
            if success:
                await self._log_punishment(guild.id, member.id, punishment_type, reason, duration_seconds, evidence)
                
            return success
            
        except Exception as e:
            print(f"Error applying punishment {punishment_type} to {member.id}: {e}")
            return False
    
    async def unmute_user(self, user_id: int):
        """Unmute a user across all servers"""
        # Remove from muted users
        if user_id in self.system.muted_users:
            del self.system.muted_users[user_id]
            
        # Find all guilds where user is a member
        for guild in self.bot.guilds:
            try:
                member = await guild.fetch_member(user_id)
                if member and member.is_timed_out():
                    await member.timeout(None, reason="Timeout duration expired")
                    
                    # Log the unmute
                    await self._log_punishment(
                        guild.id, user_id, "unmute", "Automatic unmute after timeout expiry", 0
                    )
            except Exception as e:
                print(f"Error unmuting user {user_id} in guild {guild.id}: {e}")
    
    async def _get_punishment_settings(self, guild_id: int) -> Dict:
        """Get punishment settings for a guild"""
        settings = await self.bot.db["punishment_settings"].find_one({"guild_id": guild_id})
        
        if not settings:
            # Create default settings
            settings = {
                "guild_id": guild_id,
                "enabled": True,
                "violation_threshold": self.default_thresholds["violation_threshold"],
                "time_window_minutes": self.default_thresholds["time_window_minutes"],
                "auto_reset_violations": True,
                "punishments": self.default_thresholds["punishments"],
                "created_at": datetime.datetime.utcnow().isoformat()
            }
            
            await self.bot.db["punishment_settings"].insert_one(settings)
        
        return settings
    
    async def _warn_user(self, guild: discord.Guild, member: discord.Member, reason: str) -> bool:
        """Send a warning to a user"""
        try:
            # Try to DM the user
            try:
                await member.send(f"⚠️ **Warning**: You have received a warning in {guild.name} for: {reason}")
            except Exception:
                # Cannot DM user, will notify in log only
                pass
                
            # Success even if DM fails
            return True
            
        except Exception as e:
            print(f"Error warning user: {e}")
            return False
    
    async def _mute_user(self, guild: discord.Guild, member: discord.Member, duration: int, reason: str) -> bool:
        """Mute a user for the specified duration"""
        try:
            # Calculate timedelta
            timeout_duration = datetime.timedelta(seconds=duration) if duration > 0 else None
            
            # Apply timeout
            await member.timeout(timeout_duration, reason=reason)
            
            # Track for unmute (if not indefinite)
            if duration > 0:
                unmute_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration)
                self.system.muted_users[member.id] = unmute_time
            
            # Try to notify the user
            try:
                if duration > 0:
                    duration_text = self._format_duration(duration)
                    await member.send(f"🔇 You have been muted in {guild.name} for {duration_text}.\nReason: {reason}")
                else:
                    await member.send(f"🔇 You have been muted indefinitely in {guild.name}.\nReason: {reason}")
            except Exception:
                # Cannot DM user
                pass
                
            return True
            
        except Exception as e:
            print(f"Error muting user: {e}")
            return False
    
    async def _kick_user(self, guild: discord.Guild, member: discord.Member, reason: str) -> bool:
        """Kick a user from the server"""
        try:
            # Try to notify the user before kicking
            try:
                await member.send(f"👢 You have been kicked from {guild.name}.\nReason: {reason}")
            except Exception:
                # Cannot DM user
                pass
                
            # Kick the user
            await member.kick(reason=reason)
            return True
            
        except Exception as e:
            print(f"Error kicking user: {e}")
            return False
    
    async def _ban_user(self, guild: discord.Guild, member: discord.Member, reason: str) -> bool:
        """Ban a user from the server"""
        try:
            # Try to notify the user before banning
            try:
                await member.send(f"🔨 You have been banned from {guild.name}.\nReason: {reason}")
            except Exception:
                # Cannot DM user
                pass
                
            # Ban the user, delete 1 day of messages
            await member.ban(reason=reason, delete_message_days=1)
            return True
            
        except Exception as e:
            print(f"Error banning user: {e}")
            return False
    
    async def _log_punishment(self, guild_id: int, user_id: int, punishment_type: str, 
                             reason: str, duration: int = 0, evidence: str = None):
        """Log a punishment to the database"""
        log_data = {
            "guild_id": guild_id,
            "user_id": user_id,
            "punishment_type": punishment_type,
            "reason": reason,
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "duration_seconds": duration,
            "evidence": evidence,
            "automatic": True
        }
        
        await self.bot.db["punishment_logs"].insert_one(log_data)
        
        # Check for log channel
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return
                
            # Get moderation settings
            settings = await self.bot.db["moderation_settings"].find_one({"guild_id": guild_id})
            if not settings or not settings.get("log_channel_id"):
                return
                
            log_channel = guild.get_channel(int(settings["log_channel_id"]))
            if not log_channel:
                return
                
            # Create embed
            embed = discord.Embed(
                title=f"Automatic {punishment_type.title()}",
                description=f"<@{user_id}> has been {punishment_type}ed automatically.",
                color=discord.Color.red() if punishment_type != "unmute" else discord.Color.green(),
                timestamp=datetime.datetime.utcnow()
            )
            
            embed.add_field(name="Reason", value=reason, inline=False)
            
            if duration > 0:
                embed.add_field(name="Duration", value=self._format_duration(duration), inline=True)
                
            if evidence:
                embed.add_field(name="Evidence", value=evidence[:1024], inline=False)
                
            await log_channel.send(embed=embed)
            
        except Exception as e:
            print(f"Error logging punishment to channel: {e}")
    
    def _format_duration(self, seconds: int) -> str:
        """Format a duration in seconds to a human-readable string"""
        if seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        elif seconds < 86400:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if minutes == 0:
                return f"{hours} hour{'s' if hours != 1 else ''}"
            return f"{hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''}"
        else:
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            if hours == 0:
                return f"{days} day{'s' if days != 1 else ''}"
            return f"{days} day{'s' if days != 1 else ''} and {hours} hour{'s' if hours != 1 else ''}"
