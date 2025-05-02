import discord
from discord import app_commands
from discord.ext import commands
from enum import Enum
import re
from typing import Optional, List, Dict, Any
import math

class MatchType(Enum):
    CONTAINS = "contains"
    EXACT = "exact"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    REGEX = "regex"

class PaginationView(discord.ui.View):
    def __init__(self, items: List[Dict[str, Any]], match_type: str, 
                 page: int, items_per_page: int, is_blacklist: bool, 
                 interaction: discord.Interaction):
        super().__init__(timeout=180)  # 3 minute timeout
        self.items = items
        self.match_type = match_type
        self.current_page = page
        self.items_per_page = items_per_page
        self.is_blacklist = is_blacklist
        self.interaction = interaction
        self.total_pages = math.ceil(len(self.filtered_items) / self.items_per_page)
        
        # Disable buttons if needed
        self.update_buttons()

    @property
    def filtered_items(self) -> List[Dict[str, Any]]:
        """Get items filtered by match_type"""
        if self.match_type == "all":
            return self.items
        return [item for item in self.items if item.get("match_type") == self.match_type]
    
    def get_embed(self) -> discord.Embed:
        """Generate the embed for the current page"""
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        
        filtered = self.filtered_items
        page_items = filtered[start_idx:end_idx]
        
        title = "Blacklisted Items" if self.is_blacklist else "Whitelisted Items"
        color = discord.Color.red() if self.is_blacklist else discord.Color.green()
        
        embed = discord.Embed(
            title=title,
            description=f"Filter: {self.match_type} | Page {self.current_page}/{self.total_pages}",
            color=color
        )
        
        if not page_items:
            embed.add_field(name="No items found", value="Try a different page or filter", inline=False)
        else:
            for doc in page_items:
                embed.add_field(
                    name=doc["item"], 
                    value=f"Type: {doc['match_type']}" + (f"\nReason: {doc.get('reason')}" if doc.get('reason') else ""),
                    inline=False
                )
                
        embed.set_footer(text=f"Showing {len(page_items)} items | Total: {len(filtered)} items")
        return embed
    
    def update_buttons(self):
        """Update button states based on current page"""
        # Disable prev button if on first page
        self.prev_button.disabled = (self.current_page <= 1)
        # Disable next button if on last page
        self.next_button.disabled = (self.current_page >= self.total_pages)

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.grey)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(1, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = min(self.total_pages, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def on_timeout(self):
        """Remove buttons when the view times out"""
        # Disable all buttons
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        
        # Try to update the message - might fail if message is too old
        try:
            await self.message.edit(view=self)
        except:
            pass

class FilterCog(commands.Cog):
    """Cog for managing content filtering with blacklist and whitelist functionality"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.blacklist_cache = {}
        self.whitelist_cache = {}

    async def cog_load(self):
        if hasattr(self.bot, 'db'):
            names = await self.bot.db.list_collection_names()
            if "blacklist" not in names:
                await self.bot.db.create_collection("blacklist")
            if "whitelist" not in names:
                await self.bot.db.create_collection("whitelist")
            self.blacklist_collection = self.bot.db["blacklist"]
            self.whitelist_collection = self.bot.db["whitelist"]
        else:
            print("Warning: Bot database not initialized")
            return
        for guild in self.bot.guilds:
            await self._load_cache(guild.id)
        await self.bot.tree.sync()

    async def _load_cache(self, guild_id: int):
        self.blacklist_cache[guild_id] = {}
        self.whitelist_cache[guild_id] = {}
        async for doc in self.blacklist_collection.find({"guild_id": guild_id}):
            self.blacklist_cache[guild_id][doc["item"]] = doc["match_type"]
        async for doc in self.whitelist_collection.find({"guild_id": guild_id}):
            self.whitelist_cache[guild_id][doc["item"]] = doc["match_type"]

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self._load_cache(guild.id)
        await self.bot.tree.sync(guild=guild)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        gid = message.guild.id
        if gid not in self.blacklist_cache:
            await self._load_cache(gid)
        content = message.content.lower()
        for item, mt in self.whitelist_cache.get(gid, {}).items():
            if self._matches(content, item, mt):
                return
        for item, mt in self.blacklist_cache.get(gid, {}).items():
            if self._matches(content, item, mt):
                try:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention}, your message was removed because it contained blacklisted content.",
                        delete_after=5
                    )
                except discord.Forbidden:
                    pass
                return

    def _matches(self, content: str, item: str, match_type: str) -> bool:
        try:
            if match_type == MatchType.CONTAINS.value:
                return item.lower() in content
            if match_type == MatchType.EXACT.value:
                return content == item.lower()
            if match_type == MatchType.STARTS_WITH.value:
                return content.startswith(item.lower())
            if match_type == MatchType.ENDS_WITH.value:
                return content.endswith(item.lower())
            if match_type == MatchType.REGEX.value:
                return bool(re.search(item, content, re.IGNORECASE))
        except:
            return False
        return False

    # Single-item slash commands

    @app_commands.command(name="blacklist", description="Add or update an item in the blacklist")
    @app_commands.describe(item="The word/phrase/link to blacklist", match_type="Match type", reason="Reason for blacklisting")
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value=MatchType.CONTAINS.value),
        app_commands.Choice(name="Exact", value=MatchType.EXACT.value),
        app_commands.Choice(name="Starts With", value=MatchType.STARTS_WITH.value),
        app_commands.Choice(name="Ends With", value=MatchType.ENDS_WITH.value),
        app_commands.Choice(name="Regex", value=MatchType.REGEX.value)
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def blacklist(self, interaction: discord.Interaction, item: str, match_type: str = MatchType.CONTAINS.value, reason: Optional[str] = None):
        gid = interaction.guild.id
        await self.whitelist_collection.delete_one({"guild_id": gid, "item": item})
        self.whitelist_cache.get(gid, {}).pop(item, None)
        await self.blacklist_collection.update_one({"guild_id": gid, "item": item}, {"$set": {"match_type": match_type, "reason": reason, "added_by": interaction.user.id, "added_at": discord.utils.utcnow().isoformat()}}, upsert=True)
        self.blacklist_cache.setdefault(gid, {})[item] = match_type
        await interaction.response.send_message(f"🚫 Blacklisted `{item}` ({match_type})", ephemeral=True)

    @app_commands.command(name="whitelist", description="Add or update an item in the whitelist")
    @app_commands.describe(item="The word/phrase/link to whitelist", match_type="Match type", reason="Reason for whitelisting")
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value=MatchType.CONTAINS.value),
        app_commands.Choice(name="Exact", value=MatchType.EXACT.value),
        app_commands.Choice(name="Starts With", value=MatchType.STARTS_WITH.value),
        app_commands.Choice(name="Ends With", value=MatchType.ENDS_WITH.value),
        app_commands.Choice(name="Regex", value=MatchType.REGEX.value)
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def whitelist(self, interaction: discord.Interaction, item: str, match_type: str = MatchType.CONTAINS.value, reason: Optional[str] = None):
        gid = interaction.guild.id
        await self.blacklist_collection.delete_one({"guild_id": gid, "item": item})
        self.blacklist_cache.get(gid, {}).pop(item, None)
        await self.whitelist_collection.update_one({"guild_id": gid, "item": item}, {"$set": {"match_type": match_type, "reason": reason, "added_by": interaction.user.id, "added_at": discord.utils.utcnow().isoformat()}}, upsert=True)
        self.whitelist_cache.setdefault(gid, {})[item] = match_type
        await interaction.response.send_message(f"✅ Whitelisted `{item}` ({match_type})", ephemeral=True)

    # Bulk slash commands

    @app_commands.command(name="bulk_blacklist", description="Add or update multiple items to the blacklist")
    @app_commands.describe(items="Comma-separated list of items to blacklist", match_type="Match type for all items", reason="Optional reason applied to all items")
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value=MatchType.CONTAINS.value),
        app_commands.Choice(name="Exact", value=MatchType.EXACT.value),
        app_commands.Choice(name="Starts With", value=MatchType.STARTS_WITH.value),
        app_commands.Choice(name="Ends With", value=MatchType.ENDS_WITH.value),
        app_commands.Choice(name="Regex", value=MatchType.REGEX.value)
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def bulk_blacklist(self, interaction: discord.Interaction, items: str, match_type: str = MatchType.CONTAINS.value, reason: Optional[str] = None):
        gid = interaction.guild.id
        entries = [entry.strip() for entry in items.split(',') if entry.strip()]
        processed: List[str] = []
        for item in entries:
            # Remove from whitelist
            await self.whitelist_collection.delete_one({"guild_id": gid, "item": item})
            self.whitelist_cache.get(gid, {}).pop(item, None)
            # Upsert blacklist
            await self.blacklist_collection.update_one({"guild_id": gid, "item": item}, {"$set": {"match_type": match_type, "reason": reason, "added_by": interaction.user.id, "added_at": discord.utils.utcnow().isoformat()}}, upsert=True)
            self.blacklist_cache.setdefault(gid, {})[item] = match_type
            processed.append(item)
        await interaction.response.send_message(f"🚫 Bulk blacklisted: {', '.join(processed)} ({match_type})", ephemeral=True)

    @app_commands.command(name="bulk_whitelist", description="Add or update multiple items to the whitelist")
    @app_commands.describe(items="Comma-separated list of items to whitelist", match_type="Match type for all items", reason="Optional reason applied to all items")
    @app_commands.choices(match_type=[
        app_commands.Choice(name="Contains", value=MatchType.CONTAINS.value),
        app_commands.Choice(name="Exact", value=MatchType.EXACT.value),
        app_commands.Choice(name="Starts With", value=MatchType.STARTS_WITH.value),
        app_commands.Choice(name="Ends With", value=MatchType.ENDS_WITH.value),
        app_commands.Choice(name="Regex", value=MatchType.REGEX.value)
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def bulk_whitelist(self, interaction: discord.Interaction, items: str, match_type: str = MatchType.CONTAINS.value, reason: Optional[str] = None):
        gid = interaction.guild.id
        entries = [entry.strip() for entry in items.split(',') if entry.strip()]
        processed: List[str] = []
        for item in entries:
            # Remove from blacklist
            await self.blacklist_collection.delete_one({"guild_id": gid, "item": item})
            self.blacklist_cache.get(gid, {}).pop(item, None)
            # Upsert whitelist
            await self.whitelist_collection.update_one({"guild_id": gid, "item": item}, {"$set": {"match_type": match_type, "reason": reason, "added_by": interaction.user.id, "added_at": discord.utils.utcnow().isoformat()}}, upsert=True)
            self.whitelist_cache.setdefault(gid, {})[item] = match_type
            processed.append(item)
        await interaction.response.send_message(f"✅ Bulk whitelisted: {', '.join(processed)} ({match_type})", ephemeral=True)

    # Updated paginated commands
    
    @app_commands.command(name="show_blacklisted", description="Show all blacklisted items")
    @app_commands.describe(
        match_type="Filter by match type (default: all)",
        page="Page number to view",
        ephemeral="Whether to show only to you"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="All", value="all"),
        app_commands.Choice(name="Contains", value=MatchType.CONTAINS.value),
        app_commands.Choice(name="Exact", value=MatchType.EXACT.value),
        app_commands.Choice(name="Starts With", value=MatchType.STARTS_WITH.value),
        app_commands.Choice(name="Ends With", value=MatchType.ENDS_WITH.value),
        app_commands.Choice(name="Regex", value=MatchType.REGEX.value)
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def show_blacklisted(self, interaction: discord.Interaction, match_type: str = "all", page: int = 1, ephemeral: bool = True):
        gid = interaction.guild.id
        items = await self.blacklist_collection.find({"guild_id": gid}).to_list(length=None)
        
        if not items:
            return await interaction.response.send_message("No blacklisted items found.", ephemeral=ephemeral)
        
        # Paginate with 25 items per page (Discord's limit for embed fields)
        items_per_page = 25
        
        # Validate page number
        filtered_items = items if match_type == "all" else [item for item in items if item.get("match_type") == match_type]
        total_pages = max(1, math.ceil(len(filtered_items) / items_per_page))
        page = max(1, min(page, total_pages))  # Ensure page is in valid range
        
        # Create paginator view
        view = PaginationView(
            items=items,
            match_type=match_type,
            page=page,
            items_per_page=items_per_page,
            is_blacklist=True,
            interaction=interaction
        )
        
        # Send the paginated response
        await interaction.response.send_message(
            embed=view.get_embed(), 
            view=view,
            ephemeral=ephemeral
        )
        
        # Store the message for timeout handling
        view.message = await interaction.original_response()

    @app_commands.command(name="show_whitelisted", description="Show all whitelisted items")
    @app_commands.describe(
        match_type="Filter by match type (default: all)", 
        page="Page number to view",
        ephemeral="Whether to show only to you"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="All", value="all"),
        app_commands.Choice(name="Contains", value=MatchType.CONTAINS.value),
        app_commands.Choice(name="Exact", value=MatchType.EXACT.value),
        app_commands.Choice(name="Starts With", value=MatchType.STARTS_WITH.value),
        app_commands.Choice(name="Ends With", value=MatchType.ENDS_WITH.value),
        app_commands.Choice(name="Regex", value=MatchType.REGEX.value)
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def show_whitelisted(self, interaction: discord.Interaction, match_type: str = "all", page: int = 1, ephemeral: bool = True):
        gid = interaction.guild.id
        items = await self.whitelist_collection.find({"guild_id": gid}).to_list(length=None)
        
        if not items:
            return await interaction.response.send_message("No whitelisted items found.", ephemeral=ephemeral)
        
        # Paginate with 25 items per page (Discord's limit for embed fields)
        items_per_page = 25
        
        # Validate page number
        filtered_items = items if match_type == "all" else [item for item in items if item.get("match_type") == match_type]
        total_pages = max(1, math.ceil(len(filtered_items) / items_per_page))
        page = max(1, min(page, total_pages))  # Ensure page is in valid range
        
        # Create paginator view
        view = PaginationView(
            items=items,
            match_type=match_type,
            page=page,
            items_per_page=items_per_page,
            is_blacklist=False,
            interaction=interaction
        )
        
        # Send the paginated response
        await interaction.response.send_message(
            embed=view.get_embed(), 
            view=view,
            ephemeral=ephemeral
        )
        
        # Store the message for timeout handling
        view.message = await interaction.original_response()

async def setup(bot: commands.Bot):
    await bot.add_cog(FilterCog(bot))
