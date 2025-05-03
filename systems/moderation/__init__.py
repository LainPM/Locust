# systems/moderation/__init__.py
from systems.base_system import System
from .filter import ContentFilter
from .anti_raid import RaidProtection
from .anti_spam import SpamProtection
from .punishment import PunishmentManager

class ModerationSystem(System):
    """Comprehensive content moderation system"""
    
    def __init__(self, bot):
        super().__init__(bot)
        
        # Components
        self.filter = ContentFilter(self)
        self.raid_protection = RaidProtection(self)
        self.spam_protection = SpamProtection(self)
        self.punishments = PunishmentManager(self)
        
        # Settings cache
        self.filter_settings_cache = {}  # Guild ID -> settings
        self.raid_settings_cache = {}    # Guild ID -> settings
        
        # Shared resources - caches and trackers
        self.message_cache = {}          # User ID -> list of recent messages
        self.violation_counts = {}       # Guild ID -> User ID -> violation count
        self.processing_users = set()    # Users currently being processed
        self.muted_users = {}            # User ID -> unmute time
        
    async def initialize(self):
        """Initialize the moderation system"""
        # Register event handlers with high priority
        self.register_event("on_message", self.process_message, priority=90)
        self.register_event("on_member_join", self.raid_protection.process_member_join, priority=90)
        
        # Load settings from database for all guilds
        await self.load_settings()
        
        # Initialize components
        await self.filter.initialize()
        await self.raid_protection.initialize()
        await self.spam_protection.initialize()
        await self.punishments.initialize()
        
        # Start background cleanup task
        self.bot.loop.create_task(self.cleanup_task())
        
        print("Content Moderation system initialized")
    
    async def load_settings(self):
        """Load settings from database"""
        # Load filter settings
        filter_collection = self.bot.db["filter_settings"]
        async for doc in filter_collection.find({}):
            guild_id = doc["guild_id"]
            self.filter_settings_cache[guild_id] = doc
        
        # Load raid settings
        raid_collection = self.bot.db["raid_settings"]
        async for doc in raid_collection.find({}):
            guild_id = doc["guild_id"]
            self.raid_settings_cache[guild_id] = doc
        
        print(f"Loaded moderation settings for {len(self.filter_settings_cache)} guilds")
    
    async def get_filter_settings(self, guild_id: int):
        """Get filter settings for a guild"""
        if guild_id not in self.filter_settings_cache:
            settings = await self.filter.load_settings(guild_id)
            self.filter_settings_cache[guild_id] = settings
        
        return self.filter_settings_cache[guild_id]
    
    async def get_raid_settings(self, guild_id: int):
        """Get raid protection settings for a guild"""
        if guild_id not in self.raid_settings_cache:
            settings = await self.raid_protection.load_settings(guild_id)
            self.raid_settings_cache[guild_id] = settings
        
        return self.raid_settings_cache[guild_id]
    
    async def process_message(self, message):
        """Central message processor for all moderation components"""
        # Skip bot messages and DMs
        if message.author.bot or not message.guild:
            return True
            
        # Skip if user is a guild administrator
        if message.author.guild_permissions.administrator:
            return True
            
        # Add to message cache for tracking
        user_id = message.author.id
        guild_id = message.guild.id
        
        if user_id not in self.message_cache:
            self.message_cache[user_id] = []
            
        # Add message to cache with timestamp
        self.message_cache[user_id].append({
            "content": message.content,
            "channel_id": message.channel.id,
            "guild_id": guild_id,
            "timestamp": message.created_at
        })
        
        # Check filter first (blacklist/whitelist)
        if not await self.filter.check_message(message):
            return False  # Message was filtered, stop propagation
            
        # Check for spam patterns
        if not await self.spam_protection.check_message(message):
            return False  # Message was flagged as spam, stop propagation
            
        # Check for raid patterns
        if not await self.raid_protection.check_message(message):
            return False  # Message was flagged as part of a raid, stop propagation
            
        # Message passed all checks
        return True
    
    async def increment_violation(self, guild_id: int, user_id: int, violation_type: str, evidence: str = None):
        """Increment violation count and check for punishment threshold"""
        # Initialize user in violation tracking
        if guild_id not in self.violation_counts:
            self.violation_counts[guild_id] = {}
            
        if user_id not in self.violation_counts[guild_id]:
            self.violation_counts[guild_id][user_id] = {
                "count": 0,
                "timestamps": [],
                "types": []
            }
            
        # Add violation
        self.violation_counts[guild_id][user_id]["count"] += 1
        self.violation_counts[guild_id][user_id]["timestamps"].append(datetime.datetime.utcnow().isoformat())
        self.violation_counts[guild_id][user_id]["types"].append(violation_type)
        
        violation_count = self.violation_counts[guild_id][user_id]["count"]
        
        # Store in database
        await self.bot.db["user_violations"].update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {
                "violation_count": violation_count,
                "timestamps": self.violation_counts[guild_id][user_id]["timestamps"],
                "violation_types": self.violation_counts[guild_id][user_id]["types"],
                "last_violation": datetime.datetime.utcnow().isoformat(),
                "last_violation_type": violation_type,
                "last_evidence": evidence
            }},
            upsert=True
        )
        
        # Check if punishment threshold reached
        await self.punishments.check_for_punishment(guild_id, user_id, violation_count, violation_type)
        
        return violation_count
    
    async def cleanup_task(self):
        """Background task to clean up old message data and process unmutes"""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            try:
                now = datetime.datetime.utcnow()
                
                # Clear old messages (older than 10 minutes)
                for user_id in list(self.message_cache.keys()):
                    self.message_cache[user_id] = [
                        msg for msg in self.message_cache[user_id]
                        if (now - msg["timestamp"]).total_seconds() < 600
                    ]
                    
                    # Remove users with no recent messages
                    if not self.message_cache[user_id]:
                        del self.message_cache[user_id]
                
                # Check for users to unmute
                for user_id in list(self.muted_users.keys()):
                    unmute_time = self.muted_users[user_id]
                    if now >= unmute_time:
                        await self.punishments.unmute_user(user_id)
                
                # Wait before next cleanup cycle
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break  # Exit cleanly on cancel
            except Exception as e:
                print(f"Error in moderation cleanup task: {e}")
                await asyncio.sleep(60)  # Still wait before retry
