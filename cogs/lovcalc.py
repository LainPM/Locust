# cogs/lovecalc.py
import discord
from discord.ext import commands
from discord import app_commands
import hashlib

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
        
        # Add user avatars
        embed.set_thumbnail(url=user1.display_avatar.url)
        embed.set_footer(text=f"Requested by {interaction.user.display_name}", 
                         icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
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

async def setup(bot):
    await bot.add_cog(LoveCalc(bot))
