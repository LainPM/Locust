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
        
        # AI intent check counter
        self.ai_checks_performed = defaultdict(int)  # User ID -> number of AI checks performed

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
        manager_role="Community Manager role to ping (required for high sensitivity)",
        raid_alert_channel="Channel to send detailed raid alerts to (optional)"
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
        
        # Make sure manager_role is provided for high sensitivity
        if sensitivity == 3 and not manager_role:
            await interaction.response.send_message("Please specify a community manager role. This is required for high sensitivity level.", ephemeral=True)
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
        
        # Store configuration
        self.config[guild_id] = {
            "enabled": sensitivity > 0,
            "sensitivity": sensitivity,
            "mod_role_id": mod_role.id if mod_role else None,
            "manager_role_id": manager_role.id if manager_role else None,
            "raid_alert_channel_id": raid_alert_channel.id if raid_alert_channel else None
        }
        
        # Save to database
        await self.save_config(guild_id)
        
        # Build response message
        if sensitivity == 0:
            message = "✅ Anti-Raid system has been **disabled** for this server."
        else:
            sensitivity_names = {1: "Low", 2: "Medium", 3: "High"}
            timeout_durations = {1: "5 minutes", 2: "15 minutes", 3: "1 hour"}
            message = f"✅ Anti-Raid system has been set up with **{sensitivity_names[sensitivity]}** sensitivity!\n\n"
            
            message += f"• Default timeout duration: **{timeout_durations[sensitivity]}**\n"
            message += f"• Moderator Role: {mod_role.mention}\n"
                
            if manager_role:
                if sensitivity == 3:
                    message += f"• Community Manager Role: {manager_role.mention} (will always be pinged)\n"
                elif sensitivity == 2:
                    message += f"• Community Manager Role: {manager_role.mention} (pinged for extended timeouts)\n"
                else:
                    message += f"• Community Manager Role: {manager_role.mention} (pinged only for max timeouts)\n"
                
            if raid_alert_channel:
                message += f"• Raid Alert Channel: {raid_alert_channel.mention}\n"
            
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

    async def mute_user(self, user_id: int, guild_id: int, duration_minutes: int = 5, reason: str = "Raid detection") -> bool:
        """Mute a user for the specified duration and delete their recent messages"""
        # Get guild and config
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False, []
            
        # Get member
        try:
            member = await guild.fetch_member(user_id)
            if not member:
                return False, []
            
            # Set timeout for the specified duration
            timeout_duration = datetime.timedelta(minutes=duration_minutes)
            await member.timeout(timeout_duration, reason=reason)
            
            # Set unmute time for tracking
            unmute_time = datetime.datetime.utcnow() + timeout_duration
            self.muted_users[user_id] = unmute_time
            
            # Store deleted messages info
            deleted_messages = []
            
            # Get the last 24 hours cutoff
            cutoff_time = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
            
            # For each channel in the guild, use more thorough deletion with the Purge functionality
            for channel in guild.text_channels:
                try:
                    # Check if bot can manage messages in this channel
                    if not channel.permissions_for(guild.me).manage_messages:
                        continue
                    
                    # Create a check function to match this user's messages
                    def is_user_message(message):
                        return message.author.id == user_id
                    
                    # Purge messages - more reliable than iterating through history
                    batch = []
                    async for message in channel.history(limit=200, after=cutoff_time):
                        if message.author.id == user_id:
                            # Store message info before deletion
                            deleted_messages.append({
                                "content": message.content,
                                "channel_id": channel.id,
                                "message_id": message.id,
                                "timestamp": message.created_at,
                                "jump_url": message.jump_url
                            })
                            batch.append(message)
                            
                            # Delete in batches of 100 (Discord's bulk delete limit)
                            if len(batch) >= 100:
                                try:
                                    await channel.delete_messages(batch)
                                    batch = []
                                except Exception as e:
                                    print(f"AntiRaid: Error bulk deleting messages: {e}")
                                    # If bulk delete fails, try individual deletion
                                    for msg in batch:
                                        try:
                                            await msg.delete()
                                        except Exception as e2:
                                            print(f"AntiRaid: Error deleting individual message: {e2}")
                                    batch = []
                    
                    # Delete any remaining messages in the batch
                    if batch:
                        try:
                            if len(batch) > 1:
                                await channel.delete_messages(batch)
                            else:
                                await batch[0].delete()
                        except Exception as e:
                            print(f"AntiRaid: Error deleting final batch: {e}")
                            # Try individual deletion if bulk fails
                            for msg in batch:
                                try:
                                    await msg.delete()
                                except Exception:
                                    pass
                    
                except Exception as e:
                    print(f"AntiRaid: Error purging messages in channel {channel.name}: {e}")
            
            print(f"AntiRaid: Muted user {user_id} for {duration_minutes} minutes and deleted {len(deleted_messages)} messages")
            return True, deleted_messages
            
        except Exception as e:
            print(f"AntiRaid: Error muting user {user_id}: {e}")
            return False, []

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
        
        # AI intent check counter for this user
        if not hasattr(self, 'ai_checks_performed'):
            self.ai_checks_performed = defaultdict(int)
            
        # If score exceeds AI threshold but below mute threshold, check with AI (but not too often)
        if ai_threshold <= total_score < mute_threshold and user_id not in self.currently_processing:
            # Only use AI for messages that are substantial AND haven't checked this user too many times
            if len(message.content) >= 20 and self.ai_checks_performed[user_id] < 2:
                self.currently_processing.add(user_id)
                try:
                    # Increment the AI check counter for this user
                    self.ai_checks_performed[user_id] += 1
                    
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
            # Determine mute duration based on sensitivity, AI involvement, and severity
            
            # Calculate severity on a scale of 0-1
            severity = min(1.0, (total_score - mute_threshold) / (mute_threshold * 0.5))
            
            # Determine if AI confirmed malicious intent
            ai_confirmed = self.ai_checks_performed.get(user_id, 0) > 0
            
            # Get base duration based on sensitivity
            base_duration_minutes = {1: 5, 2: 15, 3: 60}[sensitivity]
            
            # Set maximum durations based on sensitivity
            max_duration_minutes = {1: 60, 2: 360, 3: 1440}[sensitivity]  # 1h, 6h, 24h
            
            # Calculate duration more dynamically based on severity and AI confirmation
            if sensitivity == 1:  # Low sensitivity
                if ai_confirmed:
                    # AI confirmed - scale between 10 and 60 minutes
                    duration_minutes = int(10 + severity * 50)
                else:
                    # No AI confirmation - scale between 5 and 30 minutes
                    duration_minutes = int(base_duration_minutes + severity * 25)
            elif sensitivity == 2:  # Medium sensitivity
                if ai_confirmed or severity > 0.5:
                    # AI confirmed or high severity - scale between 30 and 360 minutes
                    duration_minutes = int(30 + severity * 330)
                else:
                    # No AI confirmation - scale between 15 and 120 minutes
                    duration_minutes = int(base_duration_minutes + severity * 105)
            else:  # High sensitivity
                # Scale between 60 and 1440 minutes (1 hour to 24 hours)
                duration_minutes = int(base_duration_minutes + severity * (max_duration_minutes - base_duration_minutes))
            
            # Set alert level based on duration and severity
            if duration_minutes >= max_duration_minutes * 0.75:
                alert_level = "SEVERE"
            elif duration_minutes >= max_duration_minutes * 0.4 or ai_confirmed:
                alert_level = "CONFIRMED"
            else:
                alert_level = "POTENTIAL"
            
            # Try to delete the current triggering message
            try:
                await message.delete()
            except Exception as e:
                print(f"AntiRaid: Failed to delete trigger message: {e}")
            
            # Try to mute user and delete their messages
            muted, deleted_messages = await self.mute_user(
                user_id, 
                guild_id, 
                duration_minutes, 
                f"AntiRaid: Score {total_score}"
            )
            
            if muted:
                # Get ping roles - prioritize mod_role
                ping_mentions = []
                
                # Always include mod_role (required)
                if config.get("mod_role_id"):
                    ping_mentions.append(f"<@&{config['mod_role_id']}>")
                
                # Determine if community manager should be pinged based on sensitivity and duration
                if config.get("manager_role_id"):
                    ping_manager = False
                    
                    # High sensitivity: Always ping manager
                    if sensitivity == 3:
                        ping_manager = True
                    # Medium sensitivity: Ping manager only if AI extended the timeout
                    elif sensitivity == 2 and (ai_confirmed or severity > 0.5):
                        ping_manager = True
                    # Low sensitivity: Ping manager only if max timeout (1 hour)
                    elif sensitivity == 1 and duration_minutes >= 45:  # Ping managers if close to max timeout
                        ping_manager = True
                        
                    if ping_manager:
                        ping_mentions.append(f"<@&{config['manager_role_id']}>")
                
                # Format minutes into hours and minutes if needed
                duration_str = f"{duration_minutes} minutes"
                if duration_minutes >= 60:
                    hours = duration_minutes // 60
                    mins = duration_minutes % 60
                    if mins == 0:
                        duration_str = f"{hours} hour{'s' if hours > 1 else ''}"
                    else:
                        duration_str = f"{hours} hour{'s' if hours > 1 else ''} and {mins} minute{'s' if mins > 1 else ''}"
                
                # Create standard alert message (without message content)
                alert = f"⚠️ **{alert_level} RAID ALERT** ⚠️\n\n"
                alert += f"User <@{user_id}> has been automatically timed out for {duration_str}.\n"
                alert += f"Raid Detection Score: {total_score}/{mute_threshold}\n"
                alert += f"Channel: {message.channel.mention}\n"
                alert += f"Deleted {len(deleted_messages)} messages from this user.\n\n"
                
                if ping_mentions:
                    alert += f"Please investigate: {' '.join(ping_mentions)}"
                
                # Try to send standard alert to the channel
                try:
                    await message.channel.send(alert)
                except Exception as e:
                    print(f"AntiRaid: Error sending alert: {e}")
                
                # If we have a dedicated raid alert channel, send detailed info there
                if config.get("raid_alert_channel_id") and deleted_messages:
                    alert_channel = None
                    try:
                        alert_channel = guild.get_channel(config["raid_alert_channel_id"])
                        
                        # If not found as a regular channel, try to find as a thread
                        if not alert_channel:
                            for channel in guild.text_channels:
                                for thread in channel.threads:
                                    if thread.id == config["raid_alert_channel_id"]:
                                        alert_channel = thread
                                        break
                                if alert_channel:
                                    break
                        
                        if alert_channel:
                            # Create detailed alert with message previews
                            detailed_alert = f"⚠️ **DETAILED {alert_level} RAID ALERT** ⚠️\n\n"
                            detailed_alert += f"User <@{user_id}> has been automatically timed out for {duration_str}.\n"
                            detailed_alert += f"Raid Detection Score: {total_score}/{mute_threshold}\n"
                            detailed_alert += f"Deleted {len(deleted_messages)} messages from this user.\n\n"
                            detailed_alert += f"**Raid Detection Channel:** {message.channel.mention}\n\n"
                            
                            # Add the most recent message (up to 3 messages max)
                            detailed_alert += "**Sample of Deleted Messages:**\n"
                            
                            # Sort messages by timestamp (newest first)
                            sorted_messages = sorted(deleted_messages, key=lambda x: x["timestamp"], reverse=True)
                            
                            # Show up to 3 most recent messages
                            for i, msg in enumerate(sorted_messages[:3]):
                                channel = guild.get_channel(msg["channel_id"])
                                channel_mention = channel.mention if channel else f"<#{msg['channel_id']}>"
                                
                                # Format the message
                                detailed_alert += f"**Message {i+1}:** [Link]({msg['jump_url']}) in {channel_mention}\n"
                                
                                # Truncate content if needed
                                content = msg["content"]
                                if len(content) > 400:
                                    content = content[:397] + "..."
                                    
                                detailed_alert += f"```\n{content}\n```\n"
                            
                            # Send detailed alert to the dedicated channel
                            await alert_channel.send(detailed_alert)
                            print(f"AntiRaid: Sent detailed alert to channel {alert_channel.name}")
                    except Exception as e:
                        print(f"AntiRaid: Error sending detailed alert: {e}")
                        # If we failed to send to the alert channel, try to send to the original channel
                        if not alert_channel:
                            print(f"AntiRaid: Alert channel {config['raid_alert_channel_id']} not found")
                
                # Reset the user's raid score
                self.user_raid_score[user_id] = 0
                
                # Reset AI checks counter for this user
                if user_id in self.ai_checks_performed:
                    del self.ai_checks_performed[user_id]
    
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
