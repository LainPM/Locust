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
        
        # Set up command group for organization in Discord UI
        self.purge_group = app_commands.Group(name="purge", description="Message purge commands")
    
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
    
    # Removed prefix commands - Converted all to slash commands
    
    # SLASH COMMANDS
    
    @app_commands.command(name="purge", description="Delete a number of messages from a channel")
    @app_commands.describe(amount="Number of messages to delete (max 1000)")
    @app_commands.default_permissions(manage_messages=True)
    async def slash_purge(self, interaction: discord.Interaction, amount: int = 100):
        """Delete a specified number of messages from the channel"""
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
    
    @purge_group.command(name="user", description="Delete messages from a specific user")
    @app_commands.describe(
        user="The user whose messages to delete",
        amount="Number of messages to check (max 1000)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def purge_user(self, interaction: discord.Interaction, user: discord.Member, amount: int = 100):
        """Delete messages from a specific user"""
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
            
    @purge_group.command(name="match", description="Delete messages containing specific text")
    @app_commands.describe(
        text="The text to match",
        amount="Number of messages to check (max 100)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def purge_match(self, interaction: discord.Interaction, text: str, amount: int = 100):
        """Delete messages containing specific text"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        # Limit to 100 messages for text filters as per Dyno's approach
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, contains_text=text)
        
        if deleted:
            await self.log_purge(ctx, deleted, f"Purge match: '{text}'")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages containing '{text}'.", ephemeral=True)
        else:
            await interaction.followup.send(f"No messages containing '{text}' were found.", ephemeral=True)
            
    @purge_group.command(name="not", description="Delete messages NOT containing specific text")
    @app_commands.describe(
        text="The text to match against",
        amount="Number of messages to check (max 100)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def purge_not(self, interaction: discord.Interaction, text: str, amount: int = 100):
        """Delete messages that do not contain specific text"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        # Limit to 100 messages for text filters as per Dyno's approach
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, not_contains_text=text)
        
        if deleted:
            await self.log_purge(ctx, deleted, f"Purge not containing: '{text}'")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages not containing '{text}'.", ephemeral=True)
        else:
            await interaction.followup.send(f"No messages not containing '{text}' were found.", ephemeral=True)
            
    @purge_group.command(name="startswith", description="Delete messages starting with specific text")
    @app_commands.describe(
        text="The text that messages should start with",
        amount="Number of messages to check (max 100)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def purge_startswith(self, interaction: discord.Interaction, text: str, amount: int = 100):
        """Delete messages that start with specific text"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        # Limit to 100 messages for text filters as per Dyno's approach
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, starts_with=text)
        
        if deleted:
            await self.log_purge(ctx, deleted, f"Purge starts with: '{text}'")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages starting with '{text}'.", ephemeral=True)
        else:
            await interaction.followup.send(f"No messages starting with '{text}' were found.", ephemeral=True)
            
    @purge_group.command(name="endswith", description="Delete messages ending with specific text")
    @app_commands.describe(
        text="The text that messages should end with",
        amount="Number of messages to check (max 100)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def purge_endswith(self, interaction: discord.Interaction, text: str, amount: int = 100):
        """Delete messages that end with specific text"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        # Limit to 100 messages for text filters as per Dyno's approach
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, ends_with=text)
        
        if deleted:
            await self.log_purge(ctx, deleted, f"Purge ends with: '{text}'")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages ending with '{text}'.", ephemeral=True)
        else:
            await interaction.followup.send(f"No messages ending with '{text}' were found.", ephemeral=True)
            
    @purge_group.command(name="links", description="Delete messages containing links")
    @app_commands.describe(amount="Number of messages to check (max 100)")
    @app_commands.default_permissions(manage_messages=True)
    async def purge_links(self, interaction: discord.Interaction, amount: int = 100):
        """Delete messages containing links"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        # Limit to 100 messages for special filters
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, has_links=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge links")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages containing links.", ephemeral=True)
        else:
            await interaction.followup.send("No messages containing links were found.", ephemeral=True)
            
    @purge_group.command(name="invites", description="Delete messages containing Discord invites")
    @app_commands.describe(amount="Number of messages to check (max 100)")
    @app_commands.default_permissions(manage_messages=True)
    async def purge_invites(self, interaction: discord.Interaction, amount: int = 100):
        """Delete messages containing Discord invite links"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        # Limit to 100 messages for special filters
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, has_invites=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge invites")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages containing Discord invites.", ephemeral=True)
        else:
            await interaction.followup.send("No messages containing Discord invites were found.", ephemeral=True)
            
    @purge_group.command(name="images", description="Delete messages containing images")
    @app_commands.describe(amount="Number of messages to check (max 100)")
    @app_commands.default_permissions(manage_messages=True)
    async def purge_images(self, interaction: discord.Interaction, amount: int = 100):
        """Delete messages containing images"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        # Limit to 100 messages for special filters
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, has_images=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge images")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages containing images.", ephemeral=True)
        else:
            await interaction.followup.send("No messages containing images were found.", ephemeral=True)
            
    @purge_group.command(name="mentions", description="Delete messages containing mentions")
    @app_commands.describe(amount="Number of messages to check (max 100)")
    @app_commands.default_permissions(manage_messages=True)
    async def purge_mentions(self, interaction: discord.Interaction, amount: int = 100):
        """Delete messages containing mentions"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        # Limit to 100 messages for special filters
        amount = min(amount, 100)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, has_mentions=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge mentions")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages containing mentions.", ephemeral=True)
        else:
            await interaction.followup.send("No messages containing mentions were found.", ephemeral=True)
            
    @purge_group.command(name="embeds", description="Delete messages containing embeds")
    @app_commands.describe(amount="Number of messages to check (max 100)")
    @app_commands.default_permissions(manage_messages=True)
    async def purge_embeds(self, interaction: discord.Interaction, amount: int = 100):
        """Delete messages containing embeds"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, has_embeds=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge embeds")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages containing embeds.", ephemeral=True)
        else:
            await interaction.followup.send("No messages containing embeds were found.", ephemeral=True)
            
    @purge_group.command(name="bots", description="Delete messages sent by bots")
    @app_commands.describe(amount="Number of messages to check (max 100)")
    @app_commands.default_permissions(manage_messages=True)
    async def purge_bots(self, interaction: discord.Interaction, amount: int = 100):
        """Delete messages sent by bots"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, from_bots=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge bot messages")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages from bots.", ephemeral=True)
        else:
            await interaction.followup.send("No messages from bots were found.", ephemeral=True)
            
    @purge_group.command(name="humans", description="Delete messages sent by humans")
    @app_commands.describe(amount="Number of messages to check (max 100)")
    @app_commands.default_permissions(manage_messages=True)
    async def purge_humans(self, interaction: discord.Interaction, amount: int = 100):
        """Delete messages sent by humans (non-bots)"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, from_humans=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge human messages")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages from humans.", ephemeral=True)
        else:
            await interaction.followup.send("No messages from humans were found.", ephemeral=True)
            
    @purge_group.command(name="text", description="Delete text-only messages")
    @app_commands.describe(amount="Number of messages to check (max 100)")
    @app_commands.default_permissions(manage_messages=True)
    async def purge_text(self, interaction: discord.Interaction, amount: int = 100):
        """Delete messages containing only text (no attachments or embeds)"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, text_only=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge text-only messages")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} text-only messages.", ephemeral=True)
        else:
            await interaction.followup.send("No text-only messages were found.", ephemeral=True)
            
    @purge_group.command(name="after", description="Delete messages after a specific message ID")
    @app_commands.describe(
        message_id="The ID of the message to purge after",
        amount="Number of messages to check (max 100)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def purge_after(self, interaction: discord.Interaction, message_id: str, amount: int = 100):
        """Delete messages after a specific message ID"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        try:
            # Convert the message ID to an integer
            message_id_int = int(message_id)
            
            # Try to fetch the message to use as reference
            reference_msg = await interaction.channel.fetch_message(message_id_int)
            
            deleted = await self.handle_purge_filters(ctx, limit=amount, after_message=reference_msg)
            
            if deleted:
                await self.log_purge(ctx, deleted, f"Purge after message ID: {message_id}")
                await interaction.followup.send(f"✅ Deleted {len(deleted)} messages after the specified message.", ephemeral=True)
            else:
                await interaction.followup.send("No messages were found after the specified message.", ephemeral=True)
                
        except ValueError:
            await interaction.followup.send("Invalid message ID. Please provide a valid numeric ID.", ephemeral=True)
        except discord.NotFound:
            await interaction.followup.send("Message not found. Make sure to use a valid message ID from this channel.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to fetch that message.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"Error fetching message: {str(e)}", ephemeral=True)
            
    @purge_group.command(name="pinned", description="Delete messages excluding pinned messages")
    @app_commands.describe(amount="Number of messages to check (max 100)")
    @app_commands.default_permissions(manage_messages=True)
    async def purge_pinned(self, interaction: discord.Interaction, amount: int = 100):
        """Delete non-pinned messages (preserves pinned messages)"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, exclude_pinned=True)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge non-pinned messages")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} non-pinned messages.", ephemeral=True)
        else:
            await interaction.followup.send("No non-pinned messages were found.", ephemeral=True)
            
    @purge_group.command(name="all", description="Delete all messages including pinned")
    @app_commands.describe(amount="Number of messages to check (max 100)")
    @app_commands.default_permissions(manage_messages=True)
    async def purge_all(self, interaction: discord.Interaction, amount: int = 100):
        """Delete all messages including pinned ones"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        deleted = await self.handle_purge_filters(ctx, limit=amount, exclude_pinned=False)
        
        if deleted:
            await self.log_purge(ctx, deleted, "Purge all messages including pinned")
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages (including pinned).", ephemeral=True)
        else:
            await interaction.followup.send("No messages were found to delete.", ephemeral=True)
            
    @app_commands.command(name="clean", description="Delete the bot's messages")
    @app_commands.describe(amount="Number of messages to check (max 100)")
    @app_commands.default_permissions(manage_messages=True)
    async def clean(self, interaction: discord.Interaction, amount: int = 50):
        """Delete the bot's own messages"""
        await interaction.response.defer(ephemeral=True)
        
        ctx = await commands.Context.from_interaction(interaction)
        
        def is_bot_message(message):
            return message.author.id == self.bot.user.id and not message.pinned
        
        try:
            deleted = await interaction.channel.purge(limit=amount, check=is_bot_message)
            
            if deleted:
                await self.log_purge(ctx, deleted, "Clean bot messages")
                await interaction.followup.send(f"✅ Deleted {len(deleted)} of my messages.", ephemeral=True)
            else:
                await interaction.followup.send("No messages from me were found to delete.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to delete messages in this channel.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"Error cleaning messages: {str(e)}", ephemeral=True)

# Setup function for loading the cog
async def setup(bot):
    cog = Purge(bot)
    await bot.add_cog(cog)
    # Register the purge group with the bot
    bot.tree.add_command(cog.purge_group)
