# cogs/leveling.py
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import datetime
import random
import math
import numpy as np
import cv2
import io
import aiohttp
from typing import Optional

class Leveling(commands.Cog):
    """Leveling and ranking system for your Discord bot"""
    
    def __init__(self, bot):
        self.bot = bot
        # Use the bot's MongoDB database
        self.levels_collection = self.bot.db["levels"]
        self.settings_collection = self.bot.db["level_settings"]
        self.xp_cooldown = {}  # User ID: Last message timestamp
        self.default_cooldown = 60  # Seconds between XP gain from messages
        self.default_xp_range = (15, 25)  # Min and max XP per message
    
    # Helper methods for the leveling system
    async def get_user_data(self, user_id, guild_id):
        """Get user's level data from database"""
        data = await self.levels_collection.find_one({"user_id": user_id, "guild_id": guild_id})
        if data is None:
            # Create new user data if not exists
            data = {
                "user_id": user_id,
                "guild_id": guild_id,
                "xp": 0,
                "level": 0,
                "last_message": datetime.datetime.utcnow(),
                "messages": 0
            }
            await self.levels_collection.insert_one(data)
        return data
    
    async def update_user_xp(self, user_id, guild_id, xp_to_add):
        """Update user's XP and level"""
        data = await self.get_user_data(user_id, guild_id)
        
        # Update XP
        new_xp = data["xp"] + xp_to_add
        new_level = self.calculate_level(new_xp)
        
        # Check if level up occurred
        level_up = new_level > data["level"]
        
        # Update in database
        await self.levels_collection.update_one(
            {"user_id": user_id, "guild_id": guild_id},
            {"$set": {
                "xp": new_xp,
                "level": new_level,
                "last_message": datetime.datetime.utcnow(),
                "messages": data["messages"] + 1
            }}
        )
        
        return new_xp, new_level, level_up
    
    def calculate_level(self, xp):
        """Calculate level based on XP"""
        # Formula: level = sqrt(xp / 100)
        return math.floor(math.sqrt(xp / 100))
    
    def calculate_xp_for_level(self, level):
        """Calculate XP needed for a specific level"""
        return level * level * 100
    
    def calculate_progress(self, xp, level):
        """Calculate progress to next level (0-100%)"""
        current_level_xp = self.calculate_xp_for_level(level)
        next_level_xp = self.calculate_xp_for_level(level + 1)
        
        if next_level_xp - current_level_xp == 0:
            return 100  # Avoid division by zero
            
        progress = ((xp - current_level_xp) / (next_level_xp - current_level_xp)) * 100
        return min(100, max(0, progress))  # Ensure between 0-100
    
    async def get_guild_settings(self, guild_id):
        """Get level settings for a guild"""
        settings = await self.settings_collection.find_one({"guild_id": guild_id})
        if settings is None:
            # Create default settings
            settings = {
                "guild_id": guild_id,
                "enabled": True,
                "cooldown": self.default_cooldown,
                "min_xp": self.default_xp_range[0],
                "max_xp": self.default_xp_range[1],
                "announce_level_up": True,
                "level_up_channel": None,
                "excluded_channels": [],
                "role_rewards": {}  # level: role_id
            }
            await self.settings_collection.insert_one(settings)
        return settings
    
    async def get_leaderboard(self, guild_id, limit=10):
        """Get the top users by XP in a guild"""
        cursor = self.levels_collection.find({"guild_id": guild_id}).sort("xp", -1).limit(limit)
        leaderboard = await cursor.to_list(length=limit)
        return leaderboard
    
    async def get_user_rank(self, user_id, guild_id):
        """Get user's rank position in the server"""
        pipeline = [
            {"$match": {"guild_id": guild_id}},
            {"$sort": {"xp": -1}},
            {"$group": {"_id": None, "users": {"$push": "$user_id"}}},
            {"$project": {"rank": {"$indexOfArray": ["$users", user_id]}}},
        ]
        
        result = await self.levels_collection.aggregate(pipeline).to_list(length=1)
        if not result:
            return 0
            
        # Add 1 because indexOfArray is 0-based
        return result[0]["rank"] + 1
    
    # Event listeners
    @commands.Cog.listener()
    async def on_message(self, message):
        """Award XP when users send messages"""
        # Ignore bot messages
        if message.author.bot:
            return
            
        # Ignore DMs
        if not message.guild:
            return
            
        # Get guild settings
        settings = await self.get_guild_settings(message.guild.id)
        
        # Check if leveling is enabled
        if not settings["enabled"]:
            return
            
        # Check if channel is excluded
        if str(message.channel.id) in settings["excluded_channels"]:
            return
            
        # Check cooldown
        user_id = message.author.id
        guild_id = message.guild.id
        
        cooldown_key = f"{user_id}_{guild_id}"
        current_time = datetime.datetime.utcnow()
        
        if cooldown_key in self.xp_cooldown:
            time_diff = (current_time - self.xp_cooldown[cooldown_key]).total_seconds()
            if time_diff < settings["cooldown"]:
                return  # Still on cooldown
                
        # Update cooldown
        self.xp_cooldown[cooldown_key] = current_time
        
        # Award random XP
        xp_to_add = random.randint(settings["min_xp"], settings["max_xp"])
        new_xp, new_level, level_up = await self.update_user_xp(user_id, guild_id, xp_to_add)
        
        # Handle level up
        if level_up and settings["announce_level_up"]:
            if settings["level_up_channel"]:
                # Announce in specific channel
                channel = message.guild.get_channel(int(settings["level_up_channel"]))
                if channel:
                    await channel.send(f"🎉 {message.author.mention} just reached level {new_level}!")
            else:
                # Announce in current channel
                await message.channel.send(f"🎉 {message.author.mention} just reached level {new_level}!")
            
            # Check for role rewards
            role_rewards = settings.get("role_rewards", {})
            for level_str, role_id_str in role_rewards.items():
                if int(level_str) == new_level:
                    try:
                        role = message.guild.get_role(int(role_id_str))
                        if role:
                            await message.author.add_roles(role)
                    except Exception as e:
                        print(f"Error adding role reward: {e}")
    
    # Create rank card with OpenCV
    async def create_rank_card(self, user, user_data, rank, guild):
        """Create a rank card image using OpenCV"""
        # Image dimensions
        width = 800
        height = 200
        
        # Create a background
        image = np.zeros((height, width, 4), dtype=np.uint8)
        
        # Add a background color
        # Dark theme with slight gradient
        for y in range(height):
            for x in range(width):
                # Create a subtle gradient
                gradient_factor = y / height * 30  # Subtle variation
                image[y, x] = (33 + gradient_factor, 33 + gradient_factor, 39 + gradient_factor, 255)
        
        try:
            # Download user avatar
            async with aiohttp.ClientSession() as session:
                avatar_url = str(user.display_avatar.url)
                async with session.get(avatar_url) as resp:
                    avatar_bytes = await resp.read()
            
            # Create avatar image from bytes
            avatar_arr = np.asarray(bytearray(avatar_bytes), dtype=np.uint8)
            avatar = cv2.imdecode(avatar_arr, cv2.IMREAD_COLOR)
            
            # Resize avatar
            avatar_size = 130
            avatar = cv2.resize(avatar, (avatar_size, avatar_size))
            
            # Convert BGR to BGRA (add alpha channel)
            avatar = cv2.cvtColor(avatar, cv2.COLOR_BGR2BGRA)
            
            # Create circular mask for avatar
            mask = np.zeros((avatar_size, avatar_size), dtype=np.uint8)
            center = avatar_size // 2
            radius = avatar_size // 2
            cv2.circle(mask, (center, center), radius, 255, -1)
            
            # Apply mask to make avatar circular
            for c in range(3):  # Apply to BGR channels
                avatar[:, :, c] = cv2.bitwise_and(avatar[:, :, c], avatar[:, :, c], mask=mask)
            
            # Set transparent background for the circular mask
            avatar[:, :, 3] = mask
            
            # Place avatar on the card
            avatar_position = (30, 35)  # (x, y)
            for y in range(avatar_size):
                for x in range(avatar_size):
                    if avatar[y, x, 3] > 0:  # Not fully transparent
                        if (0 <= avatar_position[1] + y < height and 
                            0 <= avatar_position[0] + x < width):
                            image[avatar_position[1] + y, avatar_position[0] + x] = avatar[y, x]
            
            # Get user data
            level = user_data["level"]
            xp = user_data["xp"]
            current_level_xp = self.calculate_xp_for_level(level)
            next_level_xp = self.calculate_xp_for_level(level + 1)
            progress = self.calculate_progress(xp, level)
            
            # Add username
            username_text = user.display_name
            if len(username_text) > 16:
                username_text = username_text[:16] + "..."
                
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 1.0
            font_thickness = 2
            font_color = (255, 255, 255, 255)  # White with full opacity
            
            # Position username text
            text_position = (avatar_position[0] + avatar_size + 20, avatar_position[1] + 30)
            cv2.putText(image, username_text, text_position, font, font_scale, font_color, font_thickness)
            
            # Add rank info
            rank_text = f"Rank #{rank}"
            rank_text_size = cv2.getTextSize(rank_text, font, 0.8, 2)[0]
            rank_position = (width - rank_text_size[0] - 20, text_position[1])
            cv2.putText(image, rank_text, rank_position, font, 0.8, font_color, 2)
            
            # Add level info
            level_text = f"Level {level}"
            level_position = (text_position[0], text_position[1] + 35)
            cv2.putText(image, level_text, level_position, font, 0.8, font_color, 2)
            
            # Add XP progress text
            xp_text = f"XP: {xp - current_level_xp}/{next_level_xp - current_level_xp}"
            xp_position = (rank_position[0] - 150, level_position[1])
            cv2.putText(image, xp_text, xp_position, font, 0.6, font_color, 1)
            
            # Draw progress bar background (darker)
            progress_bar_start = (text_position[0], level_position[1] + 30)
            progress_bar_width = width - progress_bar_start[0] - 30
            progress_bar_height = 30
            cv2.rectangle(
                image, 
                progress_bar_start, 
                (progress_bar_start[0] + progress_bar_width, progress_bar_start[1] + progress_bar_height), 
                (60, 60, 70, 255), 
                -1
            )
            
            # Draw progress bar (filled portion)
            filled_width = int((progress / 100) * progress_bar_width)
            
            # Choose color based on level (changing every 10 levels)
            color_options = [
                (52, 152, 219, 255),  # Blue
                (155, 89, 182, 255),  # Purple
                (46, 204, 113, 255),  # Green
                (230, 126, 34, 255),  # Orange
                (231, 76, 60, 255),   # Red
                (241, 196, 15, 255),  # Yellow
            ]
            color_index = (level // 10) % len(color_options)
            progress_color = color_options[color_index]
            
            cv2.rectangle(
                image, 
                progress_bar_start, 
                (progress_bar_start[0] + filled_width, progress_bar_start[1] + progress_bar_height), 
                progress_color, 
                -1
            )
            
            # Add percentage text on progress bar (centered)
            percentage_text = f"{int(progress)}%"
            text_size = cv2.getTextSize(percentage_text, font, 0.6, 1)[0]
            percentage_position = (
                progress_bar_start[0] + (progress_bar_width - text_size[0]) // 2,
                progress_bar_start[1] + (progress_bar_height + text_size[1]) // 2
            )
            cv2.putText(image, percentage_text, percentage_position, font, 0.6, (255, 255, 255, 255), 1)
            
            # Add messages count
            message_count = user_data.get("messages", 0)
            message_text = f"Messages: {message_count}"
            message_position = (text_position[0], progress_bar_start[1] + progress_bar_height + 25)
            cv2.putText(image, message_text, message_position, font, 0.6, font_color, 1)
            
        except Exception as e:
            print(f"Error creating rank card: {e}")
            # Add error text if image creation fails
            cv2.putText(
                image, 
                f"Error creating rank card: {str(e)[:50]}", 
                (50, 100), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.7, 
                (255, 255, 255, 255), 
                1
            )
        
        # Convert the image to a format Discord can use
        _, buffer = cv2.imencode(".png", image)
        byte_io = io.BytesIO(buffer)
        
        # Create Discord file
        return discord.File(fp=byte_io, filename="rank.png")
    
    # User commands
    @app_commands.command(
        name="rank",
        description="Show your current rank and level"
    )
    async def rank(
        self, 
        interaction: discord.Interaction, 
        user: Optional[discord.User] = None
    ):
        """Show your current rank and level"""
        await interaction.response.defer()
        
        # Get settings
        settings = await self.get_guild_settings(interaction.guild.id)
        if not settings["enabled"]:
            await interaction.followup.send("The leveling system is disabled in this server.")
            return
        
        # Get target user (default to command user)
        target_user = user or interaction.user
        
        # Get user data
        user_data = await self.get_user_data(target_user.id, interaction.guild.id)
        
        # Get user rank
        rank = await self.get_user_rank(target_user.id, interaction.guild.id)
        
        try:
            # Create rank card
            rank_card = await self.create_rank_card(target_user, user_data, rank, interaction.guild)
            
            await interaction.followup.send(file=rank_card)
        except Exception as e:
            # Fallback to text response if image creation fails
            print(f"Error generating rank card: {e}")
            
            level = user_data["level"]
            xp = user_data["xp"]
            current_xp = self.calculate_xp_for_level(level)
            next_level_xp = self.calculate_xp_for_level(level + 1)
            progress = self.calculate_progress(xp, level)
            
            embed = discord.Embed(
                title=f"{target_user.display_name}'s Rank",
                description=f"**Rank:** #{rank}\n"
                            f"**Level:** {level}\n"
                            f"**XP:** {xp} ({xp - current_xp}/{next_level_xp - current_xp})\n"
                            f"**Progress:** {int(progress)}%\n"
                            f"**Messages:** {user_data.get('messages', 0)}",
                color=discord.Color.blue()
            )
            
            embed.set_thumbnail(url=target_user.display_avatar.url)
            embed.set_footer(text=f"Requested by {interaction.user.display_name}", 
                            icon_url=interaction.user.display_avatar.url)
            
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(
        name="leaderboard",
        description="Show the server's XP leaderboard"
    )
    async def leaderboard(
        self, 
        interaction: discord.Interaction,
        page: Optional[int] = 1
    ):
        """Show the server's XP leaderboard"""
        await interaction.response.defer()
        
        # Get settings
        settings = await self.get_guild_settings(interaction.guild.id)
        if not settings["enabled"]:
            await interaction.followup.send("The leveling system is disabled in this server.")
            return
        
        # Validate page
        page = max(1, page)
        limit = 10
        skip = (page - 1) * limit
        
        # Get leaderboard data
        cursor = self.levels_collection.find({"guild_id": interaction.guild.id}).sort("xp", -1).skip(skip).limit(limit)
        leaderboard_data = await cursor.to_list(length=limit)
        
        if not leaderboard_data:
            await interaction.followup.send("No users found in the leaderboard.")
            return
        
        # Count total users
        total_users = await self.levels_collection.count_documents({"guild_id": interaction.guild.id})
        total_pages = math.ceil(total_users / limit)
        
        # Create embed
        embed = discord.Embed(
            title=f"{interaction.guild.name} Leaderboard",
            description=f"Showing page {page}/{total_pages}",
            color=discord.Color.gold()
        )
        
        # Add leaderboard entries
        for i, data in enumerate(leaderboard_data):
            rank = skip + i + 1
            user_id = data["user_id"]
            level = data["level"]
            xp = data["xp"]
            
            # Try to get Discord user
            user = interaction.guild.get_member(user_id)
            name = user.display_name if user else f"User {user_id}"
            
            embed.add_field(
                name=f"#{rank} {name}",
                value=f"Level: {level}\nXP: {xp}",
                inline=(i % 2 == 0)  # Alternate between left and right columns
            )
        
        # Add footer
        embed.set_footer(text=f"Requested by {interaction.user.display_name}", 
                        icon_url=interaction.user.display_avatar.url)
        
        # Add page navigation instructions
        embed.add_field(
            name="\u200b",  # Zero-width space for spacing
            value=f"Use `/leaderboard page:{page+1}` to see the next page" if page < total_pages else "\u200b",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
    
    # Admin commands - Level settings
    @app_commands.command(
        name="levelconfig",
        description="Configure the leveling system (Admin only)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def level_config(
        self, 
        interaction: discord.Interaction, 
        setting: str, 
        value: str
    ):
        """Configure the leveling system (Admin only)"""
        await interaction.response.defer(ephemeral=True)
        
        # Get current settings
        settings = await self.get_guild_settings(interaction.guild.id)
        
        # Parse setting and value
        setting = setting.lower()
        
        if setting == "enabled":
            # Enable/disable the leveling system
            if value.lower() in ["true", "yes", "on", "1"]:
                settings["enabled"] = True
                result = "Leveling system has been **enabled**."
            elif value.lower() in ["false", "no", "off", "0"]:
                settings["enabled"] = False
                result = "Leveling system has been **disabled**."
            else:
                await interaction.followup.send("Invalid value. Use 'true' or 'false'.")
                return
                
        elif setting == "cooldown":
            # Set XP gain cooldown
            try:
                cooldown = int(value)
                if cooldown < 0:
                    await interaction.followup.send("Cooldown cannot be negative.")
                    return
                settings["cooldown"] = cooldown
                result = f"XP cooldown set to **{cooldown} seconds**."
            except ValueError:
                await interaction.followup.send("Invalid value. Please provide a number for cooldown.")
                return
                
        elif setting == "minxp":
            # Set minimum XP per message
            try:
                min_xp = int(value)
                if min_xp < 1:
                    await interaction.followup.send("Minimum XP must be at least 1.")
                    return
                if min_xp > settings["max_xp"]:
                    await interaction.followup.send(f"Minimum XP cannot be greater than maximum XP ({settings['max_xp']}).")
                    return
                settings["min_xp"] = min_xp
                result = f"Minimum XP set to **{min_xp}**."
            except ValueError:
                await interaction.followup.send("Invalid value. Please provide a number for minimum XP.")
                return
                
        elif setting == "maxxp":
            # Set maximum XP per message
            try:
                max_xp = int(value)
                if max_xp < settings["min_xp"]:
                    await interaction.followup.send(f"Maximum XP cannot be less than minimum XP ({settings['min_xp']}).")
                    return
                settings["max_xp"] = max_xp
                result = f"Maximum XP set to **{max_xp}**."
            except ValueError:
                await interaction.followup.send("Invalid value. Please provide a number for maximum XP.")
                return
                
        elif setting == "announce":
            # Set level up announcement
            if value.lower() in ["true", "yes", "on", "1"]:
                settings["announce_level_up"] = True
                result = "Level up announcements have been **enabled**."
            elif value.lower() in ["false", "no", "off", "0"]:
                settings["announce_level_up"] = False
                result = "Level up announcements have been **disabled**."
            else:
                await interaction.followup.send("Invalid value. Use 'true' or 'false'.")
                return
                
        elif setting == "announcechannel":
            # Set level up announcement channel
            if value.lower() in ["none", "reset", "clear", "0"]:
                settings["level_up_channel"] = None
                result = "Level up announcements will be sent in the same channel as the message."
            else:
                # Try to parse channel ID or mention
                try:
                    # Check if it's a channel mention
                    if value.startswith("<#") and value.endswith(">"):
                        channel_id = int(value[2:-1])
                    else:
                        channel_id = int(value)
                        
                    # Verify channel exists
                    channel = interaction.guild.get_channel(channel_id)
                    if channel is None:
                        await interaction.followup.send("Channel not found.")
                        return
                        
                    settings["level_up_channel"] = str(channel_id)
                    result = f"Level up announcements will be sent in {channel.mention}."
                except (ValueError, IndexError):
                    await interaction.followup.send("Invalid channel. Please provide a valid channel ID or mention.")
                    return
                    
        elif setting == "excludechannel":
            # Add or remove excluded channel
            try:
                # Check if it's a channel mention
                if value.startswith("<#") and value.endswith(">"):
                    channel_id = value[2:-1]
                else:
                    channel_id = value
                    
                # Verify channel exists
                channel = interaction.guild.get_channel(int(channel_id))
                if channel is None:
                    await interaction.followup.send("Channel not found.")
                    return
                    
                # Add or remove from excluded channels
                if channel_id in settings["excluded_channels"]:
                    settings["excluded_channels"].remove(channel_id)
                    result = f"{channel.mention} is no longer excluded from XP gain."
                else:
                    settings["excluded_channels"].append(channel_id)
                    result = f"{channel.mention} is now excluded from XP gain."
            except (ValueError, IndexError):
                await interaction.followup.send("Invalid channel. Please provide a valid channel ID or mention.")
                return
                
        else:
            await interaction.followup.send(
                "Unknown setting. Available settings:\n"
                "- `enabled` (true/false)\n"
                "- `cooldown` (seconds)\n"
                "- `minxp` (number)\n"
                "- `maxxp` (number)\n"
                "- `announce` (true/false)\n"
                "- `announcechannel` (channel ID or 'none')\n"
                "- `excludechannel` (channel ID to toggle)"
            )
            return
            
        # Update settings in database
        await self.settings_collection.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": settings}
        )
        
        # Send confirmation
        await interaction.followup.send(result)
    
    @app_commands.command(
        name="setlevel",
        description="Set a user's level (Admin only)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_level(
        self, 
        interaction: discord.Interaction, 
        user: discord.User,
        level: int
    ):
        """Set a user's level (Admin only)"""
        await interaction.response.defer(ephemeral=True)
        
        # Validate level
        if level < 0:
            await interaction.followup.send("Level cannot be negative.")
            return
            
        # Calculate XP for level
        xp = self.calculate_xp_for_level(level)
        
        # Update user data
        await self.levels_collection.update_one(
            {"user_id": user.id, "guild_id": interaction.guild.id},
            {"$set": {"xp": xp, "level": level}},
            upsert=True
        )
        
        await interaction.followup.send(f"Set {user.mention}'s level to **{level}** ({xp} XP).")
    
    @app_commands.command(
        name="addxp",
        description="Add XP to a user (Admin only)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def add_xp(
        self, 
        interaction: discord.Interaction, 
        user: discord.User,
        xp: int
    ):
        """Add XP to a user (Admin only)"""
        await interaction.response.defer(ephemeral=True)
        
        # Validate XP
        if xp <= 0:
            await interaction.followup.send("XP to add must be positive.")
            return
            
        # Get user data first
        data = await self.get_user_data(user.id, interaction.guild.id)
        old_level = data["level"]
        
        # Update user XP
        new_xp, new_level, level_up = await self.update_user_xp(user.id, interaction.guild.id, xp)
        
        # Prepare response message
        response = f"Added **{xp}** XP to {user.mention}. "
        response += f"New total: **{new_xp}** XP (Level **{new_level}**)."
        
        if level_up:
            levels_gained = new_level - old_level
            response += f"\nUser leveled up {levels_gained} time{'s' if levels_gained > 1 else ''}!"
            
        await interaction.followup.send(response)
    
    @app_commands.command(
        name="resetlevels",
        description="Reset all levels and XP for the server (Admin only)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_levels(
        self, 
        interaction: discord.Interaction, 
        confirmation: str
    ):
        """Reset all levels and XP for the server (Admin only)"""
        await interaction.response.defer(ephemeral=True)
        
        # Require specific confirmation
        if confirmation.lower() != "confirm reset all levels":
            await interaction.followup.send(
                "To reset all levels, type `/resetlevels confirmation:confirm reset all levels`"
            )
            return
            
        # Delete all level data for this guild
        result = await self.levels_collection.delete_many({"guild_id": interaction.guild.id})
        
        await interaction.followup.send(
            f"✅ Reset levels for this server. Deleted {result.deleted_count} user records."
        )
    
    @app_commands.command(
        name="levelreward",
        description="Set up a role reward for reaching a level (Admin only)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def level_reward(
        self, 
        interaction: discord.Interaction, 
        level: int,
        role: Optional[discord.Role] = None
    ):
        """Set up a role reward for reaching a level (Admin only)"""
        await interaction.response.defer(ephemeral=True)
        
        # Get settings
        settings = await self.get_guild_settings(interaction.guild.id)
        
        # Initialize role_rewards if not exists
        if "role_rewards" not in settings:
            settings["role_rewards"] = {}
            
        # Convert to strings for MongoDB compatibility
        level_str = str(level)
        
        if role is None:
            # Remove reward for this level
            if level_str in settings["role_rewards"]:
                del settings["role_rewards"][level_str]
                await self.settings_collection.update_one(
                    {"guild_id": interaction.guild.id},
                    {"$set": {"role_rewards": settings["role_rewards"]}}
                )
                await interaction.followup.send(f"Removed role reward for level {level}.")
            else:
                await interaction.followup.send(f"No role reward was set for level {level}.")
        else:
            # Validate role is assignable
            if role.position >= interaction.guild.me.top_role.position:
                await interaction.followup.send(
                    "I cannot assign this role because it is positioned above or equal to my highest role."
                )
                return
                
            # Set role reward
            settings["role_rewards"][level_str] = str(role.id)
            
            # Update database
            await self.settings_collection.update_one(
                {"guild_id": interaction.guild.id},
                {"$set": {"role_rewards": settings["role_rewards"]}}
            )
            
            await interaction.followup.send(f"Set {role.mention} as a reward for reaching level {level}.")
    
    @app_commands.command(
        name="listrewards",
        description="List all level role rewards"
    )
    async def list_rewards(
        self, 
        interaction: discord.Interaction
    ):
        """List all level role rewards"""
        await interaction.response.defer()
        
        # Get settings
        settings = await self.get_guild_settings(interaction.guild.id)
        
        # Get role rewards
        role_rewards = settings.get("role_rewards", {})
        
        if not role_rewards:
            await interaction.followup.send("No role rewards are set up for this server.")
            return
            
        # Create embed
        embed = discord.Embed(
            title="Level Role Rewards",
            color=discord.Color.blue()
        )
        
        # Sort by level
        sorted_rewards = sorted(role_rewards.items(), key=lambda x: int(x[0]))
        
        # Add each reward to the embed
        for level_str, role_id_str in sorted_rewards:
            # Get role object
            role = interaction.guild.get_role(int(role_id_str))
            role_text = role.mention if role else f"Unknown Role (ID: {role_id_str})"
            
            embed.add_field(
                name=f"Level {level_str}",
                value=role_text,
                inline=True
            )
            
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(
        name="showsettings",
        description="Show current level system settings"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def show_settings(
        self, 
        interaction: discord.Interaction
    ):
        """Show current level system settings"""
        await interaction.response.defer(ephemeral=True)
        
        # Get settings
        settings = await self.get_guild_settings(interaction.guild.id)
        
        # Format excluded channels
        excluded_channels = []
        for channel_id in settings["excluded_channels"]:
            channel = interaction.guild.get_channel(int(channel_id))
            if channel:
                excluded_channels.append(channel.mention)
            else:
                excluded_channels.append(f"Unknown Channel ({channel_id})")
                
        excluded_text = ", ".join(excluded_channels) if excluded_channels else "None"
        
        # Format announcement channel
        if settings["level_up_channel"]:
            channel = interaction.guild.get_channel(int(settings["level_up_channel"]))
            announce_channel = channel.mention if channel else f"Unknown Channel ({settings['level_up_channel']})"
        else:
            announce_channel = "Same as message channel"
            
        # Create embed
        embed = discord.Embed(
            title="Leveling System Settings",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="System Enabled", value=str(settings["enabled"]), inline=True)
        embed.add_field(name="XP Cooldown", value=f"{settings['cooldown']} seconds", inline=True)
        embed.add_field(name="XP Per Message", value=f"{settings['min_xp']} - {settings['max_xp']}", inline=True)
        embed.add_field(name="Announce Level Ups", value=str(settings["announce_level_up"]), inline=True)
        embed.add_field(name="Announcement Channel", value=announce_channel, inline=True)
        embed.add_field(name="Excluded Channels", value=excluded_text, inline=False)
        
        # Count role rewards
        role_rewards = settings.get("role_rewards", {})
        embed.add_field(name="Role Rewards", value=f"{len(role_rewards)} rewards set" if role_rewards else "None", inline=False)
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Leveling(bot))
