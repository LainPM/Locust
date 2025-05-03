# systems/moderation/purge.py
import discord
import datetime
import re
from typing import List, Callable, Optional

class PurgeHandler:
    """Handler for message deletion and purging"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        
        # Store audit log entries for completed purges
        self.purge_logs = []
    
    def can_purge_message(self, message: discord.Message) -> bool:
        """Check if a message can be purged (< 14 days old)"""
        # Discord API can only bulk delete messages < 14 days old
        two_weeks_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)
        return message.created_at > two_weeks_ago
    
    async def delete_messages(
        self,
        channel: discord.TextChannel,
        limit: int = 100,
        reason: str = None,
        check: Optional[Callable] = None,
        before: Optional[discord.Message] = None,
        after: Optional[discord.Message] = None,
        exclude_pinned: bool = True
    ) -> List[discord.Message]:
        """Delete messages from a channel"""
        # Limit can't be more than 1000 due to API constraints
        limit = min(limit, 1000)
        
        # Default check function
        if check is None:
            def check_message(message: discord.Message) -> bool:
                # Skip pinned messages if exclude_pinned is True
                if exclude_pinned and message.pinned:
                    return False
                    
                # Skip messages older than 14 days (Discord limitation)
                if not self.can_purge_message(message):
                    return False
                    
                return True
        else:
            original_check = check
            def check_message(message: discord.Message) -> bool:
                # Apply the original check first
                if not original_check(message):
                    return False
                    
                # Then apply standard checks
                if exclude_pinned and message.pinned:
                    return False
                    
                if not self.can_purge_message(message):
                    return False
                    
                return True
        
        try:
            # Execute purge based on channel type
            if isinstance(channel, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
                deleted = await channel.purge(
                    limit=limit,
                    check=check_message,
                    before=before,
                    after=after,
                    reason=reason
                )
                
                # Log the purge
                self._log_purge(channel.guild.id, channel.id, len(deleted), reason)
                
                return deleted
            else:
                print(f"Purge failed: Channel type {type(channel)} not supported")
                return []
        except discord.Forbidden:
            print(f"Purge failed: Missing permissions in channel {channel.id}")
            return []
        except discord.HTTPException as e:
            print(f"Purge failed: HTTP error: {e}")
            return []
    
    async def delete_user_messages(
        self,
        channel: discord.TextChannel,
        user: discord.Member,
        limit: int = 100,
        reason: str = None
    ) -> List[discord.Message]:
        """Delete messages from a specific user"""
        def check_user(message: discord.Message) -> bool:
            return message.author.id == user.id
            
        return await self.delete_messages(
            channel,
            limit=limit,
            reason=reason,
            check=check_user
        )
    
    def _log_purge(self, guild_id: int, channel_id: int, count: int, reason: str = None) -> None:
        """Log purge operation to bot's internal history"""
        entry = {
            'timestamp': datetime.datetime.now(),
            'guild_id': guild_id,
            'channel_id': channel_id,
            'deleted_count': count,
            'reason': reason or "No reason provided"
        }
        self.purge_logs.append(entry)
        
        # Also log to database if available
        if self.bot.db:
            try:
                self.bot.db["purge_logs"].insert_one(entry)
            except Exception as e:
                print(f"Error logging purge to database: {e}")
