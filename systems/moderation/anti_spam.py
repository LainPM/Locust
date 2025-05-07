# systems/moderation/anti_spam.py
import discord
import datetime
import asyncio
from collections import Counter
from typing import Dict, List, Set, Any, Tuple

class SpamProtection:
    """Anti-spam component for content moderation"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        
        # Default thresholds
        self.default_thresholds = {
            "message_rate": 5,     # Max messages per 5 seconds
            "duplicate_limit": 3,  # Max duplicate messages in 30 seconds
            "mention_limit": 5,    # Max mentions per message
            "character_spam": 10,  # Max repeated characters
            "emoji_limit": 6,      # Max emojis per message
        }
    
    async def initialize(self):
        """Initialize the anti-spam component"""
        # Nothing to initialize here currently
        pass
    
    async def check_message(self, message: discord.Message) -> bool:
        """
        Check if message is spam
        Returns True if message passes checks, False if it's spam
        """
        user_id = message.author.id
        guild_id = message.guild.id
        content = message.content
        
        # Get guild-specific thresholds
        thresholds = await self._get_thresholds(guild_id)
        
        # Check message rate
        rate_check = await self._check_message_rate(user_id, guild_id, thresholds)
        if not rate_check:
            await self._handle_spam(message, "message_rate", "Sending messages too quickly")
            return False
        
        # Check for duplicate messages
        if len(content) > 5:  # Only check non-trivial messages
            duplicate_check = await self._check_duplicates(user_id, content, thresholds)
            if not duplicate_check:
                await self._handle_spam(message, "duplicate_messages", "Sending duplicate messages")
                return False
        
        # Check for mention spam
        if message.mentions or message.role_mentions:
            mention_count = len(message.mentions) + len(message.role_mentions)
            if mention_count > thresholds["mention_limit"]:
                await self._handle_spam(message, "mention_spam", f"Message contains {mention_count} mentions")
                return False
        
        # Check for character spam
        if len(content) > 10:  # Only check non-trivial messages
            char_spam = self._check_character_spam(content, thresholds)
            if char_spam:
                await self._handle_spam(message, "character_spam", f"Message contains character spam: '{char_spam}'")
                return False
        
        # Check for emoji spam
        emoji_count = self._count_emojis(content)
        if emoji_count > thresholds["emoji_limit"]:
            await self._handle_spam(message, "emoji_spam", f"Message contains {emoji_count} emojis")
            return False
        
        # All checks passed
        return True
    
    async def _get_thresholds(self, guild_id: int) -> Dict[str, int]:
        """Get spam thresholds for a guild, with defaults if not specified"""
        settings = await self.bot.db["spam_settings"].find_one({"guild_id": guild_id})
        
        if not settings:
            return self.default_thresholds.copy()
        
        # Merge with defaults
        thresholds = self.default_thresholds.copy()
        for key in thresholds:
            if key in settings:
                thresholds[key] = settings[key]
        
        return thresholds
    
    async def _check_message_rate(self, user_id: int, guild_id: int, thresholds: Dict[str, int]) -> bool:
        """Check if user is sending messages too quickly"""
        if user_id not in self.system.message_cache:
            return True
        
        # Get recent messages in this guild
        now = datetime.datetime.utcnow()
        recent_messages = [
            msg for msg in self.system.message_cache[user_id]
            if msg["guild_id"] == guild_id and (now - msg["timestamp"]).total_seconds() < 5
        ]
        
        # Check if too many messages in short time
        return len(recent_messages) <= thresholds["message_rate"]
    
    async def _check_duplicates(self, user_id: int, content: str, thresholds: Dict[str, int]) -> bool:
        """Check if user is sending duplicate messages"""
        if user_id not in self.system.message_cache or len(content) < 10:
            return True
        
        # Get recent messages
        now = datetime.datetime.utcnow()
        recent_messages = [
            msg for msg in self.system.message_cache[user_id]
            if (now - msg["timestamp"]).total_seconds() < 30
        ]
        
        # Count identical content
        content_lower = content.lower()
        duplicate_count = sum(1 for msg in recent_messages if msg["content"].lower() == content_lower)
        
        return duplicate_count <= thresholds["duplicate_limit"]
    
    def _check_character_spam(self, content: str, thresholds: Dict[str, int]) -> str:
        """Check for repeated character spam"""
        # Ignore very short messages
        if len(content) < 10:
            return ""
        
        # Simple check for character repetition
        for char in set(content):
            if content.count(char) > thresholds["character_spam"]:
                return char * min(5, content.count(char))
        
        return ""
    
    def _count_emojis(self, content: str) -> int:
        """Count emojis in a message"""
        # Simple regex to catch most common emojis and custom emojis
        emoji_patterns = [
            r'[\U0001F000-\U0001F9FF]',  # Unicode emojis
            r'<a?:\w+:\d+>'  # Custom Discord emojis
        ]
        
        emoji_count = 0
        for pattern in emoji_patterns:
            emoji_count += len(re.findall(pattern, content))
        
        return emoji_count
    
    async def _handle_spam(self, message: discord.Message, spam_type: str, evidence: str):
        """Handle a detected spam message"""
        guild_id = message.guild.id
        user_id = message.author.id
        
        # Try to delete the message
        try:
            await message.delete()
        except Exception as e:
            print(f"Failed to delete spam message: {e}")
        
        # Track violation
        await self.system.increment_violation(guild_id, user_id, f"spam_{spam_type}", evidence)
        
        # Notify in channel
        try:
            await message.channel.send(
                f"{message.author.mention}, please don't spam. ({spam_type.replace('_', ' ')})",
                delete_after=5
            )
        except Exception:
            pass  # Can't notify
