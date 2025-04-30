# cogs/starboard.py
import discord
from discord.ext import commands
from discord import app_commands
import datetime
import asyncio
from typing import Optional, List, Literal

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
                async for server_settings in self.starboard_settings.find():
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
                    
                    # Get posts from the database that haven't been featured yet
                    async for post in self.starboard_posts.find({
                        "guild_id": guild_id,
                        "featured": False,
                        "star_count": {"$gte": threshold}
                    }):
                        # Try to get the original message
                        channel = guild.get_channel(post["channel_id"])
                        if not channel:
                            continue
                            
                        try:
                            message = await channel.fetch_message(post["message_id"])
                        except (discord.NotFound, discord.Forbidden):
                            # Message was deleted or can't be accessed
                            continue
                        
                        # Create the featured post embed
                        embed = await self.create_featured_embed(message, post["star_count"])
                        
                        # Copy any attachments
                        attachments = []
                        for attachment in message.attachments:
                            try:
                                file_bytes = await attachment.read()
                                attachments.append(discord.File(
                                    fp=file_bytes,
                                    filename=attachment.filename,
                                    description=attachment.description
                                ))
                            except:
                                pass
                        
                        # Send to featured channel
                        content = f"⭐ **{post['star_count']}** | {message.channel.mention} | {message.author.mention}"
                        if len(attachments) > 0:
                            featured_message = await featured_channel.send(content=content, embed=embed, files=attachments)
                        else:
                            featured_message = await featured_channel.send(content=content, embed=embed)
                        
                        # Update the post in the database
                        await self.starboard_posts.update_one(
                            {"_id": post["_id"]},
                            {"$set": {
                                "featured": True,
                                "featured_message_id": featured_message.id
                            }}
                        )
                
                # Check for posts that need their star count updated
                async for post in self.starboard_posts.find({"featured": True}):
                    guild_id = post["guild_id"]
                    guild = self.bot.get_guild(guild_id)
                    
                    if not guild:
                        continue
                    
                    # Get the server settings
                    server_settings = await self.starboard_settings.find_one({"guild_id": guild_id})
                    if not server_settings:
                        continue
                    
                    featured_channel_id = server_settings.get("featured_channel_id")
                    featured_channel = guild.get_channel(featured_channel_id)
                    
                    if not featured_channel:
                        continue
                    
                    # Try to get the original message
                    channel = guild.get_channel(post["channel_id"])
                    if not channel:
                        continue
                        
                    try:
                        message = await channel.fetch_message(post["message_id"])
                        star_emoji = server_settings.get("star_emoji", "⭐")
                        
                        # Count reactions
                        star_count = 0
                        for reaction in message.reactions:
                            if str(reaction.emoji) == star_emoji:
                                star_count = reaction.count
                                break
                        
                        # If star count has changed, update the featured message
                        if star_count != post["star_count"]:
                            try:
                                featured_message = await featured_channel.fetch_message(post["featured_message_id"])
                                
                                # Update the star count
                                content = featured_message.content
                                new_content = f"⭐ **{star_count}** | {message.channel.mention} | {message.author.mention}"
                                
                                await featured_message.edit(content=new_content)
                                
                                # Update the post in the database
                                await self.starboard_posts.update_one(
                                    {"_id": post["_id"]},
                                    {"$set": {"star_count": star_count}}
                                )
                                
                            except (discord.NotFound, discord.Forbidden):
                                # Featured message was deleted or can't be accessed
                                continue
                    except (discord.NotFound, discord.Forbidden):
                        # Original message was deleted or can't be accessed
                        continue
                
                # Check every 30 seconds
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                # Task was cancelled
                break
            except Exception as e:
                print(f"Error in starboard reaction task: {str(e)}")
                await asyncio.sleep(30)  # Continue checking
    
    async def create_featured_embed(self, message, star_count):
        """Create an embed for a featured post"""
        embed = discord.Embed(
            description=message.content,
            color=discord.Color.gold(),
            timestamp=message.created_at
        )
        
        embed.set_author(
            name=message.author.display_name,
            icon_url=message.author.display_avatar.url
        )
        
        # Add a footer with jump URL
        embed.add_field(name="Original", value=f"[Jump to message]({message.jump_url})", inline=False)
        
        embed.set_footer(text=f"ID: {message.id}")
        
        # If the message has embeds, include the first one
        if len(message.embeds) > 0 and message.embeds[0].type == 'rich':
            original_embed = message.embeds[0]
            
            # Copy image if present
            if original_embed.image:
                embed.set_image(url=original_embed.image.url)
            
            # Copy thumbnail if present and no image
            elif original_embed.thumbnail:
                embed.set_thumbnail(url=original_embed.thumbnail.url)
        
        # If no embed image but there's an attachment, use the first attachment as an image
        elif len(message.attachments) > 0 and message.attachments[0].content_type and message.attachments[0].content_type.startswith('image/'):
            embed.set_image(url=message.attachments[0].url)
        
        return embed
    
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handle reaction being added to messages"""
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
        
        # Check attachments setting
        attachments_only = server_settings.get("attachments_only", False)
        if attachments_only and len(message.attachments) == 0:
            return
        
        # Count the stars
        star_count = 0
        for reaction in message.reactions:
            if str(reaction.emoji) == star_emoji:
                star_count = reaction.count
                break
        
        # Check if the post is already in the database
        post = await self.starboard_posts.find_one({
            "guild_id": payload.guild_id,
            "channel_id": payload.channel_id,
            "message_id": payload.message_id
        })
        
        if post:
            # Update the post
            await self.starboard_posts.update_one(
                {"_id": post["_id"]},
                {"$set": {"star_count": star_count}}
            )
        else:
            # Create a new post entry
            await self.starboard_posts.insert_one({
                "guild_id": payload.guild_id,
                "channel_id": payload.channel_id,
                "message_id": payload.message_id,
                "author_id": message.author.id,
                "star_count": star_count,
                "featured": False,
                "created_at": datetime.datetime.now()
            })
        
        # Add the bot's reaction if enabled
        bot_react = server_settings.get("bot_react", True)
        if bot_react:
            # Check if the bot has already reacted
            for reaction in message.reactions:
                if str(reaction.emoji) == star_emoji:
                    async for user in reaction.users():
                        if user.id == self.bot.user.id:
                            # Bot has already reacted
                            return
            
            # Add the bot's reaction
            try:
                await message.add_reaction(star_emoji)
            except (discord.Forbidden, discord.NotFound):
                pass
        
        # Create a thread if auto_threads is enabled
        auto_threads = server_settings.get("auto_threads", False)
        if auto_threads and not message.thread:
            try:
                thread_name = f"Discussion: {message.content[:40]}..." if message.content else f"Discussion: Post by {message.author.display_name}"
                await message.create_thread(name=thread_name[:100], auto_archive_duration=1440)  # 24 hours
            except (discord.Forbidden, discord.HTTPException):
                pass
    
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """Handle reaction being removed from messages"""
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
        
        # Count the stars
        star_count = 0
        for reaction in message.reactions:
            if str(reaction.emoji) == star_emoji:
                star_count = reaction.count
                break
        
        # Check if the post is in the database
        post = await self.starboard_posts.find_one({
            "guild_id": payload.guild_id,
            "channel_id": payload.channel_id,
            "message_id": payload.message_id
        })
        
        if post:
            # Update the post
            await self.starboard_posts.update_one(
                {"_id": post["_id"]},
                {"$set": {"star_count": star_count}}
            )
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle new messages in showcase channels"""
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
            except (discord.Forbidden, discord.NotFound):
                pass
        
        # Create a thread if auto_threads is enabled
        auto_threads = server_settings.get("auto_threads", False)
        if auto_threads:
            try:
                thread_name = f"Discussion: {message.content[:40]}..." if message.content else f"Discussion: Post by {message.author.display_name}"
                await message.create_thread(name=thread_name[:100], auto_archive_duration=1440)  # 24 hours
            except (discord.Forbidden, discord.HTTPException):
                pass
    
    async def get_server_settings(self, guild_id):
        """Get starboard settings for a server"""
        settings = await self.starboard_settings.find_one({"guild_id": guild_id})
        return settings
    
    @app_commands.command(name="starboard", description="Set up or update the starboard system")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def starboard(
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
