# systems/moderation/anti_raid.py
import discord
import datetime
import asyncio
import re
from collections import Counter, defaultdict
from typing import Dict, List, Set, Any, Tuple

class RaidProtection:
    """Anti-raid component for content moderation"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        
        # Raid detection tracking
        self.join_tracker = defaultdict(list)  # Guild ID -> list of join timestamps
        self.raid_mode_active = set()  # Set of guild IDs with active raid mode
        self.raid_mode_expiry = {}     # Guild ID -> expiry time
        
        # Sensitivity thresholds
        self.sensitivity_thresholds = {
            1: {"joins": 5, "time": 20, "score": 15},  # Low sensitivity
            2: {"joins": 4, "time": 30, "score": 12},  # Medium sensitivity
            3: {"joins": 3, "time": 30, "score": 10}   # High sensitivity
        }
    
    async def initialize(self):
        """Initialize the anti-raid component"""
        # Nothing to initialize here currently
        pass
    
    async def load_settings(self, guild_id: int) -> Dict:
        """Load raid settings for a guild"""
        settings = await self.bot.db["raid_settings"].find_one({"guild_id": guild_id})
        
        if not settings:
            # Create default settings
            settings = {
                "guild_id": guild_id,
                "enabled": False,
                "sensitivity": 1,  # 1=Low, 2=Medium, 3=High
                "mod_role_id": None,
                "alert_channel_id": None,
                "auto_raid_mode": True,
                "raid_mode_action": "mute",  # mute, kick, ban
                "created_at": datetime.datetime.utcnow().isoformat()
            }
            
            await self.bot.db["raid_settings"].insert_one(settings)
        
        return settings
    
    async def process_member_join(self, member: discord.Member) -> bool:
        """Process a new member joining"""
        guild_id = member.guild.id
        
        # Get settings
        settings = await self.system.get_raid_settings(guild_id)
        
        # Check if raid protection is enabled
        if not settings.get("enabled", False):
            return True
        
        # Check if raid mode is active
        if guild_id in self.raid_mode_active:
            await self._apply_raid_mode_action(member, settings)
            return False
            
        # Track join in raid detection
        now = datetime.datetime.utcnow()
        self.join_tracker[guild_id].append(now)
        
        # Remove old joins (older than 5 minutes)
        self.join_tracker[guild_id] = [
            timestamp for timestamp in self.join_tracker[guild_id]
            if (now - timestamp).total_seconds() < 300
        ]
        
        # Check for raid join pattern
        sensitivity = settings.get("sensitivity", 1)
        thresholds = self.sensitivity_thresholds.get(sensitivity, self.sensitivity_thresholds[1])
        
        # Get recent joins within threshold time window
        time_window = thresholds["time"]
        recent_joins = [
            timestamp for timestamp in self.join_tracker[guild_id]
            if (now - timestamp).total_seconds() < time_window
        ]
        
        # Check if join rate exceeds threshold
        if len(recent_joins) >= thresholds["joins"]:
            # Potential raid detected
            await self._handle_raid_detection(member.guild, len(recent_joins), time_window, settings)
            await self._apply_raid_mode_action(member, settings)
            return False
        
        return True
    
    async def check_message(self, message: discord.Message) -> bool:
        """
        Check message for raid indicators
        Returns True if message passes checks, False if flagged
        """
        guild_id = message.guild.id
        user_id = message.author.id
        
        # Get settings
        settings = await self.system.get_raid_settings(guild_id)
        
        # Check if raid protection is enabled
        if not settings.get("enabled", False):
            return True
        
        # If raid mode is active, apply to new messages
        if guild_id in self.raid_mode_active:
            # In raid mode, apply action to newer accounts
            join_date = message.author.joined_at
            if join_date:
                account_age = (datetime.datetime.utcnow() - join_date).total_seconds()
                
                # If account joined during raid (last 5 minutes)
                if account_age < 300:
                    await self._handle_raid_message(message, settings)
                    return False
        
        # Calculate raid score for the message
        sensitivity = settings.get("sensitivity", 1)
        raid_score = self._calculate_raid_score(message, sensitivity)
        
        # Check if score exceeds threshold
        threshold = self.sensitivity_thresholds.get(sensitivity, self.sensitivity_thresholds[1])["score"]
        
        if raid_score >= threshold:
            await self._handle_raid_message(message, settings)
            return False
            
        return True
    
    def _calculate_raid_score(self, message: discord.Message, sensitivity: int) -> int:
        """Calculate a raid score for a message"""
        score = 0
        content = message.content
        
        # Base multiplier based on sensitivity
        sensitivity_multiplier = {1: 0.6, 2: 0.8, 3: 1.0}[sensitivity]
        
        # Check for invite links (high weight)
        invite_pattern = r'discord(?:\.gg|app\.com/invite)/\S+'
        if re.search(invite_pattern, content):
            score += 8 * sensitivity_multiplier
        
        # Check for external links
        link_pattern = r'https?://\S+'
        links = re.findall(link_pattern, content)
        score += min(len(links), 3) * 4 * sensitivity_multiplier
        
        # Check for mass mentions
        mention_count = len(message.mentions) + len(message.role_mentions)
        if mention_count > 0:
            score += min(mention_count, 5) * 3 * sensitivity_multiplier
        
        # Check for @everyone/@here
        if message.mention_everyone:
            score += 10 * sensitivity_multiplier
        
        # Check for suspicious patterns
        patterns = [
            (r'@everyone', 5),            # Raw text everyone mention
            (r'@here', 5),                # Raw text here mention
            (r'free\s+nitro', 6),         # Free Nitro scams
            (r'steam\s+gift', 6),         # Steam gift scams
            (r'discord\s+staff', 6),      # Discord staff impersonation
            (r'account\s+disabled', 5),   # Account disabled scams
            (r'claim\s+rewards', 5),      # Reward claim scams
            (r'password', 3),             # Password phishing
            (r'login', 3),                # Login phishing
        ]
        
        for pattern, weight in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                score += weight * sensitivity_multiplier
        
        # Check for new account
        join_date = message.author.joined_at
        if join_date:
            account_age = (datetime.datetime.utcnow() - join_date).total_seconds()
            
            if account_age < 3600:  # Less than 1 hour
                score += 5 * sensitivity_multiplier
            elif account_age < 86400:  # Less than 1 day
                score += 3 * sensitivity_multiplier
        
        return int(score)
    
    async def _handle_raid_detection(self, guild: discord.Guild, join_count: int, time_window: int, settings: Dict):
        """Handle detection of potential raid"""
        guild_id = guild.id
        
        # Check if auto raid mode is enabled
        if settings.get("auto_raid_mode", True):
            # Activate raid mode
            await self._activate_raid_mode(guild, settings)
        
        # Send alert to configured channel
        alert_channel_id = settings.get("alert_channel_id")
        if alert_channel_id:
            channel = guild.get_channel(int(alert_channel_id))
            
            if channel:
                # Get configured mod role mention
                mod_role_mention = ""
                mod_role_id = settings.get("mod_role_id")
                if mod_role_id:
                    mod_role_mention = f"<@&{mod_role_id}> "
                
                # Create alert embed
                embed = discord.Embed(
                    title="⚠️ RAID ALERT",
                    description=f"Potential raid detected: {join_count} joins in {time_window} seconds",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.utcnow()
                )
                
                # Add raid mode info
                if guild_id in self.raid_mode_active:
                    action = settings.get("raid_mode_action", "mute")
                    expiry = self.raid_mode_expiry.get(guild_id)
                    expiry_str = f"<t:{int(expiry.timestamp())}:R>" if expiry else "Unknown"
                    
                    embed.add_field(
                        name="Raid Mode Activated",
                        value=f"Action: {action.title()}\nExpires: {expiry_str}"
                    )
                
                # Add instructions
                embed.add_field(
                    name="Manual Actions",
                    value="Use `/raid_mode` to manually toggle raid mode" +
                          ("\nUse `/raid_mode off` to disable" if guild_id in self.raid_mode_active else "")
                )
                
                try:
                    await channel.send(content=mod_role_mention, embed=embed)
                except Exception as e:
                    print(f"Failed to send raid alert: {e}")
    
    async def _activate_raid_mode(self, guild: discord.Guild, settings: Dict):
        """Activate raid mode for a guild"""
        guild_id = guild.id
        
        # Already in raid mode
        if guild_id in self.raid_mode_active:
            return
        
        # Set raid mode
        self.raid_mode_active.add(guild_id)
        
        # Set expiry (10 minutes by default)
        expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
        self.raid_mode_expiry[guild_id] = expiry
        
        # Log to database
        await self.bot.db["raid_history"].insert_one({
            "guild_id": guild_id,
            "activated_at": datetime.datetime.utcnow().isoformat(),
            "expires_at": expiry.isoformat(),
            "action": settings.get("raid_mode_action", "mute"),
            "triggered_by": "auto",
            "status": "active"
        })
        
        # Schedule task to disable raid mode
        self.bot.loop.create_task(self._schedule_raid_mode_end(guild_id, 600))
    
    async def _schedule_raid_mode_end(self, guild_id: int, delay_seconds: int):
        """Schedule the end of raid mode"""
        await asyncio.sleep(delay_seconds)
        
        # Check if still active
        if guild_id in self.raid_mode_active:
            # Deactivate raid mode
            self.raid_mode_active.remove(guild_id)
            if guild_id in self.raid_mode_expiry:
                del self.raid_mode_expiry[guild_id]
            
            # Update database
            await self.bot.db["raid_history"].update_many(
                {"guild_id": guild_id, "status": "active"},
                {"$set": {"status": "expired", "ended_at": datetime.datetime.utcnow().isoformat()}}
            )
            
            # Try to notify alert channel
            try:
                settings = await self.system.get_raid_settings(guild_id)
                alert_channel_id = settings.get("alert_channel_id")
                
                if alert_channel_id:
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        channel = guild.get_channel(int(alert_channel_id))
                        if channel:
                            await channel.send("🛡️ Raid mode has been automatically deactivated.")
            except Exception as e:
                print(f"Error sending raid mode deactivation notification: {e}")
    
    async def _apply_raid_mode_action(self, member: discord.Member, settings: Dict):
        """Apply configured raid mode action to a new member"""
        action = settings.get("raid_mode_action", "mute")
        
        if action == "mute":
            # Apply timeout (mute) for 1 hour
            try:
                await member.timeout(datetime.timedelta(hours=1), reason="Raid mode active")
            except Exception as e:
                print(f"Failed to mute user during raid mode: {e}")
        
        elif action == "kick":
            try:
                await member.send(f"You have been removed from {member.guild.name} because raid mode is active. You may try joining again later.")
            except:
                pass  # Can't DM
                
            try:
                await member.kick(reason="Raid mode active")
            except Exception as e:
                print(f"Failed to kick user during raid mode: {e}")
        
        elif action == "ban":
            try:
                await member.send(f"You have been banned from {member.guild.name} because raid mode is active. This may be temporary.")
            except:
                pass  # Can't DM
                
            try:
                await member.ban(reason="Raid mode active", delete_message_days=1)
            except Exception as e:
                print(f"Failed to ban user during raid mode: {e}")
    
    async def _handle_raid_message(self, message: discord.Message, settings: Dict):
        """Handle a message flagged as potential raid message"""
        guild_id = message.guild.id
        user_id = message.author.id
        
        # Delete message
        try:
            await message.delete()
        except Exception as e:
            print(f"Failed to delete raid message: {e}")
        
        # Track violation
        evidence = f"Message flagged as potential raid content: {message.content[:100]}"
        violation_count = await self.system.increment_violation(guild_id, user_id, "raid", evidence)
        
        # Apply punishment based on violation count
        sensitivity = settings.get("sensitivity", 1)
        
        # Determine appropriate action based on sensitivity and violation count
        if violation_count >= 3:
            # Multiple violations, take stronger action
            if sensitivity == 3:
                # High sensitivity - ban
                await self.system.punishments.apply_punishment(
                    message.guild, message.author, "ban", "Multiple raid message violations", 
                    evidence=evidence
                )
            elif sensitivity == 2:
                # Medium sensitivity - longer timeout
                await self.system.punishments.apply_punishment(
                    message.guild, message.author, "mute", "Multiple raid message violations", 
                    duration_seconds=3600, evidence=evidence
                )
            else:
                # Low sensitivity - shorter timeout
                await self.system.punishments.apply_punishment(
                    message.guild, message.author, "mute", "Multiple raid message violations", 
                    duration_seconds=1800, evidence=evidence
                )
        else:
            # First violation, just delete and warn
            try:
                await message.channel.send(
                    f"{message.author.mention}, your message was removed as it was flagged as potential raid/spam content.",
                    delete_after=5
                )
            except:
                pass  # Can't send
