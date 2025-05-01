# cogs/roblox.py
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import datetime
from typing import Optional
import io

class Roblox(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
    
    async def cog_load(self):
        """Initialize aiohttp session when the cog is loaded"""
        self.session = aiohttp.ClientSession()
        print("Roblox cog loaded")
    
    async def cog_unload(self):
        """Close the aiohttp session when the cog is unloaded"""
        if self.session:
            await self.session.close()
    
    async def get_user_by_username(self, username):
        """Get Roblox user ID from username"""
        try:
            async with self.session.post(
                "https://users.roblox.com/v1/usernames/users",
                json={"usernames": [username], "excludeBannedUsers": False}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data["data"] and len(data["data"]) > 0:
                        return data["data"][0]["id"]
                return None
        except Exception as e:
            print(f"Error in get_user_by_username: {str(e)}")
            return None
    
    async def get_user_info(self, user_id):
        """Get detailed user information"""
        try:
            async with self.session.get(f"https://users.roblox.com/v1/users/{user_id}") as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            print(f"Error in get_user_info: {str(e)}")
            return None
    
    async def get_user_presence(self, user_id):
        """Get user's online status and current activity"""
        try:
            async with self.session.post(
                "https://presence.roblox.com/v1/presence/users",
                json={"userIds": [user_id]}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if "userPresences" in data and len(data["userPresences"]) > 0:
                        return data["userPresences"][0]
                return None
        except Exception as e:
            print(f"Error in get_user_presence: {str(e)}")
            return None
    
    async def get_user_avatar_image(self, user_id):
        """Get user's avatar image as bytes"""
        avatar_url = f"https://www.roblox.com/avatar-thumbnail/image?userId={user_id}&width=420&height=420&format=png"
        try:
            async with self.session.get(avatar_url) as response:
                if response.status == 200:
                    return await response.read()
                return None
        except Exception as e:
            print(f"Error in get_user_avatar_image: {str(e)}")
            return None
    
    async def get_user_friends_count(self, user_id):
        """Get count of user's friends"""
        try:
            async with self.session.get(f"https://friends.roblox.com/v1/users/{user_id}/friends/count") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("count", 0)
                return 0
        except Exception as e:
            print(f"Error in get_user_friends_count: {str(e)}")
            return 0
    
    async def get_user_followers_count(self, user_id):
        """Get count of user's followers"""
        try:
            async with self.session.get(f"https://friends.roblox.com/v1/users/{user_id}/followers/count") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("count", 0)
                return 0
        except Exception as e:
            print(f"Error in get_user_followers_count: {str(e)}")
            return 0
    
    @app_commands.command(name="roblox", description="Look up a Roblox user by username or ID")
    @app_commands.describe(username="Roblox username or user ID")
    async def roblox_lookup(self, interaction: discord.Interaction, username: str):
        """Look up a Roblox user by username or ID"""
        await interaction.response.defer()
        
        user_id = None
        
        # Check if this is a Roblox user ID (all digits)
        if username.isdigit():
            user_id = int(username)
        else:
            # Get user ID from username
            user_id = await self.get_user_by_username(username)
            
            if not user_id:
                await interaction.followup.send(f"Could not find Roblox user with username '{username}'.")
                return
        
        # Get user information
        user_info = await self.get_user_info(user_id)
        if not user_info:
            await interaction.followup.send(f"Could not find Roblox user with ID {user_id}.")
            return
        
        # Get additional information in parallel for efficiency
        tasks = [
            self.get_user_presence(user_id),
            self.get_user_friends_count(user_id),
            self.get_user_followers_count(user_id),
            self.get_user_avatar_image(user_id),
        ]
        
        results = await asyncio.gather(*tasks)
        presence = results[0]
        friends_count = results[1]
        followers_count = results[2]
        avatar_bytes = results[3]
        
        # Create embed
        embed = discord.Embed(
            title=f"Roblox User: {user_info['name']}",
            description=user_info.get("description", "No description") or "No description",
            color=discord.Color.from_rgb(226, 35, 26),  # Roblox red
            timestamp=datetime.datetime.now(),
            url=f"https://www.roblox.com/users/{user_id}/profile"
        )
        
        # Add display name if different from username
        if user_info.get("displayName") and user_info.get("displayName") != user_info["name"]:
            embed.add_field(name="Display Name", value=user_info["displayName"], inline=True)
        
        # Add account badges
        account_badges = []
        if user_info.get("isBanned", False):
            account_badges.append("🚫 Banned")
        if user_info.get("hasVerifiedBadge", False):
            account_badges.append("✓ Verified")
        
        # Check premium status from presence
        if presence and presence.get("premiumMembershipType", 0) > 0:
            account_badges.append("⭐ Premium")
        
        if account_badges:
            embed.add_field(name="Account Badges", value=" | ".join(account_badges), inline=True)
        
        # Add creation date
        if "created" in user_info:
            created_date = datetime.datetime.fromisoformat(user_info["created"].replace("Z", "+00:00"))
            account_age = (datetime.datetime.now(datetime.timezone.utc) - created_date).days
            embed.add_field(name="Account Created", value=f"{created_date.strftime('%Y-%m-%d')} ({account_age} days)", inline=True)
        
        # Add presence information if available
        if presence:
            online_status = presence.get("userPresenceType", 0)
            status_text = "Offline"
            if online_status == 1:
                status_text = "🟢 Online"
            elif online_status == 2:
                status_text = "🎮 In Game"
            elif online_status == 3:
                status_text = "🛠️ In Studio"
            
            embed.add_field(name="Online Status", value=status_text, inline=True)
            
            # If user is in game, show the game
            if online_status == 2 and presence.get("lastLocation"):
                embed.add_field(name="Playing", value=presence["lastLocation"], inline=True)
        
        # Add social stats
        embed.add_field(name="Friends", value=f"{friends_count:,}", inline=True)
        embed.add_field(name="Followers", value=f"{followers_count:,}", inline=True)
        
        # Set footer
        embed.set_footer(text=f"Roblox User ID: {user_id}")
        
        # Add avatar image as attachment if available
        if avatar_bytes:
            file = discord.File(fp=io.BytesIO(avatar_bytes), filename="avatar.png")
            embed.set_thumbnail(url="attachment://avatar.png")
            await interaction.followup.send(embed=embed, file=file)
        else:
            # Fallback to URL if we couldn't download the image
            embed.set_thumbnail(url=f"https://www.roblox.com/avatar-thumbnail/image?userId={user_id}&width=420&height=420&format=png")
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="robloxgroup", description="Look up a Roblox group by ID")
    @app_commands.describe(group_id="Roblox group ID")
    async def roblox_group_lookup(self, interaction: discord.Interaction, group_id: str):
        """Look up a Roblox group by ID"""
        await interaction.response.defer()
        
        if not group_id.isdigit():
            await interaction.followup.send("Group ID must be a number.")
            return
        
        try:
            # Get group information
            async with self.session.get(f"https://groups.roblox.com/v1/groups/{group_id}") as response:
                if response.status != 200:
                    await interaction.followup.send(f"Could not find Roblox group with ID {group_id}.")
                    return
                
                group_info = await response.json()
            
            # Get group members count
            async with self.session.get(f"https://groups.roblox.com/v1/groups/{group_id}/membership") as response:
                if response.status == 200:
                    membership_data = await response.json()
                    members_count = membership_data.get("memberCount", 0)
                else:
                    members_count = "Unknown"
            
            # Create embed
            embed = discord.Embed(
                title=f"Roblox Group: {group_info['name']}",
                description=group_info.get("description", "No description") or "No description",
                color=discord.Color.from_rgb(226, 35, 26),  # Roblox red
                timestamp=datetime.datetime.now(),
                url=f"https://www.roblox.com/groups/{group_id}"
            )
            
            # Add owner info if available
            if group_info.get("owner"):
                owner_name = group_info["owner"].get("username", "Unknown")
                owner_id = group_info["owner"].get("userId", 0)
                embed.add_field(name="Owner", value=f"[{owner_name}](https://www.roblox.com/users/{owner_id}/profile)", inline=True)
            
            # Add member count
            embed.add_field(name="Members", value=f"{members_count:,}", inline=True)
            
            # Add creation date if available
            if "created" in group_info:
                created_date = datetime.datetime.fromisoformat(group_info["created"].replace("Z", "+00:00"))
                embed.add_field(name="Created", value=created_date.strftime("%Y-%m-%d"), inline=True)
            
            # Set footer
            embed.set_footer(text=f"Roblox Group ID: {group_id}")
            
            # Add group icon as thumbnail
            if group_info.get("imageUrl"):
                embed.set_thumbnail(url=group_info["imageUrl"])
            
            await interaction.followup.send(embed=embed)
        
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}")

async def setup(bot):
    await bot.add_cog(Roblox(bot))
