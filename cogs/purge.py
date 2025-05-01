import discord
from discord.ext import commands
from discord import app_commands
import datetime
import asyncio
import re
from typing import Optional, Union, List, Callable

class Purge(commands.Cog):
    """Commands for bulk message deletion (purging)"""
    
    def __init__(self, bot):
        self.bot = bot
        # Store audit log entries for completed purges
        self.purge_logs = []
    
    def can_purge_message(self, message: discord.Message) -> bool:
        """Check if a message can be purged (< 14 days old)"""
        # Discord API can only bulk delete messages < 14 days old
        two_weeks_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)
        return message.created_at > two_weeks_ago
    
    async def handle_purge_filters(
        self, ctx: commands.Context, 
        limit: int = 100, 
        user: Optional[discord.Member] = None,
        contains_text: Optional[str] = None,
        not_contains_text: Optional[str] = None,
        starts_with: Optional[str] = None,
        ends_with: Optional[str] = None,
        has_links: bool = False,
        has_invites: bool = False,
        has_images: bool = False,
        has_mentions: bool = False,
        has_embeds: bool = False,
        from_bots: bool = False,
        from_humans: bool = False,
        text_only: bool = False,
        before_message: Optional[discord.Message] = None,
        after_message: Optional[discord.Message] = None,
        before_date: Optional[datetime.datetime] = None,
        after_date: Optional[datetime.datetime] = None,
        exclude_pinned: bool = True
    ) -> List[discord.Message]:
        """Handle purge with various filters"""
        
        # Limit can't be more than 1000 due to API constraints
        limit = min(limit, 1000)
        
        # Create the check function based on filters
        def check_message(message: discord.Message) -> bool:
            # Skip command message itself
            if message.id == ctx.message.id:
                return False
                
            # Skip pinned messages if exclude_pinned is True
            if exclude_pinned and message.pinned:
                return False
                
            # Skip messages older than 14 days (Discord limitation)
            if not self.can_purge_message(message):
                return False
                
            # Filter by user
            if user and message.author.id != user.id:
                return False
                
            # Filter by text content
            if contains_text and contains_text.lower() not in message.content.lower():
                return False
                
            if not_contains_text and not_contains_text.lower() in message.content.lower():
                return False
                
            if starts_with and not message.content.lower().startswith(starts_with.lower()):
                return False
                
            if ends_with and not message.content.lower().endswith(ends_with.lower()):
                return False
            
            # Filter by link presence
            if has_links:
                # Simple URL matching regex
                url_pattern = r'https?://\S+'
                if not re.search(url_pattern, message.content):
                    return False
            
            # Filter by Discord invite presence
            if has_invites:
                invite_pattern = r'discord(?:\.gg|app\.com/invite)/\S+'
                if not re.search(invite_pattern, message.content):
                    return False
            
            # Filter by image attachments
            if has_images:
                has_img = False
                for attachment in message.attachments:
                    if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                        has_img = True
                        break
                if not has_img:
                    return False
            
            # Filter by mention presence
            if has_mentions and not (message.mentions or message.role_mentions or message.mention_everyone):
                return False
            
            # Filter by embed presence
            if has_embeds and not message.embeds:
                return False
            
            # Filter bot messages
            if from_bots and not message.author.bot:
                return False
            
            # Filter human messages
            if from_humans and message.author.bot:
                return False
            
            # Filter text-only messages (no attachments or embeds)
            if text_only and (message.attachments or message.embeds):
                return False
            
            # All checks passed
            return True
        
        # Set up purge parameters
        purge_kwargs = {
            'limit': limit,
            'check': check_message,
            'before': before_message,
            'after': after_message,
        }
        
        # Add date filters if provided
        if before_date:
            purge_kwargs['before'] = before_date
        if after_date:
            purge_kwargs['after'] = after_date
            
        try:
            # Execute purge based on channel type
            # Works in normal channels, threads, and forum posts
            if isinstance(ctx.channel, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
                deleted = await ctx.channel.purge(**purge_kwargs)
                return deleted
            else:
                await ctx.send("Purge commands can only be used in text channels, threads, or forum posts.")
                return []
        except discord.Forbidden:
            await ctx.send("I don't have permission to delete messages in this channel.")
            return []
        except discord.HTTPException as e:
            await ctx.send(f"Error purging messages: {str(e)}")
            return []
    
    async def log_purge(self, ctx: commands.Context, deleted: List[discord.Message], reason: str = None) -> None:
        """Log purge operation to bot's internal history"""
        entry = {
            'timestamp': datetime.datetime.now(),
            'moderator': ctx.author.id,
            'channel': ctx.channel.id,
            'guild': ctx.guild.id,
            'deleted_count': len(deleted),
            'reason': reason or "No reason provided"
        }
        self.purge_logs.append(entry)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purge", aliases=["clear", "prune"], 
                    description="Delete a number of messages from a channel")
    async def purge(self, ctx: commands.Context, amount: int = 100):
        """Delete a specified number of messages from the channel"""
        # Delete the command message first
        await ctx.message.delete()
        
        deleted = await self.handle_purge_filters(ctx, limit=amount)
        
        if deleted:
            await self.log_purge(ctx, deleted)
            response = await ctx.send(f"✅ Deleted {len(deleted)} messages.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgeuser", aliases=["clearuser", "pruneuser"], 
                    description="Delete messages from a specific user")
    async def purge_user(self, ctx: commands.Context, user: discord.Member, amount: int = 100):
        """Delete a specified number of messages from a specific user"""
        # Delete the command message first
        await ctx.message.delete()
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, user=user)
        
        if deleted:
            await self.log_purge(ctx, deleted, f"Purge user: {user.name}")
            response = await ctx.send(f"✅ Deleted {len(deleted)} messages from {user.mention}.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgematch", aliases=["clearmatch", "prunematch"], 
                    description="Delete messages containing specific text")
    async def purge_match(self, ctx: commands.Context, text: str, amount: int = 100):
        """Delete messages that contain specific text"""
        # Delete the command message first
        await ctx.message.delete()
        
        # Limit to 100 messages for text filters as per Dyno's approach
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, contains_text=text)
        
        if deleted:
            await self.log_purge(ctx, deleted, f"Purge match: '{text}'")
            response = await ctx.send(f"✅ Deleted {len(deleted)} messages containing '{text}'.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgenot", aliases=["clearnot", "prunenot"], 
                    description="Delete messages not containing specific text")
    async def purge_not(self, ctx: commands.Context, text: str, amount: int = 100):
        """Delete messages that do not contain specific text"""
        # Delete the command message first
        await ctx.message.delete()
        
        # Limit to 100 messages for text filters as per Dyno's approach
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, not_contains_text=text)
        
        if deleted:
            await self.log_purge(ctx, deleted, f"Purge not containing: '{text}'")
            response = await ctx.send(f"✅ Deleted {len(deleted)} messages not containing '{text}'.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgestartswith", aliases=["clearstartswith", "prunestartswith"], 
                    description="Delete messages starting with specific text")
    async def purge_startswith(self, ctx: commands.Context, text: str, amount: int = 100):
        """Delete messages that start with specific text"""
        # Delete the command message first
        await ctx.message.delete()
        
        # Limit to 100 messages for text filters as per Dyno's approach
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, starts_with=text)
        
        if deleted:
            await self.log_purge(ctx, deleted, f"Purge starts with: '{text}'")
            response = await ctx.send(f"✅ Deleted {len(deleted)} messages starting with '{text}'.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgeendswith", aliases=["clearendswith", "pruneendswith"], 
                    description="Delete messages ending with specific text")
    async def purge_endswith(self, ctx: commands.Context, text: str, amount: int = 100):
        """Delete messages that end with specific text"""
        # Delete the command message first
        await ctx.message.delete()
        
        # Limit to 100 messages for text filters as per Dyno's approach
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, ends_with=text)
        
        if deleted:
            await self.log_purge(ctx, deleted, f"Purge ends with: '{text}'")
            response = await ctx.send(f"✅ Deleted {len(deleted)} messages ending with '{text}'.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgelinks", aliases=["clearlinks", "prunelinks"], 
                    description="Delete messages containing links")
    async def purge_links(self, ctx: commands.Context, amount: int = 100):
        """Delete messages containing links"""
        # Delete the command message first
        await ctx.message.delete()
        
        # Limit to 100 messages for special filters
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, has_links=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge links")
            response = await ctx.send(f"✅ Deleted {len(deleted)} messages containing links.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgeinvites", aliases=["clearinvites", "pruneinvites"], 
                    description="Delete messages containing Discord invites")
    async def purge_invites(self, ctx: commands.Context, amount: int = 100):
        """Delete messages containing Discord invite links"""
        # Delete the command message first
        await ctx.message.delete()
        
        # Limit to 100 messages for special filters
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, has_invites=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge invites")
            response = await ctx.send(f"✅ Deleted {len(deleted)} messages containing Discord invites.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgeimages", aliases=["clearimages", "pruneimages"], 
                    description="Delete messages containing images")
    async def purge_images(self, ctx: commands.Context, amount: int = 100):
        """Delete messages containing images"""
        # Delete the command message first
        await ctx.message.delete()
        
        # Limit to 100 messages for special filters
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, has_images=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge images")
            response = await ctx.send(f"✅ Deleted {len(deleted)} messages containing images.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgementions", aliases=["clearmentions", "prunementions"], 
                    description="Delete messages containing mentions")
    async def purge_mentions(self, ctx: commands.Context, amount: int = 100):
        """Delete messages containing mentions"""
        # Delete the command message first
        await ctx.message.delete()
        
        # Limit to 100 messages for special filters
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, has_mentions=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge mentions")
            response = await ctx.send(f"✅ Deleted {len(deleted)} messages containing mentions.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgeembeds", aliases=["clearembeds", "pruneembeds"], 
                    description="Delete messages containing embeds")
    async def purge_embeds(self, ctx: commands.Context, amount: int = 100):
        """Delete messages containing embeds"""
        # Delete the command message first
        await ctx.message.delete()
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, has_embeds=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge embeds")
            response = await ctx.send(f"✅ Deleted {len(deleted)} messages containing embeds.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgebots", aliases=["clearbots", "prunebots"], 
                    description="Delete messages sent by bots")
    async def purge_bots(self, ctx: commands.Context, amount: int = 100):
        """Delete messages sent by bots"""
        # Delete the command message first
        await ctx.message.delete()
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, from_bots=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge bot messages")
            response = await ctx.send(f"✅ Deleted {len(deleted)} messages from bots.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgehumans", aliases=["clearhumans", "prunehumans"], 
                    description="Delete messages sent by humans")
    async def purge_humans(self, ctx: commands.Context, amount: int = 100):
        """Delete messages sent by humans (non-bots)"""
        # Delete the command message first
        await ctx.message.delete()
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, from_humans=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge human messages")
            response = await ctx.send(f"✅ Deleted {len(deleted)} messages from humans.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgetext", aliases=["cleartext", "prunetext"], 
                    description="Delete messages containing only text")
    async def purge_text(self, ctx: commands.Context, amount: int = 100):
        """Delete messages containing only text (no attachments or embeds)"""
        # Delete the command message first
        await ctx.message.delete()
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, text_only=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge text-only messages")
            response = await ctx.send(f"✅ Deleted {len(deleted)} text-only messages.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgeafter", aliases=["clearafter", "pruneafter"], 
                    description="Delete messages after a specific message ID")
    async def purge_after(self, ctx: commands.Context, message_id: int, amount: int = 100):
        """Delete messages after a specific message ID"""
        # Delete the command message first
        await ctx.message.delete()
        
        try:
            # Try to fetch the message to use as reference
            reference_msg = await ctx.channel.fetch_message(message_id)
            
            deleted = await self.handle_purge_filters(ctx, limit=amount, after_message=reference_msg)
            
            if deleted:
                await self.log_purge(ctx, deleted, f"Purge after message ID: {message_id}")
                response = await ctx.send(f"✅ Deleted {len(deleted)} messages after the specified message.", delete_after=5)
                
        except discord.NotFound:
            await ctx.send("Message not found. Make sure to use a valid message ID from this channel.", delete_after=5)
        except discord.Forbidden:
            await ctx.send("I don't have permission to fetch that message.", delete_after=5)
        except discord.HTTPException as e:
            await ctx.send(f"Error fetching message: {str(e)}", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgepinned", aliases=["clearpinned", "prunepinned"], 
                    description="Delete messages excluding pinned messages")
    async def purge_pinned(self, ctx: commands.Context, amount: int = 100):
        """Delete non-pinned messages (preserves pinned messages)"""
        # Delete the command message first
        await ctx.message.delete()
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, exclude_pinned=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge non-pinned messages")
            response = await ctx.send(f"✅ Deleted {len(deleted)} non-pinned messages.", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="purgeall", aliases=["clearall", "pruneall"], 
                    description="Delete all messages including pinned")
    async def purge_all(self, ctx: commands.Context, amount: int = 100):
        """Delete all messages including pinned ones"""
        # Delete the command message first
        await ctx.message.delete()
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, exclude_pinned=False)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge all messages including pinned")
            response = await ctx.send(f"✅ Deleted {len(deleted)} messages (including pinned).", delete_after=5)
    
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name="clean", aliases=["cleanbot"], 
                    description="Delete the bot's messages")
    async def clean(self, ctx: commands.Context, amount: int = 50):
        """Delete the bot's own messages"""
        # Delete the command message first
        await ctx.message.delete()
        
        def is_bot_message(message):
            return message.author.id == self.bot.user.id and not message.pinned
        
        try:
            deleted = await ctx.channel.purge(limit=amount, check=is_bot_message)
            
            if deleted:
                await self.log_purge(ctx, deleted, "Clean bot messages")
                response = await ctx.send(f"✅ Deleted {len(deleted)} of my messages.", delete_after=5)
        except discord.Forbidden:
            await ctx.send("I don't have permission to delete messages in this channel.")
        except discord.HTTPException as e:
            await ctx.send(f"Error cleaning messages: {str(e)}")
    
    # Adding slash command versions of the purge commands
    
    @app_commands.command(name="purge", description="Delete a number of messages from a channel")
    @app_commands.describe(amount="Number of messages to delete (max 1000)")
    @app_commands.default_permissions(manage_messages=True)
    async def slash_purge(self, interaction: discord.Interaction, amount: int = 100):
        """Delete a specified number of messages from the channel (slash command)"""
        # Need to defer since operation might take time
        await interaction.response.defer(ephemeral=True)
        
        # Create a Context-like object for compatibility
        ctx = await commands.Context.from_interaction(interaction)
        
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.followup.send("You don't have permission to manage messages.", ephemeral=True)
            return
            
        if not interaction.guild.me.guild_permissions.manage_messages:
            await interaction.followup.send("I don't have permission to delete messages.", ephemeral=True)
            return
        
        deleted = await self.handle_purge_filters(ctx, limit=amount)
        
        if deleted:
            await self.log_purge(ctx, deleted)
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)
        else:
            await interaction.followup.send("No messages were deleted.", ephemeral=True)
    
    @app_commands.command(name="purgeuser", description="Delete messages from a specific user")
    @app_commands.describe(
        user="The user whose messages to delete",
        amount="Number of messages to check (max 1000)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def slash_purge_user(self, interaction: discord.Interaction, user: discord.Member, amount: int = 100):
        """Delete messages from a specific user (slash command)"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.followup.send("You don't have permission to manage messages.", ephemeral=True)
            return
            
        if not interaction.guild.me.guild_permissions.manage_messages:
            await interaction.followup.send("I don't have permission to delete messages.", ephemeral=True)
            return
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, user=user)
        
        if deleted:
            await self.log_purge(ctx, deleted, f"Purge user: {user.name}")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages from {user.mention}.", ephemeral=True)
        else:
            await interaction.followup.send(f"No messages from {user.mention} were deleted.", ephemeral=True)

# Setup function for loading the cog
async def setup(bot):
    await bot.add_cog(Purge(bot))
