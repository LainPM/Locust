import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import datetime
from typing import Dict, List, Optional, Set, Tuple
import re
from collections import defaultdict, Counter

class AntiRaidCog(commands.Cog):
    """Anti-Raid system for Discord servers"""
    
    def __init__(self, bot):
        self.bot = bot
        
        # Configuration
        self.config = {}  # Guild ID -> config
        
        # Message tracking
        self.user_messages = defaultdict(list)  # User ID -> list of (timestamp, content, channel_id)
        self.user_raid_score = defaultdict(int)  # User ID -> current raid score
        self.currently_processing = set()  # Set of user IDs currently being processed by AI
        self.muted_users = {}  # User ID -> unmute time

        # Database setup (use bot's MongoDB if available)
        self.db = None
        if hasattr(bot, 'mongo_client') and bot.mongo_client is not None:
            try:
                self.db = bot.db
                self.raid_config = self.db.raid_config
                print("AntiRaid Cog: Successfully connected to MongoDB")
                # Load config from database
                self.bot.loop.create_task(self.load_config())
            except Exception as e:
                print(f"AntiRaid Cog: Error connecting to MongoDB: {e}")
                self.db = None
        
        # Start background task to clear old data
        self.cleanup_task = bot.loop.create_task(self.cleanup_old_data())
    
    async def load_config(self):
        """Load raid configuration from database"""
        if self.db is None:
            return
            
        try:
            cursor = self.raid_config.find({})
            async for doc in cursor:
                guild_id = doc["guild_id"]
                self.config[guild_id] = {
                    "enabled": doc.get("enabled", False),
                    "sensitivity": doc.get("sensitivity", 1),
                    "mod_role_id": doc.get("mod_role_id"),
                    "staff_role_id": doc.get("staff_role_id"),
                    "manager_role_id": doc.get("manager_role_id"),
                    "mute_role_id": doc.get("mute_role_id")
                }
            print(f"AntiRaid Cog: Loaded configuration for {len(self.config)} guilds")
        except Exception as e:
            print(f"AntiRaid Cog: Error loading config: {e}")
    
    async def save_config(self, guild_id: int):
        """Save raid configuration to database"""
        if self.db is None or guild_id not in self.config:
            return
            
        try:
            await self.raid_config.update_one(
                {"guild_id": guild_id},
                {"$set": self.config[guild_id]},
                upsert=True
            )
        except Exception as e:
            print(f"AntiRaid Cog: Error saving config: {e}")
    
    async def cleanup_old_data(self):
        """Background task to clean up old message data"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                # Get current time
                now = datetime.datetime.utcnow()
                
                # Remove messages older than 10 minutes
                cutoff = now - datetime.timedelta(minutes=10)
                
                # For each user
                for user_id in list(self.user_messages.keys()):
                    # Filter out old messages
                    self.user_messages[user_id] = [
                        msg for msg in self.user_messages[user_id]
                        if msg[0] > cutoff
                    ]
                    
                    # If no messages left, remove user from tracking
                    if not self.user_messages[user_id]:
                        del self.user_messages[user_id]
                        if user_id in self.user_raid_score:
                            del self.user_raid_score[user_id]
                
                # Check for muted users to unmute
                for user_id in list(self.muted_users.keys()):
                    unmute_time = self.muted_users[user_id]
                    if now >= unmute_time:
                        # Try to unmute
                        await self.unmute_user(user_id)
                
                # Sleep for 1 minute
                await asyncio.sleep(60)
            except Exception as e:
                print(f"AntiRaid Cog: Error in cleanup task: {e}")
                await asyncio.sleep(60)
    
    @app_commands.command(name="setup-antiraid")
    @app_commands.describe(
        sensitivity="Raid detection sensitivity (0=Off, 1=Low, 2=Medium, 3=High)",
        mod_role="Moderator role to ping (required for alerts)",
        staff_role="Staff role to ping (optional)",
        manager_role="Manager role to ping (optional)"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_antiraid(
        self,
        interaction: discord.Interaction,
        sensitivity: int,
        mod_role: Optional[discord.Role] = None,
        staff_role: Optional[discord.Role] = None,
        manager_role: Optional[discord.Role] = None
    ):
        """Set up the anti-raid system for your server"""
        # Check if user has administrator permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need Administrator permission to use this command.", ephemeral=True)
            return
        
        # Validate sensitivity
        if sensitivity not in (0, 1, 2, 3):
            await interaction.response.send_message("Sensitivity must be 0 (Off), 1 (Low), 2 (Medium), or 3 (High)", ephemeral=True)
            return
        
        # Make sure mod_role is provided if system is enabled
        if sensitivity > 0 and not mod_role:
            await interaction.response.send_message("Please specify a moderator role to ping for alerts. This is required when the system is enabled.", ephemeral=True)
            return
        
        # Check if bot has required permissions
        required_perms = ['manage_roles', 'manage_messages']
        missing_perms = []
        
        for perm in required_perms:
            if not getattr(interaction.guild.me.guild_permissions, perm, False):
                missing_perms.append(perm)
        
        if missing_perms:
            formatted_perms = ', '.join(perm.replace('_', ' ').title() for perm in missing_perms)
            await interaction.response.send_message(f"I need the following permissions to function properly: {formatted_perms}", ephemeral=True)
            return
        
        # Get guild ID
        guild_id = interaction.guild.id
        
        # Store configuration (no mute_role_id as we're using direct muting)
        self.config[guild_id] = {
            "enabled": sensitivity > 0,
            "sensitivity": sensitivity,
            "mod_role_id": mod_role.id if mod_role else None,
            "staff_role_id": staff_role.id if staff_role else None,
            "manager_role_id": manager_role.id if manager_role else None
        }
        
        # Save to database
        await self.save_config(guild_id)
        
        # Build response message
        if sensitivity == 0:
            message = "✅ Anti-Raid system has been **disabled** for this server."
        else:
            sensitivity_names = {1: "Low", 2: "Medium", 3: "High"}
            message = f"✅ Anti-Raid system has been set up with **{sensitivity_names[sensitivity]}** sensitivity!\n\n"
            
            message += f"Moderator Role: {mod_role.mention}\n"
                
            if staff_role:
                message += f"Staff Role: {staff_role.mention}\n"
                
            if manager_role:
                message += f"Manager Role: {manager_role.mention}\n"
            
            message += "\nThe system will automatically monitor messages for raid behavior, delete raid messages, and timeout raiders."
        
        # Send response
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=False)
        else:
            await interaction.response.send_message(message, ephemeral=False)

    async def detect_intent_with_ai(self, message_content: str) -> Tuple[bool, float]:
        """
        Use AI to detect malicious intent in a message
        Returns: (is_malicious, confidence)
        """
        # Check if we have the AI Cog
        ai_cog = self.bot.get_cog("AICog")
        if not ai_cog:
            return (False, 0.0)  # Can't use AI
            
        # Prepare a simple query for intent detection
        prompt = [{
            "role": "user",
            "content": f'Analyze this message and determine if it has malicious intent (raid, spam, troll, harassment, etc). Reply with ONLY "YES" or "NO" followed by a confidence score from 0.0 to 1.0 (e.g., "YES 0.85" or "NO 0.3"): "{message_content}"'
        }]
        
        # Use Gemini API
        try:
            response = await ai_cog.query_gemini_simple(prompt)
            
            # Parse response
            if response.startswith("YES"):
                confidence_match = re.search(r'\d+\.\d+', response)
                confidence = float(confidence_match.group(0)) if confidence_match else 0.8
                return (True, confidence)
            else:
                confidence_match = re.search(r'\d+\.\d+', response)
                confidence = float(confidence_match.group(0)) if confidence_match else 0.5
                return (False, confidence)
        except Exception as e:
            print(f"AntiRaid: Error in AI detection: {e}")
            return (False, 0.0)

    async def mute_user(self, user_id: int, guild_id: int, duration_hours: int = 1, reason: str = "Raid detection") -> bool:
        """Mute a user for the specified duration and delete their recent messages"""
        # Get guild and config
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False
            
        # Get member
        try:
            member = await guild.fetch_member(user_id)
            if not member:
                return False
            
            # Set timeout for the specified duration
            timeout_duration = datetime.timedelta(hours=duration_hours)
            await member.timeout(timeout_duration, reason=reason)
            
            # Set unmute time for tracking
            unmute_time = datetime.datetime.utcnow() + timeout_duration
            self.muted_users[user_id] = unmute_time
            
            # Delete recent messages from this user (up to 100 messages from the past 24 hours)
            deleted_count = 0
            
            # Get the last 24 hours cutoff
            cutoff_time = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
            
            # For each channel in the guild
            for channel in guild.text_channels:
                try:
                    # Check if bot can manage messages in this channel
                    if not channel.permissions_for(guild.me).manage_messages:
                        continue
                        
                    # Look through message history
                    async for message in channel.history(limit=100, after=cutoff_time):
                        # If message is from the raider
                        if message.author.id == user_id:
                            try:
                                await message.delete()
                                deleted_count += 1
                            except Exception as e:
                                print(f"AntiRaid: Error deleting message: {e}")
                except Exception as e:
                    print(f"AntiRaid: Error checking channel {channel.name}: {e}")
            
            print(f"AntiRaid: Muted user {user_id} for {duration_hours} hours and deleted {deleted_count} messages")
            return True
            
        except Exception as e:
            print(f"AntiRaid: Error muting user {user_id}: {e}")
            return False

    async def unmute_user(self, user_id: int) -> bool:
        """Unmute a user"""
        # Remove from muted users
        if user_id in self.muted_users:
            del self.muted_users[user_id]
            
        # Find all guilds where this user is muted
        for guild_id, config in self.config.items():
            if not config.get("enabled"):
                continue
                
            # Get guild
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
                
            # Get member
            try:
                member = await guild.fetch_member(user_id)
                if not member:
                    continue
                    
                # Remove timeout if they have one
                if member.is_timed_out():
                    await member.timeout(None, reason="Anti-Raid timeout duration expired")
            except Exception as e:
                print(f"AntiRaid: Error unmuting user {user_id} in guild {guild_id}: {e}")
                
        return True

    def calculate_raid_score(self, user_id: int, message: discord.Message, sensitivity: int) -> int:
        """
        Calculate a raid score for a message based on sensitivity
        Higher score = more suspicious
        """
        score = 0
        user_messages = self.user_messages.get(user_id, [])
        
        # Message characteristics
        content = message.content
        
        # Content analysis
        
        # 1. Message length
        if len(content) > 500:
            score += 2 * sensitivity  # Long messages
        elif len(content) > 200:
            score += 1 * sensitivity
            
        # 2. All caps
        if len(content) > 15 and content.isupper():
            score += 2 * sensitivity
            
        # 3. Repeated characters
        for char in set(content):
            if content.count(char) > 10:
                score += 1 * sensitivity
                break
                
        # 4. External links (higher weight)
        if "http://" in content or "https://" in content:
            link_count = content.count("http")
            score += min(link_count * 2, 6) * sensitivity
            
        # 5. Mentions
        mention_count = len(message.mentions) + len(message.role_mentions)
        if mention_count > 5:
            score += 3 * sensitivity
        elif mention_count > 0:
            score += mention_count * sensitivity
        
        # 6. @everyone or @here
        if message.mention_everyone:
            score += 5 * sensitivity
            
        # Behavior analysis (based on previous messages)
        
        # 1. Message frequency
        now = datetime.datetime.utcnow()
        recent_messages = [msg for msg in user_messages if (now - msg[0]).total_seconds() < 60]
        
        if len(recent_messages) > 10:
            score += 5 * sensitivity  # Very high message rate
        elif len(recent_messages) > 5:
            score += 3 * sensitivity  # High message rate
            
        # 2. Cross-channel spam
        recent_channels = set(msg[2] for msg in recent_messages)
        if len(recent_channels) > 3:
            score += 4 * sensitivity  # Posting in many channels
            
        # 3. Content similarity
        if recent_messages:
            # Check for exact duplicates
            recent_contents = [msg[1] for msg in recent_messages]
            content_counts = Counter(recent_contents)
            
            # If same message sent multiple times
            most_common_count = content_counts.most_common(1)[0][1] if content_counts else 0
            if most_common_count > 2:
                score += most_common_count * sensitivity
        
        return score

    async def handle_raid_detection(self, message: discord.Message):
        """Main handler for raid detection"""
        # Skip if message is DM
        if not message.guild:
            return
            
        # Get guild config
        guild_id = message.guild.id
        config = self.config.get(guild_id)
        
        # Skip if not configured or disabled
        if not config or not config.get("enabled"):
            return
            
        sensitivity = config.get("sensitivity", 1)
        
        # Skip if sensitivity is 0 (off)
        if sensitivity == 0:
            return
            
        # Get user ID
        user_id = message.author.id
        
        # Skip if user is bot, guild owner, or already muted
        if (message.author.bot or 
            message.author.id == message.guild.owner_id or
            getattr(message.author, 'is_timed_out', lambda: False)()):
            return
            
        # Track message
        now = datetime.datetime.utcnow()
        self.user_messages[user_id].append((now, message.content, message.channel.id))
        
        # Calculate raid score
        raid_score = self.calculate_raid_score(user_id, message, sensitivity)
        
        # Update user's score (add to existing score for escalating behavior)
        existing_score = self.user_raid_score.get(user_id, 0)
        self.user_raid_score[user_id] = existing_score + raid_score
        total_score = self.user_raid_score[user_id]
        
        # Thresholds based on sensitivity
        ai_threshold = {1: 18, 2: 12, 3: 8}[sensitivity]
        mute_threshold = {1: 25, 2: 18, 3: 12}[sensitivity]
        
        # Debug log for high scores
        if total_score > 5:
            print(f"AntiRaid: User {user_id} raid score: {total_score}/{mute_threshold}")
        
        # If score exceeds AI threshold but below mute threshold, check with AI (but not too often)
        if ai_threshold <= total_score < mute_threshold and user_id not in self.currently_processing:
            # Only use AI for messages that are substantial
            if len(message.content) >= 20:
                self.currently_processing.add(user_id)
                try:
                    is_malicious, confidence = await self.detect_intent_with_ai(message.content)
                    
                    # If AI thinks it's malicious with high confidence, increase score
                    if is_malicious and confidence > 0.7:
                        additional_score = 10 * sensitivity
                        self.user_raid_score[user_id] = total_score + additional_score
                        total_score = self.user_raid_score[user_id]
                        print(f"AntiRaid: AI detected malicious intent ({confidence}) for user {user_id}, new score: {total_score}")
                finally:
                    self.currently_processing.remove(user_id)
        
        # If score exceeds mute threshold, take action
        if total_score >= mute_threshold:
            # Determine mute duration based on score
            if total_score >= mute_threshold * 2:  # Very high score
                duration_hours = 24
                alert_level = "SEVERE"
            else:
                duration_hours = 1
                alert_level = "POTENTIAL"
            
            # Try to delete the current triggering message
            try:
                await message.delete()
            except Exception as e:
                print(f"AntiRaid: Failed to delete trigger message: {e}")
            
            # Store message content before trying to mute (for the alert)
            message_content = message.content
            
            # Try to mute user and delete their messages
            muted = await self.mute_user(user_id, guild_id, duration_hours, f"AntiRaid: Score {total_score}")
            
            if muted:
                # Get ping roles - prioritize mod_role
                ping_mentions = []
                
                # Always include mod_role first if available
                if config.get("mod_role_id"):
                    ping_mentions.append(f"<@&{config['mod_role_id']}>")
                    
                if config.get("staff_role_id"):
                    ping_mentions.append(f"<@&{config['staff_role_id']}>")
                    
                if config.get("manager_role_id") and duration_hours > 1:  # Only ping managers for severe cases
                    ping_mentions.append(f"<@&{config['manager_role_id']}>")
                
                # Create alert message
                alert = f"⚠️ **{alert_level} RAID ALERT** ⚠️\n\n"
                alert += f"User <@{user_id}> has been automatically timed out for {duration_hours} hours.\n"
                alert += f"Raid Detection Score: {total_score}/{mute_threshold}\n"
                alert += f"Channel: {message.channel.mention}\n"
                alert += f"All recent messages from this user have been deleted.\n\n"
                
                if message_content:
                    # Truncate message content if too long
                    content_preview = message_content[:200] + ("..." if len(message_content) > 200 else "")
                    alert += f"Last message content: ```{content_preview}```\n\n"
                
                if ping_mentions:
                    alert += f"Please investigate: {' '.join(ping_mentions)}"
                
                # Try to send alert to the channel
                try:
                    await message.channel.send(alert)
                except Exception as e:
                    print(f"AntiRaid: Error sending alert: {e}")
                    # Try to find a mod channel to send alert
                    for channel in message.guild.text_channels:
                        if any(name in channel.name.lower() for name in ['mod', 'admin', 'log', 'alert']):
                            try:
                                await channel.send(alert)
                                break
                            except:
                                continue
                
                # Reset the user's raid score
                self.user_raid_score[user_id] = 0
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for messages and check for raid behavior"""
        try:
            await self.handle_raid_detection(message)
        except Exception as e:
            print(f"AntiRaid: Error in raid detection: {e}")

    async def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if self.cleanup_task:
            self.cleanup_task.cancel()

async def setup(bot):
    await bot.add_cog(AntiRaidCog(bot))
