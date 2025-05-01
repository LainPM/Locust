# cogs/lovecalc.py
import discord
from discord.ext import commands
from discord import app_commands
import hashlib
import aiohttp
import io
from PIL import Image, ImageDraw, ImageFont
import asyncio

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
        
        # Create composite image with both avatars and a heart
        image_file = await self.create_love_image(user1, user2, love_percentage)
        
        # Set footer with requester info
        embed.set_footer(text=f"Requested by {interaction.user.display_name}", 
                         icon_url=interaction.user.display_avatar.url)
        
        # Send the message with the image
        await interaction.followup.send(embed=embed, file=image_file)
    
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
        # Using modulo would skew distribution, so we use a better scaling method
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
        """Create an image with both user avatars and a heart in the middle"""
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
        
        # Create avatar images from bytes
        avatar1 = Image.open(io.BytesIO(avatar_bytes1)).convert("RGBA")
        avatar2 = Image.open(io.BytesIO(avatar_bytes2)).convert("RGBA")
        
        # Resize avatars
        avatar_size = 180
        avatar1 = avatar1.resize((avatar_size, avatar_size))
        avatar2 = avatar2.resize((avatar_size, avatar_size))
        
        # Create a circular mask for avatars
        mask = Image.new("L", (avatar_size, avatar_size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
        
        # Apply mask to avatars to make them circular
        avatar1.putalpha(mask)
        avatar2.putalpha(mask)
        
        # Create new image with transparent background
        image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        
        # Draw avatars on the image
        image.paste(avatar1, (40, 10), avatar1)
        image.paste(avatar2, (width - avatar_size - 40, 10), avatar2)
        
        # Create heart shape between avatars
        heart_size = 120
        heart_pos_x = (width - heart_size) // 2
        heart_pos_y = (height - heart_size) // 2
        
        # Draw heart shape
        heart = Image.new("RGBA", (heart_size, heart_size), (255, 255, 255, 0))
        heart_draw = ImageDraw.Draw(heart)
        
        # Get heart color based on percentage
        if percentage < 20:
            heart_color = (255, 0, 0, 255)  # Red
        elif percentage < 40:
            heart_color = (255, 127, 0, 255)  # Orange
        elif percentage < 60:
            heart_color = (255, 255, 0, 255)  # Yellow
        elif percentage < 80:
            heart_color = (127, 255, 0, 255)  # Light green
        elif percentage < 100:
            heart_color = (0, 255, 0, 255)  # Green
        else:
            heart_color = (255, 0, 255, 255)  # Purple
        
        # Draw heart (simple method)
        heart_draw.pieslice((0, 0, heart_size//2, heart_size//2), 180, 270, fill=heart_color)
        heart_draw.pieslice((heart_size//2, 0, heart_size, heart_size//2), 270, 360, fill=heart_color)
        heart_draw.polygon([
            (0, heart_size//4),
            (heart_size//2, heart_size),
            (heart_size, heart_size//4)
        ], fill=heart_color)
        
        # Add percentage text to heart
        try:
            # Try to add text with default font
            font_size = 24
            try:
                # Try to use TrueType font if available
                font = ImageFont.truetype("arial.ttf", font_size)
            except IOError:
                # Fallback to default font
                font = ImageFont.load_default()
            
            # Use newer getbbox for modern PIL or fall back to simpler positioning
            try:
                bbox = heart_draw.textbbox((0, 0), f"{percentage}%", font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            except AttributeError:
                # For older PIL versions
                try:
                    text_width, text_height = heart_draw.textsize(f"{percentage}%", font=font)
                except:
                    # Just use estimates if all else fails
                    text_width, text_height = len(f"{percentage}%") * 10, 20
                
            # Draw the text
            heart_draw.text(
                ((heart_size - text_width) // 2, (heart_size - text_height) // 2 - 10),
                f"{percentage}%",
                font=font,
                fill=(255, 255, 255, 255)
            )
        except Exception as e:
            print(f"Failed to add text to love image: {e}")
            # If any issues occur, skip text on image
        
        # Paste heart onto main image
        image.paste(heart, (heart_pos_x, heart_pos_y), heart)
        
        # Convert image to bytes for Discord
        byte_arr = io.BytesIO()
        image.save(byte_arr, format="PNG")
        byte_arr.seek(0)
        
        # Create Discord file
        return discord.File(fp=byte_arr, filename="lovecalc.png")

async def setup(bot):
    await bot.add_cog(LoveCalc(bot))
