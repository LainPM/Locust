# cogs/roblox.py
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import datetime
import re
from typing import Optional, List, Dict, Any
import io

class Roblox(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.brand_color = discord.Color.from_rgb(226, 35, 26)  # Roblox red
    
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
        """Get user's full body avatar image"""
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
    
    async def get_user_followings_count(self, user_id):
        """Get count of users the user is following"""
        try:
            async with self.session.get(f"https://friends.roblox.com/v1/users/{user_id}/followings/count") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("count", 0)
                return 0
        except Exception as e:
            print(f"Error in get_user_followings_count: {str(e)}")
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
    
    async def get_user_experiences(self, user_id):
        """Get user's created experiences/games"""
        try:
            async with self.session.get(
                f"https://games.roblox.com/v2/users/{user_id}/games?accessFilter=Public&limit=10&sortOrder=Desc"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", [])
                return []
        except Exception as e:
            print(f"Error in get_user_experiences: {str(e)}")
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
    
    async def get_favorite_games(self, user_id):
        """Get user's favorite games"""
        try:
            async with self.session.get(
                f"https://games.roblox.com/v2/users/{user_id}/favorite/games?accessFilter=All&sortOrder=Desc&limit=5"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", [])
                return []
        except Exception as e:
            print(f"Error in get_favorite_games: {str(e)}")
            return []
    
    async def scrape_profile_stats(self, user_id):
        """Scrape profile page to get place visits and profile views"""
        try:
            # This is a fallback method that tries to get data from the HTML page
            # It's not recommended for production use as it relies on page structure
            profile_url = f"https://www.roblox.com/users/{user_id}/profile"
            async with self.session.get(profile_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }) as response:
                if response.status != 200:
                    return {"profile_views": "Unknown", "place_visits": "Unknown"}
                
                html = await response.text()
                
                # These patterns might break if Roblox changes their website
                profile_views_match = re.search(r'Profile Views:\s*([0-9,]+)', html)
                place_visits_match = re.search(r'Place Visits:\s*([0-9,]+)', html)
                
                profile_views = profile_views_match.group(1) if profile_views_match else "Unknown"
                place_visits = place_visits_match.group(1) if place_visits_match else "Unknown"
                
                return {"profile_views": profile_views, "place_visits": place_visits}
        except Exception as e:
            print(f"Error in scrape_profile_stats: {str(e)}")
            return {"profile_views": "Not available", "place_visits": "Not available"}
    
    async def get_group_icon(self, group_id):
        """Get the group's icon image"""
        try:
            async with self.session.get(f"https://thumbnails.roblox.com/v1/groups/icons?groupIds={group_id}&size=150x150&format=Png") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("data") and len(data["data"]) > 0:
                        icon_url = data["data"][0].get("imageUrl")
                        if icon_url:
                            async with self.session.get(icon_url) as img_response:
                                if img_response.status == 200:
                                    return await img_response.read()
                return None
        except Exception as e:
            print(f"Error in get_group_icon: {str(e)}")
            return None
    
    @app_commands.command(name="roblox", description="Look up a Roblox user by username or ID")
    @app_commands.describe(username="Roblox username or user ID")
    async def roblox_lookup(self, interaction: discord.Interaction, username: str):
        """Look up a Roblox user by username or ID with enhanced details"""
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
            self.get_user_status(user_id),
            self.get_user_presence(user_id),
            self.get_user_badges(user_id),
            self.get_user_friends_count(user_id),
            self.get_user_followers_count(user_id),
            self.get_user_followings_count(user_id),
            self.get_user_groups(user_id),
            self.get_user_experiences(user_id),
            self.get_user_avatar_image(user_id),
            self.get_user_full_avatar(user_id),
            self.get_premium_info(user_id),
            self.get_favorite_games(user_id),
            self.scrape_profile_stats(user_id)
        ]
        
        results = await asyncio.gather(*tasks)
        status = results[0]
        presence = results[1]
        badges_count = results[2]
        friends_count = results[3]
        followers_count = results[4]
        followings_count = results[5]
        groups = results[6]
        experiences = results[7]
        avatar_bytes = results[8]
        full_avatar_bytes = results[9]
        is_premium = results[10]
        favorite_games = results[11]
        profile_stats = results[12]
        
        # Create embed with rich details
        embed = discord.Embed(
            title=f"📊 Roblox Profile: {user_info['name']}",
            description="",
            color=self.brand_color,
            timestamp=datetime.datetime.now(),
            url=f"https://www.roblox.com/users/{user_id}/profile"
        )
        
        # Add header information
        display_name = user_info.get("displayName", user_info["name"])
        if display_name != user_info["name"]:
            embed.add_field(name="Display Name", value=display_name, inline=True)
        
        # Account badges section
        badges = []
        if user_info.get("isBanned", False):
            badges.append("🚫 Banned")
        if user_info.get("hasVerifiedBadge", False):
            badges.append("✅ Verified")
        if is_premium or (presence and presence.get("premiumMembershipType", 0) > 0):
            badges.append("⭐ Premium")
        
        if badges:
            embed.add_field(name="Account Status", value=" | ".join(badges), inline=True)
        
        # Online status section
        if presence:
            online_status = presence.get("userPresenceType", 0)
            status_text = "🔴 Offline"
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
        
        # Creation date in a nice format
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
                value=f"**Created:** {created_date.strftime('%b %d, %Y')}\n**Age:** {age_text} old", 
                inline=True
            )
        
        # Add status if available
        if status and status.get("status"):
            embed.add_field(name="Status", value=f""{status['status']}"", inline=False)
        
        # Add bio/description if available
        if user_info.get("description"):
            # Limit description to 300 characters to avoid huge embeds
            desc = user_info["description"]
            if len(desc) > 300:
                desc = desc[:297] + "..."
            embed.add_field(name="About Me", value=desc, inline=False)
        
        # Add social statistics
        embed.add_field(name="👥 Friends", value=f"{friends_count:,}", inline=True)
        embed.add_field(name="👀 Followers", value=f"{followers_count:,}", inline=True)
        embed.add_field(name="👤 Following", value=f"{followings_count:,}", inline=True)
        embed.add_field(name="🏆 Badges", value=f"{badges_count:,}", inline=True)
        
        # Add profile views and place visits if available
        if profile_stats:
            embed.add_field(name="👁️ Profile Views", value=profile_stats["profile_views"], inline=True)
            embed.add_field(name="🚶 Place Visits", value=profile_stats["place_visits"], inline=True)
        
        # Group memberships
        if groups:
            group_text = []
            for i, group_data in enumerate(groups[:5]):
                group = group_data.get("group", {})
                role = group_data.get("role", {})
                group_name = group.get("name", "Unknown Group")
                role_name = role.get("name", "Member")
                
                # Add rank number if higher than 1
                rank = role.get("rank", 0)
                rank_display = f" (Rank: {rank})" if rank > 1 else ""
                
                group_text.append(f"{i+1}. **{group_name}** - {role_name}{rank_display}")
            
            embed.add_field(
                name=f"📋 Groups ({len(groups)})",
                value="\n".join(group_text) if group_text else "Not in any groups",
                inline=False
            )
        
        # Created games/experiences
        if experiences:
            games_text = []
            total_visits = 0
            for i, exp in enumerate(experiences[:3]):
                name = exp.get("name", "Unnamed Game")
                visits = exp.get("placeVisits", 0)
                total_visits += visits
                games_text.append(f"{i+1}. **{name}** - {visits:,} visits")
            
            if games_text:
                embed.add_field(
                    name=f"🎮 Created Experiences ({len(experiences)})",
                    value=f"Total Visits: {total_visits:,}\n" + "\n".join(games_text),
                    inline=False
                )
        
        # Favorite games if available
        if favorite_games:
            fav_text = []
            for i, game in enumerate(favorite_games[:3]):
                name = game.get("name", "Unknown Game")
                fav_text.append(f"{i+1}. **{name}**")
            
            if fav_text:
                embed.add_field(
                    name=f"❤️ Favorite Games ({len(favorite_games)})",
                    value="\n".join(fav_text),
                    inline=False
                )
        
        # Set footer with user ID for reference
        embed.set_footer(text=f"Roblox User ID: {user_id} • Powered by Roblox API")
        
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
        """Look up a Roblox group by ID with enhanced details"""
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
            
            # Get parallel data
            tasks = [
                # Try the primary method for member count
                self.session.get(f"https://groups.roblox.com/v1/groups/{group_id}/membership"),
                # Backup method for member count
                self.session.get(f"https://groups.roblox.com/v1/groups/{group_id}"),
                # Get roles in the group
                self.session.get(f"https://groups.roblox.com/v1/groups/{group_id}/roles"),
                # Get group wall posts
                self.session.get(f"https://groups.roblox.com/v2/groups/{group_id}/wall/posts?limit=10&sortOrder=Desc"),
                # Get group games
                self.session.get(f"https://games.roblox.com/v2/groups/{group_id}/games?accessFilter=Public&limit=10&sortOrder=Desc"),
                # Get group audit log (need additional permissions, may not work)
                self.session.get(f"https://groups.roblox.com/v1/groups/{group_id}/audit-log?actionType=All&limit=10&sortOrder=Desc"),
                # Get group icon
                self.get_group_icon(group_id)
            ]
            
            # Use gather to run all tasks in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results - catch exceptions along the way
            membership_data = None
            roles_data = None
            wall_data = None
            games_data = None
            audit_data = None
            group_icon_bytes = None
            
            # Process membership data
            try:
                if not isinstance(results[0], Exception) and results[0].status == 200:
                    membership_data = await results[0].json()
            except:
                pass
            
            # Process backup membership data from group info
            try:
                if not isinstance(results[1], Exception) and results[1].status == 200:
                    backup_data = await results[1].json()
            except:
                backup_data = None
            
            # Process roles
            try:
                if not isinstance(results[2], Exception) and results[2].status == 200:
                    roles_data = await results[2].json()
            except:
                pass
            
            # Process wall
            try:
                if not isinstance(results[3], Exception) and results[3].status == 200:
                    wall_data = await results[3].json()
            except:
                pass
            
            # Process games
            try:
                if not isinstance(results[4], Exception) and results[4].status == 200:
                    games_data = await results[4].json()
            except:
                pass
            
            # Process audit data
            try:
                if not isinstance(results[5], Exception) and results[5].status == 200:
                    audit_data = await results[5].json()
            except:
                pass
            
            # Process group icon
            if not isinstance(results[6], Exception):
                group_icon_bytes = results[6]
            
            # Extract member count - try both methods
            if membership_data and "memberCount" in membership_data:
                members_count = membership_data.get("memberCount", 0)
            elif backup_data and "memberCount" in backup_data:
                members_count = backup_data.get("memberCount", 0)
            else:
                # As a last resort, try to extract from the original group_info
                members_count = group_info.get("memberCount", "Unknown")
                if not isinstance(members_count, (int, str)):
                    members_count = "Unknown"
            
            # Create embed with rich details
            embed = discord.Embed(
                title=f"🏢 Roblox Group: {group_info['name']}",
                description=group_info.get("description", "No description") or "No description",
                color=self.brand_color,
                timestamp=datetime.datetime.now(),
                url=f"https://www.roblox.com/groups/{group_id}/group#!/about"
            )
            
            # Add owner info if available
            if group_info.get("owner"):
                owner_name = group_info["owner"].get("username", "Unknown")
                owner_id = group_info["owner"].get("userId", 0)
                embed.add_field(
                    name="👑 Owner", 
                    value=f"[{owner_name}](https://www.roblox.com/users/{owner_id}/profile)", 
                    inline=True
                )
            else:
                embed.add_field(name="👑 Owner", value="No owner (owned by Roblox)", inline=True)
            
            # Add member count
            embed.add_field(name="👥 Members", value=f"{members_count:,}", inline=True)
            
            # Add creation date if available
            if "created" in group_info:
                created_date = datetime.datetime.fromisoformat(group_info["created"].replace("Z", "+00:00"))
                days_old = (datetime.datetime.now(datetime.timezone.utc) - created_date).days
                years = days_old // 365
                months = (days_old % 365) // 30
                
                if years > 0:
                    age_text = f"{years} year{'s' if years != 1 else ''}"
                    if months > 0:
                        age_text += f", {months} month{'s' if months != 1 else ''}"
                else:
                    age_text = f"{months} month{'s' if months != 1 else ''}" if months > 0 else f"{days_old} day{'s' if days_old != 1 else ''}"
                
                embed.add_field(
                    name="📅 Age", 
                    value=f"**Created:** {created_date.strftime('%b %d, %Y')}\n**Age:** {age_text} old", 
                    inline=True
                )
            
            # Add group status (public/private)
            is_public = "✅ Public" if group_info.get("publicEntryAllowed", False) else "🔒 Private"
            embed.add_field(name="🔐 Entry", value=is_public, inline=True)
            
            # Add group shout if available
            if group_info.get("shout") and group_info["shout"].get("body"):
                shout_text = group_info["shout"]["body"]
                shout_poster = group_info["shout"]["poster"]["username"]
                shout_date = datetime.datetime.fromisoformat(group_info["shout"]["updated"].replace("Z", "+00:00"))
                
                # Limit shout text to 200 characters
                if len(shout_text) > 200:
                    shout_text = shout_text[:197] + "..."
                
                embed.add_field(
                    name="📢 Group Shout",
                    value=f""{shout_text}"\n— **{shout_poster}** on {shout_date.strftime('%b %d, %Y')}",
                    inline=False
                )
            
            # Add group roles
            if roles_data and "roles" in roles_data:
                roles = roles_data["roles"]
                roles_text = []
                
                for role in roles:
                    role_name = role.get("name", "Unknown")
                    role_rank = role.get("rank", 0)
                    member_count = role.get("memberCount", "?")
                    
                    roles_text.append(f"**{role_name}** (Rank {role_rank}) - {member_count:,} members")
                
                if roles_text:
                    # Show at most 8 roles to avoid huge embeds
                    shown_roles = roles_text[:8]
                    if len(roles_text) > 8:
                        shown_roles.append(f"*...and {len(roles_text) - 8} more roles*")
                    
                    embed.add_field(
                        name=f"👥 Roles ({len(roles)})",
                        value="\n".join(shown_roles),
                        inline=False
                    )
            
            # Add group games if available
            if games_data and "data" in games_data:
                games = games_data["data"]
                games_text = []
                total_visits = 0
                
                for game in games[:5]:  # Show up to 5 games
                    game_name = game.get("name", "Unknown Game")
                    game_visits = game.get("placeVisits", 0)
                    total_visits += game_visits
                    games_text.append(f"**{game_name}** - {game_visits:,} visits")
                
                if games_text:
                    embed.add_field(
                        name=f"🎮 Group Games ({len(games)})",
                        value=f"Total Visits: {total_visits:,}\n" + "\n".join(games_text),
                        inline=False
                    )
            
            # Add recent wall posts if available
            if wall_data and "data" in wall_data:
                posts = wall_data["data"]
                wall_text = []
                
                for post in posts[:3]:  # Show most recent 3 posts
                    body = post.get("body", "")
                    poster = post.get("poster", {}).get("username", "Unknown")
                    
                    # Limit post text to 100 characters
                    if len(body) > 100:
                        body = body[:97] + "..."
                    
                    wall_text.append(f"**{poster}**: "{body}"")
                
                if wall_text:
                    embed.add_field(
                        name="📝 Recent Wall Posts",
                        value="\n".join(wall_text),
                        inline=False
                    )
            
            # Set footer
            embed.set_footer(text=f"Roblox Group ID: {group_id} • Powered by Roblox API")
            
            # Send with icon as attachment if available
            if group_icon_bytes:
                file = discord.File(fp=io.BytesIO(group_icon_bytes), filename="group_icon.png")
                embed.set_thumbnail(url="attachment://group_icon.png")
                await interaction.followup.send(embed=embed, file=file)
            else:
                # Fallback to URL if we couldn't download the image
                if group_info.get("imageUrl"):
                    embed.set_thumbnail(url=group_info["imageUrl"])
                await interaction.followup.send(embed=embed)
        
        except Exception as e:
            await interaction.followup.send(f"An error occurred while retrieving group information: {str(e)}")

async def setup(bot):
    await bot.add_cog(Roblox(bot))
