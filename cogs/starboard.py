# cogs/starboard.py
import discord
from discord.ext import commands
from discord import app_commands
import datetime
import asyncio
from typing import Optional, List

class Starboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Create references to MongoDB collections
        self.starboard_settings = bot.db["starboard_settings"]
        self.starboard_posts = bot.db["starboard_posts"]
        
        # Start the reaction checking task
        self.reaction_task = self.bot.loop.create_task(self.check_reactions())
    
    def cog_unload(self):
        # Cancel the task when the cog is unloaded
        if self.reaction_task:
            self.reaction_task.cancel()
    
    async def check_reactions(self):
        """Task to periodically check for posts that have crossed the reaction threshold"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                # Get all server settings
                cursor = self.starboard_settings.find({})
                async for server_settings in cursor:
                    guild_id = server_settings.get("guild_id")
                    featured_channel_id = server_settings.get("featured_channel_id")
                    
                    # Skip if no featured channel is set
                    if not featured_channel_id:
                        continue
                    
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        continue
                    
                    featured_channel = guild.get_channel(featured_channel_id)
                    if not featured_channel:
                        continue
                    
                    # Get tracked channels
                    showcase_channels = server_settings.get("showcase_channels", [])
                    threshold = server_settings.get("threshold", 3)
                    star_emoji = server_settings.get("star_emoji", "⭐")
                    
                    # Check for deleted messages and clean up database
                    post_cursor = self.starboard_posts.find({"guild_id": guild_id})
                    async for post in post_cursor:
                        channel_id = post["channel_id"]
                        channel = guild.get_channel(channel_id)
                        
                        if not channel:
                            # Channel deleted, remove post
                            await self.starboard_posts.delete_one({"_id": post["_id"]})
                            continue
                        
                        try:
                            message = await channel.fetch_message(post["message_id"])
                        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                            # Message deleted, remove post
                            await self.starboard_posts.delete_one({"_id": post["_id"]})
                            continue
                    
                    # Get posts that reached the threshold but aren't featured yet
                    pending_posts = self.starboard_posts.find({
                        "guild_id": guild_id,
                        "featured": False,
                        "star_count": {"$gte": threshold}
                    })
                    
                    async for post in pending_posts:
                        try:
                            channel = guild.get_channel(post["channel_id"])
                            if not channel:
                                await self.starboard_posts.delete_one({"_id": post["_id"]})
                                continue
                                
                            message = await channel.fetch_message(post["message_id"])
                            
                            # Create and send the featured post
                            embed = discord.Embed(
                                description=message.content,
                                color=discord.Color.gold(),
                                timestamp=message.created_at
                            )
                            
                            embed.set_author(
                                name=message.author.display_name,
                                icon_url=message.author.display_avatar.url
                            )
                            
                            embed.add_field(name="Original", value=f"[Jump to message]({message.jump_url})", inline=False)
                            embed.set_footer(text=f"ID: {message.id}")
                            
                            # If the message has an image attachment, add it to the embed
                            if message.attachments:
                                for attachment in message.attachments:
                                    if attachment.content_type and attachment.content_type.startswith('image/'):
                                        embed.set_image(url=attachment.url)
                                        break
                            
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
                            content = f"⭐ **{post['star_count']}** | {message.channel.mention} | {message.author.mention}"
                            
                            if files:
                                featured_message = await featured_channel.send(content=content, embed=embed, files=files)
                            else:
                                featured_message = await featured_channel.send(content=content, embed=embed)
                            
                            # Mark as featured in the database
                            await self.starboard_posts.update_one(
                                {"_id": post["_id"]},
                                {"$set": {
                                    "featured": True,
                                    "featured_message_id": featured_message.id
                                }}
                            )
                            
                            print(f"Featured post {message.id} with {post['star_count']} stars")
                            
                        except Exception as e:
                            print(f"Error featuring post: {e}")
                            continue
                    
                    # Update star counts for featured posts
                    featured_posts = self.starboard_posts.find({
                        "guild_id": guild_id,
                        "featured": True
                    })
                    
                    async for post in featured_posts:
                        try:
                            # Check if the original message still exists
                            channel = guild.get_channel(post["channel_id"])
                            if not channel:
                                await self.starboard_posts.delete_one({"_id": post["_id"]})
                                continue
                                
                            message = await channel.fetch_message(post["message_id"])
                            
                            # Count stars (excluding author's reaction)
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
                                    new_content = f"⭐ **{star_count}** | {message.channel.mention} | {message.author.mention}"
                                    await featured_message.edit(content=new_content)
                                    
                                    # Update database
                                    await self.starboard_posts.update_one(
                                        {"_id": post["_id"]},
                                        {"$set": {"star_count": star_count}}
                                    )
                                    
                                    print(f"Updated star count for post {message.id} to {star_count}")
                                    
                                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                                    # Featured message was deleted
                                    await self.starboard_posts.update_one(
                                        {"_id": post["_id"]},
                                        {"$set": {
                                            "featured": False,
                                            "featured_message_id": None
                                        }}
                                    )
                        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                            # Original message was deleted
                            await self.starboard_posts.delete_one({"_id": post["_id"]})
                            continue
                
            except asyncio.CancelledError:
                # Task was cancelled
                break
            except Exception as e:
                print(f"Error in starboard task: {e}")
            
            # Check every 30 seconds
            await asyncio.sleep(30)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle new messages in showcase channels"""
        try:
            # Ignore bot messages
            if message.author.bot:
                return
            
            # Ignore DMs
            if not message.guild:
                return
            
            # Get server settings
            server_settings = await self.starboard_settings.find_one({"guild_id": message.guild.id})
            if not server_settings:
                return
            
            # Check if this is a showcase channel
            showcase_channels = server_settings.get("showcase_channels", [])
            if message.channel.id not in showcase_channels:
                return
            
            print(f"Detected new post in showcase channel: {message.id}")
            
            # Check attachments setting
            attachments_only = server_settings.get("attachments_only", False)
            if attachments_only and len(message.attachments) == 0:
                return
            
            # Add the bot's reaction if enabled
            bot_react = server_settings.get("bot_react", True)
            if bot_react:
                star_emoji = server_settings.get("star_emoji", "⭐")
                try:
                    await message.add_reaction(star_emoji)
                    print(f"Added reaction to post: {message.id}")
                except Exception as e:
                    print(f"Failed to add reaction: {e}")
            
            # Create a thread if auto_threads is enabled
            auto_threads = server_settings.get("auto_threads", False)
            if auto_threads:
                try:
                    thread_name = f"Discussion: {message.content[:40]}..." if message.content else f"Discussion: Post by {message.author.display_name}"
                    await message.create_thread(name=thread_name[:100], auto_archive_duration=1440)  # 24 hours
                    print(f"Created thread for post: {message.id}")
                except Exception as e:
                    print(f"Failed to create thread: {e}")
            
            # Create initial entry in database
            post_data = {
                "guild_id": message.guild.id,
                "channel_id": message.channel.id,
                "message_id": message.id,
                "author_id": message.author.id,
                "star_count": 0,
                "featured": False,
                "created_at": datetime.datetime.now()
            }
            
            result = await self.starboard_posts.insert_one(post_data)
            print(f"Added post to database: {message.id}, result: {result.inserted_id}")
            
        except Exception as e:
            print(f"Error processing message: {e}")
    
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handle when a reaction is added to a message"""
        try:
            # Ignore bot reactions
            if payload.member and payload.member.bot:
                return
            
            # Get server settings
            server_settings = await self.starboard_settings.find_one({"guild_id": payload.guild_id})
            if not server_settings:
                return
            
            # Check if this is a showcase channel
            showcase_channels = server_settings.get("showcase_channels", [])
            if payload.channel_id not in showcase_channels:
                return
            
            # Check if this is the star emoji
            star_emoji = server_settings.get("star_emoji", "⭐")
            if str(payload.emoji) != star_emoji:
                return
            
            # Get the message
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                return
            
            channel = guild.get_channel(payload.channel_id)
            if not channel:
                return
            
            try:
                message = await channel.fetch_message(payload.message_id)
            except (discord.NotFound, discord.Forbidden):
                return
            
            # Check if user is reacting to their own message
            if payload.user_id == message.author.id:
                # Remove their reaction
                for reaction in message.reactions:
                    if str(reaction.emoji) == star_emoji:
                        member = guild.get_member(payload.user_id)
                        if member:
                            await reaction.remove(member)
                            print(f"Removed self-reaction from post: {message.id}")
                return
            
            # Count stars (excluding author and bots)
            star_count = 0
            for reaction in message.reactions:
                if str(reaction.emoji) == star_emoji:
                    users = []
                    async for user in reaction.users():
                        if not user.bot and user.id != message.author.id:
                            users.append(user)
                    star_count = len(users)
                    break
            
            print(f"Post {message.id} now has {star_count} stars")
            
            # Check if post is in the database
            post = await self.starboard_posts.find_one({
                "guild_id": payload.guild_id,
                "channel_id": payload.channel_id,
                "message_id": payload.message_id
            })
            
            if post:
                # Update star count
                await self.starboard_posts.update_one(
                    {"_id": post["_id"]},
                    {"$set": {"star_count": star_count}}
                )
                print(f"Updated post {message.id} in database with {star_count} stars")
            else:
                # Create new entry
                post_data = {
                    "guild_id": payload.guild_id,
                    "channel_id": payload.channel_id,
                    "message_id": payload.message_id,
                    "author_id": message.author.id,
                    "star_count": star_count,
                    "featured": False,
                    "created_at": datetime.datetime.now()
                }
                
                result = await self.starboard_posts.insert_one(post_data)
                print(f"Added post to database on reaction: {message.id}, result: {result.inserted_id}")
            
        except Exception as e:
            print(f"Error processing reaction: {e}")
    
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """Handle when a reaction is removed from a message"""
        try:
            # Get server settings
            server_settings = await self.starboard_settings.find_one({"guild_id": payload.guild_id})
            if not server_settings:
                return
            
            # Check if this is a showcase channel
            showcase_channels = server_settings.get("showcase_channels", [])
            if payload.channel_id not in showcase_channels:
                return
            
            # Check if this is the star emoji
            star_emoji = server_settings.get("star_emoji", "⭐")
            if str(payload.emoji) != star_emoji:
                return
            
            # Get the message
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                return
            
            channel = guild.get_channel(payload.channel_id)
            if not channel:
                return
            
            try:
                message = await channel.fetch_message(payload.message_id)
            except (discord.NotFound, discord.Forbidden):
                # Message was deleted
                await self.starboard_posts.delete_one({
                    "guild_id": payload.guild_id,
                    "channel_id": payload.channel_id,
                    "message_id": payload.message_id
                })
                return
            
            # Count stars (excluding author and bots)
            star_count = 0
            for reaction in message.reactions:
                if str(reaction.emoji) == star_emoji:
                    users = []
                    async for user in reaction.users():
                        if not user.bot and user.id != message.author.id:
                            users.append(user)
                    star_count = len(users)
                    break
            
            print(f"Post {message.id} now has {star_count} stars after removal")
            
            # Update the post in the database
            post = await self.starboard_posts.find_one({
                "guild_id": payload.guild_id,
                "channel_id": payload.channel_id,
                "message_id": payload.message_id
            })
            
            if post:
                await self.starboard_posts.update_one(
                    {"_id": post["_id"]},
                    {"$set": {"star_count": star_count}}
                )
                print(f"Updated post {message.id} in database with {star_count} stars")
        
        except Exception as e:
            print(f"Error processing reaction removal: {e}")
    
    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        """Handle message deletion"""
        try:
            # Delete from database if exists
            result = await self.starboard_posts.delete_one({
                "guild_id": payload.guild_id,
                "channel_id": payload.channel_id,
                "message_id": payload.message_id
            })
            
            if result.deleted_count > 0:
                print(f"Deleted post {payload.message_id} from database due to message deletion")
        except Exception as e:
            print(f"Error handling message deletion: {e}")
    
    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        """Handle bulk message deletion"""
        try:
            # Delete each message from database if it exists
            for message_id in payload.message_ids:
                result = await self.starboard_posts.delete_one({
                    "guild_id": payload.guild_id,
                    "channel_id": payload.channel_id,
                    "message_id": message_id
                })
                
                if result.deleted_count > 0:
                    print(f"Deleted post {message_id} from database due to bulk message deletion")
        except Exception as e:
            print(f"Error handling bulk message deletion: {e}")
    
    @app_commands.command(name="setup_starboard", description="Set up or update the starboard system")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def setup_starboard(
        self,
        interaction: discord.Interaction,
        channels: str,
        star_emoji: str,
        attachments_only: Optional[bool] = False,
        auto_threads: Optional[bool] = False,
        featured_channel: Optional[discord.TextChannel] = None,
        threshold: Optional[int] = 3
    ):
        """Set up the starboard system"""
        await interaction.response.defer(ephemeral=True)
        
        # Check for admin permissions
        if not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send("You need administrator permissions to set up the starboard.", ephemeral=True)
        
        # Parse the channels input
        showcase_channel_ids = []
        showcase_channels_mentions = []
        
        # Split the input by spaces and process each part
        parts = channels.split()
        for part in parts:
            # Check if it's a channel mention
            if part.startswith("<#") and part.endswith(">"):
                try:
                    channel_id = int(part[2:-1])
                    channel = interaction.guild.get_channel(channel_id)
                    if channel and isinstance(channel, discord.TextChannel):
                        showcase_channel_ids.append(channel_id)
                        showcase_channels_mentions.append(channel.mention)
                except ValueError:
                    continue
        
        if not showcase_channel_ids:
            return await interaction.followup.send("Please provide at least one valid channel using #channel format.", ephemeral=True)
        
        # Validate the emoji
        if len(star_emoji.strip()) == 0:
            return await interaction.followup.send("Please provide a valid emoji for starring posts.", ephemeral=True)
        
        # Additional validation for thresholds
        if threshold is not None and threshold < 1:
            threshold = 1
        
        # Save settings to database
        guild_id = interaction.guild.id
        
        settings = {
            "guild_id": guild_id,
            "showcase_channels": showcase_channel_ids,
            "star_emoji": star_emoji.strip(),
            "attachments_only": attachments_only,
            "auto_threads": auto_threads,
            "bot_react": True,  # Default to true for auto-reactions
            "updated_at": datetime.datetime.now()
        }
        
        # Add featured channel and threshold if provided
        if featured_channel:
            settings["featured_channel_id"] = featured_channel.id
            settings["threshold"] = threshold or 3
        
        # Update or insert settings
        await self.starboard_settings.update_one(
            {"guild_id": guild_id},
            {"$set": settings},
            upsert=True
        )
        
        print(f"Starboard settings updated for guild {guild_id}")
        
        # Create confirmation message
        embed = discord.Embed(
            title="Starboard Setup Complete",
            description="The starboard system has been configured successfully.",
            color=discord.Color.gold(),
            timestamp=datetime.datetime.now()
        )
        
        embed.add_field(name="Showcase Channels", value="\n".join(showcase_channels_mentions), inline=False)
        embed.add_field(name="Star Emoji", value=star_emoji.strip(), inline=True)
        embed.add_field(name="Attachments Only", value="Yes" if attachments_only else "No", inline=True)
        embed.add_field(name="Auto Threads", value="Yes" if auto_threads else "No", inline=True)
        
        if featured_channel:
            embed.add_field(name="Featured Channel", value=featured_channel.mention, inline=True)
            embed.add_field(name="Star Threshold", value=str(threshold or 3), inline=True)
        else:
            embed.add_field(name="Featured Posts", value="Disabled (no featured channel set)", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Starboard(bot))
