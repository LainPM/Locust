# cogs/lovecalc.py
import discord
from discord.ext import commands
from discord import app_commands
import hashlib
import aiohttp
import io
import numpy as np
import cv2
import asyncio
import math

class LoveCalc(commands.Cog):
    """Love Calculator command for Axis bot"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="lovecalc",
        description="Calculate the love compatibility between two users"
    )
    async def love_calculator(
        self, 
        interaction: discord.Interaction, 
        user1: discord.User,
        user2: discord.User
    ):
        """Calculate love compatibility between two users"""
        await interaction.response.defer()
        
        # Get the love percentage using a deterministic method
        love_percentage = self.calculate_love_percentage(user1.id, user2.id)
        
        # Create the message
        message = f"{user1.display_name} and {user2.display_name} are {love_percentage}% compatible! 💞"
        
        # Add extra message if 100% match
        if love_percentage == 100:
            message += "\n# love is in the air!"
        
        # Create a nice embed
        embed = discord.Embed(
            title="❤️ Love Calculator ❤️",
            description=message,
            color=self.get_love_color(love_percentage)
        )
        
        try:
            # Create composite image with both avatars and a heart
            image_file = await self.create_love_image(user1, user2, love_percentage)
            embed.set_image(url="attachment://lovecalc.png")
            
            # Set footer with requester info
            embed.set_footer(text=f"Requested by {interaction.user.display_name}", 
                            icon_url=interaction.user.display_avatar.url)
            
            # Send the message with the image
            await interaction.followup.send(embed=embed, file=image_file)
        except Exception as e:
            # Fallback to simpler embed if image creation fails
            print(f"Error creating love image: {e}")
            embed.set_thumbnail(url=user1.display_avatar.url)
            embed.set_footer(text=f"Requested by {interaction.user.display_name}", 
                            icon_url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=embed)
    
    def calculate_love_percentage(self, id1, id2):
        """Calculate love percentage based on user IDs in a consistent manner"""
        # Convert IDs to strings and sort them to ensure consistent results
        # regardless of parameter order
        ids = sorted([str(id1), str(id2)])
        
        # Combine the IDs
        combined = f"{ids[0]}_{ids[1]}"
        
        # Create a hash from the combined string
        hash_value = int(hashlib.md5(combined.encode()).hexdigest(), 16)
        
        # Convert hash to a number between 0 and 100
        percentage = (hash_value % 101)
        
        return percentage
    
    def get_love_color(self, percentage):
        """Get a color based on the love percentage"""
        if percentage < 20:
            return discord.Color.from_rgb(255, 0, 0)  # Red
        elif percentage < 40:
            return discord.Color.from_rgb(255, 127, 0)  # Orange
        elif percentage < 60:
            return discord.Color.from_rgb(255, 255, 0)  # Yellow
        elif percentage < 80:
            return discord.Color.from_rgb(127, 255, 0)  # Light green
        elif percentage < 100:
            return discord.Color.from_rgb(0, 255, 0)  # Green
        else:
            return discord.Color.from_rgb(255, 0, 255)  # Purple for 100% match
    
    async def create_love_image(self, user1, user2, percentage):
        """Create an image with both user avatars and a heart in the middle using OpenCV"""
        # Image dimensions
        width = 600
        height = 200
        
        # Download avatars
        async with aiohttp.ClientSession() as session:
            # Get first user avatar
            avatar_url1 = str(user1.display_avatar.url)
            async with session.get(avatar_url1) as resp:
                avatar_bytes1 = await resp.read()
                
            # Get second user avatar
            avatar_url2 = str(user2.display_avatar.url)
            async with session.get(avatar_url2) as resp:
                avatar_bytes2 = await resp.read()
        
        # Create avatar images from bytes using OpenCV
        avatar1_arr = np.asarray(bytearray(avatar_bytes1), dtype=np.uint8)
        avatar1 = cv2.imdecode(avatar1_arr, cv2.IMREAD_COLOR)
        
        avatar2_arr = np.asarray(bytearray(avatar_bytes2), dtype=np.uint8)
        avatar2 = cv2.imdecode(avatar2_arr, cv2.IMREAD_COLOR)
        
        # Create a transparent background
        image = np.zeros((height, width, 4), dtype=np.uint8)
        
        # Resize avatars
        avatar_size = 180
        avatar1 = cv2.resize(avatar1, (avatar_size, avatar_size))
        avatar2 = cv2.resize(avatar2, (avatar_size, avatar_size))
        
        # Convert BGR to BGRA (add alpha channel)
        avatar1 = cv2.cvtColor(avatar1, cv2.COLOR_BGR2BGRA)
        avatar2 = cv2.cvtColor(avatar2, cv2.COLOR_BGR2BGRA)
        
        # Create circular masks for avatars
        mask1 = np.zeros((avatar_size, avatar_size), dtype=np.uint8)
        mask2 = np.zeros((avatar_size, avatar_size), dtype=np.uint8)
        
        center = avatar_size // 2
        radius = avatar_size // 2
        cv2.circle(mask1, (center, center), radius, 255, -1)
        cv2.circle(mask2, (center, center), radius, 255, -1)
        
        # Apply masks to make avatars circular
        for c in range(3):  # Apply to BGR channels
            avatar1[:, :, c] = cv2.bitwise_and(avatar1[:, :, c], avatar1[:, :, c], mask=mask1)
            avatar2[:, :, c] = cv2.bitwise_and(avatar2[:, :, c], avatar2[:, :, c], mask=mask2)
        
        # Set transparent background for the circular masks
        avatar1[:, :, 3] = mask1
        avatar2[:, :, 3] = mask2
        
        # Get heart color based on percentage
        if percentage < 20:
            heart_color = (0, 0, 255, 255)  # Red (BGR format)
        elif percentage < 40:
            heart_color = (0, 127, 255, 255)  # Orange
        elif percentage < 60:
            heart_color = (0, 255, 255, 255)  # Yellow
        elif percentage < 80:
            heart_color = (0, 255, 127, 255)  # Light green
        elif percentage < 100:
            heart_color = (0, 255, 0, 255)  # Green
        else:
            heart_color = (255, 0, 255, 255)  # Purple

        # Create heart shape
        heart_size = 120
        heart_img = np.zeros((heart_size, heart_size, 4), dtype=np.uint8)
        
        # Draw heart shape using two circles and a triangle
        center1 = (heart_size // 4, heart_size // 4)
        center2 = (heart_size * 3 // 4, heart_size // 4)
        radius = heart_size // 4
        
        cv2.circle(heart_img, center1, radius, heart_color, -1)
        cv2.circle(heart_img, center2, radius, heart_color, -1)
        
        triangle_pts = np.array([
            [0, heart_size // 3],
            [heart_size // 2, heart_size - 10],
            [heart_size, heart_size // 3]
        ], np.int32)
        
        cv2.fillPoly(heart_img, [triangle_pts], heart_color)
        
        # Add percentage text to heart
        text = f"{percentage}%"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        text_size = cv2.getTextSize(text, font, font_scale, 2)[0]
        text_pos = ((heart_size - text_size[0]) // 2, (heart_size + text_size[1]) // 2)
        
        cv2.putText(heart_img, text, text_pos, font, font_scale, (255, 255, 255, 255), 2)
        
        # Place avatars and heart on the image
        try:
            # Place first avatar
            for y in range(avatar_size):
                for x in range(avatar_size):
                    if avatar1[y, x, 3] > 0:  # Not fully transparent
                        image[10 + y, 40 + x] = avatar1[y, x]
            
            # Place second avatar
            for y in range(avatar_size):
                for x in range(avatar_size):
                    if avatar2[y, x, 3] > 0:  # Not fully transparent
                        image[10 + y, width - avatar_size - 40 + x] = avatar2[y, x]
            
            # Place heart
            heart_pos_x = (width - heart_size) // 2
            heart_pos_y = (height - heart_size) // 2
            
            for y in range(heart_size):
                for x in range(heart_size):
                    if heart_img[y, x, 3] > 0:  # Not fully transparent
                        if (0 <= heart_pos_y + y < height and 0 <= heart_pos_x + x < width):
                            image[heart_pos_y + y, heart_pos_x + x] = heart_img[y, x]
        
        except Exception as e:
            print(f"Error compositing image: {e}")
        
        # Convert the image back to a format that Discord can use
        _, buffer = cv2.imencode(".png", image)
        byte_io = io.BytesIO(buffer)
        
        # Create Discord file
        return discord.File(fp=byte_io, filename="lovecalc.png")

async def setup(bot):
    await bot.add_cog(LoveCalc(bot))
