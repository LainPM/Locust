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
        
        # Cooldown for raid alerts to prevent spam
        self.alert_cooldowns = {}  # User ID -> last alert time
        self.alert_cooldown_seconds = 30  # Minimum seconds between alerts for the same user
        
        # Custom thresholds for different sensitivity levels (less strict)
        self.thresholds = {
            1: {"ai": 15, "mute": 20},  # Low sensitivity
            2: {"ai": 10, "mute": 15},  # Medium sensitivity 
            3: {"ai": 8, "mute": 12}    # High sensitivity
        }

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
                    "mute_role_id": doc.get("mute_role_id"),
                    "raid_alert_channel_id": doc.get("raid_alert_channel_id")  # Fixed: Added this line to properly load the raid alert channel ID
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
        # Check if user has administrator permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need Administrator permission to use this command.", ephemeral=True)
            return
        
        # Validate sensitivity
        if sensitivity not in (0, 1, 2, 3):
            await interaction.response.send_message("Sensitivity must be 0 (Off), 1 (Low), 2 (Medium), or 3 (High)", ephemeral=True)
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
        
        # If raid_alert_channel is provided, verify and test it
        if raid_alert_channel:
            try:
                # Check permissions explicitly before attempting to send
                if not raid_alert_channel.permissions_for(interaction.guild.me).send_messages:
                    await interaction.response.send_message(
                        f"Error: I don't have permission to send messages in {raid_alert_channel.mention}. "
                        f"Please make sure I have the 'Send Messages' permission in that channel.", 
                        ephemeral=True
                    )
                    return
                
                # Test if bot can send messages to this channel
                test_message = await raid_alert_channel.send("Testing anti-raid alert channel... ✅")
                await test_message.delete()
                print(f"AntiRaid: Successfully configured alert channel {raid_alert_channel.name} ({raid_alert_channel.id})")
            except discord.Forbidden:
                await interaction.response.send_message(
                    f"Error: I don't have permission to send messages to {raid_alert_channel.mention}. "
                    f"Please check my permissions in that channel.", 
                    ephemeral=True
                )
                return
            except Exception as e:
                await interaction.response.send_message(
                    f"Error: I cannot send messages to {raid_alert_channel.mention}. "
                    f"Error details: {str(e)}", 
                    ephemeral=True
                )
                print(f"AntiRaid: Error testing alert channel: {e}")
                return
        
        # Store configuration
        self.config[guild_id] = {
            "enabled": sensitivity > 0,
            "sensitivity": sensitivity,
            "mod_role_id": mod_role.id if mod_role else None,
            "manager_role_id": manager_role.id if manager_role else None,
            "raid_alert_channel_id": raid_alert_channel.id if raid_alert_channel else None
        }
        
        # Adjusted thresholds based on sensitivity to make them less strict
        self.thresholds = {
            1: {"ai": 15, "mute": 20},  # Low sensitivity
            2: {"ai": 10, "mute": 15},  # Medium sensitivity 
            3: {"ai": 8, "mute": 12}    # High sensitivity
        }
        
        # Save to database
        await self.save_config(guild_id)
        
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
        
        # Fixed: Removed duplicate message sending - only use one response method
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

    async def mute_user(self, user_id: int, guild_id: int, duration_minutes: int = 5, reason: str = "Raid detection") -> tuple:
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
            deleted_count = 0
            
            # Get channels where user recently spammed (from last 5 minutes)
            now = datetime.datetime.utcnow()
            cutoff = now - datetime.timedelta(minutes=5)
            
            # Track which channels this user has been active in
            active_channels = set()
            for timestamp, content, channel_id in self.user_messages.get(user_id, []):
                if timestamp > cutoff:
                    active_channels.add(channel_id)
            
            # Also add the current channel if not already included
            if hasattr(member, 'channel') and member.channel:
                active_channels.add(member.channel.id)
                
            # Only delete messages in channels where user was recently active
            for channel_id in active_channels:
                channel = guild.get_channel(channel_id)
                if not channel or not isinstance(channel, discord.TextChannel):
                    continue
                    
                # Check if bot has permission to delete messages in this channel
                if not channel.permissions_for(guild.me).manage_messages:
                    continue
                
                try:
                    # Fixed: Changed from 20 to 50 messages per channel
                    async for message in channel.history(limit=50):
                        if message.author.id == user_id:
                            # Save message info before deletion
                            deleted_messages.append({
                                "content": message.content or "[No content/attachment]",
                                "channel_id": channel.id,
                                "message_id": message.id,
                                "timestamp": message.created_at,
                                "jump_url": message.jump_url
                            })
                            
                            # Delete the message
                            await message.delete()
                            deleted_count += 1
                            
                            # Fixed: Changed from 20 to 50 messages per channel
                            if len(deleted_messages) >= 50:
                                break
                except Exception as e:
                    print(f"AntiRaid: Error deleting messages in {channel.name}: {e}")
            
            print(f"AntiRaid: Muted user {user_id} for {duration_minutes} minutes and deleted {deleted_count} messages")
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
        # Reduce base multipliers to make scoring less strict
        sensitivity_multiplier = {1: 0.6, 2: 0.8, 3: 1.0}[sensitivity]
        score = 0
        user_messages = self.user_messages.get(user_id, [])
        
        # Message characteristics
        content = message.content
        
        # Content analysis
        
        # 1. Message length
        if len(content) > 500:
            score += 2 * sensitivity_multiplier  # Long messages
        elif len(content) > 200:
            score += 1 * sensitivity_multiplier
            
        # 2. All caps
        if len(content) > 15 and content.isupper():
            score += 2 * sensitivity_multiplier
            
        # 3. Repeated characters
        for char in set(content):
            if content.count(char) > 10:
                score += 1 * sensitivity_multiplier
                break
                
        # 4. External links (higher weight)
        if "http://" in content or "https://" in content:
            link_count = content.count("http")
            score += min(link_count * 2, 6) * sensitivity_multiplier
            
        # 5. Mentions
        mention_count = len(message.mentions) + len(message.role_mentions)
        if mention_count > 5:
            score += 3 * sensitivity_multiplier
        elif mention_count > 0:
            score += mention_count * sensitivity_multiplier
        
        # 6. @everyone or @here
        if message.mention_everyone:
            score += 5 * sensitivity_multiplier
            
        # Behavior analysis (based on previous messages)
        
        # 1. Message frequency
        now = datetime.datetime.utcnow()
        recent_messages = [msg for msg in user_messages if (now - msg[0]).total_seconds() < 60]
        
        if len(recent_messages) > 10:
            score += 5 * sensitivity_multiplier  # Very high message rate
        elif len(recent_messages) > 5:
            score += 3 * sensitivity_multiplier  # High message rate
            
        # 2. Cross-channel spam
        recent_channels = set(msg[2] for msg in recent_messages)
        if len(recent_channels) > 3:
            score += 4 * sensitivity_multiplier  # Posting in many channels
            
        # 3. Content similarity
        if recent_messages:
            # Check for exact duplicates
            recent_contents = [msg[1] for msg in recent_messages]
            content_counts = Counter(recent_contents)
            
            # If same message sent multiple times
            most_common_count = content_counts.most_common(1)[0][1] if content_counts else 0
            if most_common_count > 2:
                score += most_common_count * sensitivity_multiplier
        
        return int(score)

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
            
        # Check cooldown - don't process too many messages from the same user in a short time
        now = datetime.datetime.utcnow()
        last_alert_time = self.alert_cooldowns.get(user_id)
        if last_alert_time and (now - last_alert_time).total_seconds() < self.alert_cooldown_seconds:
            # On cooldown, skip processing
            return
            
        # Track message
        self.user_messages[user_id].append((now, message.content, message.channel.id))
        
        # Calculate raid score
        raid_score = self.calculate_raid_score(user_id, message, sensitivity)
        
        # Update user's score (add to existing score for escalating behavior)
        existing_score = self.user_raid_score.get(user_id, 0)
        self.user_raid_score[user_id] = existing_score + raid_score
        total_score = self.user_raid_score[user_id]
        
        # Get thresholds for this sensitivity level
        thresholds = self.thresholds.get(sensitivity, {"ai": 15, "mute": 20})
        ai_threshold = thresholds["ai"]
        mute_threshold = thresholds["mute"]
        
        # Debug log for high scores
        if total_score > 5:
            print(f"AntiRaid: User {user_id} raid score: {total_score}/{mute_threshold}")
            
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
                        additional_score = 8 * sensitivity  # Reduced from 10
                        self.user_raid_score[user_id] = total_score + additional_score
                        total_score = self.user_raid_score[user_id]
                        print(f"AntiRaid: AI detected malicious intent ({confidence}) for user {user_id}, new score: {total_score}")
                finally:
                    self.currently_processing.remove(user_id)
        
        # If score exceeds mute threshold, take action
        if total_score >= mute_threshold:
            # Set alert cooldown to prevent multiple alerts for same user
            self.alert_cooldowns[user_id] = now
            
            # Determine mute duration based on severity (simplified)
            severity = min(1.0, (total_score - mute_threshold) / mute_threshold)
            
            # Simpler duration calculation
            base_duration_minutes = {1: 5, 2: 10, 3: 30}[sensitivity]
            max_duration_minutes = {1: 30, 2: 120, 3: 480}[sensitivity]  # 30m, 2h, 8h
            
            # Scale duration with severity, but keep it reasonable
            if severity < 0.3:
                duration_minutes = base_duration_minutes
            elif severity < 0.6:
                duration_minutes = base_duration_minutes * 2
            else:
                duration_minutes = int(base_duration_minutes + severity * (max_duration_minutes - base_duration_minutes))
            
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
                
                # Include roles if configured
                if config.get("mod_role_id"):
                    ping_mentions.append(f"<@&{config['mod_role_id']}>")
                
                # Determine if community manager should be pinged 
                if config.get("manager_role_id"):
                    ping_manager = False
                    
                    # High sensitivity: Always ping manager
                    if sensitivity == 3:
                        ping_manager = True
                    # Medium sensitivity: Only ping for longer timeouts
                    elif sensitivity == 2 and duration_minutes > base_duration_minutes * 2:
                        ping_manager = True
                    # Low sensitivity: Only ping for severe cases
                    elif sensitivity == 1 and severity > 0.7:
                        ping_manager = True
                        
                    if ping_manager:
                        ping_mentions.append(f"<@&{config['manager_role_id']}>")
                
                # Create a very concise alert for the main channel
                alert = f"⚠️ Raider <@{user_id}> timed out for {duration_minutes}m, deleted {len(deleted_messages)} msgs. {' '.join(ping_mentions)}"
                
                # Try to send concise alert to the channel (with auto-delete after 15 seconds)
                try:
                    await message.channel.send(alert, delete_after=15)
                except Exception as e:
                    print(f"AntiRaid: Error sending alert: {e}")
                
                # Send detailed alert to the dedicated alert channel if configured
                raid_alert_channel_id = config.get("raid_alert_channel_id")
                # FIXED: Removed dependency on deleted_messages - alert channel should always be notified
                if raid_alert_channel_id:
                    print(f"AntiRaid: Attempting to send alert to channel ID {raid_alert_channel_id}")
                    
                    # Try to find the alert channel directly first
                    alert_channel = guild.get_channel(raid_alert_channel_id)
                    
                    # Debug info
                    if alert_channel:
                        print(f"AntiRaid: Found alert channel {alert_channel.name} ({alert_channel.id})")
                    else:
                        print(f"AntiRaid: Direct channel lookup failed for ID {raid_alert_channel_id}, trying thread lookup")
                    
                    # If not found, try to find as a thread
                    if not alert_channel:
                        for channel in guild.text_channels:
                            try:
                                for thread in channel.threads:
                                    if thread.id == raid_alert_channel_id:
                                        alert_channel = thread
                                        print(f"AntiRaid: Found alert channel as thread {thread.name} in {channel.name}")
                                        break
                                if alert_channel:
                                    break
                            except AttributeError:
                                pass  # Not all channels have threads
                    
                    # If alert channel found, send detailed report
                    if alert_channel and isinstance(alert_channel, (discord.TextChannel, discord.Thread)):
                        try:
                            print(f"AntiRaid: Preparing to send alert to {alert_channel.name}")
                            
                            # Test permission check
                            if not alert_channel.permissions_for(guild.me).send_messages:
                                print(f"AntiRaid: ERROR - Missing send_messages permission in {alert_channel.name}")
                                return
                                
                            # Create a rich embed for the detailed alert
                            embed = discord.Embed(
                                title=f"Raid Detection: User Timed Out",
                                description=f"User <@{user_id}> (ID: {user_id}) has been timed out for {duration_minutes} minutes.",
                                color=discord.Color.red(),
                                timestamp=datetime.datetime.utcnow()
                            )
                            
                            # Add basic info fields
                            embed.add_field(name="Detection Score", value=f"{total_score}/{mute_threshold}", inline=True)
                            embed.add_field(name="Sensitivity Level", value=f"{sensitivity}", inline=True)
                            embed.add_field(name="Timeout Duration", value=f"{duration_minutes} minutes", inline=True)
                            embed.add_field(name="Detection Channel", value=message.channel.mention, inline=True)
                            embed.add_field(name="Messages Deleted", value=f"{len(deleted_messages)}", inline=True)
                            embed.add_field(name="Detection Time", value=f"<t:{int(now.timestamp())}:F>", inline=True)
                            
                            # Find unique message contents (to avoid showing duplicates)
                            unique_messages = []
                            unique_contents = set()
                            
                            # Sort messages by timestamp (newest first)
                            sorted_messages = sorted(deleted_messages, key=lambda x: x["timestamp"], reverse=True)
                            
                            # Filter for unique messages only
                            for msg in sorted_messages:
                                content = msg["content"]
                                # Use a simplified version for uniqueness check
                                simplified = content.strip().lower()[:50]
                                if simplified not in unique_contents:
                                    unique_contents.add(simplified)
                                    unique_messages.append(msg)
                                    # Only keep up to 3 unique messages
                                    if len(unique_messages) >= 3:
                                        break
                            
                            # Add message samples field (make it large and obvious)
                            if unique_messages:
                                embed.add_field(
                                    name="__Message Samples__", 
                                    value="The following are examples of messages that triggered the raid detection:", 
                                    inline=False
                                )
                                
                                # Add each unique message as its own field for better visibility
                                for i, msg in enumerate(unique_messages):
                                    channel = guild.get_channel(msg["channel_id"])
                                    channel_name = channel.name if channel else f"Unknown ({msg['channel_id']})"
                                    
                                    # Format the message content
                                    content = msg["content"]
                                    if len(content) > 1024:  # Discord embed field value limit
                                        content = content[:1020] + "..."
                                    
                                    jump_link = f"[Link to message]({msg['jump_url']})"
                                    
                                    embed.add_field(
                                        name=f"Message {i+1} in #{channel_name}", 
                                        value=f"{content}\n\n{jump_link}", 
                                        inline=False
                                    )
                            
                            # Set footer with additional info
                            embed.set_footer(text=f"Anti-Raid Protection | User ID: {user_id}")
                            
                            # Send the detailed embed to the alert channel
                            try:
                                alert_message = await alert_channel.send(
                                    content=f"**RAID ALERT:** User <@{user_id}> has been detected as a potential raider.",
                                    embed=embed
                                )
                                print(f"AntiRaid: Successfully sent detailed alert to channel {alert_channel.name}")
                                # Optional - add a reaction to confirm the message was sent
                                try:
                                    await alert_message.add_reaction("✅")
                                except:
                                    pass  # It's ok if this fails
                            except discord.Forbidden:
                                print(f"AntiRaid: ERROR - No permission to send messages to {alert_channel.name}")
                            except discord.HTTPException as he:
                                print(f"AntiRaid: HTTP error sending alert: {he.status} - {he.text}")
                            except Exception as e:
                                print(f"AntiRaid: Error sending detailed alert: {e}")
                                print(f"Error details: {str(e)}")
                    else:
                        print(f"AntiRaid: Alert channel {raid_alert_channel_id} not found or not a text channel. Guild has {len(guild.text_channels)} text channels")
                
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
