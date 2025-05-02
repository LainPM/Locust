import discord
from discord import app_commands
from discord.ext import commands
from enum import Enum
import re
from typing import List, Optional, Literal


class MatchType(Enum):
    CONTAINS = "contains"
    EXACT = "exact"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    REGEX = "regex"


class FilterCog(commands.Cog):
    """Cog for managing content filtering with blacklist and whitelist functionality"""
    
    def __init__(self, bot):
        self.bot = bot
        # Create collections if they don't exist already
        self.ensure_collections()
        # Cache for quick lookups during message filtering
        self.blacklist_cache = {}  # {guild_id: {item: match_type}}
        self.whitelist_cache = {}  # {guild_id: {item: match_type}}
        # Views cache to store active pagination views
        self.active_views = {}
        
    def ensure_collections(self):
        """Ensure required collections exist in the database"""
        if not hasattr(self.bot, 'db'):
            print("Warning: Bot database not initialized")
            return
            
        # Create collections if they don't exist
        if "blacklist" not in self.bot.db.list_collection_names():
            self.bot.db.create_collection("blacklist")
        if "whitelist" not in self.bot.db.list_collection_names():
            self.bot.db.create_collection("whitelist")
            
        # Set up collection references
        self.blacklist_collection = self.bot.db["blacklist"]
        self.whitelist_collection = self.bot.db["whitelist"]
        
    async def load_cache_for_guild(self, guild_id: int):
        """Load blacklist and whitelist items for a specific guild into cache"""
        # Clear existing cache for guild
        self.blacklist_cache[guild_id] = {}
        self.whitelist_cache[guild_id] = {}
        
        # Load blacklist items
        async for doc in self.blacklist_collection.find({"guild_id": guild_id}):
            self.blacklist_cache[guild_id][doc["item"]] = doc["match_type"]
            
        # Load whitelist items
        async for doc in self.whitelist_collection.find({"guild_id": guild_id}):
            self.whitelist_cache[guild_id][doc["item"]] = doc["match_type"]
    
    async def cog_load(self):
        """Called when the cog is loaded"""
        print("Loading FilterCog...")
        # Pre-load cache for all guilds
        for guild in self.bot.guilds:
            await self.load_cache_for_guild(guild.id)
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Initialize cache when bot joins a new guild"""
        await self.load_cache_for_guild(guild.id)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Filter messages based on blacklist and whitelist"""
        # Skip if message is from a bot or DM
        if message.author.bot or not message.guild:
            return
            
        # Skip if message is a command
        if message.content.startswith(self.bot.command_prefix):
            return
            
        guild_id = message.guild.id
        
        # Ensure we have cache for this guild
        if guild_id not in self.blacklist_cache:
            await self.load_cache_for_guild(guild_id)
            
        # Skip if no blacklist items for this guild
        if not self.blacklist_cache.get(guild_id):
            return
            
        # Check if message content matches any blacklisted item
        content = message.content.lower()
        
        # First check if content matches any whitelisted item - this overrides blacklist
        if await self._is_whitelisted(content, guild_id):
            return
            
        # Then check if content matches any blacklisted item
        if await self._is_blacklisted(content, guild_id):
            try:
                await message.delete()
                # Optional: send a warning to the user
                await message.channel.send(
                    f"{message.author.mention}, your message was removed because it contained blacklisted content.",
                    delete_after=5  # Auto-delete after 5 seconds
                )
            except discord.Forbidden:
                print(f"Missing permissions to delete message in {message.guild.name}, channel {message.channel.name}")
            except Exception as e:
                print(f"Error deleting message: {e}")
    
    async def _is_blacklisted(self, content: str, guild_id: int) -> bool:
        """Check if content matches any blacklisted item"""
        if guild_id not in self.blacklist_cache:
            return False
            
        for item, match_type in self.blacklist_cache[guild_id].items():
            if self._matches(content, item, match_type):
                return True
                
        return False
    
    async def _is_whitelisted(self, content: str, guild_id: int) -> bool:
        """Check if content matches any whitelisted item"""
        if guild_id not in self.whitelist_cache:
            return False
            
        for item, match_type in self.whitelist_cache[guild_id].items():
            if self._matches(content, item, match_type):
                return True
                
        return False
    
    def _matches(self, content: str, item: str, match_type: str) -> bool:
        """Check if content matches an item based on match type"""
        try:
            if match_type == MatchType.CONTAINS.value:
                return item.lower() in content
            elif match_type == MatchType.EXACT.value:
                return content == item.lower()
            elif match_type == MatchType.STARTS_WITH.value:
                return content.startswith(item.lower())
            elif match_type == MatchType.ENDS_WITH.value:
                return content.endswith(item.lower())
            elif match_type == MatchType.REGEX.value:
                return bool(re.search(item, content, re.IGNORECASE))
                
        except Exception as e:
            print(f"Error matching pattern {item} with type {match_type}: {e}")
            
        return False
    
    # Slash commands
    
    @app_commands.command(name="blacklist", description="Add an item to the blacklist")
    @app_commands.describe(
        item="The word, phrase, link, etc. to blacklist",
        match_type="How to match this item in messages (default: contains)",
        reason="Optional reason for blacklisting this item"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value="contains"),
        app_commands.Choice(name="Exact Match", value="exact"),
        app_commands.Choice(name="Starts With", value="starts_with"),
        app_commands.Choice(name="Ends With", value="ends_with"),
        app_commands.Choice(name="Regex Pattern", value="regex")
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def blacklist_command(
        self, 
        interaction: discord.Interaction, 
        item: str, 
        match_type: str = "contains", 
        reason: Optional[str] = None
    ):
        """Add an item to the blacklist"""
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("You need 'Manage Messages' permission to use this command.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        
        # Initialize cache for guild if not exists
        if guild_id not in self.blacklist_cache:
            self.blacklist_cache[guild_id] = {}
            
        if guild_id not in self.whitelist_cache:
            self.whitelist_cache[guild_id] = {}
            
        # Check if item is in whitelist - if so, remove it
        existing_whitelist = await self.whitelist_collection.find_one({
            "guild_id": guild_id,
            "item": item
        })
        
        if existing_whitelist:
            await self.whitelist_collection.delete_one({
                "guild_id": guild_id,
                "item": item
            })
            if item in self.whitelist_cache[guild_id]:
                del self.whitelist_cache[guild_id][item]
        
        # Check if item is already blacklisted
        existing_blacklist = await self.blacklist_collection.find_one({
            "guild_id": guild_id,
            "item": item
        })
        
        if existing_blacklist:
            # Update existing entry if match_type is different
            if existing_blacklist["match_type"] != match_type:
                await self.blacklist_collection.update_one(
                    {"_id": existing_blacklist["_id"]},
                    {"$set": {"match_type": match_type, "reason": reason}}
                )
                self.blacklist_cache[guild_id][item] = match_type
                await interaction.response.send_message(
                    f"Updated blacklist entry for `{item}` with match type `{match_type}`", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"`{item}` is already blacklisted with match type `{match_type}`", 
                    ephemeral=True
                )
        else:
            # Add new blacklist entry
            await self.blacklist_collection.insert_one({
                "guild_id": guild_id,
                "item": item,
                "match_type": match_type,
                "reason": reason,
                "added_by": interaction.user.id,
                "added_at": discord.utils.utcnow().isoformat()
            })
            
            # Update cache
            self.blacklist_cache[guild_id][item] = match_type
            
            await interaction.response.send_message(
                f"Added `{item}` to the blacklist with match type `{match_type}`", 
                ephemeral=True
            )
    
    @app_commands.command(name="whitelist", description="Add an item to the whitelist (overrides blacklist)")
    @app_commands.describe(
        item="The word, phrase, link, etc. to whitelist",
        match_type="How to match this item in messages (default: contains)",
        reason="Optional reason for whitelisting this item"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value="contains"),
        app_commands.Choice(name="Exact Match", value="exact"),
        app_commands.Choice(name="Starts With", value="starts_with"),
        app_commands.Choice(name="Ends With", value="ends_with"),
        app_commands.Choice(name="Regex Pattern", value="regex")
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def whitelist_command(
        self, 
        interaction: discord.Interaction, 
        item: str, 
        match_type: str = "contains", 
        reason: Optional[str] = None
    ):
        """Add an item to the whitelist"""
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("You need 'Manage Messages' permission to use this command.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        
        # Initialize cache for guild if not exists
        if guild_id not in self.blacklist_cache:
            self.blacklist_cache[guild_id] = {}
            
        if guild_id not in self.whitelist_cache:
            self.whitelist_cache[guild_id] = {}
            
        # Check if item is in blacklist - if so, remove it
        existing_blacklist = await self.blacklist_collection.find_one({
            "guild_id": guild_id,
            "item": item
        })
        
        if existing_blacklist:
            await self.blacklist_collection.delete_one({
                "guild_id": guild_id,
                "item": item
            })
            if item in self.blacklist_cache[guild_id]:
                del self.blacklist_cache[guild_id][item]
        
        # Check if item is already whitelisted
        existing_whitelist = await self.whitelist_collection.find_one({
            "guild_id": guild_id,
            "item": item
        })
        
        if existing_whitelist:
            # Update existing entry if match_type is different
            if existing_whitelist["match_type"] != match_type:
                await self.whitelist_collection.update_one(
                    {"_id": existing_whitelist["_id"]},
                    {"$set": {"match_type": match_type, "reason": reason}}
                )
                self.whitelist_cache[guild_id][item] = match_type
                await interaction.response.send_message(
                    f"Updated whitelist entry for `{item}` with match type `{match_type}`", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"`{item}` is already whitelisted with match type `{match_type}`", 
                    ephemeral=True
                )
        else:
            # Add new whitelist entry
            await self.whitelist_collection.insert_one({
                "guild_id": guild_id,
                "item": item,
                "match_type": match_type,
                "reason": reason,
                "added_by": interaction.user.id,
                "added_at": discord.utils.utcnow().isoformat()
            })
            
            # Update cache
            self.whitelist_cache[guild_id][item] = match_type
            
            await interaction.response.send_message(
                f"Added `{item}` to the whitelist with match type `{match_type}`", 
                ephemeral=True
            )
    
    # List pagination view
    class FilterListView(discord.ui.View):
        def __init__(self, cog, guild_id: int, list_type: str, items: List[dict], timeout: float = 180):
            super().__init__(timeout=timeout)
            self.cog = cog
            self.guild_id = guild_id
            self.list_type = list_type
            self.items = items
            self.current_page = 0
            self.items_per_page = 10
            self.max_pages = (len(items) - 1) // self.items_per_page + 1
            
            # Update button states
            self.update_buttons()
            
        def update_buttons(self):
            # Enable/disable buttons based on current page
            self.previous_button.disabled = (self.current_page == 0)
            self.next_button.disabled = (self.current_page >= self.max_pages - 1)
        
        @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="⬅️")
        async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.current_page > 0:
                self.current_page -= 1
                self.update_buttons()
                await interaction.response.edit_message(embed=self.get_embed(), view=self)
            else:
                await interaction.response.defer()
        
        @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="➡️")
        async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.current_page < self.max_pages - 1:
                self.current_page += 1
                self.update_buttons()
                await interaction.response.edit_message(embed=self.get_embed(), view=self)
            else:
                await interaction.response.defer()
                
        async def on_timeout(self):
            """Remove the view from active_views when it times out"""
            view_key = f"{self.guild_id}_{self.list_type}"
            if view_key in self.cog.active_views:
                del self.cog.active_views[view_key]
                
            # Try to update the message to disable buttons
            for item in self.children:
                item.disabled = True
                
            # The try/except is needed because the message might have been deleted
            try:
                await self.message.edit(view=self)
            except:
                pass
        
        def get_embed(self):
            """Generate the embed for the current page"""
            start_idx = self.current_page * self.items_per_page
            end_idx = min(start_idx + self.items_per_page, len(self.items))
            
            title = "Blacklisted Items" if self.list_type == "blacklist" else "Whitelisted Items"
            color = discord.Color.red() if self.list_type == "blacklist" else discord.Color.green()
            
            embed = discord.Embed(
                title=title,
                description=f"Page {self.current_page + 1}/{self.max_pages}",
                color=color
            )
            
            for i in range(start_idx, end_idx):
                item = self.items[i]
                reason_text = f"\nReason: {item['reason']}" if item.get('reason') else ""
                added_by = f"<@{item['added_by']}>" if 'added_by' in item else "Unknown"
                added_at = item.get('added_at', 'Unknown')
                
                value = f"Match: `{item['match_type']}`{reason_text}\nAdded by: {added_by}\nAdded: {added_at}"
                embed.add_field(name=f"#{i+1}: {item['item']}", value=value, inline=False)
                
            return embed
        
    @app_commands.command(name="show_blacklisted", description="Show all blacklisted items")
    @app_commands.describe(
        match_type="Filter by match type",
        ephemeral="Whether to show the list only to you"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="All Types", value="all"),
        app_commands.Choice(name="Contains", value="contains"),
        app_commands.Choice(name="Exact Match", value="exact"),
        app_commands.Choice(name="Starts With", value="starts_with"),
        app_commands.Choice(name="Ends With", value="ends_with"),
        app_commands.Choice(name="Regex Pattern", value="regex")
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def show_blacklisted_command(
        self, 
        interaction: discord.Interaction,
        match_type: str = "all",
        ephemeral: bool = True
    ):
        """Show all blacklisted items"""
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("You need 'Manage Messages' permission to use this command.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        
        # Get all blacklisted items for this guild
        query = {"guild_id": guild_id}
        if match_type != "all":
            query["match_type"] = match_type
            
        blacklist_items = await self.blacklist_collection.find(query).to_list(length=None)
        
        if not blacklist_items:
            await interaction.response.send_message(
                f"No blacklisted items found{' with that match type' if match_type != 'all' else ''}.", 
                ephemeral=ephemeral
            )
            return
            
        # Create pagination view
        view = self.FilterListView(self, guild_id, "blacklist", blacklist_items)
        embed = view.get_embed()
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)
        
        # Store the view message for timeout handling
        view_message = await interaction.original_response()
        view.message = view_message
        
        # Store active view
        view_key = f"{guild_id}_blacklist"
        self.active_views[view_key] = view
    
    @app_commands.command(name="show_whitelisted", description="Show all whitelisted items")
    @app_commands.describe(
        match_type="Filter by match type",
        ephemeral="Whether to show the list only to you"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="All Types", value="all"),
        app_commands.Choice(name="Contains", value="contains"),
        app_commands.Choice(name="Exact Match", value="exact"),
        app_commands.Choice(name="Starts With", value="starts_with"),
        app_commands.Choice(name="Ends With", value="ends_with"),
        app_commands.Choice(name="Regex Pattern", value="regex")
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def show_whitelisted_command(
        self, 
        interaction: discord.Interaction,
        match_type: str = "all",
        ephemeral: bool = True
    ):
        """Show all whitelisted items"""
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("You need 'Manage Messages' permission to use this command.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        
        # Get all whitelisted items for this guild
        query = {"guild_id": guild_id}
        if match_type != "all":
            query["match_type"] = match_type
            
        whitelist_items = await self.whitelist_collection.find(query).to_list(length=None)
        
        if not whitelist_items:
            await interaction.response.send_message(
                f"No whitelisted items found{' with that match type' if match_type != 'all' else ''}.", 
                ephemeral=ephemeral
            )
            return
            
        # Create pagination view
        view = self.FilterListView(self, guild_id, "whitelist", whitelist_items)
        embed = view.get_embed()
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)
        
        # Store the view message for timeout handling
        view_message = await interaction.original_response()
        view.message = view_message
        
        # Store active view
        view_key = f"{guild_id}_whitelist"
        self.active_views[view_key] = view
        
    @app_commands.command(name="remove_filter", description="Remove an item from blacklist or whitelist")
    @app_commands.describe(
        item="The word, phrase, link, etc. to remove",
        list_type="Which list to remove the item from"
    )
    @app_commands.choices(list_type=[
        app_commands.Choice(name="Blacklist", value="blacklist"),
        app_commands.Choice(name="Whitelist", value="whitelist"),
        app_commands.Choice(name="Both Lists", value="both")
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def remove_filter_command(
        self, 
        interaction: discord.Interaction,
        item: str,
        list_type: str
    ):
        """Remove an item from blacklist or whitelist"""
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("You need 'Manage Messages' permission to use this command.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        removed = False
        message = ""
        
        # Remove from blacklist if requested
        if list_type in ["blacklist", "both"]:
            result = await self.blacklist_collection.delete_one({
                "guild_id": guild_id,
                "item": item
            })
            
            if result.deleted_count > 0:
                removed = True
                message += f"Removed `{item}` from the blacklist.\n"
                
                # Update cache
                if guild_id in self.blacklist_cache and item in self.blacklist_cache[guild_id]:
                    del self.blacklist_cache[guild_id][item]
        
        # Remove from whitelist if requested
        if list_type in ["whitelist", "both"]:
            result = await self.whitelist_collection.delete_one({
                "guild_id": guild_id,
                "item": item
            })
            
            if result.deleted_count > 0:
                removed = True
                message += f"Removed `{item}` from the whitelist.\n"
                
                # Update cache
                if guild_id in self.whitelist_cache and item in self.whitelist_cache[guild_id]:
                    del self.whitelist_cache[guild_id][item]
        
        if not removed:
            message = f"`{item}` was not found in the specified list(s)."
            
        await interaction.response.send_message(message, ephemeral=True)
    
    @app_commands.command(name="clear_filters", description="Clear all items from blacklist or whitelist")
    @app_commands.describe(
        list_type="Which list to clear",
        confirm="Type 'confirm' to proceed"
    )
    @app_commands.choices(list_type=[
        app_commands.Choice(name="Blacklist", value="blacklist"),
        app_commands.Choice(name="Whitelist", value="whitelist"),
        app_commands.Choice(name="Both Lists", value="both")
    ])
    @app_commands.default_permissions(administrator=True)
    async def clear_filters_command(
        self, 
        interaction: discord.Interaction,
        list_type: str,
        confirm: str
    ):
        """Clear all items from blacklist or whitelist"""
        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need 'Administrator' permission to use this command.", ephemeral=True)
            return
            
        # Confirm safety check
        if confirm.lower() != "confirm":
            await interaction.response.send_message(
                "You must type 'confirm' to proceed with clearing filters. This action cannot be undone.", 
                ephemeral=True
            )
            return
            
        guild_id = interaction.guild.id
        message = ""
        
        # Clear blacklist if requested
        if list_type in ["blacklist", "both"]:
            result = await self.blacklist_collection.delete_many({"guild_id": guild_id})
            message += f"Deleted {result.deleted_count} items from the blacklist.\n"
            
            # Update cache
            self.blacklist_cache[guild_id] = {}
        
        # Clear whitelist if requested
        if list_type in ["whitelist", "both"]:
            result = await self.whitelist_collection.delete_many({"guild_id": guild_id})
            message += f"Deleted {result.deleted_count} items from the whitelist.\n"
            
            # Update cache
            self.whitelist_cache[guild_id] = {}
            
        await interaction.response.send_message(message, ephemeral=True)
    
    @app_commands.command(name="test_filter", description="Test if text would be filtered")
    @app_commands.describe(
        text="The text to test against filters"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def test_filter_command(
        self, 
        interaction: discord.Interaction,
        text: str
    ):
        """Test if text would be filtered by current blacklist/whitelist"""
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("You need 'Manage Messages' permission to use this command.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        
        # Ensure we have cache for this guild
        if guild_id not in self.blacklist_cache:
            await self.load_cache_for_guild(guild_id)
            
        # Test against whitelist first
        is_whitelisted = await self._is_whitelisted(text.lower(), guild_id)
        
        # Then test against blacklist
        is_blacklisted = await self._is_blacklisted(text.lower(), guild_id)
        
        # Determine result
        if is_whitelisted:
            if is_blacklisted:
                result = "✅ This text matches both blacklist and whitelist. It would **NOT** be filtered (whitelist overrides blacklist)."
            else:
                result = "✅ This text does not match any blacklist items and is explicitly whitelisted."
        else:
            if is_blacklisted:
                result = "❌ This text matches blacklist items and would be **FILTERED OUT**."
            else:
                result = "✅ This text does not match any blacklist items and would be allowed."
                
        # Find matching items for detailed report
        matching_details = []
        
        # Check blacklist matches
        for item, match_type in self.blacklist_cache.get(guild_id, {}).items():
            if self._matches(text.lower(), item, match_type):
                matching_details.append(f"Blacklist: `{item}` (match type: `{match_type}`)")
                
        # Check whitelist matches
        for item, match_type in self.whitelist_cache.get(guild_id, {}).items():
            if self._matches(text.lower(), item, match_type):
                matching_details.append(f"Whitelist: `{item}` (match type: `{match_type}`)")
                
        # Create embed
        embed = discord.Embed(
            title="Filter Test Results",
            description=result,
            color=discord.Color.green() if not is_blacklisted or is_whitelisted else discord.Color.red()
        )
        
        if matching_details:
            embed.add_field(name="Matching Filter Items", value="\n".join(matching_details), inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @app_commands.command(name="export_filters", description="Export all filters as JSON")
    @app_commands.default_permissions(administrator=True)
    async def export_filters_command(self, interaction: discord.Interaction):
        """Export all filters to a JSON file"""
        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need 'Administrator' permission to use this command.", ephemeral=True)
            return
            
        guild_id = interaction.guild.id
        
        # Get all items for this guild
        blacklist_items = await self.blacklist_collection.find({"guild_id": guild_id}).to_list(length=None)
        whitelist_items = await self.whitelist_collection.find({"guild_id": guild_id}).to_list(length=None)
        
        # Clean up items for export (remove _id and other unnecessary fields)
        for item in blacklist_items:
            if "_id" in item:
                del item["_id"]
                
        for item in whitelist_items:
            if "_id" in item:
                del item["_id"]
                
        # Create export data
        export_data = {
            "guild_id": guild_id,
            "guild_name": interaction.guild.name,
            "exported_at": discord.utils.utcnow().isoformat(),
            "exported_by": {
                "id": interaction.user.id,
                "name": str(interaction.user)
            },
            "blacklist": blacklist_items,
            "whitelist": whitelist_items
        }
        
        # Convert to JSON string
        import json
        json_data = json.dumps(export_data, indent=2)
        
        # Create file object
        import io
        file = discord.File(
            io.BytesIO(json_data.encode()),
            filename=f"filters_export_{interaction.guild.name}_{discord.utils.utcnow().strftime('%Y%m%d')}.json"
        )
        
        await interaction.response.send_message(
            "Here's your filter export. You can use this file to back up your filters or import them to another server.",
            file=file,
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(FilterCog(bot))
