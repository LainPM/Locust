# cogs/roblox.py
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import datetime
from typing import Optional, Union
import io
from PIL import Image
import re

class RobloxModal(discord.ui.Modal):
    def __init__(self, cog):
        super().__init__(title="Enter Roblox Username")
        self.cog = cog
        
        self.username = discord.ui.TextInput(
            label="Roblox Username",
            placeholder="Enter a Roblox username",
            min_length=3,
            max_length=20,
            required=True
        )
        self.add_item(self.username)
    
    async def on_submit(self, interaction: discord.Interaction):
        # Call the lookup method with the entered username
        await interaction.response.defer()
        await self.cog.lookup_and_respond(interaction, self.username.value)

class Roblox(commands.Cog):
    """Cog for looking up Roblox user information"""
    
    def __init__(self, bot):
        self.bot = bot
        self.session = None  # We'll initialize in setup hook
        print("Roblox cog initialized")
    
    async def cog_load(self):
        # Initialize aiohttp session when the cog is loaded
        self.session = aiohttp.ClientSession()
        print("Roblox cog loaded - aiohttp session initialized")
    
    async def cog_unload(self):
        # Close the aiohttp session when the cog is unloaded
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
            print(f"Exception in get_user_by_username: {str(e)}")
            return None
    
    async def get_user_info(self, user_id):
        """Get detailed user information"""
        try:
            async with self.session.get(f"https://users.roblox.com/v1/users/{user_id}") as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            print(f"Exception in get_user_info: {str(e)}")
            return None
    
    async def get_user_status(self, user_id):
        """Get user's status/about me"""
        try:
            async with self.session.get(f"https://users.roblox.com/v1/users/{user_id}/status") as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            print(f"Exception in get_user_status: {str(e)}")
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
            print(f"Exception in get_user_presence: {str(e)}")
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
            print(f"Exception in get_user_avatar_image: {str(e)}")
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
            print(f"Exception in get_user_badges: {str(e)}")
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
            print(f"Exception in get_user_friends_count: {str(e)}")
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
            print(f"Exception in get_user_followers_count: {str(e)}")
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
            print(f"Exception in get_user_followings_count: {str(e)}")
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
            print(f"Exception in get_user_groups: {str(e)}")
            return []
    
    async def get_user_experiences(self, user_id):
        """Get user's created experiences/games"""
        try:
            async with self.session.get(
                f"https://games.roblox.com/v2/users/{user_id}/games?accessFilter=Public&limit=10&sortOrder=Asc"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", [])
                return []
        except Exception as e:
            print(f"Exception in get_user_experiences: {str(e)}")
            return []
    
    async def get_profile_views(self, user_id):
        """Get user's profile views (approximate)
        Note: This is not available through the official API"""
        # This is a placeholder as this data isn't easily accessible
        # In a real implementation, you might need to web scrape
        return None
        
    async def lookup_and_respond(self, interaction, identifier):
        """Main method to handle lookup and send response"""
        user_id = None
        username = None
        
        # Check if this is a Roblox user ID (all digits)
        if isinstance(identifier, str) and identifier.isdigit():
            user_id = int(identifier)
        
        # Otherwise, assume it's a username
        else:
            username = identifier
            user_id = await self.get_user_by_username(username)
            
            if not user_id:
                await interaction.followup.send(f"Could not find Roblox user with username '{username}'.")
                return
        
        # Get user information
        user_info = await self.get_user_info(user_id)
        if not user_info:
            await interaction.followup.send(f"Could not find Roblox user with ID {user_id}.")
            return
        
        # Get additional information (in parallel to speed things up)
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
        if presence and presence.get("userPresenceType") is not None:
            if presence.get("premiumMembershipType", 0) > 0:
                account_badges.append("⭐ Premium")
        
        if account_badges:
            embed.add_field(name="Account Badges", value=" | ".join(account_badges), inline=True)
        
        # Add creation date
        if "created" in user_info:
            created_date = datetime.datetime.fromisoformat(user_info["created"].replace("Z", "+00:00"))
            account_age = (datetime.datetime.now(datetime.timezone.utc) - created_date).days
            embed.add_field(name="Account Created", value=f"{created_date.strftime('%Y-%m-%d')} ({account_age} days)", inline=True)
        
        # Add status if available
        if status and status.get("status"):
            embed.add_field(name="Status", value=status["status"], inline=True)
        
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
        embed.add_field(name="Following", value=f"{followings_count:,}", inline=True)
        embed.add_field(name="Badges", value=f"{badges_count:,}", inline=True)
        
        # Add groups information
        if groups:
            group_names = []
            for group_data in groups[:5]:  # Show up to 5 groups
                group = group_data.get("group", {})
                role = group_data.get("role", {})
                group_names.append(f"{group.get('name', 'Unknown Group')} - {role.get('name', 'Member')}")
            
            embed.add_field(
                name=f"Groups ({len(groups)})",
                value="\n".join(group_names) if group_names else "None",
                inline=False
            )
            
            if len(groups) > 5:
                embed.add_field(name="\u200b", value=f"*and {len(groups) - 5} more...*", inline=False)
        
        # Add experiences/games info if available
        if experiences:
            game_info = []
            for exp in experiences[:3]:  # Show up to 3 games
                name = exp.get("name", "Unnamed Game")
                visits = exp.get("placeVisits", 0)
                game_info.append(f"{name} - {visits:,} visits")
            
            if game_info:
                embed.add_field(
                    name=f"Created Experiences ({len(experiences)})",
                    value="\n".join(game_info),
                    inline=False
                )
        
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
    
    @commands.command(name="roblox_legacy")
    async def roblox_legacy(self, ctx, *, identifier=None):
        """Traditional command version for looking up Roblox users"""
        if not identifier:
            await ctx.send("Please provide a Roblox username or ID.")
            return
        
        # Create a mock interaction for compatibility with the lookup method
        # This is a simplified approach - in a real bot you might want to handle this differently
        class MockInteraction:
            async def followup(self, send):
                return ctx
            
        mock_interaction = MockInteraction()
        mock_interaction.followup = ctx
        
        await self.lookup_and_respond(mock_interaction, identifier)

    # App command for Roblox lookup
    @app_commands.command(name="roblox", description="Look up a Roblox user by username or ID")
    @app_commands.describe(identifier="Roblox username or user ID")
    async def roblox_lookup(self, interaction: discord.Interaction, identifier: Optional[str] = None):
        """Look up a Roblox user by username or ID"""
        # If no identifier is provided, show a modal to enter username
        if identifier is None:
            modal = RobloxModal(self)
            await interaction.response.send_modal(modal)
            return
        
        # Process the lookup
        await interaction.response.defer()
        await self.lookup_and_respond(interaction, identifier)
    
    # App command for Discord user's Roblox lookup
    @app_commands.command(name="robloxuser", description="Look up a Discord user's Roblox profile if linked")
    @app_commands.describe(user="Discord user to look up")
    async def roblox_discord_lookup(self, interaction: discord.Interaction, user: discord.User):
        """Look up a Discord user's linked Roblox account (if possible)"""
        await interaction.response.defer()
        
        # Try to get the user's connections
        # Note: This requires privileged intents and is generally not possible for bots
        # Instead, we'll explain the limitation
        
        embed = discord.Embed(
            title="Discord to Roblox Linking",
            description="Looking up Roblox accounts linked to Discord users requires privileged API access, which is not available for most bots.",
            color=discord.Color.orange()
        )
        
        embed.add_field(
            name="Alternative Methods",
            value=(
                "There are a few ways you can find a user's Roblox account:\n"
                "1. Ask them for their Roblox username\n"
                "2. Check if they have it in their Discord status or bio\n"
                "3. Use a verification bot like Bloxlink or RoVer that creates roles for verified users"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Verification Bots",
            value=(
                "You can invite these bots to your server for Roblox verification:\n"
                "• [Bloxlink](https://blox.link/)\n"
                "• [RoVer](https://rover.link/)"
            ),
            inline=False
        )
        
        embed.set_footer(text="This limitation is due to Discord's API policies, not a limitation of this bot.")
        
        await interaction.followup.send(embed=embed)
    
    # App command for Roblox group lookup
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
            
            # Get group roles
            async with self.session.get(f"https://groups.roblox.com/v1/groups/{group_id}/roles") as response:
                if response.status == 200:
                    roles_data = await response.json()
                    roles = roles_data.get("roles", [])
                else:
                    roles = []

            # Get group icon
            group_icon_url = f"https://t7.rbxcdn.com/75831a957170b368210ad6866e752d8a"
            if group_info.get("imageUrl"):
                group_icon_url = group_info["imageUrl"]
            
            # Try to get group icon bytes
            group_icon_bytes = None
            try:
                async with self.session.get(group_icon_url) as response:
                    if response.status == 200:
                        group_icon_bytes = await response.read()
            except:
                pass

            # Get group games (if any)
            games = []
            try:
                async with self.session.get(
                    f"https://games.roblox.com/v2/groups/{group_id}/games?accessFilter=Public&limit=10&sortOrder=Asc"
                ) as response:
                    if response.status == 200:
                        games_data = await response.json()
                        games = games_data.get("data", [])
            except Exception as e:
                print(f"Error getting group games: {e}")
            
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
            
            # Add group status (public/private)
            is_public = "Yes" if group_info.get("publicEntryAllowed", False) else "No"
            embed.add_field(name="Public Entry", value=is_public, inline=True)
            
            # Add group roles
            if roles:
                roles_text = []
                for role in roles:
                    role_name = role.get("name", "Unknown")
                    role_rank = role.get("rank", 0)
                    roles_text.append(f"{role_name} (Rank: {role_rank})")
                
                embed.add_field(
                    name=f"Roles ({len(roles)})",
                    value="\n".join(roles_text[:5]) if roles_text else "None",
                    inline=False
                )
                
                if len(roles) > 5:
                    embed.add_field(name="\u200b", value=f"*and {len(roles) - 5} more...*", inline=False)
            
            # Add group games if available
            if games:
                games_text = []
                for game in games[:3]:
                    game_name = game.get("name", "Unknown Game")
                    game_visits = game.get("placeVisits", 0)
                    games_text.append(f"{game_name} - {game_visits:,} visits")
                
                if games_text:
                    embed.add_field(
                        name=f"Group Games ({len(games)})",
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
                # Fallback to URL
                embed.set_thumbnail(url=group_icon_url)
                await interaction.followup.send(embed=embed)
        
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}")

async def setup(bot):
    print(f"Setting up Roblox cog...")
    try:
        # Create instance of the cog
        cog = Roblox(bot)
        
        # Add the cog to the bot
        await bot.add_cog(cog)
        
        # Force sync commands with Discord
        # Note: In production, you wouldn't do this with every cog load
        # as it can hit rate limits. Normally this is done once at bot startup.
        try:
            # Sync commands with Discord
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} commands")
            
            # Print all registered commands for debugging
            commands = [command.name for command in bot.tree.get_commands()]
            print(f"Registered commands: {commands}")
        except Exception as e:
            print(f"Error syncing commands: {e}")
        
        print(f"Roblox cog added successfully!")
    except Exception as e:
        print(f"Error loading Roblox cog: {e}")
        import traceback
        traceback.print_exc()
