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
    
    async def get_user_status(self, user_id):
        """Get user's status/about me"""
        try:
            async with self.session.get(f"https://users.roblox.com/v1/users/{user_id}/status") as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            print(f"Error in get_user_status: {str(e)}")
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
    
    async def get_user_full_avatar(self, user_id):
        """Get user's full avatar image as bytes"""
        avatar_url = f"https://www.roblox.com/outfit-thumbnail/image?userOutfitId={user_id}&width=420&height=420&format=png"
        try:
            async with self.session.get(avatar_url) as response:
                if response.status == 200:
                    return await response.read()
                return None
        except Exception as e:
            print(f"Error in get_user_full_avatar: {str(e)}")
            return None
    
    async def get_user_badges(self, user_id):
        """Get count of user's badges"""
        try:
            async with self.session.get(f"https://badges.roblox.com/v1/users/{user_id}/badges?limit=1&sortOrder=Asc") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("totalCount", 0)
                return 0
        except Exception as e:
            print(f"Error in get_user_badges: {str(e)}")
            return 0
    
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
    
    async def get_user_following_count(self, user_id):
        """Get count of users the user is following"""
        try:
            async with self.session.get(f"https://friends.roblox.com/v1/users/{user_id}/followings/count") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("count", 0)
                return 0
        except Exception as e:
            print(f"Error in get_user_following_count: {str(e)}")
            return 0
    
    async def get_user_groups(self, user_id):
        """Get user's groups"""
        try:
            async with self.session.get(f"https://groups.roblox.com/v2/users/{user_id}/groups/roles") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", [])
                return []
        except Exception as e:
            print(f"Error in get_user_groups: {str(e)}")
            return []
    
    async def get_premium_info(self, user_id):
        """Get user's premium membership info"""
        try:
            async with self.session.get(f"https://premiumfeatures.roblox.com/v1/users/{user_id}/validate-membership") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("isPremium", False)
                return False
        except Exception as e:
            print(f"Error in get_premium_info: {str(e)}")
            return False
    
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
        
        # Get additional information in parallel
        tasks = [
            self.get_user_status(user_id),
            self.get_user_presence(user_id),
            self.get_user_badges(user_id),
            self.get_user_friends_count(user_id),
            self.get_user_followers_count(user_id),
            self.get_user_following_count(user_id),
            self.get_user_groups(user_id),
            self.get_user_avatar_image(user_id),
            self.get_user_full_avatar(user_id),
            self.get_premium_info(user_id)
        ]
        
        results = await asyncio.gather(*tasks)
        status = results[0]
        presence = results[1]
        badges_count = results[2]
        friends_count = results[3]
        followers_count = results[4]
        following_count = results[5]
        groups = results[6]
        avatar_bytes = results[7]
        full_avatar_bytes = results[8]
        is_premium = results[9]
        
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
        if is_premium or (presence and presence.get("premiumMembershipType", 0) > 0):
            account_badges.append("⭐ Premium")
        
        if account_badges:
            embed.add_field(name="Account Badges", value=" | ".join(account_badges), inline=True)
        
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
                embed.add_field(name="Currently Playing", value=presence["lastLocation"], inline=True)
        
        # Add creation date
        if "created" in user_info:
            created_date = datetime.datetime.fromisoformat(user_info["created"].replace("Z", "+00:00"))
            account_age = (datetime.datetime.now(datetime.timezone.utc) - created_date).days
            years = account_age // 365
            months = (account_age % 365) // 30
            
            if years > 0:
                age_text = f"{years} year{'s' if years != 1 else ''}"
                if months > 0:
                    age_text += f", {months} month{'s' if months != 1 else ''}"
            else:
                age_text = f"{months} month{'s' if months != 1 else ''}" if months > 0 else f"{account_age} day{'s' if account_age != 1 else ''}"
                
            embed.add_field(
                name="Account Age", 
                value=f"Created: {created_date.strftime('%b %d, %Y')}\nAge: {age_text}", 
                inline=True
            )
        
        # Add status if available
        if status and status.get("status"):
            embed.add_field(name="Status", value=status["status"], inline=False)
        
        # Add social statistics
        embed.add_field(name="Friends", value=f"{friends_count:,}", inline=True)
        embed.add_field(name="Followers", value=f"{followers_count:,}", inline=True)
        embed.add_field(name="Following", value=f"{following_count:,}", inline=True)
        embed.add_field(name="Badges", value=f"{badges_count:,}", inline=True)
        
        # Group memberships
        if groups:
            group_text = []
            for i, group_data in enumerate(groups[:5]):  # Show up to 5 groups
                group = group_data.get("group", {})
                role = group_data.get("role", {})
                group_name = group.get("name", "Unknown Group")
                role_name = role.get("name", "Member")
                
                # Add rank number if higher than 1
                rank = role.get("rank", 0)
                rank_display = f" (Rank: {rank})" if rank > 1 else ""
                
                group_text.append(f"{i+1}. {group_name} - {role_name}{rank_display}")
            
            embed.add_field(
                name=f"Groups ({len(groups)})",
                value="\n".join(group_text) if group_text else "Not in any groups",
                inline=False
            )
        
        # Set footer
        embed.set_footer(text=f"Roblox User ID: {user_id}")
        
        # Prepare files for sending
        files = []
        
        # Add avatar as thumbnail
        if avatar_bytes:
            avatar_file = discord.File(fp=io.BytesIO(avatar_bytes), filename="avatar.png")
            files.append(avatar_file)
            embed.set_thumbnail(url="attachment://avatar.png")
        
        # Add full avatar as image if available
        if full_avatar_bytes:
            full_avatar_file = discord.File(fp=io.BytesIO(full_avatar_bytes), filename="full_avatar.png")
            files.append(full_avatar_file)
            embed.set_image(url="attachment://full_avatar.png")
        
        # Send the message with files
        if files:
            await interaction.followup.send(embed=embed, files=files)
        else:
            # Fallback to URLs if we couldn't download the images
            embed.set_thumbnail(url=f"https://www.roblox.com/avatar-thumbnail/image?userId={user_id}&width=420&height=420&format=png")
            embed.set_image(url=f"https://www.roblox.com/outfit-thumbnail/image?userOutfitId={user_id}&width=420&height=420&format=png")
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
            
            # Get more accurate member count from Roblox API
            async with self.session.get(f"https://groups.roblox.com/v1/groups/{group_id}/membership") as response:
                if response.status == 200:
                    membership_data = await response.json()
                    members_count = membership_data.get("memberCount", "Unknown")
                else:
                    # Fallback to the count from group_info
                    members_count = group_info.get("memberCount", "Unknown")
            
            # Get group roles
            async with self.session.get(f"https://groups.roblox.com/v1/groups/{group_id}/roles") as response:
                if response.status == 200:
                    roles_data = await response.json()
                    roles = roles_data.get("roles", [])
                else:
                    roles = []
            
            # Get group games
            async with self.session.get(f"https://games.roblox.com/v2/groups/{group_id}/games?accessFilter=Public&limit=10&sortOrder=Desc") as response:
                if response.status == 200:
                    games_data = await response.json()
                    games = games_data.get("data", [])
                else:
                    games = []
            
            # Get group icon image
            group_icon_url = None
            if group_info.get("imageUrl"):
                group_icon_url = group_info["imageUrl"]
                
                try:
                    async with self.session.get(group_icon_url) as response:
                        if response.status == 200:
                            group_icon_bytes = await response.read()
                        else:
                            group_icon_bytes = None
                except:
                    group_icon_bytes = None
            else:
                group_icon_bytes = None
            
            # Create embed
            embed = discord.Embed(
                title=f"Roblox Group: {group_info['name']}",
                description=group_info.get("description", "No description") or "No description",
                color=discord.Color.from_rgb(226, 35, 26),  # Roblox red
                timestamp=datetime.datetime.now(),
                url=f"https://www.roblox.com/groups/{group_id}/group"
            )
            
            # Add owner info if available
            if group_info.get("owner"):
                owner_name = group_info["owner"].get("username", "Unknown")
                owner_id = group_info["owner"].get("userId", 0)
                embed.add_field(name="👑 Owner", value=f"[{owner_name}](https://www.roblox.com/users/{owner_id}/profile)", inline=True)
            else:
                embed.add_field(name="👑 Owner", value="No owner (owned by Roblox)", inline=True)
            
            # Add member count
            embed.add_field(name="👥 Members", value=f"{members_count:,}", inline=True)
            
            # Add creation date if available
            if "created" in group_info:
                created_date = datetime.datetime.fromisoformat(group_info["created"].replace("Z", "+00:00"))
                embed.add_field(name="📅 Created", value=created_date.strftime("%b %d, %Y"), inline=True)
            
            # Add group status (public/private)
            is_public = "Yes" if group_info.get("publicEntryAllowed", False) else "No"
            embed.add_field(name="🔐 Public Entry", value=is_public, inline=True)
            
            # Add group shout if available
            if group_info.get("shout") and group_info["shout"].get("body"):
                shout_text = group_info["shout"]["body"]
                shout_poster = group_info["shout"]["poster"]["username"]
                shout_date = datetime.datetime.fromisoformat(group_info["shout"]["updated"].replace("Z", "+00:00"))
                
                # Limit shout text to avoid excessive length
                if len(shout_text) > 200:
                    shout_text = shout_text[:197] + "..."
                
                embed.add_field(
                    name="📢 Group Shout",
                    value=f'"{shout_text}"\n— {shout_poster} on {shout_date.strftime("%b %d, %Y")}',
                    inline=False
                )
            
            # Add group roles
            if roles:
                roles_text = []
                for role in roles:
                    role_name = role.get("name", "Unknown")
                    role_rank = role.get("rank", 0)
                    roles_text.append(f"{role_name} (Rank: {role_rank})")
                
                embed.add_field(
                    name=f"👥 Roles ({len(roles)})",
                    value="\n".join(roles_text[:5]) if roles_text else "None",
                    inline=False
                )
                
                if len(roles) > 5:
                    embed.add_field(name="", value=f"*and {len(roles) - 5} more roles...*", inline=False)
            
            # Add group games if available
            if games:
                games_text = []
                for game in games[:3]:  # Show up to 3 games
                    game_name = game.get("name", "Unknown Game")
                    game_visits = game.get("placeVisits", 0)
                    games_text.append(f"{game_name} - {game_visits:,} visits")
                
                if games_text:
                    embed.add_field(
                        name=f"🎮 Group Games ({len(games)})",
                        value="\n".join(games_text),
                        inline=False
                    )
            
            # Set footer
            embed.set_footer(text=f"Roblox Group ID: {group_id}")
            
            # Send with icon as attachment if available
            if group_icon_bytes:
                file = discord.File(fp=io.BytesIO(group_icon_bytes), filename="group_icon.png")
                embed.set_thumbnail(url="attachment://group_icon.png")
                await interaction.followup.send(embed=embed, file=file)
            else:
                # Fallback to URL if we couldn't download the image
                if group_icon_url:
                    embed.set_thumbnail(url=group_icon_url)
                await interaction.followup.send(embed=embed)
        
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}")

async def setup(bot):
    await bot.add_cog(Roblox(bot))
