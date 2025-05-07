# systems/utility/roblox.py
import discord
import aiohttp
import io
from typing import Dict, List, Any, Optional, Tuple

class RobloxLookup:
    """Component for Roblox user and group lookup"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        self.base_url = "https://api.roblox.com/"
        self.users_base_url = "https://users.roblox.com/v1/"
        self.thumbnails_url = "https://thumbnails.roblox.com/v1/"
        self.groups_url = "https://groups.roblox.com/v1/"
    
    async def initialize(self) -> bool:
        """Initialize the component"""
        return True
    
    async def lookup_user(self, username_or_id: str) -> Tuple[Optional[discord.Embed], List[discord.File]]:
        """Look up a Roblox user by username or ID"""
        user_id = None
        
        try:
            # Check if input is a user ID
            if username_or_id.isdigit():
                user_id = int(username_or_id)
                user_info = await self._get_user_by_id(user_id)
            else:
                # Look up by username
                user_id = await self._get_user_id_by_name(username_or_id)
                if user_id:
                    user_info = await self._get_user_by_id(user_id)
                else:
                    return None, []
            
            if not user_info:
                return None, []
            
            # Get additional information
            avatar_url = await self._get_avatar_url(user_id)
            
            # Create embed
            embed = discord.Embed(
                title=f"Roblox User: {user_info.get('name', 'Unknown')}",
                url=f"https://www.roblox.com/users/{user_id}/profile",
                color=discord.Color.red()
            )
            
            # Add user info
            embed.add_field(name="Display Name", value=user_info.get('displayName', 'Unknown'), inline=True)
            embed.add_field(name="User ID", value=str(user_id), inline=True)
            
            if 'created' in user_info:
                created_at = user_info['created'].split('T')[0]  # Extract date part
                embed.add_field(name="Account Created", value=created_at, inline=True)
            
            if 'description' in user_info and user_info['description']:
                embed.add_field(name="Description", value=user_info['description'][:1024], inline=False)
            
            # Set thumbnail
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)
            
            # Download avatar for file attachment
            files = []
            if avatar_url:
                avatar_data = await self._download_image(avatar_url)
                if avatar_data:
                    avatar_file = discord.File(avatar_data, filename="roblox_avatar.png")
                    files.append(avatar_file)
            
            return embed, files
            
        except Exception as e:
            print(f"Error looking up Roblox user: {e}")
            return None, []
    
    async def lookup_group(self, group_id: str) -> Tuple[Optional[discord.Embed], Optional[discord.File]]:
        """Look up a Roblox group by ID"""
        try:
            # Make sure group_id is a number
            if not group_id.isdigit():
                return None, None
                
            group_id = int(group_id)
            
            # Get group info
            group_info = await self._get_group_info(group_id)
            if not group_info:
                return None, None
            
            # Get group icon
            icon_url = await self._get_group_icon(group_id)
            
            # Create embed
            embed = discord.Embed(
                title=f"Roblox Group: {group_info.get('name', 'Unknown')}",
                url=f"https://www.roblox.com/groups/{group_id}",
                color=discord.Color.blue()
            )
            
            # Add group info
            embed.add_field(name="Group ID", value=str(group_id), inline=True)
            embed.add_field(name="Member Count", value=str(group_info.get('memberCount', 'Unknown')), inline=True)
            
            if 'owner' in group_info and group_info['owner']:
                embed.add_field(name="Owner", value=group_info['owner'].get('username', 'Unknown'), inline=True)
            
            if 'description' in group_info and group_info['description']:
                embed.add_field(name="Description", value=group_info['description'][:1024], inline=False)
            
            # Set thumbnail
            if icon_url:
                embed.set_thumbnail(url=icon_url)
            
            # Download icon for file attachment
            icon_file = None
            if icon_url:
                icon_data = await self._download_image(icon_url)
                if icon_data:
                    icon_file = discord.File(icon_data, filename="group_icon.png")
            
            return embed, icon_file
            
        except Exception as e:
            print(f"Error looking up Roblox group: {e}")
            return None, None
    
    async def _get_user_id_by_name(self, username: str) -> Optional[int]:
        """Get user ID from username"""
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}users/get-by-username?username={username}"
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    
                    data = await resp.json()
                    if 'Id' in data:
                        return data['Id']
                    return None
            except Exception as e:
                print(f"Error getting user ID: {e}")
                return None
    
    async def _get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information by ID"""
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.users_base_url}users/{user_id}"
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    
                    return await resp.json()
            except Exception as e:
                print(f"Error getting user info: {e}")
                return None
    
    async def _get_avatar_url(self, user_id: int) -> Optional[str]:
        """Get user avatar URL"""
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.thumbnails_url}users/avatar-headshot?userIds={user_id}&size=420x420&format=Png"
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    
                    data = await resp.json()
                    if 'data' in data and data['data']:
                        return data['data'][0].get('imageUrl')
                    return None
            except Exception as e:
                print(f"Error getting avatar URL: {e}")
                return None
    
    async def _get_group_info(self, group_id: int) -> Optional[Dict[str, Any]]:
        """Get group information by ID"""
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.groups_url}groups/{group_id}"
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    
                    return await resp.json()
            except Exception as e:
                print(f"Error getting group info: {e}")
                return None
    
    async def _get_group_icon(self, group_id: int) -> Optional[str]:
        """Get group icon URL"""
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.thumbnails_url}groups/icons?groupIds={group_id}&size=420x420&format=Png"
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    
                    data = await resp.json()
                    if 'data' in data and data['data']:
                        return data['data'][0].get('imageUrl')
                    return None
            except Exception as e:
                print(f"Error getting group icon: {e}")
                return None
    
    async def _download_image(self, url: str) -> Optional[io.BytesIO]:
        """Download image from URL"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    
                    data = await resp.read()
                    return io.BytesIO(data)
            except Exception as e:
                print(f"Error downloading image: {e}")
                return None
