# systems/starboard/processor.py
import discord
import asyncio
import datetime
import io
from typing import Dict, List, Set, Any

class StarboardProcessor:
    """Processor component for the Starboard system"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        
        # Track posts to avoid duplicates
        self.processed_messages = set()
    
    async def process_message(self, message: discord.Message):
        """Process new messages in showcase channels"""
        if message.author.bot or not message.guild:
            return True  # Continue event propagation
        
        # Get guild settings
        guild_id = message.guild.id
        settings = await self.system.get_settings(guild_id)
        
        # Check if starboard is enabled
        if not settings.get("enabled", False):
            return True
        
        # Check if this is a showcase channel
        showcase_channels = settings.get("showcase_channels", [])
        if message.channel.id not in showcase_channels:
            return True
        
        # Check attachments setting
        attachments_only = settings.get("attachments_only", False)
        if attachments_only and len(message.attachments) == 0:
            return True
        
        # Add the bot's reaction if enabled
        bot_react = settings.get("bot_react", True)
        if bot_react:
            star_emoji = settings.get("star_emoji", "⭐")
            try:
                await message.add_reaction(star_emoji)
            except Exception as e:
                print(f"Failed to add reaction: {e}")
        
        # Create a thread if auto_threads is enabled
        auto_threads = settings.get("auto_threads", False)
        if auto_threads:
            try:
                thread_name = f"Discussion: {message.content[:40]}..." if message.content else f"Discussion: Post by {message.author.display_name}"
                await message.create_thread(name=thread_name[:100], auto_archive_duration=1440)  # 24 hours
            except Exception as e:
                print(f"Failed to create thread: {e}")
        
        # Create initial entry in database
        post_data = {
            "guild_id": guild_id,
            "channel_id": message.channel.id,
            "message_id": message.id,
            "author_id": message.author.id,
            "star_count": 0,
            "featured": False,
            "created_at": datetime.datetime.now()
        }
        
        await self.system.storage.add_post(post_data)
        return True
    
    async def process_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Process added reactions"""
        # Skip bot reactions and DMs
        if user.bot or not reaction.message.guild:
            return True
        
        message = reaction.message
        guild_id = message.guild.id
        
        # Get settings
        settings = await self.system.get_settings(guild_id)
        
        # Check if this is a showcase channel
        showcase_channels = settings.get("showcase_channels", [])
        if message.channel.id not in showcase_channels:
            return True
        
        # Check if this is the star emoji
        star_emoji = settings.get("star_emoji", "⭐")
        if str(reaction.emoji) != star_emoji:
            return True
        
        # Check if user is reacting to their own message
        if user.id == message.author.id:
            # Remove their reaction
            try:
                await reaction.remove(user)
                print(f"Removed self-reaction from post: {message.id}")
            except Exception as e:
                print(f"Error removing self-reaction: {e}")
            return True
        
        # Count stars (excluding author and bots)
        star_count = 0
        for r in message.reactions:
            if str(r.emoji) == star_emoji:
                users = []
                async for u in r.users():
                    if not u.bot and u.id != message.author.id:
                        users.append(u)
                star_count = len(users)
                break
        
        # Update star count in database
        post = await self.system.storage.get_post(guild_id, message.channel.id, message.id)
        
        if post:
            # Update star count
            await self.system.storage.update_post_star_count(post["_id"], star_count)
        else:
            # Create new entry
            post_data = {
                "guild_id": guild_id,
                "channel_id": message.channel.id,
                "message_id": message.id,
                "author_id": message.author.id,
                "star_count": star_count,
                "featured": False,
                "created_at": datetime.datetime.now()
            }
            await self.system.storage.add_post(post_data)
        
        return True
    
    async def process_reaction_remove(self, reaction: discord.Reaction, user: discord.User):
        """Process removed reactions"""
        # Skip bot reactions and DMs
        if user.bot or not reaction.message.guild:
            return True
        
        message = reaction.message
        guild_id = message.guild.id
        
        # Get settings
        settings = await self.system.get_settings(guild_id)
        
        # Check if this is a showcase channel
        showcase_channels = settings.get("showcase_channels", [])
        if message.channel.id not in showcase_channels:
            return True
        
        # Check if this is the star emoji
        star_emoji = settings.get("star_emoji", "⭐")
        if str(reaction.emoji) != star_emoji:
            return True
        
        # Count stars again after removal
        star_count = 0
        for r in message.reactions:
            if str(r.emoji) == star_emoji:
                users = []
                async for u in r.users():
                    if not u.bot and u.id != message.author.id:
                        users.append(u)
                star_count = len(users)
                break
        
        # Update star count in database
        post = await self.system.storage.get_post(guild_id, message.channel.id, message.id)
        
        if post:
            await self.system.storage.update_post_star_count(post["_id"], star_count)
        
        return True
    
    async def check_reactions_task(self, guild_id: int):
        """Background task to check for posts that need to be featured"""
        try:
            await self.bot.wait_until_ready()
            
            while not self.bot.is_closed():
                # Get settings
                settings = await self.system.get_settings(guild_id)
                
                # Skip if not configured or disabled
                if not settings or not settings.get("enabled", False):
                    await asyncio.sleep(30)
                    continue
                
                # Get the guild
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    await asyncio.sleep(30)
                    continue
                
                # Get featured channel
                featured_channel_id = settings.get("featured_channel_id")
                if not featured_channel_id:
                    await asyncio.sleep(30)
                    continue
                
                featured_channel = guild.get_channel(int(featured_channel_id))
                if not featured_channel:
                    await asyncio.sleep(30)
                    continue
                
                # Get threshold
                threshold = settings.get("threshold", 3)
                star_emoji = settings.get("star_emoji", "⭐")
                
                # Get posts that reached the threshold but aren't featured yet
                pending_posts = await self.system.storage.get_pending_posts(guild_id, threshold)
                
                for post in pending_posts:
                    try:
                        # Get the message
                        channel = guild.get_channel(post["channel_id"])
                        if not channel:
                            await self.system.storage.delete_post(post["_id"])
                            continue
                        
                        message = await channel.fetch_message(post["message_id"])
                        
                        # Create the embed
                        embed = await self.system.renderer.create_starboard_embed(message, post["star_count"])
                        
                        # Copy all attachments
                        files = []
                        for attachment in message.attachments:
                            try:
                                file_bytes = await attachment.read()
                                files.append(discord.File(
                                    fp=io.BytesIO(file_bytes),
                                    filename=attachment.filename,
                                    description=attachment.description
                                ))
                            except Exception as e:
                                print(f"Failed to copy attachment: {e}")
                        
                        # Send the featured post
                        content = f"⭐ **{post['star_count']}** | {channel.mention} | {message.author.mention}"
                        
                        featured_message = None
                        if files:
                            featured_message = await featured_channel.send(content=content, embed=embed, files=files)
                        else:
                            featured_message = await featured_channel.send(content=content, embed=embed)
                        
                        # Mark as featured in the database
                        await self.system.storage.mark_post_featured(post["_id"], featured_message.id)
                        
                        print(f"Featured post {message.id} with {post['star_count']} stars")
                        
                    except Exception as e:
                        print(f"Error featuring post: {e}")
                        continue
                
                # Update star counts for featured posts
                featured_posts = await self.system.storage.get_featured_posts(guild_id)
                
                for post in featured_posts:
                    try:
                        # Check if the original message still exists
                        channel = guild.get_channel(post["channel_id"])
                        if not channel:
                            await self.system.storage.delete_post(post["_id"])
                            continue
                        
                        message = await channel.fetch_message(post["message_id"])
                        
                        # Count stars
                        star_count = 0
                        for reaction in message.reactions:
                            if str(reaction.emoji) == star_emoji:
                                users = []
                                async for user in reaction.users():
                                    if not user.bot and user.id != message.author.id:
                                        users.append(user)
                                star_count = len(users)
                                break
                        
                        # Update if count changed
                        if star_count != post["star_count"]:
                            # Update featured message
                            try:
                                featured_message = await featured_channel.fetch_message(post["featured_message_id"])
                                new_content = f"⭐ **{star_count}** | {channel.mention} | {message.author.mention}"
                                await featured_message.edit(content=new_content)
                                
                                # Update database
                                await self.system.storage.update_post_star_count(post["_id"], star_count)
                            except Exception as e:
                                print(f"Error updating featured message: {e}")
                                # If message was deleted, unmark as featured
                                await self.system.storage.unmark_post_featured(post["_id"])
                    except Exception as e:
                        print(f"Error updating featured post: {e}")
                        # If original message was deleted, remove the post
                        await self.system.storage.delete_post(post["_id"])
                
                # Sleep between checks to avoid rate limits
                await asyncio.sleep(30)
                
        except asyncio.CancelledError:
            # Task was cancelled gracefully
            print(f"Starboard task for guild {guild_id} was cancelled")
        except Exception as e:
            print(f"Error in starboard task for guild {guild_id}: {e}")
