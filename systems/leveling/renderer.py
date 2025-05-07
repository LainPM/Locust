# systems/leveling/renderer.py
import discord
import io
import aiohttp
import numpy as np
import cv2  # We'll still use OpenCV but in a more modular way
import re
import base64
from typing import Dict, Any

class RankCardRenderer:
    """Handles generating rank card images"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
    
    def hex_to_bgr(self, hex_color: str) -> tuple:
        """Convert hex color to BGR format (for OpenCV)"""
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return (b, g, r)
    
    def is_valid_hex_color(self, color: str) -> bool:
        """Check if a string is a valid hex color"""
        pattern = r'^#?([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$'
        return bool(re.match(pattern, color))
    
    async def create_rank_card(self, user, user_data, rank, guild):
        """Create a rank card image using OpenCV"""
        # Get user profile settings
        profile = await self.system.storage.get_user_profile(user.id, guild.id)
        
        # Image dimensions
        width = 800
        height = 200
        
        try:
            # Create a blank image with alpha channel
            image = np.zeros((height, width, 4), dtype=np.uint8)
            
            # Handle background (simplified for this example)
            bg_color = self.hex_to_bgr(profile["background_color"])
            image[:, :] = (*bg_color, 255)
            
            # Download user avatar
            async with aiohttp.ClientSession() as session:
                avatar_url = str(user.display_avatar.url)
                async with session.get(avatar_url) as resp:
                    avatar_bytes = await resp.read()
            
            # Create avatar image from bytes
            avatar_arr = np.asarray(bytearray(avatar_bytes), dtype=np.uint8)
            avatar = cv2.imdecode(avatar_arr, cv2.IMREAD_COLOR)
            
            # Resize avatar (simplified version)
            avatar_size = 130
            avatar = cv2.resize(avatar, (avatar_size, avatar_size))
            
            # Add circular mask for avatar (simplified)
            avatar = cv2.cvtColor(avatar, cv2.COLOR_BGR2BGRA)
            mask = np.zeros((avatar_size, avatar_size), dtype=np.uint8)
            cv2.circle(mask, (avatar_size//2, avatar_size//2), avatar_size//2, 255, -1)
            
            # Apply basic overlay on main image (simplified)
            avatar_pos = (30, 35)
            for c in range(3):
                avatar[:, :, c] = cv2.bitwise_and(avatar[:, :, c], avatar[:, :, c], mask=mask)
            avatar[:, :, 3] = mask
            
            # Place avatar on card (simplified)
            for y in range(avatar_size):
                for x in range(avatar_size):
                    if avatar[y, x, 3] > 0:
                        if 0 <= avatar_pos[1] + y < height and 0 <= avatar_pos[0] + x < width:
                            image[avatar_pos[1] + y, avatar_pos[0] + x] = avatar[y, x]
            
            # Add text elements (simplified)
            font = cv2.FONT_HERSHEY_SIMPLEX
            text_color = self.hex_to_bgr(profile["text_color"])
            
            # Username
            cv2.putText(image, user.display_name, (180, 65), font, 1.0, (*text_color, 255), 2)
            
            # Level info
            level = user_data["level"]
            xp = user_data["xp"]
            cv2.putText(image, f"Level: {level}", (180, 100), font, 0.8, (*text_color, 255), 2)
            cv2.putText(image, f"Rank: #{rank}", (550, 65), font, 0.8, (*text_color, 255), 2)
            
            # Progress bar (simplified)
            current_level_xp = self.system.storage.calculate_xp_for_level(level)
            next_level_xp = self.system.storage.calculate_xp_for_level(level + 1)
            progress = ((xp - current_level_xp) / (next_level_xp - current_level_xp)) * 100
            
            # Draw progress bar background
            bar_bg_color = self.hex_to_bgr(profile["progress_bar_background"])
            cv2.rectangle(image, (180, 120), (700, 150), (*bar_bg_color, 255), -1)
            
            # Draw progress bar fill
            fill_width = int((progress / 100) * 520)
            bar_color = self.hex_to_bgr(profile["progress_bar_color"])
            cv2.rectangle(image, (180, 120), (180 + fill_width, 150), (*bar_color, 255), -1)
            
            # XP text
            cv2.putText(image, f"XP: {xp-current_level_xp}/{next_level_xp-current_level_xp}", (400, 170), font, 0.6, (*text_color, 255), 1)
            
            # Convert to file
            _, buffer = cv2.imencode(".png", image)
            byte_io = io.BytesIO(buffer)
            
            return discord.File(fp=byte_io, filename="rank.png")
            
        except Exception as e:
            print(f"Error creating rank card: {e}")
            # Create simple error card
            image = np.zeros((height, width, 4), dtype=np.uint8)
            image[:, :] = (33, 33, 39, 255)  # Dark background
            
            cv2.putText(image, f"Error creating rank card: {str(e)[:50]}", (50, 100), font, 0.7, (255, 255, 255, 255), 1)
            
            _, buffer = cv2.imencode(".png", image)
            byte_io = io.BytesIO(buffer)
            
            return discord.File(fp=byte_io, filename="rank.png")
