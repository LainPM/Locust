# systems/fun/lovecalc.py
import discord
import random
import io
from typing import Tuple, Optional

class LoveCalculator:
    """Simple love calculator component"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
    
    async def calculate(self, user1: discord.User, user2: discord.User) -> Tuple[str, Optional[discord.File]]:
        """Calculate love compatibility between two users"""
        # Use usernames to generate a consistent but random score
        seed = (user1.id + user2.id) % 1000
        random.seed(seed)
        
        # Generate compatibility percentage (50-100% for positivity)
        compatibility = random.randint(50, 100)
        
        # Create the result message
        if compatibility >= 90:
            result = f"💖 **Love Match: {compatibility}%** 💖\n{user1.display_name} and {user2.display_name} are practically soulmates!"
        elif compatibility >= 70:
            result = f"💕 **Love Match: {compatibility}%** 💕\n{user1.display_name} and {user2.display_name} have great chemistry!"
        elif compatibility >= 50:
            result = f"💓 **Love Match: {compatibility}%** 💓\n{user1.display_name} and {user2.display_name} might have something special."
        else:
            result = f"💔 **Love Match: {compatibility}%** 💔\n{user1.display_name} and {user2.display_name} might be better as friends."
        
        # No image file for now, returning None as the file
        return result, None
